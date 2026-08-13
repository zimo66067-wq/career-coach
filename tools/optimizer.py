# -*- coding: utf-8 -*-
"""optimizer.py · 简历优化器（阶段4）

基于 F1 诊断 suggestions 生成可复写段落。
有模型 key 时经 model_router 生成；无 key 时使用规则模板降级，
输出统一带 pending_confirm 标记，用户确认后才由 API 落库。
"""
import re

_PATTERN_RULES = [
    {
        "keys": ["量化", "成果", "具体", "可验证", "数据"],
        "template": (
            "将“{issue}”改写为可量化表达：补充该项工作的影响范围、产出数字"
            "（如处理量级、耗时下降、转化/效率提升百分比）与可验证的证据来源。"
        ),
    },
    {
        "keys": ["技能", "证据", "能力"],
        "template": (
            "为“{issue}”补充技能证据：写明在哪个项目/场景中使用了该技能、"
            "解决了什么问题、产出了什么结果，让技能有出处而非罗列。"
        ),
    },
    {
        "keys": ["结构", "清晰", "ATS", "可读"],
        "template": (
            "针对“{issue}”调整表达结构：先写结论（角色+成果），再写过程要点，"
            "使用短句与项目符号，确保关键词可被 ATS 识别。"
        ),
    },
]


def _pick_rule(issue):
    issue = str(issue or "")
    best, best_hits = None, 0
    for rule in _PATTERN_RULES:
        hits = sum(1 for k in rule["keys"] if k in issue)
        if hits > best_hits:
            best, best_hits = rule, hits
    return best


def _evidence_from_profile(profile):
    """从诊断 profile 中提取可引用的原文片段（最多 3 段，各 60 字）。"""
    if not isinstance(profile, dict):
        return []
    spans = []
    for sub in (profile.get("subscores") or {}).values():
        for span in (sub.get("source_spans") or []):
            quote = str(span.get("quote") or "").strip()
            if len(quote) >= 4:
                spans.append(quote[:60])
    seen, out = set(), []
    for q in spans:
        if q not in seen:
            seen.add(q)
            out.append(q)
        if len(out) >= 3:
            break
    return out


def rewrite_suggestion(suggestion, resume_profile=None, model_router=None):
    """生成改写候选。

    Returns:
        dict: {"candidate": str, "pending_confirm": True, "basis": str,
               "suggestion_id": str, "severity": str}
    """
    suggestion = suggestion if isinstance(suggestion, dict) else {}
    issue = str(suggestion.get("issue") or "描述不够具体")
    suggestion_text = str(suggestion.get("suggestion") or "")
    severity = str(suggestion.get("severity") or "P2")
    suggestion_id = str(suggestion.get("id") or "")
    rule = _pick_rule(issue)

    if model_router is not None:
        try:
            prompt = (
                "你是一名资深简历优化顾问。请基于以下诊断建议生成一段可直接"
                "粘贴进简历的改写段落，要求具体、有证据导向、不超过 120 字。"
                "\n诊断问题：%s\n建议：%s"
                % (issue, suggestion_text)
            )
            result = model_router.call(system="", user=prompt)
            if result.get("status") == "success" and result.get("output"):
                candidate = str(result["output"]).strip()[:300]
                basis = "model"
                return {
                    "candidate": candidate,
                    "pending_confirm": True,
                    "basis": basis,
                    "suggestion_id": suggestion_id,
                    "severity": severity,
                }
        except Exception:
            pass

    evidence = _evidence_from_profile(resume_profile)
    if rule is not None:
        body = rule["template"].format(issue=issue)
    else:
        body = (
            "针对“{issue}”进行改写：保留事实，补充背景、动作与结果，"
            "让表述更具体、更可验证。".format(issue=issue)
        )
    candidate = body
    if evidence:
        candidate += "可参考的原文片段：" + "；".join(evidence) + "。"
    candidate += "（请补充准确数字后使用）"
    return {
        "candidate": candidate,
        "pending_confirm": True,
        "basis": "rule",
        "suggestion_id": suggestion_id,
        "severity": severity,
    }
