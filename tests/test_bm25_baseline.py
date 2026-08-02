# -*- coding: utf-8 -*-
"""test_bm25_baseline.py · BM25 召回率基线测试

纯本地运行，无需 API Key。
覆盖 5 简历 × 5 JD = 25 对组合，统计 covered+weak 比例。
"""
import io
import json
import os
import sys

# 把 tools 加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import match_requirements as mr

FIX = os.path.join(os.path.dirname(__file__), "fixtures-synthetic")

COVERED_TH = 0.55
WEAK_TH = 0.30


def load_text(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def load_requirements(path):
    with io.open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["requirements"]


# 抽样 5 简历 × 5 JD
resume_slugs = ["resume-01-swe", "resume-05-fresh", "resume-10-devops", "resume-15-bigdata", "resume-20-fresh-general"]
job_slugs = ["job-01-swe", "job-02-fe", "job-07-pm", "job-09-algo", "job-10-bigdata"]

print("=" * 60)
print("BM25 召回率基线测试 (5×5 抽样)")
print("=" * 60)

total_reqs = 0
hit_reqs = 0
details = []

for rslug in resume_slugs:
    resume_text = load_text(os.path.join(FIX, "resumes", rslug + ".txt"))
    sentences = mr.split_sentences(resume_text)
    sentences_tokens = [mr.tokenize(s) for s in sentences]
    sent_uni = [mr.unigrams(s) for s in sentences]
    doc_uni = mr.unigrams(resume_text)
    matcher = mr.Bm25Matcher()

    for jslug in job_slugs:
        reqs = load_requirements(os.path.join(FIX, "jobs", jslug + ".expected.json"))
        for req in reqs:
            total_reqs += 1
            conf, best_idx = matcher.best(req["text"], sentences_tokens, sent_uni=sent_uni, doc_uni=doc_uni)
            req_tokens = mr.unigrams(req["text"])
            has_partial = bool(req_tokens & doc_uni)
            status = mr.judge(conf, has_partial)
            if status in ("covered", "weak"):
                hit_reqs += 1
            details.append({
                "resume": rslug, "job": jslug, "req": req["id"],
                "status": status, "confidence": round(conf, 3)
            })

recall = hit_reqs / total_reqs if total_reqs else 0
print("\n结果：")
print("  总要求数: %d" % total_reqs)
print("  命中数(covered+weak): %d" % hit_reqs)
print("  召回率: %.1f%%" % (recall * 100))

# 按简历维度统计
print("\n按简历维度召回率：")
for rslug in resume_slugs:
    r_data = [d for d in details if d["resume"] == rslug]
    r_hit = sum(1 for d in r_data if d["status"] in ("covered", "weak"))
    print("  %s: %d/%d = %.1f%%" % (rslug, r_hit, len(r_data), r_hit / len(r_data) * 100))

# 按 JD 维度统计
print("\n按 JD 维度召回率：")
for jslug in job_slugs:
    j_data = [d for d in details if d["job"] == jslug]
    j_hit = sum(1 for d in j_data if d["status"] in ("covered", "weak"))
    print("  %s: %d/%d = %.1f%%" % (jslug, j_hit, len(j_data), j_hit / len(j_data) * 100))

# 按状态分布
print("\n状态分布：")
from collections import Counter
status_counts = Counter(d["status"] for d in details)
for s, c in status_counts.most_common():
    print("  %s: %d (%.1f%%)" % (s, c, c / total_reqs * 100))

print("\n" + "=" * 60)
print("BM25 基线召回率: %.1f%%" % (recall * 100))
print("目标对比: 千帆 Embedding 目标 ≥85%%")
print("=" * 60)
