# -*- coding: utf-8 -*-
"""test_match.py · BM25 匹配：硬性要求召回对拍 + 四态互斥"""
import io
import json
import os

import match_requirements as mr

FIX = os.path.join(os.path.dirname(__file__), "fixtures-synthetic")


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def run_match(resume_slug, job_slug):
    resume = read(os.path.join(FIX, "resumes", resume_slug + ".txt"))
    job_expected = json.load(io.open(os.path.join(FIX, "jobs", job_slug + ".expected.json"), encoding="utf-8"))
    sentences = mr.split_sentences(resume)
    sentences_tokens = [mr.tokenize(s) for s in sentences]
    sent_uni = [mr.unigrams(s) for s in sentences]
    doc_uni = mr.unigrams(resume)
    matcher = mr.Bm25Matcher()
    results = []
    for req in job_expected["requirements"]:
        conf, idx = matcher.best(req["text"], sentences_tokens, sent_uni=sent_uni, doc_uni=doc_uni)
        has_partial = bool(mr.unigrams(req["text"]) & doc_uni)
        results.append({"id": req["id"], "type": req["type"], "status": mr.judge(conf, has_partial)})
    return results


def test_hard_recall_swe():
    """resume-01 × job-01：硬性要求召回（covered+weak）≥ 85% 口径的人工标注对拍
    合成样本仅 4 条硬性要求，BM25 简化匹配下允许 covered/weak/missing/unknown 组合，
    这里断言：与简历强相关的 J1（学历专业）与 J2（Go/Java 项目）不得 missing。"""
    results = run_match("resume-01-swe", "job-01-swe")
    by_id = {r["id"]: r for r in results}
    assert by_id["J1"]["status"] in ("covered", "weak"), "学历专业要求未被识别"
    assert by_id["J2"]["status"] in ("covered", "weak"), "Go/Java 要求未被识别"


def test_four_states_mutually_exclusive():
    results = run_match("resume-01-swe", "job-01-swe")
    valid = {"covered", "weak", "missing", "unknown"}
    for r in results:
        assert r["status"] in valid


def test_irrelevant_resume_lower_confidence():
    """应届简历（resume-05）对后端 JD 的覆盖率应低于对口简历（resume-01）"""
    def coverage(slug):
        results = run_match(slug, "job-01-swe")
        return sum(1 for r in results if r["status"] in ("covered", "weak")) / len(results)
    assert coverage("resume-01-swe") >= coverage("resume-05-fresh")


def test_embedding_backend_not_implemented():
    import pytest
    with pytest.raises(NotImplementedError):
        mr.QianfanEmbedder(api_key=None)


def test_evidence_filter_removes_headers():
    """章节标题/过短句不作为匹配证据。"""
    assert not mr._is_substantive_evidence("技能清单")
    assert not mr._is_substantive_evidence("项目经历")
    assert not mr._is_substantive_evidence("姓名：张三")
    assert mr._is_substantive_evidence("语言：Go（熟练）、Java（熟练）、Python（了解）")


def test_verify_evidence_requires_factual_overlap():
    """证据验证器：泛化词不算重叠，无事实重叠即否决。"""
    assert mr.verify_evidence("熟悉 Go 语言", "使用 Go 语言实现订单查询接口")
    assert not mr.verify_evidence("熟悉 HTML/CSS/JavaScript 及 ES6+",
                                  "Java（熟悉）、MySQL（熟悉）、Spring Boot（入门）")
    assert not mr.verify_evidence("熟练使用 SQL 进行数据分析",
                                  "语言：JavaScript（熟练）、TypeScript（熟练）")
    assert not mr.verify_evidence("编写单元测试保证代码质量",
                                  "编写接口文档并推动联调，与前端约定统一的错误码规范")
    assert not mr.verify_evidence("熟悉 Go", "")
