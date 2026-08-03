# -*- coding: utf-8 -*-
"""Contract tests for the public browser API, without a real provider call."""
import io
import json
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

    def call(self, *_args, **_kwargs):
        return {
            "status": self.status,
            "output": self.output,
            "trace_id": "model_test_trace",
            "degraded": self.degraded,
        }


def client(monkeypatch, router=None):
    if router is not None:
        monkeypatch.setattr(api_module, "build_model_router", lambda: router)
    api_module.app.config.update(TESTING=True)
    return api_module.app.test_client()


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
    assert "Access-Control-Allow-Origin" not in rejected.headers


def test_health_reports_zhipu_configuration(monkeypatch):
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    unconfigured = client(monkeypatch).get("/api/health")
    monkeypatch.setenv("ZHIPU_API_KEY", "test-key")
    configured = client(monkeypatch).get("/api/health")
    assert unconfigured.json["model_configured"] is False
    assert configured.json["model_configured"] is True


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


def test_diagnosis_returns_only_valid_grounded_profile(monkeypatch):
    response = client(monkeypatch, FakeRouter(valid_profile())).post(
        "/api/wf02/diagnose", json={"resumeText": RESUME}
    )
    assert response.status_code == 200
    assert response.json["score_R"] == 75.5
    assert response.json["model_trace_id"] == "model_test_trace"
    assert response.json["resumeProfile"]["pii_removed"] is True


def test_degraded_or_ungrounded_model_output_is_not_shown(monkeypatch):
    degraded = client(monkeypatch, FakeRouter(valid_profile(), degraded=True)).post(
        "/api/wf02/diagnose", json={"resumeText": RESUME}
    )
    invalid_profile = valid_profile()
    invalid_profile["subscores"]["structure"]["source_spans"][0]["quote"] = "不存在的证据"
    invalid = client(monkeypatch, FakeRouter(invalid_profile)).post(
        "/api/wf02/diagnose", json={"resumeText": RESUME}
    )
    assert degraded.status_code == 503
    assert degraded.json["error"] == "model_unavailable"
    assert invalid.status_code == 502
    assert invalid.json["error"] == "model_output_invalid"
