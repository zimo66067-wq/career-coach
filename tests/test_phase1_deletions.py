# -*- coding: utf-8 -*-
"""Phase 1 deletion contract: everything Phase 1 removed must stay gone.

D1 removed the 专业→职业 matching surface (catalog search, intent ranking and
mode A/B matching) together with the asynchronous chunked-task subsystem that
existed only to drive it.  The rest of Phase 1 then removed the C7 predictive
scoring, the standalone knowledge-base product, the whole voice/ASR chain and
four dead routes.  These tests pin that down so a later change cannot quietly
re-expose a route, a table, a page or a metric that no longer has a product
reason to exist.
"""
import json
import os
import re
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
RETIRED_TREES = ["public", "docs"]
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


def test_the_legacy_prototype_tree_is_gone():
    """Phase 6a: `ui/` was a third front-end copy (stale fork + duplicate assets).

    It had 7 broken references, was deployed nowhere, and nothing at runtime
    referenced it. `public/` is the only canonical tree now, so the whole
    directory must stay gone — not just the files retired in Phase 1.
    """
    assert not (ROOT / "ui").exists(), "ui/ must not be resurrected: public/ is the only front-end tree"


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
        "js/radar.js",
        "js/mock-data.js",
        "pages/f1-resume.html",
        "pages/f3-interview.html",
        "pages/f4-report.html",
        "pages/f5-apply.html",
        "pages/states.html",
        "assets/favicon.svg",
        "assets/logo.svg",
        "assets/vendor/echarts.min.js",
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
            for needle in ("f2-match.html", "f2-major.js", "matchMajor", "quickDemoF2",
                           "kb.html", "kb.js", "voice.js", "VoiceHandler",
                           "scenario_day7", "C7_low", "C7_high"):
                assert needle not in body, "%s still references %s" % (path, needle)


# ------------------------------------------------------------------ #
# Phase 1 其余删除项（2026-09-13）
# ------------------------------------------------------------------ #

RETIRED_PHASE1B_FILES = [
    "public/pages/kb.html", "public/js/kb.js",
    "docs/pages/kb.html", "docs/js/kb.js",
    "ui/prototype/pages/kb.html", "ui/prototype/js/kb.js",
    "public/js/voice.js", "docs/js/voice.js", "ui/prototype/js/voice.js",
    "tools/voice_handler.py", "tools/providers/asr.py",
    "scripts/p0-04-voice-validation.py",
    "public/voice-test-checklist.md", "docs/voice-test-checklist.md",
    "tests/test_new_tools.py", "tests/test_voice_browser.py",
    "tests/e2e_closed_loop_results.json",
]


def test_phase1b_retired_files_are_absent():
    for relative in RETIRED_PHASE1B_FILES:
        assert not (ROOT / relative).exists(), "%s must be deleted" % relative


def test_retired_endpoints_for_phase1b_return_404(client):
    client.post("/api/wf01/consent", json={"accepted": True})
    for path in ("/api/knowledge/search", "/api/knowledge/questions", "/api/wf04/asr"):
        assert client.get(path).status_code == 404, path
        assert client.options(path).status_code == 404, path + " (preflight)"


def test_c7_predictive_output_is_gone(client):
    """C7 预测区间不得以任何形式回流：复算器、响应、合同、前端。"""
    import rescore

    fixture = json.loads(
        (ROOT / "tests" / "fixtures-synthetic" / "abilities" / "score-input-01.json")
        .read_text(encoding="utf-8")
    )
    result = rescore.compute(fixture)
    assert "C0" in result
    for banned in ("C7_low", "C7_high"):
        assert banned not in result, "rescore must not emit %s" % banned

    schema = json.loads((ROOT / "contracts" / "ability-profile.schema.json").read_text(encoding="utf-8"))
    assert "scenario_day7" not in schema["properties"]
    assert "scenario_day7" not in schema["required"]

    scoring = (ROOT / "contracts" / "scoring.md").read_text(encoding="utf-8")
    # 合同里不得再出现 C7 的**公式定义**；只允许出现「已删除」的说明性提及。
    for formula in ("C7_low  = min(100", "C7_high = min(100", "可提升空间 = 100"):
        assert formula not in scoring, "scoring.md still defines %r" % formula
    assert "删除" in scoring, "scoring.md must state that the C0 extrapolation was retired"


def test_radar_option_has_no_predictive_series():
    from radar_adapter import build_option

    ability = json.loads(
        (ROOT / "tests" / "fixtures-synthetic" / "abilities" / "ability-01.json")
        .read_text(encoding="utf-8")
    )
    option = build_option(ability)
    assert len(option["series"][0]["data"]) == 1
    assert option["series"][0]["data"][0]["name"] == "当前证据快照"
    blob = json.dumps(option, ensure_ascii=False)
    for banned in ("七天推演", "C7", "scenario"):
        assert banned not in blob


def test_assets_rewrite_targets_the_deployed_tree():
    """favicon / 本地 ECharts 必须落在真正部署的 public 树里。"""
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    rules = {item["source"]: item["destination"] for item in config["rewrites"]}
    assert rules.get("/assets/:path*") == "/public/assets/:path*"
    assert "ui/assets" not in json.dumps(config)
    for relative in ("public/assets/favicon.svg", "public/assets/logo.svg",
                     "public/assets/vendor/echarts.min.js"):
        assert (ROOT / relative).is_file(), relative


def test_no_dead_routes_in_vercel_config():
    """每条 static 重写的目标都必须存在；每条 _route 都必须有处理器。"""
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    index_source = (ROOT / "api" / "index.py").read_text(encoding="utf-8")

    for rule in config["rewrites"]:
        destination = rule["destination"]
        if "?" in destination:
            match = re.match(r"^/api\?_route=([^&]+)$", destination)
            assert match, "unexpected api rewrite: %s" % destination
            route = match.group(1).replace("/$1", "")
            assert not route.startswith("retired/"), "retired shim left: %s" % rule["source"]
            assert route in index_source, "no handler for %s" % route
        elif destination.endswith(".html"):
            assert (ROOT / destination.lstrip("/")).is_file(), destination


def test_user_navigation_has_no_retired_entries():
    """导航不得再出现已下线能力，也不得超过 DoD 的 4 项上限 + 首页。"""
    html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
    labels = re.findall(r'class="nav"[^>]*>([^<]*)<', html)
    assert labels == ["首页", "F1 简历诊断", "F3 模拟面试", "F4 能力报告", "F5 投递"], labels
    for banned in ("面经知识库", "岗位匹配", "知识库"):
        assert banned not in " ".join(labels), banned
