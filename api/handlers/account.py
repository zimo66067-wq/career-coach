# -*- coding: utf-8 -*-
"""账号与历史：注册 / 登录 / 登出 / 当前用户，浏览与删除历史。

Phase 7c：本文件从 `api/index.py` 拆出。**分支体是按行号逐字搬过来的，逻辑未改写**，
改的只有外壳 —— 原 `if route == ...` 们被包进一个函数，末尾补 `return UNHANDLED` 表示
「本族没接住，交给下一个」。

为什么末尾要 `return UNHANDLED` 而不是 `return None`：None 是合法返回值（虽然现在没人返回
它），用哨兵才能让"没接住"和"故意返回 None"区分开。哨兵见 `api/dispatch.py`。

打桩点：本模块只用 `from providers import model as model_provider` 后做属性查找，
不绑定 `build_model_router`（见 `tests/test_layering.py` 规则 5）。
"""

import re

from flask import request

from services.account_service import (
    AccountError,
    add_history,
    authenticate,
    create_session,
    delete_history,
    end_session,
    list_history,
    public_user,
    register_user,
)
from domain.internal.api_errors import ApiError

from api.http_layer import api_response, require_json_object
from api.security import (
    _claim_guest_resources,
    _clear_session_cookie,
    _client_rate_key,
    _session_ttl_days,
    _set_session_cookie,
    current_session,
    enforce_usage,
    ensure_session_access,
    require_login,
)
from api.sentinel import UNHANDLED


def handle_account(route):
    if route == "auth/register" and request.method == "POST":
        body = require_json_object("注册请求")
        phone = str(body.get("phone") or "").strip()
        email = str(body.get("email") or "").strip()
        password = str(body.get("password") or "")
        name = str(body.get("name") or "").strip()
        if not re.fullmatch(r"1\d{10}", phone):
            raise ApiError("invalid_phone", "手机号格式不正确（11 位，1 开头）。", 422)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ApiError("invalid_email", "邮箱格式不正确。", 422)
        if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            raise ApiError("weak_password", "密码至少 8 位且需包含字母和数字。", 422)
        if not (2 <= len(name) <= 16):
            raise ApiError("invalid_name", "账户名需 2-16 个字符。", 422)
        enforce_usage("auth_register", 5, 3600, owner_key=_client_rate_key())
        try:
            user = register_user(phone, email, password, name)
        except AccountError as err:
            raise ApiError(err.code, err.message, err.status)
        token, _expires = create_session(user["id"], _session_ttl_days())
        _claim_guest_resources(user["id"])
        resp, status = api_response(public_user(user), 201)
        _set_session_cookie(resp, token)
        return resp, status

    if route == "auth/login" and request.method == "POST":
        body = require_json_object("登录请求")
        identifier = str(body.get("account") or "").strip()
        password = str(body.get("password") or "")
        if not identifier or not password:
            raise ApiError("invalid_request", "请输入手机号/邮箱和密码。", 422)
        enforce_usage("auth_login", 10, 900, owner_key=_client_rate_key())
        user = authenticate(identifier, password)
        if not user:
            raise ApiError("bad_credentials", "手机号/邮箱或密码不正确。", 401)
        token, _expires = create_session(user["id"], _session_ttl_days())
        _claim_guest_resources(user["id"])
        resp, status = api_response(public_user(user))
        _set_session_cookie(resp, token)
        return resp, status

    if route == "auth/logout" and request.method == "POST":
        _user, token = current_session()
        end_session(token)
        resp, status = api_response({"status": "LOGGED_OUT"})
        _clear_session_cookie(resp)
        return resp, status

    if route == "auth/me" and request.method == "GET":
        user, _token = current_session()
        if not user:
            return api_response({"logged_in": False})
        return api_response({"logged_in": True, "user": public_user(user)})

    if route == "history" and request.method == "GET":
        user = require_login()
        try:
            limit = min(max(int(request.args.get("limit", 50)), 1), 100)
            offset = max(int(request.args.get("offset", 0)), 0)
        except ValueError:
            limit, offset = 50, 0
        event_type = (request.args.get("type") or "").strip() or None
        if event_type and event_type not in ("F1", "F2", "F3", "F4"):
            raise ApiError("invalid_type", "历史类型仅支持 F1-F4。", 422)
        items, total = list_history(
            user["id"],
            limit=limit,
            offset=offset,
            event_type=event_type,
            role=user["role"],
        )
        return api_response({
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        })

    if route == "history" and request.method == "POST":
        user = require_login()
        body = require_json_object("历史记录请求")
        session_id = str(body.get("session_id") or "").strip()
        event_type = str(body.get("event_type") or "").strip()
        title = str(body.get("title") or "").strip()
        status = str(body.get("status") or "done").strip()
        if not session_id:
            raise ApiError("session_required", "缺少会话标识。", 422)
        ensure_session_access(session_id, allow_create=True)
        if event_type not in ("F1", "F2", "F3", "F4"):
            raise ApiError("invalid_type", "历史类型仅支持 F1-F4。", 422)
        if status not in ("done", "partial", "failed"):
            raise ApiError("invalid_status", "状态仅支持 done/partial/failed。", 422)
        if not (1 <= len(title) <= 200):
            raise ApiError("invalid_title", "标题长度需在 1-200 字符之间。", 422)
        history_id = add_history(user["id"], session_id, event_type, title, status)
        return api_response({"id": history_id, "status": "CREATED"}, 201)

    if route.startswith("history/") and request.method == "DELETE":
        user = require_login()
        try:
            event_id = int(route.split("/", 1)[1])
        except (IndexError, ValueError):
            raise ApiError("invalid_id", "历史记录标识无效。", 422)
        try:
            delete_history(user["id"], event_id)
        except AccountError as err:
            raise ApiError(err.code, err.message, err.status)
        return api_response({"status": "DELETED"})

    return UNHANDLED
