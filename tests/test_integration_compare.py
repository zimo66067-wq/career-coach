#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""集成对比测试：BM25 vs Zhipu Embedding 端到端匹配质量对比。

对每对 resume/job：
  1. 分别用 --backend bm25 和 --backend embedding 跑匹配
  2. 对比两者的 status 判定差异
  3. 统计 embedding 相对 BM25 的改进

用法:
  ZHIPU_API_KEY=xxx python tests/test_integration_compare.py
  ZHIPU_API_KEY=xxx python tests/test_integration_compare.py --model zhipu-embedding-3
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
    """加载 10 对 resume/job。"""
    pairs = []
    for num in range(1, 11):
        num_str = "%02d" % num
        # 找 resume
        resume_txt = None
        for fname in os.listdir(RESUME_DIR):
            if fname.startswith("resume-%s-" % num_str) and fname.endswith(".txt"):
                resume_txt = os.path.join(RESUME_DIR, fname)
                break
        # 找 job
        job_txt = None
        for jname in os.listdir(JOB_DIR):
            if jname.startswith("job-%s-" % num_str) and jname.endswith(".txt"):
                job_txt = os.path.join(JOB_DIR, jname)
                break
        if resume_txt and job_txt:
            pairs.append({"num": num_str, "resume": resume_txt, "job": job_txt})
    return pairs


def run_match(resume_path, job_path, backend, model=None):
    """调用 match_requirements.py CLI，返回解析后的 JSON。"""
    out_path = "/tmp/match_result.json"
    cmd = [
        sys.executable, "tools/match_requirements.py",
        "--resume", resume_path,
        "--job", job_path,
        "--backend", backend,
        "--output", out_path,
    ]
    if model and backend == "embedding":
        cmd.extend(["--embedding-model", model])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding="utf-8")
    if result.returncode != 0:
        print("  STDERR:", (result.stderr or "")[-300:])
        return None
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            return json.load(f)
    return None


def compare_results(bm25_data, emb_data):
    """对比两组匹配结果。"""
    bm25_results = {r["id"]: r for r in bm25_data.get("results", [])}
    emb_results = {r["id"]: r for r in emb_data.get("results", [])}

    diffs = []
    agree = 0
    emb_better = 0  # embedding 判 covered/weak 而 BM25 判 missing/unknown
    bm25_better = 0  # 反之

    for rid in bm25_results:
        b_status = bm25_results[rid]["status"]
        e_status = emb_results.get(rid, {}).get("status", "?")
        b_conf = bm25_results[rid]["confidence"]
        e_conf = emb_results.get(rid, {}).get("confidence", 0)

        if b_status == e_status:
            agree += 1
        else:
            b_match = b_status in ("covered", "weak")
            e_match = e_status in ("covered", "weak")
            if e_match and not b_match:
                emb_better += 1
            elif b_match and not e_match:
                bm25_better += 1
            diffs.append({
                "id": rid,
                "bm25_status": b_status, "bm25_conf": b_conf,
                "emb_status": e_status, "emb_conf": e_conf,
                "emb_evidence": emb_results.get(rid, {}).get("evidence", "")[:80],
            })

    return {"agree": agree, "emb_better": emb_better, "bm25_better": bm25_better,
            "diffs": diffs, "total": len(bm25_results)}


def main():
    ap = argparse.ArgumentParser(description="BM25 vs Embedding 集成对比")
    ap.add_argument("--model", default="zhipu-embedding-2",
                    help="zhipu-embedding-2 / zhipu-embedding-3")
    args = ap.parse_args()

    if not os.environ.get("ZHIPU_API_KEY"):
        print("[ERROR] ZHIPU_API_KEY 未设置", file=sys.stderr)
        sys.exit(1)

    pairs = load_pairs()
    print("=== 集成对比测试: BM25 vs %s ===" % args.model)
    print("测试对数: %d" % len(pairs))
    print()

    all_agree = 0
    all_emb_better = 0
    all_bm25_better = 0
    all_total = 0
    all_diffs = []
    t0 = time.time()

    for pair in pairs:
        print("[pair %s] resume=%s job=%s" % (
            pair["num"],
            os.path.basename(pair["resume"]),
            os.path.basename(pair["job"])))

        # BM25
        bm25_data = run_match(pair["resume"], pair["job"], "bm25")
        if bm25_data is None:
            print("  BM25 失败，跳过")
            continue

        # Embedding
        emb_data = run_match(pair["resume"], pair["job"], "embedding", args.model)
        if emb_data is None:
            print("  Embedding 失败，跳过")
            continue

        cmp = compare_results(bm25_data, emb_data)
        all_agree += cmp["agree"]
        all_emb_better += cmp["emb_better"]
        all_bm25_better += cmp["bm25_better"]
        all_total += cmp["total"]
        all_diffs.extend([(pair["num"], d) for d in cmp["diffs"]])

        print("  一致: %d/%d  embedding更优: %d  bm25更优: %d" % (
            cmp["agree"], cmp["total"], cmp["emb_better"], cmp["bm25_better"]))
        for d in cmp["diffs"]:
            print("    [diff] %s: bm25(%s,%.3f) -> emb(%s,%.3f)" % (
                d["id"], d["bm25_status"], d["bm25_conf"],
                d["emb_status"], d["emb_conf"]))

    elapsed = time.time() - t0
    print()
    print("=== 汇总 ===")
    print("总要求数: %d  耗时: %.1fs" % (all_total, elapsed))
    print("一致率: %.1f%% (%d/%d)" % (
        100 * all_agree / all_total if all_total else 0, all_agree, all_total))
    print("embedding 更优: %d 条 (BM25漏判→embedding纠正)" % all_emb_better)
    print("BM25 更优: %d 条 (embedding误判)" % all_bm25_better)
    print("净改进: %+d 条" % (all_emb_better - all_bm25_better))

    # 保存详细结果
    result_file = "tests/integration_compare_%s.json" % args.model.replace("-", "_")
    summary = {
        "model": args.model,
        "pairs": len(pairs),
        "total_requirements": all_total,
        "agree": all_agree,
        "emb_better": all_emb_better,
        "bm25_better": all_bm25_better,
        "elapsed_sec": round(elapsed, 1),
        "diffs": [{"pair": p, **d} for p, d in all_diffs],
    }
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("\n详细结果: %s" % result_file)


if __name__ == "__main__":
    main()
