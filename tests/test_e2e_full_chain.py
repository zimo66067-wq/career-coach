# -*- coding: utf-8 -*-
"""test_e2e_full_chain.py · 端到端全链路验证

A. HTTP 层：F1（同意 -> 上传 -> 诊断）与 F2（同意 -> 上传 JD -> 解析
   -> 用户确认 -> 匹配），校验输入到输出的全程可追溯。
B. 工具层全链路：去标识化 -> 规则诊断 -> BM25 匹配 -> 面试引擎 ->
   分数复算 C0 -> 能力聚合 -> 雷达图 -> Schema 校验，保证模块间
   集成调用无断裂。
"""
import io
import json
import tempfile
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator

import api.index as api_module
from tools import deidentify, radar_adapter, rescore, validate_schema
from tools.interview_engine import InterviewEngine


ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures-synthetic"

RESUME = (
    "教育经历：某某大学计算机本科。"
    "项目经历：负责订单接口开发，将响应从 800ms 优化到 220ms。"
    "技能：Python、MySQL、Redis。"
)
JD_TEXT = (
    "职位名称：后端开发工程师\n"
    "岗位职责：负责订单服务接口开发与维护\n"
    "任职要求：熟悉 Python、Flask、SQL 与 Redis；本科及以上学历\n"
    "加分项：有分布式系统经验者优先\n"
)


def grounded_profile(resume=RESUME):
    span = {"doc": "resume", "quote": resume, "start": 0, "end": len(resume)}
    subscores = {}
    for key, score in {
        "structure": 80,
        "clarity": 75,
        "achievement_evidence": 70,
        "skill_evidence": 70,
        "ats_readability": 85,
    }.items():
        subscores[key] = {
            "score": score,
            "rationale": "该项依据简历原文进行判断。",
            "source_spans": [span],
        }
    return {
        "version": "1.0",
        "pii_removed": True,
        "subscores": subscores,
        "suggestions": [{
            "id": "suggestion-1",
            "severity": "P1",
            "issue": "项目成果描述不够具体。",
            "suggestion": "建议补充可验证的项目成果描述。",
            "source_spans": [span],
        }],
    }


class FakeRouter:
    def __init__(self, output):
        self.output = output

    def call(self, *_args, **_kwargs):
        return {
            "status": "success",
            "output": self.output,
            "trace_id": "e2e_model_trace",
            "degraded": False,
        }


def consented_client(monkeypatch, router=None):
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "test-consent-secret")
    monkeypatch.setenv(
        "RESUME_DB_PATH",
        str(Path(tempfile.mkdtemp(prefix="career_coach_test_")) / ("test_%s.db" % uuid.uuid4().hex[:8])),
    )
    if router is not None:
        monkeypatch.setattr(api_module, "build_model_router", lambda: router)
    api_module.app.config.update(TESTING=True)
    raw = api_module.app.test_client()
    consent = raw.post("/api/wf01/consent", json={"accepted": True})
    assert consent.status_code == 200
    token = consent.json["consent_token"]

    class Consented:
        def __getattr__(self, name):
            method = getattr(raw, name)

            def call(*args, **kwargs):
                headers = dict(kwargs.pop("headers", {}) or {})
                headers.setdefault("X-Consent-Token", token)
                return method(*args, headers=headers, **kwargs)

            return call

    return Consented()


# ---------------------------------------------------------------- #
# A. HTTP 端到端
# ---------------------------------------------------------------- #


def test_http_f1_chain_full(monkeypatch):
    client = consented_client(monkeypatch, FakeRouter(grounded_profile()))

    upload = client.post(
        "/api/wf01/upload",
        data={"file": (io.BytesIO(RESUME.encode("utf-8")), "resume.txt")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 200
    assert upload.json["resumeProfile"] is None
    assert upload.json["trace_id"]
    session_id = upload.json["session_id"]
    assert session_id

    diagnose = client.post(
        "/api/wf02/diagnose",
        json={"resumeText": upload.json["resumeText"], "session_id": session_id},
    )
    assert diagnose.status_code == 200
    body = diagnose.json
    assert body["score_R"] == 75.5
    assert body["diagnosis_mode"] == "model"
    assert body["resumeProfile"]["pii_removed"] is True
    assert body["resumeProfile"]["subscores"]["structure"]["score"] == 80
    assert body["model_trace_id"] == "e2e_model_trace"
    assert body["session_id"] == session_id


def test_http_f2_chain_full(monkeypatch):
    client = consented_client(monkeypatch)

    upload = client.post(
        "/api/wf03/upload",
        data={"file": (io.BytesIO(JD_TEXT.encode("utf-8")), "jd.txt")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 200
    session_id = upload.json["session_id"]

    parsed = client.post("/api/wf03/jd", json={"jdText": upload.json["jdText"]})
    assert parsed.status_code == 200
    job_profile = parsed.json["jobProfile"]
    assert job_profile["user_confirmed"] is False
    assert job_profile["requirements"]

    job_profile["user_confirmed"] = True
    matched = client.post(
        "/api/wf03/match",
        json={"resumeText": RESUME, "jobProfile": job_profile, "session_id": session_id},
    )
    assert matched.status_code == 200
    body = matched.json
    assert body["match_mode"] == "rule_bm25"
    assert isinstance(body["score_M"], int)
    assert 0 <= body["score_M"] <= 100
    assert body["requirements"]
    assert all(r["status"] in {"covered", "weak", "missing", "unknown"} for r in body["requirements"])
    assert "规则" in body["match_notice"]
    assert body["trace_id"]
    assert body["session_id"] == session_id


def test_http_full_product_chain_f1_to_f4_and_delete(monkeypatch):
    """端到端：同意 -> F1 上传/诊断 -> F2 解析/确认/匹配 -> F3 面试
    -> F4 能力报告 -> F6 删除闭环，全程经 HTTP 接口无断裂。"""
    client = consented_client(monkeypatch, FakeRouter(grounded_profile()))

    # F1
    upload = client.post(
        "/api/wf01/upload",
        data={"file": (io.BytesIO(RESUME.encode("utf-8")), "resume.txt")},
        content_type="multipart/form-data",
    )
    session_id = upload.json["session_id"]
    diagnose = client.post(
        "/api/wf02/diagnose",
        json={"resumeText": upload.json["resumeText"], "session_id": session_id},
    )
    assert diagnose.status_code == 200
    resume_profile = diagnose.json["resumeProfile"]
    score_r = diagnose.json["score_R"]

    # F2
    parsed = client.post("/api/wf03/jd", json={"jdText": JD_TEXT, "session_id": session_id})
    job_profile = parsed.json["jobProfile"]
    job_profile["user_confirmed"] = True
    matched = client.post(
        "/api/wf03/match",
        json={"resumeText": RESUME, "jobProfile": job_profile, "session_id": session_id},
    )
    assert matched.status_code == 200
    score_m = matched.json["score_M"]

    # F3：启动面试 -> 回答 3 轮 -> 结束
    started = client.post(
        "/api/wf04/start",
        json={
            "session_id": session_id,
            "jobProfile": job_profile,
            "resumeProfile": resume_profile,
            "matchGaps": matched.json["gaps"],
        },
    )
    assert started.status_code == 200
    assert started.json["firstQuestion"]
    assert started.json["session_id"] == session_id

    answers = [
        "背景是订单接口响应慢。我的任务是定位瓶颈。我通过慢查询日志加索引并引入 Redis 缓存，最终响应从 800ms 降到 220ms。",
        "团队讨论库存方案时有分歧。我做了压测对比，最终采用乐观锁加分布式锁的组合方案，解决了超卖问题。",
        "学习新技术时我先读官方文档 Quickstart，跑通最小示例再对照项目代码，两周内能独立写接口。",
    ]
    for answer in answers:
        answered = client.post(
            "/api/wf04/answer",
            json={"session_id": session_id, "answer_text": answer, "asr_confidence": None},
        )
        assert answered.status_code == 200
        assert answered.json["turn"]["turn_id"] >= 1

    ended = client.post("/api/wf04/end", json={"session_id": session_id})
    assert ended.status_code == 200
    score_i = ended.json["score_I"]
    assert score_i is not None and 0 <= score_i <= 100
    assert len(ended.json["turns"]) == 3

    # F4：能力报告 + 雷达图
    ability = client.post("/api/wf05/ability", json={"session_id": session_id})
    assert ability.status_code == 200
    body = ability.json
    assert body["score_R"] == score_r
    assert body["score_M"] == score_m
    assert body["score_I"] == score_i
    assert 0 <= body["C0"] <= 100
    assert len(body["ability"]["dimensions"]) == 6
    assert len(body["radar_option"]["radar"]["indicator"]) == 6
    assert len(body["ability"]["plan"]) == 7

    # F6：删除闭环 -> 数据不可再用
    deleted = client.post("/api/wf06/delete", json={"session_id": session_id})
    assert deleted.status_code == 200
    assert deleted.json["status"] == "DELETED"

    after_delete = client.post("/api/wf05/ability", json={"session_id": session_id})
    assert after_delete.status_code == 422
    assert after_delete.json["error"] == "insufficient_evidence"


# ---------------------------------------------------------------- #
# B. 工具层全链路
# ---------------------------------------------------------------- #


def test_tool_chain_full_products(monkeypatch):
    # WF-01：去标识化
    raw = (FIX / "resumes" / "resume-01-swe.txt").read_text(encoding="utf-8")
    cleaned, _mapping = deidentify.deidentify(raw)
    assert "[REDACTED_" in cleaned

    # WF-02：规则诊断 -> R
    profile = api_module.build_rule_based_resume_profile(cleaned)
    r_score = rescore.calc_R({k: v["score"] for k, v in profile["subscores"].items()})
    assert 0 <= r_score <= 100

    # WF-03：JD 解析 -> BM25 匹配 -> M
    job_text = (FIX / "jobs" / "job-01-swe.txt").read_text(encoding="utf-8")
    job_profile = api_module.build_job_profile(job_text)
    job_profile["user_confirmed"] = True
    match = api_module.match_job_profile(cleaned, job_profile)
    m_score = match["score_M"]
    assert 0 <= m_score <= 100
    gaps = [
        {"id": r["id"], "type": r["type"], "text": r["text"], "status": r["status"]}
        for r in match["requirements"]
        if r["status"] in ("missing", "weak")
    ]

    # WF-04：面试引擎（基于 F2 缺口）-> I
    engine = InterviewEngine()
    session = engine.start(job_profile, profile, gaps)
    answers = [
        "背景是订单接口响应慢。我的任务是定位瓶颈。我通过慢查询日志加索引并引入 Redis 缓存，最终响应从 800ms 降到 220ms。",
        "团队讨论库存方案时有分歧。我做了压测对比，最终采用乐观锁加分布式锁的组合方案，解决了超卖问题。",
        "学习新技术时我先读官方文档 Quickstart，跑通最小示例再对照项目代码，两周内能独立写接口。",
    ]
    for answer in answers:
        engine.next_question(session)
        engine.submit_answer(session, answer)
    ended = engine.end_session(session)
    i_score = ended["score_I"]
    assert i_score is not None and 0 <= i_score <= 100
    assert len(ended["turns"]) == 3

    # WF-05：分数复算 C0 -> 能力聚合 -> 雷达图 -> Schema 校验
    computed = rescore.compute({
        "R": {k: v["score"] for k, v in profile["subscores"].items()},
        "M": {"requirements": [{"type": r["type"], "status": r["status"]} for r in match["requirements"]]},
        "I": ended["i_subscores"],
    })
    c0 = computed["C0"]
    assert 0 <= c0 <= 100
    assert computed["C7_low"] <= computed["C7_high"]

    ability = json.loads((FIX / "abilities" / "ability-01.json").read_text(encoding="utf-8"))
    ability["resume_score"] = round(r_score, 2)
    ability["match_score"] = m_score
    ability["interview_score"] = round(i_score, 2)
    ability["baseline"] = c0

    errors = []
    validate_schema.business_rules(ability, errors)
    assert not errors, "AbilityProfile 业务规则校验失败: %s" % errors
    schema = json.loads(
        (ROOT / "contracts" / "ability-profile.schema.json").read_text(encoding="utf-8")
    )
    assert not list(Draft202012Validator(schema).iter_errors(ability))

    option = radar_adapter.build_option(ability)
    assert len(option["radar"]["indicator"]) == 6
    assert len(option["series"][0]["data"]) == 3


def test_tool_chain_rejects_broken_contract():
    """链路断裂防护：interview 的 answer_quote 非子串时不得进入评分。"""
    engine = InterviewEngine()
    session = engine.start(
        {"requirements": [{"id": "J1", "type": "hard", "text": "缺口"}]},
        {},
        [{"id": "J1", "type": "hard", "text": "缺口", "status": "weak"}],
    )
    engine.next_question(session)
    engine.submit_answer(session, "这是我的完整回答，包含量化结果 30%。")
    session["turns"][0]["answer_quote"] = "与回答无关的引用"
    ended = engine.end_session(session)
    assert ended["score_I"] is None
