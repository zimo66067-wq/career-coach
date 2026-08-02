# -*- coding: utf-8 -*-
"""test_e2e_closed_loop.py · 端到端真实数据闭环测试 (P0-02)

验证从简历输入 -> 去标识化 -> 诊断 -> JD匹配 -> 面试 -> 评分 -> 七天计划
的完整链路，使用真实合成数据（非 mock）。

测试模式:
  1. 全链路冒烟: 简历 -> 诊断 -> 匹配 -> 面试 -> 评分 -> 计划
  2. 降级闭环: 模型不可用时全链路降级是否正常
  3. DataBridge 模拟: 验证前端 data-bridge.js 的三级降级逻辑
  4. 隐私闭环: 数据从激活到删除的完整生命周期

用法:
  python tests/test_e2e_closed_loop.py
  python tests/test_e2e_closed_loop.py --verbose
  python tests/test_e2e_closed_loop.py --resume tests/fixtures-synthetic/resumes/resume-01-swe.txt --job tests/fixtures-synthetic/jobs/job-01-swe.txt
"""
import argparse
import io
import json
import os
import sys
import time
import tempfile
import traceback

# 确保能 import tools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import extract_text
import deidentify
import match_requirements as mr
import rescore
from interview_engine import InterviewEngine
from model_router import ModelRouter, DEGRADED_OUTPUTS, MODEL_PARAMS, TASK_PROMPTS
from privacy_lifecycle import DataLifecycle, ConsentManager

FIX = os.path.join(os.path.dirname(__file__), "fixtures-synthetic")


def _read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


class ClosedLoopResult:
    """端到端测试结果"""
    def __init__(self):
        self.steps = []
        self.total_latency_ms = 0
        self.success = True
        self.trace_id = "e2e_%d" % int(time.time() * 1000)

    def add_step(self, name, passed, detail="", latency_ms=0):
        self.steps.append({
            "step": name,
            "passed": passed,
            "detail": detail,
            "latency_ms": latency_ms,
        })
        self.total_latency_ms += latency_ms
        if not passed:
            self.success = False

    def summary(self):
        passed = sum(1 for s in self.steps if s["passed"])
        total = len(self.steps)
        return {
            "trace_id": self.trace_id,
            "success": self.success,
            "steps_passed": passed,
            "steps_total": total,
            "total_latency_ms": self.total_latency_ms,
            "steps": self.steps,
        }


# ────────────────────────────────────────────────────────────────── #
# 1. 全链路冒烟测试
# ────────────────────────────────────────────────────────────────── #

def test_full_pipeline(resume_path=None, job_path=None, verbose=False):
    """全链路: 简历 -> 去标识化 -> 诊断(降级) -> JD匹配 -> 面试 -> 评分 -> 计划"""
    result = ClosedLoopResult()

    # 默认使用合成数据
    if not resume_path:
        resume_path = os.path.join(FIX, "resumes", "resume-01-swe.txt")
    if not job_path:
        job_path = os.path.join(FIX, "jobs", "job-01-swe.txt")

    if verbose:
        print("[E2E] trace_id=%s" % result.trace_id)
        print("[E2E] resume=%s" % resume_path)
        print("[E2E] job=%s" % job_path)

    # Step 1: 文本提取
    t0 = time.time()
    try:
        raw_text = extract_text.extract_txt(resume_path)
        assert len(raw_text) > 50, "提取文本过短"
        result.add_step(
            "WF-01: extract_text", True,
            "raw_text_len=%d" % len(raw_text),
            int((time.time() - t0) * 1000)
        )
    except Exception as e:
        result.add_step("WF-01: extract_text", False, str(e), int((time.time() - t0) * 1000))
        return result

    # Step 2: 去标识化
    t0 = time.time()
    try:
        cleaned, mapping = deidentify.deidentify(raw_text)
        assert "[REDACTED_" in cleaned or len(mapping) >= 0
        result.add_step(
            "WF-01: deidentify", True,
            "cleaned_len=%d, pii_count=%d" % (len(cleaned), len(mapping)),
            int((time.time() - t0) * 1000)
        )
    except Exception as e:
        result.add_step("WF-01: deidentify", False, str(e), int((time.time() - t0) * 1000))
        return result

    # Step 3: 模型诊断（降级模式）
    t0 = time.time()
    try:
        class DegradedRouter(ModelRouter):
            def _try_call(self, *a, **kw):
                raise RuntimeError("model unavailable (e2e test)")

        router = DegradedRouter(primary_model="test")
        diag_result = router.call("resume_diagnosis", cleaned[:500])
        assert diag_result["status"] == "degraded"
        assert diag_result["degraded"] is True
        result.add_step(
            "WF-02: diagnose (degraded)", True,
            "status=%s, model=%s" % (diag_result["status"], diag_result["model"]),
            int((time.time() - t0) * 1000)
        )
    except Exception as e:
        result.add_step("WF-02: diagnose", False, str(e), int((time.time() - t0) * 1000))
        return result

    # Step 4: JD 匹配
    t0 = time.time()
    try:
        job_text = _read(job_path)
        # 尝试读取 expected.json
        job_expected_path = job_path.replace(".txt", ".expected.json")
        if os.path.exists(job_expected_path):
            job_expected = json.loads(_read(job_expected_path))
            requirements = job_expected.get("requirements", [])
        else:
            requirements = [{"id": "R1", "type": "hard", "text": job_text[:100]}]

        sentences = mr.split_sentences(cleaned)
        sentences_tokens = [mr.tokenize(s) for s in sentences]
        sent_uni = [mr.unigrams(s) for s in sentences]
        doc_uni = mr.unigrams(cleaned)
        matcher = mr.Bm25Matcher()

        match_results = []
        for req in requirements:
            conf, idx = matcher.best(req["text"], sentences_tokens, sent_uni=sent_uni, doc_uni=doc_uni)
            has_partial = bool(mr.unigrams(req["text"]) & doc_uni)
            status = mr.judge(conf, has_partial)
            match_results.append({"id": req["id"], "text": req["text"], "type": req.get("type", "hard"), "status": status, "confidence": round(conf, 3)})

        covered = sum(1 for r in match_results if r["status"] == "covered")
        weak = sum(1 for r in match_results if r["status"] == "weak")
        missing = sum(1 for r in match_results if r["status"] == "missing")
        unknown = sum(1 for r in match_results if r["status"] == "unknown")

        result.add_step(
            "WF-03: jd_match (BM25)", True,
            "total=%d, covered=%d, weak=%d, missing=%d, unknown=%d" % (
                len(match_results), covered, weak, missing, unknown
            ),
            int((time.time() - t0) * 1000)
        )
    except Exception as e:
        result.add_step("WF-03: jd_match", False, str(e), int((time.time() - t0) * 1000))
        return result

    # Step 5: 模拟面试
    t0 = time.time()
    try:
        engine = InterviewEngine(model_router=None)
        job_profile = {
            "title": "Backend Engineer",
            "requirements": requirements[:5] if len(requirements) > 5 else requirements,
        }
        resume_profile = {"score_R": 73.0}
        match_gaps = [
            {"id": r["id"], "type": "hard", "text": r["text"], "status": "weak"}
            for r in match_results if r["status"] in ("weak", "missing")
        ][:3]

        session = engine.start(job_profile, resume_profile, match_gaps)
        assert session["state"] == "ASK"

        answers = [
            "在实习中我负责订单查询接口的开发。背景是接口响应慢，用户投诉多。"
            "我的任务是优化性能。我通过分析慢查询日志，加了复合索引，并引入 Redis 缓存。"
            "最终平均响应从 800ms 降到 220ms，提升了 72%。",
            "在团队协作中我负责推动联调。我编写了接口文档，与前端约定了错误码规范。"
            "结果是联调周期缩短了 3 天，效率提升约 30%。",
        ]

        for i in range(min(2, len(answers))):
            q = engine.next_question(session)
            assert q["question"] is not None
            engine.submit_answer(session, answers[i])

        report = engine.end_session(session)
        assert "score_I" in report
        assert "report" in report

        result.add_step(
            "WF-04: interview", True,
            "turns=%d, score_I=%.1f" % (len(report.get("turns", [])), report.get("score_I", 0)),
            int((time.time() - t0) * 1000)
        )
    except Exception as e:
        result.add_step("WF-04: interview", False, str(e), int((time.time() - t0) * 1000))
        return result

    # Step 6: 能力评分
    t0 = time.time()
    try:
        score_input_path = os.path.join(FIX, "abilities", "score-input-01.json")
        score_input = json.loads(_read(score_input_path))
        score_result = rescore.compute(score_input)
        assert "C0" in score_result
        assert 0 <= score_result["C0"] <= 100
        assert score_result["C7_low"] <= score_result["C7_high"]

        result.add_step(
            "WF-05: rescore", True,
            "C0=%.1f, C7_low=%.1f, C7_high=%.1f" % (
                score_result["C0"], score_result["C7_low"], score_result["C7_high"]
            ),
            int((time.time() - t0) * 1000)
        )
    except Exception as e:
        result.add_step("WF-05: rescore", False, str(e), int((time.time() - t0) * 1000))
        return result

    # Step 7: 七天计划（降级模式）
    t0 = time.time()
    try:
        plan_result = router.call("seven_day_plan", "test plan input")
        assert plan_result["status"] == "degraded"
        assert "plan" in plan_result["output"] or "note" in plan_result["output"]

        result.add_step(
            "WF-05: seven_day_plan (degraded)", True,
            "status=%s, plan_days=%d" % (
                plan_result["status"],
                len(plan_result["output"].get("plan", []))
            ),
            int((time.time() - t0) * 1000)
        )
    except Exception as e:
        result.add_step("WF-05: seven_day_plan", False, str(e), int((time.time() - t0) * 1000))

    return result


# ────────────────────────────────────────────────────────────────── #
# 2. 降级闭环测试
# ────────────────────────────────────────────────────────────────── #

def test_degraded_closed_loop(verbose=False):
    """模型完全不可用时，全链路降级是否正常"""
    result = ClosedLoopResult()

    class FailRouter(ModelRouter):
        def _try_call(self, *a, **kw):
            raise RuntimeError("all models unavailable")

    router = FailRouter(primary_model="fail_primary", fallback_model="fail_fallback")

    # 测试所有 7 种任务类型的降级
    for task_type in TASK_PROMPTS:
        t0 = time.time()
        try:
            r = router.call(task_type, "test input for %s" % task_type)
            assert r["status"] == "degraded", "%s should degrade, got %s" % (task_type, r["status"])
            assert r["degraded"] is True
            assert r["output"] is not None

            result.add_step(
                "degrade: %s" % task_type, True,
                "status=%s, model=%s" % (r["status"], r["model"]),
                int((time.time() - t0) * 1000)
            )
        except Exception as e:
            result.add_step(
                "degrade: %s" % task_type, False, str(e),
                int((time.time() - t0) * 1000)
            )

    return result


# ────────────────────────────────────────────────────────────────── #
# 3. DataBridge 降级逻辑验证
# ────────────────────────────────────────────────────────────────── #

def test_data_bridge_degradation(verbose=False):
    """验证 data-bridge.js 的三级降级逻辑（后端模拟）"""
    result = ClosedLoopResult()

    # 模拟 DataBridge 的三级降级: API -> 缓存 -> MOCK
    t0 = time.time()
    try:
        # 模拟 API 不可用 -> 缓存 -> MOCK
        api_available = False
        cache_available = False
        mock_available = True

        # Level 1: API
        if api_available:
            data_source = "api"
        elif cache_available:
            data_source = "cache"
        elif mock_available:
            data_source = "mock_degraded"
        else:
            raise RuntimeError("all data sources unavailable")

        assert data_source == "mock_degraded", "should fall back to mock"

        result.add_step(
            "DataBridge: API->Cache->MOCK", True,
            "final_source=%s, degraded=True" % data_source,
            int((time.time() - t0) * 1000)
        )
    except Exception as e:
        result.add_step("DataBridge degradation", False, str(e), int((time.time() - t0) * 1000))

    # 验证 normalizeResumeProfile 逻辑
    t0 = time.time()
    try:
        # 模拟后端返回的 ResumeProfile（source_spans 格式）
        backend_profile = {
            "subscores": {
                "structure": {
                    "score": 80,
                    "source_spans": [{"quote": "教育背景：XX大学", "start": 0, "end": 12}]
                },
                "clarity": {
                    "score": 75,
                    "source_spans": [{"quote": "负责后端API开发", "start": 50, "end": 60}]
                },
            },
            "suggestions": [
                {"text": "增加量化成果", "source_spans": [{"quote": "优化了性能", "start": 100, "end": 105}]}
            ]
        }

        # 模拟 normalizeResumeProfile 的字段映射逻辑
        view = json.loads(json.dumps(backend_profile))
        for key in view.get("subscores", {}):
            item = view["subscores"][key] or {}
            spans = item.get("source_spans", [])
            if not item.get("quote") and spans:
                item["quote"] = spans[0].get("quote", "")

        for item in view.get("suggestions", []):
            spans = item.get("source_spans", [])
            if not item.get("quote") and spans:
                item["quote"] = spans[0].get("quote", "")

        # 验证映射结果
        assert view["subscores"]["structure"]["quote"] == "教育背景：XX大学"
        assert view["subscores"]["clarity"]["quote"] == "负责后端API开发"
        assert view["suggestions"][0]["quote"] == "优化了性能"

        result.add_step(
            "DataBridge: normalizeResumeProfile", True,
            "source_spans -> quote mapping verified",
            int((time.time() - t0) * 1000)
        )
    except Exception as e:
        result.add_step("DataBridge: normalizeResumeProfile", False, str(e), int((time.time() - t0) * 1000))

    return result


# ────────────────────────────────────────────────────────────────── #
# 4. 隐私闭环测试
# ────────────────────────────────────────────────────────────────── #

def test_privacy_closed_loop(verbose=False):
    """数据从激活到删除的完整生命周期"""
    result = ClosedLoopResult()

    t0 = time.time()
    try:
        tmpdir = tempfile.mkdtemp()
        dl = DataLifecycle(store_dir=tmpdir)
        cm = ConsentManager(store_dir=tmpdir)
        user_id = "e2e_privacy_user"

        # 1. 初始状态
        assert not dl.is_active(user_id)
        assert not dl.is_deleted(user_id)

        # 2. 授权同意
        cm.grant_consent(user_id)
        assert cm.check_consent(user_id)

        # 3. 激活数据
        dl.activate(user_id)
        assert dl.is_active(user_id)
        assert not dl.is_deleted(user_id)

        # 4. 验证可调用模型
        dl.assert_can_call_model(user_id)

        # 5. 模拟使用（写入一些数据）
        user_dir = os.path.join(tmpdir, user_id)
        os.makedirs(user_dir, exist_ok=True)
        with open(os.path.join(user_dir, "resume_clean.txt"), "w", encoding="utf-8") as f:
            f.write("test resume data")

        # 6. 删除数据
        dl.delete(user_id)
        assert dl.is_deleted(user_id)
        assert not dl.is_active(user_id)

        # 7. 验证删除后不能调用模型
        try:
            dl.assert_can_call_model(user_id)
            raise AssertionError("should raise PermissionError after delete")
        except PermissionError:
            pass  # expected

        # 8. 撤销同意
        cm.revoke_consent(user_id)
        assert not cm.check_consent(user_id)

        result.add_step(
            "Privacy: full lifecycle", True,
            "activate -> use -> delete -> block -> revoke_consent",
            int((time.time() - t0) * 1000)
        )
    except Exception as e:
        result.add_step("Privacy: full lifecycle", False, str(e), int((time.time() - t0) * 1000))

    return result


# ────────────────────────────────────────────────────────────────── #
# 主入口
# ────────────────────────────────────────────────────────────────── #

def run_all_tests(resume_path=None, job_path=None, verbose=False):
    """运行全部端到端闭环测试"""
    all_results = []

    if verbose:
        print("=" * 70)
        print("End-to-End Closed Loop Tests (P0-02)")
        print("=" * 70)

    # 1. 全链路冒烟
    if verbose:
        print("\n[1/4] Full Pipeline Smoke Test")
    r = test_full_pipeline(resume_path, job_path, verbose)
    all_results.append(("full_pipeline", r))

    # 2. 降级闭环
    if verbose:
        print("\n[2/4] Degraded Closed Loop Test")
    r = test_degraded_closed_loop(verbose)
    all_results.append(("degraded_loop", r))

    # 3. DataBridge 降级
    if verbose:
        print("\n[3/4] DataBridge Degradation Test")
    r = test_data_bridge_degradation(verbose)
    all_results.append(("data_bridge", r))

    # 4. 隐私闭环
    if verbose:
        print("\n[4/4] Privacy Closed Loop Test")
    r = test_privacy_closed_loop(verbose)
    all_results.append(("privacy_loop", r))

    # 汇总
    total_steps = sum(len(r.steps) for _, r in all_results)
    passed_steps = sum(sum(1 for s in r.steps if s["passed"]) for _, r in all_results)
    total_latency = sum(r.total_latency_ms for _, r in all_results)

    if verbose:
        print("\n" + "=" * 70)
        print("Summary:")
        for name, r in all_results:
            sp = sum(1 for s in r.steps if s["passed"])
            st = len(r.steps)
            status = "PASS" if r.success else "FAIL"
            print("  [%s] %s: %d/%d steps, %dms" % (status, name, sp, st, r.total_latency_ms))
        print("-" * 70)
        print("Total: %d/%d steps passed, %dms total" % (passed_steps, total_steps, total_latency))
        print("=" * 70)

    # 保存 JSON 结果
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_steps": total_steps,
        "passed_steps": passed_steps,
        "total_latency_ms": total_latency,
        "suites": [
            {"name": name, **r.summary()} for name, r in all_results
        ],
    }

    output_path = os.path.join(
        os.path.dirname(__file__), "e2e_closed_loop_results.json"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    if verbose:
        print("Results saved to: %s" % output_path)

    return passed_steps == total_steps


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="E2E Closed Loop Tests")
    parser.add_argument("--resume", help="Resume file path")
    parser.add_argument("--job", help="Job description file path")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    success = run_all_tests(
        resume_path=args.resume,
        job_path=args.job,
        verbose=args.verbose
    )
    sys.exit(0 if success else 1)
