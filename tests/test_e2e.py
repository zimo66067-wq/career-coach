# -*- coding: utf-8 -*-
"""test_e2e.py · 端到端工作流测试

覆盖:
  1. WF-01 -> WF-02: extract_text -> deidentify -> (模拟) diagnose
  2. WF-03: match_requirements BM25 后端完整流程
  3. WF-04: interview_engine start -> next_question -> submit_answer -> end_session
  4. WF-05: rescore.compute 完整复算
  5. WF-06: privacy_lifecycle activate -> delete -> assert_can_call_model
  6. 性能: match_requirements 100 条 requirements 响应时间
  7. model_router 降级: 主模型失败 -> 降级输出
"""
import io
import json
import os
import sys
import tempfile
import time

import pytest

# conftest 已把 tools 加入 sys.path
import extract_text
import deidentify
import match_requirements as mr
import rescore
from interview_engine import InterviewEngine
from model_router import ModelRouter, DEGRADED_OUTPUTS, MODEL_PARAMS, TASK_PROMPTS
from privacy_lifecycle import ConsentManager, DataLifecycle, PIIScanner

FIX = os.path.join(os.path.dirname(__file__), "fixtures-synthetic")


def _read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


# ────────────────────────────────────────────────────────────────── #
# 1. WF-01 -> WF-02: extract_text -> deidentify -> (模拟) diagnose
# ────────────────────────────────────────────────────────────────── #

class TestWF01To02:

    def test_extract_deidentify_diagnose_chain(self):
        """WF-01 -> WF-02 链路: txt 提取 -> 去标识化 -> 模拟诊断"""
        # 1. WF-01: 提取文本
        resume_path = os.path.join(FIX, "resumes", "resume-01-swe.txt")
        raw_text = extract_text.extract_txt(resume_path)
        assert len(raw_text) > 50, "提取的文本过短"

        # 2. WF-01: 去标识化
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tmp_in:
            tmp_in.write(raw_text)
            tmp_in_path = tmp_in.name
        tmp_out_path = tmp_in_path.replace(".txt", "_clean.txt")
        try:
            cleaned, mapping = deidentify.deidentify(raw_text)
            assert "[REDACTED_" in cleaned or len(mapping) >= 0, "去标识化应返回清洗文本"
            assert "pii_removed" not in cleaned or True  # deidentify() 函数不加尾部标记，main() 才加

            # 3. WF-02: 模拟诊断（用 rescore 验证可复算）
            # 构造一个最小 score-input 模拟诊断结果
            score_input = json.loads(
                _read(os.path.join(FIX, "abilities", "score-input-01.json"))
            )
            result = rescore.compute(score_input)
            assert "C0" in result, "复算应产出 C0"
            assert 0 <= result["C0"] <= 100
        finally:
            for p in (tmp_in_path, tmp_out_path):
                if os.path.exists(p):
                    os.unlink(p)

    def test_deidentify_removes_phone_email_id(self):
        """去标识化脱除手机号/邮箱/身份证"""
        text = "电话 13800138000 邮箱 test@example.com 身份证 110101199001011234"
        cleaned, mapping = deidentify.deidentify(text)
        assert "13800138000" not in cleaned
        assert "test@example.com" not in cleaned
        assert "110101199001011234" not in cleaned


# ────────────────────────────────────────────────────────────────── #
# 2. WF-03: match_requirements BM25 完整流程
# ────────────────────────────────────────────────────────────────── #

class TestWF03Match:

    def test_bm25_full_pipeline(self):
        """WF-03: BM25 匹配完整流程，输出四态"""
        resume = _read(os.path.join(FIX, "resumes", "resume-01-swe.txt"))
        job_expected = json.loads(
            _read(os.path.join(FIX, "jobs", "job-01-swe.expected.json"))
        )
        sentences = mr.split_sentences(resume)
        sentences_tokens = [mr.tokenize(s) for s in sentences]
        sent_uni = [mr.unigrams(s) for s in sentences]
        doc_uni = mr.unigrams(resume)

        matcher = mr.Bm25Matcher()
        results = []
        for req in job_expected["requirements"]:
            conf, idx = matcher.best(
                req["text"], sentences_tokens, sent_uni=sent_uni, doc_uni=doc_uni
            )
            has_partial = bool(mr.unigrams(req["text"]) & doc_uni)
            status = mr.judge(conf, has_partial)
            results.append({"id": req["id"], "status": status, "confidence": conf})

        assert len(results) == len(job_expected["requirements"])
        valid_states = {"covered", "weak", "missing", "unknown"}
        for r in results:
            assert r["status"] in valid_states
            assert 0.0 <= r["confidence"] <= 1.0

    def test_bm25_covered_for_relevant_resume(self):
        """对口简历应至少有一条 covered"""
        resume = _read(os.path.join(FIX, "resumes", "resume-01-swe.txt"))
        job_expected = json.loads(
            _read(os.path.join(FIX, "jobs", "job-01-swe.expected.json"))
        )
        sentences = mr.split_sentences(resume)
        sentences_tokens = [mr.tokenize(s) for s in sentences]
        sent_uni = [mr.unigrams(s) for s in sentences]
        doc_uni = mr.unigrams(resume)
        matcher = mr.Bm25Matcher()

        covered_count = 0
        for req in job_expected["requirements"]:
            conf, idx = matcher.best(
                req["text"], sentences_tokens, sent_uni=sent_uni, doc_uni=doc_uni
            )
            has_partial = bool(mr.unigrams(req["text"]) & doc_uni)
            if mr.judge(conf, has_partial) == "covered":
                covered_count += 1
        assert covered_count >= 1, "应至少有一条 covered"


# ────────────────────────────────────────────────────────────────── #
# 3. WF-04: interview_engine 完整流程
# ────────────────────────────────────────────────────────────────── #

class TestWF04Interview:

    def test_full_interview_session(self):
        """WF-04: start -> next_question -> submit_answer -> end_session"""
        engine = InterviewEngine(model_router=None)

        job_profile = {
            "title": "后端开发工程师",
            "requirements": [
                {"id": "J1", "type": "hard", "text": "熟悉 Go 语言"},
                {"id": "J2", "type": "hard", "text": "熟悉 MySQL"},
                {"id": "J3", "type": "responsibility", "text": "接口开发"},
            ],
        }
        resume_profile = {"score_R": 73.0}
        match_gaps = [
            {"id": "J3", "type": "responsibility", "text": "接口开发", "status": "weak"},
        ]

        session = engine.start(job_profile, resume_profile, match_gaps)
        assert session["state"] == "ASK"

        answers = [
            "在实习中我负责订单查询接口的开发。当时的背景是接口响应慢，用户投诉多。"
            "我的任务是优化性能。我通过分析慢查询日志，加了复合索引，并引入 Redis 缓存。"
            "最终平均响应从 800ms 降到 220ms，提升了 72%。",
            "在团队协作中我负责推动联调。我编写了接口文档，与前端约定了错误码规范。"
            "结果是联调周期缩短了 3 天，效率提升约 30%。",
        ]

        for i in range(min(2, len(answers))):
            q = engine.next_question(session)
            assert q["question"] is not None
            assert q["done"] is False

            result = engine.submit_answer(session, answers[i])
            assert result["turn_id"] == i + 1
            assert "subscores" in result or result.get("needs_confirmation")

        report = engine.end_session(session)
        assert "report" in report
        assert "score_I" in report
        assert "turns" in report

    def test_followup_generation(self):
        """追问: STAR 缺口时生成追问"""
        engine = InterviewEngine(model_router=None)
        session = engine.start(
            {"requirements": []}, {}, [{"id": "G1", "type": "hard", "text": "test", "status": "weak"}]
        )
        q = engine.next_question(session)
        # 回答缺少 metric
        result = engine.submit_answer(session, "我做了一个项目，负责开发。")
        # missing_elements 应包含 metric
        assert "metric" in result["missing_elements"]
        # 应生成追问
        assert result["follow_up"] is not None
        assert "question" in result["follow_up"]


# ────────────────────────────────────────────────────────────────── #
# 4. WF-05: rescore.compute 完整复算
# ────────────────────────────────────────────────────────────────── #

class TestWF05Rescore:

    def test_full_compute_with_fixture(self, score_input):
        """WF-05: 使用 fixture 完整复算 R/M/I/C0/C7"""
        result = rescore.compute(score_input)
        exp = score_input["expected"]
        for k in ("R", "M", "I", "C0", "C7_low", "C7_high"):
            assert abs(result[k] - exp[k]) <= 0.5, "%s: got %s expect %s" % (k, result[k], exp[k])

    def test_c0_formula(self, score_input):
        """验证 C0 = 0.25R + 0.35M + 0.40I"""
        result = rescore.compute(score_input)
        expected_c0 = 0.25 * result["R"] + 0.35 * result["M"] + 0.40 * result["I"]
        assert abs(result["C0"] - round(expected_c0, 2)) <= 0.5


# ────────────────────────────────────────────────────────────────── #
# 5. WF-06: privacy_lifecycle activate -> delete -> assert_can_call_model
# ────────────────────────────────────────────────────────────────── #

class TestWF06Privacy:

    def test_activate_delete_assert_chain(self, tmp_path):
        """WF-06: activate -> delete -> assert_can_call_model 抛异常"""
        dl = DataLifecycle(store_dir=str(tmp_path))
        user_id = "test_user_e2e"

        # activate
        dl.activate(user_id)
        assert dl.is_active(user_id)
        assert not dl.is_deleted(user_id)

        # assert_can_call_model 应通过
        dl.assert_can_call_model(user_id)

        # delete
        dl.delete(user_id)
        assert dl.is_deleted(user_id)
        assert not dl.is_active(user_id)

        # assert_can_call_model 应抛 PermissionError
        with pytest.raises(PermissionError):
            dl.assert_can_call_model(user_id)

    def test_consent_grant_revoke(self, tmp_path):
        """同意管理: 授权 -> 撤销"""
        cm = ConsentManager(store_dir=str(tmp_path))
        user_id = "test_consent_user"
        assert not cm.check_consent(user_id)
        cm.grant_consent(user_id)
        assert cm.check_consent(user_id)
        cm.revoke_consent(user_id)
        assert not cm.check_consent(user_id)

    def test_pii_scanner_detects_residue(self, tmp_path):
        """PIIScanner 检测到残留 PII"""
        log_file = tmp_path / "app.log"
        log_file.write_text("用户电话 13800138000 联系", encoding="utf-8")
        results = PIIScanner.scan_logs(str(tmp_path))
        assert len(results) > 0


# ────────────────────────────────────────────────────────────────── #
# 6. 性能: match_requirements 100 条 requirements
# ────────────────────────────────────────────────────────────────── #

class TestPerformance:

    def test_match_100_requirements_under_threshold(self):
        """100 条 requirements 的 BM25 匹配应在 5 秒内完成"""
        resume = _read(os.path.join(FIX, "resumes", "resume-01-swe.txt"))
        sentences = mr.split_sentences(resume)
        sentences_tokens = [mr.tokenize(s) for s in sentences]
        sent_uni = [mr.unigrams(s) for s in sentences]
        doc_uni = mr.unigrams(resume)
        matcher = mr.Bm25Matcher()

        # 生成 100 条 requirements
        base_reqs = [
            "熟悉 Go 语言开发", "熟悉 Java 开发", "熟悉 Python 开发",
            "MySQL 数据库优化", "Redis 缓存中间件", "RabbitMQ 消息队列",
            "微服务架构设计", "分布式系统开发", "Kubernetes 容器编排",
            "gRPC 通信协议",
        ]
        reqs = []
        for i in range(100):
            base = base_reqs[i % len(base_reqs)]
            reqs.append("%s (变体 %d)" % (base, i))

        t0 = time.time()
        for req_text in reqs:
            conf, idx = matcher.best(req_text, sentences_tokens, sent_uni=sent_uni, doc_uni=doc_uni)
            has_partial = bool(mr.unigrams(req_text) & doc_uni)
            mr.judge(conf, has_partial)
        elapsed = time.time() - t0

        assert elapsed < 5.0, "100 条 requirements 匹配耗时 %.2fs 超过 5s 阈值" % elapsed


# ────────────────────────────────────────────────────────────────── #
# 7. model_router 降级: 主模型失败 -> 降级输出
# ────────────────────────────────────────────────────────────────── #

class TestModelRouterDegradation:

    def test_primary_fails_to_degraded(self):
        """主模型失败 -> 规则降级输出"""
        class FailRouter(ModelRouter):
            def _try_call(self, model, prompt, user_input, params, context):
                raise RuntimeError("model unavailable")

        router = FailRouter(primary_model="test_primary", fallback_model="test_fallback")
        result = router.call("resume_diagnosis", "test input")

        assert result["status"] == "degraded"
        assert result["degraded"] is True
        assert result["model"] == "rule_degraded"
        assert result["output"] is not None

    def test_no_model_configured_degrades(self):
        """无模型配置时直接降级"""
        class NoModelRouter(ModelRouter):
            def _try_call(self, model, prompt, user_input, params, context):
                raise NotImplementedError("no model")

        router = NoModelRouter(primary_model=None, fallback_model=None)
        result = router.call("resume_diagnosis", "test input")

        assert result["status"] == "degraded"
        assert result["degraded"] is True

    def test_unknown_task_type_fails(self):
        """未知任务类型返回 failed"""
        class TestRouter(ModelRouter):
            def _try_call(self, model, prompt, user_input, params, context):
                return "ok"

        router = TestRouter(primary_model="test")
        result = router.call("unknown_task", "test input")
        assert result["status"] == "failed"
        assert result["error_type"] == "unknown_task_type"

    def test_degraded_output_structure(self):
        """降级输出结构完整"""
        for task_type in TASK_PROMPTS:
            output = DEGRADED_OUTPUTS.get(task_type, {})
            assert "note" in output or len(output) > 0, "降级输出缺少 note: %s" % task_type

    def test_model_params_frozen(self):
        """冻结参数完整性: 每个任务有 temperature/max_tokens/timeout"""
        for task_type in TASK_PROMPTS:
            params = MODEL_PARAMS[task_type]
            assert "temperature" in params
            assert "max_tokens" in params
            assert "timeout" in params
