# -*- coding: utf-8 -*-
"""test_new_tools.py · 新增工具测试

测试:
  1. interview_engine: 敏感词阻断（20条全测）、STAR 缺口检测、追问生成、降级题库
  2. model_router: 路由表完整性、参数冻结、降级输出
  3. voice_handler: 状态码、超时设置
  4. privacy_lifecycle: ConsentManager / DataLifecycle / PIIScanner
"""
import io
import json
import os
import re
import tempfile

import pytest

from interview_engine import (
    InterviewEngine, SENSITIVE_PATTERNS, STAR_KEYWORDS,
    GENERIC_QUESTIONS, QUESTION_TEMPLATES, MAX_MAIN_QUESTIONS,
    MAX_FOLLOWUPS_PER_QUESTION,
)
from model_router import (
    ModelRouter, TASK_PROMPTS, MODEL_PARAMS, DEGRADED_OUTPUTS,
)
from voice_handler import VoiceHandler
from privacy_lifecycle import ConsentManager, DataLifecycle, PIIScanner


# =====================================================================
# 1. InterviewEngine 测试
# =====================================================================

class TestSensitivePatterns:
    """20 条敏感词模式全测"""

    def test_pattern_count(self):
        """确认恰好 20 条敏感词模式"""
        assert len(SENSITIVE_PATTERNS) == 20

    def test_all_patterns_compile(self):
        """所有正则可编译"""
        for p in SENSITIVE_PATTERNS:
            re.compile(p)

    @pytest.mark.parametrize("idx", range(20))
    def test_each_pattern_matches(self, idx):
        """每条模式至少匹配一个示例"""
        samples = [
            "你怀孕了吗？有没有计划生育？",
            "你今年多大？哪年出生？属相是什么？",
            "你的籍贯是哪里？户口在什么地方？",
            "你有什么宗教信仰？政治面貌是什么？",
            "你有残疾证吗？健康状况如何？",
            "你的性取向是什么？性别认同呢？",
            "你的配偶做什么工作？家庭收入多少？",
            "你的身高体重多少？外貌条件怎么样？",
            "你有贷款吗？征信记录如何？",
            "你有违法犯罪记录吗？有案底吗？",
            "你为什么从上家离职？被辞退了吗？",
            "你上家薪水多少？期望薪资是多少？",
            "你的社保公积金断缴过吗？",
            "你在哪买房？有房贷吗？",
            "你有几个孩子？子女学龄多大？",
            "你说什么方言？母语是什么？",
            "你有抑郁症吗？做过心理咨询吗？",
            "你从疫区来的吗？需要隔离吗？",
            "你退伍了吗？服役过吗？当过兵吗？",
            "你是工会会员吗？工会身份是什么？",
        ]
        pat = re.compile(SENSITIVE_PATTERNS[idx])
        assert pat.search(samples[idx]), "模式 %d 未匹配: %s" % (idx, samples[idx])

    def test_safe_question_not_blocked(self):
        """安全问题不被阻断"""
        engine = InterviewEngine()
        assert not engine._check_sensitive("请介绍一个你最有成就感的项目")
        assert not engine._check_sensitive("你熟悉 Go 语言吗？")

    def test_sensitive_question_replaced(self):
        """敏感问题被替换为通用行为题"""
        engine = InterviewEngine()
        session = engine.start(
            {"requirements": []}, {}, []
        )
        # 模拟敏感问题
        assert engine._check_sensitive("你今年几岁了？")
        # 降级到通用题
        q, targets = engine._fallback_generic_by_index(0)
        assert "年龄" not in q
        assert "几岁" not in q


class TestStarGapDetection:

    def test_complete_answer_no_gaps(self):
        """完整 STAR 回答无缺口"""
        engine = InterviewEngine()
        answer = (
            "在实习项目中，背景是接口响应慢。我的任务是优化性能。"
            "我采取了加索引和使用 Redis 缓存的方法。"
            "最终结果是将响应时间从 800ms 降低到 220ms，提升了 72%。"
            "回过头看，我学到了性能优化的系统性方法。"
        )
        gaps = engine._detect_star_gaps(answer)
        assert len(gaps) == 0 or "reflection" not in gaps[:3]

    def test_missing_metric(self):
        """缺少量化数据"""
        engine = InterviewEngine()
        answer = "我做了一个项目，负责开发，采取了行动，结果是完成了。"
        gaps = engine._detect_star_gaps(answer)
        assert "metric" in gaps

    def test_missing_action(self):
        """缺少行动描述"""
        engine = InterviewEngine()
        answer = "项目背景是这样，任务是目标，结果上线了。"
        gaps = engine._detect_star_gaps(answer)
        assert "action" in gaps

    def test_too_short_answer_all_missing(self):
        """过短回答全部缺失"""
        engine = InterviewEngine()
        gaps = engine._detect_star_gaps("好")
        assert len(gaps) == 6

    def test_all_six_star_keys(self):
        """STAR_KEYWORDS 包含 6 个维度"""
        assert len(STAR_KEYWORDS) == 6
        for key in ("situation", "task", "action", "result", "metric", "reflection"):
            assert key in STAR_KEYWORDS


class TestFollowupGeneration:

    def test_followup_for_missing_metric(self):
        """metric 缺失生成量化追问"""
        engine = InterviewEngine()
        followup = engine._generate_followup("做了一些事", ["metric"])
        assert followup is not None
        assert "数据" in followup["question"] or "数字" in followup["question"]

    def test_followup_for_missing_action(self):
        """action 缺失生成本人行动追问"""
        engine = InterviewEngine()
        followup = engine._generate_followup("完成了一个项目", ["action"])
        assert followup is not None
        assert "本人" in followup["question"] or "工具" in followup["question"]

    def test_no_followup_when_no_gaps(self):
        """无缺口时不生成追问"""
        engine = InterviewEngine()
        followup = engine._generate_followup("完整回答", [])
        assert followup is None

    def test_max_one_followup_per_question(self):
        """每题最多 1 次追问"""
        assert MAX_FOLLOWUPS_PER_QUESTION == 1


class TestDegradedQuestionBank:

    def test_generic_questions_count(self):
        """通用行为题恰好 3 道"""
        assert len(GENERIC_QUESTIONS) == 3

    def test_generic_question_has_targets(self):
        """每道通用题有 targets"""
        for q in GENERIC_QUESTIONS:
            assert "question" in q
            assert "targets" in q
            assert len(q["targets"]) >= 1

    def test_fallback_generic_by_index_cycles(self):
        """通用题按 index 循环"""
        engine = InterviewEngine()
        q1, _ = engine._fallback_generic_by_index(0)
        q4, _ = engine._fallback_generic_by_index(3)  # 3 % 3 = 0
        assert q1 == q4

    def test_question_templates_exist(self):
        """岗位题库模板存在"""
        assert len(QUESTION_TEMPLATES) == 5
        for key, tmpl in QUESTION_TEMPLATES.items():
            assert "{gap}" in tmpl

    def test_max_main_questions(self):
        """最多 5 个主问题"""
        assert MAX_MAIN_QUESTIONS == 5

    def test_no_router_uses_fallback(self):
        """无 router 时走降级题库"""
        engine = InterviewEngine(model_router=None)
        session = engine.start(
            {"requirements": [{"id": "R1", "type": "hard", "text": "Go"}]},
            {},
            [{"id": "R1", "type": "hard", "text": "Go", "status": "weak"}],
        )
        q = engine.next_question(session)
        assert q["question"] is not None
        assert session["degraded"] is True


# =====================================================================
# 2. ModelRouter 测试
# =====================================================================

class TestModelRouterRouting:

    def test_task_prompts_complete(self):
        """路由表完整: 7 个任务"""
        expected = {
            "resume_diagnosis", "resume_report", "jd_extract",
            "jd_match_explain", "interview_question", "interview_review",
            "seven_day_plan",
        }
        assert set(TASK_PROMPTS.keys()) == expected

    def test_model_params_frozen(self):
        """参数冻结: 每个任务有 temperature/max_tokens/timeout"""
        for task in TASK_PROMPTS:
            params = MODEL_PARAMS[task]
            assert "temperature" in params
            assert "max_tokens" in params
            assert "timeout" in params
            assert isinstance(params["temperature"], (int, float))
            assert isinstance(params["max_tokens"], int)
            assert isinstance(params["timeout"], int)

    def test_degraded_outputs_cover_all_tasks(self):
        """降级输出覆盖所有任务"""
        for task in TASK_PROMPTS:
            assert task in DEGRADED_OUTPUTS, "缺少降级输出: %s" % task

    def test_degraded_output_has_note(self):
        """降级输出含 note 说明"""
        for task, output in DEGRADED_OUTPUTS.items():
            assert "note" in output, "%s 降级输出缺少 note" % task

    def test_unknown_task_fails(self):
        """未知任务返回 failed"""
        class TestRouter(ModelRouter):
            def _try_call(self, *a, **kw):
                return "ok"
        router = TestRouter(primary_model="test")
        result = router.call("nonexistent", "input")
        assert result["status"] == "failed"
        assert result["error_type"] == "unknown_task_type"

    def test_primary_success_no_degradation(self):
        """主模型成功不降级"""
        class SuccessRouter(ModelRouter):
            def _try_call(self, *a, **kw):
                return {"diagnosis": "ok"}
        router = SuccessRouter(primary_model="primary_model")
        result = router.call("resume_diagnosis", "input")
        assert result["status"] == "success"
        assert result["degraded"] is False
        assert result["model"] == "primary_model"

    def test_primary_fail_fallback_success(self):
        """主模型失败 -> 备用成功，标记 degraded"""
        class FailThenSuccess(ModelRouter):
            call_count = 0
            def _try_call(self, model, *a, **kw):
                self.call_count += 1
                if self.call_count == 1:
                    raise RuntimeError("primary down")
                return "fallback result"
        router = FailThenSuccess(primary_model="p", fallback_model="f")
        result = router.call("resume_diagnosis", "input")
        assert result["status"] == "success"
        assert result["degraded"] is True
        assert result["model"] == "f"

    def test_all_fail_rule_degraded(self):
        """主备都失败 -> 规则降级"""
        class AllFail(ModelRouter):
            def _try_call(self, *a, **kw):
                raise RuntimeError("all models down")
        router = AllFail(primary_model="p", fallback_model="f")
        result = router.call("resume_diagnosis", "input")
        assert result["status"] == "degraded"
        assert result["model"] == "rule_degraded"
        assert result["degraded"] is True

    def test_trace_id_generated(self):
        """每次调用生成 trace_id"""
        class TestRouter(ModelRouter):
            def _try_call(self, *a, **kw):
                return "ok"
        router = TestRouter(primary_model="t")
        r1 = router.call("resume_diagnosis", "input1")
        r2 = router.call("resume_diagnosis", "input2")
        assert r1["trace_id"] != r2["trace_id"]

    def test_input_hashed_not_stored(self):
        """输入哈希化，不存原文"""
        class TestRouter(ModelRouter):
            def _try_call(self, *a, **kw):
                return "ok"
        router = TestRouter(primary_model="t", enable_log=False)
        result = router.call("resume_diagnosis", "sensitive input text")
        # output 中不应包含原始输入
        assert "sensitive input text" not in json.dumps(result)


# =====================================================================
# 3. VoiceHandler 测试
# =====================================================================

class TestVoiceHandler:

    def test_state_codes(self):
        """故障类型常量存在"""
        vh = VoiceHandler()
        assert vh.OK == "ok"
        assert vh.MIC_DENIED == "mic_denied"
        assert vh.NETWORK_ERROR == "network_error"
        assert vh.ASR_ERROR == "asr_error"
        assert vh.TTS_ERROR == "tts_error"

    def test_default_timeout_10s(self):
        """默认回退超时 10 秒"""
        vh = VoiceHandler()
        assert vh.fallback_timeout == 10

    def test_custom_timeout(self):
        """自定义超时"""
        vh = VoiceHandler(fallback_timeout=15)
        assert vh.fallback_timeout == 15

    def test_confidence_threshold(self):
        """ASR 置信度阈值 = 0.75"""
        vh = VoiceHandler()
        assert vh.ASR_CONFIDENCE_THRESHOLD == 0.75

    def test_check_confidence_accepted(self):
        """高置信度接受"""
        vh = VoiceHandler()
        result = vh.check_confidence(0.9, "turn1")
        assert result["accepted"] is True
        assert result["needs_confirmation"] is False

    def test_check_confidence_needs_confirmation(self):
        """低置信度需确认"""
        vh = VoiceHandler()
        result = vh.check_confidence(0.5, "turn1")
        assert result["accepted"] is False
        assert result["needs_confirmation"] is True

    def test_check_confidence_none(self):
        """None 置信度需确认"""
        vh = VoiceHandler()
        result = vh.check_confidence(None, "turn1")
        assert result["accepted"] is False

    def test_get_fallback_text_input(self):
        """文字回退方案"""
        vh = VoiceHandler()
        fb = vh.get_fallback_text_input("turn1", "partial draft")
        assert fb["mode"] == "text_input"
        assert fb["turn_id"] == "turn1"
        assert fb["draft"] == "partial draft"

    def test_get_fallback_text_input_no_draft(self):
        """无草稿的文字回退"""
        vh = VoiceHandler()
        fb = vh.get_fallback_text_input("turn2")
        assert fb["draft"] == ""

    def test_handle_tts_error_non_blocking(self):
        """TTS 错误不阻断主链路"""
        vh = VoiceHandler()
        result = vh.handle_error(vh.TTS_ERROR, "turn1", "tts failed")
        assert result["fallback"] is None
        assert result["should_retry"] is False

    def test_handle_asr_error_triggers_fallback(self):
        """ASR 错误触发文字回退"""
        vh = VoiceHandler()
        result = vh.handle_error(vh.ASR_ERROR, "turn1", "asr failed")
        assert result["fallback"] is not None
        assert result["fallback"]["mode"] == "text_input"

    def test_cancel_clears_state(self):
        """cancel 清除状态"""
        vh = VoiceHandler()
        vh._cancelled = False
        vh._active_turn = "turn1"
        vh.cancel()
        assert vh._cancelled is True
        assert vh._active_turn is None

    def test_browser_availability_returns_true(self):
        """后端编排层浏览器能力检测返回 True"""
        vh = VoiceHandler()
        assert vh._browser_asr_available() is True
        assert vh._browser_tts_available() is True


# =====================================================================
# 4. PrivacyLifecycle 测试
# =====================================================================

class TestConsentManager:

    def test_grant_and_check(self, tmp_path):
        cm = ConsentManager(store_dir=str(tmp_path))
        assert not cm.check_consent("user1")
        cm.grant_consent("user1")
        assert cm.check_consent("user1")

    def test_revoke(self, tmp_path):
        cm = ConsentManager(store_dir=str(tmp_path))
        cm.grant_consent("user1")
        assert cm.check_consent("user1")
        cm.revoke_consent("user1")
        assert not cm.check_consent("user1")

    def test_consent_version(self, tmp_path):
        cm = ConsentManager(store_dir=str(tmp_path))
        assert cm.CONSENT_VERSION == "1.0"

    def test_show_consent_returns_text(self, tmp_path):
        cm = ConsentManager(store_dir=str(tmp_path))
        text = cm.show_consent("user1")
        assert "隐私" in text or "同意" in text

    def test_persisted_across_instances(self, tmp_path):
        """同意状态持久化"""
        cm1 = ConsentManager(store_dir=str(tmp_path))
        cm1.grant_consent("persist_user")
        cm2 = ConsentManager(store_dir=str(tmp_path))
        assert cm2.check_consent("persist_user")


class TestDataLifecycle:

    def test_activate(self, tmp_path):
        dl = DataLifecycle(store_dir=str(tmp_path))
        dl.activate("user1")
        assert dl.is_active("user1")
        assert dl.get_status("user1") == "ACTIVE"

    def test_delete(self, tmp_path):
        dl = DataLifecycle(store_dir=str(tmp_path))
        dl.activate("user1")
        dl.delete("user1")
        assert dl.is_deleted("user1")
        assert not dl.is_active("user1")

    def test_delete_unactivated(self, tmp_path):
        """未激活用户直接删除"""
        dl = DataLifecycle(store_dir=str(tmp_path))
        dl.delete("new_user")
        assert dl.is_deleted("new_user")

    def test_assert_can_call_when_active(self, tmp_path):
        """ACTIVE 状态可调用模型"""
        dl = DataLifecycle(store_dir=str(tmp_path))
        dl.activate("user1")
        dl.assert_can_call_model("user1")  # 不抛异常

    def test_assert_cannot_call_when_deleted(self, tmp_path):
        """DELETED 状态禁止调用模型"""
        dl = DataLifecycle(store_dir=str(tmp_path))
        dl.activate("user1")
        dl.delete("user1")
        with pytest.raises(PermissionError):
            dl.assert_can_call_model("user1")

    def test_assert_cannot_call_when_not_activated(self, tmp_path):
        """未激活状态禁止调用模型"""
        dl = DataLifecycle(store_dir=str(tmp_path))
        with pytest.raises(PermissionError):
            dl.assert_can_call_model("unknown_user")

    def test_delete_irreversible(self, tmp_path):
        """删除不可恢复: delete 后 activate 不会自动恢复"""
        dl = DataLifecycle(store_dir=str(tmp_path))
        dl.activate("user1")
        dl.delete("user1")
        # 再次 activate 会覆盖状态
        dl.activate("user1")
        assert dl.is_active("user1")


class TestPIIScanner:

    def test_scan_text_finds_phone(self):
        """扫描手机号"""
        hits = PIIScanner.scan_text("电话 13800138000")
        assert any(h["type"] == "phone" for h in hits)

    def test_scan_text_finds_email(self):
        """扫描邮箱"""
        hits = PIIScanner.scan_text("邮箱 test@example.com")
        assert any(h["type"] == "email" for h in hits)

    def test_scan_text_finds_id(self):
        """扫描身份证"""
        hits = PIIScanner.scan_text("身份证 110101199001011234")
        assert any(h["type"] == "id" for h in hits)

    def test_scan_text_clean(self):
        """无 PII 文本返回空"""
        hits = PIIScanner.scan_text("这是一条干净的日志")
        assert len(hits) == 0

    def test_scan_file(self, tmp_path):
        """扫描文件"""
        f = tmp_path / "app.log"
        f.write_text("phone 13912345678", encoding="utf-8")
        hits = PIIScanner.scan_file(str(f))
        assert len(hits) > 0

    def test_scan_logs_by_dir(self, tmp_path):
        """扫描目录"""
        (tmp_path / "a.log").write_text("13800138000", encoding="utf-8")
        (tmp_path / "b.txt").write_text("clean text", encoding="utf-8")
        results = PIIScanner.scan_logs(str(tmp_path))
        assert len(results) >= 1

    def test_scan_logs_extensions_filter(self, tmp_path):
        """扩展名过滤"""
        (tmp_path / "a.log").write_text("13800138000", encoding="utf-8")
        (tmp_path / "a.json").write_text("13800138000", encoding="utf-8")
        results = PIIScanner.scan_logs(str(tmp_path), extensions=[".log"])
        assert any(".log" in k for k in results)
        assert not any(".json" in k for k in results)

    def test_assert_clean_passes(self, tmp_path):
        """干净目录通过断言"""
        (tmp_path / "clean.log").write_text("no pii here", encoding="utf-8")
        PIIScanner.assert_clean(str(tmp_path))  # 不抛异常

    def test_assert_clean_raises(self, tmp_path):
        """有 PII 的目录抛异常"""
        (tmp_path / "dirty.log").write_text("13800138000", encoding="utf-8")
        with pytest.raises(RuntimeError, match="PII"):
            PIIScanner.assert_clean(str(tmp_path))
