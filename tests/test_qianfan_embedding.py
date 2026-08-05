# -*- coding: utf-8 -*-
"""千帆 Embedding 连通性与小样本召回率的手工联调脚本。

该文件保留在 ``tests`` 目录是为了复用合成样本，但它依赖真实的外部
服务和用户凭据，不能在 pytest 收集或 CI 中自动执行。请显式运行：

    QIANFAN_AK=... QIANFAN_SK=... python tests/test_qianfan_embedding.py
"""

from __future__ import annotations

import io
import json
import math
import os
import time
from pathlib import Path


COVERED_TH = 0.55
WEAK_TH = 0.30
SAMPLE_RESUMES = [
    "resume-01-swe",
    "resume-05-fresh",
    "resume-10-devops",
    "resume-15-bigdata",
    "resume-20-fresh-general",
]
SAMPLE_JOBS = ["job-01-swe", "job-02-fe", "job-07-pm", "job-09-algo", "job-10-bigdata"]


def embed(texts: list[str], access_key: str, secret_key: str, model: str = "embedding-v1") -> list[list[float]]:
    """Call the documented Qianfan embedding endpoint for a small manual check."""
    import requests

    response = requests.post(
        "https://qianfan.baidubce.com/v2/embeddings",
        headers={
            "Authorization": f"Bearer {access_key}/{secret_key}",
            "Content-Type": "application/json",
        },
        json={"input": texts, "model": model},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(f"千帆返回错误：{payload['error'].get('message', payload['error'])}")
    return [item["embedding"] for item in payload.get("data", [])]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(x * y for x, y in zip(left, right))
    left_norm = math.sqrt(sum(x * x for x in left))
    right_norm = math.sqrt(sum(x * x for x in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def load_text(path: Path) -> str:
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def load_requirements(path: Path) -> list[dict]:
    with io.open(path, encoding="utf-8") as handle:
        return json.load(handle)["requirements"]


def run_sample_recall_check(access_key: str, secret_key: str) -> dict:
    """Run the bounded 5×5 sample only; this intentionally performs remote requests."""
    fixture_root = Path(__file__).parent / "fixtures-synthetic"
    total_requirements = 0
    hit_requirements = 0
    details: list[dict] = []

    for resume_slug in SAMPLE_RESUMES:
        resume_text = load_text(fixture_root / "resumes" / f"{resume_slug}.txt")
        resume_sentences = [line.strip() for line in resume_text.splitlines() if len(line.strip()) >= 4]
        for job_slug in SAMPLE_JOBS:
            requirements = load_requirements(fixture_root / "jobs" / f"{job_slug}.expected.json")
            vectors = embed(
                [item["text"] for item in requirements] + resume_sentences[:10],
                access_key,
                secret_key,
            )
            requirement_vectors = vectors[: len(requirements)]
            sentence_vectors = vectors[len(requirements) :]
            for index, requirement in enumerate(requirements):
                total_requirements += 1
                confidence = max(
                    (cosine_similarity(requirement_vectors[index], vector) for vector in sentence_vectors),
                    default=0.0,
                )
                status = "covered" if confidence >= COVERED_TH else "weak" if confidence >= WEAK_TH else "missing"
                if status != "missing":
                    hit_requirements += 1
                details.append(
                    {
                        "resume": resume_slug,
                        "job": job_slug,
                        "requirement": requirement["id"],
                        "status": status,
                        "confidence": round(confidence, 3),
                    }
                )
            time.sleep(2)

    recall_rate = hit_requirements / total_requirements if total_requirements else 0.0
    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "api_status": "ok",
        "recall_rate": round(recall_rate, 4),
        "total_requirements": total_requirements,
        "hit_requirements": hit_requirements,
        "thresholds": {"covered": COVERED_TH, "weak": WEAK_TH},
        "samples": SAMPLE_RESUMES,
        "jobs": SAMPLE_JOBS,
        "details": details,
    }


def main() -> int:
    access_key = os.environ.get("QIANFAN_AK", "")
    secret_key = os.environ.get("QIANFAN_SK", "")
    if not access_key or not secret_key:
        print("缺少 QIANFAN_AK 或 QIANFAN_SK；此手工外部联调未执行。")
        return 2

    try:
        probe = embed(["连通性测试文本"], access_key, secret_key)
        if not probe:
            raise RuntimeError("Embedding 接口返回空向量")
        result = run_sample_recall_check(access_key, secret_key)
    except Exception as exc:  # The command is a diagnostic utility and must return a clear nonzero status.
        print(f"千帆 Embedding 联调失败：{exc}")
        return 1

    result["embedding_dimension"] = len(probe[0])
    output_path = Path(__file__).with_name("qianfan_embedding_test_result.json")
    with io.open(output_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(f"千帆 Embedding 联调通过，维度={len(probe[0])}，召回率={result['recall_rate']:.1%}")
    print(f"结果已写入：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
