# -*- coding: utf-8 -*-
"""F5 投递闭环服务（阶段5）。

流程：求职信生成（模型优先/规则模板降级，pending_confirm=True）→
用户人工确认 → 申请跟踪落库。owner_key 由 api 层按登录用户/游客派生，
服务层不接触 request，保证可单测。
"""
import json

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
                candidate = str(result["output"]).strip()[:800]
                if candidate:
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
