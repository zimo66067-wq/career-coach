"""Negative controls for release privacy and truthful model provenance."""
import importlib.util
import json
import logging
from pathlib import Path

import pytest

import api.startup as startup
from providers import model as model_provider
from providers.model_router import ModelRouter
from services.diagnosis_service import diagnose_resume
from tests.test_core_release import core  # fixture with isolated DB and no network


@pytest.mark.parametrize("output", [{}, [], {"subscores": {}}, {"unrelated": "text"}])
def test_empty_or_unusable_model_output_is_not_called_model(core, monkeypatch, output):
    class EmptyRouter:
        def call(self, *args, **kwargs):
            return {"status": "success", "output": output, "degraded": False}
    monkeypatch.setattr(model_provider, "build_model_router", lambda: EmptyRouter())
    result = diagnose_resume("项目经历：负责接口开发、测试与联调并记录可核验的项目结果。")
    assert result[3] == "rule_fallback"


def test_model_router_exception_does_not_log_provider_payload(core, caplog):
    class BrokenRouter(ModelRouter):
        def _try_call(self, *args, **kwargs):
            raise RuntimeError("SYNTHETIC_PRIVATE_PROVIDER_PAYLOAD")
    with caplog.at_level(logging.WARNING):
        result = BrokenRouter(primary_model="synthetic", fallback_model="", enable_log=False).call("resume_diagnosis", "synthetic")
    assert result["status"] == "degraded"
    assert "SYNTHETIC_PRIVATE_PROVIDER_PAYLOAD" not in caplog.text


def test_health_never_exposes_database_exception(core, monkeypatch, caplog):
    def fail():
        raise RuntimeError("SYNTHETIC_PRIVATE_DATABASE_DSN")
    monkeypatch.setattr(startup, "_MIGRATION_ERROR", None)
    monkeypatch.setattr(startup._migrations, "ensure_applied", fail)
    with caplog.at_level(logging.ERROR):
        startup.bootstrap()
        state = startup.migration_status()
    assert not state["ok"] and state["error"] == "RuntimeError"
    assert "SYNTHETIC_PRIVATE_DATABASE_DSN" not in json.dumps(state) + caplog.text


def test_session_delete_reports_retained_long_term_records(core):
    runner, _ = core
    token = runner.consent()
    runner.request("POST", "/api/wf04/start", {"session_id": "synthetic-delete-scope"}, token)
    response = runner.request("POST", "/api/wf06/delete", {"session_id": "synthetic-delete-scope"}, token)
    assert response["scope"] == "workflow_session"
    assert {"career_profile", "career_evidence", "target_jobs", "account"} <= set(response["retained"])


def test_export_refuses_repository_and_overwrite(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("safe_legacy_export", root / "scripts/backup-sessions.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError):
        module.export_destination(str(root / "deliverables/private-data.json"))
    existing = tmp_path / "existing.json"
    existing.write_text("unchanged", encoding="utf-8")
    with pytest.raises(ValueError):
        module.export_destination(str(existing))
    assert existing.read_text() == "unchanged"
    assert module.export_destination(str(tmp_path / "new.json")) == tmp_path / "new.json"
