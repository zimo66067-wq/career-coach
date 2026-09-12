# -*- coding: utf-8 -*-
"""F5 单位/职位检索服务（阶段 1：内部基础框架）

阶段 1 只建立数据索引、provider 契约与失败降级，**不接入任何外部数据源**，
因此对外一律返回「未配置」的明确状态，并且永远不生成单位事实。

规划见 `docs/f5-organization-job-search-plan-2026-09-11.md`；阶段 1 的验收
要求是「无外部 API 时不伪造数据；归属隔离、删除闭环和失败降级通过」。
"""
from tools.api_errors import ApiError
from tools.database import (
    find_organizations_by_name,
    get_organization as _get_organization_row,
    index_counts,
    list_job_postings,
    upsert_organization,
)
from tools.providers.organization import (
    build_organization_provider,
    eligible_results,
)

MAX_QUERY_CHARS = 64
MAX_LIMIT = 20

# 启动阶段 2/3 前必须先确定的产品与合规决策（规划第 10 节）
PENDING_DECISIONS = (
    "覆盖地域与单位类型：是否包含港澳台及境外单位。",
    "至少一个允许向终端用户展示并进行必要缓存的单位数据授权方案。",
    "实时职位来源及其展示、摘要、缓存和跳转权利。",
    "月度外部数据预算、目标搜索量与缓存策略。",
    "单位纠错与虚假招聘复核责任人。",
)

UNCONFIGURED_NOTICE = (
    "尚未接入获得终端展示授权的单位数据源，因此不提供单位搜索结果，"
    "也不会生成任何单位信息。请通过单位官网或权威登记信息自行核验后手动填写。"
)


def normalize_query(value):
    """Bound and normalize a user-supplied organization query."""
    text = str(value or "").strip()
    if len(text) > MAX_QUERY_CHARS:
        raise ApiError(
            "query_too_long",
            "搜索词不能超过 %d 个字符。" % MAX_QUERY_CHARS,
            422,
        )
    return text


def _bounded_limit(value, default=10):
    try:
        limit = int(value)
    except (TypeError, ValueError):
        raise ApiError(
            "invalid_limit", "limit 必须是 1-%d 的整数。" % MAX_LIMIT, 422
        )
    return min(max(limit, 1), MAX_LIMIT)


def _verification_state(row):
    """Derive the display state from the provenance fields we actually hold."""
    if str(row.get("verified_at") or "").strip():
        return "verified"
    if str(row.get("source_updated_at") or "").strip():
        return "stale"
    return "unknown"


def _public_item(row):
    """Project a stored row into the provenance-complete result contract."""
    return {
        "id": row.get("id"),
        "source_provider": row.get("source_provider"),
        "source_key": row.get("source_key"),
        "canonical_name": row.get("canonical_name"),
        "org_type": row.get("org_type"),
        "region": row.get("region"),
        "industry": row.get("industry"),
        "unified_id": row.get("unified_id"),
        "status": row.get("status"),
        "website": row.get("website"),
        "source_url": row.get("source_url"),
        "source_updated_at": row.get("source_updated_at"),
        "verified_at": row.get("verified_at"),
        "verification_state": _verification_state(row),
    }


def provider_status():
    """Data-source health, for the admin health check and the UI banner."""
    provider = build_organization_provider()
    configured = bool(provider.is_configured())
    return {
        "status": "ready" if configured else "unconfigured",
        "configured": configured,
        "provider": provider.name,
        "license_notice": provider.license_notice(),
        "index": index_counts(),
        "pending_decisions": list(PENDING_DECISIONS),
    }


def suggest_organizations(query, limit=10):
    """Name lookup with an explicit unconfigured state.

    Returning ``status="unconfigured"`` (instead of a bare empty list) lets the
    page render a banner rather than implying "no such organization exists".
    """
    query = normalize_query(query)
    limit = _bounded_limit(limit)
    provider = build_organization_provider()
    configured = bool(provider.is_configured())

    if not query:
        return {
            "status": "empty_query",
            "configured": configured,
            "provider": provider.name,
            "items": [],
            "total": 0,
        }

    if not configured:
        return {
            "status": "unconfigured",
            "configured": False,
            "provider": provider.name,
            "license_notice": provider.license_notice(),
            "notice": UNCONFIGURED_NOTICE,
            "pending_decisions": list(PENDING_DECISIONS),
            "items": [],
            "total": 0,
        }

    local = [
        _public_item(row) for row in find_organizations_by_name(query, limit=limit)
    ]
    items = eligible_results(local)[:limit]
    return {
        "status": "ok" if items else "not_found",
        "configured": True,
        "provider": provider.name,
        "license_notice": provider.license_notice(),
        "items": items,
        "total": len(items),
    }


def discover_organizations(payload=None):
    """Natural-language organization discovery (phase 3).

    Not implemented on purpose: the ranking pipeline (BM25 + vectors + RRF,
    plan section 5.2) is phase 3 work and must not be faked with model output.
    """
    provider = build_organization_provider()
    if not provider.is_configured():
        raise ApiError(
            "discovery_unavailable",
            "单位发现尚未开放：需要先接入获得授权的单位数据源，并完成规划中的五项业务决策。",
            422,
        )
    raise ApiError(
        "discovery_unavailable",
        "单位发现属于阶段 3，尚未实现。",
        422,
    )


def get_organization(org_id):
    """Return one indexed organization, or 404 when the index has no such row."""
    row = _get_organization_row(org_id)
    if row is None:
        raise ApiError("organization_not_found", "单位不存在或尚未收录。", 404)
    return {
        "organization": _public_item(row),
        "aliases": row.get("aliases") or [],
        "profile": row.get("profile"),
    }


def list_jobs_for(org_id, limit=20):
    """Return non-closed postings for an indexed organization."""
    limit = _bounded_limit(limit)
    if _get_organization_row(org_id) is None:
        raise ApiError("organization_not_found", "单位不存在或尚未收录。", 404)
    return {"items": list_job_postings(org_id, limit=limit), "total": None}


def ingest_organizations(records):
    """Persist provider records into the local index.

    Only call this with data the source licence permits us to store, and it
    re-applies the provenance contract at the write boundary: records without
    a traceable source are dropped instead of stored.
    """
    stored = []
    for record in eligible_results(records):
        row = upsert_organization(record, aliases=record.get("aliases"))
        if row is not None:
            stored.append(row)
    return stored
