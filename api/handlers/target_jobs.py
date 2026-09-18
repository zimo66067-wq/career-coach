# -*- coding: utf-8 -*-
"""目标岗位分析：建单、查询、按未解决缺口出题。

Phase 7c：本文件从 `api/index.py` 拆出。**分支体是按行号逐字搬过来的，逻辑未改写**，
改的只有外壳 —— 原 `if route == ...` 们被包进一个函数，末尾补 `return UNHANDLED` 表示
「本族没接住，交给下一个」。

为什么末尾要 `return UNHANDLED` 而不是 `return None`：None 是合法返回值（虽然现在没人返回
它），用哨兵才能让"没接住"和"故意返回 None"区分开。哨兵见 `api/dispatch.py`。

打桩点：本模块只用 `from providers import model as model_provider` 后做属性查找，
不绑定 `build_model_router`（见 `tests/test_layering.py` 规则 5）。
"""

from flask import request

from services import target_job_service
from domain.internal.api_errors import ApiError
from repositories.database import get_resume_detail

from api.constants import MAX_TEXT_CHARS
from api.http_layer import api_response, require_json_object
from api.security import _task_owner_key, enforce_usage, ensure_session_access, require_consent
from api.sentinel import UNHANDLED


def handle_target_jobs(route):
    if route == "target-jobs" and request.method == "GET":
        require_consent()
        items = target_job_service.list_target_jobs(_task_owner_key())
        return api_response({"targetJobs": items, "total": len(items)})

    if route == "target-jobs" and request.method == "POST":
        require_consent()
        enforce_usage("target_job_create_hour", 20, 3600)
        body = require_json_object("目标岗位请求")
        session_id = str(body.get("session_id") or "")
        if session_id:
            ensure_session_access(session_id)
        job_profile = body.get("jobProfile")
        jd_text = str(body.get("jdText") or "").strip()
        if not isinstance(job_profile, dict):
            job_profile = None
        if job_profile is None and not jd_text:
            raise ApiError("jd_required", "请提供 JD 文本或已确认的岗位画像。", 422)
        if len(jd_text) > MAX_TEXT_CHARS:
            raise ApiError("payload_too_large", "JD 文本超过服务允许的长度。", 413)
        record = target_job_service.create_target_job(
            owner_key=_task_owner_key(),
            session_id=session_id or None,
            company=str(body.get("company") or "").strip() or None,
            position=str(body.get("position") or "").strip() or None,
            jd_text=jd_text or None,
            job_profile=job_profile,
        )
        return api_response({
            "targetJob": record,
            "requirements": target_job_service.requirements_of(record["id"]),
            "droppedNonRequirements": record.get("dropped_non_requirements") or [],
        }, 201)

    if route.startswith("target-jobs/") and request.method in ("GET", "POST", "DELETE"):
        require_consent()
        parts = route.split("/")
        if len(parts) not in (2, 3):
            raise ApiError("not_found", "接口不存在。", 404)
        try:
            target_job_id = int(parts[1])
        except (TypeError, ValueError):
            raise ApiError("invalid_request", "目标岗位 ID 无效。", 422)
        action = parts[2] if len(parts) == 3 else ""
        owner = _task_owner_key()

        if request.method == "GET" and not action:
            record = target_job_service.get_target_job(target_job_id, owner)
            return api_response({
                "targetJob": record,
                "requirements": target_job_service.requirements_of(target_job_id),
                "decision": target_job_service.decision_of(target_job_id, owner),
            })

        if request.method == "GET" and action == "decision":
            return api_response({
                "decision": target_job_service.decision_of(target_job_id, owner),
            })

        if request.method == "POST" and action == "analyse":
            enforce_usage("target_job_analyse_hour", 30, 3600)
            body = require_json_object("分析请求") if request.data else {}
            resume_text = str(body.get("resumeText") or "").strip()
            if not resume_text:
                session_id = str(body.get("session_id") or "")
                if not session_id:
                    record = target_job_service.get_target_job(target_job_id, owner)
                    session_id = str(record.get("session_id") or "")
                if not session_id:
                    raise ApiError("resume_required", "请先上传并完成简历诊断。", 422)
                ensure_session_access(session_id)
                detail = get_resume_detail(session_id)
                resume_text = str((detail or {}).get("resume_text") or "")
            if not resume_text:
                raise ApiError("resume_required", "请先上传并完成简历诊断。", 422)
            if len(resume_text) > MAX_TEXT_CHARS:
                raise ApiError("payload_too_large", "简历文本超过服务允许的长度。", 413)
            return api_response(target_job_service.analyse(target_job_id, owner, resume_text))

        if request.method == "DELETE" and not action:
            target_job_service.delete_target_job(target_job_id, owner)
            return api_response({"deleted": True, "id": target_job_id})

        raise ApiError("not_found", "接口不存在。", 404)

    return UNHANDLED
