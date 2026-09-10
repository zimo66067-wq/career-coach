"""Contracts for the unified F2 routes and session persistence."""
import json
from pathlib import Path

import api.index as api_module
from api import f2_major
from tools.database import load_match


RESUME = "教育背景：计算机科学本科。项目经历：使用 Python 和 Flask 完成订单接口，并将延迟降低百分之五十。"
JD = "岗位职责：负责后端接口开发。任职要求：本科，熟悉 Python、Flask 和 SQL。有性能优化经验优先。"


def _client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RESUME_DB_PATH", str(tmp_path / "f2.db"))
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "f2-route-test-secret")
    api_module.app.config.update(TESTING=True)
    return api_module.app.test_client()


def _consent(client):
    response = client.post("/api/wf01/consent", json={"accepted": True})
    assert response.status_code == 200
    return {
        "X-Consent-Token": response.json["consent_token"],
        "X-Guest-Token": response.json["guest_token"],
    }


def test_f2_catalog_routes_are_served_by_main_api(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    health = client.get("/api/f2/health")
    tree = client.get("/api/f2/majors/tree")
    search = client.get("/api/f2/majors/search?q=计算机&limit=5")
    detail = client.get("/api/f2/majors/080901")
    intent = client.get("/api/f2/intent?q=程序员")

    assert health.status_code == 200
    assert health.json["majors"] == 845
    assert health.json["profiles"] == 30
    assert tree.status_code == 200 and tree.json["categories"]
    assert search.status_code == 200 and search.json["items"]
    assert detail.status_code == 200 and detail.json["major"]["code"] == "080901"
    assert intent.status_code == 200 and intent.json["items"]


def test_f2_preflight_and_invalid_search_limit_are_bounded(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    preflight = client.options(
        "/api/f2/match",
        headers={
            "Origin": "https://zimo66067-wq.github.io",
            "Access-Control-Request-Method": "POST",
        },
    )
    invalid = client.get("/api/f2/majors/search?q=计算机&limit=oops")

    assert preflight.status_code == 204
    assert preflight.headers["Access-Control-Allow-Origin"] == "https://zimo66067-wq.github.io"
    assert invalid.status_code == 422
    assert invalid.json["error"] == "invalid_limit"


def test_legacy_f2_serverless_path_cannot_bypass_unified_middleware():
    with f2_major.app.test_request_context(
        "/api/f2_major?_route=match",
        method="POST",
        json={"majorCode": "080901", "resumeText": RESUME},
    ):
        legacy = f2_major.route_api()
        assert legacy.status_code == 404


def test_vercel_rewrites_f2_routes_to_the_unified_api():
    config = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
    routes = {item["source"]: item["destination"] for item in config["rewrites"]}
    assert routes["/api/f2_major"] == "/api?_route=retired/f2-major"
    assert routes["/api/f2/health"] == "/api?_route=f2/health"
    assert routes["/api/f2/majors/tree"] == "/api?_route=f2/majors/tree"
    assert routes["/api/f2/majors/search"] == "/api?_route=f2/majors/search"
    assert routes["/api/f2/majors/(.*)"] == "/api?_route=f2/majors/$1"
    assert routes["/api/f2/match"] == "/api?_route=f2/match"
    assert routes["/api/f2/intent"] == "/api?_route=f2/intent"


def test_f2_direct_match_persists_score_for_f4(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    headers = _consent(client)
    sid = "f2_direct_session"
    response = client.post(
        "/api/f2/match",
        json={"majorCode": "080901", "resumeText": RESUME, "jdText": "", "session_id": sid},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json["mode"] == "A"
    assert response.json["session_id"] == sid
    stored = load_match(sid)
    assert stored["score_M"] == response.json["scores"]["overall"]


def test_f2_mode_b_persists_the_common_f4_contract(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    headers = _consent(client)
    sid = "f2_mode_b_session"
    response = client.post(
        "/api/f2/match",
        json={"majorCode": "080901", "resumeText": RESUME, "jdText": JD, "session_id": sid},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json["mode"] == "B"
    assert response.json["requirements"]
    assert response.json["subscores"]
    assert {row["type"] for row in response.json["requirements"]} <= {
        "hard", "responsibility", "preferred", "terminology"
    }
    assert set(response.json["subscores"]) <= {
        "hard", "responsibility", "preferred", "terminology"
    }
    assert "term" in response.json["modeB"]["subscores"]
    stored = load_match(sid)
    assert stored["requirements"] == response.json["requirements"]
    assert stored["subscores"] == response.json["subscores"]
    assert stored["gaps"] == response.json["gaps"]


def test_f2_chunked_match_persists_and_is_owner_isolated(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    owner = _consent(client)
    sid = "f2_task_session"
    created = client.post(
        "/api/tasks",
        json={
            "task_type": "f2_match",
            "payload": {
                "major_code": "080901",
                "resume_text": RESUME,
                "jd_text": JD,
                "session_id": sid,
            },
        },
        headers=owner,
    )
    assert created.status_code == 201
    task = created.json["task"]
    for _ in range(20):
        advanced = client.post(f"/api/tasks/{task['id']}/next", json={}, headers=owner)
        assert advanced.status_code == 200
        task = advanced.json["task"]
        if task["state"] == "done":
            break
    assert task["state"] == "done"
    report = task["result_json"]["__result"]
    assert report["session_id"] == sid
    stored = load_match(sid)
    assert stored["score_M"] == report["scores"]["overall"]
    assert stored["requirements"] == report["requirements"]
    assert stored["subscores"] == report["subscores"]
    assert {row["type"] for row in stored["requirements"]} <= {
        "hard", "responsibility", "preferred", "terminology"
    }

    attacker = _consent(client)
    blocked = client.post(
        "/api/f2/match",
        json={"majorCode": "080901", "resumeText": RESUME, "jdText": "", "session_id": sid},
        headers=attacker,
    )
    assert blocked.status_code == 404
