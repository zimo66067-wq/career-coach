# -*- coding: utf-8 -*-
"""test_embedding_recall.py · Embedding 召回率全量测试

支持多种后端:
  - zhipu:    智谱AI (免费2000万Token,推荐)
  - qianfan:  百度千帆
  - local:    本地 BGE 模型 (需 torch+transformers)
  - mock:     Mock Embedding (纯Python,用于框架验证)

用法:
  ZHIPU_API_KEY=xxx python test_embedding_recall.py --backend zhipu
  QIANFAN_AK=xxx QIANFAN_SK=yyy python test_embedding_recall.py --backend qianfan
  python test_embedding_recall.py --backend mock
"""
import argparse
import io
import json
import math
import os
import re
import sys
import time
from collections import Counter
from typing import List, Tuple

COVERED_TH = 0.55
WEAK_TH = 0.30


# ============== Embedding 后端抽象 ==============
class EmbeddingBackend:
    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class MockBackend(EmbeddingBackend):
    """Mock Embedding - 纯Python实现,用于框架验证和本地测试
    
    基于 TF-IDF 向量化,效果不如真实 Embedding,但零依赖、零成本。
    召回率通常比 BM25 略高(语义增强),但远低于真实 Embedding。
    """
    def __init__(self, dim: int = 256):
        self.dim = dim
        self.df = Counter()
        self.idf = {}
        self.vocab = {}
        self.vocab_size = 0
        self.N = 0  # 文档数
    
    RE_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*|[\u4e00-\u9fa5]")
    STOP = set("的了和是有在与我你他她它们这那也不都就及或着吧呢啊嘛么很还被把对于等以及一个我们你们他们".split())
    
    def _tokenize(self, text: str) -> List[str]:
        toks = self.RE_TOKEN.findall(text.lower())
        return [t for t in toks if len(t) > 1 and t not in self.STOP]
    
    def _build_vocab(self, texts: List[str]):
        """构建词表和IDF"""
        self.N = len(texts)
        for text in texts:
            tokens = set(self._tokenize(text))
            for t in tokens:
                self.df[t] += 1
        
        # 构建词表(取频率最高的dim个词)
        top_words = [w for w, _ in self.df.most_common(self.dim)]
        self.vocab = {w: i for i, w in enumerate(top_words)}
        self.vocab_size = len(top_words)
        
        # 计算IDF
        for w, df in self.df.items():
            if w in self.vocab:
                self.idf[w] = math.log((self.N + 1) / (df + 1)) + 1
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        if not self.vocab:
            self._build_vocab(texts)
        
        results = []
        for text in texts:
            tokens = self._tokenize(text)
            tf = Counter(tokens)
            vec = [0.0] * self.vocab_size
            for t, count in tf.items():
                if t in self.vocab:
                    idx = self.vocab[t]
                    vec[idx] = count * self.idf.get(t, 1.0)
            # L2归一化
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            results.append(vec)
        return results


class ZhipuBackend(EmbeddingBackend):
    """智谱AI Embedding - 免费2000万Token"""
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("ZHIPU_API_KEY", "")
        if not self.api_key:
            raise ValueError("请设置 ZHIPU_API_KEY 环境变量")
        self.model = "embedding-2"
        self.dim = 1024
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        from zhipuai import ZhipuAI
        client = ZhipuAI(api_key=self.api_key)
        resp = client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in resp.data]


class QianfanBackend(EmbeddingBackend):
    """百度千帆 Embedding"""
    def __init__(self, ak: str = "", sk: str = ""):
        self.ak = ak or os.environ.get("QIANFAN_AK", "")
        self.sk = sk or os.environ.get("QIANFAN_SK", "")
        if not self.ak or not self.sk:
            raise ValueError("请设置 QIANFAN_AK 和 QIANFAN_SK 环境变量")
        self.url = "https://qianfan.baidubce.com/v2/embeddings"
        self.model = "embedding-v1"
        self.dim = 384
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        import requests
        bearer = f"{self.ak}/{self.sk}"
        headers = {
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        }
        payload = {"input": texts, "model": self.model}
        resp = requests.post(self.url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"千帆API错误: {data['error']}")
        return [item["embedding"] for item in data["data"]]


class LocalBackend(EmbeddingBackend):
    """本地 BGE 模型 - 完全免费,需 torch + transformers"""
    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5"):
        try:
            import torch
            from transformers import AutoTokenizer, AutoModel
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModel.from_pretrained(model_name)
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model = self.model.to(self.device)
            self.dim = 1024
            print(f"本地模型加载成功: {model_name} ({self.device})")
        except ImportError:
            raise RuntimeError("缺少依赖: pip install torch transformers")
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        import torch
        encoded = self.tokenizer(texts, padding=True, truncation=True, 
                                max_length=512, return_tensors="pt")
        encoded = {k: v.to(self.device) for k, v in encoded.items()}
        with torch.no_grad():
            model_output = self.model(**encoded)
        embeddings = model_output.last_hidden_state[:, 0]
        embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
        return embeddings.cpu().numpy().tolist()


# ============== 工具函数 ==============
def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def load_text(path: str) -> str:
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def load_requirements(path: str) -> List[dict]:
    with io.open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["requirements"]


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"[\n。；;！？!?]", text)
    return [p.strip() for p in parts if len(p.strip()) >= 4]


# ============== 主测试 ==============
def run_recall_test(backend: EmbeddingBackend, resume_dir: str, job_dir: str,
                   resume_slugs: List[str], job_slugs: List[str]) -> dict:
    total_reqs = 0
    hit_reqs = 0
    details = []
    
    for rslug in resume_slugs:
        resume_text = load_text(os.path.join(resume_dir, rslug + ".txt"))
        resume_sents = split_sentences(resume_text)
        
        for jslug in job_slugs:
            reqs = load_requirements(os.path.join(job_dir, jslug + ".expected.json"))
            
            # 批量 embedding: 所有要求 + 所有句子
            all_texts = [r["text"] for r in reqs] + resume_sents[:15]
            try:
                vecs = backend.embed(all_texts)
                req_vecs = vecs[:len(reqs)]
                sent_vecs = vecs[len(reqs):]
                
                for idx, req in enumerate(reqs):
                    total_reqs += 1
                    best_conf = 0.0
                    for sv in sent_vecs:
                        conf = cosine_similarity(req_vecs[idx], sv)
                        if conf > best_conf:
                            best_conf = conf
                    
                    status = "covered" if best_conf >= COVERED_TH else (
                        "weak" if best_conf >= WEAK_TH else "missing"
                    )
                    if status in ("covered", "weak"):
                        hit_reqs += 1
                    
                    details.append({
                        "resume": rslug, "job": jslug, "req": req["id"],
                        "status": status, "confidence": round(best_conf, 3)
                    })
            except Exception as e:
                print(f"  ! API 异常 ({rslug} × {jslug}): {e}")
                # 对该JD的所有要求标记为错误
                for req in reqs:
                    total_reqs += 1
                    details.append({
                        "resume": rslug, "job": jslug, "req": req["id"],
                        "status": "error", "confidence": 0.0, "error": str(e)
                    })
            
            # 频率限制保护
            time.sleep(0.5)
    
    recall = hit_reqs / total_reqs if total_reqs else 0
    return {
        "total_requirements": total_reqs,
        "hit_requirements": hit_reqs,
        "recall_rate": round(recall, 4),
        "details": details,
    }


def main():
    parser = argparse.ArgumentParser(description="Embedding 召回率测试")
    parser.add_argument("--backend", choices=["zhipu", "qianfan", "local", "mock"],
                       default="mock", help="Embedding 后端")
    parser.add_argument("--api-key", help="API Key (智谱)")
    parser.add_argument("--ak", help="Access Key (千帆)")
    parser.add_argument("--sk", help="Secret Key (千帆)")
    parser.add_argument("--samples", type=int, default=5,
                       help="抽样简历数量 (默认5,全量=20)")
    args = parser.parse_args()
    
    # 初始化后端
    if args.backend == "zhipu":
        backend = ZhipuBackend(args.api_key)
        print(f"后端: 智谱AI (模型: {backend.model}, 维度: {backend.dim})")
    elif args.backend == "qianfan":
        backend = QianfanBackend(args.ak, args.sk)
        print(f"后端: 百度千帆 (模型: {backend.model}, 维度: {backend.dim})")
    elif args.backend == "local":
        backend = LocalBackend()
        print(f"后端: 本地模型 (维度: {backend.dim})")
    else:
        backend = MockBackend(dim=256)
        print(f"后端: Mock Embedding (维度: {backend.dim}, 纯Python零依赖)")
        print("  注意: Mock效果远低于真实Embedding,仅用于框架验证")
    
    # 连通性测试
    print("\n[1/3] 连通性测试...")
    try:
        test_vec = backend.embed(["测试文本"])
        print(f"  ✓ 连通成功, 维度 = {len(test_vec[0])}")
    except Exception as e:
        print(f"  ✗ 连通失败: {e}")
        sys.exit(1)
    
    # 召回率测试
    print(f"\n[2/3] 召回率测试 (抽样 {args.samples} 简历 × 10 JD)...")
    FIX = os.path.join(os.path.dirname(__file__), "fixtures-synthetic")
    resume_dir = os.path.join(FIX, "resumes")
    job_dir = os.path.join(FIX, "jobs")
    
    all_resumes = sorted([f.replace(".txt", "") for f in os.listdir(resume_dir) if f.endswith(".txt")])
    all_jobs = sorted([f.replace(".expected.json", "") for f in os.listdir(job_dir) if f.endswith(".expected.json")])
    
    resume_slugs = all_resumes[:args.samples]
    job_slugs = all_jobs
    
    print(f"  简历: {resume_slugs}")
    print(f"  JD: {job_slugs}")
    
    # Mock Backend 预构建词表(基于所有文本)
    if isinstance(backend, MockBackend):
        print("  [Mock] 预构建全局词表...")
        all_texts = []
        for rslug in resume_slugs:
            resume_text = load_text(os.path.join(resume_dir, rslug + ".txt"))
            all_texts.extend(split_sentences(resume_text))
        for jslug in job_slugs:
            reqs = load_requirements(os.path.join(job_dir, jslug + ".expected.json"))
            all_texts.extend([r["text"] for r in reqs])
        backend.embed(all_texts)  # 预构建词表
        print(f"  [Mock] 词表大小: {backend.vocab_size}")
    
    result = run_recall_test(backend, resume_dir, job_dir, resume_slugs, job_slugs)
    
    # 输出结果
    print(f"\n[3/3] 结果")
    print(f"  总要求数: {result['total_requirements']}")
    print(f"  命中数(covered+weak): {result['hit_requirements']}")
    print(f"  召回率: {result['recall_rate']*100:.1f}%")
    
    # 按简历维度
    print("\n  按简历维度:")
    for rslug in resume_slugs:
        r_data = [d for d in result["details"] if d["resume"] == rslug and d["status"] != "error"]
        r_hit = sum(1 for d in r_data if d["status"] in ("covered", "weak"))
        r_total = len(r_data)
        if r_total > 0:
            print(f"    {rslug}: {r_hit}/{r_total} = {r_hit/r_total*100:.1f}%")
    
    # 按JD维度
    print("\n  按JD维度:")
    for jslug in job_slugs:
        j_data = [d for d in result["details"] if d["job"] == jslug and d["status"] != "error"]
        j_hit = sum(1 for d in j_data if d["status"] in ("covered", "weak"))
        j_total = len(j_data)
        if j_total > 0:
            print(f"    {jslug}: {j_hit}/{j_total} = {j_hit/j_total*100:.1f}%")
    
    # 保存结果
    out_path = os.path.join(os.path.dirname(__file__), 
                           f"embedding_recall_{args.backend}_{args.samples}samples.json")
    with io.open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "backend": args.backend,
            "model": getattr(backend, "model", "mock"),
            "dim": getattr(backend, "dim", 0),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            **result,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存: {out_path}")
    
    # 结论
    print("\n" + "=" * 60)
    if args.backend == "mock":
        print(f"Mock 召回率: {result['recall_rate']*100:.1f}% (仅框架验证)")
        print("  真实 Embedding 预计召回率: 80-95%")
    elif result["recall_rate"] >= 0.85:
        print(f"✓ 召回率达标: {result['recall_rate']*100:.1f}% (目标≥85%)")
    else:
        print(f"✗ 召回率未达标: {result['recall_rate']*100:.1f}% (目标≥85%)")
    print("=" * 60)


if __name__ == "__main__":
    main()
