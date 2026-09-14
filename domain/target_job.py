# -*- coding: utf-8 -*-
"""domain.target_job · TargetJob / JobRequirement / EvidenceMatch / Gap / Decision

    TargetJob
    ├── JobRequirement   JD 拆出的要求（类型与既有 match_service 完全一致）
    ├── EvidenceMatch    某条要求 ↔ 某条证据的四态判定
    ├── Gap              未满足的要求 → 可执行的补强动作
    ├── Decision         APPLY / STRETCH / PASS（透明规则，见 decide）
    └── Application      投递记录（见 domain.application）

口径与既有实现对齐，不新造词：

* 要求类型 = ``hard | responsibility | preferred | terminology``（同 ``match_service``）
* 匹配四态 = ``covered | weak | missing | unknown``（同 ``tools.match_requirements.judge``）
* 缺口优先级 = ``P0 | P1 | P2``（hard→P0，responsibility→P1，其余→P2）

Decision 规则（**必须透明**，因此写成可读谓词而不是权重求和）：

* **PASS**：存在未解决的 **P0** 缺口 —— ``priority_for`` 把 hard 要求唯一映射成 P0，
  所以 P0 就是"短期无法补齐的关键门槛"。
* **STRETCH**：没有未解决的 P0，但存在未解决的 **P1** 缺口（岗位职责级），
  可由已有证据重写或短期补强。
* **APPLY**：不存在未解决的 P0/P1 缺口 —— 关键要求都有真实证据。

任何 Decision 都必须至少引用 3 条具体依据（DoD #9）。
"""
from datetime import datetime, timezone
from enum import Enum

from domain.errors import DomainError

REQUIREMENT_TYPES = ("hard", "responsibility", "preferred", "terminology")
MATCH_STATUSES = ("covered", "weak", "missing", "unknown")
GAP_PRIORITIES = ("P0", "P1", "P2")
GAP_TYPES = ("missing", "weak")

#: 未解决的缺口 —— 只有 open / doing 参与 Decision 判定。
OPEN_GAP_STATUSES = ("open", "doing")

#: Decision 至少要引用几条依据。
MIN_DECISION_CITATIONS = 3

REQUIREMENT_LABELS = {
    "hard": "硬性要求",
    "responsibility": "岗位职责",
    "preferred": "加分项",
    "terminology": "术语与工具",
}


class Decision(str, Enum):
    APPLY = "APPLY"
    STRETCH = "STRETCH"
    PASS = "PASS"


def _utc_iso():
    return datetime.now(timezone.utc).isoformat()


def _one_of(value, allowed, field):
    raw = value.value if isinstance(value, Enum) else str(value or "").strip()
    if raw not in allowed:
        raise DomainError(
            "invalid_%s" % field,
            "%s 必须是 %s 之一，收到 %r。" % (field, " / ".join(allowed), value),
        )
    return raw


def priority_for(requirement_type):
    """要求类型 → 缺口优先级。与既有 task/match 实现的映射保持一致。"""
    kind = _one_of(requirement_type, REQUIREMENT_TYPES, "requirement_type")
    if kind == "hard":
        return "P0"
    if kind == "responsibility":
        return "P1"
    return "P2"


def new_target_job(owner_key, session_id=None, company=None, position=None, jd_text=None, now=None):
    owner = str(owner_key or "").strip()
    if not owner:
        raise DomainError("missing_owner_key", "owner_key 不能为空。")
    stamp = now or _utc_iso()
    return {
        "owner_key": owner,
        "session_id": (str(session_id).strip() or None) if session_id else None,
        "company": (str(company).strip() or None) if company else None,
        "position": (str(position).strip() or None) if position else None,
        "jd_text": jd_text or None,
        "job_profile_json": None,
        "status": "open",
        "created_at": stamp,
        "updated_at": stamp,
    }


def requirement_from_profile_item(target_job_id, item, ordinal=0, now=None):
    """把 JobProfile 里的一条 requirement 落成领域记录（保留来源 span）。"""
    import json

    if not isinstance(item, dict):
        raise DomainError("invalid_requirement", "requirement 必须是对象。")
    text = str(item.get("text") or "").strip()
    if not text:
        raise DomainError("invalid_requirement", "requirement.text 不能为空。")
    req_key = str(item.get("id") or "").strip() or "req_%02d" % (ordinal + 1)
    return {
        "target_job_id": int(target_job_id),
        "req_key": req_key,
        "req_type": _one_of(item.get("type", "hard"), REQUIREMENT_TYPES, "req_type"),
        "text": text,
        "ordinal": int(ordinal),
        "source_span_json": json.dumps(item.get("source_span"), ensure_ascii=False)
        if item.get("source_span") else None,
        "created_at": now or _utc_iso(),
    }


def new_evidence_match(requirement_id, evidence_id, match_status, rationale=None, now=None):
    return {
        "requirement_id": int(requirement_id),
        "evidence_id": int(evidence_id) if evidence_id is not None else None,
        "match_status": _one_of(match_status, MATCH_STATUSES, "match_status"),
        "rationale": (str(rationale).strip() or None) if rationale else None,
        "created_at": now or _utc_iso(),
    }


def gap_from_requirement(
    target_job_id,
    requirement,
    match_status,
    reason=None,
    missing_evidence=None,
    action=None,
    expected_artifact=None,
    retest=None,
    now=None,
):
    """按 Gap → Reason → Current Evidence → Missing Evidence → Action → Artifact → Retest 建缺口。

    ``covered`` / ``unknown`` 的要求不产生缺口（unknown 是"材料不足无法判定"，
    属于要补材料，而不是要补能力）。
    """
    status = _one_of(match_status, MATCH_STATUSES, "match_status")
    if status in ("covered", "unknown"):
        raise DomainError(
            "no_gap_for_status",
            "只有 weak / missing 的要求才会生成缺口，收到 %s。" % status,
        )
    req_type = requirement.get("req_type") or requirement.get("type") or "hard"
    stamp = now or _utc_iso()
    return {
        "target_job_id": int(target_job_id),
        "requirement_id": requirement.get("id"),
        "gap_type": "missing" if status == "missing" else "weak",
        "priority": priority_for(req_type),
        "reason": reason or ("该要求目前%s。" % ("没有对应证据" if status == "missing" else "只有弱证据")),
        "current_evidence": requirement.get("evidence") or None,
        "missing_evidence": missing_evidence,
        "action": action,
        "expected_artifact": expected_artifact,
        "retest": retest,
        "status": "open",
        "created_at": stamp,
        "updated_at": stamp,
    }


def open_gaps(gaps):
    return [g for g in (gaps or []) if g.get("status") in OPEN_GAP_STATUSES]


def open_priorities(gaps):
    """当前未解决缺口的优先级集合。"""
    return {g.get("priority") for g in open_gaps(gaps)}


def expected_decision(gaps):
    """透明规则的唯一实现：给定当前缺口，应当得出哪个 Decision。

    优先级由 ``priority_for`` 唯一决定（hard→P0、responsibility→P1、其余→P2），
    所以判定只需要看优先级，不需要再回查要求类型 —— 多一层类型过滤只会把
    「P0 硬性缺口」误判成 STRETCH。
    """

    priorities = open_priorities(gaps)
    if "P0" in priorities:
        return Decision.PASS.value
    if "P1" in priorities:
        return Decision.STRETCH.value
    return Decision.APPLY.value


def decide(target_job_id, decision, citations, rationale=None, gaps=None, now=None):
    """生成一条 TargetJob Decision；不满足条件直接抛 DomainError。

    ``citations`` 是依据列表（requirement.req_key / evidence id / 缺口说明），
    至少 ``MIN_DECISION_CITATIONS`` 条且不重复。
    """
    import json

    value = _one_of(decision, tuple(item.value for item in Decision), "decision")
    items = [str(item).strip() for item in (citations or [])]
    if len(items) < MIN_DECISION_CITATIONS:
        raise DomainError(
            "insufficient_citations",
            "关键判断至少需要 %d 条依据，当前只有 %d 条。" % (MIN_DECISION_CITATIONS, len(items)),
        )
    if any(not item for item in items):
        raise DomainError("invalid_citation", "依据不允许为空字符串。")
    if len(set(items)) != len(items):
        raise DomainError("duplicate_citation", "依据不允许重复。")

    if gaps is not None:
        expected = expected_decision(gaps)
        if value != expected:
            raise DomainError(
                "decision_inconsistent",
                "当前缺口分布应当得出 %s，而不是 %s（判定规则见 domain/target_job.py）。" % (expected, value),
            )

    return {
        "target_job_id": int(target_job_id),
        "decision": value,
        "rationale_json": json.dumps(
            {"citations": items, "rationale": rationale}, ensure_ascii=False
        ),
        "created_at": now or _utc_iso(),
    }
