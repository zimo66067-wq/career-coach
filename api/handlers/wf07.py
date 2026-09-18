# -*- coding: utf-8 -*-
"""WF-07 · 求职信生成、投递记录增删查、投递结果回流。

Phase 7c：本文件从 `api/index.py` 拆出。**分支体是按行号逐字搬过来的，逻辑未改写**，
改的只有外壳 —— 原 `if route == ...` 们被包进一个函数，末尾补 `return UNHANDLED` 表示
「本族没接住，交给下一个」。

为什么末尾要 `return UNHANDLED` 而不是 `return None`：None 是合法返回值（虽然现在没人返回
它），用哨兵才能让"没接住"和"故意返回 None"区分开。哨兵见 `api/dispatch.py`。

打桩点：本模块只用 `from tools.providers import model as model_provider` 后做属性查找，
不绑定 `build_model_router`（见 `tests/test_layering.py` 规则 5）。
"""

from flask import request

from services.apply_service import (
    create_application,
    delete_application,
    generate_cover_letter,
    list_applications_for,
    list_outcomes_for,
    record_outcome_feedback,
)
from tools.api_errors import ApiError

from api.http_layer import api_response, require_json_object
from api.security import _task_owner_key, enforce_usage, ensure_session_access, require_consent
from api.sentinel import UNHANDLED


def handle_wf07(route):
    if route == "wf07/cover-letter" and request.method == "POST":
        require_consent()
        enforce_usage("model_generation_hour", 20, 3600)
        enforce_usage("model_generation_day", 60, 86400)
        body = require_json_object("求职信请求")
        session_id = str(body.get("session_id") or "")
        if not session_id:
            raise ApiError("session_required", "缺少会话标识。", 422)
        ensure_session_access(session_id)

        # DoD #10：带上 targetJobId 就走"岗位要求 + 已确认证据"的接地路径
        # （公司/职位也可从岗位记录里取）。不带则保持旧行为（只读 F1 诊断）。
        target_job_id = body.get("targetJobId")
        if target_job_id is not None:
            try:
                target_job_id = int(target_job_id)
            except (TypeError, ValueError):
                raise ApiError("invalid_request", "目标岗位 ID 无效。", 422)

        return api_response(
            generate_cover_letter(
                session_id,
                company=body.get("company", ""),
                position=body.get("position", ""),
                target_job_id=target_job_id,
                owner_key=_task_owner_key(),
            )
        )

    if route == "wf07/applications" and request.method == "GET":
        require_consent()
        return api_response({"applications": list_applications_for(_task_owner_key())})

    if route == "wf07/applications" and request.method == "POST":
        require_consent()
        body = require_json_object("申请记录请求")
        session_id = str(body.get("session_id") or "")
        ensure_session_access(session_id)
        application = create_application(
            session_id=session_id,
            owner_key=_task_owner_key(),
            company=body.get("company", ""),
            position=body.get("position", ""),
            cover_letter=body.get("cover_letter", ""),
        )
        return api_response({"application": application}, 201)

    if route == "wf07/applications" and request.method == "DELETE":
        require_consent()
        app_id = request.args.get("id", "")
        try:
            app_id = int(app_id)
        except (TypeError, ValueError):
            raise ApiError("invalid_request", "缺少有效的申请记录 ID。", 422)
        deleted = delete_application(app_id, _task_owner_key())
        return api_response({"application": deleted, "status": "DELETED"})

    # 投递结果回流（Phase 4）：一次结果同时推进申请状态并反向写**待确认**证据。
    if route.startswith("wf07/applications/") and request.method in ("GET", "POST"):
        require_consent()
        parts = route.split("/")
        if len(parts) != 4:
            raise ApiError("not_found", "接口不存在。", 404)
        try:
            application_id = int(parts[2])
        except (TypeError, ValueError):
            raise ApiError("invalid_request", "申请记录 ID 无效。", 422)
        verb = parts[3]
        owner = _task_owner_key()

        if verb == "outcomes" and request.method == "GET":
            return api_response({"outcomes": list_outcomes_for(application_id, owner)})

        if verb == "outcome" and request.method == "POST":
            body = require_json_object("结果记录请求")
            outcome = str(body.get("outcome") or "").strip().lower()
            if not outcome:
                raise ApiError(
                    "invalid_request",
                    "请提供 outcome（applied / interview / offer / rejected / "
                    "withdrawn / no_response）。",
                    422,
                )
            note = str(body.get("note") or "").strip() or None
            return api_response(
                record_outcome_feedback(application_id, owner, outcome, note=note)
            )

        raise ApiError("not_found", "接口不存在。", 404)

    return UNHANDLED
