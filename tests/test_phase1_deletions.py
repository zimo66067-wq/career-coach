# -*- coding: utf-8 -*-
"""Phase 1 deletion contract: the major-based match capability must stay gone.

D1 removed the 专业→职业 matching surface (catalog search, intent ranking and
mode A/B matching) together with the asynchronous chunked-task subsystem that
existed only to drive it.  These tests pin that deletion down so a later change
cannot quietly re-expose a route, a table or a page that no longer has a product
reason to exist.
"""
import json
import os
from pathlib import Path

import pytest

import api.index as api_module

ROOT = Path(__file__).resolve().parents[1]

# Every endpoint that belonged to the retired capability.  They must not answer.
RETIRED_API_PATHS = [
    "/api/f2/health",
    "/api/f2/majors/tree",
    "/api/f2/majors/search",
    "/api/f2/majors/080901",
    "/api/f2/match",
    "/api/f2/intent",
    "/api/tasks",
    "/api/tasks/any-id",
    "/api/tasks/any-id/next",
    "/api/f2_major",
]

# Every file that carried the capability and must no longer ship in any tree.
RETIRED_FILES = [
    "api/f2_major.py",
    "services/task_service.py",
    "tools/tasks.py",
    "data/f2/majors_2025.json",
    "data/f2/profiles_top30.json",
    "scripts/build_majors_data.py",
    "scripts/validate_f2_data.py",
]
RETIRED_TREES = ["public", "docs", "ui/prototype"]
RETIRED_TREE_FILES = ["pages/f2-match.html", "css/f2-major.css", "js/f2-major.js"]


@pytest.fixture()
def client():
    api_module.app.config["TESTING"] = True
    return api_module.app.test_client()


def test_retired_endpoints_return_404(client):
    client.post("/api/wf01/consent", json={"accepted": True})
    for path in RETIRED_API_PATHS:
        response = client.get(path)
        assert response.status_code == 404, "%s must be gone, got %s" % (path, response.status_code)


def test_retired_endpoints_are_not_advertised_as_options(client):
    """A retired route must not answer the CORS preflight either."""
    for path in RETIRED_API_PATHS:
        response = client.options(path)
        assert response.status_code == 404, "%s preflight must 404" % path


def test_capability_map_no_longer_advertises_major_match(client):
    body = client.get("/api/health").json
    assert "f2_major" not in body["workflows"]


def test_retired_files_are_absent():
    for relative in RETIRED_FILES:
        assert not (ROOT / relative).exists(), "%s must be deleted" % relative
    for tree in RETIRED_TREES:
        for relative in RETIRED_TREE_FILES:
            assert not (ROOT / tree / relative).exists(), "%s/%s must be deleted" % (tree, relative)
    assert not (ROOT / "data" / "f2").exists(), "data/f2 directory must be deleted"


def test_module_no_longer_imports_the_retired_capability():
    source = (ROOT / "api" / "index.py").read_text(encoding="utf-8")
    assert "f2_major" not in source
    assert "task_service" not in source
    assert "tools.tasks" not in source


def test_vercel_rewrites_do_not_reference_retired_routes():
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    sources = [item["source"] for item in config["rewrites"]]
    destinations = [item["destination"] for item in config["rewrites"]]
    for item in sources + destinations:
        lowered = item.lower()
        assert "f2_major" not in lowered, item
        assert "/api/f2/" not in lowered, item
        assert "/api/tasks" not in lowered, item


def test_retired_table_is_dropped_from_schema():
    source = (ROOT / "tools" / "database.py").read_text(encoding="utf-8")
    assert '("tasks",)' in source, "tasks must be listed as a retired table"
    assert "CREATE TABLE IF NOT EXISTS tasks" not in source
    # And it must not be reachable through the owner-transfer path either.
    assert '("session_owners", "applications", "tasks")' not in source


def test_retired_table_is_absent_after_init(client):
    from tools import database

    database.init_db()
    conn = database._get_conn()
    try:
        names = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        conn.close()
    assert "tasks" not in names


def test_target_job_match_still_works(monkeypatch):
    """Positive control: the kept JD-matching path must be unaffected."""
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "test-consent-secret")
    api_module.app.config["TESTING"] = True
    raw = api_module.app.test_client()
    consent = raw.post("/api/wf01/consent", json={"accepted": True})
    assert consent.status_code == 200
    headers = {
        "X-Consent-Token": consent.json["consent_token"],
        "X-Guest-Token": consent.json.get("guest_token", ""),
    }
    jd = (
        "岗位职责：负责订单中心接口开发与维护。\n"
        "任职要求：熟悉 Python 与 Flask，了解 SQL 查询优化，具备项目交付经验。"
    )
    parsed = raw.post("/api/wf03/jd", json={"jdText": jd}, headers=headers)
    assert parsed.status_code == 200
    profile = parsed.json["jobProfile"]
    profile["user_confirmed"] = True
    resume = (
        "项目经历：负责订单接口开发并完成上线验证，熟悉 Python 与 Flask，"
        "通过 SQL 查询优化将响应时间从 800ms 降至 220ms，具备完整项目交付经验。"
    )
    matched = raw.post(
        "/api/wf03/match",
        json={"resumeText": resume, "jobProfile": profile},
        headers=headers,
    )
    assert matched.status_code == 200
    body = matched.json
    assert isinstance(body["score_M"], int)
    assert body["requirements"]
    assert body["match_mode"] == "rule_bm25"


def test_publish_trees_remain_byte_identical():
    """Removing the page must not introduce mirror drift."""
    pairs = [
        "index.html",
        "js/quick-demo.js",
        "js/data-bridge.js",
        "js/account.js",
        "pages/f1-resume.html",
        "pages/f3-interview.html",
        "pages/f4-report.html",
        "pages/f5-apply.html",
        "pages/kb.html",
        "pages/states.html",
    ]
    for relative in pairs:
        public = (ROOT / "public" / relative).read_bytes()
        docs = (ROOT / "docs" / relative).read_bytes()
        assert public == docs, "publish mirror differs: %s" % relative


def test_publish_trees_do_not_reference_the_retired_page():
    for tree in RETIRED_TREES:
        for path in (ROOT / tree).rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".html", ".js"}:
                continue
            body = path.read_text(encoding="utf-8", errors="ignore")
            for needle in ("f2-match.html", "f2-major.js", "matchMajor", "quickDemoF2"):
                assert needle not in body, "%s still references %s" % (path, needle)
