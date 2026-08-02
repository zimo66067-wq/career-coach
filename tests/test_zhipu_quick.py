# -*- coding: utf-8 -*-
"""test_zhipu_quick.py · 智谱Embedding快速连通性+召回率测试"""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from zhipuai import ZhipuAI
import match_requirements as mr

API_KEY = "eb96db33a49942e39cca6ace6dff497b.1IjKi9E7D0Bv1c1x"
FIX = os.path.join(os.path.dirname(__file__), "fixtures-synthetic")

def load_text(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()

def load_requirements(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f).get("requirements", [])

def main():
    client = ZhipuAI(api_key=API_KEY)
    
    # 1. 连通性
    print("[1/3] 连通性测试...")
    t0 = time.time()
    resp = client.embeddings.create(model="embedding-2", input=["测试文本"])
    dim = len(resp.data[0].embedding)
    print(f"  ✓ 连通成功, 维度 = {dim}, 耗时={int((time.time()-t0)*1000)}ms")
    
    # 2. 单条召回率测试 (1简历 × 1JD)
    print("\n[2/3] 单条召回率测试 (1简历 × 1JD)...")
    resume_path = os.path.join(FIX, "resumes", "resume-01-swe.txt")
    job_path = os.path.join(FIX, "jobs", "job-01-swe.expected.json")
    
    resume_text = load_text(resume_path)
    cleaned, _ = __import__("deidentify").deidentify(resume_text)
    requirements = load_requirements(job_path)
    
    # 批量获取embedding
    all_texts = [cleaned] + [r["text"] for r in requirements]
    t0 = time.time()
    resp = client.embeddings.create(model="embedding-2", input=all_texts)
    embeddings = [item.embedding for item in resp.data]
    print(f"  批量embedding耗时: {int((time.time()-t0)*1000)}ms, 文本数={len(all_texts)}")
    
    resume_vec = embeddings[0]
    req_vectors = embeddings[1:]
    
    # 计算相似度
    def cos_sim(a, b):
        import math
        dot = sum(x*y for x,y in zip(a,b))
        na = math.sqrt(sum(x*x for x in a))
        nb = math.sqrt(sum(x*x for x in b))
        return dot / (na * nb) if na*nb > 0 else 0.0
    
    # 同时计算BM25作为对比
    sentences = mr.split_sentences(cleaned)
    sentences_tokens = [mr.tokenize(s) for s in sentences]
    sent_uni = [mr.unigrams(s) for s in sentences]
    doc_uni = mr.unigrams(cleaned)
    matcher = mr.Bm25Matcher()
    
    print(f"\n  逐条对比 (智谱Embedding vs BM25):")
    print(f"  {'ID':<6} {'Status':<10} {'Embed':<8} {'BM25':<8} {'Text[:40]'}")
    print("  " + "-" * 70)
    
    covered = weak = missing = 0
    bm25_covered = bm25_weak = bm25_missing = 0
    
    for i, req in enumerate(requirements):
        # Embedding
        sim = cos_sim(resume_vec, req_vectors[i])
        has_partial = bool(mr.unigrams(req["text"]) & doc_uni)
        status = mr.judge(sim, has_partial)
        if status == "covered": covered += 1
        elif status == "weak": weak += 1
        else: missing += 1
        
        # BM25
        conf, idx = matcher.best(req["text"], sentences_tokens, sent_uni=sent_uni, doc_uni=doc_uni)
        bm25_status = mr.judge(conf, has_partial)
        if bm25_status == "covered": bm25_covered += 1
        elif bm25_status == "weak": bm25_weak += 1
        else: bm25_missing += 1
        
        print(f"  {req['id']:<6} {status:<10} {sim:.3f}    {conf:.3f}    {req['text'][:40]}")
    
    total = len(requirements)
    embed_recall = (covered + weak) / total * 100
    bm25_recall = (bm25_covered + bm25_weak) / total * 100
    
    print(f"\n[3/3] 结果")
    print(f"  智谱Embedding: covered={covered}, weak={weak}, missing={missing}")
    print(f"  召回率: {embed_recall:.1f}%")
    print(f"\n  BM25基线: covered={bm25_covered}, weak={bm25_weak}, missing={bm25_missing}")
    print(f"  召回率: {bm25_recall:.1f}%")
    
    print(f"\n{'='*60}")
    if embed_recall >= 85:
        print(f"✓ 智谱Embedding达标: {embed_recall:.1f}% (目标≥85%)")
    else:
        print(f"✗ 智谱Embedding未达标: {embed_recall:.1f}% (目标≥85%)")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
