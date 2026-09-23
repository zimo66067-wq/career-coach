# -*- coding: utf-8 -*-
"""p0-03-real-model-test.py · 7种任务类型各3次真实模型复测

用法:
  python scripts/p0-03-real-model-test.py

环境要求:
  - ZHIPU_API_KEY 已在当前 shell 导出（用于 Embedding 验证）
  - QIANFAN_API_KEY 已在当前 shell 导出（用于 Chat 复测）

输出:
  - deliverables/p0-03-evidence/ 下的日志和报告
"""
import io
import json
import os
import sys
import time
import hashlib
from datetime import datetime

# ============================================================================
# API Key 从环境变量读取，不要硬编码
# ============================================================================
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "")
QIANFAN_API_KEY = os.environ.get("QIANFAN_API_KEY", "")

if ZHIPU_API_KEY:
    os.environ["ZHIPU_API_KEY"] = ZHIPU_API_KEY
if QIANFAN_API_KEY:
    os.environ["QIANFAN_API_KEY"] = QIANFAN_API_KEY

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from providers.model_router import ZhipuChatRouter, QianfanModelRouter

# ============================================================================
# 配置
# ============================================================================
# ============================================================================
# 配置（支持智谱 / 千帆双模型切换）
# ============================================================================
# 自动检测可用模型：
#   - 如果设置了 QIANFAN_ACCESS_KEY + QIANFAN_SECRET_KEY，优先用千帆
#   - 否则使用智谱 ZHIPU_API_KEY
# ============================================================================
if os.environ.get("QIANFAN_ACCESS_KEY") and os.environ.get("QIANFAN_SECRET_KEY"):
    ROUTER_CLASS = QianfanModelRouter
    MODEL = os.environ.get("P0_MODEL", "ernie-lite-8k")
    PROVIDER = "qianfan"
elif os.environ.get("ZHIPU_API_KEY"):
    ROUTER_CLASS = ZhipuChatRouter
    MODEL = os.environ.get("P0_MODEL", "glm-4-flash")
    PROVIDER = "zhipu"
else:
    raise EnvironmentError(
        "Neither QIANFAN_ACCESS_KEY/QIANFAN_SECRET_KEY nor ZHIPU_API_KEY set. "
        "Please configure at least one model provider."
    )

REPEAT = 3
TASK_TYPES = [
    "resume_diagnosis",
    "resume_report",
    "jd_extract",
    "jd_match_explain",
    "interview_question",
    "interview_review",
    "seven_day_plan",
]

# ---------------------------------------------------------------------------
# 真实输入构造（2026-09-23 修）
#
# 为什么必须修：`resume_report` 与 `jd_match_explain` 的提示词要的是**结构化输入**
# （见 prompts/resume/report-deep.md 与 prompts/match/explain.md 的「## 用户输入」段），
# 而这里原先喂的是字符串 "同上简历文本" / "简历同上，JD同上"。模型如实拒答 ——
# 实测原文：「由于您没有提供具体的 ResumeProfile JSON 内容和简历文本，我无法生成
# 针对性的深度诊断报告。请提供…」—— 而脚本只看 HTTP 层 status，于是拒答被计成
# success（"21/21 成功"是这么来的）。现在改用 tests/fixtures-synthetic/ 里
# **已过 Schema 校验**的真实样本构造输入。
#
# 刻意**不**在失败时回退到占位符：占位符正是假绿的成因。构造不出来就如实记为
# "无有效输入"，而不是再产一次假绿。
# ---------------------------------------------------------------------------
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "tests", "fixtures-synthetic")


def _read_fixture(*parts):
    with io.open(os.path.join(FIXTURES_DIR, *parts), encoding="utf-8") as f:
        return f.read()


def _build_structured_inputs():
    """构造 resume_report / jd_match_explain 需要的结构化输入。"""
    from services.match_service import match_job_profile

    resume_profile = json.loads(_read_fixture("resumes", "resume-01-swe.expected.json"))
    resume_text = _read_fixture("resumes", "resume-01-swe.txt")
    job_profile = json.loads(_read_fixture("jobs", "job-01-swe.expected.json"))

    resume_dump = json.dumps(resume_profile, ensure_ascii=False)
    job_dump = json.dumps(job_profile, ensure_ascii=False)
    # 四态匹配结果由规则引擎算出来（分数由规则算、解释才交给模型）
    match_result = match_job_profile(resume_text, job_profile)

    resume_report_input = "ResumeProfile: %s\n简历文本: %s" % (resume_dump, resume_text)
    jd_match_explain_input = "JobProfile: %s\n四态结果: %s\nResumeProfile: %s" % (
        job_dump, json.dumps(match_result, ensure_ascii=False), resume_dump)
    return resume_report_input, jd_match_explain_input


try:
    _RESUME_REPORT_INPUT, _JD_MATCH_EXPLAIN_INPUT = _build_structured_inputs()
    INPUT_BUILD_ERROR = None
except Exception as _exc:  # noqa: BLE001
    _RESUME_REPORT_INPUT = _JD_MATCH_EXPLAIN_INPUT = None
    INPUT_BUILD_ERROR = "%s: %s" % (type(_exc).__name__, _exc)

# 固定测试输入（简历 + JD 样本）
TEST_INPUTS = {
    "resume_diagnosis": """
姓名：张三
电话：13800138000
邮箱：test@example.com
教育：北京大学 计算机科学与技术 本科
工作：字节跳动 后端开发工程师 2021.07-至今
    负责抖音电商订单系统核心链路开发
    主导支付异步化改造，QPS从2k提升到12k
    使用Go、MySQL、Redis、Kafka
技能：Go、Java、MySQL、Redis、Kafka、Docker、K8s
""",
    "resume_report": _RESUME_REPORT_INPUT,
    "jd_extract": """
高级后端开发工程师
岗位职责：
1. 负责公司核心交易系统的架构设计与开发
2. 主导高并发场景下的性能优化
3. 参与技术方案评审与代码审查
任职要求：
1. 本科及以上学历，计算机相关专业
2. 熟悉Go或Java至少一门语言并有项目经验
3. 熟悉MySQL索引优化与慢查询分析
4. 了解Redis缓存使用场景
5. 熟悉消息队列RabbitMQ/Kafka
""",
    "jd_match_explain": _JD_MATCH_EXPLAIN_INPUT,
    "interview_question": "后端开发工程师，5年经验，熟悉Go和分布式系统",
    "interview_review": "候选人回答了关于Go并发模型的问题，提到了GMP调度器",
    "seven_day_plan": "目标岗位：高级后端开发工程师，当前差距：缺乏K8s实战经验",
}

# ---------------------------------------------------------------------------
# 内容断言（2026-09-23 新增）
#
# 判据必须是**内容**，不能只看 HTTP 层。下面每条拒答标记都来自实测的模型原文
# （deliverables/p0-03-evidence/ 下 20260921_150058 与 20260806_* 两批）：
#   「由于您没有提供具体的 ResumeProfile JSON 内容和简历文本，我无法生成针对性的…」
#   「由于您没有提供具体的四态匹配结果（covered/weak/missing/unknown）…我无法直接生成…」
#   「…我将提供一个示例性的深度诊断报告模板，您可以根据实际情况进行填充。」
# 注意最后一种：它**输出很长**、结构看着像模像样，但内容是编的模板 —— 只看长度抓不到，
# 所以标记判据是主力，长度判据只是补充。
# ---------------------------------------------------------------------------
REFUSAL_MARKERS = (
    "无法生成", "无法为您生成", "无法直接生成", "无法撰写", "我无法",
    "没有提供", "未提供", "请提供完整", "请提供具体",
    "示例框架", "示例性", "示例报告", "示例模板", "基于假设内容",
    "您可以根据实际情况进行填充", "可以根据实际情况进行调整",
)

#: 长文任务的**最小**长度下限（实测：正常输出 2k 字符以上，拒答多为 100~300 字符）
MIN_TEXT_LEN = {"resume_report": 400, "jd_match_explain": 200}


def output_to_text(output):
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        return json.dumps(output, ensure_ascii=False)
    return "" if output is None else str(output)


def judge_output(task, output):
    """判**内容**是否有效，返回 (ok, reason)。reason 为 None 表示有效。

    只收能确定的判据：空输出、命中拒答标记、长文任务过短。
    刻意不对结构化任务做键名断言 —— 那要靠猜返回结构，猜错就是制造假红。
    """
    text = output_to_text(output)
    if not text.strip():
        return False, "empty_output"
    for marker in REFUSAL_MARKERS:
        if marker in text:
            return False, "refusal:" + marker
    floor = MIN_TEXT_LEN.get(task)
    if floor and len(text.strip()) < floor:
        return False, "too_short:%d<%d" % (len(text.strip()), floor)
    return True, None

OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "deliverables", "p0-03-evidence"
)

# ============================================================================
# 执行
# ============================================================================
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def main():
    ensure_dir(OUTPUT_DIR)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(OUTPUT_DIR, f"p0-03-run-{timestamp}.jsonl")
    report_path = os.path.join(OUTPUT_DIR, f"p0-03-report-{timestamp}.json")

    print("=" * 60)
    print("P0-03 真实 AI 模型调用复测")
    print(f"模型提供商: {PROVIDER}")
    print(f"模型: {MODEL}")
    print(f"路由器: {ROUTER_CLASS.__name__}")
    print(f"任务类型: {len(TASK_TYPES)} 种 × {REPEAT} 次 = {len(TASK_TYPES)*REPEAT} 次调用")
    print(f"输出目录: {OUTPUT_DIR}")
    print("=" * 60)

    router = ROUTER_CLASS(primary_model=MODEL)

    all_results = []
    summary = {task: {"success": 0, "invalid": 0, "failed": 0, "skipped": 0,
                      "avg_latency_ms": 0, "degraded": 0} for task in TASK_TYPES}

    total_start = time.time()

    for task in TASK_TYPES:
        print(f"\n▶ {task}")
        user_input = TEST_INPUTS.get(task)
        if not user_input:
            # 结构化输入没构造出来（fixture 缺失/匹配引擎异常）。**不降级成占位符**：
            # 占位符会让模型拒答、而拒答曾一直被计成 success。
            summary[task]["skipped"] = REPEAT
            print("  SKIP   没有可用输入（结构化输入构造失败），本项不产出任何证据")
            continue
        latencies = []

        for i in range(REPEAT):
            run_id = f"{task}_run{i+1}"
            t0 = time.time()
            try:
                result = router.call(task, user_input, {"test_run": i+1})
                latency_ms = result.get("latency_ms", int((time.time() - t0) * 1000))
                latencies.append(latency_ms)

                # 安全提取 output_preview（支持字符串和字典）
                raw_output = result.get("output")
                if isinstance(raw_output, dict):
                    preview = json.dumps(raw_output, ensure_ascii=False)[:200]
                elif isinstance(raw_output, str):
                    preview = raw_output[:200]
                else:
                    preview = str(raw_output)[:200]

                record = {
                    "run_id": run_id,
                    "task": task,
                    "status": result["status"],
                    "model": result["model"],
                    "latency_ms": latency_ms,
                    "degraded": result["degraded"],
                    "error_type": result.get("error_type"),
                    "output_preview": preview,
                    "timestamp": datetime.now().isoformat(),
                }

                all_results.append(record)

                # 内容断言：HTTP 层成功 ≠ 内容有效（2026-09-23）
                content_ok, content_reason = judge_output(task, result.get("output"))
                record["content_ok"] = content_ok
                record["content_reason"] = content_reason

                if result["status"] == "success":
                    if content_ok:
                        summary[task]["success"] += 1
                    else:
                        summary[task]["invalid"] += 1
                else:
                    summary[task]["failed"] += 1

                if result["degraded"]:
                    summary[task]["degraded"] += 1

                print(f"  [{i+1}/{REPEAT}] {result['status']:7s} "
                      f"{'valid  ' if content_ok else 'INVALID'}  "
                      f"model={result['model']:20s}  "
                      f"latency={latency_ms:5d}ms  "
                      f"degraded={result['degraded']}"
                      + ("" if content_ok else f"   <- {content_reason}"))

            except Exception as e:
                latency_ms = int((time.time() - t0) * 1000)
                record = {
                    "run_id": run_id,
                    "task": task,
                    "status": "error",
                    "model": MODEL,
                    "latency_ms": latency_ms,
                    "degraded": False,
                    "error_type": type(e).__name__,
                    "error_msg": str(e)[:200],
                    "timestamp": datetime.now().isoformat(),
                }
                all_results.append(record)
                summary[task]["failed"] += 1
                print(f"  [{i+1}/{REPEAT}] ERROR   {type(e).__name__}: {str(e)[:80]}")

            time.sleep(0.3)  # 避免触发限流

        if latencies:
            summary[task]["avg_latency_ms"] = int(sum(latencies) / len(latencies))

    total_time = int((time.time() - total_start) * 1000)

    # ---- 写入 JSONL 日志 ----
    with io.open(log_path, "w", encoding="utf-8") as f:
        for rec in all_results:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---- 生成报告 ----
    total_calls = len(TASK_TYPES) * REPEAT
    total_success = sum(s["success"] for s in summary.values())
    total_failed = sum(s["failed"] for s in summary.values())
    total_degraded = sum(s["degraded"] for s in summary.values())
    total_invalid = sum(s["invalid"] for s in summary.values())
    total_skipped = sum(s["skipped"] for s in summary.values())
    actual_calls = total_calls - total_skipped

    report = {
        "meta": {
            "title": "P0-03 真实 AI 模型调用复测报告",
            "date": datetime.now().isoformat(),
            "model": MODEL,
            "total_tasks": len(TASK_TYPES),
            "repeat_per_task": REPEAT,
            "total_calls": total_calls,
            "actual_calls": actual_calls,
            "total_time_ms": total_time,
            "input_build_error": INPUT_BUILD_ERROR,
        },
        "summary": {
            "success_rate": f"{total_success}/{total_calls}",
            "success_pct": round(total_success / total_calls * 100, 1) if total_calls else 0,
            "content_valid_rate": (f"{total_success}/{actual_calls}" if actual_calls else "0/0"),
            "content_invalid_count": total_invalid,
            "skipped_count": total_skipped,
            "degraded_count": total_degraded,
            "failed_count": total_failed,
            "content_assertion": (
                "success 必须同时通过内容断言：空输出 / 命中拒答标记 / 长文过短 都记为 "
                "INVALID（不计入 success）。2026-09-23 之前只判 HTTP 层 status，"
                "模型拒答被计成 success。"
            ),
        },
        "per_task": summary,
        "log_file": log_path,
    }

    with io.open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # ---- 终端摘要 ----
    print("\n" + "=" * 60)
    print("复测完成")
    print(f"HTTP 层成功: {total_success}/{total_calls}")
    print(f"内容无效(INVALID): {total_invalid}   <- 拒答/空输出/过短，不计入成功")
    print(f"跳过(无有效输入): {total_skipped}")
    print(f"降级次数: {total_degraded}")
    print(f"失败次数: {total_failed}")
    if INPUT_BUILD_ERROR:
        print(f"结构化输入构造失败: {INPUT_BUILD_ERROR}")
    print(f"总耗时: {total_time}ms")
    print(f"日志: {log_path}")
    print(f"报告: {report_path}")
    print("=" * 60)

    # 有失败 / 有内容无效 / 有跳过，都算"没达成" —— 证据不足也是没达成。
    ok = (total_failed == 0 and total_invalid == 0 and total_skipped == 0)
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
