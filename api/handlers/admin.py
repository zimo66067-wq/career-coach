# -*- coding: utf-8 -*-
"""运维只读端点：简历列表与全量导出（口令 + 限流）。

Phase 7c：本文件从 `api/index.py` 拆出。**分支体是按行号逐字搬过来的，逻辑未改写**，
改的只有外壳 —— 原 `if route == ...` 们被包进一个函数，末尾补 `return UNHANDLED` 表示
「本族没接住，交给下一个」。

为什么末尾要 `return UNHANDLED` 而不是 `return None`：None 是合法返回值（虽然现在没人返回
它），用哨兵才能让"没接住"和"故意返回 None"区分开。哨兵见 `api/dispatch.py`。

打桩点：本模块只用 `from tools.providers import model as model_provider` 后做属性查找，
不绑定 `build_model_router`（见 `tests/test_layering.py` 规则 5）。
"""

from flask import request

from tools.api_errors import ApiError
from tools.database import admin_password_ok, count_resumes, export_all, list_resumes

from api.http_layer import api_response
from api.security import _client_rate_key, enforce_usage
from api.sentinel import UNHANDLED


def handle_admin(route):
    if route == "admin/resumes" and request.method == "GET":
        enforce_usage("admin_read", 10, 900, owner_key=_client_rate_key())
        password = request.headers.get("X-Admin-Password", "")
        if not admin_password_ok(password):
            raise ApiError("forbidden", "访问被拒绝。", 403)
        try:
            limit = min(int(request.args.get("limit", 100)), 500)
            offset = max(int(request.args.get("offset", 0)), 0)
        except ValueError:
            limit, offset = 100, 0
        return api_response({
            "total": count_resumes(),
            "limit": limit,
            "offset": offset,
            "items": list_resumes(limit=limit, offset=offset),
            "warning": "Vercel /tmp 是临时文件系统；服务重启后数据会丢失。请定期导出。",
        })
    if route == "admin/export" and request.method == "GET":
        enforce_usage("admin_export", 3, 3600, owner_key=_client_rate_key())
        password = request.headers.get("X-Admin-Password", "")
        if not admin_password_ok(password):
            raise ApiError("forbidden", "访问被拒绝。", 403)
        return api_response(export_all())

    return UNHANDLED
