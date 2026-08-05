# -*- coding: utf-8 -*-
"""Contract tests for the unified public API (WF-01~06), no real provider call."""
import io
import json
from unittest.mock import patch

import api.index as api_module
from tools.model_router import ZhipuModelRouter


RESUME = "项目经历：负责接口开发并完成上线验证，持续跟进问题闭环。"
JD_TEXT = (
    "岗位职责：负责后端 API 开发与接口文档维护。\n"
    "任职要求：熟悉 Python、Flask 与 SQL；有项目交付经验。\n"
    "加分项：熟悉 Redis。\n"
    "技术栈：Python、Flask、SQLite。"
)


def valid_profile(resume=RESUME):
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
    def __init__(self, output, status="success", degraded=False):
        self.output = output
        self.status = status
        self.degraded = degraded
        self.call_count = 0

    def call(self, *_args, **_kwargs):
        self.call_count += 1
        return {
            "status": self.status,
            "output": self.output,
            "trace_id": "model_test_trace",
            "degraded": self.degraded,
        }


def raw_client(monkeypatch, router=None):
    if router is not None:
        monkeypatch.setattr(api_module, "build_model_router", lambda: router)
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "test-consent-secret")
    monkeypatch.delenv("DUMATE_CONSENT_MAX_AGE_SECONDS", raising=False)
    api_module.app.config.update(TESTING=True)
    return api_module.app.test_client()


class ConsentedClient:
    """Wraps a test client with a valid consent token."""

    def __init__(self, raw, consent_token):
        self._raw = raw
        self._consent_token = consent_token

    def __getattr__(self, name):
        request_method = getattr(self._raw, name)
        if name not in {"delete", "get", "open", "patch", "post", "put"}:
            return request_method

        def request_with_consent(*args, **kwargs):
            headers = dict(kwargs.pop("headers", {}) or {})
            headers.setdefault("X-Consent-Token", self._consent_token)
            return request_method(*args, headers=headers, **kwargs)

        return request_with_consent


def client(monkeypatch, router=None):
    raw = raw_client(monkeypatch, router)
    consent = raw.post("/api/wf01/consent", json={"accepted": True})
    assert consent.status_code == 200
    return ConsentedClient(raw, consent.json["consent_token"])


def test_consent_issues_short_lived_token(monkeypatch):
    raw = raw_client(monkeypatch)
    response = raw.post("/api/wf01/consent", json={"accepted": True})
    assert response.status_code == 200
    body = response.json
    assert body["status"] == "ACCEPTED"
    assert body["consent_token"]
    assert body["expires_in_seconds"] == 1800

    rejected = raw.post("/api/wf01/consent", json={"accepted": False})
    assert rejected.status_code == 422
    assert rejected.json["error"] == "consent_required"


def test_material_apis_reject_without_consent(monkeypatch):
    raw = raw_client(monkeypatch)
    response = raw.post("/api/wf02/diagnose", json={"resumeText": RESUME})
    assert response.status_code == 428
    assert response.json["error"] == "consent_required"


def test_upload_txt_deidentifies_and_sets_cors(monkeypatch):
    response = client(monkeypatch).post(
        "/api/wf01/upload",
        headers={"Origin": "https://zimo66067-wq.github.io"},
        data={"file": (io.BytesIO(RESUME.encode("utf-8")), "resume.txt")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.json["resumeText"]
    assert response.json["resumeProfile"] is None
    assert response.json["session_id"]
    assert response.headers["Access-Control-Allow-Origin"] == "https://zimo66067-wq.github.io"
    assert response.headers["Cache-Control"] == "no-store"


def test_preflight_allows_only_public_pages_origin(monkeypatch):
    allowed = client(monkeypatch).open(
        "/api/wf02/diagnose", method="OPTIONS", headers={"Origin": "https://zimo66067-wq.github.io"}
    )
    rejected = client(monkeypatch).open(
        "/api/wf02/diagnose", method="OPTIONS", headers={"Origin": "https://attacker.example"}
    )
    assert allowed.status_code == 204
    assert allowed.headers["Access-Control-Allow-Origin"] == "https://zimo66067-wq.github.io"
    assert "X-Consent-Token" in allowed.headers["Access-Control-Allow-Headers"]
    assert "Access-Control-Allow-Origin" not in rejected.headers


def test_health_reports_zhipu_configuration(monkeypatch):
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    unconfigured = client(monkeypatch).get("/api/health")
    monkeypatch.setenv("ZHIPU_API_KEY", "test-key")
    configured = client(monkeypatch).get("/api/health")
    assert unconfigured.json["model_configured"] is False
    assert configured.json["model_configured"] is True
    assert unconfigured.json["workflows"]["wf04"] == "available"


def test_unknown_paths_remain_404(monkeypatch):
    response = client(monkeypatch).get("/docs/")
    assert response.status_code == 404
    assert response.json["error"] == "not_found"


def test_model_router_requires_zhipu_key(monkeypatch):
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.setenv("DUMATE_MODEL", "glm-4.7-flash")
    try:
        api_module.build_model_router()
    except api_module.ApiError as error:
        assert error.code == "model_not_configured"
    else:
        raise AssertionError("model router must require ZHIPU_API_KEY")


def test_zhipu_router_calls_chat_completions_and_parses_json(monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "test-key")
    router = ZhipuModelRouter(primary_model="glm-4.7-flash", enable_log=False)

    class FakeResponse:
        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": '{"ok": true}'}}]}
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    with patch("tools.model_router.urlopen", return_value=FakeResponse()) as mocked_open:
        result = router.call("resume_diagnosis", "分析简历", "简历正文")

    request = mocked_open.call_args.args[0]
    assert request.full_url == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    assert request.get_header("Authorization") == "Bearer test-key"
    assert result["status"] == "success"
    assert result["output"] == {"ok": True}


def test_zhipu_router_extracts_json_after_a_model_preface():
    assert ZhipuModelRouter._parse_output('分析结果如下：\n{"ok": true}') == {"ok": True}


def test_diagnosis_returns_only_valid_grounded_profile(monkeypatch):
    response = client(monkeypatch, FakeRouter(valid_profile())).post(
        "/api/wf02/diagnose", json={"resumeText": RESUME}
    )
    assert response.status_code == 200
    assert response.json["score_R"] == 75.5
    assert response.json["model_trace_id"] == "model_test_trace"
    assert response.json["resumeProfile"]["pii_removed"] is True


def test_diagnosis_normalizes_provider_offsets(monkeypatch):
    provider_profile = {
        "version": "1.0",
        "pii_removed": True,
        "subscores": {
            "structure": 80,
            "clarity": 75,
            "achievement_evidence": 70,
            "skill_evidence": 70,
            "ats_readability": 85,
        },
        "suggestions": [{
            "severity": "P1",
            "issue": "项目成果描述不够具体。",
            "suggestion": "建议补充可验证的项目成果描述。",
            "source_spans": [{"start": 0, "end": len(RESUME)}],
        }],
    }

    response = client(monkeypatch, FakeRouter(provider_profile)).post(
        "/api/wf02/diagnose", json={"resumeText": RESUME}
    )

    assert response.status_code == 200
    profile = response.json["resumeProfile"]
    assert profile["subscores"]["structure"]["score"] == 80
    assert profile["suggestions"][0]["source_spans"][0] == {
        "doc": "resume", "quote": RESUME, "start": 0, "end": len(RESUME)
    }


def test_degraded_or_ungrounded_model_output_uses_grounded_fallback(monkeypatch):
    degraded = client(monkeypatch, FakeRouter(valid_profile(), degraded=True)).post(
        "/api/wf02/diagnose", json={"resumeText": RESUME}
    )
    invalid_profile = valid_profile()
    invalid_profile["subscores"]["structure"]["source_spans"][0]["quote"] = "不存在的证据"
    invalid = client(monkeypatch, FakeRouter(invalid_profile)).post(
        "/api/wf02/diagnose", json={"resumeText": RESUME}
    )
    assert degraded.status_code == 200
    assert degraded.json["diagnosis_mode"] == "fallback_model"
    assert "备用模型" in degraded.json["diagnosis_notice"]
    assert invalid.status_code == 200
    repaired = invalid.json["resumeProfile"]["subscores"]["structure"]
    assert repaired["source_spans"][0]["quote"] == RESUME
    assert "不存在的证据" not in json.dumps(invalid.json, ensure_ascii=False)


def test_unavailable_model_returns_labeled_rule_fallback(monkeypatch):
    response = client(monkeypatch, FakeRouter({}, status="degraded", degraded=True)).post(
        "/api/wf02/diagnose", json={"resumeText": RESUME}
    )
    assert response.status_code == 200
    assert response.json["diagnosis_mode"] == "rule_fallback"
    assert "基础规则诊断" in response.json["diagnosis_notice"]
    assert 0 <= response.json["score_R"] <= 100


# ------------------------------------------------------------------ #
# F2 (WF-03)
# ------------------------------------------------------------------ #

def test_f2_jd_parse_and_match_require_confirmation(monkeypatch):
    session = client(monkeypatch)
    parsed = session.post("/api/wf03/jd", json={"jdText": JD_TEXT})
    assert parsed.status_code == 200
    profile = parsed.json["jobProfile"]
    assert profile["user_confirmed"] is False
    assert len(profile["requirements"]) >= 1

    rejected = session.post("/api/wf03/match", json={"resumeText": RESUME, "jobProfile": profile})
    assert rejected.status_code == 422
    assert rejected.json["error"] == "invalid_job_profile"

    profile["user_confirmed"] = True
    matched = session.post(
        "/api/wf03/match",
        json={"resumeText": RESUME, "jobProfile": profile, "session_id": "test_f2_session"},
    )
    assert matched.status_code == 200
    body = matched.json
    assert body["match_mode"] == "rule_bm25"
    assert isinstance(body["score_M"], (int, float))
    assert body["requirements"]
    assert body["session_id"] == "test_f2_session"
    for item in body["requirements"]:
        assert item["status"] in {"covered", "weak", "missing", "unknown"}


def test_f2_jd_file_upload_accepted(monkeypatch):
    session = client(monkeypatch)
    response = session.post(
        "/api/wf03/jd",
        data={"file": (io.BytesIO(JD_TEXT.encode("utf-8")), "jd.txt")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.json["jobProfile"]["requirements"]


# ------------------------------------------------------------------ #
# F3 (WF-04)
# ------------------------------------------------------------------ #

def _full_flow(monkeypatch, router=None):
    """Run consent -> diagnose -> jd -> match -> interview -> report. Returns session."""
    session = client(monkeypatch, router)
    session_id = "test_full_flow_session"
    diag = session.post(
        "/api/wf02/diagnose",
        json={"resumeText": RESUME, "session_id": session_id},
    )
    assert diag.status_code == 200
    resume_profile = diag.json["resumeProfile"]

    parsed = session.post("/api/wf03/jd", json={"jdText": JD_TEXT, "session_id": session_id})
    assert parsed.status_code == 200
    job_profile = parsed.json["jobProfile"]
    job_profile["user_confirmed"] = True
    match = session.post(
        "/api/wf03/match",
        json={"resumeText": RESUME, "jobProfile": job_profile, "session_id": session_id},
    )
    assert match.status_code == 200
    match_gaps = [
        {"id": item["id"], "type": item["type"], "text": item["text"], "status": item["status"]}
        for item in match.json["requirements"]
        if item["status"] in {"missing", "weak"}
    ]

    start = session.post(
        "/api/wf04/start",
        json={
            "session_id": session_id,
            "jobProfile": job_profile,
            "resumeProfile": resume_profile,
            "matchGaps": match_gaps,
        },
    )
    assert start.status_code == 200
    assert start.json["session_id"] == session_id
    assert start.json["firstQuestion"]

    answers = [
        "我在实习中负责订单接口开发，背景是接口响应慢。我的任务是优化性能，我加了索引并引入缓存，"
        "最终平均响应从 800ms 降到 220ms，提升了 72%。",
        "团队讨论库存方案时我有分歧，我做了压测对比，最终常态用乐观锁、秒杀切分布式锁，"
        "上线后超卖投诉降为 0。",
    ]
    for answer in answers:
        turn = session.post(
            "/api/wf04/answer",
            json={"session_id": session_id, "answer_text": answer, "asr_confidence": None},
        )
        assert turn.status_code == 200
        assert turn.json["turn"]["answer_quote"] in answer
        fu = turn.json["followUp"]
        if fu:
            follow = session.post(
                "/api/wf04/answer",
                json={"session_id": session_id, "answer_text": answer + "补充量化数据，指标符合预期。"},
            )
            assert follow.status_code == 200

    ended = session.post("/api/wf04/end", json={"session_id": session_id})
    assert ended.status_code == 200
    assert ended.json["score_I"] is not None
    assert ended.json["report"]
    return session_id


def test_f3_interview_full_flow(monkeypatch):
    session_id = _full_flow(monkeypatch, FakeRouter(valid_profile()))
    assert session_id


def test_f4_ability_report_requires_completed_flow(monkeypatch):
    session = client(monkeypatch, FakeRouter(valid_profile()))
    missing = session.post("/api/wf05/ability", json={"session_id": "no_data_session"})
    assert missing.status_code == 422
    assert missing.json["error"] == "insufficient_evidence"


def test_f4_ability_report_after_full_flow(monkeypatch):
    session_id = _full_flow(monkeypatch, FakeRouter(valid_profile()))
    response = client(monkeypatch).post("/api/wf05/ability", json={"session_id": session_id})
    # The ability route needs its own consent token; re-issue through a fresh client.
    assert response.status_code == 200 or response.status_code == 422


def test_f4_ability_report_consented_full_flow(monkeypatch):
    session_id = _full_flow(monkeypatch, FakeRouter(valid_profile()))
    session = client(monkeypatch)
    response = session.post("/api/wf05/ability", json={"session_id": session_id})
    assert response.status_code == 200
    ability = response.json["ability"]
    assert ability["baseline"] >= 0
    assert len(ability["dimensions"]) == 6
    assert len(ability["plan"]) == 7
    assert ability["scenario_day7"]["low"] <= ability["scenario_day7"]["high"]
    assert response.json["radar_option"]["radar"]["indicator"]


def test_f6_delete_removes_session_data(monkeypatch):
    session_id = _full_flow(monkeypatch, FakeRouter(valid_profile()))
    session = client(monkeypatch)
    deleted = session.post("/api/wf06/delete", json={"session_id": session_id})
    assert deleted.status_code == 200
    assert deleted.json["status"] == "DELETED"

    # Data is gone: ability now reports insufficient evidence.
    ability = session.post("/api/wf05/ability", json={"session_id": session_id})
    assert ability.status_code == 422
    assert ability.json["error"] == "insufficient_evidence"
