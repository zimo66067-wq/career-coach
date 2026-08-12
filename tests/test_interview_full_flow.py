# -*- coding: utf-8 -*-
"""test_interview_full_flow.py · 面试引擎全流程（正常/边界/异常）

覆盖：状态机 5 主问题上限（防死循环）、追问每题最多 1 次、
敏感问题替换、模型故障题库降级、通用题池轮换、低 ASR 置信度确认、
end_session 评分与报告、answer_quote 子串校验。
"""
import pytest

from interview_engine import (
    InterviewEngine,
    GENERIC_QUESTIONS,
    MAX_MAIN_QUESTIONS,
    MAX_FOLLOWUPS_PER_QUESTION,
)


def make_session(engine, gaps=None, requirements=None):
    return engine.start(
        {"title": "后端开发工程师", "requirements": requirements or []},
        {"score_R": 73.0},
        gaps or [],
    )


class SensitiveRouter:
    def call(self, _task, _user_input, context=None):
        return {
            "status": "success",
            "output": {"question": "你今年多大？有孩子吗？", "targets": ["forbidden"]},
            "trace_id": "t1",
            "degraded": False,
        }


class BoomRouter:
    def call(self, *_args, **_kwargs):
        raise RuntimeError("provider down")


# ---------------------------------------------------------------- #
# 正常流程：会话初始化
# ---------------------------------------------------------------- #


def test_session_starts_and_filters_gaps():
    engine = InterviewEngine()
    gaps = [
        {"id": "G1", "type": "hard", "text": "缺口A", "status": "missing"},
        {"id": "G2", "type": "hard", "text": "缺口B", "status": "weak"},
        {"id": "G3", "type": "hard", "text": "已覆盖", "status": "covered"},
    ]
    session = make_session(engine, gaps)
    assert session["state"] == "ASK"
    assert [g["id"] for g in session["match_gaps"]] == ["G1", "G2"]


def test_gaps_padded_from_requirements():
    engine = InterviewEngine()
    requirements = [{"id": "J%d" % i, "type": "hard", "text": "要求%d" % i} for i in range(5)]
    session = make_session(engine, [], requirements)
    assert len(session["match_gaps"]) == 5


# ---------------------------------------------------------------- #
# 状态机：主问题上限与上下文持久化
# ---------------------------------------------------------------- #


def test_state_machine_ends_after_five_main_questions():
    engine = InterviewEngine()
    session = make_session(engine)
    done = None
    for _ in range(MAX_MAIN_QUESTIONS):
        done = engine.next_question(session)
        assert done["done"] is False
        assert done["question"]
    done = engine.next_question(session)
    assert done["done"] is True
    assert done["question"] is None
    assert session["current_main"] == MAX_MAIN_QUESTIONS


def test_question_context_persisted_into_turn():
    engine = InterviewEngine()
    session = make_session(engine)
    question = engine.next_question(session)
    result = engine.submit_answer(session, "我在实习中负责接口开发，结果响应时间从 800ms 降到 220ms。")
    assert result["turn_id"] == 1
    turn = session["turns"][0]
    assert turn["question"] == question["question"]
    assert turn["targets"] == question["targets"]
    assert turn["answer_quote"] in turn["answer"]


# ---------------------------------------------------------------- #
# 追问：每题最多 1 次
# ---------------------------------------------------------------- #


def test_followup_capped_at_one_per_question():
    engine = InterviewEngine()
    session = make_session(engine, [{"id": "G1", "type": "hard", "text": "缺口", "status": "weak"}])
    engine.next_question(session)

    first = engine.submit_answer(session, "我做了一个项目，负责开发。")
    assert first["follow_up"] is not None

    engine.submit_followup_answer(session, "补充：结果提升 30%。")
    assert len(session["turns"]) == 2
    assert session["current_followup_count"] == MAX_FOLLOWUPS_PER_QUESTION

    second = engine.submit_answer(session, "再次回答，仍缺少量化数据。")
    assert second["follow_up"] is None, "同一主问题下不应出现第二次追问"


def test_followup_resets_on_next_main_question():
    engine = InterviewEngine()
    session = make_session(engine, [{"id": "G1", "type": "hard", "text": "缺口", "status": "weak"}])
    engine.next_question(session)
    first = engine.submit_answer(session, "我做了一个项目，负责开发。")
    assert first["follow_up"] is not None
    engine.submit_followup_answer(session, "补充：结果提升 30%。")

    engine.next_question(session)
    assert session["current_followup_count"] == 0


# ---------------------------------------------------------------- #
# 异常：敏感问题与模型故障
# ---------------------------------------------------------------- #


def test_sensitive_question_replaced_with_generic():
    engine = InterviewEngine(model_router=SensitiveRouter())
    session = make_session(engine, [{"id": "G1", "type": "hard", "text": "缺口", "status": "weak"}])
    question = engine.next_question(session)
    assert "多大" not in question["question"]
    assert "孩子" not in question["question"]
    assert session["degraded"] is True


def test_router_failure_falls_back_to_question_bank():
    engine = InterviewEngine(model_router=BoomRouter())
    session = make_session(engine, [{"id": "G1", "type": "hard", "text": "缺口", "status": "weak"}])
    question = engine.next_question(session)
    assert question["question"]
    assert session["degraded"] is True
    assert session["router_error"] == "RuntimeError"


def test_generic_question_pool_cycles():
    engine = InterviewEngine()
    session = make_session(engine)
    questions = [engine.next_question(session)["question"] for _ in range(3)]
    assert questions == [q["question"] for q in GENERIC_QUESTIONS]
    fourth = engine.next_question(session)
    assert fourth["question"] == GENERIC_QUESTIONS[0]["question"]


def test_low_asr_confidence_requires_confirmation():
    engine = InterviewEngine()
    session = make_session(engine, [{"id": "G1", "type": "hard", "text": "缺口", "status": "weak"}])
    engine.next_question(session)
    turn_count = len(session["turns"])
    result = engine.submit_answer(session, "语音转写结果。", asr_confidence=0.5)
    assert result["needs_confirmation"] is True
    assert len(session["turns"]) == turn_count, "低置信度结果不应计入轮次"


def test_high_asr_confidence_accepted():
    engine = InterviewEngine()
    session = make_session(engine, [{"id": "G1", "type": "hard", "text": "缺口", "status": "weak"}])
    engine.next_question(session)
    result = engine.submit_answer(session, "我的答案是：负责开发并完成上线，耗时 2 周。", asr_confidence=0.92)
    assert result.get("needs_confirmation") is None or result["needs_confirmation"] is False
    assert len(session["turns"]) == 1


# ---------------------------------------------------------------- #
# 评分与报告
# ---------------------------------------------------------------- #


def test_end_session_scoring_excludes_invalid_turns():
    engine = InterviewEngine()
    session = make_session(engine, [{"id": "G1", "type": "hard", "text": "缺口", "status": "weak"}])
    engine.next_question(session)
    engine.submit_answer(
        session,
        "背景是订单接口慢。任务明确。我加索引并引入缓存，结果从 800ms 降到 220ms，提升显著。",
    )
    engine.next_question(session)
    engine.submit_answer(session, "短答。")
    # 篡改第二轮引用使其不满足子串约束 -> 该轮作废
    session["turns"][1]["answer_quote"] = "不存在的引用"

    report = engine.end_session(session)
    assert report["score_I"] is not None
    assert report["i_subscores"]["structure"] is not None
    valid_turn = session["turns"][0]
    assert abs(report["i_subscores"]["clarity"] - valid_turn["subscores"]["clarity"]) < 0.01
    assert "# Interview Review Report" in report["report"]
    assert "Per-Turn Review" in report["report"]


def test_end_session_without_evidence_returns_insufficient():
    engine = InterviewEngine()
    session = make_session(engine)
    for _ in range(MAX_MAIN_QUESTIONS):
        engine.next_question(session)
    report = engine.end_session(session)
    assert report["score_I"] is None
    assert "insufficient evidence" in report["report"]


def test_sensitive_check_detects_forbidden_terms():
    engine = InterviewEngine()
    assert engine._check_sensitive("请描述你的婚育情况和配偶职业") is True
    assert engine._check_sensitive("请描述你在项目中的角色") is False
