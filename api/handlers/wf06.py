# -*- coding: utf-8 -*-
"""WF-06 · 会话数据删除（按 owner 校验后删）。

Phase 7c：本文件从 `api/index.py` 拆出。**分支体是按行号逐字搬过来的，逻辑未改写**，
改的只有外壳 —— 原 `if route == ...` 们被包进一个函数，末尾补 `return UNHANDLED` 表示
「本族没接住，交给下一个」。

为什么末尾要 `return UNHANDLED` 而不是 `return None`：None 是合法返回值（虽然现在没人返回
它），用哨兵才能让"没接住"和"故意返回 None"区分开。哨兵见 `api/dispatch.py`。

打桩点：本模块只用 `from providers import model as model_provider` 后做属性查找，
不绑定 `build_model_router`（见 `tests/test_layering.py` 规则 5）。
"""

from flask import request

from domain.internal.api_errors import ApiError
from repositories.database import delete_session_data

from api.app_instance import app
from api.http_layer import api_response
from api.security import _task_owner_key, ensure_session_access, require_consent
from api.sentinel import UNHANDLED


def handle_wf06(route):
    if route == "wf06/delete" and request.method == "POST":
        require_consent()
        if not request.is_json:
            raise ApiError("invalid_content_type", "删除请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "删除请求格式无效。", 422)
        session_id = body.get("session_id", "")
        if not session_id:
            raise ApiError("session_required", "缺少会话标识。", 422)
        ensure_session_access(session_id)
        owner_key = _task_owner_key()
        try:
            deleted = delete_session_data(session_id, owner_key=owner_key)
        except Exception:
            app.logger.exception("DB delete session failed")
            raise ApiError("delete_failed", "数据删除失败，请稍后重试。", 500)
        if not deleted:
            raise ApiError("session_not_found", "会话不存在或无权访问。", 404)
        return api_response({
            "status": "DELETED",
            "deleted_at": __import__("datetime").datetime.now().isoformat(),
            "session_id": session_id,
        })

    return UNHANDLED
