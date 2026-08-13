# -*- coding: utf-8 -*-
"""F1 简历诊断服务（阶段5：自 api/index.py 机械搬迁，行为不变）。

依赖模型路由（tools.providers.model）与契约校验（tools.contracts）；
无 key 时以规则降级（rule_fallback_diagnosis）交付。
"""
import json

from tools.api_errors import ApiError
from tools.contracts import RESUME_PROFILE_VALIDATOR, SUBSCORE_DEFAULTS
from tools.deidentify import deidentify
from tools.redflag import JSON_NOISE, RE_NUMBER, RE_PLACEHOLDER
from tools.rescore import calc_R, round2
from tools.trace import trace_id
from tools.validate_schema import business_rules


def profile_validation_errors(profile, resume_text):
    errors = []
    for error in sorted(RESUME_PROFILE_VALIDATOR.iter_errors(profile), key=str):
        path = "/".join(str(part) for part in error.absolute_path) or "(root)"
        errors.append("schema:%s" % path)
    try:
        business_rules(profile, errors)
    except (AttributeError, TypeError):
        errors.append("business_rule_type")

    for subscore in (profile.get("subscores") or {}).values():
        if not isinstance(subscore, dict):
            continue
        for span in subscore.get("source_spans", []):
            validate_source_span(span, resume_text, errors)
    for suggestion in profile.get("suggestions", []):
        if not isinstance(suggestion, dict):
            continue
        for span in suggestion.get("source_spans", []):
            validate_source_span(span, resume_text, errors)
    errors.extend(redflag_errors(profile, resume_text))
    return errors


def validate_source_span(span, resume_text, errors):
    if not isinstance(span, dict):
        return
    quote = span.get("quote")
    start = span.get("start")
    end = span.get("end")
    if not isinstance(quote, str) or not isinstance(start, int) or not isinstance(end, int):
        return
    if start < 0 or end <= start or end > len(resume_text) or resume_text[start:end] != quote:
        errors.append("source_span_not_grounded")


def fallback_source_span(resume_text):
    """Return a short, exact excerpt when the provider omitted location metadata."""
    start = next((index for index, char in enumerate(resume_text) if not char.isspace()), 0)
    end = min(len(resume_text), start + 160)
    return {
        "doc": "resume",
        "quote": resume_text[start:end],
        "start": start,
        "end": end,
    }


def normalize_source_spans(raw_spans, resume_text):
    """Fill omitted source-span fields and flag provider citations that cannot be proven."""
    if not isinstance(raw_spans, list):
        return [], False

    normalized = []
    for raw_span in raw_spans:
        if not isinstance(raw_span, dict):
            continue
        quote = raw_span.get("quote")
        start = raw_span.get("start")
        end = raw_span.get("end")

        if isinstance(quote, str) and quote:
            if isinstance(start, int) and isinstance(end, int):
                if start < 0 or end <= start or end > len(resume_text) or resume_text[start:end] != quote:
                    return [], True
            else:
                start = resume_text.find(quote)
                end = start + len(quote)
                if start < 0:
                    return [], True
        elif isinstance(start, int) and isinstance(end, int):
            if start < 0 or end <= start or end > len(resume_text):
                return [], True
            quote = resume_text[start:end]
        else:
            continue

        normalized.append({
            "doc": "resume",
            "quote": quote,
            "start": start,
            "end": end,
        })
    return normalized, False


def normalize_score(raw_score):
    """Keep a provider score only when it is a finite numeric value."""
    if isinstance(raw_score, dict):
        raw_score = raw_score.get("score")
    if isinstance(raw_score, bool):
        return 50
    if isinstance(raw_score, (int, float)) and raw_score == raw_score:
        return max(0, min(100, raw_score))
    if isinstance(raw_score, str) and re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", raw_score):
        return max(0, min(100, float(raw_score)))
    return 50


def has_unsupported_number(text, resume_text):
    placeholder_numbers = set(RE_PLACEHOLDER.findall(text))
    for match in RE_NUMBER.finditer(text):
        number = match.group(1)
        if number in placeholder_numbers or number in JSON_NOISE:
            continue
        variants = {number, number + "%"}
        if "." in number:
            variants.add(number.rstrip("0").rstrip("."))
        if not any(value in resume_text for value in variants):
            return True
    return False


def safe_narrative(value, fallback, resume_text):
    """Avoid presenting provider prose that contains unsupported facts."""
    if not isinstance(value, str):
        return fallback
    candidate = value.strip()
    if not candidate or has_unsupported_number(candidate, resume_text):
        return fallback
    return candidate


def normalize_resume_profile(raw_profile, resume_text):
    """Adapt known provider shape omissions into the frozen public contract."""
    raw_subscores = raw_profile.get("subscores") if isinstance(raw_profile.get("subscores"), dict) else {}
    normalized_subscores = {}
    for key, label in SUBSCORE_DEFAULTS.items():
        raw_subscore = raw_subscores.get(key)
        raw_data = raw_subscore if isinstance(raw_subscore, dict) else {}
        spans, has_invalid_quote = normalize_source_spans(raw_data.get("source_spans"), resume_text)
        if has_invalid_quote:
            spans = [fallback_source_span(resume_text)]
        elif not spans:
            spans = [fallback_source_span(resume_text)]
        rationale = "%s仅基于所引用的简历原文进行评估。" % label
        if not has_invalid_quote:
            rationale = safe_narrative(raw_data.get("rationale"), rationale, resume_text)
        normalized_subscores[key] = {
            "score": normalize_score(raw_subscore),
            "rationale": rationale,
            "source_spans": spans,
        }

    raw_suggestions = raw_profile.get("suggestions") if isinstance(raw_profile.get("suggestions"), list) else []
    normalized_suggestions = []
    for index, raw_suggestion in enumerate(raw_suggestions):
        if not isinstance(raw_suggestion, dict):
            continue
        spans, has_invalid_quote = normalize_source_spans(raw_suggestion.get("source_spans"), resume_text)
        if has_invalid_quote:
            spans = [fallback_source_span(resume_text)]
        elif not spans:
            spans = [fallback_source_span(resume_text)]
        issue = "当前简历中存在可进一步核实和完善的表达。"
        suggestion_text = "请根据已引用的简历原文，补充职责、成果和技能的可核验证据。"
        if not has_invalid_quote:
            issue = safe_narrative(raw_suggestion.get("issue"), issue, resume_text)
            suggestion_text = safe_narrative(raw_suggestion.get("suggestion"), suggestion_text, resume_text)
        suggestion = {
            "id": raw_suggestion.get("id") if isinstance(raw_suggestion.get("id"), str) and raw_suggestion["id"].strip() else "suggestion-%s" % (index + 1),
            "severity": raw_suggestion.get("severity") if raw_suggestion.get("severity") in {"P0", "P1", "P2"} else "P1",
            "issue": issue,
            "suggestion": suggestion_text,
            "source_spans": spans,
        }
        rewrite_draft = ""
        if not has_invalid_quote:
            rewrite_draft = safe_narrative(raw_suggestion.get("rewrite_draft"), "", resume_text)
        if rewrite_draft:
            suggestion["rewrite_draft"] = rewrite_draft
        normalized_suggestions.append(suggestion)

    if not normalized_suggestions:
        normalized_suggestions.append({
            "id": "suggestion-1",
            "severity": "P1",
            "issue": "当前模型结果未提供完整的可展示建议。",
            "suggestion": "请根据已引用的简历原文，补充职责、成果和技能的可核验证据。",
            "source_spans": [fallback_source_span(resume_text)],
        })

    return {
        "version": "1.0",
        "pii_removed": True,
        "subscores": normalized_subscores,
        "suggestions": normalized_suggestions,
    }


def redflag_errors(profile, resume_text):
    """Apply redflag.py's numeric fact-lock without persisting user content."""
    strings = []
    for subscore in (profile.get("subscores") or {}).values():
        if isinstance(subscore, dict) and isinstance(subscore.get("rationale"), str):
            strings.append(subscore["rationale"])
    for suggestion in profile.get("suggestions", []):
        if not isinstance(suggestion, dict):
            continue
        for field in ("issue", "suggestion", "rewrite_draft"):
            if isinstance(suggestion.get(field), str):
                strings.append(suggestion[field])
    joined = "\n".join(strings)
    placeholder_numbers = set(RE_PLACEHOLDER.findall(joined))
    unsupported = set()
    for match in RE_NUMBER.finditer(joined):
        number = match.group(1)
        if number in placeholder_numbers or number in JSON_NOISE:
            continue
        variants = {number, number + "%"}
        if "." in number:
            variants.add(number.rstrip("0").rstrip("."))
        if not any(value in resume_text for value in variants):
            unsupported.add(number)
    return ["unsupported_number:%s" % number for number in sorted(unsupported)]


def rule_score(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, int(value)))


def count_present_terms(text, terms):
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered)


def build_rule_based_resume_profile(resume_text):
    """Produce a transparent, evidence-bound fallback when models are unavailable."""
    span = fallback_source_span(resume_text)
    section_count = count_present_terms(resume_text, (
        "教育", "经历", "项目", "技能", "实习", "工作", "奖项", "证书",
    ))
    action_count = count_present_terms(resume_text, (
        "负责", "完成", "优化", "开发", "设计", "推动", "协作", "上线", "分析", "管理",
    ))
    skill_count = count_present_terms(resume_text, (
        "python", "java", "javascript", "sql", "excel", "figma", "linux", "git", "ai", "数据",
    ))
    number_count = len(RE_NUMBER.findall(resume_text))
    line_count = len([line for line in resume_text.splitlines() if line.strip()])

    scores = {
        "structure": rule_score(38 + section_count * 7 + min(line_count, 10) * 2),
        "clarity": rule_score(45 + min(line_count, 12) * 2 + min(action_count, 5) * 3),
        "achievement_evidence": rule_score(35 + min(action_count, 7) * 5 + min(number_count, 5) * 6),
        "skill_evidence": rule_score(38 + min(skill_count, 8) * 6),
        "ats_readability": rule_score(50 + min(section_count, 6) * 5 + min(line_count, 10)),
    }
    rationales = {
        "structure": "依据简历原文中的标题和段落组织进行基础规则检查。",
        "clarity": "依据简历原文的分行和行动表达进行基础规则检查。",
        "achievement_evidence": "依据简历原文中可见的行动词和量化文本进行基础规则检查。",
        "skill_evidence": "依据简历原文中可见的技能关键词进行基础规则检查。",
        "ats_readability": "依据简历原文的常见栏目和文本可读性进行基础规则检查。",
    }
    suggestions = [
        {
            "id": "rule-evidence",
            "severity": "P1",
            "issue": "请复核已引用段落中的职责与成果表达。",
            "suggestion": "为关键项目补充可公开核验的职责、动作和结果，并确保新增数字与原始材料一致。",
            "source_spans": [span],
        },
        {
            "id": "rule-structure",
            "severity": "P2",
            "issue": "请复核已引用段落中的栏目组织和技能呈现。",
            "suggestion": "使用清晰栏目和统一格式呈现经历与技能，方便招聘系统和人工阅读。",
            "source_spans": [span],
        },
    ]
    return {
        "version": "1.0",
        "pii_removed": True,
        "subscores": {
            key: {"score": scores[key], "rationale": rationales[key], "source_spans": [span]}
            for key in SUBSCORE_DEFAULTS
        },
        "suggestions": suggestions,
    }


def rule_fallback_diagnosis(resume_text, reason, trace=None):
    """Return a usable, explicitly labeled result rather than an opaque 503."""
    fallback_profile = build_rule_based_resume_profile(resume_text)
    fallback_trace = trace or trace_id()
    print(json.dumps({
        "event": "resume_rule_fallback",
        "trace_id": fallback_trace,
        "reason": reason,
    }, ensure_ascii=False), flush=True)
    score_r = round2(calc_R({
        key: value["score"] for key, value in fallback_profile["subscores"].items()
    }))
    return (
        fallback_profile,
        score_r,
        fallback_trace,
        "rule_fallback",
        "诊断模型暂时不可用，本次展示基于简历原文的基础规则诊断；恢复后可再次诊断以获取模型解释。",
    )


def diagnose_resume(resume_text):
    cleaned_text, _mapping = deidentify(resume_text)
    try:
        from api.index import build_model_router  # runtime lookup keeps monkeypatch compat

        router = build_model_router()
        result = router.call("resume_diagnosis", cleaned_text)
    except ApiError as error:
        if error.code == "model_not_configured":
            return rule_fallback_diagnosis(cleaned_text, error.code)
        raise
    except Exception as error:
        return rule_fallback_diagnosis(cleaned_text, "router_exception:%s" % type(error).__name__)

    if not isinstance(result, dict) or result.get("status") != "success" or not isinstance(result.get("output"), dict):
        result_trace = result.get("trace_id") if isinstance(result, dict) else None
        return rule_fallback_diagnosis(cleaned_text, "model_unavailable", result_trace)

    profile = normalize_resume_profile(result["output"], cleaned_text)
    validation_errors = profile_validation_errors(profile, cleaned_text)
    if validation_errors:
        print(json.dumps({
            "event": "resume_validation_rejected",
            "trace_id": result.get("trace_id"),
            "error_codes": sorted(set(validation_errors))[:20],
        }, ensure_ascii=False), flush=True)
        return rule_fallback_diagnosis(cleaned_text, "validation_rejected", result.get("trace_id"))

    score_r = round2(calc_R({
        key: value["score"] for key, value in profile["subscores"].items()
    }))
    if result.get("degraded"):
        return (
            profile,
            score_r,
            result.get("trace_id") or trace_id(),
            "fallback_model",
            "主模型暂时不可用，本次由备用模型完成诊断。",
        )
    return profile, score_r, result.get("trace_id") or trace_id(), "model", ""


# ------------------------------------------------------------------ #
