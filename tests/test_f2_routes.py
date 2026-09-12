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


def test_f2_search_tolerates_typo_and_explains_the_match(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/f2/majors/search", query_string={"q": "计算机科学与技木"})

    assert response.status_code == 200
    assert response.json["items"][0]["code"] == "080901"
    assert response.json["items"][0]["match_type"] == "name_fuzzy"
    assert response.json["items"][0]["match_reason"] == "专业名称近似"
    assert response.json["items"][0]["match_score"] >= 80


def test_f2_search_understands_job_intent_in_a_sentence(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/f2/majors/search", query_string={"q": "我想做程序员"})

    assert response.status_code == 200
    assert [item["code"] for item in response.json["items"][:2]] == ["080901", "080902"]
    assert all(item["match_type"] == "intent" for item in response.json["items"][:2])
    assert all(item["match_reason"] == "求职意向相关" for item in response.json["items"][:2])

    niche = client.get("/api/f2/majors/search", query_string={"q": "我想做芯片设计"})
    assert niche.status_code == 200
    assert niche.json["items"][0]["code"] == "080710"

    energy = client.get("/api/f2/majors/search", query_string={"q": "新能源电池研发"})
    assert energy.status_code == 200
    assert energy.json["items"][0]["code"] in {"080503", "080414", "080504"}


def test_f2_search_supports_explicit_short_major_aliases(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    computer = client.get("/api/f2/majors/search", query_string={"q": "计科"})
    software = client.get("/api/f2/majors/search", query_string={"q": "软工"})

    assert computer.json["items"][0]["code"] == "080901"
    assert software.json["items"][0]["code"] == "080902"
    assert computer.json["items"][0]["match_type"] == "alias_exact"
    assert software.json["items"][0]["match_reason"] == "专业简称匹配"


def test_f2_search_does_not_treat_embedded_words_as_job_intent(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    invoice = client.get("/api/f2/majors/search", query_string={"q": "开发票"})
    feeling = client.get("/api/f2/majors/search", query_string={"q": "安全感"})

    assert invoice.status_code == 200 and invoice.json["items"] == []
    assert feeling.status_code == 200 and feeling.json["items"] == []


def test_f2_long_search_skips_quadratic_fuzzy_distance(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("long queries must not enter edit-distance matching")

    monkeypatch.setattr(f2_major, "damerau_levenshtein", fail_if_called)
    result = f2_major.search_majors("这是一个用于验证搜索成本有界的超长自然语言查询" * 2)
    assert isinstance(result, list)


def test_f2_search_normalizes_full_width_code_and_spacing(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/f2/majors/search", query_string={"q": "０８０９ ０１"})

    assert response.status_code == 200
    assert response.json["items"][0]["code"] == "080901"
    assert response.json["items"][0]["match_type"] == "code_exact"


def test_f2_search_rejects_oversized_queries_and_treats_input_as_text(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    oversized = client.get("/api/f2/majors/search", query_string={"q": "计" * 65})
    literal = client.get("/api/f2/majors/search", query_string={"q": ".*(计算机)[a-z]+"})

    assert oversized.status_code == 422
    assert oversized.json["error"] == "query_too_long"
    assert literal.status_code == 200
    assert isinstance(literal.json["items"], list)


def test_f2_total_counts_candidates_before_the_limit(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/f2/majors/search", query_string={"q": "计算机", "limit": 1})

    assert response.status_code == 200
    body = response.json
    assert len(body["items"]) == 1
    assert body["total"] > len(body["items"]), "total 必须是截断前的候选数"


def test_f2_intent_total_is_the_pre_limit_candidate_count(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/f2/intent", query_string={"q": "计算机"})

    assert response.status_code == 200
    body = response.json
    assert body["items"]
    assert body["total"] > len(body["items"])


def test_f2_two_character_queries_use_explicit_aliases_only(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    computer = client.get("/api/f2/majors/search", query_string={"q": "计科"})
    assert [item["code"] for item in computer.json["items"]] == ["080901"]

    electronics = client.get("/api/f2/majors/search", query_string={"q": "电科"})
    assert electronics.json["items"][0]["code"] == "080702"

    media = client.get("/api/f2/majors/search", query_string={"q": "数媒"})
    media_codes = [item["code"] for item in media.json["items"]]
    assert media_codes[0] == "080906"
    assert "130508" in media_codes


def test_f2_two_character_queries_keep_prefix_recall_without_cross_word_noise(
    tmp_path, monkeypatch
):
    client = _client(tmp_path, monkeypatch)

    # 前缀命中必须保留（「数学」→「数学与应用数学」）
    math = client.get("/api/f2/majors/search", query_string={"q": "数学"})
    assert math.json["items"][0]["code"] == "070101"

    # 「计科」不得再跨词命中「材料设计科学与工程」(080415)
    computer = client.get("/api/f2/majors/search", query_string={"q": "计科"})
    codes = [item["code"] for item in computer.json["items"]]
    assert "080415" not in codes


def test_f2_search_tolerates_typos_and_intent_without_false_positives(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    positives = {
        "计算机科学与技术": "080901",
        "软件工成": "080902",
        "软件程工": "080902",
        "会际学": "120203",
        "想从事财务审计": "120203",
    }
    for query, expected in positives.items():
        response = client.get("/api/f2/majors/search", query_string={"q": query})
        assert response.status_code == 200, query
        assert response.json["items"], query
        assert response.json["items"][0]["code"] == expected, query

    negatives = (
        "我想开发票",
        "我需要安全感",
        "<script>alert(1)</script>",
        "'; DROP TABLE majors;--",
    )
    for query in negatives:
        response = client.get("/api/f2/majors/search", query_string={"q": query})
        assert response.status_code == 200, query
        assert response.json["items"] == [], query


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
