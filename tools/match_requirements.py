# -*- coding: utf-8 -*-
"""match_requirements.py · JD 要求级匹配（WF-03）

用法:
  python tools/match_requirements.py --resume <clean.txt> --job <job.txt 或 job.expected.json> \
      --backend bm25|embedding [--output match.json]

后端:
  - embedding: 千帆 Embedding-V1（HTTP API；需配置 QIANFAN_API_KEY + QIANFAN_SECRET_KEY）
  - bm25: 纯 stdlib TF-IDF/BM25 实现（默认，标注「简化匹配」）

输出: 逐条 requirement 的 {status: covered|weak|missing|unknown, evidence}
  covered: 最佳匹配分 >= COVERED_TH
  weak:    WEAK_TH <= 分 < COVERED_TH
  missing: 分 < WEAK_TH 且简历中存在部分相关词
  unknown: 分 < WEAK_TH 且几乎无相关词（材料不足以判断）
"""
import argparse
import io
import json
import math
import os
import re
import sys
from collections import Counter

COVERED_TH = 0.55
WEAK_TH = 0.30
UNKNOWN_TH = 0.12

# ---------------- 文本切分（中英文混合，无需第三方分词） ----------------
RE_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*|[\u4e00-\u9fa5]")
STOP = set("的了和是有在与我你他她它们这那也不都就及或着吧呢啊嘛么很还被把对于等以及一个我们你们他们".split())


def tokenize(text):
    toks = RE_TOKEN.findall(text.lower())
    bigrams = ["".join(toks[i:i + 2]) for i in range(len(toks) - 1)
               if re.match(r"^[\u4e00-\u9fa5]", toks[i]) and re.match(r"^[\u4e00-\u9fa5]", toks[i + 1])]
    words = [t for t in toks if len(t) > 1 and t not in STOP]
    return words + bigrams


def unigrams(text):
    """覆盖率判定用的词集：英文词 + 去停用词的中文单字。"""
    toks = RE_TOKEN.findall(text.lower())
    return set(t for t in toks
               if t not in STOP and (len(t) > 1 or re.match(r"^[\u4e00-\u9fa5]$", t)))


def split_sentences(text):
    parts = re.split(r"[\n。；;！？!?]", text)
    return [p.strip() for p in parts if len(p.strip()) >= 4]


# ---------------- BM25 ----------------
class Bm25Matcher:
    def __init__(self, k1=1.5, b=0.75):
        self.k1, self.b = k1, b

    def score(self, query_tokens, doc_tokens_list):
        n = len(doc_tokens_list)
        if n == 0:
            return [0.0]
        dfs = Counter()
        tfs = []
        avgdl = 0.0
        for toks in doc_tokens_list:
            tf = Counter(toks)
            tfs.append(tf)
            avgdl += len(toks)
            for t in tf:
                dfs[t] += 1
        avgdl = avgdl / n or 1.0
        scores = []
        for tf in tfs:
            s = 0.0
            dl = sum(tf.values()) or 1
            for q in set(query_tokens):
                df = dfs.get(q, 0)
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                f = tf.get(q, 0)
                s += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / avgdl))
            scores.append(s)
        return scores

    def best(self, requirement, sentences_tokens, sent_uni=None, doc_uni=None):
        """返回 (置信度, 最佳句索引)。
        先用 BM25 选最佳证据句，再以「去停用词词集覆盖率」计算置信度：
        conf = max(句级覆盖率, 0.9 × 文档级覆盖率) ∈ [0,1]，可解释。"""
        q = tokenize(requirement)
        q_uni = unigrams(requirement)
        if not q or not sentences_tokens or not q_uni:
            return 0.0, -1
        raw = self.score(q, sentences_tokens)
        idx = raw.index(max(raw))
        sent_cov = 0.0
        if sent_uni is not None:
            sent_cov = len(q_uni & sent_uni[idx]) / len(q_uni)
        doc_cov = 0.0
        if doc_uni:
            doc_cov = len(q_uni & doc_uni) / len(q_uni)
        conf = max(sent_cov, 0.9 * doc_cov)
        return conf, idx


# ---------------- Embedding 后端 ----------------
class EmbedderBase:
    def similarity(self, a, b):
        raise NotImplementedError


class ZhipuEmbedder(EmbedderBase):
    """智谱AI Embedding-2/3 封装（推荐，免费2000万Token）

    用法:
      from tools.match_requirements import ZhipuEmbedder
      embedder = ZhipuEmbedder(api_key=os.environ.get("ZHIPU_API_KEY"))
      vecs = embedder.embed(["文本1", "文本2"])
    """

    def __init__(self, api_key=None, model="embedding-2"):
        self.api_key = api_key or os.environ.get("ZHIPU_API_KEY")
        self.model = model
        if not self.api_key:
            raise NotImplementedError(
                "智谱 embedding 未配置 ZHIPU_API_KEY；"
                "请改用 --backend bm25（简化匹配）"
            )
        from zhipuai import ZhipuAI
        self.client = ZhipuAI(api_key=self.api_key)
        self.dim = 1024 if model == "embedding-2" else 2048

    def embed(self, texts):
        """批量嵌入，返回 List[List[float]]。"""
        all_embeddings = []
        batch_size = 16  # 智谱API批量限制
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            resp = self.client.embeddings.create(model=self.model, input=batch)
            all_embeddings.extend([item.embedding for item in resp.data])
        return all_embeddings

    @staticmethod
    def _cosine(va, vb):
        """对两个向量算余弦相似度，返回 [0, 1]。"""
        dot = sum(x * y for x, y in zip(va, vb))
        na = math.sqrt(sum(x * x for x in va))
        nb = math.sqrt(sum(x * x for x in vb))
        return dot / (na * nb) if na * nb > 0 else 0.0

    def similarity(self, a, b):
        """对两段文本算余弦相似度（先 embed 再算）。"""
        vecs = self.embed([a, b])
        return self._cosine(vecs[0], vecs[1])

    def batch_match(self, requirements_text, sentences):
        """句子级批量匹配：预 embed 所有简历句子和 JD 要求，矩阵计算余弦相似度。

        Args:
            requirements_text: List[str]，JD 要求文本列表
            sentences: List[str]，简历切分后的句子列表

        Returns:
            List of (best_conf, best_idx) 对，长度 == len(requirements_text)
        """
        # 一次性 embed 全部句子和全部要求
        sent_vecs = self.embed(sentences)
        req_vecs = self.embed(requirements_text)

        results = []
        for ri, rv in enumerate(req_vecs):
            best_conf = 0.0
            best_idx = -1
            for si, sv in enumerate(sent_vecs):
                conf = self._cosine(rv, sv)
                if conf > best_conf:
                    best_conf = conf
                    best_idx = si
            results.append((best_conf, best_idx))
        return results


class QianfanEmbedder(EmbedderBase):
    """千帆 Embedding-V1 HTTP API 封装。

    鉴权流程: AK/SK -> access_token -> 调用 embedding 接口。
    降级策略: AK/SK 缺失时 raise NotImplementedError，调用方应回退到 BM25。
    """

    TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
    EMBED_URL = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenniu/embedding_v1"

    def __init__(self, api_key=None, secret_key=None, model="Embedding-V1"):
        self.api_key = api_key or os.environ.get("QIANFAN_API_KEY")
        self.secret_key = secret_key or os.environ.get("QIANFAN_SECRET_KEY")
        self.model = model
        if not self.api_key or not self.secret_key:
            raise NotImplementedError(
                "千帆 embedding 未配置 QIANFAN_API_KEY/QIANFAN_SECRET_KEY；"
                "请改用 --backend bm25（简化匹配）"
            )
        self._token = None
        self._token_expiry = 0

    def _get_token(self):
        """获取 access_token，带简易缓存。"""
        import time
        if self._token and time.time() < self._token_expiry:
            return self._token
        import requests
        params = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.secret_key,
        }
        resp = requests.post(self.TOKEN_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 2592000) - 60
        return self._token

    def embed(self, texts):
        """批量嵌入，返回 List[List[float]]。单次最多 16 条。"""
        import requests
        token = self._get_token()
        url = self.EMBED_URL + "?access_token=" + token
        payload = {"input": texts, "model": self.model}
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "error_code" in data:
            raise RuntimeError("千帆 embedding 错误 %s: %s" % (
                data.get("error_code"), data.get("error_msg", "")))
        return [item["embedding"] for item in data["data"]]

    def similarity(self, a, b):
        """计算两段文本的余弦相似度，返回 [0, 1] 浮点数。"""
        vecs = self.embed([a, b])
        va, vb = vecs[0], vecs[1]
        dot = sum(x * y for x, y in zip(va, vb))
        norm_a = math.sqrt(sum(x * x for x in va))
        norm_b = math.sqrt(sum(x * x for x in vb))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        # 余弦相似度范围 [-1,1]，线性映射到 [0,1]
        cos_sim = dot / (norm_a * norm_b)
        return (cos_sim + 1) / 2


def judge(conf, has_partial):
    if conf >= COVERED_TH:
        return "covered"
    if conf >= WEAK_TH:
        return "weak"
    return "missing" if has_partial else "unknown"


def load_requirements(job_path):
    """job 为纯文本 JD 时按行抽取要求；为 *.expected.json 时直接读 requirements。"""
    if job_path.endswith(".json"):
        data = json.load(io.open(job_path, encoding="utf-8"))
        return [{"id": r["id"], "type": r["type"], "text": r["text"]} for r in data["requirements"]]
    text = io.open(job_path, encoding="utf-8").read()
    reqs = []
    sec = None
    type_map = {"任职要求": "hard", "工作职责": "responsibility", "加分项": "preferred", "常用技术栈": "terminology"}
    idx = 0
    for line in text.splitlines():
        line = line.strip()
        if line in type_map:
            sec = type_map[line]
            continue
        if sec and re.match(r"^\d+[.、]", line):
            idx += 1
            reqs.append({"id": "L%d" % idx, "type": sec, "text": re.sub(r"^\d+[.、]\s*", "", line)})
        elif sec == "terminology" and line and "：" not in line and "、" in line:
            idx += 1
            reqs.append({"id": "L%d" % idx, "type": "terminology", "text": line})
    if not reqs:  # 兜底：全文按句切
        for i, s in enumerate(split_sentences(text)):
            reqs.append({"id": "S%d" % i, "type": "hard", "text": s})
    return reqs


def _run_embedding_match(embedder, requirements, sentences, resume_tokens):
    """通用 embedding 匹配流程。

    优先用 batch_match（批量 embed + 矩阵计算）；
    若 embedder 不支持 batch_match，逐条降级到 similarity。
    """
    req_texts = [r["text"] for r in requirements]

    if hasattr(embedder, "batch_match"):
        # 批量模式：只调 2 次 API（句子 + 要求），矩阵计算余弦
        match_results = embedder.batch_match(req_texts, sentences)
    else:
        # 逐条模式
        match_results = []
        for req_text in req_texts:
            best_conf = 0.0
            best_idx = -1
            for si, sent in enumerate(sentences):
                try:
                    conf = embedder.similarity(req_text, sent)
                except Exception as exc:
                    print("[match] embedding 调用失败: %s" % exc, file=sys.stderr)
                    conf = 0.0
                if conf > best_conf:
                    best_conf = conf
                    best_idx = si
            match_results.append((best_conf, best_idx))

    results = []
    for i, req in enumerate(requirements):
        best_conf, best_idx = match_results[i]
        req_tokens = unigrams(req["text"])
        has_partial = bool(req_tokens & resume_tokens)
        status = judge(best_conf, has_partial)
        results.append({
            "id": req["id"], "type": req["type"], "text": req["text"],
            "status": status, "confidence": round(best_conf, 3),
            "evidence": sentences[best_idx] if best_idx >= 0 and best_conf >= WEAK_TH else "",
        })
    return results


def main():
    ap = argparse.ArgumentParser(description="JD 要求级匹配（covered/weak/missing/unknown）")
    ap.add_argument("--resume", required=True)
    ap.add_argument("--job", required=True, help="JD 纯文本或 job expected.json")
    ap.add_argument("--backend", choices=["bm25", "embedding"], default="bm25")
    ap.add_argument("--embedding-model", default=None,
                    help="指定 embedding 模型：zhipu-embedding-2 / zhipu-embedding-3 / qianfan")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    resume_text = io.open(args.resume, encoding="utf-8").read()
    requirements = load_requirements(args.job)
    sentences = split_sentences(resume_text)
    sentences_tokens = [tokenize(s) for s in sentences]
    sent_uni = [unigrams(s) for s in sentences]
    resume_tokens = unigrams(resume_text)

    if args.backend == "embedding":
        embedder = None
        embedder_name = "none"

        # 1) 优先尝试智谱 Embedding（免费2000万Token）
        if args.embedding_model in (None, "zhipu-embedding-2", "zhipu-embedding-3"):
            model = "embedding-3" if args.embedding_model == "zhipu-embedding-3" else "embedding-2"
            try:
                embedder = ZhipuEmbedder(model=model)
                embedder_name = "zhipu-%s" % model
                print("[match] 使用智谱 %s（句子级批量匹配）" % model, file=sys.stderr)
            except NotImplementedError as e:
                print("[match] 智谱不可用: %s" % e, file=sys.stderr)

        # 2) 降级到千帆 Embedding
        if embedder is None and args.embedding_model in (None, "qianfan"):
            try:
                embedder = QianfanEmbedder()
                embedder_name = "qianfan-%s" % embedder.model
                print("[match] 降级到千帆 %s" % embedder.model, file=sys.stderr)
            except NotImplementedError as e:
                print("[match] 千帆不可用: %s" % e, file=sys.stderr)

        if embedder is not None:
            results = _run_embedding_match(embedder, requirements, sentences, resume_tokens)
            output = {
                "backend": "embedding", "degraded": False,
                "model": embedder_name,
                "note": "句子级 embedding 语义匹配（%s）" % embedder_name,
                "thresholds": {"covered": COVERED_TH, "weak": WEAK_TH, "unknown": UNKNOWN_TH},
                "results": results,
            }
            payload = json.dumps(output, ensure_ascii=False, indent=2)
            if args.output:
                with io.open(args.output, "w", encoding="utf-8") as f:
                    f.write(payload + "\n")
                print("[match] OK -> %s（%d 条要求, %s）" % (args.output, len(results), embedder_name))
            else:
                print(payload)
            return
        # embedding 初始化失败，降级到 BM25
        print("[match] 所有 embedding 后端不可用，降级到 BM25 简化匹配", file=sys.stderr)

    matcher = Bm25Matcher()
    results = []
    for req in requirements:
        conf, best_idx = matcher.best(req["text"], sentences_tokens, sent_uni=sent_uni, doc_uni=resume_tokens)
        req_tokens = unigrams(req["text"])
        has_partial = bool(req_tokens & resume_tokens)
        status = judge(conf, has_partial)
        results.append({
            "id": req["id"], "type": req["type"], "text": req["text"],
            "status": status, "confidence": round(conf, 3),
            "evidence": sentences[best_idx] if best_idx >= 0 and conf >= WEAK_TH else "",
        })

    degraded = args.backend == "embedding"
    output = {
        "backend": "bm25",
        "degraded": degraded,
        "note": "简化匹配（本地 BM25）" + ("（从 embedding 降级）" if degraded else ""),
        "thresholds": {"covered": COVERED_TH, "weak": WEAK_TH, "unknown": UNKNOWN_TH},
        "results": results,
    }
    payload = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        with io.open(args.output, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
        print("[match] OK -> %s（%d 条要求）" % (args.output, len(results)))
    else:
        print(payload)


if __name__ == "__main__":
    main()
