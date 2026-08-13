# -*- coding: utf-8 -*-
"""F3 面试会话与 F4 能力报告服务（阶段5：自 api/index.py 机械搬迁，行为不变）。"""
import json
import uuid

from tools.api_errors import ApiError
from tools.contracts import SUBSCORE_DEFAULTS
from tools.database import (
    get_resume_detail,
    load_match,
    load_session,
    save_ability,
    save_session,
    update_session,
)
from tools.interview_engine import InterviewEngine
from tools.rescore import calc_R, compute as rescore_compute, round2

from services.match_service import MATCH_WEIGHTS


# ------------------------------------------------------------------ #

STAR_LABELS = {
    "situation": "情境交代",
    "task": "任务职责",
    "action": "行动过程",
    "result": "结果呈现",
    "metric": "量化数据",
    "reflection": "复盘反思",
}


def build_turn_evaluation(result):
    """将引擎单轮结果转换为前端可展示的 优点/不足/子分 结构。"""
    missing = result.get("missing_elements") or []
    covered = [STAR_LABELS[k] for k in STAR_LABELS if k not in missing]
    return {
        "strengths": covered,
        "weaknesses": [STAR_LABELS.get(k, k) for k in missing],
        "missing_elements": missing,
        "subscores": result.get("subscores"),
        "answer_quote": result.get("answer_quote", ""),
    }


def build_interview_router():
    """Return a router when configured; None otherwise (question-bank fallback)."""
    try:
        from api.index import build_model_router  # runtime lookup keeps monkeypatch compat

        return build_model_router()
    except ApiError:
        return None


def start_interview(body):
    engine = InterviewEngine(model_router=build_interview_router())
    job_profile = body.get("jobProfile") if isinstance(body.get("jobProfile"), dict) else {}
    resume_profile = body.get("resumeProfile") if isinstance(body.get("resumeProfile"), dict) else {}
    match_gaps = body.get("matchGaps") if isinstance(body.get("matchGaps"), list) else []
    session = engine.start(job_profile, resume_profile, match_gaps)
    first = engine.next_question(session)
    if not first or first.get("question") is None:
        raise ApiError("interview_not_started", "未能生成面试问题，请稍后重试。", 503)
    session_id = body.get("session_id") or ("iv_" + uuid.uuid4().hex[:16])
    save_session(session_id, "ASK", session)
    return {
        "session_id": session_id,
        "firstQuestion": first.get("question"),
        "targets": first.get("targets", []),
        "state": session.get("state", "ASK"),
    }


def answer_interview(body):
    session_id = body.get("session_id", "")
    if not session_id:
        raise ApiError("session_required", "缺少面试会话标识。", 422)
    state, payload = load_session(session_id)
    if not payload:
        raise ApiError("session_not_found", "面试会话不存在或已过期。", 404)
    engine = InterviewEngine(model_router=build_interview_router())
    engine.start(
        payload.get("job_profile", {}),
        payload.get("resume_profile", {}),
        payload.get("match_gaps", []),
    )
    # Rebuild the engine session object from the stored payload in-place.
    engine_session = payload
    answer_text = str(body.get("answer_text", "") or "").strip()
    if len(answer_text) < 1:
        raise ApiError("invalid_answer", "回答内容不能为空。", 422)
    asr_confidence = body.get("asr_confidence")
    result = engine.submit_answer(engine_session, answer_text, asr_confidence)
    update_session(session_id, engine_session.get("state", "ASK"), engine_session)
    return {
        "session_id": session_id,
        "turn": result,
        "followUp": result.get("follow_up"),
    }


def end_interview(body):
    session_id = body.get("session_id", "")
    if not session_id:
        raise ApiError("session_required", "缺少面试会话标识。", 422)
    state, payload = load_session(session_id)
    if not payload:
        raise ApiError("session_not_found", "面试会话不存在或已过期。", 404)
    engine = InterviewEngine(model_router=build_interview_router())
    engine_session = payload
    report = engine.end_session(engine_session)
    update_session(session_id, engine_session.get("state", "REPORT"), engine_session)
    return {
        "session_id": session_id,
        "report": report.get("report", ""),
        "score_I": report.get("score_I"),
        "turns": report.get("turns", []),
        "i_subscores": report.get("i_subscores", {}),
    }


# ------------------------------------------------------------------ #
# F4 Ability report (WF-05)
# ------------------------------------------------------------------ #

PLAN_TEMPLATE = [
    (1, "为三条核心经历补充量化证据，无法确认的数字用「待用户核实：」占位", 40, "修订后的三段经历文本"),
    (2, "针对 P0 缺口整理项目复盘笔记", 35, "一页复盘笔记"),
    (3, "按 STAR 结构重写两个面试高频回答", 40, "两份 STAR 回答稿"),
    (4, "针对岗位术语做概念速学并自测", 30, "术语自测清单"),
    (5, "完成一轮五题文字模拟面试并复盘 missing_elements", 45, "面试复盘记录"),
    (6, "根据复盘改写简历自我评价与技能描述", 35, "简历修订版 v2"),
    (7, "复测诊断与匹配，对比 C0 变化并记录真实提升", 40, "复测对比表"),
]

ABILITY_DIMENSIONS = [
    ("job_fit", "岗位契合"),
    ("achievement_evidence", "成果证据"),
    ("professional_expression", "专业表达"),
    ("structured_answer", "结构化回答"),
    ("job_depth", "岗位深度"),
    ("followup_adaptation", "追问适应"),
]


def _latest_diagnosis(session_id):
    detail = get_resume_detail(session_id)
    if not detail or not detail.get("diagnoses"):
        return None
    return detail["diagnoses"][0]


def build_ability_profile(session_id):
    """Aggregate stored R/M/I and produce AbilityProfile + radar option."""
    diag = _latest_diagnosis(session_id)
    match = load_match(session_id)
    state, payload = load_session(session_id)
    turns = (payload or {}).get("turns", []) or []

    if not diag or not match or not turns:
        missing = []
        if not diag:
            missing.append("F1 简历诊断")
        if not match:
            missing.append("F2 岗位匹配")
        if not turns:
            missing.append("F3 模拟面试")
        raise ApiError(
            "insufficient_evidence",
            "能力报告需要先完成：%s。" % "、".join(missing),
            422,
        )

    try:
        profile = json.loads(diag.get("diagnosis_json") or "{}")
    except (TypeError, ValueError):
        profile = {}
    r_subscores = {}
    for key in SUBSCORE_DEFAULTS:
        item = (profile.get("subscores") or {}).get(key)
        r_subscores[key] = item.get("score") if isinstance(item, dict) else None
    r_score = diag.get("score_r")
    if r_score is None:
        try:
            r_score = round2(calc_R(r_subscores))
        except (ValueError, TypeError):
            r_score = None

    m_score = match.get("score_M")
    m_requirements = [
        {"type": item.get("type", "hard"), "status": item.get("status", "unknown")}
        for item in match.get("requirements", [])
        if isinstance(item, dict)
    ]
    m_categories = {}
    for key in MATCH_WEIGHTS:
        item = (match.get("subscores") or {}).get(key)
        m_categories[key] = item.get("score") if isinstance(item, dict) else None

    i_keys = ["structure", "relevance", "specificity", "followup_adaptation", "clarity"]
    sums = {k: 0.0 for k in i_keys}
    counts = {k: 0 for k in i_keys}
    for turn in turns:
        sc = turn.get("subscores")
        if not isinstance(sc, dict):
            continue
        quote = turn.get("answer_quote", "")
        answer = turn.get("answer", "")
        if not quote or not answer or quote not in answer:
            continue
        for k in i_keys:
            v = sc.get(k)
            if isinstance(v, (int, float)):
                sums[k] += v
                counts[k] += 1
    i_subscores = {
        k: round(sums[k] / counts[k], 2) if counts[k] else None
        for k in i_keys
    }
    if not any(v is not None for v in i_subscores.values()):
        raise ApiError("insufficient_evidence", "面试回合证据不足，无法生成能力报告。", 422)

    score_input = {"R": r_subscores, "M": {"requirements": m_requirements}, "I": i_subscores}
    try:
        result = rescore_compute(score_input)
    except (ValueError, KeyError):
        result = {"insufficient_evidence": True}
    if result.get("insufficient_evidence"):
        raise ApiError("insufficient_evidence", "综合证据不足，无法计算 C0；请先完成 F1-F3。", 422)

    c0 = result["C0"]
    dims = []
    for key, name in ABILITY_DIMENSIONS:
        if key == "job_fit":
            value = m_score if m_score is not None else (m_categories.get("hard") or 0)
        elif key == "achievement_evidence":
            value = r_subscores.get("achievement_evidence") or 0
        elif key == "professional_expression":
            value = round(((r_subscores.get("clarity") or 0) + (i_subscores.get("clarity") or 0)) / 2, 1)
        elif key == "structured_answer":
            value = i_subscores.get("structure") or 0
        elif key == "job_depth":
            value = round(((m_categories.get("responsibility") or 0) + (i_subscores.get("relevance") or 0)) / 2, 1)
        else:
            value = i_subscores.get("followup_adaptation") or 0
        dims.append({
            "key": key,
            "name": name,
            "score": round(max(0, min(100, float(value))), 1),
            "evidence": ["F1-F3 规则复算结果"],
        })

    plan = [
        {"day": day, "focus": focus, "minutes": minutes, "artifact": artifact}
        for day, focus, minutes, artifact in PLAN_TEMPLATE
    ]
    ability = {
        "version": "1.0",
        "resume_score": round(r_score, 2) if r_score is not None else None,
        "match_score": round(m_score, 2) if m_score is not None else None,
        "interview_score": round(result["I"], 2),
        "dimensions": dims,
        "baseline": round(c0, 2),
        "scenario_day7": {
            "low": result["C7_low"],
            "high": result["C7_high"],
            "assumptions": [
                "0.30 与 0.70 为 MVP 演示假设，非统计学习参数",
                "假设用户按计划完成每天 30-45 分钟训练并产出 artifact",
                "第七天复测结果才是真实变化",
            ],
        },
        "plan": plan,
    }
    save_ability(session_id, ability)
    return ability, result


# ------------------------------------------------------------------ #
# ------------------------------------------------------------------ #
