# -*- coding: utf-8 -*-
"""Contract tests for the tasks API (phase 3: client-driven chunked tasks).

Covers creation, idempotency, chunked progression, guest ownership isolation,
unsupported task types, and the failed-state transition in the service layer.
"""
import tempfile
import time
import uuid
from pathlib import Path

import api.index as api_module
import tools.tasks as tasks_service

RESUME = (
    "项目经历：负责后端接口开发并完成上线验证，持续跟进问题闭环。"
    "熟悉 Python、Flask 与 SQL 查询优化，具备数据库设计与接口文档维护经验。"
)


def long_jd(count=23):
    return "\n".join(
        "任职要求：熟悉 %s 号技术栈并具备实际项目经验，能够在简历中提供对应成果证据。"
        % i
        for i in range(1, count + 1)
    )


def make_payload():
    return {
        "major_code": "080901",
        "resume_text": RESUME,
        "jd_text": long_jd(23),
    }


def raw_client(monkeypatch):
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "test-consent-secret")
    monkeypatch.delenv("DUMATE_CONSENT_MAX_AGE_SECONDS", raising=False)
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


def authed_post(raw, token, path, json_body):
    return raw.post(path, json=json_body, headers={"X-Consent-Token": token})


def authed_get(raw, token, path):
    return raw.get(path, headers={"X-Consent-Token": token})


def test_create_task_returns_pending_and_chunks_to_done(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)
    created = authed_post(
        raw, token, "/api/tasks",
        {"task_type": "f2_match", "payload": make_payload(), "idempotency_key": "k-1"},
    )
    assert created.status_code == 201
    task = created.json["task"]
    task_id = task["id"]
    assert task_id.startswith("task_")
    assert task["state"] == "pending"
    assert task["progress"] == 0
    assert task["task_type"] == "f2_match"
    assert task["payload"]["major_code"] == "080901"

    seen_progress = []
    last = None
    for _ in range(10):
        response = authed_post(raw, token, "/api/tasks/%s/next" % task_id, {})
        assert response.status_code == 200
        last = response.json["task"]
        seen_progress.append(last["progress"])
        if last["state"] == "done":
            break
    assert last["state"] == "done"
    assert last["progress"] == 100
    assert seen_progress == sorted(set(seen_progress)) and seen_progress[-1] == 100
    result = last["result_json"]
    assert result.get("__requirements")
    assert result.get("__rows")
    mode_b = result.get("__result", {}).get("modeB") or {}
    assert mode_b.get("coverage") is not None
    assert mode_b.get("overall") is not None
    assert mode_b.get("requirements")

    # Done task can be queried and re-advanced without changes.
    queried = authed_get(raw, token, "/api/tasks/%s" % task_id)
    assert queried.status_code == 200
    assert queried.json["task"]["state"] == "done"
    again = authed_post(raw, token, "/api/tasks/%s/next" % task_id, {})
    assert again.status_code == 200
    assert again.json["task"]["state"] == "done"
    assert again.json["notice"] == "任务已完成。"


def test_same_idempotency_key_returns_same_task(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)
    body = {"task_type": "f2_match", "payload": make_payload(), "idempotency_key": "idem-dup"}
    first = authed_post(raw, token, "/api/tasks", body)
    second = authed_post(raw, token, "/api/tasks", body)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json["task"]["id"] == second.json["task"]["id"]


def test_guest_ownership_isolation_returns_404(monkeypatch):
    raw = raw_client(monkeypatch)
    token_a = issue_consent(raw)
    # Consent tokens embed a second-granularity timestamp, so two tokens issued
    # in the same second are identical. Sleep to obtain a distinct guest owner.
    time.sleep(1.1)
    token_b = issue_consent(raw)
    created = authed_post(
        raw, token_a, "/api/tasks",
        {"task_type": "f2_match", "payload": make_payload(), "idempotency_key": "iso-1"},
    )
    task_id = created.json["task"]["id"]
    assert authed_get(raw, token_b, "/api/tasks/%s" % task_id).status_code == 404
    assert authed_post(raw, token_b, "/api/tasks/%s/next" % task_id, {}).status_code == 404


def test_unsupported_task_type_rejected(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)
    response = authed_post(
        raw, token, "/api/tasks",
        {"task_type": "interview", "payload": make_payload()},
    )
    assert response.status_code == 422
    assert response.json["error"] == "unsupported_task_type"


def test_task_service_marks_failed_on_handler_error(monkeypatch):
    raw_client(monkeypatch)
    task = tasks_service.create_task(
        "f2_match", "guest:test-owner",
        payload={"major_code": "080901"},
        idempotency_key="fail-1",
        total_steps=3,
    )
    task_id = task["id"]

    def boom(_step, _payload, _result):
        raise RuntimeError("handler exploded")

    task_after, status = tasks_service.advance_task(task_id, "guest:test-owner", boom)
    assert status == "failed"
    assert task_after["state"] == "failed"
    assert task_after["error_code"] == "task_failed"
    assert "exploded" in task_after["error_message"]

    wrong_owner, wrong_status = tasks_service.advance_task(task_id, "guest:other", boom)
    assert wrong_status == "forbidden"
