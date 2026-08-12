# -*- coding: utf-8 -*-
"""Phase-0 account system tests: register/login/me/history isolation."""
import os

import pytest

import api.index as api_module
from tools import account as account_module
from tools.database import get_resume_detail, save_resume


@pytest.fixture(autouse=True)
def _fresh_account_db(tmp_path, monkeypatch):
    """每个账号测试使用独立的临时数据库，避免会话级 DB 残留数据。"""
    db_file = tmp_path / "account_test.db"
    monkeypatch.setenv("RESUME_DB_PATH", str(db_file))
    from tools import database
    database.init_db()
    account_module._RATE_BUCKETS.clear()
    yield
    account_module._RATE_BUCKETS.clear()


def raw_client(monkeypatch):
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "test-consent-secret")
    monkeypatch.delenv("DUMATE_CONSENT_MAX_AGE_SECONDS", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    api_module.app.config.update(TESTING=True)
    return api_module.app.test_client()


def register(client, phone="13800000001", email="alice@example.com",
             password="pass1234", name="小张"):
    return client.post(
        "/api/auth/register",
        json={
            "phone": phone,
            "email": email,
            "password": password,
            "name": name,
        },
    )


def test_register_login_me_logout_flow(monkeypatch):
    client = raw_client(monkeypatch)
    resp = register(client)
    assert resp.status_code == 201
    user = resp.json
    assert user["name"] == "小张"
    assert user["role"] == "user"
    assert "password" not in json_dump(resp)
    assert "zy_session" in resp.headers.get("Set-Cookie", "")

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json["logged_in"] is True
    assert me.json["user"]["email"] == "alice@example.com"

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    me2 = client.get("/api/auth/me")
    assert me2.json["logged_in"] is False

    # 登出后再次登录必须成功（回归：旧原型登出即删号）
    login = client.post(
        "/api/auth/login",
        json={"account": "alice@example.com", "password": "pass1234"},
    )
    assert login.status_code == 200
    assert login.json["name"] == "小张"


def json_dump(response):
    import json
    return json.dumps(response.json, ensure_ascii=False)


def test_duplicate_phone_and_email_rejected(monkeypatch):
    client = raw_client(monkeypatch)
    assert register(client).status_code == 201
    resp = register(client, phone="13800000001", email="bob@example.com")
    assert resp.status_code == 409
    assert resp.json["error"] == "phone_taken"
    resp = register(client, phone="13800000002", email="alice@example.com")
    assert resp.status_code == 409
    assert resp.json["error"] == "email_taken"


def test_validation_and_bad_credentials(monkeypatch):
    client = raw_client(monkeypatch)
    cases = [
        {"phone": "123", "email": "a@b.com", "password": "pass1234", "name": "小张"},
        {"phone": "13800000003", "email": "bad", "password": "pass1234", "name": "小张"},
        {"phone": "13800000003", "email": "a@b.com", "password": "short", "name": "小张"},
        {"phone": "13800000003", "email": "a@b.com", "password": "password", "name": "小张"},
        {"phone": "13800000003", "email": "a@b.com", "password": "pass1234", "name": "x"},
    ]
    for payload in cases:
        resp = client.post("/api/auth/register", json=payload)
        assert resp.status_code == 422, payload

    assert register(client).status_code == 201
    bad = client.post(
        "/api/auth/login", json={"account": "alice@example.com", "password": "wrong123"}
    )
    assert bad.status_code == 401


def test_history_requires_login_and_is_isolated(monkeypatch):
    alice = raw_client(monkeypatch)
    assert alice.get("/api/history").status_code == 401
    assert alice.post("/api/history", json={}).status_code == 401

    assert register(alice).status_code == 201
    created = alice.post(
        "/api/history",
        json={
            "session_id": "sess-alice-1",
            "event_type": "F2",
            "title": "岗位匹配 · M82",
            "status": "done",
        },
    )
    assert created.status_code == 201
    event_id = created.json["id"]

    items = alice.get("/api/history").json["items"]
    assert len(items) == 1
    assert items[0]["title"] == "岗位匹配 · M82"

    # 第二个用户看不到、删不掉第一个用户的历史
    bob = raw_client(monkeypatch)
    assert register(
        bob, phone="13800000004", email="bob@example.com", name="小张"
    ).status_code == 201
    assert bob.get("/api/history").json["total"] == 0
    assert bob.delete("/api/history/%s" % event_id).status_code == 404

    # 删除本人历史，且级联删除会话数据
    save_resume(
        session_id="sess-alice-1",
        client_ip="",
        user_agent="",
        filename="a.txt",
        file_type="txt",
        file_size=10,
        resume_text="deleted",
    )
    assert get_resume_detail("sess-alice-1") is not None
    deleted = alice.delete("/api/history/%s" % event_id)
    assert deleted.status_code == 200
    assert get_resume_detail("sess-alice-1") is None
    assert alice.get("/api/history").json["total"] == 0


def test_rate_limit_register(monkeypatch):
    client = raw_client(monkeypatch)
    for i in range(5):
        resp = register(client, phone="138%08d" % (10000000 + i),
                        email="u%d@example.com" % i)
        assert resp.status_code == 201
    resp = register(client, phone="13899999999", email="u5@example.com")
    assert resp.status_code == 429


def test_admin_demo_only_with_dev_demo_flag(monkeypatch):
    monkeypatch.setenv("DEV_DEMO", "1")
    client = raw_client(monkeypatch)
    assert register(client).status_code == 201
    # 普通用户不注入演示数据
    assert client.get("/api/history").json["total"] == 0

    from tools.database import create_user
    create_user("13900000001", "admin@example.com",
                account_module.hash_password("admin1234"), "管理员", role="admin")
    login = client.post(
        "/api/auth/login",
        json={"account": "admin@example.com", "password": "admin1234"},
    )
    assert login.status_code == 200
    items = client.get("/api/history").json["items"]
    assert len(items) >= 6
    assert items[0]["id"] < 0
