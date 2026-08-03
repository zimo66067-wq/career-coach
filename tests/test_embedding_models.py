# -*- coding: utf-8 -*-
"""test_embedding_models.py · 多模型Embedding召回率对比测试

支持模型:
  - zhipu-embedding-2: 智谱1024维
  - zhipu-embedding-3: 智谱2048维
  - sentence-level: 句子级匹配策略

用法:
  python tests/test_embedding_models.py --model zhipu-embedding-2
  python tests/test_embedding_models.py --model zhipu-embedding-3
  python tests/test_embedding_models.py --model zhipu-embedding-3 --strategy sentence
"""
import argparse
import io
import json
import os
import sys
import time
import math
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

try:
    from zhipuai import ZhipuAI
except ImportError:
    import pytest
    pytest.skip("zhipuai 包未安装，跳过智谱在线测试", allow_module_level=True)
import match_requirements as mr
import deidentify

API_KEY = os.environ.get("ZHIPUAI_API_KEY", "")
if not API_KEY:
    import pytest
    pytest.skip("未设置 ZHIPUAI_API_KEY，跳过智谱在线测试", allow_module_level=True)
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

def split_sentences(text):
    parts = mr.split_sentences(text)
    return [p.strip() for p in parts if len(p.strip()) >= 8]

class EmbeddingTester:
    def __init__(self, model_name, strategy="document"):
        self.client = ZhipuAI(api_key=API_KEY)
        # 映射: zhipu-embedding-2 -> embedding-2
        self.model = model_name.replace("zhipu-", "")
        self.strategy = strategy  # "document" or "sentence"
        self.dim = 1024 if "embedding-2" in model_name else 2048
        
    def embed(self, texts):
        """批量获取embedding，自动分批"""
        all_embeddings = []
        batch_size = 16  # 智谱API批量限制
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            resp = self.client.embeddings.create(model=self.model, input=batch)
            all_embeddings.extend([item.embedding for item in resp.data])
        return all_embeddings
    
    def test_document_level(self, resume_text, requirements):
        """文档级匹配：整篇简历 vs 每条JD要求"""
        all_texts = [resume_text] + [r["text"] for r in requirements]
        embeddings = self.embed(all_texts)
        resume_vec = embeddings[0]
        results = []
        for i, req in enumerate(requirements):
            sim = cos_sim(resume_vec, embeddings[i+1])
            results.append((req["id"], sim, req["text"]))
        return results
    
    def test_sentence_level(self, resume_text, requirements):
        """句子级匹配：每条JD要求 vs 简历最佳句子"""
        sentences = split_sentences(resume_text)
        if not sentences:
            return [(r["id"], 0.0, r["text"]) for r in requirements]
        
        # 嵌入所有句子和所有JD要求
        all_texts = sentences + [r["text"] for r in requirements]
        embeddings = self.embed(all_texts)
        sentence_vecs = embeddings[:len(sentences)]
        req_vecs = embeddings[len(sentences):]
        
        results = []
        for i, req in enumerate(requirements):
            # 找与JD要求相似度最高的简历句子
            best_sim = max(cos_sim(sentence_vecs[j], req_vecs[i]) 
                          for j in range(len(sentences)))
            results.append((req["id"], best_sim, req["text"]))
        return results
    
    def run_test(self, resume_dir, job_dir, resume_files, job_files):
        """运行完整测试"""
        all_scores = []
        
        for resume_file in resume_files:
            resume_slug = resume_file.replace(".txt", "")
            resume_text = load_text(os.path.join(resume_dir, resume_file))
            cleaned, _ = deidentify.deidentify(resume_text)
            
            for job_file in job_files:
                job_slug = job_file.replace(".expected.json", "")
                requirements = load_requirements(os.path.join(job_dir, job_file))
                
                is_matched = (resume_slug.replace("resume-", "").split("-")[0] == 
                             job_slug.replace("job-", "").split("-")[0])
                
                if self.strategy == "sentence":
                    results = self.test_sentence_level(cleaned, requirements)
                else:
                    results = self.test_document_level(cleaned, requirements)
                
                for rid, sim, text in results:
                    all_scores.append((sim, is_matched, resume_slug, job_slug, rid, text[:30]))
        
        return all_scores

def analyze_results(all_scores, model_name, strategy):
    """分析结果并输出报告"""
    matched_scores = [s[0] for s in all_scores if s[1]]
    unmatched_scores = [s[0] for s in all_scores if not s[1]]
    total_matched = len(matched_scores)
    
    print(f"\n{'='*70}")
    print(f"模型: {model_name} | 策略: {strategy}")
    print(f"{'='*70}")
    
    # 分数分布
    def stats(arr, name):
        if not arr:
            return
        arr_sorted = sorted(arr)
        n = len(arr)
        print(f"\n{name} (n={n}):")
        print(f"  最小值: {min(arr):.4f} | 最大值: {max(arr):.4f}")
        print(f"  均值: {sum(arr)/n:.4f} | 中位数: {arr_sorted[n//2]:.4f}")
        print(f"  P25: {arr_sorted[int(n*0.25)]:.4f} | P75: {arr_sorted[int(n*0.75)]:.4f}")
    
    stats(matched_scores, "匹配对")
    stats(unmatched_scores, "非匹配对")
    
    # 阈值扫描
    print(f"\n{'='*70}")
    print("不同阈值下的匹配对召回率")
    print(f"{'='*70}")
    best_recall = 0
    best_th = 0
    for th in [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]:
        cov = sum(1 for s, m, *_ in all_scores if m and s >= th)
        rec = cov / total_matched * 100 if total_matched > 0 else 0
        if rec > best_recall:
            best_recall = rec
            best_th = th
        print(f"  th={th:.2f}: {cov}/{total_matched} = {rec:.1f}%")
    
    print(f"\n最佳召回率: th={best_th:.2f} -> {best_recall:.1f}%")
    
    # 对比BM25
    print(f"\n{'='*70}")
    print("与BM25基线对比")
    print(f"{'='*70}")
    print(f"  Embedding最佳召回: {best_recall:.1f}% (th={best_th:.2f})")
    print(f"  BM25基线召回: 66.4% (COV+WEAK) / 100% (仅COV)")
    
    return best_th, best_recall

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="zhipu-embedding-2", 
                       choices=["zhipu-embedding-2", "zhipu-embedding-3"])
    parser.add_argument("--strategy", default="document",
                       choices=["document", "sentence"])
    parser.add_argument("--samples", type=int, default=5,
                       help="测试的简历样本数 (默认5)")
    args = parser.parse_args()
    
    resume_dir = os.path.join(FIX, "resumes")
    job_dir = os.path.join(FIX, "jobs")
    
    resumes = sorted([f for f in os.listdir(resume_dir) if f.endswith(".txt")])[:args.samples]
    jobs = sorted([f for f in os.listdir(job_dir) if f.endswith(".expected.json")])
    
    print(f"测试配置:")
    print(f"  模型: {args.model}")
    print(f"  策略: {args.strategy}")
    print(f"  简历: {len(resumes)}份, JD: {len(jobs)}份")
    print(f"  预计对比: {len(resumes)} × {len(jobs)} = {len(resumes)*len(jobs)}对")
    
    tester = EmbeddingTester(args.model, args.strategy)
    
    # 连通性测试
    print("\n[连通性测试]...")
    t0 = time.time()
    tester.embed(["测试文本"])
    print(f"  ✓ 连通成功, 耗时={int((time.time()-t0)*1000)}ms")
    
    # 运行测试
    print(f"\n[召回率测试]...")
    t0 = time.time()
    all_scores = tester.run_test(resume_dir, job_dir, resumes, jobs)
    elapsed = int((time.time()-t0)*1000)
    print(f"  完成, {len(all_scores)}条要求, 耗时={elapsed}ms")
    
    # 分析
    best_th, best_recall = analyze_results(all_scores, args.model, args.strategy)
    
    # 保存结果
    out = {
        "model": args.model,
        "strategy": args.strategy,
        "total_comparisons": len(all_scores),
        "best_threshold": best_th,
        "best_recall": best_recall,
        "elapsed_ms": elapsed,
    }
    out_path = os.path.join(os.path.dirname(__file__), 
                           f"embedding_model_{args.model.replace('-','_')}_{args.strategy}.json")
    with io.open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out_path}")

if __name__ == "__main__":
    main()
