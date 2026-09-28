"""Five formal core acceptance cases. Synthetic/offline; NOT five real people."""
import importlib.util
import json
import logging
import socket
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import api.index as api_module
from api.http_layer import handle_unexpected_error
from providers import model as model_provider
from repositories import database
from services import career_evidence_service

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("core_acceptance", ROOT / "scripts/core-release-acceptance.py")
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


@pytest.fixture
def core(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "placeholder-offline-consent-only")
    monkeypatch.setenv("RESUME_DB_PATH", str(tmp_path / "core.db"))
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("offline network forbidden")))
    api_module.app.config.update(TESTING=True)
    client = api_module.app.test_client()
    def request(method, path, body, token):
        headers = {"X-Consent-Token": token} if token else {}
        response = client.open(path, method=method, json=body, headers=headers)
        return response.status_code, response.get_json(silent=True) or {}
    return acceptance.Acceptance("http://127.0.0.1", request), tmp_path


class GroundedOfflineRouter:
    """Deterministic provider double; the network is explicitly forbidden."""
    def call(self, task, user_input, **kwargs):
        if task != "resume_diagnosis":
            return {"status": "failed", "output": {}, "degraded": True}
        text = str(user_input)
        quote = "编写接口文档并推动联调，与前端约定统一的错误码规范"
        start = text.index(quote)
        span = {"doc": "resume", "quote": quote, "start": start, "end": start + len(quote)}
        output = {"version": "1.0", "pii_removed": True,
                  "subscores": {key: {"score": 75, "rationale": "仅合成验收，依据原文。", "source_spans": [span]}
                                for key in ("structure", "clarity", "achievement_evidence", "skill_evidence", "ats_readability")},
                  "suggestions": [{"id": "core-1", "severity": "P1", "issue": "需补充验证方法。", "suggestion": "补充接口文档评审与联调验证记录。", "source_spans": [span]}]}
        return {"status": "success", "output": output, "model": "offline-double", "degraded": False, "trace_id": "offline_core"}


def test_tc01_full_core_journey_offline_and_cleanup(core, monkeypatch):
    runner, _ = core
    monkeypatch.setattr(model_provider, "build_model_router", lambda: GroundedOfflineRouter())
    runner.journey(1, require_model=False)
    assert runner.checks and all(x["passed"] for x in runner.checks)
    conn = database._get_conn()
    try:
        for table in ("resumes", "diagnoses", "career_evidence", "target_jobs", "applications", "interview_sessions"):
            assert conn.execute("SELECT COUNT(*) AS n FROM " + table).fetchone()["n"] == 0
    finally:
        conn.close()


def test_tc02_production_model_gate_does_not_accept_fallback(core):
    runner, _ = core
    with pytest.raises(AssertionError, match="diagnosis is model, not fallback"):
        runner.journey(1, require_model=True)
    assert any(not row["passed"] for row in runner.checks)


def test_tc03_parallel_quota_is_atomic(core):
    database.init_db()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: database.consume_usage("guest:synthetic-quota", "acceptance", 3, 60, now_epoch=1000), range(8)))
    assert sum(item["allowed"] for item in results) == 3
    assert all(item["retry_after"] > 0 for item in results if not item["allowed"])


def test_tc04_unexpected_exception_never_logs_secret_contents(core, caplog):
    canary = "SYNTHETIC_SENSITIVE_CONTENT_MUST_NOT_APPEAR"
    with api_module.app.test_request_context("/api/health"):
        with caplog.at_level(logging.ERROR):
            try:
                raise RuntimeError(canary)
            except RuntimeError as exc:
                response, status = handle_unexpected_error(exc)
    assert status == 500 and response.json["trace_id"]
    assert canary not in response.get_data(as_text=True)
    assert canary not in caplog.text
    assert "RuntimeError" in caplog.text


def test_tc05_isolated_sqlite_restore_and_session_scope(core):
    """Exercises native SQLite backup/restore only; NOT production Postgres PITR."""
    runner, tmp_path = core
    owner = "guest:synthetic-restore"
    database.bind_session_owner("synthetic-restore-session", owner)
    database.save_resume("synthetic-restore-session", "", "", "synthetic.txt", ".txt", 20, "仅合成测试资料，不含真实个人信息。")
    career_evidence_service.ensure_profile(owner)
    source = sqlite3.connect(tmp_path / "core.db")
    backup = sqlite3.connect(tmp_path / "backup.db")
    restored = sqlite3.connect(tmp_path / "restored.db")
    try:
        source.backup(backup)
        backup.backup(restored)
        assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        tables = [row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for table in tables:
            assert source.execute('SELECT * FROM "' + table + '" ORDER BY rowid').fetchall() == restored.execute('SELECT * FROM "' + table + '" ORDER BY rowid').fetchall()
    finally:
        source.close()
        backup.close()
        restored.close()
    assert database.delete_session_data("synthetic-restore-session", owner)
    assert database.get_resume_detail("synthetic-restore-session") is None
    assert career_evidence_service.profile_payload(owner)["profile"] is not None
