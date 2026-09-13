"""Security regression tests for ownership, quotas, uploads and CSRF."""
import io
import json
from pathlib import Path
import sqlite3
import zipfile

from pypdf import PdfWriter
import pytest

import api.index as api_module
from tools import database
from tools.upload_security import UploadSecurityError, validate_upload


RESUME = "项目经历：负责接口开发、测试、部署与故障复盘，最终将平均响应时间降低百分之六十。"


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = tmp_path / "security.db"
    monkeypatch.setenv("RESUME_DB_PATH", str(path))
    return path


def test_sqlite_and_postgres_schema_definitions_are_separate(isolated_db):
    database.init_db()
    conn = sqlite3.connect(isolated_db)
    try:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert {"session_owners", "usage_events", "resumes", "applications"}.issubset(names)
    assert "BIGSERIAL" not in database._INIT_SQL
    assert "BIGSERIAL" in database._INIT_SQL_PG


def test_database_quota_is_shared_and_atomic(isolated_db):
    first = database.consume_usage("guest:one", "model", 2, 60, now_epoch=1000)
    second = database.consume_usage("guest:one", "model", 2, 60, now_epoch=1001)
    denied = database.consume_usage("guest:one", "model", 2, 60, now_epoch=1002)
    assert first == {"allowed": True, "remaining": 1, "retry_after": 0}
    assert second == {"allowed": True, "remaining": 0, "retry_after": 0}
    assert denied["allowed"] is False
    assert denied["retry_after"] == 58


def test_short_quota_window_does_not_erase_daily_usage(isolated_db):
    owner = "guest:quota-owner"
    assert database.consume_usage(owner, "daily", 2, 86400, now_epoch=1000)["allowed"]
    assert database.consume_usage(owner, "hourly", 10, 3600, now_epoch=6000)["allowed"]
    assert database.consume_usage(owner, "daily", 2, 86400, now_epoch=6001)["allowed"]
    assert database.consume_usage(owner, "daily", 2, 86400, now_epoch=6002)["allowed"] is False


def test_owned_delete_is_transactional_and_complete(isolated_db):
    sid = "owned_delete_session"
    owner = "guest:owner-a"
    assert database.bind_session_owner(sid, owner)
    database.save_resume(sid, "", "", "resume.txt", ".txt", 50, RESUME)
    database.save_diagnosis(sid, 80, "model", "", "trace", json.dumps({"ok": True}))
    database.save_match(sid, {"score_M": 70}, 70)
    database.save_session(sid, "ASK", {"turns": []})
    database.save_ability(sid, {"baseline": 75})
    database.save_rewrite(sid, "s1", "issue", "candidate result")
    database.save_application(sid, owner, "A", "Engineer", "cover letter")

    assert database.delete_session_data(sid, owner_key="guest:attacker") is False
    assert database.get_resume_detail(sid) is not None
    assert database.delete_session_data(sid, owner_key=owner) is True
    assert database.get_resume_detail(sid) is None
    assert database.load_match(sid) is None
    assert database.load_session(sid) == (None, None)
    assert database.load_ability(sid) is None
    assert database.list_rewrites(sid) == []
    assert database.list_applications(owner) == []
    assert database.get_session_owner(sid) is None


def _consent(client, prior_guest_token=""):
    response = client.post(
        "/api/wf01/consent",
        json={"accepted": True, "guest_token": prior_guest_token},
    )
    assert response.status_code == 200
    return response.json


def _material_headers(consent, **extra):
    headers = {
        "X-Consent-Token": consent["consent_token"],
        "X-Guest-Token": consent["guest_token"],
    }
    headers.update(extra)
    return headers


def test_guest_identity_owns_session_and_survives_consent_renewal(isolated_db, monkeypatch):
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "security-test-secret")
    api_module.app.config.update(TESTING=True)
    client = api_module.app.test_client()
    owner = _consent(client)
    attacker = _consent(client)
    sid = "secure_upload_session"

    uploaded = client.post(
        "/api/wf01/upload",
        data={"file": (io.BytesIO(RESUME.encode("utf-8")), "private.txt")},
        content_type="multipart/form-data",
        headers=_material_headers(owner, **{"X-Trace-Id": sid}),
    )
    assert uploaded.status_code == 200

    blocked = client.post(
        "/api/wf06/delete",
        json={"session_id": sid},
        headers=_material_headers(attacker),
    )
    assert blocked.status_code == 404

    renewed = _consent(client, owner["guest_token"])
    deleted = client.post(
        "/api/wf06/delete",
        json={"session_id": sid},
        headers=_material_headers(renewed),
    )
    assert deleted.status_code == 200


def test_verified_guest_resources_transfer_on_registration(isolated_db, monkeypatch):
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "security-test-secret")
    api_module.app.config.update(TESTING=True)
    client = api_module.app.test_client()
    guest = _consent(client)
    sid = "guest_to_user_session"
    uploaded = client.post(
        "/api/wf01/upload",
        data={"file": (io.BytesIO(RESUME.encode("utf-8")), "private.txt")},
        content_type="multipart/form-data",
        headers=_material_headers(guest, **{"X-Trace-Id": sid}),
    )
    assert uploaded.status_code == 200
    assert database.get_session_owner(sid).startswith("guest:")

    registered = client.post(
        "/api/auth/register",
        json={
            "phone": "13800138000",
            "email": "security@example.test",
            "password": "SafePass123",
            "name": "安全测试",
        },
        headers={"X-Guest-Token": guest["guest_token"]},
    )
    assert registered.status_code == 201
    assert database.get_session_owner(sid) == f"user:{registered.json['id']}"

    deleted = client.post(
        "/api/wf06/delete",
        json={"session_id": sid},
        headers=_material_headers(guest),
    )
    assert deleted.status_code == 200


def test_cross_site_cookie_write_is_rejected(isolated_db, monkeypatch):
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "security-test-secret")
    api_module.app.config.update(TESTING=True)
    client = api_module.app.test_client()
    client.set_cookie("zy_session", "opaque-cookie")
    response = client.post(
        "/api/wf01/consent",
        json={"accepted": True},
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403
    assert response.json["error"] == "csrf_rejected"


def test_cross_site_guest_token_delete_is_rejected(isolated_db, monkeypatch):
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "security-test-secret")
    api_module.app.config.update(TESTING=True)
    client = api_module.app.test_client()
    consent = _consent(client)
    headers = _material_headers(consent, **{"X-Trace-Id": "csrf_guest_session"})
    uploaded = client.post(
        "/api/wf01/upload",
        data={"file": (io.BytesIO(RESUME.encode("utf-8")), "resume.txt")},
        content_type="multipart/form-data",
        headers=headers,
    )
    assert uploaded.status_code == 200
    session_id = uploaded.json["session_id"]

    blocked_headers = _material_headers(consent, Origin="https://attacker.example")
    blocked = client.post(
        "/api/wf06/delete",
        json={"session_id": session_id},
        headers=blocked_headers,
    )
    assert blocked.status_code == 403
    assert blocked.json["error"] == "csrf_rejected"
    assert database.get_resume_detail(session_id) is not None

    deleted = client.post(
        "/api/wf06/delete",
        json={"session_id": session_id},
        headers=_material_headers(consent),
    )
    assert deleted.status_code == 200


def test_sensitive_json_endpoints_reject_array_bodies(isolated_db, monkeypatch):
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "security-test-secret")
    api_module.app.config.update(TESTING=True)
    client = api_module.app.test_client()
    consent = _consent(client)
    headers = _material_headers(consent)

    register = client.post("/api/auth/register", json=[])
    assert register.status_code == 422
    assert register.json["error"] == "invalid_request"

    for endpoint in (
        "/api/wf04/stream",
        "/api/wf02/optimize",
        "/api/wf02/apply-rewrite",
        "/api/wf07/cover-letter",
        "/api/wf07/applications",
    ):
        response = client.post(endpoint, json=[], headers=headers)
        assert response.status_code == 422, endpoint
        assert response.json["error"] == "invalid_request", endpoint




def _minimal_docx(path, extra_entries=None):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("word/document.xml", "<w:document></w:document>")
        for name, data in extra_entries or []:
            archive.writestr(name, data)


def test_upload_validator_accepts_structurally_valid_documents(tmp_path):
    text_path = tmp_path / "resume.txt"
    text_path.write_text(RESUME, encoding="utf-8")
    docx_path = tmp_path / "resume.docx"
    _minimal_docx(docx_path)
    pdf_path = tmp_path / "resume.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    assert validate_upload(text_path, ".txt") == {}
    assert validate_upload(docx_path, ".docx")["entry_count"] == 2
    assert validate_upload(pdf_path, ".pdf")["page_count"] == 1


@pytest.mark.parametrize(
    "name,data,code",
    [
        ("fake.pdf", b"not a pdf", "file_signature_mismatch"),
        ("fake.docx", b"not a zip", "file_signature_mismatch"),
        ("binary.txt", b"hello\x00world", "binary_text_file"),
    ],
)
def test_upload_validator_rejects_signature_spoofing(tmp_path, name, data, code):
    path = tmp_path / name
    path.write_bytes(data)
    with pytest.raises(UploadSecurityError) as raised:
        validate_upload(path, path.suffix)
    assert raised.value.code == code


@pytest.mark.parametrize(
    "entry_name,entry_data,code",
    [
        ("../escape.xml", "x", "unsafe_archive_path"),
        ("word/vbaProject.bin", b"macro", "active_content"),
        ("word/embeddings/object.bin", b"object", "active_content"),
        ("word/media/bomb.bin", "__compressed_bomb__", "compression_bomb"),
    ],
)
def test_upload_validator_rejects_hostile_docx(tmp_path, entry_name, entry_data, code):
    path = tmp_path / "hostile.docx"
    if entry_data == "__compressed_bomb__":
        entry_data = b"A" * (2 * 1024 * 1024)
    _minimal_docx(path, [(entry_name, entry_data)])
    with pytest.raises(UploadSecurityError) as raised:
        validate_upload(path, ".docx")
    assert raised.value.code == code
