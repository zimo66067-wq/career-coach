#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""test_embedding_comprehensive.py · Embedding 多模型召回率综合测试

支持后端:
  - zhipu-2:    智谱 embedding-2 (1024维, 免费)
  - zhipu-3:    智谱 embedding-3 (2048维, 免费)
  - bge-local:  本地 BGE 模型 (sentence-transformers, 完全免费)
  - bge-m3:     BGE-m3 (多语言, 完全免费)
  - jina:       Jina Embedding (免费 100万Token/月)
  - mock:       Mock (框架验证)

精确阈值扫描:
  对 [0.10, 0.50] 区间以 0.01 步长扫描，输出精确召回率/Precision/F1 曲线。

用法:
  python tests/test_embedding_comprehensive.py --backend zhipu-2
  python tests/test_embedding_comprehensive.py --backend bge-local
  python tests/test_embedding_comprehensive.py --backend bge-m3
  python tests/test_embedding_comprehensive.py --backend jina
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
from typing import List, Tuple, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import match_requirements as mr
import deidentify

# ---------- 后端抽象 ----------

class Backend:
    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class MockBackend(Backend):
    def __init__(self, dim=256):
        self.dim = dim
        self._vocab = {}
        self._idf = {}
        self._N = 0
        self._built = False

    RE_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*|[\u4e00-\u9fa5]")
    STOP = set("的了和是有在与我你他她它们这那也不都就及或着吧呢啊嘛么很还被把对于等以及一个我们你们他们".split())

    def _tokenize(self, text):
        toks = self.RE_TOKEN.findall(text.lower())
        return [t for t in toks if len(t) > 1 and t not in self.STOP]

    def embed(self, texts):
        if not self._built:
            self._N = len(texts)
            dfs = Counter()
            all_toks = []
            for t in texts:
                toks = self._tokenize(t)
                all_toks.append(toks)
                for tok in set(toks):
                    dfs[tok] += 1
            top = [w for w, _ in dfs.most_common(self.dim)]
            self._vocab = {w: i for i, w in enumerate(top)}
            for w, df in dfs.items():
                if w in self._vocab:
                    self._idf[w] = math.log((self._N + 1) / (df + 1)) + 1
            self._built = True
            self._cache_toks = all_toks

        results = []
        for text in texts:
            toks = self._tokenize(text)
            tf = Counter(toks)
            vec = [0.0] * len(self._vocab)
            for t, c in tf.items():
                if t in self._vocab:
                    vec[self._vocab[t]] = c * self._idf.get(t, 1.0)
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            results.append(vec)
        return results


class ZhipuBackend(Backend):
    def __init__(self, model="embedding-2"):
        from zhipuai import ZhipuAI
        key = os.environ.get("ZHIPU_API_KEY", "")
        if not key:
            raise RuntimeError("ZHIPU_API_KEY 未设置")
        self.client = ZhipuAI(api_key=key)
        self.model = model
        self.dim = 1024 if "2" in model else 2048

    def embed(self, texts):
        all_emb = []
        batch = 16
        for i in range(0, len(texts), batch):
            b = texts[i:i + batch]
            resp = self.client.embeddings.create(model=self.model, input=b)
            all_emb.extend([item.embedding for item in resp.data])
        return all_emb


class BgeLocalBackend(Backend):
    """本地 BGE 模型 (sentence-transformers)。完全免费，零 API 调用。"""
    def __init__(self, model_name="BAAI/bge-large-zh-v1.5"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError("请先安装: pip install sentence-transformers")
        print(f"[BGE] 正在加载模型 {model_name} ...")
        t0 = time.time()
        self.model = SentenceTransformer(model_name)
        self.device = str(self.model.device)
        self.dim = self.model.get_sentence_embedding_dimension()
        print(f"[BGE] 加载完成 ({self.device}), 维度={self.dim}, 耗时={time.time()-t0:.1f}s")

    def embed(self, texts):
        return self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()


class BgeM3Backend(Backend):
    """BGE-m3 多语言模型。"""
    def __init__(self):
        BgeLocalBackend.__init__(self, model_name="BAAI/bge-m3")


class JinaBackend(Backend):
    """Jina Embedding (免费 100万 Token/月)。"""
    def __init__(self):
        self.key = os.environ.get("JINA_API_KEY", "")
        if not self.key:
            raise RuntimeError("JINA_API_KEY 未设置 (https://jina.ai/embeddings/)")
        self.url = "https://api.jina.ai/v1/embeddings"
        self.dim = 768

    def embed(self, texts):
        import requests
        payload = {"model": "jina-embeddings-v3", "input": texts}
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        resp = requests.post(self.url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if "data" not in data:
            raise RuntimeError(f"Jina API 错误: {data}")
        # 按 index 排序
        return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]


# ---------- 工具函数 ----------

def cos_sim(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na * nb > 0 else 0.0


def load_text(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def load_requirements(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f).get("requirements", [])


def split_sentences(text):
    parts = mr.split_sentences(text)
    return [p.strip() for p in parts if len(p.strip()) >= 8]


# ---------- 核心测试 ----------

def run_sentence_test(backend: Backend, resume_dir, job_dir, resume_files, job_files) -> List[Tuple]:
    """句子级匹配测试。返回 [(sim, is_matched, resume_slug, job_slug, req_id, req_text)]。"""
    results = []
    for rfile in resume_files:
        rslug = rfile.replace(".txt", "")
        resume_text = load_text(os.path.join(resume_dir, rfile))
        cleaned, _ = deidentify.deidentify(resume_text)
        sentences = split_sentences(cleaned)

        for jfile in job_files:
            jslug = jfile.replace(".expected.json", "")
            reqs = load_requirements(os.path.join(job_dir, jfile))
            is_matched = (rslug.split("-")[1] == jslug.split("-")[1])

            # 批量 embed：句子 + 所有要求
            all_texts = sentences + [r["text"] for r in reqs]
            all_vecs = backend.embed(all_texts)
            sent_vecs = all_vecs[:len(sentences)]
            req_vecs = all_vecs[len(sentences):]

            for ri, req in enumerate(reqs):
                best_sim = max(cos_sim(sent_vecs[j], req_vecs[ri]) for j in range(len(sentences))) if sentences else 0.0
                results.append((best_sim, is_matched, rslug, jslug, req["id"], req["text"][:40]))

    return results


def analyze(results: List[Tuple], backend_name: str) -> Dict:
    """阈值扫描 + 统计报告。"""
    matched = [r[0] for r in results if r[1]]
    unmatched = [r[0] for r in results if not r[1]]
    total_matched = len(matched)
    total_unmatched = len(unmatched)

    def stats(arr, name):
        if not arr:
            return
        arr_s = sorted(arr)
        n = len(arr)
        mean = sum(arr) / n
        print(f"\n{name} (n={n}):")
        print(f"  min={min(arr):.4f} max={max(arr):.4f} mean={mean:.4f} median={arr_s[n//2]:.4f}")
        print(f"  P25={arr_s[int(n*0.25)]:.4f} P75={arr_s[int(n*0.75)]:.4f}")

    stats(matched, "匹配对")
    stats(unmatched, "非匹配对")

    # 阈值扫描 0.10 ~ 0.50, 步长 0.01
    print(f"\n{'='*70}")
    print("阈值扫描 (召回率 / 精确率 / F1)")
    print(f"{'='*70}")
    best = {"f1": 0, "th": 0, "recall": 0, "precision": 0}
    for th in [round(x * 0.01, 2) for x in range(10, 51)]:
        tp = sum(1 for s, m, *_ in results if m and s >= th)
        fp = sum(1 for s, m, *_ in results if not m and s >= th)
        fn = total_matched - tp
        recall = tp / total_matched * 100 if total_matched else 0
        precision = tp / (tp + fp) * 100 if (tp + fp) else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0
        if f1 > best["f1"]:
            best = {"f1": round(f1, 2), "th": th, "recall": round(recall, 2), "precision": round(precision, 2)}
        # 只打印关键阈值和 >90% 的
        if th in [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50] or recall >= 90:
            print(f"  th={th:.2f}: recall={recall:.1f}% precision={precision:.1f}% f1={f1:.1f}%")

    print(f"\n最佳 F1: th={best['th']:.2f} -> recall={best['recall']:.1f}% precision={best['precision']:.1f}% f1={best['f1']:.1f}%")

    # 检查 >= 90% 召回率的阈值
    over90 = [(round(x * 0.01, 2),) for x in range(10, 51)]
    over90 = []
    for th in [round(x * 0.01, 2) for x in range(10, 51)]:
        tp = sum(1 for s, m, *_ in results if m and s >= th)
        recall = tp / total_matched * 100 if total_matched else 0
        if recall >= 90:
            over90.append((th, recall))
    if over90:
        print(f"  >=90% 召回率的阈值范围: {over90[0][0]:.2f} ~ {over90[-1][0]:.2f}")
    else:
        print(f"  警告: 无任何阈值能达到 >=90% 召回率")

    return {
        "backend": backend_name,
        "total": len(results),
        "matched": total_matched,
        "unmatched": total_unmatched,
        "matched_mean": round(sum(matched)/len(matched), 4) if matched else 0,
        "unmatched_mean": round(sum(unmatched)/len(unmatched), 4) if unmatched else 0,
        "best": best,
        "over90_thresholds": over90,
    }


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser(description="Embedding 综合召回率测试")
    ap.add_argument("--backend", choices=["zhipu-2", "zhipu-3", "bge-local", "bge-m3", "jina", "mock"],
                    default="mock", help="Embedding 后端")
    ap.add_argument("--samples", type=int, default=5, help="简历样本数 (默认5)")
    ap.add_argument("--output", default=None, help="结果 JSON 文件")
    args = ap.parse_args()

    # 初始化后端
    t0 = time.time()
    if args.backend == "zhipu-2":
        backend = ZhipuBackend("embedding-2")
    elif args.backend == "zhipu-3":
        backend = ZhipuBackend("embedding-3")
    elif args.backend == "bge-local":
        backend = BgeLocalBackend("BAAI/bge-large-zh-v1.5")
    elif args.backend == "bge-m3":
        backend = BgeLocalBackend("BAAI/bge-m3")
    elif args.backend == "jina":
        backend = JinaBackend()
    else:
        backend = MockBackend()

    print(f"后端: {args.backend} (维度={backend.dim})")

    # 连通性测试
    print("\n[连通性测试]...")
    try:
        v = backend.embed(["测试文本", "hello world"])
        print(f"  OK, 维度={len(v[0])}")
    except Exception as e:
        print(f"  失败: {e}")
        return 1

    # 加载数据
    FIX = os.path.join(os.path.dirname(__file__), "fixtures-synthetic")
    resume_dir = os.path.join(FIX, "resumes")
    job_dir = os.path.join(FIX, "jobs")
    resumes = sorted([f for f in os.listdir(resume_dir) if f.endswith(".txt")])[:args.samples]
    jobs = sorted([f for f in os.listdir(job_dir) if f.endswith(".expected.json")])
    print(f"\n[数据] {len(resumes)} 简历 × {len(jobs)} JD = {len(resumes)*len(jobs)} 对")

    # 运行测试
    print(f"\n[召回率测试] 句子级匹配...")
    t0 = time.time()
    results = run_sentence_test(backend, resume_dir, job_dir, resumes, jobs)
    elapsed = time.time() - t0
    print(f"完成: {len(results)} 条要求, 耗时={elapsed:.1f}s")

    # 分析
    report = analyze(results, args.backend)
    report["elapsed_sec"] = round(elapsed, 1)

    # 保存
    out = args.output or f"tests/embedding_comprehensive_{args.backend}.json"
    with io.open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out}")

    # 召回率判定
    if report["best"]["recall"] >= 90:
        print(f"\n✅ 任务完成: {args.backend} 召回率 {report['best']['recall']:.1f}% >= 90%")
        return 0
    else:
        print(f"\n❌ {args.backend} 最佳召回率 {report['best']['recall']:.1f}% < 90%, 需继续测试其他模型")
        return 2


if __name__ == "__main__":
    sys.exit(main())
