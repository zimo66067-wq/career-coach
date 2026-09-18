# -*- coding: utf-8 -*-
"""缺口行动闭环：铺开 / 单条开单、推进、完成、结果、放弃。

Phase 7c：本文件从 `api/index.py` 拆出。**分支体是按行号逐字搬过来的，逻辑未改写**，
改的只有外壳 —— 原 `if route == ...` 们被包进一个函数，末尾补 `return UNHANDLED` 表示
「本族没接住，交给下一个」。

为什么末尾要 `return UNHANDLED` 而不是 `return None`：None 是合法返回值（虽然现在没人返回
它），用哨兵才能让"没接住"和"故意返回 None"区分开。哨兵见 `api/dispatch.py`。

打桩点：本模块只用 `from tools.providers import model as model_provider` 后做属性查找，
不绑定 `build_model_router`（见 `tests/test_layering.py` 规则 5）。
"""

from flask import request

from services import action_plan_service
from tools.api_errors import ApiError

from api.http_layer import api_response, require_json_object
from api.security import _task_owner_key, enforce_usage, require_consent
from api.sentinel import UNHANDLED


def handle_actions(route):
    # ------------------------------------------------------------------ #
    # Gap Action Plan（Phase 4）：把缺口翻成可执行、可验证的行动
    # ------------------------------------------------------------------ #
    if route == "actions" and request.method == "GET":
        require_consent()
        status = str(request.args.get("status") or "").strip() or None
        items = action_plan_service.list_actions(_task_owner_key(), status=status)
        return api_response({"actions": items, "total": len(items)})

    if route == "actions" and request.method == "POST":
        require_consent()
        enforce_usage("action_plan_hour", 30, 3600)
        body = require_json_object("行动计划请求")
        owner = _task_owner_key()

        # 两种开单方式：给 targetJobId 就按该岗位未解决缺口整体铺开（幂等），
        # 给 gapId 就只开这一条。两者都走服务层的同一套校验。
        if body.get("targetJobId") is not None:
            try:
                target_job_id = int(body["targetJobId"])
            except (TypeError, ValueError):
                raise ApiError("invalid_request", "目标岗位 ID 无效。", 422)
            plan = action_plan_service.plan_for_target(target_job_id, owner)
            return api_response({
                "targetJobId": target_job_id,
                "created": plan["created"],
                "existing": plan["existing"],
                "skipped": plan["skipped"],
                "createdCount": len(plan["created"]),
                "existingCount": len(plan["existing"]),
            }, 201 if plan["created"] else 200)

        if body.get("gapId") is not None:
            try:
                gap_id = int(body["gapId"])
            except (TypeError, ValueError):
                raise ApiError("invalid_request", "缺口 ID 无效。", 422)
            record, opened = action_plan_service.open_action(gap_id, owner)
            return api_response({"action": record, "opened": opened}, 201 if opened else 200)

        raise ApiError(
            "invalid_request",
            "请提供 targetJobId（按岗位铺开）或 gapId（单条开单）。",
            422,
        )

    if route.startswith("actions/"):
        parts = route.split("/")
        if len(parts) not in (2, 3):
            raise ApiError("not_found", "接口不存在。", 404)
        try:
            action_id = int(parts[1])
        except (TypeError, ValueError):
            raise ApiError("invalid_request", "行动 ID 无效。", 422)
        verb = parts[2] if len(parts) == 3 else ""

        if request.method == "GET" and not verb:
            require_consent()
            owner = _task_owner_key()
            return api_response({"action": action_plan_service.get_action(action_id, owner)})

        if request.method == "DELETE" and not verb:
            require_consent()
            owner = _task_owner_key()
            action_plan_service.delete_action(action_id, owner)
            return api_response({"deleted": True, "id": action_id})

        if request.method == "POST" and verb in ("start", "complete", "outcome", "drop"):
            require_consent()
            owner = _task_owner_key()

            if verb == "start":
                return api_response({"action": action_plan_service.start_action(action_id, owner)})

            if verb == "drop":
                return api_response({"action": action_plan_service.drop_action(action_id, owner)})

            if verb == "complete":
                body = require_json_object("完成请求") if request.data else {}
                artifact = str(body.get("artifact") or "").strip() or None
                return api_response({
                    "action": action_plan_service.complete_action(
                        action_id, owner, artifact=artifact
                    )
                })

            body = require_json_object("结果记录请求")
            outcome = str(body.get("outcome") or "").strip()
            if not outcome:
                raise ApiError("invalid_request", "请描述做完之后发生了什么。", 422)
            return api_response({
                "action": action_plan_service.record_action_outcome(action_id, owner, outcome)
            })

        raise ApiError("not_found", "接口不存在。", 404)

    return UNHANDLED
