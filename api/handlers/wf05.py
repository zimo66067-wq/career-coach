# -*- coding: utf-8 -*-
"""WF-05 · 能力报告（R/M/I 三轴 + C0 基线 + 雷达选项）。

Phase 7c：本文件从 `api/index.py` 拆出。**分支体是按行号逐字搬过来的，逻辑未改写**，
改的只有外壳 —— 原 `if route == ...` 们被包进一个函数，末尾补 `return UNHANDLED` 表示
「本族没接住，交给下一个」。

为什么末尾要 `return UNHANDLED` 而不是 `return None`：None 是合法返回值（虽然现在没人返回
它），用哨兵才能让"没接住"和"故意返回 None"区分开。哨兵见 `api/dispatch.py`。

打桩点：本模块只用 `from providers import model as model_provider` 后做属性查找，
不绑定 `build_model_router`（见 `tests/test_layering.py` 规则 5）。
"""

from flask import request

from services.interview_service import build_ability_profile
from domain.internal.api_errors import ApiError
from domain.internal.radar_adapter import build_option

from api.http_layer import api_response
from api.security import ensure_session_access, require_consent
from api.sentinel import UNHANDLED


def handle_wf05(route):
    if route == "wf05/ability" and request.method == "POST":
        require_consent()
        if not request.is_json:
            raise ApiError("invalid_content_type", "能力报告请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "能力报告请求格式无效。", 422)
        session_id = body.get("session_id", "")
        if not session_id:
            raise ApiError("session_required", "缺少会话标识。", 422)
        # A never-seen/deleted id contains no data and may be safely bound so
        # the domain layer can return its existing "insufficient evidence" response.
        ensure_session_access(session_id, allow_create=True)
        ability, result = build_ability_profile(session_id)
        return api_response({
            "ability": ability,
            "radar_option": build_option(ability),
            "score_R": ability["resume_score"],
            "score_M": ability["match_score"],
            "score_I": ability["interview_score"],
            "C0": ability["baseline"],
            "session_id": session_id,
        })

    return UNHANDLED
