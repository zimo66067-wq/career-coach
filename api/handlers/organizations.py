# -*- coding: utf-8 -*-
"""F5 单位 / 职位检索（契约 + 显式降级）。

Phase 7c：本文件从 `api/index.py` 拆出。**分支体是按行号逐字搬过来的，逻辑未改写**，
改的只有外壳 —— 原 `if route == ...` 们被包进一个函数，末尾补 `return UNHANDLED` 表示
「本族没接住，交给下一个」。

为什么末尾要 `return UNHANDLED` 而不是 `return None`：None 是合法返回值（虽然现在没人返回
它），用哨兵才能让"没接住"和"故意返回 None"区分开。哨兵见 `api/dispatch.py`。

打桩点：本模块只用 `from providers import model as model_provider` 后做属性查找，
不绑定 `build_model_router`（见 `tests/test_layering.py` 规则 5）。
"""

from flask import request

from services.organization_service import (
    discover_organizations,
    get_organization,
    list_jobs_for,
    provider_status,
    suggest_organizations,
)
from domain.internal.api_errors import ApiError

from api.http_layer import api_response, require_json_object
from api.security import _client_rate_key, enforce_usage, require_consent
from api.sentinel import UNHANDLED


def handle_organizations(route):
    # F5 unit/job index (phase 1 foundation: contract + explicit degrade only).
    if route.startswith("f5/organizations/"):
        if request.method == "GET":
            enforce_usage("f5_catalog_read", 240, 600, owner_key=_client_rate_key())
        else:
            require_consent()
            enforce_usage("f5_discover", 30, 3600)
        if route == "f5/organizations/status" and request.method == "GET":
            return api_response(provider_status())
        if route == "f5/organizations/suggest" and request.method == "GET":
            return api_response(
                suggest_organizations(
                    request.args.get("q", ""),
                    limit=request.args.get("limit", 10),
                )
            )
        if route == "f5/organizations/discover" and request.method == "POST":
            body = require_json_object("单位发现请求")
            return api_response(discover_organizations(body))
        if route == "f5/organizations/detail" and request.method == "GET":
            return api_response(get_organization(request.args.get("id", "")))
        if route == "f5/organizations/jobs" and request.method == "GET":
            return api_response(
                list_jobs_for(
                    request.args.get("organization_id", ""),
                    limit=request.args.get("limit", 20),
                )
            )
        raise ApiError("not_found", "接口不存在。", 404)

    return UNHANDLED
