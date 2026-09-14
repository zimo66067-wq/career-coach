# -*- coding: utf-8 -*-
"""domain.evidence · CareerEvidence：个人职业事实的唯一可信来源

字段（与 ``career_evidence`` 表一一对应）：

    id, owner_key, evidence_type, claim, source_type, source_id, source_quote,
    confidence, status, user_confirmed, created_at, updated_at, confirmed_at

三条硬规则（全部有测试覆盖）：

1. **可回指来源**：``source_quote`` 必填；若调用方给了 ``source_text``，则 quote 必须是它的
   逐字子串 —— 与 F1 诊断的 ``source_span`` 事实锁同口径，防止 AI 编造引文。
2. **AI 不能直接写入已确认事实**：``source_type`` 属于模型产出（resume / interview /
   application_outcome）时，``status`` 只能是 ``pending``。只有用户本人输入的
   ``user_input`` 才允许直接 ``confirmed``。
3. **改动需要重新确认**：任何对 ``confirmed`` 证据正文的修改都会把它退回 ``pending``，
   除非调用方显式表示"这次修改就是用户本人做的"。

记录用普通 dict 表示（与数据库行同形），因此本模块不 import 任何 I/O 依赖。
"""
from datetime import datetime, timezone
from enum import Enum

from domain.errors import DomainError

MAX_CLAIM_CHARS = 300
MAX_QUOTE_CHARS = 500


class EvidenceType(str, Enum):
    """证据类别，与 CareerProfile 的五个分支一一对应。"""

    EXPERIENCE = "experience"
    SKILL = "skill"
    ACHIEVEMENT = "achievement"
    STORY = "story"
    PREFERENCE = "preference"


class EvidenceSourceType(str, Enum):
    """允许的来源白名单（不得扩到白名单之外）。"""

    RESUME = "resume"
    INTERVIEW = "interview"
    USER_INPUT = "user_input"
    APPLICATION_OUTCOME = "application_outcome"


class EvidenceStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


#: 由模型抽取或推断产生的来源 —— 一律不得直接写成 confirmed。
AI_PRODUCED_SOURCES = frozenset({
    EvidenceSourceType.RESUME.value,
    EvidenceSourceType.INTERVIEW.value,
    EvidenceSourceType.APPLICATION_OUTCOME.value,
})

#: 唯一允许直接落成 confirmed 的来源：用户本人陈述。
USER_ASSERTED_SOURCES = frozenset({EvidenceSourceType.USER_INPUT.value})

#: 需要外部定位对象的来源：没有 source_id 就无法回指，视为不可核验。
SOURCES_REQUIRING_ID = frozenset({
    EvidenceSourceType.RESUME.value,
    EvidenceSourceType.INTERVIEW.value,
    EvidenceSourceType.APPLICATION_OUTCOME.value,
})


def _utc_iso():
    return datetime.now(timezone.utc).isoformat()


def _enum_value(value, enum_cls, field):
    raw = value.value if isinstance(value, enum_cls) else str(value or "").strip()
    allowed = {item.value for item in enum_cls}
    if raw not in allowed:
        raise DomainError(
            "invalid_%s" % field,
            "%s 必须是 %s 之一，收到 %r。" % (field, " / ".join(sorted(allowed)), value),
        )
    return raw


def _compact(value, limit, field):
    text = " ".join(str(value or "").split())
    if not text:
        raise DomainError("missing_%s" % field, "%s 不能为空。" % field)
    if len(text) > limit:
        raise DomainError("oversized_%s" % field, "%s 超过 %d 字。" % (field, limit))
    return text


def _confidence(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise DomainError("invalid_confidence", "confidence 必须是 0-1 之间的数字。")
    if not 0.0 <= number <= 1.0:
        raise DomainError("invalid_confidence", "confidence 必须在 [0, 1] 之间。")
    return number


def new_evidence(
    owner_key,
    evidence_type,
    claim,
    source_type,
    source_quote,
    source_id=None,
    source_text=None,
    confidence=0.5,
    status=None,
    now=None,
):
    """构造一条证据记录；返回可直接落库的 dict。

    ``status`` 默认由来源决定：``user_input`` → ``confirmed``，其余 → ``pending``。
    若显式传入 ``confirmed`` 而来源属于模型产出，直接抛 DomainError。
    """
    owner = _compact(owner_key, 120, "owner_key")
    kind = _enum_value(evidence_type, EvidenceType, "evidence_type")
    source = _enum_value(source_type, EvidenceSourceType, "source_type")
    text = _compact(claim, MAX_CLAIM_CHARS, "claim")
    quote = _compact(source_quote, MAX_QUOTE_CHARS, "source_quote")

    if source in SOURCES_REQUIRING_ID and not str(source_id or "").strip():
        raise DomainError(
            "missing_source_id",
            "来源为 %s 的证据必须带 source_id，否则无法回指。" % source,
        )

    if source_text is not None:
        # 事实锁：引文必须是来源原文的逐字子串。
        if quote not in str(source_text):
            raise DomainError(
                "quote_not_verbatim",
                "source_quote 必须是来源原文的逐字子串（当前引文在来源中找不到）。",
            )

    default_status = (
        EvidenceStatus.CONFIRMED.value if source in USER_ASSERTED_SOURCES
        else EvidenceStatus.PENDING.value
    )
    resolved = _enum_value(status or default_status, EvidenceStatus, "status")

    if source in AI_PRODUCED_SOURCES and resolved == EvidenceStatus.CONFIRMED.value:
        raise DomainError(
            "evidence_requires_confirmation",
            "由模型产出（%s）的证据不得直接写入 confirmed，必须先 pending 再由用户确认。" % source,
        )

    stamp = now or _utc_iso()
    confirmed = resolved == EvidenceStatus.CONFIRMED.value
    return {
        "owner_key": owner,
        "evidence_type": kind,
        "claim": text,
        "source_type": source,
        "source_id": (str(source_id).strip() or None) if source_id is not None else None,
        "source_quote": quote,
        "confidence": _confidence(confidence),
        "status": resolved,
        "user_confirmed": 1 if confirmed else 0,
        "created_at": stamp,
        "updated_at": stamp,
        "confirmed_at": stamp if confirmed else None,
    }


def confirm(record, now=None):
    """用户确认：pending → confirmed。已是 confirmed 时幂等返回。"""
    status = record.get("status")
    if status == EvidenceStatus.REJECTED.value:
        raise DomainError("evidence_rejected", "已否决的证据不能直接确认，请先修改正文。")
    if status == EvidenceStatus.CONFIRMED.value:
        return dict(record)
    stamp = now or _utc_iso()
    updated = dict(record)
    updated["status"] = EvidenceStatus.CONFIRMED.value
    updated["user_confirmed"] = 1
    updated["confirmed_at"] = stamp
    updated["updated_at"] = stamp
    return updated


def reject(record, now=None):
    """用户否决：pending → rejected，并撤销确认标记。"""
    stamp = now or _utc_iso()
    updated = dict(record)
    updated["status"] = EvidenceStatus.REJECTED.value
    updated["user_confirmed"] = 0
    updated["confirmed_at"] = None
    updated["updated_at"] = stamp
    return updated


def edit_claim(record, claim, source_quote=None, confirmed_by_user=False, now=None):
    """修改证据正文。

    已确认的证据被修改后**退回 pending**，除非 ``confirmed_by_user=True``
    表示这次修改由用户本人做出并当场确认。这条规则防止"确认过的旧文案被悄悄替换"。
    """
    updated = dict(record)
    updated["claim"] = _compact(claim, MAX_CLAIM_CHARS, "claim")
    if source_quote is not None:
        updated["source_quote"] = _compact(source_quote, MAX_QUOTE_CHARS, "source_quote")
    stamp = now or _utc_iso()
    updated["updated_at"] = stamp
    if record.get("status") == EvidenceStatus.CONFIRMED.value and not confirmed_by_user:
        updated["status"] = EvidenceStatus.PENDING.value
        updated["user_confirmed"] = 0
        updated["confirmed_at"] = None
    return updated


def is_usable(record):
    """只有"已确认"的证据才算可信事实，才能喂给改写 / 匹配 / 面试 / 求职信。"""
    return (
        record.get("status") == EvidenceStatus.CONFIRMED.value
        and int(record.get("user_confirmed") or 0) == 1
    )


def usable(records):
    return [item for item in records if is_usable(item)]


def pending(records):
    return [item for item in records if item.get("status") == EvidenceStatus.PENDING.value]


def verify_quote(record, source_text):
    """独立的事实锁校验（落库后仍可复查）。"""
    quote = str(record.get("source_quote") or "")
    return bool(quote) and quote in str(source_text or "")
