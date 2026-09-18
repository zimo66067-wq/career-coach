# -*- coding: utf-8 -*-
"""WF-01 · 数据处理同意（consent）与简历上传。

Phase 7c：本文件从 `api/index.py` 拆出。**分支体是按行号逐字搬过来的，逻辑未改写**，
改的只有外壳 —— 原 `if route == ...` 们被包进一个函数，末尾补 `return UNHANDLED` 表示
「本族没接住，交给下一个」。

为什么末尾要 `return UNHANDLED` 而不是 `return None`：None 是合法返回值（虽然现在没人返回
它），用哨兵才能让"没接住"和"故意返回 None"区分开。哨兵见 `api/dispatch.py`。

打桩点：本模块只用 `from providers import model as model_provider` 后做属性查找，
不绑定 `build_model_router`（见 `tests/test_layering.py` 规则 5）。
"""

from flask import request

from repositories.database import save_resume
from domain.deidentify import deidentify
from api.trace import trace_id

from api.app import app
from api.http_layer import api_response
from api.security import (
    _client_rate_key,
    enforce_usage,
    ensure_session_access,
    issue_consent,
    require_consent,
)
from api.sentinel import UNHANDLED
from api.validation import read_uploaded_resume


def handle_wf01(route):
    if route == "wf01/consent" and request.method == "POST":
        enforce_usage("consent_hour", 30, 3600, owner_key=_client_rate_key())
        return api_response(issue_consent())

    if route == "wf01/upload" and request.method == "POST":
        require_consent()
        enforce_usage("upload_hour", 20, 3600)
        source_text, filename, extension, file_size = read_uploaded_resume()
        cleaned_text, _mapping = deidentify(source_text)
        session_id = trace_id()
        ensure_session_access(session_id, allow_create=True)
        try:
            save_resume(
                session_id=session_id,
                client_ip=request.remote_addr or "",
                user_agent=request.headers.get("User-Agent", "")[:500],
                filename=filename[:200],
                file_type=extension,
                file_size=file_size,
                resume_text=cleaned_text[:100000],
            )
        except Exception:
            app.logger.exception("DB save resume failed")
        return api_response({
            "resumeText": cleaned_text,
            "resumeProfile": None,
            "session_id": session_id,
        })

    return UNHANDLED
