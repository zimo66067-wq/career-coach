# -*- coding: utf-8 -*-
"""Phase 5 contract tests: provider abstraction (mock-first), services layer,
and the apply loop (cover letter -> confirm -> application tracking CRUD)."""
import io
import json
import time
import tempfile
import uuid
from pathlib import Path

import api.index as api_module
import services.apply_service as apply_service
import services.diagnosis_service as diagnosis_service
import services.interview_service as interview_service
import services.match_service as match_service
import services.task_service as task_service

RESUME = (
    "项目经历：负责后端接口开发并完成上线验证，持续跟进问题闭环。"
    "熟悉 Python、Flask 与 SQL 查询优化，具备数据库设计与接口文档维护经验。"
)


def raw_client(monkeypatch):
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "test-consent-secret")
    monkeypatch.delenv("DUMATE_CONSENT_MAX_AGE_SECONDS", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    if not hasattr(monkeypatch, "_career_test_db"):
        monkeypatch._career_test_db = str(
            Path(tempfile.mkdtemp(prefix="career_coach_test_"))
            / ("test_%s.db" % uuid.uuid4().hex[:8])
        )
    monkeypatch.setenv("RESUME_DB_PATH", monkeypatch._career_test_db)
    api_module.app.config.update(TESTING=True)
    return api_module.app.test_client()


def issue_consent(raw):
    response = raw.post("/api/wf01/consent", json={"accepted": True})
    assert response.status_code == 200
    return response.json["consent_token"]


def authed(raw, token, method, path, json_body=None, data=None, content_type=None):
    kwargs = {"headers": {"X-Consent-Token": token}}
    if json_body is not None:
        kwargs["json"] = json_body
    if data is not None:
        kwargs["data"] = data
    if content_type is not None:
        kwargs["content_type"] = content_type
    return getattr(raw, method)(path, **kwargs)


def upload_and_diagnose(raw, token):
    uploaded = raw.post(
        "/api/wf01/upload",
        data={"file": (io.BytesIO(RESUME.encode("utf-8")), "resume.txt")},
        content_type="multipart/form-data",
        headers={"X-Consent-Token": token},
    )
    assert uploaded.status_code == 200
    body = uploaded.json
    sid = body["session_id"]
    diag = authed(raw, token, "post", "/api/wf02/diagnose", {"resumeText": body["resumeText"], "session_id": sid})
    assert diag.status_code == 200
    return sid


# ---------------------------------------------------------------- #
# Provider abstraction
# ---------------------------------------------------------------- #

def test_model_provider_mock_first_without_key(monkeypatch):
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    router = api_module.build_model_router()
    result = router.call("resume_diagnosis", "项目经历：负责开发并上线。")
    assert result["status"] == "success"
    assert isinstance(result["output"], dict)
    assert result["degraded"] is True
    # cover-letter style call returns text
    text = router.call("cover_letter", "写一封求职信")
    assert result["status"] == "success"
    assert isinstance(text["output"], str) and text["output"]


def test_model_provider_default_requires_key(monkeypatch):
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    try:
        api_module.build_model_router()
    except api_module.ApiError as error:
        assert error.code == "model_not_configured"
    else:
        raise AssertionError("default router must require ZHIPU_API_KEY")


# ---------------------------------------------------------------- #
# Services layer exports
# ---------------------------------------------------------------- #

def test_services_layer_exposes_expected_entry_points():
    assert callable(diagnosis_service.diagnose_resume)
    assert callable(diagnosis_service.build_rule_based_resume_profile)
    assert callable(match_service.build_job_profile)
    assert callable(match_service.match_job_profile)
    assert callable(interview_service.start_interview)
    assert callable(interview_service.answer_interview)
    assert callable(interview_service.end_interview)
    assert callable(interview_service.build_ability_profile)
    assert callable(task_service._f2_match_chunk)
    assert callable(apply_service.generate_cover_letter)
    assert callable(apply_service.create_application)
    assert callable(apply_service.list_applications_for)
    assert callable(apply_service.delete_application)


def test_services_diagnose_matches_previous_rule_fallback(monkeypatch):
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    with api_module.app.test_request_context("/"):
        profile, score, _trace, mode, notice = diagnosis_service.diagnose_resume(RESUME)
    assert mode == "rule_fallback"
    assert 0 <= score <= 100
    assert profile["version"] == "1.0"
    assert profile["suggestions"]
    assert notice


# ---------------------------------------------------------------- #
# Apply loop (wf07)
# ---------------------------------------------------------------- #

def test_wf07_requires_consent(monkeypatch):
    raw = raw_client(monkeypatch)
    response = raw.post("/api/wf07/cover-letter", json={"session_id": "x"})
    assert response.status_code == 428


def test_apply_loop_generate_confirm_list_delete(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)
    sid = upload_and_diagnose(raw, token)

    cover = authed(
        raw, token, "post", "/api/wf07/cover-letter",
        {"session_id": sid, "company": "字节跳动", "position": "后端开发工程师"},
    )
    assert cover.status_code == 200
    candidate = cover.json["candidate"]
    assert cover.json["pending_confirm"] is True
    assert len(candidate) >= 10
    assert "字节跳动" in candidate or "岗位" in candidate

    created = authed(
        raw, token, "post", "/api/wf07/applications",
        {
            "session_id": sid,
            "company": "字节跳动",
            "position": "后端开发工程师",
            "cover_letter": candidate,
        },
    )
    assert created.status_code == 201
    app = created.json["application"]
    app_id = app["id"]
    assert app["company"] == "字节跳动"
    assert app["status"] == "applied"

    listed = authed(raw, token, "get", "/api/wf07/applications")
    assert listed.status_code == 200
    apps = listed.json["applications"]
    assert len(apps) == 1
    assert apps[0]["id"] == app_id

    deleted = authed(raw, token, "delete", "/api/wf07/applications?id=%s" % app_id)
    assert deleted.status_code == 200
    assert deleted.json["status"] == "DELETED"

    listed_after = authed(raw, token, "get", "/api/wf07/applications")
    assert listed_after.json["applications"] == []


def test_apply_loop_rejects_other_owner(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)
    sid = upload_and_diagnose(raw, token)
    cover = authed(
        raw, token, "post", "/api/wf07/cover-letter",
        {"session_id": sid, "company": "A公司", "position": "测试工程师"},
    )
    assert cover.status_code == 200
    created = authed(
        raw, token, "post", "/api/wf07/applications",
        {
            "session_id": sid,
            "company": "A公司",
            "position": "测试工程师",
            "cover_letter": cover.json["candidate"],
        },
    )
    assert created.status_code == 201
    app_id = created.json["application"]["id"]

    # a different guest token cannot see or delete the record
    raw2 = raw_client(monkeypatch)
    time.sleep(1.1)  # consent token 秒级时间戳：错开避免同秒生成相同 token
    token2 = issue_consent(raw2)
    other_listed = authed(raw2, token2, "get", "/api/wf07/applications")
    assert other_listed.json["applications"] == []
    other_deleted = authed(raw2, token2, "delete", "/api/wf07/applications?id=%s" % app_id)
    assert other_deleted.status_code == 404


def test_cover_letter_requires_diagnosis(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)
    uploaded = raw.post(
        "/api/wf01/upload",
        data={"file": (io.BytesIO(RESUME.encode("utf-8")), "resume.txt")},
        content_type="multipart/form-data",
        headers={"X-Consent-Token": token},
    )
    sid = uploaded.json["session_id"]
    cover = authed(
        raw, token, "post", "/api/wf07/cover-letter",
        {"session_id": sid, "company": "B公司", "position": "开发工程师"},
    )
    assert cover.status_code == 422
    assert cover.json["error"] == "diagnosis_required"


# ---------------------------------------------------------------- #
# Vercel routing coverage
# ---------------------------------------------------------------- #

def test_vercel_routes_cover_phase5_endpoints():
    config = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
    routes = {item["source"]: item["destination"] for item in config["rewrites"]}
    assert routes["/api/wf07/cover-letter"] == "/api?_route=wf07/cover-letter"
    assert routes["/api/wf07/applications"] == "/api?_route=wf07/applications"
