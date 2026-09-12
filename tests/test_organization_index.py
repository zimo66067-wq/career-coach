# -*- coding: utf-8 -*-
"""F5 单位/职位索引：阶段 1 基础框架契约。

阶段 1 的验收要求是「无外部 API 时不伪造数据」。这些测试锁定：

- 索引表存在且初始为空，且只在获得授权的数据源写入后才会有内容；
- 未配置数据源时 API 返回明确的 unconfigured 状态，而不是裸空列表或编造结果；
- 缺少来源/核验元数据的结果既不能写入索引，也不能对外返回；
- provider 契约、失败的 provider 选择与职位版本去重行为。
"""
import json
from pathlib import Path

import api.index as api_module
from services import organization_service as org_service
from tools import database
from tools.providers import organization as org_provider

FIXTURE_ORG = {
    "source_provider": "fixture-licensed-source",
    "source_key": "ORG-0001",
    "canonical_name": "示例海洋遥感研究院（厦门）",
    "org_type": "research_institute",
    "region": "福建/厦门",
    "industry": "海洋遥感",
    "status": "active",
    "website": "https://example.test",
    "source_url": "https://example.test/org/0001",
    "source_updated_at": "2026-09-01T00:00:00Z",
    "verified_at": "2026-09-02T00:00:00Z",
    "verification_state": "verified",
    "aliases": [
        {"alias": "示例海遥"},
        {"alias": "厦门海洋遥感研究院"},
    ],
}


def _client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ORG_DATA_PROVIDER", raising=False)
    monkeypatch.setenv("RESUME_DB_PATH", str(tmp_path / "f5org.db"))
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "f5-org-test-secret")
    api_module.app.config.update(TESTING=True)
    return api_module.app.test_client()


def _consent(client):
    response = client.post("/api/wf01/consent", json={"accepted": True})
    assert response.status_code == 200
    return {
        "X-Consent-Token": response.json["consent_token"],
        "X-Guest-Token": response.json["guest_token"],
    }


# ---------------------------------------------------------------- #
# 索引层
# ---------------------------------------------------------------- #

def test_index_tables_exist_and_start_empty(tmp_path, monkeypatch):
    _client(tmp_path, monkeypatch)

    counts = database.index_counts()

    assert counts == {
        "organizations": 0,
        "organization_aliases": 0,
        "organization_profiles": 0,
        "source_snapshots": 0,
        "job_postings": 0,
        "job_posting_versions": 0,
        "job_embeddings": 0,
    }


def test_normalized_lookup_finds_canonical_name_and_alias(tmp_path, monkeypatch):
    _client(tmp_path, monkeypatch)
    stored = database.upsert_organization(FIXTURE_ORG, aliases=FIXTURE_ORG["aliases"])
    assert stored is not None

    by_alias = database.find_organizations_by_name("示例海遥")
    by_full_width = database.find_organizations_by_name("示例海洋遥感研究院（厦门）")
    by_spacing = database.find_organizations_by_name("  示例海遥  ")

    assert [row["id"] for row in by_alias] == [stored["id"]]
    assert [row["id"] for row in by_full_width] == [stored["id"]]
    assert [row["id"] for row in by_spacing] == [stored["id"]]

    # 阶段 1 只做精确匹配；模糊/拼音召回属于阶段 2，不应在这里发生
    assert database.find_organizations_by_name("示例海瑶") == []


def test_organization_upsert_is_idempotent_per_source_key(tmp_path, monkeypatch):
    _client(tmp_path, monkeypatch)
    database.upsert_organization(FIXTURE_ORG, aliases=FIXTURE_ORG["aliases"])
    updated = dict(FIXTURE_ORG, canonical_name="示例海洋遥感研究院", org_type="institute")
    database.upsert_organization(updated, aliases=FIXTURE_ORG["aliases"])

    counts = database.index_counts()
    rows = database.find_organizations_by_name("示例海遥")

    assert counts["organizations"] == 1, "同一 (provider, source_key) 不应重复入库"
    assert counts["organization_aliases"] == 2, "别名必须按组织整体替换"
    assert rows[0]["canonical_name"] == "示例海洋遥感研究院"


def test_job_posting_versions_only_grow_when_content_changes(tmp_path, monkeypatch):
    _client(tmp_path, monkeypatch)
    org = database.upsert_organization(FIXTURE_ORG, aliases=[])

    base = {
        "source_provider": FIXTURE_ORG["source_provider"],
        "external_job_id": "JOB-1",
        "title": "海洋遥感算法工程师",
        "organization_id": org["id"],
        "skill_tags": ["Python", "遥感"],
        "status": "open",
    }
    database.upsert_job_posting(base)
    assert database.index_counts()["job_posting_versions"] == 1

    database.upsert_job_posting(base)
    assert database.index_counts()["job_posting_versions"] == 1, "内容未变不应追加版本"

    database.upsert_job_posting(dict(base, title="高级海洋遥感算法工程师"))
    assert database.index_counts()["job_posting_versions"] == 2

    titles = [row["title"] for row in database.list_job_postings(org["id"])]
    assert titles == ["高级海洋遥感算法工程师"]


# ---------------------------------------------------------------- #
# provider 契约
# ---------------------------------------------------------------- #

def test_unconfigured_provider_is_the_default(monkeypatch):
    monkeypatch.delenv("ORG_DATA_PROVIDER", raising=False)

    provider = org_provider.build_organization_provider()

    assert isinstance(provider, org_provider.UnconfiguredOrganizationProvider)
    assert provider.is_configured() is False
    assert provider.search_organizations("任何单位") == []
    assert provider.search_jobs("ORG-0001") == []


def test_unknown_or_unlicensed_provider_falls_back_to_unconfigured(monkeypatch):
    monkeypatch.setenv("ORG_DATA_PROVIDER", "no-such-provider")
    assert org_provider.build_organization_provider().name == "unconfigured"

    class UnlicensedProvider(org_provider.BaseOrganizationProvider):
        name = "registered-but-unlicensed"

        def is_configured(self):
            return False

    monkeypatch.setitem(org_provider.PROVIDER_REGISTRY, "registered-but-unlicensed", UnlicensedProvider)
    monkeypatch.setenv("ORG_DATA_PROVIDER", "registered-but-unlicensed")
    assert org_provider.build_organization_provider().name == "unconfigured"


def test_results_without_provenance_are_dropped():
    complete = dict(FIXTURE_ORG)

    assert org_provider.eligible_results([complete]) == [complete]
    for field in org_provider.RESULT_REQUIRED_FIELDS:
        incomplete = dict(complete)
        incomplete.pop(field)
        assert org_provider.eligible_results([incomplete]) == [], field
    assert org_provider.eligible_results([dict(complete, verification_state="made_up")]) == []
    assert org_provider.eligible_results(["not-a-dict"]) == []


def test_ingest_refuses_records_without_provenance(tmp_path, monkeypatch):
    _client(tmp_path, monkeypatch)

    stored = org_service.ingest_organizations([
        {"source_key": "X1", "canonical_name": "无来源单位"},
        dict(FIXTURE_ORG, source_url=""),
    ])

    assert stored == []
    assert database.index_counts()["organizations"] == 0, "无来源记录绝不能落库"


def test_ingest_stores_licensed_records(tmp_path, monkeypatch):
    _client(tmp_path, monkeypatch)

    stored = org_service.ingest_organizations([FIXTURE_ORG])

    assert len(stored) == 1
    assert database.index_counts()["organizations"] == 1
    assert database.index_counts()["organization_aliases"] == 2


# ---------------------------------------------------------------- #
# API 合同：未配置时必须显式降级
# ---------------------------------------------------------------- #

def test_status_endpoint_reports_unconfigured_and_pending_decisions(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/f5/organizations/status")

    assert response.status_code == 200
    body = response.json
    assert body["status"] == "unconfigured"
    assert body["configured"] is False
    assert body["provider"] == "unconfigured"
    assert set(body["index"]) == {
        "organizations", "organization_aliases", "organization_profiles",
        "source_snapshots", "job_postings", "job_posting_versions", "job_embeddings",
    }
    assert all(value == 0 for value in body["index"].values())
    assert len(body["pending_decisions"]) == 5


def test_suggest_reports_unconfigured_instead_of_an_empty_result_set(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/f5/organizations/suggest", query_string={"q": "厦门海洋遥感研究院"})

    assert response.status_code == 200
    body = response.json
    assert body["status"] == "unconfigured"
    assert body["configured"] is False
    assert body["items"] == []
    assert body["total"] == 0
    assert "不提供单位搜索结果" in body["notice"]
    assert "不会生成任何单位信息" in body["notice"]
    assert len(body["pending_decisions"]) == 5


def test_suggest_never_returns_rows_even_when_the_index_has_data(tmp_path, monkeypatch):
    """未配置数据源时，即使索引里有人为写入的行，也不得对外返回。"""
    client = _client(tmp_path, monkeypatch)
    database.upsert_organization(FIXTURE_ORG, aliases=FIXTURE_ORG["aliases"])

    response = client.get("/api/f5/organizations/suggest", query_string={"q": "示例海遥"})

    assert response.status_code == 200
    assert response.json["status"] == "unconfigured"
    assert response.json["items"] == []


def test_suggest_bounds_query_and_limit(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    too_long = client.get("/api/f5/organizations/suggest", query_string={"q": "单" * 65})
    bad_limit = client.get("/api/f5/organizations/suggest", query_string={"q": "示例", "limit": "oops"})
    empty = client.get("/api/f5/organizations/suggest", query_string={"q": "  "})

    assert too_long.status_code == 422 and too_long.json["error"] == "query_too_long"
    assert bad_limit.status_code == 422 and bad_limit.json["error"] == "invalid_limit"
    assert empty.status_code == 200 and empty.json["status"] == "empty_query"


def test_discover_is_explicitly_unavailable(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    headers = _consent(client)

    response = client.post(
        "/api/f5/organizations/discover",
        json={"query": "厦门做海洋遥感、接受应届生的研究院"},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json["error"] == "discovery_unavailable"
    assert "五项业务决策" in response.json["message"]


def test_detail_and_jobs_are_404_while_the_index_is_empty(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    detail = client.get("/api/f5/organizations/detail", query_string={"id": "1"})
    jobs = client.get("/api/f5/organizations/jobs", query_string={"organization_id": "1"})

    assert detail.status_code == 404 and detail.json["error"] == "organization_not_found"
    assert jobs.status_code == 404 and jobs.json["error"] == "organization_not_found"


# ---------------------------------------------------------------- #
# 路由与发布配置
# ---------------------------------------------------------------- #

def test_vercel_rewrites_cover_the_f5_organization_routes():
    config = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
    routes = {item["source"]: item["destination"] for item in config["rewrites"]}

    for name in ("status", "suggest", "discover", "detail", "jobs"):
        source = "/api/f5/organizations/%s" % name
        assert routes[source] == "/api?_route=f5/organizations/%s" % name, source
