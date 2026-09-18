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
* 匹配四态 = ``covered | weak | missing | unknown``（同 ``domain.match_requirements.judge``）
* 缺口优先级 = ``P0 | P1 | P2``（hard→P0，responsibility→P1，其余→P2）

Decision 规则（**必须透明**，因此写成可读谓词而不是权重求和）：

* **PASS**：存在未解决的 P0 缺口，**且该缺口不可短期解决**（``blocking``）——
  典型是学历 / 专业 / 证书这类结构性门槛。
* **STRETCH**：其余存在未解决 P0/P1 缺口的情形。**硬性要求只是弱命中（weak）
  也属于这里** —— weak 恰恰意味着"材料能对上但不够强"，可由已有证据重写或短期补强。
* **APPLY**：不存在未解决的 P0/P1 缺口 —— 关键要求都有真实证据。

``blocking`` 由服务层判定并入库（服务层才拿得到要求原文），域层只消费，
因此判定规则可以完全从 ``gaps`` 表复现。

任何 Decision 都必须至少引用 3 条具体依据（DoD #9）。
"""
from datetime import datetime, timezone
from enum import Enum

from domain.errors import DomainError

REQUIREMENT_TYPES = ("hard", "responsibility", "preferred", "terminology")
MATCH_STATUSES = ("covered", "weak", "missing", "unknown")
GAP_PRIORITIES = ("P0", "P1", "P2")

#: 缺口类型。
#:
#: ``unverifiable`` 对应匹配结果 ``unknown``：**材料完全对不上，无法判定**。
#: 它必须算缺口 —— 否则"我们找不到任何相关材料"会被当成"满足要求"，
#: 于是输出 APPLY（"关键要求均有已确认证据支撑"），那是假话。
#: 但它不是 ``blocking``（补材料即可判定），所以推 STRETCH 而不是 PASS。
GAP_TYPES = ("missing", "weak", "unverifiable")

#: 未解决的缺口 —— 只有 open / doing 参与 Decision 判定。
OPEN_GAP_STATUSES = ("open", "doing")

#: 缺口生命周期。
#:
#: ``cleared`` 表示**该要求现在已被证据覆盖，缺口不再适用**（重新分析时由系统写入）；
#: 它与 ``done``（用户完成了补强动作）语义不同，不能混用 —— 否则报告会显示成
#: "用户解决了它"，而事实只是简历变了。
GAP_STATUSES = ("open", "doing", "done", "dropped", "cleared")
CLEARED_GAP_STATUS = "cleared"

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
    blocking=False,
    now=None,
):
    """按 Gap → Reason → Current Evidence → Missing Evidence → Action → Artifact → Retest 建缺口。

    只有 ``covered`` 不产生缺口。``weak`` → ``weak``、``missing`` → ``missing``、
    ``unknown`` → ``unverifiable``。

    ``unknown`` **必须**算缺口：它是"材料完全对不上"，不是"满足要求"。若把它当无事发生，
    一条关键硬性要求就会既不产生缺口也不阻断，最终输出 APPLY —— 而事实是我们什么都没能核实。

    ``blocking``：该缺口是否**不可短期解决**。判定由服务层给出（它才拿得到要求原文），
    域层只负责消费 —— 这是 APPLY/STRETCH/PASS 区分 PASS 与 STRETCH 的唯一依据。
    """
    status = _one_of(match_status, MATCH_STATUSES, "match_status")
    if status == "covered":
        raise DomainError(
            "no_gap_for_status",
            "已覆盖（covered）的要求不产生缺口，收到 %s。" % status,
        )
    req_type = requirement.get("req_type") or requirement.get("type") or "hard"
    stamp = now or _utc_iso()
    gap_type = "missing" if status == "missing" else ("unverifiable" if status == "unknown" else "weak")
    return {
        "target_job_id": int(target_job_id),
        "requirement_id": requirement.get("id"),
        "gap_type": gap_type,
        "priority": priority_for(req_type),
        "reason": reason or _default_reason(status),
        "current_evidence": requirement.get("evidence") or None,
        "missing_evidence": missing_evidence,
        "action": action,
        "expected_artifact": expected_artifact,
        "retest": retest,
        "status": "open",
        "blocking": 1 if blocking else 0,
        "created_at": stamp,
        "updated_at": stamp,
    }


def _default_reason(match_status):
    if match_status == "missing":
        return "该要求目前没有对应证据。"
    if match_status == "unknown":
        return "材料中找不到与该要求相关的内容，无法判定当前是否满足。"
    return "该要求目前只有弱证据。"


def open_gaps(gaps):
    return [g for g in (gaps or []) if g.get("status") in OPEN_GAP_STATUSES]


def open_priorities(gaps):
    """当前未解决缺口的优先级集合。"""
    return {g.get("priority") for g in open_gaps(gaps)}


def is_blocking_gap(gap):
    """未解决的 **P0 且不可短期解决** 的缺口 —— 只有它才推 PASS。"""
    return gap.get("priority") == "P0" and bool(gap.get("blocking"))


def expected_decision(gaps):
    """透明规则的唯一实现：给定当前缺口，应当得出哪个 Decision。

    规则与产品口径一一对应（见 docs/product-scope.md §10.7）：

    * **PASS**  ⟺ 存在未解决的 P0 缺口 **且该缺口不可短期解决**（如学历 / 专业 / 证书）。
    * **STRETCH** ⟺ 其余存在未解决 P0/P1 缺口的情形 —— 包括"硬性要求只是弱命中"，
      它恰恰是"可由已有证据重写或短期补强"。
    * **APPLY** ⟺ 没有未解决的 P0/P1 缺口。

    ``blocking`` 之所以必须由服务层传入而不能在这里推断：域层拿不到要求原文，
    而"这个缺口能不能短期补上"只有原文能回答。
    """
    open_list = open_gaps(gaps)
    if any(is_blocking_gap(gap) for gap in open_list):
        return Decision.PASS.value
    if any(gap.get("priority") in ("P0", "P1") for gap in open_list):
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
