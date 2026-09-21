# -*- coding: utf-8 -*-
"""WF-02 · 简历诊断、单条建议改写、改写确认落库。

Phase 7c：本文件从 `api/index.py` 拆出。**分支体是按行号逐字搬过来的，逻辑未改写**，
改的只有外壳 —— 原 `if route == ...` 们被包进一个函数，末尾补 `return UNHANDLED` 表示
「本族没接住，交给下一个」。

为什么末尾要 `return UNHANDLED` 而不是 `return None`：None 是合法返回值（虽然现在没人返回
它），用哨兵才能让"没接住"和"故意返回 None"区分开。哨兵见 `api/dispatch.py`。

打桩点：本模块只用 `from providers import model as model_provider` 后做属性查找，
不绑定 `build_model_router`（见 `tests/test_layering.py` 规则 5）。
"""

import json

from flask import request

from services.diagnosis_service import diagnose_resume
from domain.internal.api_errors import ApiError
from repositories.database import (
    get_resume_detail,
    mark_rewrite_applied,
    save_diagnosis,
    save_resume,
    save_rewrite,
)
from domain.deidentify import deidentify
from domain.optimizer import rewrite_suggestion
from providers import model as model_provider
from api.trace import trace_id

from api.app_instance import app
from api.http_layer import api_response, require_json_object
from api.security import enforce_usage, ensure_session_access, require_consent
from api.sentinel import UNHANDLED
from api.validation import validate_text


def handle_wf02(route):
    if route == "wf02/optimize" and request.method == "POST":
        require_consent()
        enforce_usage("model_generation_hour", 20, 3600)
        enforce_usage("model_generation_day", 60, 86400)
        body = require_json_object("简历优化请求")
        session_id = str(body.get("session_id") or "")
        if not session_id:
            raise ApiError("session_required", "缺少会话标识。", 422)
        ensure_session_access(session_id)
        detail = get_resume_detail(session_id)
        if not detail or not detail.get("diagnoses"):
            raise ApiError("diagnosis_required", "请先完成 F1 简历诊断。", 422)
        profile = {}
        diag = detail["diagnoses"][0]
        try:
            profile = json.loads(diag.get("diagnosis_json") or "{}")
        except (TypeError, ValueError):
            profile = {}
        suggestions = profile.get("suggestions") if isinstance(profile, dict) else []
        suggestion_id = str(body.get("suggestion_id") or "")
        suggestion = None
        for item in suggestions:
            if str(item.get("id") or "") == suggestion_id:
                suggestion = item
                break
        if suggestion is None and suggestions:
            suggestion = suggestions[0]
        if suggestion is None:
            raise ApiError("suggestion_required", "暂无可用诊断建议。", 422)
        try:
            router = model_provider.build_model_router()
        except ApiError:
            router = None
        return api_response(
            rewrite_suggestion(suggestion, resume_profile=profile, model_router=router)
        )

    if route == "wf02/apply-rewrite" and request.method == "POST":
        require_consent()
        body = require_json_object("改写确认请求")
        session_id = str(body.get("session_id") or "")
        candidate = str(body.get("candidate_text") or "").strip()
        suggestion_id = str(body.get("suggestion_id") or "")
        issue = str(body.get("issue") or "")
        if not session_id or len(candidate) < 5:
            raise ApiError("invalid_request", "缺少会话标识或改写内容。", 422)
        ensure_session_access(session_id)
        saved = save_rewrite(session_id, suggestion_id, issue, candidate)
        if saved is None:
            raise ApiError("save_failed", "改写内容保存失败。", 500)
        applied = mark_rewrite_applied(saved["id"], session_id)
        return api_response({"rewrite": applied, "status": "APPLIED"}, 201)

    if route == "wf02/diagnose" and request.method == "POST":
        require_consent()
        enforce_usage("model_generation_hour", 20, 3600)
        enforce_usage("model_generation_day", 60, 86400)
        if not request.is_json:
            raise ApiError("invalid_content_type", "诊断请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "诊断请求格式无效。", 422)
        resume_text = validate_text(body.get("resumeText"))
        session_id = body.get("session_id") or trace_id()
        ensure_session_access(session_id, allow_create=True)
        # A diagnosis must always be attachable: ensure a resume row exists even
        # when the client diagnoses pasted text without a preceding upload.
        if get_resume_detail(session_id) is None:
            cleaned_text, _mapping = deidentify(resume_text)
            try:
                save_resume(
                    session_id=session_id,
                    client_ip=request.remote_addr or "",
                    user_agent=request.headers.get("User-Agent", "")[:500],
                    filename="pasted-resume.txt",
                    file_type="paste",
                    file_size=len(resume_text),
                    resume_text=cleaned_text[:100000],
                )
            except Exception:
                app.logger.exception("DB save resume failed")
        # trace 由 web 层解析（透传 X-Trace-Id）后注入：服务层不再碰请求上下文（Phase 5）
        profile, score_r, model_trace_id, diagnosis_mode, diagnosis_notice = diagnose_resume(
            resume_text, trace=trace_id()
        )
        try:
            save_diagnosis(
                session_id=session_id,
                score_r=score_r,
                diagnosis_mode=diagnosis_mode,
                diagnosis_notice=diagnosis_notice,
                model_trace_id=model_trace_id,
                diagnosis_json=json.dumps(profile, ensure_ascii=False)[:500000],
            )
        except Exception:
            app.logger.exception("DB save diagnosis failed")
        return api_response({
            "resumeProfile": profile,
            "score_R": score_r,
            "model_trace_id": model_trace_id,
            "diagnosis_mode": diagnosis_mode,
            "diagnosis_notice": diagnosis_notice,
            "session_id": session_id,
        })

    return UNHANDLED
