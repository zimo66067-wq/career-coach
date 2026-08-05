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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from model_router import ZhipuChatRouter, QianfanModelRouter

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
    "resume_report": "同上简历文本",
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
    "jd_match_explain": "简历同上，JD同上",
    "interview_question": "后端开发工程师，5年经验，熟悉Go和分布式系统",
    "interview_review": "候选人回答了关于Go并发模型的问题，提到了GMP调度器",
    "seven_day_plan": "目标岗位：高级后端开发工程师，当前差距：缺乏K8s实战经验",
}

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
    summary = {task: {"success": 0, "failed": 0, "avg_latency_ms": 0, "degraded": 0} for task in TASK_TYPES}

    total_start = time.time()

    for task in TASK_TYPES:
        print(f"\n▶ {task}")
        user_input = TEST_INPUTS.get(task, "这是一个测试输入。")
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

                if result["status"] == "success":
                    summary[task]["success"] += 1
                else:
                    summary[task]["failed"] += 1

                if result["degraded"]:
                    summary[task]["degraded"] += 1

                print(f"  [{i+1}/{REPEAT}] {result['status']:7s}  "
                      f"model={result['model']:20s}  "
                      f"latency={latency_ms:5d}ms  "
                      f"degraded={result['degraded']}")

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

    report = {
        "meta": {
            "title": "P0-03 真实 AI 模型调用复测报告",
            "date": datetime.now().isoformat(),
            "model": MODEL,
            "total_tasks": len(TASK_TYPES),
            "repeat_per_task": REPEAT,
            "total_calls": total_calls,
            "total_time_ms": total_time,
        },
        "summary": {
            "success_rate": f"{total_success}/{total_calls}",
            "success_pct": round(total_success / total_calls * 100, 1) if total_calls else 0,
            "degraded_count": total_degraded,
            "failed_count": total_failed,
        },
        "per_task": summary,
        "log_file": log_path,
    }

    with io.open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # ---- 终端摘要 ----
    print("\n" + "=" * 60)
    print("复测完成")
    print(f"总调用: {total_success}/{total_calls} 成功 ({report['summary']['success_pct']}%)")
    print(f"降级次数: {total_degraded}")
    print(f"失败次数: {total_failed}")
    print(f"总耗时: {total_time}ms")
    print(f"日志: {log_path}")
    print(f"报告: {report_path}")
    print("=" * 60)

    return 0 if total_failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
