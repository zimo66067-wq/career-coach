# -*- coding: utf-8 -*-
"""test_zhipu_threshold.py · 智谱Embedding阈值校准与多样本召回率测试"""
import io
import json
import os
import sys
import time
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import match_requirements as mr
import deidentify

API_KEY = os.environ.get("ZHIPU_API_KEY", "")
FIX = os.path.join(os.path.dirname(__file__), "fixtures-synthetic")

def load_text(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()

def load_requirements(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f).get("requirements", [])

def cos_sim(a, b):
    dot = sum(x*y for x,y in zip(a,b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    return dot / (na * nb) if na*nb > 0 else 0.0

def main():
    if not API_KEY:
        print("缺少 ZHIPU_API_KEY；此手工外部联调未执行。")
        return 2
    from zhipuai import ZhipuAI

    client = ZhipuAI(api_key=API_KEY)
    
    resume_dir = os.path.join(FIX, "resumes")
    job_dir = os.path.join(FIX, "jobs")
    
    # 取所有简历和JD
    resumes = sorted([f for f in os.listdir(resume_dir) if f.endswith(".txt")])
    job_files = sorted([f for f in os.listdir(job_dir) if f.endswith(".expected.json")])
    
    print(f"简历数: {len(resumes)}, JD数: {len(job_files)}")
    print(f"预计总对比对: {len(resumes)} × {len(job_files)} = {len(resumes)*len(job_files)}")
    
    # 收集所有相似度分数
    all_scores = []  # (score, is_matched_pair)
    
    print("\n开始批量测试（每简历每JD各一次Embedding调用）...")
    
    for resume_file in resumes:
        resume_slug = resume_file.replace(".txt", "")
        resume_text = load_text(os.path.join(resume_dir, resume_file))
        cleaned, _ = deidentify.deidentify(resume_text)
        
        for job_file in job_files:
            job_slug = job_file.replace(".expected.json", "")
            requirements = load_requirements(os.path.join(job_dir, job_file))
            
            # 批量embedding：简历 + 所有要求
            all_texts = [cleaned] + [r["text"] for r in requirements]
            
            try:
                resp = client.embeddings.create(model="embedding-2", input=all_texts)
                embeddings = [item.embedding for item in resp.data]
            except Exception as e:
                print(f"  错误 {resume_slug}/{job_slug}: {e}")
                continue
            
            resume_vec = embeddings[0]
            req_vectors = embeddings[1:]
            
            is_matched = (resume_slug.replace("resume-", "").split("-")[0] == 
                         job_slug.replace("job-", "").split("-")[0])
            
            for i, req in enumerate(requirements):
                sim = cos_sim(resume_vec, req_vectors[i])
                all_scores.append((sim, is_matched, resume_slug, job_slug, req["id"], req["text"][:30]))
    
    # 分析分数分布
    matched_scores = [s[0] for s in all_scores if s[1]]
    unmatched_scores = [s[0] for s in all_scores if not s[1]]
    
    print(f"\n{'='*70}")
    print(f"分数分布分析 (共{len(all_scores)}条要求)")
    print(f"{'='*70}")
    
    def stats(arr, name):
        if not arr:
            return
        arr_sorted = sorted(arr)
        n = len(arr)
        print(f"\n{name} (n={n}):")
        print(f"  最小值: {min(arr):.4f}")
        print(f"  最大值: {max(arr):.4f}")
        print(f"  均值: {sum(arr)/n:.4f}")
        print(f"  中位数: {arr_sorted[n//2]:.4f}")
        print(f"  P25: {arr_sorted[int(n*0.25)]:.4f}")
        print(f"  P75: {arr_sorted[int(n*0.75)]:.4f}")
        print(f"  P90: {arr_sorted[int(n*0.90)]:.4f}")
    
    stats(matched_scores, "匹配对 (resume/JD同编号)")
    stats(unmatched_scores, "非匹配对 (resume/JD不同编号)")
    
    # 寻找最佳阈值
    print(f"\n{'='*70}")
    print("阈值扫描 (寻找F1最佳点)")
    print(f"{'='*70}")
    
    best_f1 = 0
    best_th = 0
    for th in [x * 0.02 for x in range(1, 50)]:
        tp = sum(1 for s, m, *_ in all_scores if m and s >= th)
        fp = sum(1 for s, m, *_ in all_scores if not m and s >= th)
        fn = sum(1 for s, m, *_ in all_scores if m and s < th)
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        if f1 > best_f1:
            best_f1 = f1
            best_th = th
    
    print(f"\n最佳阈值 (F1最高): th={best_th:.2f}, F1={best_f1:.3f}")
    
    # 用最佳阈值计算召回率
    # 区分：matched pair中多少被判定为covered/weak
    # 模拟judge函数：score>=th且has_partial->covered, score>=weak_th->weak
    
    # 需要重新计算has_partial...简化：假设所有都有partial
    # 只看matched pair的召回
    covered_matched = sum(1 for s, m, *_ in all_scores if m and s >= best_th)
    total_matched = len(matched_scores)
    recall_matched = covered_matched / total_matched * 100 if total_matched > 0 else 0
    
    print(f"\n匹配对召回率 (th={best_th:.2f}): {covered_matched}/{total_matched} = {recall_matched:.1f}%")
    
    # 同时测试不同阈值
    print(f"\n{'='*70}")
    print("不同阈值下的匹配对召回率")
    print(f"{'='*70}")
    for th in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55]:
        cov = sum(1 for s, m, *_ in all_scores if m and s >= th)
        rec = cov / total_matched * 100 if total_matched > 0 else 0
        print(f"  th={th:.2f}: {cov}/{total_matched} = {rec:.1f}%")
    
    # 展示top10低分匹配对
    print(f"\n{'='*70}")
    print("匹配对中分数最低的10条 (可能是阈值校准的关键)")
    print(f"{'='*70}")
    matched_items = [s for s in all_scores if s[1]]
    matched_items.sort(key=lambda x: x[0])
    for score, _, r, j, rid, text in matched_items[:10]:
        print(f"  {score:.4f} | {r} vs {j} | {rid} | {text}")
    
    # 保存结果
    out_path = os.path.join(os.path.dirname(__file__), "zhipu_threshold_analysis.json")
    with io.open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "backend": "zhipu",
            "model": "embedding-2",
            "dim": 1024,
            "total_comparisons": len(all_scores),
            "matched_pairs": len(matched_scores),
            "unmatched_pairs": len(unmatched_scores),
            "best_threshold": best_th,
            "best_f1": best_f1,
            "matched_recall_at_best": recall_matched,
            "matched_scores": matched_scores,
            "unmatched_scores": unmatched_scores,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out_path}")

if __name__ == "__main__":
    raise SystemExit(main())
