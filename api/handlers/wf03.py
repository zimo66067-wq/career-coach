# -*- coding: utf-8 -*-
"""WF-03 · JD 上传 / JD 解析 / 简历与岗位匹配（BM25 四态）。

Phase 7c：本文件从 `api/index.py` 拆出。**分支体是按行号逐字搬过来的，逻辑未改写**，
改的只有外壳 —— 原 `if route == ...` 们被包进一个函数，末尾补 `return UNHANDLED` 表示
「本族没接住，交给下一个」。

为什么末尾要 `return UNHANDLED` 而不是 `return None`：None 是合法返回值（虽然现在没人返回
它），用哨兵才能让"没接住"和"故意返回 None"区分开。哨兵见 `api/dispatch.py`。

打桩点：本模块只用 `from tools.providers import model as model_provider` 后做属性查找，
不绑定 `build_model_router`（见 `tests/test_layering.py` 规则 5）。
"""

from flask import request

from services.match_service import build_job_profile, match_job_profile, validate_job_profile
from tools.api_errors import ApiError
from tools.database import save_match
from tools.trace import trace_id

from api.app import app
from api.http_layer import api_response
from api.security import enforce_usage, ensure_session_access, require_consent
from api.sentinel import UNHANDLED
from api.validation import read_uploaded_job, validate_job_text, validate_text


def handle_wf03(route):
    if route == "wf03/upload" and request.method == "POST":
        require_consent()
        enforce_usage("upload_hour", 20, 3600)
        source_text, _filename, _ext, _size = read_uploaded_job()
        session_id = request.form.get("session_id") or trace_id()
        ensure_session_access(session_id, allow_create=True)
        return api_response({"jdText": source_text, "jobProfile": None, "session_id": session_id})
    if route == "wf03/jd" and request.method == "POST":
        require_consent()
        session_id = trace_id()
        if request.files.get("file"):
            jd_text, _filename, _ext, _size = read_uploaded_job()
            session_id = request.form.get("session_id") or session_id
        else:
            if not request.is_json:
                raise ApiError("invalid_content_type", "JD 解析请求必须使用 JSON 格式。", 415)
            body = request.get_json(silent=True)
            if not isinstance(body, dict):
                raise ApiError("invalid_request", "JD 解析请求格式无效。", 422)
            jd_text = validate_job_text(body.get("jdText"))
            session_id = body.get("session_id") or session_id
        ensure_session_access(session_id, allow_create=True)
        return api_response({"jobProfile": build_job_profile(jd_text), "session_id": session_id})
    if route == "wf03/match" and request.method == "POST":
        require_consent()
        if not request.is_json:
            raise ApiError("invalid_content_type", "岗位匹配请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "岗位匹配请求格式无效。", 422)
        session_id = body.get("session_id") or trace_id()
        ensure_session_access(session_id, allow_create=True)
        match = match_job_profile(
            validate_text(body.get("resumeText")),
            validate_job_profile(body.get("jobProfile")),
        )
        try:
            save_match(session_id, match, match.get("score_M"))
        except Exception:
            app.logger.exception("DB save match failed")
        return api_response(dict(match, session_id=session_id))

    return UNHANDLED
