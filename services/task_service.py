# -*- coding: utf-8 -*-
"""F2 分片任务服务（阶段5：自 api/index.py 机械搬迁，行为不变）。"""
from tools.api_errors import ApiError
from tools.contracts import MIN_TEXT_CHARS


# Tasks（阶段3：客户端驱动分片任务）
# ------------------------------------------------------------------ #

_F2_TASK_CHUNK = 8

def _f2_assemble_result(payload, rows, major_code):
    """由分片判定结果汇总 F2 模式B 报告（与 api/f2_major.mode_b_result 同口径）。"""
    from api import f2_major

    profile = f2_major.PROFILE_INDEX.get(major_code)
    jd_text = str(payload.get("jd_text") or "")
    type_values = {t: [] for t in f2_major.MATCH_WEIGHTS}
    for row in rows:
        if row.get("status") == "unknown":
            continue
        type_values.setdefault(row.get("type"), []).append(
            {"covered": 1.0, "weak": 0.5, "missing": 0.0}[row.get("status")]
        )
    subscores = {}
    weighted, active = 0.0, 0.0
    for req_type, weight in f2_major.MATCH_WEIGHTS.items():
        values = type_values.get(req_type) or []
        score = round(sum(values) / len(values) * 100) if values else 0
        subscores[req_type] = {
            "label": f2_major.TYPE_LABELS.get(req_type, req_type),
            "score": score,
            "count": len(values),
        }
        if values:
            weighted += weight * score
            active += weight
    coverage = round(weighted / active) if active else 0
    occupation = f2_major.detect_occupation(jd_text, profile or {})
    if occupation:
        major_fit = f2_major.LEVEL_SCORE.get(occupation["level"], 50)
        major_fit_notice = "JD 命中职业「%s」（%s对应）" % (occupation["occupation"], occupation["level"])
    else:
        major_fit = None
        major_fit_notice = "未能识别 JD 对应职业画像，专业契合分暂不计入综合分。"
    overall = round(0.4 * major_fit + 0.6 * coverage) if major_fit is not None else coverage
    gaps = []
    for row in rows:
        if row.get("status") in ("covered", "unknown"):
            continue
        priority = "P0" if row.get("type") == "hard" else ("P1" if row.get("type") == "responsibility" else "P2")
        gaps.append({
            "level": priority,
            "text": row.get("text", ""),
            "action": "在简历中补充与该要求直接相关的真实经历、成果或技能证据。",
        })
    major_info = f2_major.MAJOR_INDEX[major_code]
    return {
        "mode": "B",
        "mode_notice": "模式B：JD 精准匹配（四态 + 专业契合度）。",
        "modeB": {
            "requirements": rows,
            "subscores": subscores,
            "coverage": coverage,
            "major_fit": major_fit,
            "major_fit_notice": major_fit_notice,
            "overall": overall,
            "occupation_hit": {
                "occupation": occupation["occupation"],
                "level": occupation["level"],
            } if occupation else None,
            "gaps": gaps,
        },
        "modeA": None,
        "major": {
            "code": major_code,
            "name": major_info["name"],
            "path": "%s / %s" % (major_info["category_name"], major_info["class_name"]),
        },
        "profile_status": "ready" if profile else "building",
        "scores": {
            "major_fit": major_fit,
            "coverage": coverage,
            "overall": overall,
            "major_fit_notice": major_fit_notice,
        },
    }


def _f2_match_chunk(step, payload, result):
    """F2 模式B 分片：step0 解析 JD 与分词，随后每片判定 8 条要求，最后汇总。"""
    from api import f2_major

    major_code = str(payload.get("major_code") or "")
    resume_text = str(payload.get("resume_text") or "")
    jd_text = str(payload.get("jd_text") or "")
    if major_code not in f2_major.MAJOR_INDEX:
        raise ApiError("major_required", "请先选择有效的专业。", 422)
    if len(resume_text) < MIN_TEXT_CHARS:
        raise ApiError("resume_too_short", "简历内容过短，请粘贴完整简历。", 422)

    if step == 0:
        requirements = f2_major.extract_requirements(jd_text)
        resume_tokens = sorted(f2_major.tokenize(resume_text))
        total = 1 + max(0, (len(requirements) + _F2_TASK_CHUNK - 1) // _F2_TASK_CHUNK)
        fragment = {"__requirements": requirements, "__resume_tokens": resume_tokens}
        if not requirements:
            fragment["__rows"] = []
            fragment["__result"] = _f2_assemble_result(payload, [], major_code)
            return 100, fragment, True, total
        return round((step + 1) / total * 100), fragment, False, total

    rows = list(result.get("__rows") or [])
    requirements = result.get("__requirements") or []
    resume_tokens = set(result.get("__resume_tokens") or [])
    start = (step - 1) * _F2_TASK_CHUNK
    for req in requirements[start:start + _F2_TASK_CHUNK]:
        status, hits = f2_major.judge_requirement(req["text"], resume_tokens, resume_text)
        rows.append({
            "id": req["id"],
            "type": req["type"],
            "typeLabel": f2_major.TYPE_LABELS.get(req["type"], req["type"]),
            "text": req["text"],
            "status": status,
            "evidence": hits,
        })
    total = 1 + max(0, (len(requirements) + _F2_TASK_CHUNK - 1) // _F2_TASK_CHUNK)
    done = start + _F2_TASK_CHUNK >= len(requirements)
    fragment = {"__rows": rows}
    if done:
        fragment["__result"] = _f2_assemble_result(payload, rows, major_code)
    progress = 100 if done else round((step + 1) / total * 100)
    return progress, fragment, done, total
