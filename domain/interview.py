# -*- coding: utf-8 -*-
"""domain.interview · InterviewSession 的子实体与"面试新事实"入口

    InterviewSession
    ├── TargetJob   本次面试针对的岗位
    ├── Gap         出题依据的缺口
    ├── Question    题目（含类型与优先级来源）
    ├── Answer      用户回答
    ├── Evaluation  本轮评估（训练指标，不是录用概率）
    └── NewEvidence 面试中发现的新经历 —— **必须经用户确认**

出题优先级（产品口径，Phase 3 的引擎按这个顺序取题）：

    P0 Gap > P1 Gap > 关键证据验证 > 行为问题 > 通用题库

两条硬规则：

1. 面试里冒出来的"新经历"不能直接进可信事实：``candidate_evidence()`` 一律产出
   ``status='pending'``（复用 ``domain.evidence.new_evidence`` 的 AI 产出保护）。
2. 本轮评估的分数是**训练指标**，必须显式标注，不能暗示真实招聘成功率。
"""
from datetime import datetime, timezone

from domain.errors import DomainError
from domain.evidence import EvidenceType, new_evidence

#: 出题优先级（由高到低）。引擎按此顺序消费，取不到再降级。
QUESTION_PRIORITY = (
    "p0_gap",
    "p1_gap",
    "evidence_verification",
    "behavioural",
    "generic_bank",
)

QUESTION_PRIORITY_LABELS = {
    "p0_gap": "P0 缺口定向题",
    "p1_gap": "P1 缺口定向题",
    "evidence_verification": "关键证据验证题",
    "behavioural": "行为问题",
    "generic_bank": "通用题库",
}

#: 评分维度 —— 与既有 interview_engine 的 subscores 保持一致。
EVALUATION_DIMENSIONS = (
    "structure",
    "relevance",
    "specificity",
    "clarity",
    "followup_adaptation",
)

#: 训练指标标注，任何展示分数的地方都必须带上。
TRAINING_METRIC_NOTICE = (
    "本轮评分为训练指标，用于对比自己的练习前后变化，不代表真实招聘结果或录用概率。"
)


def _utc_iso():
    return datetime.now(timezone.utc).isoformat()


def question_kind_for(gap_priority):
    """缺口优先级 → 出题类型。"""
    if gap_priority == "P0":
        return "p0_gap"
    if gap_priority == "P1":
        return "p1_gap"
    return None


def priority_rank(kind):
    """返回出题类型的排序位次；未知类型排到最后。"""
    try:
        return QUESTION_PRIORITY.index(kind)
    except ValueError:
        return len(QUESTION_PRIORITY)


def plan_question_order(gaps):
    """把缺口翻译成有序的出题计划（只做排序，不做文案生成）。

    返回 ``[{"kind":..., "gap_id":..., "priority":...}, ...]``。
    """
    ranked = []
    for gap in gaps or []:
        kind = question_kind_for(gap.get("priority"))
        if kind is None:
            continue
        if gap.get("status") not in (None, "open", "doing"):
            continue
        ranked.append({
            "kind": kind,
            "gap_id": gap.get("id"),
            "priority": gap.get("priority"),
        })
    ranked.sort(key=lambda item: (priority_rank(item["kind"]), item["gap_id"] or 0))
    return ranked


def new_question(session_id, text, kind="generic_bank", basis=None, gap_id=None, now=None):
    text = " ".join(str(text or "").split())
    if not text:
        raise DomainError("invalid_question", "题目不能为空。")
    if kind not in QUESTION_PRIORITY:
        raise DomainError(
            "invalid_question_kind",
            "题目类型必须是 %s 之一。" % " / ".join(QUESTION_PRIORITY),
        )
    return {
        "session_id": str(session_id or "").strip(),
        "text": text,
        "kind": kind,
        "basis": (str(basis).strip() or None) if basis else None,
        "gap_id": int(gap_id) if gap_id is not None else None,
        "created_at": now or _utc_iso(),
    }


def new_answer(session_id, turn_id, text, quote=None, now=None):
    """建一条回答记录。``quote`` 必须是 ``text`` 的逐字子串（与引擎的事实锁同口径）。"""
    body = str(text or "").strip()
    if not body:
        raise DomainError("invalid_answer", "回答不能为空。")
    resolved_quote = None
    if quote is not None:
        resolved_quote = str(quote).strip()
        if not resolved_quote or resolved_quote not in body:
            raise DomainError(
                "quote_not_verbatim", "answer_quote 必须是回答原文的逐字子串。"
            )
    return {
        "session_id": str(session_id or "").strip(),
        "turn_id": int(turn_id),
        "text": body,
        "quote": resolved_quote,
        "created_at": now or _utc_iso(),
    }


def evaluation(subscores, missing_elements=None, notice=None):
    """构造本轮评估。分数是训练指标，标注强制带上。"""
    cleaned = {}
    for key in EVALUATION_DIMENSIONS:
        value = (subscores or {}).get(key)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise DomainError("invalid_subscores", "%s 必须是数字。" % key)
        if not 0.0 <= number <= 100.0:
            raise DomainError("invalid_subscores", "%s 必须在 [0, 100] 之间。" % key)
        cleaned[key] = number
    return {
        "subscores": cleaned,
        "missing_elements": [str(item) for item in (missing_elements or [])],
        "notice": notice or TRAINING_METRIC_NOTICE,
        "is_training_metric": True,
    }


def candidate_evidence(session, target_job, claim, quote, answer_text, evidence_type=None,
                       turn_id=None, now=None):
    """面试中发现的新经历 → **待确认**证据。

    绝不返回 confirmed：面试内容由模型从回答里抽取，属于推断，必须由用户确认。

    ``quote`` 必须是 ``answer_text`` 的逐字子串 —— 事实锁在这里同样生效，否则
    "面试新证据"可以凭空生成引文。
    """
    if not session or not session.get("session_id"):
        raise DomainError("session_required", "缺少面试会话。")
    if not target_job or not target_job.get("owner_key"):
        raise DomainError("target_job_required", "面试新证据必须挂在一个目标岗位上。")
    return new_evidence(
        owner_key=target_job["owner_key"],
        evidence_type=evidence_type or EvidenceType.EXPERIENCE.value,
        claim=claim,
        source_type="interview",
        source_id="%s:%s" % (session["session_id"], turn_id if turn_id is not None else "na"),
        source_quote=quote,
        source_text=answer_text,
        confidence=0.6,
        now=now,
    )
