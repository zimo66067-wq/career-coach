# -*- coding: utf-8 -*-
"""domain.application · 投递记录 7 态状态机 + 结果回写

状态（产品负责人指定）：

    considering → preparing → applied → interview → offer
                                       ↘ rejected
    任意状态 → withdrawn

规则：

* 只允许状态机里的迁移；其余组合抛 DomainError（``invalid_transition``）。
* ``rejected`` / ``withdrawn`` 是终态，不能再迁出。
* 结果必须能**反向写入 Career Profile**：``evidence_from_outcome()`` 把一次结果
  转成一条 ``source_type='application_outcome'`` 的**待确认**证据 —— 因为
  "被拒说明我缺 X"是推断，不是用户陈述，必须走 pending → 用户确认。
"""
from datetime import datetime, timezone
from enum import Enum

from domain.errors import DomainError
from domain.evidence import EvidenceType, new_evidence


class ApplicationStatus(str, Enum):
    CONSIDERING = "considering"
    PREPARING = "preparing"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


#: 允许的迁移。终态不出现在键里。
TRANSITIONS = {
    ApplicationStatus.CONSIDERING.value: {
        ApplicationStatus.PREPARING.value,
        ApplicationStatus.WITHDRAWN.value,
    },
    ApplicationStatus.PREPARING.value: {
        ApplicationStatus.APPLIED.value,
        ApplicationStatus.CONSIDERING.value,
        ApplicationStatus.WITHDRAWN.value,
    },
    ApplicationStatus.APPLIED.value: {
        ApplicationStatus.INTERVIEW.value,
        ApplicationStatus.REJECTED.value,
        ApplicationStatus.WITHDRAWN.value,
    },
    ApplicationStatus.INTERVIEW.value: {
        ApplicationStatus.OFFER.value,
        ApplicationStatus.REJECTED.value,
        ApplicationStatus.WITHDRAWN.value,
    },
    ApplicationStatus.OFFER.value: {
        ApplicationStatus.WITHDRAWN.value,
    },
    ApplicationStatus.REJECTED.value: set(),
    ApplicationStatus.WITHDRAWN.value: set(),
}

TERMINAL_STATUSES = frozenset({
    ApplicationStatus.REJECTED.value,
    ApplicationStatus.WITHDRAWN.value,
})

#: 历史数据里可能出现过的写法 → 7 态。API 从未写过 status（默认 'applied'），
#: 这里只为脏数据兜底，每条映射都在 migration 里记录计数。
LEGACY_STATUS_MAP = {
    "saved": ApplicationStatus.PREPARING.value,
    "draft": ApplicationStatus.PREPARING.value,
    "pending": ApplicationStatus.CONSIDERING.value,
    "considering": ApplicationStatus.CONSIDERING.value,
    "preparing": ApplicationStatus.PREPARING.value,
    "applied": ApplicationStatus.APPLIED.value,
    "submitted": ApplicationStatus.APPLIED.value,
    "done": ApplicationStatus.APPLIED.value,
    "interview": ApplicationStatus.INTERVIEW.value,
    "interviewing": ApplicationStatus.INTERVIEW.value,
    "in_review": ApplicationStatus.INTERVIEW.value,
    "offer": ApplicationStatus.OFFER.value,
    "rejected": ApplicationStatus.REJECTED.value,
    "withdrawn": ApplicationStatus.WITHDRAWN.value,
    "cancelled": ApplicationStatus.WITHDRAWN.value,
}

#: 未知历史值的兜底目标 —— 保持"已投递"这一最保守的历史默认。
LEGACY_FALLBACK_STATUS = ApplicationStatus.APPLIED.value

#: 结果类型（反向写入用）。
OUTCOME_VALUES = (
    "applied",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
    "no_response",
)

OUTCOME_LABELS = {
    "applied": "已投递",
    "interview": "进入面试",
    "offer": "拿到 offer",
    "rejected": "被拒",
    "withdrawn": "主动撤回",
    "no_response": "无回复",
}

#: 结果 → 状态的推进（用于一次结果同时更新申请状态）。
OUTCOME_STATUS_MAP = {
    "applied": ApplicationStatus.APPLIED.value,
    "interview": ApplicationStatus.INTERVIEW.value,
    "offer": ApplicationStatus.OFFER.value,
    "rejected": ApplicationStatus.REJECTED.value,
    "withdrawn": ApplicationStatus.WITHDRAWN.value,
    "no_response": None,
}


def _utc_iso():
    return datetime.now(timezone.utc).isoformat()


def _status(value):
    raw = value.value if isinstance(value, Enum) else str(value or "").strip()
    allowed = {item.value for item in ApplicationStatus}
    if raw not in allowed:
        raise DomainError(
            "invalid_status", "申请状态必须是 %s 之一，收到 %r。" % (" / ".join(sorted(allowed)), value)
        )
    return raw


def normalize_legacy_status(value):
    """把历史/脏状态规范化到 7 态；返回 ``(status, was_known)``。"""
    raw = str(value or "").strip().lower()
    if raw in LEGACY_STATUS_MAP:
        return LEGACY_STATUS_MAP[raw], True
    return LEGACY_FALLBACK_STATUS, False


def can_transition(current, target):
    current = _status(current)
    target = _status(target)
    if current == target:
        return True
    return target in TRANSITIONS.get(current, set())


def transition(current, target):
    """推进状态；非法迁移抛 ``invalid_transition``。"""
    current = _status(current)
    target = _status(target)
    if current == target:
        return target
    if target not in TRANSITIONS.get(current, set()):
        raise DomainError(
            "invalid_transition",
            "申请状态不允许从 %s 直接变为 %s。" % (current, target),
        )
    return target


def new_application(session_id, owner_key, company, position, cover_letter,
                    status=ApplicationStatus.PREPARING.value, target_job_id=None, now=None):
    """建一条申请记录。

    新建默认是 ``preparing``（而不是 ``applied``）：记录一条投递前必须先有材料，
    真正的"已投递"应当由用户显式确认（原实现默认 ``applied`` 会凭空断言已投递）。
    """
    owner = str(owner_key or "").strip()
    if not owner:
        raise DomainError("missing_owner_key", "owner_key 不能为空。")
    if not str(company or "").strip() or not str(position or "").strip():
        raise DomainError("invalid_application", "公司与职位不能为空。")
    if len(str(cover_letter or "").strip()) < 10:
        raise DomainError("invalid_application", "求职信内容不完整。")
    stamp = now or _utc_iso()
    return {
        "session_id": str(session_id or "").strip(),
        "owner_key": owner,
        "company": str(company).strip(),
        "position": str(position).strip(),
        "cover_letter": str(cover_letter).strip(),
        "status": _status(status),
        "target_job_id": int(target_job_id) if target_job_id is not None else None,
        "created_at": stamp,
    }


def record_outcome(application, outcome, note=None, now=None):
    """记录一次申请结果，返回 ``(outcome_record, next_status)``。

    ``next_status`` 为 None 表示该结果不改变申请状态（例如 ``no_response``）。
    """
    raw = str(outcome or "").strip().lower()
    if raw not in OUTCOME_VALUES:
        raise DomainError(
            "invalid_outcome",
            "结果必须是 %s 之一，收到 %r。" % (" / ".join(OUTCOME_VALUES), outcome),
        )
    if not application or application.get("id") is None:
        raise DomainError("application_required", "缺少申请记录。")

    stamp = now or _utc_iso()
    record = {
        "application_id": int(application["id"]),
        "outcome": raw,
        "note": (str(note).strip() or None) if note else None,
        "recorded_at": stamp,
    }
    next_status = OUTCOME_STATUS_MAP[raw]
    return record, next_status


def evidence_from_outcome(application, outcome, claim=None, note=None, now=None):
    """结果 → 待确认证据（反向写入 Career Profile）。

    被拒/拿 offer 都会产生"我缺什么 / 我强在哪"的**推断**，因此 source_type 是
    ``application_outcome``，状态必然是 ``pending``；用户确认后才进入可信事实。
    """
    raw = str(outcome or "").strip().lower()
    if raw not in OUTCOME_VALUES:
        raise DomainError(
            "invalid_outcome",
            "结果必须是 %s 之一，收到 %r。" % (" / ".join(OUTCOME_VALUES), outcome),
        )
    if not application or not application.get("owner_key"):
        raise DomainError("application_required", "缺少申请记录。")

    company = application.get("company") or "该单位"
    position = application.get("position") or "该岗位"
    label = OUTCOME_LABELS[raw]
    quote = str(note or "").strip() or ("%s · %s：%s" % (company, position, label))
    text = claim or "申请 %s 的 %s，结果为「%s」。" % (company, position, label)

    return new_evidence(
        owner_key=application["owner_key"],
        evidence_type=EvidenceType.EXPERIENCE.value,
        claim=text,
        source_type="application_outcome",
        source_id=str(application.get("id")),
        source_quote=quote,
        confidence=0.7,
        now=now,
    )
