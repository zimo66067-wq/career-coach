# -*- coding: utf-8 -*-
"""F2 JD 解析与匹配服务（阶段5：自 api/index.py 机械搬迁，行为不变）。"""
import re

from tools.api_errors import ApiError
from tools.contracts import JOB_PROFILE_VALIDATOR
from tools.deidentify import deidentify
from tools.redflag import RE_NUMBER
from tools.match_requirements import (
    Bm25Matcher,
    judge,
    split_sentences,
    tokenize,
    unigrams,
)


# ------------------------------------------------------------------ #

JOB_TYPE_LABELS = {
    "hard": "硬性要求",
    "responsibility": "岗位职责",
    "preferred": "加分项",
    "terminology": "术语与工具",
}
MATCH_WEIGHTS = {
    "hard": 0.50,
    "responsibility": 0.25,
    "preferred": 0.15,
    "terminology": 0.10,
}
RESUME_TOO_SHORT_CHARS = 200
RESUME_SECTION_KEYWORDS = ("教育", "经历", "项目", "技能", "实习", "工作", "奖项", "证书")
JOB_SECTION_HINTS = (
    (("岗位职责", "工作职责", "职位职责", "工作内容", "你将负责"), "responsibility"),
    (("任职要求", "职位要求", "岗位要求", "基本要求", "硬性要求", "资格要求"), "hard"),
    (("加分项", "优先条件", "优先考虑", "bonus"), "preferred"),
    (("技术栈", "工具", "术语", "技术要求"), "terminology"),
)
PROMPT_INJECTION_PATTERN = re.compile(
    r"(?:忽略(?:以上|之前|前面)|ignore\s+(?:previous|above)|system\s+prompt|提示词|指令注入)",
    re.IGNORECASE,
)


def job_requirement_type(text, active_type):
    lowered = text.lower()
    for hints, requirement_type in JOB_SECTION_HINTS:
        if any(hint.lower() in lowered for hint in hints):
            return requirement_type
    if any(word in text for word in ("负责", "协同", "推进", "交付", "维护")):
        return "responsibility"
    if any(word in text for word in ("优先", "加分", "有过")):
        return "preferred"
    return active_type or "hard"


def strip_requirement_prefix(text):
    cleaned = re.sub(r"^[\s•·●▪◆\-—]+", "", text).strip()
    cleaned = re.sub(r"^\d+[.、)）]\s*", "", cleaned)
    cleaned = re.sub(r"^(?:任职要求|岗位职责|工作职责|职位要求|岗位要求|加分项|技术栈|工具)[：:\s]*", "", cleaned)
    return cleaned.strip()


def injection_flags(text):
    flags = []
    for match in PROMPT_INJECTION_PATTERN.finditer(text):
        flags.append({
            "quote": match.group(0),
            "start": match.start(),
            "end": match.end(),
            "reason": "疑似指令性文本，已按普通 JD 文本处理。",
        })
    return flags


def build_job_profile(job_text):
    requirements = []
    active_type = "hard"
    offset = 0
    job_title = ""
    for raw_line in job_text.splitlines(keepends=True):
        line = raw_line.strip()
        line_start = offset + (len(raw_line) - len(raw_line.lstrip()))
        offset += len(raw_line)
        if not line:
            continue
        title_match = re.match(r"^(?:职位名称|岗位名称|招聘职位|职位|岗位)[：:]\s*(.{2,80})$", line)
        if title_match and not job_title:
            job_title = title_match.group(1).strip()
            continue
        matched_heading = None
        for hints, requirement_type in JOB_SECTION_HINTS:
            if line.rstrip("：:") in hints:
                active_type = requirement_type
                matched_heading = True
                break
        if matched_heading:
            continue
        requirement_text = strip_requirement_prefix(line)
        if len(requirement_text) < 4:
            continue
        quote_start = job_text.find(line, max(0, line_start - 2))
        if quote_start < 0:
            quote_start = line_start
        requirements.append({
            "id": "req_%02d" % (len(requirements) + 1),
            "type": job_requirement_type(line, active_type),
            "text": requirement_text[:500],
            "source_span": {
                "doc": "job",
                "quote": line,
                "start": quote_start,
                "end": quote_start + len(line),
            },
        })
        if len(requirements) >= 30:
            break

    if not requirements:
        for match in re.finditer(r"[^。；;！？!?]{4,500}", job_text):
            quote = match.group(0).strip()
            if not quote:
                continue
            requirements.append({
                "id": "req_%02d" % (len(requirements) + 1),
                "type": job_requirement_type(quote, "hard"),
                "text": strip_requirement_prefix(quote),
                "source_span": {"doc": "job", "quote": quote, "start": match.start(), "end": match.end()},
            })
            if len(requirements) >= 30:
                break

    profile = {
        "version": "1.0",
        "user_confirmed": False,
        "requirements": requirements,
        "prompt_injection_flags": injection_flags(job_text),
    }
    if job_title:
        profile["job_title"] = job_title
    errors = sorted(JOB_PROFILE_VALIDATOR.iter_errors(profile), key=str)
    if errors:
        raise ApiError("invalid_jd_text", "未能从 JD 中识别出可匹配的岗位要求，请补充职责或任职要求。", 422)
    return profile


def validate_job_profile(value):
    if not isinstance(value, dict):
        raise ApiError("invalid_job_profile", "岗位要求解析结果无效，请重新提交 JD。", 422)
    errors = sorted(JOB_PROFILE_VALIDATOR.iter_errors(value), key=str)
    if errors or not value.get("user_confirmed"):
        raise ApiError("invalid_job_profile", "岗位要求解析结果无效，请重新提交 JD。", 422)
    return value


def requirement_status_counts(requirements, requirement_type):
    items = [r for r in requirements if r.get("type") == requirement_type]
    counts = {"covered": 0, "weak": 0, "missing": 0, "unknown": 0}
    for item in items:
        status = item.get("status")
        if status in counts:
            counts[status] += 1
    return items, counts


def _coverage_sentence(counts, total, label):
    matched = counts["covered"] + counts["weak"]
    if total == 0:
        return None
    if counts["missing"] or counts["unknown"]:
        return "岗位的%s共 %d 项，目前仅有 %d 项能找到部分关联素材，其余项目前覆盖不足或材料不足以判断。" % (
            label, total, matched)
    return "岗位的%s共 %d 项，简历中均能找到可回指的关联素材。" % (label, total)


def build_low_score_analysis(resume_text, requirements, score_m, resume_too_short):
    """生成低分/材料不足的中长文本分析（规则驱动，不少于 3 个角度）。

    文案口径：委婉、可执行、基于真实匹配数据，不做能力贬低。
    """
    hard_items, hard_c = requirement_status_counts(requirements, "hard")
    resp_items, resp_c = requirement_status_counts(requirements, "responsibility")
    pref_items, pref_c = requirement_status_counts(requirements, "preferred")
    term_items, term_c = requirement_status_counts(requirements, "terminology")

    dimensions = []

    hard_sentence = _coverage_sentence(hard_c, len(hard_items), "硬性要求")
    if hard_sentence:
        dimensions.append({
            "angle": "硬性要求覆盖",
            "level": "P0" if hard_c["missing"] else "P1",
            "finding": hard_sentence + " 硬性要求通常是岗位的准入条件，覆盖不足对匹配分影响最大。",
            "advice": "优先为未覆盖的硬性要求补充真实经历或技能证据，并确保表述与要求对应。",
        })

    resp_sentence = _coverage_sentence(resp_c, len(resp_items), "岗位职责")
    if resp_sentence:
        dimensions.append({
            "angle": "经历与职责匹配",
            "level": "P1" if resp_c["missing"] else "P2",
            "finding": resp_sentence + " 职责类要求的匹配依赖简历中的经历描述，描述越具体越容易被识别。",
            "advice": "建议用「负责…、通过…、结果…」的结构重写相关经历，突出你在其中的动作与产出。",
        })

    term_total = len(term_items) + len(pref_items)
    term_matched = (term_c["covered"] + term_c["weak"] + pref_c["covered"] + pref_c["weak"])
    if term_total:
        dimensions.append({
            "angle": "技能与术语覆盖",
            "level": "P1" if term_total - term_matched else "P2",
            "finding": "岗位涉及的技能与术语共 %d 项，简历中出现相关表述的 %d 项；术语缺失会直接影响关键词层面的匹配。" % (
                term_total, term_matched),
            "advice": "在真实经历的基础上，补充与岗位匹配的工具、框架与关键词，避免空泛罗列。",
        })

    section_count = sum(1 for kw in RESUME_SECTION_KEYWORDS if kw in resume_text)
    number_count = len(RE_NUMBER.findall(resume_text))
    material_parts = []
    if resume_too_short:
        material_parts.append("简历正文约 %d 字，篇幅较短，可供核验的素材有限" % len(resume_text))
    if section_count < 4:
        material_parts.append("常见板块（教育、经历、项目、技能等）出现 %d 处" % section_count)
    if number_count < 3:
        material_parts.append("量化成果较少（全文数字类表述 %d 处）" % number_count)
    if material_parts:
        dimensions.append({
            "angle": "材料完整度",
            "level": "P2",
            "finding": "；".join(material_parts) + "。完整且量化的简历有助于系统识别信息，也更容易让招聘方快速理解你的能力。",
            "advice": "补充项目细节、职责描述与真实可核验的数字，保持结构清晰。",
        })

    if len(dimensions) < 3:
        dimensions.append({
            "angle": "整体匹配度",
            "level": "P2",
            "finding": "当前简历与目标岗位之间的可核验关联素材整体偏少，导致匹配分偏低。",
            "advice": "围绕岗位要求逐条补齐真实经历与成果，匹配度会随之改善。",
        })

    return {
        "summary": (
            "本次匹配得分 %s 分，低于 50 分，主要原因是简历与目标岗位之间可核验的关联素材不足。"
            "以下从几个角度说明差距，供你参考——这些都可以通过补充真实素材来改进，不必把它看作能力否定。"
        ) % score_m,
        "dimensions": dimensions,
        "suggestion": (
            "建议按优先级改进：1) 为硬性要求补充直接相关的真实经历与量化成果；"
            "2) 用具体职责句重写经历；3) 补充与岗位匹配的技能与术语；"
            "4) 完善简历结构。所有补充都应以真实经历为基础。"
        ),
    }


def match_job_profile(resume_text, job_profile):
    cleaned_resume, _mapping = deidentify(resume_text)
    sentences = split_sentences(cleaned_resume) or [cleaned_resume]
    sentence_tokens = [tokenize(sentence) for sentence in sentences]
    sentence_unigrams = [unigrams(sentence) for sentence in sentences]
    document_unigrams = unigrams(cleaned_resume)
    matcher = Bm25Matcher()
    requirements = []
    type_values = {name: [] for name in MATCH_WEIGHTS}

    for requirement in job_profile["requirements"]:
        confidence, sentence_index = matcher.best(
            requirement["text"], sentence_tokens, sentence_unigrams, document_unigrams
        )
        query_words = unigrams(requirement["text"])
        partial = bool(query_words & document_unigrams)
        status = judge(confidence, partial)
        result = {
            "id": requirement["id"],
            "type": requirement["type"],
            "typeLabel": JOB_TYPE_LABELS[requirement["type"]],
            "text": requirement["text"],
            "status": status,
            "evidence": sentences[sentence_index] if status in {"covered", "weak"} and sentence_index >= 0 else "",
        }
        requirements.append(result)
        if status != "unknown":
            type_values[requirement["type"]].append({"covered": 1.0, "weak": 0.5, "missing": 0.0}[status])

    subscores = {}
    weighted_score = 0.0
    active_weight = 0.0
    for requirement_type, weight in MATCH_WEIGHTS.items():
        values = type_values[requirement_type]
        score = round(sum(values) / len(values) * 100) if values else 0
        subscores[requirement_type] = {"label": JOB_TYPE_LABELS[requirement_type], "score": score}
        if values:
            weighted_score += weight * score
            active_weight += weight
    score_m = round(weighted_score / active_weight) if active_weight else 0

    gaps = []
    for item in requirements:
        if item["status"] == "covered" or item["status"] == "unknown":
            continue
        priority = "P0" if item["type"] == "hard" else ("P1" if item["type"] == "responsibility" else "P2")
        gaps.append({
            "level": priority,
            "text": item["text"],
            "action": "在简历中补充与该要求直接相关的真实经历、成果或技能证据。",
        })

    resume_too_short = len(cleaned_resume) < RESUME_TOO_SHORT_CHARS
    all_unknown = bool(requirements) and all(r["status"] == "unknown" for r in requirements)
    insufficient_evidence = False
    low_score_analysis = None
    if all_unknown:
        insufficient_evidence = True
        score_m = None
        gaps = []
        match_notice = (
            "本次使用基于简历原文的规则关键词匹配；未调用模型。"
            "当前简历与岗位要求的可比材料不足，无法计算匹配分；"
            "建议补充与岗位相关的真实经历与技能后再试。"
        )
    elif score_m < 50 or resume_too_short:
        low_score_analysis = build_low_score_analysis(
            cleaned_resume, requirements, score_m, resume_too_short
        )
        if resume_too_short:
            match_notice = (
                "本次使用基于简历原文的规则关键词匹配；未调用模型。"
                "检测到简历内容较短，匹配结果可能不充分，下方已说明主要差距与改进建议。"
            )
        else:
            match_notice = (
                "本次使用基于简历原文的规则关键词匹配；未调用模型。"
                "匹配分低于 50，下方已从多个角度说明主要差距与改进建议。"
            )
    else:
        match_notice = "本次使用基于简历原文的规则关键词匹配；未调用模型。"

    return {
        "score_M": score_m,
        "subscores": subscores,
        "requirements": requirements,
        "gaps": gaps,
        "match_mode": "rule_bm25",
        "match_notice": match_notice,
        "resume_length": len(cleaned_resume),
        "resume_too_short": resume_too_short,
        "insufficient_evidence": insufficient_evidence,
        "low_score_analysis": low_score_analysis,
    }


# ------------------------------------------------------------------ #
