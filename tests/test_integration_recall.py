#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""集成召回率测试：验证 match_requirements.py --backend embedding 的端到端效果。

对每对 resume/job：
  1. 用 --backend embedding 跑匹配，得到结果
  2. 与 expected.json 中的 covered/missing 标签对比
  3. 统计召回率、精确率、F1

用法:
  ZHIPU_API_KEY=xxx python tests/test_integration_recall.py
  ZHIPU_API_KEY=xxx python tests/test_integration_recall.py --model zhipu-embedding-3
"""
import argparse
import json
import os
import subprocess
import sys
import time

FIXTURES = "tests/fixtures-synthetic"
RESUME_DIR = os.path.join(FIXTURES, "resumes")
JOB_DIR = os.path.join(FIXTURES, "jobs")


def load_pairs():
    """加载所有 resume/job 配对（按编号匹配）。"""
    pairs = []
    for fname in sorted(os.listdir(RESUME_DIR)):
        if not fname.endswith(".txt"):
            continue
        base = fname.replace(".txt", "")  # resume-01-swe
        num = base.split("-")[1]  # 01
        expected_path = os.path.join(RESUME_DIR, base + ".expected.json")
        # 找同编号的 job
        job_txt = None
        job_expected = None
        for jname in os.listdir(JOB_DIR):
            if jname.startswith("job-%s-" % num):
                if jname.endswith(".txt"):
                    job_txt = os.path.join(JOB_DIR, jname)
                elif jname.endswith(".expected.json"):
                    job_expected = os.path.join(JOB_DIR, jname)
        if job_txt and job_expected and os.path.exists(expected_path):
            pairs.append({
                "num": num,
                "resume_txt": os.path.join(RESUME_DIR, fname),
                "resume_expected": expected_path,
                "job_txt": job_txt,
                "job_expected": job_expected,
            })
    return pairs


def get_expected_labels(expected_path):
    """从 ground-truth-labels.json 读取该 job 的期望状态（人工真值标注）。"""
    base = os.path.basename(expected_path)
    with open(os.path.join(FIXTURES, "ground-truth-labels.json"), encoding="utf-8") as f:
        data = json.load(f)
    labels = data.get(base)
    if labels is None:
        raise KeyError("ground-truth-labels.json 缺少 %s 的标注" % base)
    return labels


def run_match(resume_path, job_path, backend, model=None, output_path=None):
    """调用 match_requirements.py CLI。"""
    cmd = [
        sys.executable, "tools/match_requirements.py",
        "--resume", resume_path,
        "--job", job_path,
        "--backend", backend,
    ]
    if model and backend == "embedding":
        cmd.extend(["--embedding-model", model])
    if output_path:
        cmd.extend(["--output", output_path])
    child_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                            encoding="utf-8", env=child_env)
    if result.returncode != 0:
        print("STDERR:", result.stderr[-500:] if result.stderr else "")
        return None
    if output_path and os.path.exists(output_path):
        with open(output_path, encoding="utf-8") as f:
            return json.load(f)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def compute_metrics(actual_results, expected_labels):
    """计算召回率/精确率/F1。

    将 covered+weak 视为「匹配」，missing+unknown 视为「不匹配」。
    """
    tp = fp = fn = tn = 0
    for r in actual_results:
        rid = r["id"]
        actual_match = r["status"] in ("covered", "weak")
        expected_match = expected_labels.get(rid, "missing") in ("covered", "weak")
        if actual_match and expected_match:
            tp += 1
        elif actual_match and not expected_match:
            fp += 1
        elif not actual_match and expected_match:
            fn += 1
        else:
            tn += 1
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": round(recall, 4), "precision": round(precision, 4), "f1": round(f1, 4)}


def main():
    ap = argparse.ArgumentParser(description="集成召回率测试")
    ap.add_argument("--model", default=None,
                    help="embedding 模型: zhipu-embedding-2 / zhipu-embedding-3 / qianfan")
    ap.add_argument("--backend", default="embedding", choices=["bm25", "embedding"])
    args = ap.parse_args()

    if args.backend == "embedding" and not os.environ.get("ZHIPU_API_KEY"):
        print("[ERROR] ZHIPU_API_KEY 未设置", file=sys.stderr)
        sys.exit(1)

    pairs = load_pairs()
    print("=== 集成召回率测试 ===")
    print("后端: %s, 模型: %s" % (args.backend, args.model or "default"))
    print("测试对数: %d" % len(pairs))
    print()

    all_metrics = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    per_pair = []
    t0 = time.time()

    for pair in pairs:
        out_path = "/tmp/match_%s.json" % pair["num"]
        data = run_match(pair["resume_txt"], pair["job_expected"],
                         args.backend, args.model, out_path)
        if data is None:
            print("[FAIL] pair %s: 匹配失败" % pair["num"])
            continue

        expected_labels = get_expected_labels(pair["job_expected"])
        metrics = compute_metrics(data.get("results", []), expected_labels)
        per_pair.append((pair["num"], metrics))
        for k in all_metrics:
            all_metrics[k] += metrics[k]
        print("[pair %s] recall=%.4f  precision=%.4f  f1=%.4f  (tp=%d fp=%d fn=%d tn=%d)" % (
            pair["num"], metrics["recall"], metrics["precision"], metrics["f1"],
            metrics["tp"], metrics["fp"], metrics["fn"], metrics["tn"]))

    elapsed = time.time() - t0
    total = all_metrics
    recall = total["tp"] / (total["tp"] + total["fn"]) if (total["tp"] + total["fn"]) > 0 else 0
    precision = total["tp"] / (total["tp"] + total["fp"]) if (total["tp"] + total["fp"]) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    print()
    print("=== 汇总 ===")
    print("总对数: %d  耗时: %.1fs" % (len(pairs), elapsed))
    print("召回率: %.4f  精确率: %.4f  F1: %.4f" % (recall, precision, f1))
    print("tp=%d  fp=%d  fn=%d  tn=%d" % (total["tp"], total["fp"], total["fn"], total["tn"]))

    # 保存结果
    result_file = "tests/integration_recall_%s.json" % (
        args.model.replace("-", "_") if args.model else args.backend)
    summary = {
        "backend": args.backend,
        "model": args.model or "default",
        "pairs": len(pairs),
        "elapsed_sec": round(elapsed, 1),
        "total": total,
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "f1": round(f1, 4),
        "per_pair": [(p[0], p[1]) for p in per_pair],
    }
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("\n结果已保存到 %s" % result_file)


if __name__ == "__main__":
    main()
