# -*- coding: utf-8 -*-
"""F5 投递闭环服务（阶段5）。

流程：求职信生成（模型优先/规则模板降级，pending_confirm=True）→
用户人工确认 → 申请跟踪落库。owner_key 由 api 层按登录用户/游客派生，
服务层不接触 request，保证可单测。
"""
import json
import re

from domain.target_job import OPEN_GAP_STATUSES, REQUIREMENT_TYPES, priority_for
from repositories import target_job as target_job_repo
from services import career_evidence_service as evidence_service
from services import target_job_service
from domain.internal.api_errors import ApiError
from repositories.database import (
    delete_application as _delete_row,
    get_resume_detail,
    list_applications as _list_rows,
    save_application as _save_row,
)
from providers import model as model_provider


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


# ------------------------------------------------------------------ #
# DoD #10 · 求职信接地：岗位要求 + 已确认证据（Phase 4b）
# ------------------------------------------------------------------ #
#
# 旧路径（不传 targetJobId）读的是 F1 诊断里模型抽的 span 引文 —— 那些**不是已确认事实**，
# 只是"模型觉得相关"的简历片段。DoD #10 要求求职信同时用上目标岗位与职业证据，这里就按
# Phase 3 定下的口径接：**下游只能读 `usable_evidence()`（= confirmed）**。
#
# 三条不可让步的规则：
#
# 1. **没有已确认证据就不请模型写。** 只给岗位要求、不给事实底座，模型一定会替用户编经历
#    （它受了"要匹配 JD"的强暗示）。宁可只给一个带占位符的框架。
# 2. **未覆盖的要求不许声称具备。** 缺口清单是"禁止声称"名单，不是写作素材；它只出现在
#    接口返回的元数据里让界面提示用户，不进正文（正文是给雇主看的，不是内部备忘）。
# 3. **正文里每一段经历都要能回指一条已确认证据。** 模型路径复用 `_grounded_in_evidence`
#    做四字片段校验；过不了就退规则模板，而不是放行一段无法核验的漂亮话。

#: 200 字的正文塞不下十几条要求 —— 贪多只会得到"我十分符合"这类空话。
MAX_LETTER_REQUIREMENTS = 5
MAX_LETTER_EVIDENCE = 3

_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2}

#: 没有任何已确认证据时，正文里给出的**明确占位**（不是编造，也不是沉默）。
EVIDENCE_PLACEHOLDER = "（请在正文中补充 1-2 个可量化的项目成果）"


def _letter_context(target_job_id, owner_key, company, position):
    """把岗位与证据压成一份"只允许引用这些事实"的底座。"""
    target = target_job_service.get_target_job(target_job_id, owner_key)  # 归属校验（非本人 404）
    company = str(company or "").strip() or str(target.get("company") or "").strip()
    position = str(position or "").strip() or str(target.get("position") or "").strip()

    requirements = []
    for row in target_job_service.requirements_of(target_job_id):
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        kind = str(row.get("req_type") or "")
        requirements.append({
            "id": row["id"],
            "text": text,
            "req_type": kind,
            "priority": priority_for(kind) if kind in REQUIREMENT_TYPES else "P2",
            "ordinal": row.get("ordinal") or 0,
        })
    requirements.sort(key=lambda item: (
        _PRIORITY_RANK.get(item["priority"], 9), item["ordinal"], item["id"]
    ))
    requirements = requirements[:MAX_LETTER_REQUIREMENTS]

    gaps = []
    for gap in target_job_repo.list_gaps(target_job_id):
        if gap.get("status") not in OPEN_GAP_STATUSES:
            continue
        gaps.append({
            "id": gap["id"],
            "priority": gap.get("priority"),
            "reason": str(gap.get("missing_evidence") or gap.get("reason") or "").strip(),
        })
    gaps.sort(key=lambda item: (_PRIORITY_RANK.get(item["priority"], 9), item["id"]))

    evidence = []
    for row in evidence_service.usable_evidence(owner_key):
        claim = str(row.get("claim") or "").strip()
        if not claim:
            continue
        evidence.append({
            "id": row["id"],
            "claim": claim,
            "quote": str(row.get("source_quote") or "").strip(),
        })
    evidence = evidence[:MAX_LETTER_EVIDENCE]

    return {"company": company, "position": position,
            "requirements": requirements, "gaps": gaps, "evidence": evidence}


def _grounded_prompt(company, position, requirements, evidence, gaps):
    requirement_lines = "\n".join(
        "- [%s] %s" % (item["priority"], item["text"]) for item in requirements
    ) or "（岗位要求为空）"
    evidence_lines = "\n".join("- %s" % item["claim"] for item in evidence)
    gap_lines = "\n".join(
        "- [%s] %s" % (item["priority"], item["reason"]) for item in gaps if item["reason"]
    ) or "（无）"
    return (
        "目标公司：%s\n目标职位：%s\n\n"
        "岗位要求（按优先级排序）：\n%s\n\n"
        "已确认的职业证据（这是**唯一**允许引用的事实）：\n%s\n\n"
        "尚未被证据覆盖的要求（**禁止**声称具备，也不要提及）：\n%s\n\n"
        "请写一封不超过 200 字的中文求职信正文，优先回应有证据支撑的要求。"
        % (company, position, requirement_lines, evidence_lines, gap_lines)
    )


def _grounded_template(company, position, evidence):
    """规则降级：只写"职位 + 已确认经历"，没有证据就留明确占位。"""
    salute = "尊敬的%s招聘负责人：" % ("%s " % company if company else "")
    if not evidence:
        return "\n".join([
            salute,
            "您好！我应聘「%s」岗位。" % position,
            EVIDENCE_PLACEHOLDER,
            "期待有机会与您进一步沟通，感谢您的时间。",
            "此致敬礼",
        ])
    return "\n".join([
        salute,
        "您好！我应聘「%s」岗位，以下是我可以核实的经历与成果：" % position,
        "；".join(item["claim"] for item in evidence) + "。",
        "这些经历与岗位要求直接相关，期待有机会与您进一步沟通，感谢您的时间。",
        "此致敬礼",
    ])


def _grounded_letter(session_id, context):
    """带 targetJobId 的求职信：事实底座 = 岗位要求 + 已确认证据。"""
    company = context["company"]
    position = context["position"]
    evidence = context["evidence"]
    requirements = context["requirements"]
    gaps = context["gaps"]
    quotes = [item["quote"] or item["claim"] for item in evidence]

    payload = {
        "pending_confirm": True,
        "session_id": session_id,
        "company": company,
        "position": position,
        "evidence": [{"id": item["id"], "claim": item["claim"]} for item in evidence],
        "requirements": [{"id": item["id"], "text": item["text"], "priority": item["priority"]}
                         for item in requirements],
        "gaps": [{"id": item["id"], "priority": item["priority"]} for item in gaps],
    }

    # 规则 1：没有已确认证据就不请模型写。空地会让模型替用户编经历。
    router = None
    if evidence:
        try:
            router = model_provider.build_model_router()
        except ApiError:
            router = None

    if router is not None:
        try:
            result = router.call(
                "cover_letter", _grounded_prompt(company, position, requirements, evidence, gaps)
            )
            if result.get("status") == "success" and result.get("output"):
                candidate = _output_text(
                    result["output"], ("candidate", "cover_letter", "content", "text")
                )
                if (candidate and (company in candidate or position in candidate)
                        and _grounded_in_evidence(candidate, quotes)):
                    payload.update({
                        "candidate": candidate,
                        "basis": "model",
                        "grounding": "target_job+evidence",
                        "notice": _letter_notice(evidence, gaps),
                    })
                    return payload
        except Exception:  # noqa: BLE001 - 模型失败一律降级，不影响出信
            pass

    payload.update({
        "candidate": _grounded_template(company, position, evidence),
        "basis": "rule",
        "grounding": "target_job+evidence" if evidence else "target_job_no_evidence",
        "notice": _letter_notice(evidence, gaps),
    })
    return payload


def _letter_notice(evidence, gaps):
    parts = []
    if evidence:
        parts.append("正文中的经历只来自你已确认的 %d 条职业证据，未确认的候选证据未被引用。"
                     % len(evidence))
    else:
        parts.append("你还没有确认任何职业证据，正文只有框架、未引用任何经历 —— "
                     "请先在证据档案里确认至少一条真实经历，再重新生成。")
    if gaps:
        parts.append("该岗位另有 %d 条要求没有已确认证据支撑，正文未声称具备。"
                     % len(gaps))
    return "".join(parts)


def generate_cover_letter(session_id, company="", position="", target_job_id=None, owner_key=None):
    """生成求职信候选（人工确认后才落库）。

    ``target_job_id`` 给了就走 DoD #10 的接地路径（岗位要求 + **已确认**职业证据，见
    ``_grounded_letter``）；不给则保持旧行为：只读 F1 诊断的 span 引文。
    """
    company = str(company or "").strip()
    position = str(position or "").strip()

    if target_job_id is not None:
        if not owner_key:
            raise ApiError("invalid_request", "缺少归属标识。", 422)
        context = _letter_context(int(target_job_id), owner_key, company, position)
        if not context["company"] or not context["position"]:
            raise ApiError("apply_info_required", "请填写目标公司与职位。", 422)
        return _grounded_letter(session_id, context)

    if not company or not position:
        raise ApiError("apply_info_required", "请填写目标公司与职位。", 422)
    detail = get_resume_detail(session_id)
    profile = _profile_from_detail(detail)
    if not profile:
        raise ApiError("diagnosis_required", "请先完成 F1 简历诊断。", 422)

    evidence = _evidence_quotes(profile)
    try:
        router = model_provider.build_model_router()
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
                        "grounding": "diagnosis",
                        "session_id": session_id,
                        "company": company,
                        "position": position,
                    }
        except Exception:
            pass

    highlights = "；".join(evidence[:3]) if evidence else EVIDENCE_PLACEHOLDER
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
        "grounding": "diagnosis",
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
    from repositories import database

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
