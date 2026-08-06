# -*- coding: utf-8 -*-
"""test_match_boundary.py · 匹配模块边界与异常场景

覆盖：judge 四态阈值边界、tokenize/unigrams/split_sentences 空输入、
BM25 空输入、load_requirements 多来源、embedding 批量/逐条降级，
以及"全部 unknown"时 API 返回与 scoring.md 契约的偏差记录。
"""
import io
import json

import pytest

import match_requirements as mr
import api.index as api_module
from tools.rescore import calc_M


# ---------------------------------------------------------------- #
# judge 阈值边界
# ---------------------------------------------------------------- #


def test_judge_threshold_boundaries():
    assert mr.judge(0.55, True) == "covered"
    assert mr.judge(0.55 - 1e-9, True) == "weak"
    assert mr.judge(0.30, True) == "weak"
    assert mr.judge(0.30 - 1e-9, True) == "missing"
    assert mr.judge(0.05, True) == "missing"
    assert mr.judge(0.05, False) == "unknown"
    assert mr.judge(0.0, True) == "missing"
    assert mr.judge(0.0, False) == "unknown"


def test_threshold_constants_frozen():
    assert mr.COVERED_TH == 0.55
    assert mr.WEAK_TH == 0.30
    assert mr.UNKNOWN_TH == 0.12


# ---------------------------------------------------------------- #
# 文本处理空输入与降级
# ---------------------------------------------------------------- #


def test_tokenize_empty_inputs():
    assert mr.tokenize(None) == []
    assert mr.tokenize("") == []


def test_tokenize_regex_fallback(monkeypatch):
    monkeypatch.setattr(mr, "_JIEBA_LOADED", False)
    tokens = mr.tokenize("熟悉 Go 语言")
    assert tokens, "regex 降级路径应产出 token"
    assert any("go" in t.lower() for t in tokens)


def test_unigrams_mixed_cjk_en():
    uni = mr.unigrams("熟悉 Python 与 MySQL")
    assert "python" in uni
    assert "mysql" in uni
    assert any(("熟悉" in uni) or ("熟" in uni) for _ in (0,))


def test_split_sentences_empty():
    assert mr.split_sentences("") == []
    assert mr.split_sentences("  \n  ") == []


def test_bm25_best_empty_inputs():
    matcher = mr.Bm25Matcher()
    assert matcher.best("", [], None, None) == (0.0, -1)
    assert matcher.best("要求", [], set(), set()) == (0.0, -1)


# ---------------------------------------------------------------- #
# load_requirements 多来源
# ---------------------------------------------------------------- #


def test_load_requirements_from_json(tmp_path):
    data = {"requirements": [
        {"id": "J1", "type": "hard", "text": "熟悉 Python"},
        {"id": "R1", "type": "responsibility", "text": "负责接口开发"},
    ]}
    path = tmp_path / "job.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    requirements = mr.load_requirements(str(path))
    assert len(requirements) == 2
    assert requirements[0]["type"] == "hard"


def test_load_requirements_from_text(tmp_path):
    text = "任职要求\n1. 熟悉 Python\n2. 本科及以上\n加分项\n1. 有分布式经验"
    path = tmp_path / "job.txt"
    path.write_text(text, encoding="utf-8")
    requirements = mr.load_requirements(str(path))
    assert requirements
    assert requirements[0]["type"] == "hard"
    assert any(r["type"] == "preferred" for r in requirements)


def test_load_requirements_falls_back_to_sentences(tmp_path):
    text = "第一句没有任何标题。第二句也是要求。"
    path = tmp_path / "job.txt"
    path.write_text(text, encoding="utf-8")
    requirements = mr.load_requirements(str(path))
    assert requirements
    assert all(r["type"] == "hard" for r in requirements)


# ---------------------------------------------------------------- #
# embedding 批量 / 逐条降级
# ---------------------------------------------------------------- #


class BatchEmbedder:
    def batch_match(self, req_texts, sentences):
        return [(0.9, 0)] * len(req_texts)


class ItemEmbedder:
    def __init__(self):
        self.calls = 0

    def similarity(self, _a, _b):
        self.calls += 1
        return 0.7


def test_run_embedding_match_batch_path():
    requirements = [{"id": "r1", "type": "hard", "text": "熟悉 Python"}]
    sentences = ["我熟悉 Python"]
    resume_tokens = mr.unigrams("我熟悉 Python")
    results = mr._run_embedding_match(BatchEmbedder(), requirements, sentences, resume_tokens)
    assert results[0]["status"] == "covered"
    assert results[0]["evidence"] == sentences[0]


def test_run_embedding_match_item_path():
    requirements = [{"id": "r1", "type": "hard", "text": "熟悉 Python"}]
    sentences = ["我熟悉 Python"]
    resume_tokens = mr.unigrams("我熟悉 Python")
    embedder = ItemEmbedder()
    results = mr._run_embedding_match(embedder, requirements, sentences, resume_tokens)
    assert results[0]["status"] == "covered"
    assert embedder.calls >= 1


# ---------------------------------------------------------------- #
# 全部 unknown 的契约偏差记录
# ---------------------------------------------------------------- #


def test_calc_m_all_unknown_is_insufficient_evidence():
    """scoring.md 契约：全部类别 unknown 时 M 为 insufficient_evidence。"""
    m, cat = calc_M([{"type": "hard", "status": "unknown"}])
    assert m is None
    assert cat["hard"] is None


def test_api_match_all_unknown_returns_insufficient():
    """契约：全部要求 unknown 时返回 insufficient_evidence，绝不输出 0 分。"""
    job_profile = {
        "user_confirmed": True,
        "requirements": [{
            "id": "r1",
            "type": "hard",
            "text": "Kubernetes 与 gRPC 微服务经验",
            "source_span": {"doc": "job", "quote": "Kubernetes 与 gRPC 微服务经验", "start": 0, "end": 20},
        }],
    }
    result = api_module.match_job_profile("技能：无任何相关关键词。", job_profile)
    assert result["requirements"][0]["status"] == "unknown"
    assert result["insufficient_evidence"] is True
    assert result["score_M"] is None
    assert result["low_score_analysis"] is None
    assert "不足" in result["match_notice"]


def job_profile_for_analysis():
    return {
        "user_confirmed": True,
        "requirements": [
            {"id": "J1", "type": "hard", "text": "熟悉 Python 与 SQL"},
            {"id": "J2", "type": "hard", "text": "本科及以上学历"},
            {"id": "J3", "type": "hard", "text": "熟悉 Java 或 Go"},
            {"id": "R1", "type": "responsibility", "text": "负责接口开发"},
            {"id": "T1", "type": "terminology", "text": "Python、Flask、Redis"},
        ],
    }


def test_resume_too_short_flags_and_analysis():
    result = api_module.match_job_profile("项目：负责接口开发。技能：Python。", job_profile_for_analysis())
    assert result["resume_too_short"] is True
    assert result["score_M"] is not None
    analysis = result["low_score_analysis"]
    assert analysis is not None
    assert len(analysis["dimensions"]) >= 3
    assert analysis["suggestion"]
    assert "较短" in result["match_notice"] or "不足" in result["match_notice"]


def test_low_score_analysis_present_below_50():
    weak_resume = "教育经历：某某大学市场营销专业。实习：负责社群运营与活动策划。技能：Excel、Python。"
    result = api_module.match_job_profile(weak_resume, job_profile_for_analysis())
    assert result["score_M"] is not None and result["score_M"] < 50
    analysis = result["low_score_analysis"]
    assert analysis is not None
    assert len(analysis["dimensions"]) >= 3
    assert ("50" in analysis["summary"]) or ("低" in analysis["summary"])


def test_low_score_analysis_absent_when_strong_match():
    strong_resume = (
        "教育经历：某某大学计算机本科。项目经历：负责订单服务接口开发，"
        "使用 Python、Flask、SQL 与 Redis，将响应从 800ms 优化到 220ms，性能提升显著。"
        "技能：Python、Flask、SQL、Redis、分布式系统。"
        "课外习惯阅读官方文档与源码，参与开源社区讨论并维护技术博客；"
        "课程设计涉及数据库设计与接口联调，能够独立完成模块开发与问题定位。"
        "曾参与一次线上性能专项，负责压测数据整理与结果分析，并输出改进报告。"
    )
    result = api_module.match_job_profile(strong_resume, job_profile_for_analysis())
    assert result["resume_too_short"] is False
    assert result["score_M"] is not None and result["score_M"] >= 50
    assert result["low_score_analysis"] is None
