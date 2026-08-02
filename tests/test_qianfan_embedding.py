# -*- coding: utf-8 -*-
"""test_qianfan_embedding.py · 千帆 Embedding 连通性 + 召回率验证

用法:
  QIANFAN_AK=xxx QIANFAN_SK=yyy python test_qianfan_embedding.py

输出:
  - 连通性: 单条 embedding 调用
  - 召回率: 抽样 5 简历 × 5 JD，统计 covered+weak / total 比例
"""
import io
import json
import math
import os
import sys
import time

# ---- 环境变量读取 ----
# 注意：千帆应用 API Key 与智能云 IAM Access Key 不同！
# 请从千帆控制台「应用管理」中获取，而非 IAM 安全认证。
AK = os.environ.get("QIANFAN_AK", "")
SK = os.environ.get("QIANFAN_SK", "")
if not AK or not SK:
    print("错误: 请设置环境变量 QIANFAN_AK 和 QIANFAN_SK")
    sys.exit(2)

COVERED_TH = 0.55
WEAK_TH = 0.30


def embed(texts, model="embedding-v1"):
    import requests
    # 千帆 Bearer token: bce-v3/ALTAK-xxx/yyy
    bearer = AK + "/" + SK
    
    headers = {
        "Authorization": "Bearer " + bearer,
        "Content-Type": "application/json",
    }
    payload = {"input": texts, "model": model}
    
    # 千帆 v2 endpoint
    url = "https://qianfan.baidubce.com/v2/embeddings"
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    
    if "error" in data:
        raise RuntimeError("千帆错误: %s" % data.get("error", {}).get("message", str(data)))
    
    # 返回格式: {"data": [{"embedding": [...], "index": 0}, ...]}
    return [item["embedding"] for item in data.get("data", [])]


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def load_text(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def load_requirements(path):
    with io.open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["requirements"]


# ---- 主流程 ----
print("=" * 60)
print("千帆 Embedding API 连通性测试")
print("=" * 60)

# 1. 连通性
print("\n[1/2] 发送 embedding 请求 ...")
try:
    vec = embed(["测试文本"])
    print("  ✓ Embedding 返回成功，维度 = %d" % len(vec[0]))
except Exception as e:
    print("  ✗ Embedding 调用失败:", e)
    sys.exit(1)

# 2. 召回率验证（抽样）
print("\n[2/2] 召回率验证（抽样 5 简历 × 5 JD）...")
BASE = os.path.join(os.path.dirname(__file__), "fixtures-synthetic")

resume_slugs = ["resume-01-swe", "resume-05-fresh", "resume-10-devops", "resume-15-bigdata", "resume-20-fresh-general"]
job_slugs = ["job-01-swe", "job-02-fe", "job-07-pm", "job-09-algo", "job-10-bigdata"]

total_reqs = 0
hit_reqs = 0
results_detail = []

for rslug in resume_slugs:
    resume_text = load_text(os.path.join(BASE, "resumes", rslug + ".txt"))
    resume_sents = [s.strip() for s in resume_text.splitlines() if len(s.strip()) >= 4]

    for jslug in job_slugs:
        reqs = load_requirements(os.path.join(BASE, "jobs", jslug + ".expected.json"))
        # 批量：把该JD的所有要求和简历句子合并到一个请求中
        all_texts = [r["text"] for r in reqs] + resume_sents[:10]
        try:
            vecs = embed(all_texts)
            req_vecs = vecs[:len(reqs)]
            sent_vecs = vecs[len(reqs):]
            for idx, req in enumerate(reqs):
                total_reqs += 1
                best_conf = 0.0
                for sv in sent_vecs:
                    conf = cosine_similarity(req_vecs[idx], sv)
                    if conf > best_conf:
                        best_conf = conf
                status = "covered" if best_conf >= COVERED_TH else ("weak" if best_conf >= WEAK_TH else "missing")
                if status in ("covered", "weak"):
                    hit_reqs += 1
                results_detail.append({
                    "resume": rslug, "job": jslug, "req": req["id"],
                    "status": status, "confidence": round(best_conf, 3)
                })
        except Exception as e:
            print("  ! API 异常 (%s × %s): %s" % (rslug, jslug, e))
        # 每对简历×JD 之间间隔 2 秒，避免触发频率限制
        time.sleep(2)

recall = hit_reqs / total_reqs if total_reqs else 0
print("  总要求数: %d" % total_reqs)
print("  命中数(covered+weak): %d" % hit_reqs)
print("  召回率: %.1f%%" % (recall * 100))

# 3. 输出摘要
print("\n" + "=" * 60)
print("结果摘要")
print("=" * 60)
print("API 连通性: 通过")
print("Embedding 维度: %d" % len(vec[0]))
print("抽样召回率: %.1f%% (%s)" % (recall * 100, "达标" if recall >= 0.85 else "未达标(目标≥85%)"))

# 输出详细结果到文件（供人工复核）
out_path = os.path.join(os.path.dirname(__file__), "qianfan_embedding_test_result.json")
with io.open(out_path, "w", encoding="utf-8") as f:
    json.dump({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "api_status": "ok",
        "embedding_dim": len(vec[0]),
        "recall_rate": round(recall, 4),
        "total_requirements": total_reqs,
        "hit_requirements": hit_reqs,
        "thresholds": {"covered": COVERED_TH, "weak": WEAK_TH},
        "samples": resume_slugs,
        "jobs": job_slugs,
        "details": results_detail,
    }, f, ensure_ascii=False, indent=2)
print("\n详细结果已写入: %s" % out_path)
print("\n如需全量 20×10 验证，请将脚本中的 resume_slugs / job_slugs 扩展为完整列表。")
