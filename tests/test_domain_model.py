# -*- coding: utf-8 -*-
"""Phase 2 domain invariants.

These tests are the executable form of the product rules the domain layer exists
to enforce.  They deliberately do not touch the database: the domain package is
imported by routes, services and repositories, so its rules must hold on their
own.

The three rules that matter most and would silently corrupt the product if they
regressed:

1. **AI cannot write a confirmed fact.**  Anything a model produced (resume,
   interview, application outcome) must enter as ``pending`` and only become
   ``confirmed`` through an explicit user action.  ``user_input`` is the single
   source allowed to be born confirmed.
2. **Every piece of career evidence is traceable.**  A quote is mandatory, and
   when the caller hands over the source text the quote must be a verbatim
   substring of it.
3. **A decision is explainable.**  APPLY / STRETCH / PASS follows one readable
   rule, never a weighted score, and every recorded decision cites at least
   three distinct concrete reasons.
"""
import pytest

from domain import action as action_domain
from domain import application as application_domain
from domain import career_profile as profile_domain
from domain import evidence as evidence_domain
from domain import interview as interview_domain
from domain import target_job as target_job_domain
from domain.errors import DomainError

RESUME_TEXT = (
    "实习经历：在示例科技负责订单接口开发，通过 SQL 查询优化"
    "将响应时间从 800ms 降至 220ms，服务日均订单 3 万单。"
)


def _resume_evidence(**overrides):
    kwargs = dict(
        owner_key="owner-1",
        evidence_type="achievement",
        claim="通过 SQL 查询优化把订单接口响应时间从 800ms 降到 220ms。",
        source_type="resume",
        source_id="resume-42",
        source_quote="将响应时间从 800ms 降至 220ms",
        source_text=RESUME_TEXT,
        confidence=0.8,
    )
    kwargs.update(overrides)
    return evidence_domain.new_evidence(**kwargs)


# ------------------------------------------------------------------ #
# CareerEvidence · 可回指来源
# ------------------------------------------------------------------ #

def test_quote_must_be_a_verbatim_substring_of_the_source():
    record = _resume_evidence()
    assert record["source_quote"] == "将响应时间从 800ms 降至 220ms"

    with pytest.raises(DomainError) as err:
        _resume_evidence(source_quote="把响应时间从 800ms 降到 220ms")  # 降/低 不同字
    assert err.value.code == "quote_not_verbatim"


def test_model_produced_sources_require_a_source_id():
    for source in ("resume", "interview", "application_outcome"):
        with pytest.raises(DomainError) as err:
            _resume_evidence(source_type=source, source_id=None, source_text=None)
        assert err.value.code == "missing_source_id"


def test_user_input_does_not_need_a_source_id():
    record = evidence_domain.new_evidence(
        owner_key="owner-1",
        evidence_type="skill",
        claim="我熟悉 Python 与 Flask。",
        source_type="user_input",
        source_quote="我熟悉 Python 与 Flask。",
    )
    assert record["source_id"] is None
    assert record["status"] == "confirmed"


# ------------------------------------------------------------------ #
# CareerEvidence · AI 不得直接写入已确认事实
# ------------------------------------------------------------------ #

def test_resume_and_interview_evidence_are_born_pending():
    for source in ("resume", "interview"):
        record = _resume_evidence(source_type=source, source_text=None)
        assert record["status"] == "pending", source
        assert record["user_confirmed"] == 0
        assert record["confirmed_at"] is None
        assert evidence_domain.is_usable(record) is False


def test_ai_source_cannot_be_created_as_confirmed():
    with pytest.raises(DomainError) as err:
        _resume_evidence(status="confirmed", source_text=None)
    assert err.value.code == "evidence_requires_confirmation"


def test_user_input_may_be_created_as_confirmed():
    record = evidence_domain.new_evidence(
        owner_key="owner-1",
        evidence_type="experience",
        claim="我在校学生会做过一年外联。",
        source_type="user_input",
        source_quote="我在校学生会做过一年外联。",
    )
    assert record["status"] == "confirmed"
    assert evidence_domain.is_usable(record) is True


def test_only_user_confirmation_flips_pending_to_confirmed():
    record = _resume_evidence()
    assert evidence_domain.is_usable(record) is False

    confirmed = evidence_domain.confirm(record)
    assert confirmed["status"] == "confirmed"
    assert confirmed["user_confirmed"] == 1
    assert confirmed["confirmed_at"]
    assert evidence_domain.is_usable(confirmed) is True

    # 原记录不被就地修改（避免调用方拿着旧引用以为已经确认）
    assert record["status"] == "pending"


def test_rejected_evidence_cannot_be_confirmed_directly():
    record = evidence_domain.reject(_resume_evidence())
    assert record["status"] == "rejected"
    assert record["user_confirmed"] == 0
    with pytest.raises(DomainError) as err:
        evidence_domain.confirm(record)
    assert err.value.code == "evidence_rejected"


def test_editing_a_confirmed_claim_sends_it_back_to_pending():
    confirmed = evidence_domain.confirm(_resume_evidence())
    edited = evidence_domain.edit_claim(confirmed, "把响应时间压到 220ms 以内。")
    assert edited["status"] == "pending"
    assert edited["user_confirmed"] == 0
    assert edited["confirmed_at"] is None

    # 用户本人在修改时当场确认，则保持 confirmed
    kept = evidence_domain.edit_claim(
        confirmed, "把响应时间压到 220ms 以内。", confirmed_by_user=True
    )
    assert kept["status"] == "confirmed"

    # pending 的证据被编辑后仍是 pending（不会因为编辑而升级成事实）
    pending = evidence_domain.edit_claim(_resume_evidence(), "新的说法。")
    assert pending["status"] == "pending"


def test_evidence_field_bounds_are_enforced():
    with pytest.raises(DomainError) as err:
        _resume_evidence(claim="长" * (evidence_domain.MAX_CLAIM_CHARS + 1), source_text=None)
    assert err.value.code == "oversized_claim"

    with pytest.raises(DomainError) as err:
        _resume_evidence(claim="   ", source_text=None)
    assert err.value.code == "missing_claim"

    with pytest.raises(DomainError) as err:
        _resume_evidence(confidence=1.5, source_text=None)
    assert err.value.code == "invalid_confidence"

    with pytest.raises(DomainError) as err:
        _resume_evidence(evidence_type="hobby", source_text=None)
    assert err.value.code == "invalid_evidence_type"

    with pytest.raises(DomainError) as err:
        _resume_evidence(source_type="model_guess", source_text=None)
    assert err.value.code == "invalid_source_type"


def test_verify_quote_rechecks_the_fact_lock_after_persistence():
    record = _resume_evidence()
    assert evidence_domain.verify_quote(record, RESUME_TEXT) is True
    assert evidence_domain.verify_quote(record, "完全无关的一段文本") is False


def test_partitioning_helpers_split_pending_from_usable():
    records = [
        _resume_evidence(source_text=None),                                   # pending
        evidence_domain.confirm(_resume_evidence(source_text=None)),          # confirmed
        evidence_domain.reject(_resume_evidence(source_text=None)),           # rejected
    ]
    assert len(evidence_domain.pending(records)) == 1
    assert len(evidence_domain.usable(records)) == 1


# ------------------------------------------------------------------ #
# TargetJob · 要求分类与缺口
# ------------------------------------------------------------------ #

def test_requirement_type_maps_to_the_documented_priority():
    assert target_job_domain.priority_for("hard") == "P0"
    assert target_job_domain.priority_for("responsibility") == "P1"
    assert target_job_domain.priority_for("preferred") == "P2"
    assert target_job_domain.priority_for("terminology") == "P2"
    with pytest.raises(DomainError):
        target_job_domain.priority_for("nice_to_have")


def test_gaps_are_only_created_for_weak_or_missing_requirements():
    requirement = {"id": 7, "req_type": "hard", "text": "熟悉 Python"}

    missing = target_job_domain.gap_from_requirement(1, requirement, "missing")
    assert missing["gap_type"] == "missing"
    assert missing["priority"] == "P0"
    assert missing["status"] == "open"

    weak = target_job_domain.gap_from_requirement(1, requirement, "weak")
    assert weak["gap_type"] == "weak"

    for status in ("covered", "unknown"):
        with pytest.raises(DomainError) as err:
            target_job_domain.gap_from_requirement(1, requirement, status)
        assert err.value.code == "no_gap_for_status"


def test_closed_gaps_stop_counting_towards_the_decision():
    requirement = {"id": 1, "req_type": "hard", "text": "熟悉 Python"}
    gap = target_job_domain.gap_from_requirement(1, requirement, "missing")
    assert target_job_domain.open_gaps([gap]) == [gap]
    assert target_job_domain.expected_decision([gap]) == "PASS"

    # 缺口一旦关闭（done / dropped），就不再参与判定
    for closed in ("done", "dropped"):
        gap["status"] = closed
        assert target_job_domain.open_gaps([gap]) == []
        assert target_job_domain.expected_decision([gap]) == "APPLY"


# ------------------------------------------------------------------ #
# TargetJob · APPLY / STRETCH / PASS
# ------------------------------------------------------------------ #

def _gap(priority, req_type, status="open", requirement_id=1):
    return {
        "priority": priority,
        "req_type": req_type,
        "requirement_id": requirement_id,
        "status": status,
    }


def test_pass_when_an_unresolved_p0_hard_gap_exists():
    gaps = [_gap("P0", "hard")]
    assert target_job_domain.expected_decision(gaps) == "PASS"


def test_stretch_when_no_p0_is_open_but_a_p1_gap_remains():
    assert target_job_domain.expected_decision([_gap("P1", "responsibility")]) == "STRETCH"
    assert target_job_domain.expected_decision([_gap("P2", "preferred")]) == "APPLY"
    # P0 一旦出现就是 PASS，即使同时存在可短期补强的 P1
    assert target_job_domain.expected_decision(
        [_gap("P0", "hard"), _gap("P1", "responsibility", requirement_id=2)]
    ) == "PASS"


def test_only_hard_requirements_can_produce_a_p0_gap():
    """PASS 的判定依赖「P0 ⟺ hard」，这条映射必须稳定。"""
    assert target_job_domain.priority_for("hard") == "P0"
    for req_type in ("responsibility", "preferred", "terminology"):
        assert target_job_domain.priority_for(req_type) != "P0"


def test_apply_when_no_open_p0_or_p1_gaps_remain():
    gaps = [_gap("P2", "preferred"), _gap("P0", "hard", status="done")]
    assert target_job_domain.expected_decision(gaps) == "APPLY"


def test_decision_requires_at_least_three_distinct_citations():
    with pytest.raises(DomainError) as err:
        target_job_domain.decide(1, "APPLY", ["req_a", "req_b"])
    assert err.value.code == "insufficient_citations"

    with pytest.raises(DomainError) as err:
        target_job_domain.decide(1, "APPLY", ["req_a", "req_a", "req_b"])
    assert err.value.code == "duplicate_citation"

    with pytest.raises(DomainError) as err:
        target_job_domain.decide(1, "APPLY", ["req_a", "req_b", ""])
    assert err.value.code == "invalid_citation"

    record = target_job_domain.decide(
        1, "APPLY", ["req_a", "req_b", "req_c"], rationale="硬性要求均有证据"
    )
    assert record["decision"] == "APPLY"
    assert "req_a" in record["rationale_json"]


def test_decision_must_agree_with_the_gap_distribution():
    """判定规则透明：与缺口分布不一致的 Decision 必须被拒绝，不能手写。"""
    gaps = [_gap("P0", "hard")]
    with pytest.raises(DomainError) as err:
        target_job_domain.decide(1, "APPLY", ["a", "b", "c"], gaps=gaps)
    assert err.value.code == "decision_inconsistent"

    ok = target_job_domain.decide(1, "PASS", ["a", "b", "c"], gaps=gaps)
    assert ok["decision"] == "PASS"


def test_decision_value_must_be_one_of_the_three_verdicts():
    with pytest.raises(DomainError) as err:
        target_job_domain.decide(1, "MAYBE", ["a", "b", "c"])
    assert err.value.code == "invalid_decision"


def test_requirements_carry_their_source_span_and_default_key():
    record = target_job_domain.requirement_from_profile_item(
        3, {"text": "熟悉 Python", "type": "hard", "source_span": {"start": 1, "end": 8}}, ordinal=0
    )
    assert record["target_job_id"] == 3
    assert record["req_key"] == "req_01"
    assert record["req_type"] == "hard"
    assert "source_span" in record["source_span_json"] or '"start"' in record["source_span_json"]

    with pytest.raises(DomainError):
        target_job_domain.requirement_from_profile_item(3, {"text": "   "})


# ------------------------------------------------------------------ #
# Application · 7 态状态机
# ------------------------------------------------------------------ #

def test_happy_path_and_the_allowed_transitions():
    path = ["considering", "preparing", "applied", "interview", "offer"]
    for current, target in zip(path, path[1:]):
        assert application_domain.transition(current, target) == target

    assert application_domain.can_transition("applied", "rejected") is True
    assert application_domain.can_transition("interview", "rejected") is True
    assert application_domain.can_transition("applied", "withdrawn") is True
    assert application_domain.can_transition("considering", "withdrawn") is True


def test_illegal_transitions_are_rejected():
    with pytest.raises(DomainError) as err:
        application_domain.transition("considering", "applied")
    assert err.value.code == "invalid_transition"

    with pytest.raises(DomainError) as err:
        application_domain.transition("offer", "rejected")
    assert err.value.code == "invalid_transition"

    with pytest.raises(DomainError) as err:
        application_domain.transition("applied", "preparing")
    assert err.value.code == "invalid_transition"


def test_terminal_states_cannot_be_left():
    for terminal in ("rejected", "withdrawn"):
        for target in ("applied", "interview", "offer", "preparing", "considering", "rejected"):
            if target == terminal:
                continue
            with pytest.raises(DomainError):
                application_domain.transition(terminal, target)


def test_unknown_status_value_is_rejected():
    with pytest.raises(DomainError) as err:
        application_domain.transition("applied", "ghosted")
    assert err.value.code == "invalid_status"


def test_legacy_status_values_normalise_and_unknown_ones_fall_back():
    assert application_domain.normalize_legacy_status("submitted") == ("applied", True)
    assert application_domain.normalize_legacy_status("INTERVIEWING") == ("interview", True)
    assert application_domain.normalize_legacy_status("cancelled") == ("withdrawn", True)
    # 未知值兜底为最保守的 applied，并明确标记 was_known=False
    assert application_domain.normalize_legacy_status("weird_value") == ("applied", False)
    assert application_domain.normalize_legacy_status("") == ("applied", False)


def test_new_application_defaults_to_preparing_not_applied():
    record = application_domain.new_application(
        session_id="sess-1",
        owner_key="owner-1",
        company="示例科技",
        position="后端开发实习生",
        cover_letter="尊敬的招聘负责人：我希望能申请贵司的后端开发实习生岗位。",
    )
    assert record["status"] == "preparing"
    assert record["target_job_id"] is None


def test_new_application_validates_required_fields():
    base = dict(
        session_id="sess-1",
        owner_key="owner-1",
        company="示例科技",
        position="后端开发实习生",
        cover_letter="尊敬的招聘负责人：我希望能申请贵司的后端开发实习生岗位。",
    )
    for field in ("company", "position"):
        broken = dict(base)
        broken[field] = "   "
        with pytest.raises(DomainError):
            application_domain.new_application(**broken)

    short = dict(base, cover_letter="太短了")
    with pytest.raises(DomainError):
        application_domain.new_application(**short)

    missing_owner = dict(base, owner_key="")
    with pytest.raises(DomainError) as err:
        application_domain.new_application(**missing_owner)
    assert err.value.code == "missing_owner_key"


def test_outcome_records_map_to_the_next_status():
    application = {"id": 9, "owner_key": "owner-1", "company": "示例科技", "position": "后端"}
    record, next_status = application_domain.record_outcome(application, "rejected", note="技术面未通过")
    assert record["outcome"] == "rejected"
    assert record["application_id"] == 9
    assert next_status == "rejected"

    _, no_change = application_domain.record_outcome(application, "no_response")
    assert no_change is None

    with pytest.raises(DomainError) as err:
        application_domain.record_outcome(application, "ghosted")
    assert err.value.code == "invalid_outcome"

    with pytest.raises(DomainError) as err:
        application_domain.record_outcome({"owner_key": "owner-1"}, "offer")
    assert err.value.code == "application_required"


def test_application_outcome_writes_back_a_pending_evidence():
    """结果能反向写入 Career Profile，但只能是待确认证据。"""
    application = {"id": 9, "owner_key": "owner-1", "company": "示例科技", "position": "后端开发"}
    record = application_domain.evidence_from_outcome(
        application, "rejected", note="面试官反馈缺少分布式系统经验"
    )
    assert record["source_type"] == "application_outcome"
    assert record["source_id"] == "9"
    assert record["status"] == "pending"
    assert record["user_confirmed"] == 0
    assert evidence_domain.is_usable(record) is False
    assert "面试官反馈缺少分布式系统经验" in record["source_quote"]


# ------------------------------------------------------------------ #
# Action · Gap → Action → Artifact → Outcome
# ------------------------------------------------------------------ #

def _open_gap():
    return {
        "id": 5,
        "priority": "P1",
        "reason": "缺乏量化项目成果",
        "action": "重构一个项目描述的指标",
        "expected_artifact": "1 条可验证的 STAR 项目描述",
        "status": "open",
    }


def test_action_requires_an_expected_artifact_to_close_the_loop():
    action = action_domain.open_from_gap("owner-1", _open_gap())
    assert action["artifact"] == "1 条可验证的 STAR 项目描述"
    assert action["task"] == "重构一个项目描述的指标"
    assert action["status"] == "todo"

    no_artifact = dict(_open_gap(), expected_artifact="")
    with pytest.raises(DomainError) as err:
        action_domain.open_from_gap("owner-1", no_artifact)
    assert err.value.code == "artifact_required"

    no_task = dict(_open_gap(), action="")
    with pytest.raises(DomainError) as err:
        action_domain.open_from_gap("owner-1", no_task)
    assert err.value.code == "task_required"

    with pytest.raises(DomainError):
        action_domain.open_from_gap("", _open_gap())


def test_outcome_can_only_be_recorded_for_a_done_action_with_an_artifact():
    action = action_domain.open_from_gap("owner-1", _open_gap())

    with pytest.raises(DomainError) as err:
        action_domain.record_outcome(action, "投出去了")
    assert err.value.code == "action_not_done"

    done = action_domain.complete(action)
    assert done["status"] == "done"
    recorded = action_domain.record_outcome(done, "简历通过初筛，进入一面")
    assert recorded["outcome"] == "简历通过初筛，进入一面"

    with pytest.raises(DomainError) as err:
        action_domain.record_outcome(done, "   ")
    assert err.value.code == "invalid_outcome"


def test_action_status_machine_allows_rework_but_not_leaving_dropped():
    assert action_domain.transition("todo", "doing") == "doing"
    assert action_domain.transition("doing", "done") == "done"
    assert action_domain.transition("done", "doing") == "doing"  # 返工
    # 当天做掉一件小事是主场景，不应该强迫先标记 doing
    assert action_domain.transition("todo", "done") == "done"

    with pytest.raises(DomainError):
        action_domain.transition("dropped", "doing")
    with pytest.raises(DomainError):
        action_domain.transition("dropped", "done")


# ------------------------------------------------------------------ #
# InterviewSession · 新经历必须经用户确认
# ------------------------------------------------------------------ #

ANSWER = "我在实习期独立负责了订单模块的重构，把接口响应时间从 900ms 压到 180ms。"


def test_interview_discovery_becomes_pending_not_confirmed():
    session = {"session_id": "iv_abc"}
    target_job = {"owner_key": "owner-1"}
    record = interview_domain.candidate_evidence(
        session,
        target_job,
        claim="我在实习期独立负责了订单模块的重构。",
        quote="独立负责了订单模块的重构",
        answer_text=ANSWER,
        evidence_type="experience",
        turn_id=3,
    )
    assert record["source_type"] == "interview"
    assert record["source_id"] == "iv_abc:3"
    assert record["status"] == "pending"
    assert record["user_confirmed"] == 0
    assert evidence_domain.is_usable(record) is False


def test_interview_discovery_quote_must_be_verbatim_from_the_answer():
    with pytest.raises(DomainError) as err:
        interview_domain.candidate_evidence(
            {"session_id": "iv_abc"},
            {"owner_key": "owner-1"},
            claim="我主导了订单模块重构。",
            quote="我主导了订单模块重构",  # 回答里没有这句
            answer_text=ANSWER,
        )
    assert err.value.code == "quote_not_verbatim"


def test_interview_discovery_requires_a_session_and_a_target_job():
    with pytest.raises(DomainError) as err:
        interview_domain.candidate_evidence({}, {"owner_key": "o"}, "c", "q", ANSWER)
    assert err.value.code == "session_required"

    with pytest.raises(DomainError) as err:
        interview_domain.candidate_evidence({"session_id": "iv"}, {}, "c", "q", ANSWER)
    assert err.value.code == "target_job_required"


def test_interview_evaluation_is_labelled_a_training_metric():
    result = interview_domain.evaluation({"structure": 72, "specificity": 55}, missing_elements=["量化结果"])
    assert result["is_training_metric"] is True
    assert result["notice"] == interview_domain.TRAINING_METRIC_NOTICE
    assert "不代表真实招聘结果" in result["notice"]
    assert result["subscores"] == {"structure": 72.0, "specificity": 55.0}

    with pytest.raises(DomainError):
        interview_domain.evaluation({"structure": 120})


def test_question_order_puts_gap_driven_questions_first():
    gaps = [
        {"id": 3, "priority": "P2", "status": "open"},
        {"id": 1, "priority": "P1", "status": "open"},
        {"id": 2, "priority": "P0", "status": "doing"},
        {"id": 9, "priority": "P0", "status": "done"},   # 已关闭，不出题
    ]
    ordered = interview_domain.plan_question_order(gaps)
    assert [item["gap_id"] for item in ordered] == [2, 1]
    assert ordered[0]["kind"] == "p0_gap"
    assert ordered[1]["kind"] == "p1_gap"


def test_answer_quote_must_be_verbatim():
    record = interview_domain.new_answer("iv_abc", 12, ANSWER, quote="独立负责了订单模块的重构")
    assert record["quote"] == "独立负责了订单模块的重构"

    with pytest.raises(DomainError) as err:
        interview_domain.new_answer("iv_abc", 12, ANSWER, quote="从头搭建了订单模块")
    assert err.value.code == "quote_not_verbatim"


# ------------------------------------------------------------------ #
# CareerProfile · 证据按五类分支归类（同一批证据的视图，不是第二套事实）
# ------------------------------------------------------------------ #

def _profile_records():
    return [
        evidence_domain.new_evidence(
            owner_key="owner-1", evidence_type="experience",
            claim="在校学生会做过一年外联。", source_type="user_input",
            source_quote="在校学生会做过一年外联。",
        ),
        evidence_domain.confirm(_resume_evidence(source_text=None)),          # achievement
        evidence_domain.new_evidence(
            owner_key="owner-1", evidence_type="skill",
            claim="我熟悉 Python 与 Flask。", source_type="user_input",
            source_quote="我熟悉 Python 与 Flask。",
        ),
        _resume_evidence(evidence_type="story", source_text=None),           # pending story
    ]


def test_profile_buckets_group_evidence_by_branch():
    grouped = profile_domain.buckets(_profile_records())

    assert set(grouped) == {"experience", "skill", "achievement", "story", "preference"}
    assert len(grouped["experience"]) == 1
    assert len(grouped["skill"]) == 1
    assert len(grouped["achievement"]) == 1
    assert len(grouped["story"]) == 1
    assert grouped["preference"] == []


def test_profile_summary_counts_confirmed_and_pending_separately():
    summary = profile_domain.summary(_profile_records())

    assert summary["total"] == 4
    assert summary["confirmed"] == 3      # 两条 user_input + 一条已确认
    assert summary["pending"] == 1
    assert [item["label"] for item in summary["branches"]] == ["经历", "技能", "成果", "故事", "偏好"]
    assert sum(item["total"] for item in summary["branches"]) == summary["total"]


def test_profile_usable_evidence_excludes_pending():
    records = _profile_records()
    usable = profile_domain.usable_evidence(records)
    assert len(usable) == 3
    assert len(profile_domain.pending_evidence(records)) == 1
    assert all(evidence_domain.is_usable(item) for item in usable)


def test_add_evidence_forces_the_profile_owner():
    """即使调用方传了别的 owner_key，也必须落在 profile 的归属下。"""
    profile = profile_domain.new_profile("owner-1")
    record = profile_domain.add_evidence(
        profile,
        owner_key="someone-else",
        evidence_type="skill",
        claim="我熟悉 Python。",
        source_type="user_input",
        source_quote="我熟悉 Python。",
    )
    assert record["owner_key"] == "owner-1"

    with pytest.raises(DomainError) as err:
        profile_domain.add_evidence({}, evidence_type="skill", claim="x", source_type="user_input", source_quote="x")
    assert err.value.code == "profile_required"


def test_profile_requires_an_owner_key():
    with pytest.raises(DomainError) as err:
        profile_domain.new_profile("   ")
    assert err.value.code == "missing_owner_key"

    assert profile_domain.new_profile("owner-1")["display_name"] is None
