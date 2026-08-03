# -*- coding: utf-8 -*-
"""Contract tests for the public browser API, without a real provider call."""
import io
import json
from pathlib import Path
from unittest.mock import patch

import api.index as api_module
from tools.model_router import ZhipuModelRouter


RESUME = "项目经历：负责接口开发并完成上线验证，持续跟进问题闭环。"


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
    """Keep pre-existing material API tests explicit about a valid consent."""

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


def test_unknown_paths_remain_404_instead_of_becoming_internal_errors(monkeypatch):
    response = client(monkeypatch).get("/docs/")

    assert response.status_code == 404
    assert response.json["error"] == "not_found"


def test_material_apis_reject_requests_without_explicit_consent(monkeypatch):
    response = raw_client(monkeypatch).post("/api/wf02/diagnose", json={"resumeText": RESUME})

    assert response.status_code == 428
    assert response.json["error"] == "consent_required"


def test_f2_requires_explicit_job_confirmation_before_matching(monkeypatch):
    session = client(monkeypatch)
    parsed = session.post(
        "/api/wf03/jd",
        json={"jdText": "Backend engineer role. Requirements include Python, Flask, SQL, Redis, and API delivery."},
    )

    assert parsed.status_code == 200
    profile = parsed.json["jobProfile"]
    assert profile["user_confirmed"] is False

    rejected = session.post("/api/wf03/match", json={"resumeText": RESUME, "jobProfile": profile})
    assert rejected.status_code == 422
    assert rejected.json["error"] == "invalid_job_profile"

    profile["user_confirmed"] = True
    matched = session.post("/api/wf03/match", json={"resumeText": RESUME, "jobProfile": profile})
    assert matched.status_code == 200
    assert matched.json["match_mode"] == "rule_bm25"


def test_unconfigured_workflows_fail_closed_instead_of_returning_404(monkeypatch):
    response = raw_client(monkeypatch).post("/api/wf04/start", json={})

    assert response.status_code == 501
    assert response.json["error"] == "workflow_not_configured"


def test_vercel_routes_cover_the_public_api_contract():
    config = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
    routes = {item["source"]: item["destination"] for item in config["rewrites"]}

    assert routes["/api/wf01/consent"] == "/api?_route=wf01/consent"
    assert routes["/api/wf03/upload"] == "/api?_route=wf03/upload"
    assert routes["/api/wf03/jd"] == "/api?_route=wf03/jd"
    assert routes["/api/wf03/match"] == "/api?_route=wf03/match"


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


def test_diagnosis_normalizes_provider_offsets_and_missing_container_fields(monkeypatch):
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
    assert profile["suggestions"][0]["id"] == "suggestion-1"
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
    assert response.json["resumeProfile"]["subscores"]["structure"]["source_spans"][0]["quote"] == RESUME
    assert 0 <= response.json["score_R"] <= 100


def test_invalid_provider_citation_is_repaired_without_retry(monkeypatch):
    invalid_profile = valid_profile()
    invalid_profile["subscores"]["structure"]["source_spans"][0]["quote"] = "不存在的证据"
    router = FakeRouter(invalid_profile)

    response = client(monkeypatch, router).post(
        "/api/wf02/diagnose", json={"resumeText": RESUME}
    )

    assert response.status_code == 200
    assert router.call_count == 1
