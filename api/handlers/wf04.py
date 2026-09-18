# -*- coding: utf-8 -*-
"""WF-04 · 模拟面试：开题、作答、结束，以及打字对话的 SSE 流。

Phase 7c：本文件从 `api/index.py` 拆出。**分支体是按行号逐字搬过来的，逻辑未改写**，
改的只有外壳 —— 原 `if route == ...` 们被包进一个函数，末尾补 `return UNHANDLED` 表示
「本族没接住，交给下一个」。

为什么末尾要 `return UNHANDLED` 而不是 `return None`：None 是合法返回值（虽然现在没人返回
它），用哨兵才能让"没接住"和"故意返回 None"区分开。哨兵见 `api/dispatch.py`。

打桩点：本模块只用 `from tools.providers import model as model_provider` 后做属性查找，
不绑定 `build_model_router`（见 `tests/test_layering.py` 规则 5）。
"""

import json
import uuid

from flask import Response, request, stream_with_context

from services import career_evidence_service as evidence_service, target_job_service
from services.interview_service import (
    _advance_interview,
    _coerce_asr_confidence,
    _validated_answer_text,
    answer_interview,
    build_interview_router,
    build_turn_evaluation,
    end_interview,
    start_interview,
)
from tools.api_errors import ApiError
from tools.database import load_session, update_session
from tools.interview_engine import InterviewEngine
from tools.providers import model as model_provider

from api.http_layer import api_response, require_json_object
from api.security import _task_owner_key, enforce_usage, ensure_session_access, require_consent
from api.sentinel import UNHANDLED


def handle_wf04(route):
    if route == "wf04/stream" and request.method == "POST":
        require_consent()
        enforce_usage("interview_turn_hour", 120, 3600)
        body = require_json_object("面试请求")
        session_id = str(body.get("session_id") or "")
        if not session_id:
            raise ApiError("session_required", "缺少面试会话标识。", 422)
        ensure_session_access(session_id)
        state, payload = load_session(session_id)
        if not payload:
            raise ApiError("session_not_found", "面试会话不存在或已过期。", 404)
        engine = InterviewEngine(model_router=build_interview_router())
        engine_session = payload
        answer_text = _validated_answer_text(body)
        asr_confidence = _coerce_asr_confidence(body.get("asr_confidence"))

        # 打字对话状态机（与 /wf04/answer 共用同一编排）：
        # 1) 有待回答追问 -> 本次输入为追问回答，记录后进入下一主问题；
        # 2) 主回答生成追问 -> 等待用户回答追问；
        # 3) 主回答无追问 -> 直接进入下一主问题；
        # 4) 低 ASR 置信度 -> 不记录、不追问、不推进，只要求用户确认转写。
        result, next_question = _advance_interview(
            engine, engine_session, answer_text, asr_confidence
        )
        update_session(session_id, engine_session.get("state", "ASK"), engine_session)

        needs_confirmation = bool(result.get("needs_confirmation"))
        follow_up = result.get("follow_up") if isinstance(result.get("follow_up"), dict) else None
        if needs_confirmation:
            full_text = (
                "这次语音转写的置信度偏低，为避免误记你的回答，我没有把它计入本轮。"
                "请确认或修改转写文本后重新提交。"
            )
        elif next_question:
            if next_question.get("done"):
                full_text = "本轮面试已完成，正在生成综合报告…"
            else:
                full_text = str(next_question.get("question") or "").strip()
        else:
            full_text = str((follow_up or {}).get("question") or "").strip()
        if not full_text:
            full_text = "已收到回答，请继续。"

        evaluation = build_turn_evaluation(result)

        def _sse_gen():
            chunk_size = 32
            for i in range(0, len(full_text), chunk_size):
                chunk = full_text[i:i + chunk_size]
                yield "data: " + json.dumps(
                    {"type": "fragment", "text": chunk, "done": False},
                    ensure_ascii=False,
                ) + "\n\n"
            yield "data: " + json.dumps(
                {"type": "done", "turn": result, "followUp": follow_up,
                 "evaluation": evaluation, "nextQuestion": next_question,
                 "needs_confirmation": needs_confirmation, "done": True},
                ensure_ascii=False,
            ) + "\n\n"

        stream_resp = Response(
            stream_with_context(_sse_gen()), mimetype="text/event-stream"
        )
        stream_resp.headers["Cache-Control"] = "no-cache"
        stream_resp.headers["X-Accel-Buffering"] = "no"
        return stream_resp

    if route == "wf04/start" and request.method == "POST":
        require_consent()
        enforce_usage("interview_start_hour", 20, 3600)
        if not request.is_json:
            raise ApiError("invalid_content_type", "面试请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "面试请求格式无效。", 422)
        body["session_id"] = body.get("session_id") or ("iv_" + uuid.uuid4().hex[:16])
        ensure_session_access(body["session_id"], allow_create=True)

        # 通过 targetJobId 把面试接到目标岗位上：出题顺序直接来自该岗位的未解决缺口
        # （P0 → P1 → P2），这就是"按 Gap 定向出题"的落地方式。
        target_job_id = body.get("targetJobId")
        plan = None
        if target_job_id is not None:
            try:
                target_job_id = int(target_job_id)
            except (TypeError, ValueError):
                raise ApiError("invalid_request", "目标岗位 ID 无效。", 422)
            owner = _task_owner_key()
            gaps = target_job_service.interview_gaps(target_job_id, owner)
            if not body.get("matchGaps"):
                body["matchGaps"] = gaps
            plan = target_job_service.question_plan(target_job_id, owner)

        result = start_interview(body)
        if plan is not None:
            result["questionPlan"] = plan
            result["targetJobId"] = target_job_id
        return api_response(result)
    if route == "wf04/answer" and request.method == "POST":
        require_consent()
        enforce_usage("interview_turn_hour", 120, 3600)
        if not request.is_json:
            raise ApiError("invalid_content_type", "面试请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "面试请求格式无效。", 422)
        if not body.get("session_id"):
            raise ApiError("session_required", "缺少面试会话标识。", 422)
        ensure_session_access(body.get("session_id"))
        return api_response(answer_interview(body))
    if route == "wf04/end" and request.method == "POST":
        require_consent()
        if not request.is_json:
            raise ApiError("invalid_content_type", "面试请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "面试请求格式无效。", 422)
        if not body.get("session_id"):
            raise ApiError("session_required", "缺少面试会话标识。", 422)
        ensure_session_access(body.get("session_id"))
        result = end_interview(body)

        # D9 方案 A：面试结束后**一次性**抽取候选事实，落成待确认证据。
        # 必须带 targetJobId —— 面试新发现的事实要挂在某个目标岗位上（域层约束），
        # 没有岗位就没有归属，宁可不抽，也不生成无主证据。
        target_job_id = body.get("targetJobId")
        if target_job_id is not None:
            try:
                target_job_id = int(target_job_id)
            except (TypeError, ValueError):
                raise ApiError("invalid_request", "目标岗位 ID 无效。", 422)
            owner = _task_owner_key()
            target_job_service.get_target_job(target_job_id, owner)  # 归属校验
            try:
                router = model_provider.build_model_router()
            except ApiError:
                router = None
            extraction = evidence_service.extract_candidates(
                owner, result.get("session_id"), result.get("turns") or [], router=router
            )
            result["candidateEvidence"] = {
                "created": len(extraction["created"]),
                "skipped": extraction["skipped"],
                "dropped": extraction["dropped"],
                "degraded": extraction["degraded"],
                "ids": [record["id"] for record in extraction["created"]],
            }
            result["targetJobId"] = target_job_id
        return api_response(result)

    return UNHANDLED
