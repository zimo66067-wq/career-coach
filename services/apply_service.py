# -*- coding: utf-8 -*-
"""F5 投递闭环服务（阶段5）。

流程：求职信生成（模型优先/规则模板降级，pending_confirm=True）→
用户人工确认 → 申请跟踪落库。owner_key 由 api 层按登录用户/游客派生，
服务层不接触 request，保证可单测。
"""
import json
import re

from tools.api_errors import ApiError
from tools.database import (
    delete_application as _delete_row,
    get_resume_detail,
    list_applications as _list_rows,
    save_application as _save_row,
)
from tools.providers.model import build_model_router


def _profile_from_detail(detail):
    if not detail or not detail.get("diagnoses"):
        return {}
    diag = detail["diagnoses"][0]
    try:
        profile = json.loads(diag.get("diagnosis_json") or "{}")
    except (TypeError, ValueError):
        profile = {}
    return profile if isinstance(profile, dict) else {}


def _evidence_quotes(profile):
    quotes = []
    for item in (profile.get("subscores") or {}).values():
        if not isinstance(item, dict):
            continue
        for span in item.get("source_spans", []) or []:
            if isinstance(span, dict) and span.get("quote"):
                quote = str(span["quote"]).strip()
                if quote and quote not in quotes:
                    quotes.append(quote)
    return quotes


def _output_text(output, fields):
    if isinstance(output, dict):
        output = next((output.get(field) for field in fields if output.get(field)), "")
    text = str(output or "").strip()
    return text if 20 <= len(text) <= 800 else ""


def _grounded_in_evidence(candidate, evidence):
    """Require at least one four-character evidence fragment in model prose."""
    if not evidence:
        return False
    normalized_candidate = re.sub(r"\s+", "", candidate)
    for quote in evidence:
        normalized = re.sub(r"\s+", "", quote)
        if any(normalized[i:i + 4] in normalized_candidate for i in range(max(0, len(normalized) - 3))):
            return True
    return False


def generate_cover_letter(session_id, company="", position=""):
    """生成求职信候选（人工确认后才落库）。"""
    company = str(company or "").strip()
    position = str(position or "").strip()
    if not company or not position:
        raise ApiError("apply_info_required", "请填写目标公司与职位。", 422)
    detail = get_resume_detail(session_id)
    profile = _profile_from_detail(detail)
    if not profile:
        raise ApiError("diagnosis_required", "请先完成 F1 简历诊断。", 422)

    evidence = _evidence_quotes(profile)
    try:
        router = build_model_router()
    except ApiError:
        router = None
    if router is not None:
        try:
            prompt = (
                "你是一名求职信写作顾问。请基于以下简历亮点为「%s」的「%s」岗位"
                "写一封不超过 200 字的求职信正文：%s"
                % (company, position, "；".join(evidence[:3]))
            )
            result = router.call("cover_letter", prompt)
            if result.get("status") == "success" and result.get("output"):
                candidate = _output_text(
                    result["output"], ("candidate", "cover_letter", "content", "text")
                )
                if candidate and (company in candidate or position in candidate) and _grounded_in_evidence(candidate, evidence):
                    return {
                        "candidate": candidate,
                        "pending_confirm": True,
                        "basis": "model",
                        "session_id": session_id,
                        "company": company,
                        "position": position,
                    }
        except Exception:
            pass

    highlights = "；".join(evidence[:3]) if evidence else "（请在正文中补充 1-2 个可量化的项目成果）"
    candidate = (
        "尊敬的招聘负责人：\n"
        "您好！我是「%s」岗位的求职者，结合个人经历与岗位要求，我的核心匹配点如下：\n"
        "1. 项目经历：%s\n"
        "2. 技能匹配：具备与岗位职责直接相关的技能，并持续跟进问题闭环。\n"
        "期待有机会与您进一步沟通，感谢您的时间。\n"
        "此致敬礼"
    ) % (position, highlights)
    return {
        "candidate": candidate,
        "pending_confirm": True,
        "basis": "rule",
        "session_id": session_id,
        "company": company,
        "position": position,
    }


def create_application(session_id, owner_key, company, position, cover_letter, status="applied"):
    """人工确认后保存申请记录。"""
    company = str(company or "").strip()
    position = str(position or "").strip()
    cover_letter = str(cover_letter or "").strip()
    if not company or not position or len(cover_letter) < 10:
        raise ApiError("invalid_request", "公司、职位与求职信内容不完整。", 422)
    row = _save_row(
        session_id=session_id,
        owner_key=owner_key,
        company=company,
        position=position,
        cover_letter=cover_letter,
        status=status,
    )
    if row is None:
        raise ApiError("save_failed", "申请记录保存失败。", 500)
    return row


def list_applications_for(owner_key):
    return _list_rows(owner_key)


def delete_application(app_id, owner_key):
    """删除本人（或本游客）的申请记录；非本人返回 404。"""
    row = _delete_row(app_id, owner_key)
    if row is None:
        raise ApiError("not_found", "申请记录不存在或无权访问。", 404)
    return row


# ------------------------------------------------------------------ #
# 结果回流（Phase 4）：投递结果 → 状态推进 + 反向写证据
# ------------------------------------------------------------------ #

def record_outcome_feedback(application_id, owner_key, outcome, note=None):
    """记录一次投递结果：推进 7 态状态，并反向写一条**待确认**证据。

    三件事分开算账：

    1. **结果始终落库** —— 结果发生过就是事实，不因为状态机拒绝推进而丢弃。
    2. **状态推进可能被拒绝** —— 例如已 ``rejected`` 再补记 ``interview`` 是非法迁移。
       此时保留原状态并如实回报 ``statusApplied=False``，而不是静默改写历史。
    3. **证据只能是 pending** —— ``domain.application.evidence_from_outcome`` 强制
       ``source_type=application_outcome``，用户确认后才进可信事实。被拒/拿 offer 都只是
       **推断**（"我缺什么 / 我强在哪"），不能直接当事实用。

    Returns:
        dict: {application, outcome, evidence, evidenceCreated, statusApplied, requestedStatus}
    """
    from domain import application as application_domain
    from domain.errors import DomainError
    from repositories import application as application_repo
    from services import career_evidence_service as evidence_service
    from tools import database

    application = application_repo.get_for_owner(application_id, owner_key)
    if application is None:
        raise ApiError("not_found", "申请记录不存在或无权访问。", 404)

    now = database.utc_iso()
    try:
        record, next_status = application_domain.record_outcome(
            application, outcome, note=note, now=now
        )
        evidence_record = application_domain.evidence_from_outcome(
            application, outcome, note=note, now=now
        )
    except DomainError as error:
        raise ApiError(error.code, error.message, 422)

    status_applied = False
    if next_status and next_status != application.get("status"):
        try:
            application_domain.transition(application.get("status"), next_status)
        except DomainError:
            # 非法推进（补记历史结果时会遇到）—— 记结果，不改状态
            status_applied = False
        else:
            application_repo.set_status(application_id, owner_key, next_status)
            status_applied = True

    application_repo.add_outcome(record)
    evidence_service.ensure_profile(owner_key)
    created, skipped = evidence_service.persist_records(owner_key, [evidence_record])

    return {
        "application": application_repo.get_for_owner(application_id, owner_key),
        "outcome": record,
        "evidence": created[0] if created else None,
        "evidenceCreated": bool(created),
        "evidenceSkipped": skipped,
        "statusApplied": status_applied,
        "requestedStatus": next_status,
    }


def list_outcomes_for(application_id, owner_key):
    """一次申请的完整结果时间线。"""
    from repositories import application as application_repo

    application = application_repo.get_for_owner(application_id, owner_key)
    if application is None:
        raise ApiError("not_found", "申请记录不存在或无权访问。", 404)
    return application_repo.list_outcomes(application_id)
