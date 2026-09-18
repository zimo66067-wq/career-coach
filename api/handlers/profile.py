# -*- coding: utf-8 -*-
"""职业证据档案：档案、候选证据抽取、确认 / 拒绝 / 修改。

Phase 7c：本文件从 `api/index.py` 拆出。**分支体是按行号逐字搬过来的，逻辑未改写**，
改的只有外壳 —— 原 `if route == ...` 们被包进一个函数，末尾补 `return UNHANDLED` 表示
「本族没接住，交给下一个」。

为什么末尾要 `return UNHANDLED` 而不是 `return None`：None 是合法返回值（虽然现在没人返回
它），用哨兵才能让"没接住"和"故意返回 None"区分开。哨兵见 `api/dispatch.py`。

打桩点：本模块只用 `from providers import model as model_provider` 后做属性查找，
不绑定 `build_model_router`（见 `tests/test_layering.py` 规则 5）。
"""

from flask import request

from services import career_evidence_service as evidence_service
from domain.internal.api_errors import ApiError
from repositories.database import get_resume_detail

from api.http_layer import api_response, require_json_object
from api.security import _task_owner_key, enforce_usage, ensure_session_access, require_consent
from api.sentinel import UNHANDLED


def handle_profile(route):
    # ---- Phase 3 · 核心闭环：职业证据档案 + 目标岗位分析 ------------------------
    # D8 方案 A：模型抽取只产出**候选证据**（pending），用户确认后才成为可信事实。
    # 这里不提供任何"直接写 confirmed"的入参 —— 见 services/career_evidence_service.py。
    if route == "profile" and request.method == "GET":
        require_consent()
        owner = _task_owner_key()
        evidence_service.ensure_profile(owner)
        return api_response(evidence_service.profile_payload(owner))

    if route == "profile/evidence/candidates" and request.method == "POST":
        require_consent()
        enforce_usage("evidence_candidates_hour", 30, 3600)
        body = require_json_object("候选证据请求")
        session_id = str(body.get("session_id") or "")
        ensure_session_access(session_id)
        detail = get_resume_detail(session_id)
        resume_text = str((detail or {}).get("resume_text") or "")
        if not resume_text:
            raise ApiError("resume_required", "请先上传并完成简历诊断。", 422)
        resume_profile = body.get("resumeProfile")
        requirements = body.get("requirements")
        owner = _task_owner_key()
        evidence_service.ensure_profile(owner)
        created, skipped, considered = evidence_service.collect_candidates(
            owner,
            session_id,
            resume_text,
            resume_profile=resume_profile if isinstance(resume_profile, dict) else None,
            requirements=requirements if isinstance(requirements, list) else None,
        )
        return api_response({
            "created": created,
            "createdCount": len(created),
            "skippedExisting": skipped,
            "considered": len(considered),
            "profile": evidence_service.profile_payload(owner),
        }, 201)

    if route.startswith("profile/evidence/") and request.method in ("POST", "DELETE"):
        require_consent()
        parts = route.split("/")
        if len(parts) not in (3, 4):
            raise ApiError("not_found", "接口不存在。", 404)
        try:
            evidence_id = int(parts[2])
        except (TypeError, ValueError):
            raise ApiError("invalid_request", "证据 ID 无效。", 422)
        action = parts[3] if len(parts) == 4 else ""
        owner = _task_owner_key()
        try:
            if request.method == "DELETE" and not action:
                evidence_service.delete(owner, evidence_id)
                return api_response({"deleted": True, "id": evidence_id})
            if request.method == "POST" and action == "confirm":
                return api_response({"evidence": evidence_service.confirm(owner, evidence_id)})
            if request.method == "POST" and action == "reject":
                return api_response({"evidence": evidence_service.reject(owner, evidence_id)})
            if request.method == "POST" and action == "edit":
                body = require_json_object("证据修改请求")
                return api_response({"evidence": evidence_service.edit(
                    owner,
                    evidence_id,
                    claim=body.get("claim"),
                    source_quote=body.get("sourceQuote"),
                    confirmed_by_user=bool(body.get("confirmedByUser")),
                )})
        except LookupError:
            raise ApiError("evidence_not_found", "证据不存在。", 404)
        raise ApiError("not_found", "接口不存在。", 404)

    return UNHANDLED
