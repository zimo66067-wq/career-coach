# -*- coding: utf-8 -*-
"""F2 专业导向岗位匹配 API（迭代一：本科 + Top30 画像 + 双分制）。

本地演示：
    python api/f2_major.py           # 127.0.0.1:8123，同时托管 ui/prototype 静态页

Vercel：
    vercel.json 中将 /api/f2/* 重写到统一的 api/index.py 入口。
"""
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
MAJORS_PATH = ROOT / "data" / "f2" / "majors_2025.json"
PROFILES_PATH = ROOT / "data" / "f2" / "profiles_top30.json"
PROTOTYPE_DIR = ROOT / "ui" / "prototype"

app = Flask(__name__)

LEVEL_SCORE = {"强": 100, "较强": 82, "较弱": 58, "弱": 40, "无关": 15, "无对应": 5}
MATCH_WEIGHTS = {"hard": 0.50, "responsibility": 0.25, "bonus": 0.15, "term": 0.10}
TYPE_LABELS = {
    "hard": "硬性要求",
    "responsibility": "职责",
    "bonus": "加分项",
    "term": "术语",
}

INTENT_MAP = {
    "程序员": ["080901", "080902"],
    "写代码": ["080901", "080902"],
    "编程": ["080901", "080902"],
    "开发": ["080901", "080902", "080703"],
    "后端": ["080901", "080902"],
    "前端": ["080901", "080902", "080906"],
    "软件开发": ["080902", "080901"],
    "cs": ["080901", "080902"],
    "算法": ["080901", "080717", "070101"],
    "人工智能": ["080717", "080901"],
    "ai": ["080717", "080901"],
    "机器学习": ["080717", "080901", "071203"],
    "大模型": ["080717", "080901"],
    "数据分析": ["080910", "071201", "120102"],
    "数据": ["080910", "071201", "120102"],
    "金融": ["020301", "020101", "071201"],
    "银行": ["020301", "020101"],
    "会计": ["120203", "120201"],
    "财务": ["120203", "120201"],
    "审计": ["120203"],
    "律师": ["030101"],
    "法务": ["030101"],
    "法律": ["030101"],
    "教师": ["040101", "050101", "070101", "050201"],
    "教学": ["040101", "050101"],
    "医生": ["100201"],
    "临床": ["100201"],
    "护士": ["101101"],
    "护理": ["101101"],
    "设计": ["130508", "080202"],
    "ui": ["130508"],
    "新媒体": ["050301", "120202", "130508"],
    "运营": ["120202", "120102", "050301"],
    "市场": ["120202", "020101"],
    "销售": ["120202", "020401"],
    "外贸": ["020401", "050201"],
    "翻译": ["050201"],
    "机械": ["080202", "080801"],
    "电气": ["080601", "080801"],
    "土木": ["081001"],
    "建筑": ["081001"],
    "化工": ["081301"],
    "电子": ["080701", "080703"],
    "芯片": ["080710", "080701"],
    "芯片设计": ["080710", "080701"],
    "集成电路": ["080710", "083204"],
    "集成电路设计": ["080710", "080701"],
    "新能源": ["080503", "080414", "080504", "080216", "080501"],
    "电池": ["080414", "080504", "080401", "081304"],
    "储能": ["080504", "080414", "080501"],
    "通信": ["080703", "080701"],
    "安全": ["080904", "080901"],
    "产品经理": ["120102", "080902", "120201"],
    "运维": ["080901", "080902", "080703"],
    "人力": ["120201", "071101"],
    "hr": ["120201", "071101"],
    "心理": ["071101"],
    "统计": ["071201", "070101"],
}

# Common names are explicit data, not fuzzy guesses.  Exact alias handling
# keeps short abbreviations useful without matching unrelated two-character
# fragments across the whole 845-major catalog.
MAJOR_ALIAS_MAP = {
    "计科": ["080901"],
    "软工": ["080902"],
    "信安": ["080904"],
    "网安": ["080904"],
    "大数据": ["080910"],
    "集成电路": ["080710", "083204"],
    "电科": ["080702"],
    "数媒": ["080906", "130508"],
}

INTENT_CONTEXT_MARKERS = (
    "想做", "从事", "求职", "就业", "岗位", "职位", "职业", "方向",
    "工程师", "专员", "经理", "工作", "实习", "研发", "设计", "分析", "运营",
)


def load_majors():
    data = json.loads(MAJORS_PATH.read_text(encoding="utf-8"))
    index = {}
    for cat in data["categories"]:
        for cls in cat["classes"]:
            for m in cls["majors"]:
                index[m["code"]] = {
                    **m,
                    "class_code": cls["code"],
                    "class_name": cls["name"],
                    "category_code": cat["code"],
                    "category_name": cat["name"],
                }
    return data, index


def load_profiles():
    data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    return {p["code"]: p for p in data["profiles"]}


MAJORS_DATA, MAJOR_INDEX = load_majors()
PROFILE_INDEX = load_profiles()

MAX_SEARCH_QUERY_CHARS = 64


def normalize_major_query(value):
    """Normalize user search text without interpreting it as a regex."""
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)


def damerau_levenshtein(left, right):
    """Small standard-library edit distance with adjacent transpositions."""
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    rows = len(left) + 1
    cols = len(right) + 1
    distance = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        distance[i][0] = i
    for j in range(cols):
        distance[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if left[i - 1] == right[j - 1] else 1
            distance[i][j] = min(
                distance[i - 1][j] + 1,
                distance[i][j - 1] + 1,
                distance[i - 1][j - 1] + cost,
            )
            if (
                i > 1 and j > 1
                and left[i - 1] == right[j - 2]
                and left[i - 2] == right[j - 1]
            ):
                distance[i][j] = min(
                    distance[i][j], distance[i - 2][j - 2] + cost
                )
    return distance[-1][-1]


def _text_similarity(left, right):
    if not left or not right:
        return 0.0
    return 1.0 - damerau_levenshtein(left, right) / max(len(left), len(right))


def _profile_search_terms(code):
    profile = PROFILE_INDEX.get(code) or {}
    terms = []
    if profile.get("summary"):
        terms.append(profile["summary"])
    for group in ("direct", "derivative"):
        for direction in profile.get(group, []) or []:
            terms.extend([
                direction.get("occupation", ""),
                direction.get("description", ""),
            ])
            terms.extend(direction.get("titles") or [])
            terms.extend(direction.get("keywords") or [])
            terms.extend(direction.get("skills") or [])
    return tuple(
        dict.fromkeys(
            normalized for normalized in map(normalize_major_query, terms)
            if len(normalized) >= 2
        )
    )


PROFILE_SEARCH_TERMS = {
    code: _profile_search_terms(code) for code in PROFILE_INDEX
}


def _best_intent_score(query, code):
    best = 0.0
    for phrase, codes in INTENT_MAP.items():
        if code not in codes:
            continue
        term = normalize_major_query(phrase)
        rank_penalty = codes.index(code) * 0.005
        if query == term:
            strength = 0.93
        elif term in query and _has_intent_context(query, term):
            # Prefer the most specific matched phrase.  For example,
            # “芯片设计” must outrank the generic “设计” intent.
            strength = 0.82 + min(len(term), 8) * 0.01
        elif 3 <= len(query) <= 12 and query in term:
            strength = 0.80
        elif (
            3 <= len(query) <= 12
            and len(term) >= 3
            and abs(len(query) - len(term)) <= 2
        ):
            similarity = _text_similarity(query, term)
            strength = 0.76 * similarity if similarity >= 0.72 else 0.0
        else:
            strength = 0.0
        best = max(best, strength - rank_penalty)
    return best


def _has_intent_context(query, term):
    """Require job-search context for an intent embedded in a longer word."""
    remainder = query.replace(term, "", 1)
    return any(marker in remainder for marker in INTENT_CONTEXT_MARKERS)


def _score_major_candidate(query, code, info):
    """Return (score, match_type, reason) for one catalog item."""
    best = (0.0, "", "")

    def consider(score, match_type, reason):
        nonlocal best
        if score > best[0]:
            best = (score, match_type, reason)

    if query == code:
        consider(1.0, "code_exact", "专业代码完全匹配")
    elif query.isdigit() and len(query) >= 2 and code.startswith(query):
        consider(0.96, "code_prefix", "专业代码前缀匹配")
    if query.isdigit():
        return best

    alias_codes = MAJOR_ALIAS_MAP.get(query, [])
    if code in alias_codes:
        consider(
            0.975 - alias_codes.index(code) * 0.005,
            "alias_exact",
            "专业简称匹配",
        )

    name = normalize_major_query(info.get("name"))
    class_name = normalize_major_query(info.get("class_name"))
    category_name = normalize_major_query(info.get("category_name"))
    if query == name:
        consider(0.99, "name_exact", "专业名称完全匹配")
    elif len(query) >= 3 and (query in name or name in query):
        consider(0.94 if query in name else 0.91, "name_contains", "专业名称相关")
    elif len(query) == 2 and name.startswith(query):
        # 两字查询只接受“名称前缀”命中：「数学」仍能召回「数学与应用数学」，
        # 但「计科」不会跨词命中「材料设计科学与工程」这类无关专业。
        consider(0.93, "name_contains", "专业名称相关")

    if 3 <= len(query) <= 16 and abs(len(query) - len(name)) <= 2:
        similarity = _text_similarity(query, name)
        if similarity >= 0.55:
            consider(0.58 + 0.34 * similarity, "name_fuzzy", "专业名称近似")

    if query == class_name:
        consider(0.87, "class_exact", "专业类完全匹配")
    elif query in class_name or (len(class_name) >= 2 and class_name in query):
        consider(0.82, "class_related", "专业类相关")
    if query == category_name:
        consider(0.72, "category_exact", "学科门类匹配")
    elif len(query) >= 2 and query in category_name:
        consider(0.66, "category_related", "学科门类相关")

    intent_score = _best_intent_score(query, code)
    if intent_score:
        consider(intent_score, "intent", "求职意向相关")

    for term in PROFILE_SEARCH_TERMS.get(code, ()):
        if query == term:
            consider(0.84, "profile_exact", "专业画像关键词匹配")
        elif len(query) >= 3 and query in term:
            consider(0.78, "profile_related", "专业画像与意向相关")
        elif len(term) >= 3 and term in query:
            specificity = min(len(term), 10) * 0.005
            consider(
                0.72 + specificity,
                "profile_related",
                "专业画像与意向相关",
            )
    return best


def search_majors(query, limit=30):
    """Rank bounded catalog candidates across names, typos and intent terms."""
    items, _total = search_majors_with_total(query, limit=limit)
    return items


def search_majors_with_total(query, limit=30):
    """Return (ranked_items, total_candidates) for one query.

    ``total`` counts every candidate above the score floor *before* the
    ``limit`` slice, so the API can report the real candidate count while
    still returning a bounded page.
    """
    normalized = normalize_major_query(query)
    if not normalized:
        return [], 0
    results = []
    for code, info in MAJOR_INDEX.items():
        score, match_type, reason = _score_major_candidate(normalized, code, info)
        if score < 0.55:
            continue
        item = dict(info)
        item.update({
            "_rank_score": score,
            "match_score": round(score * 100),
            "match_type": match_type,
            "match_reason": reason,
            "has_profile": code in PROFILE_INDEX,
            "path": "%s / %s" % (info["category_name"], info["class_name"]),
        })
        results.append(item)
    results.sort(
        key=lambda item: (
            -item["_rank_score"],
            0 if item["has_profile"] else 1,
            item["code"],
        )
    )
    total = len(results)
    limited = results[:limit]
    for item in limited:
        item.pop("_rank_score", None)
    return limited, total


def api_ok(payload, status=200):
    resp = jsonify(payload)
    resp.status_code = status
    return resp


def api_err(message, status=400, code="bad_request"):
    return api_ok({"error": code, "message": message}, status)


def tokenize(text):
    text = text.lower()
    ascii_tokens = set(re.findall(r"[a-z0-9+#]+", text))
    cn_tokens = set()
    for seg in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(seg) <= 4:
            cn_tokens.add(seg)
        for i in range(len(seg) - 1):
            cn_tokens.add(seg[i : i + 2])
    return ascii_tokens | cn_tokens


def keyword_matches(keywords, resume_text):
    norm = resume_text.lower()
    return [kw for kw in keywords if kw.lower() in norm]


def score_direction(direction, resume_text, resume_tokens):
    keywords = direction.get("keywords") or []
    matched = keyword_matches(keywords, resume_text)
    ratio = len(matched) / len(keywords) if keywords else 0.0
    score = round(ratio * 100)
    gaps = [kw for kw in keywords if kw.lower() not in resume_text.lower()]
    return {
        "occupation": direction["occupation"],
        "level": direction["level"],
        "titles": direction.get("titles") or [],
        "description": direction.get("description", ""),
        "score": score,
        "matched": matched[:12],
        "gaps": gaps[:8],
    }


def classify_requirement(text):
    if any(k in text for k in ("优先", "加分")):
        return "bonus"
    if any(k in text for k in ("学历", "本科", "硕士", "博士", "经验", "年以上", "证书", "执业", "精通", "熟悉", "掌握")):
        return "hard"
    if any(k in text for k in ("负责", "参与", "主导", "完成", "推动", "组织")):
        return "responsibility"
    return "term"


def extract_requirements(jd_text):
    parts = re.split(r"[\n；;。]", jd_text)
    seen, reqs = set(), []
    for part in parts:
        text = re.sub(r"^[\s\-•*·]+", "", part).strip()
        if len(text) < 4 or text in seen:
            continue
        seen.add(text)
        reqs.append({"id": f"r{len(reqs) + 1}", "type": classify_requirement(text), "text": text})
    return reqs


def judge_requirement(req_text, resume_tokens, resume_text):
    query_tokens = tokenize(req_text)
    hit = query_tokens & resume_tokens
    if not query_tokens:
        return "unknown", []
    ratio = len(hit) / len(query_tokens)
    if ratio >= 0.9:
        return "covered", sorted(hit)[:10]
    if ratio >= 0.4:
        return "weak", sorted(hit)[:10]
    return "missing", []


def detect_occupation(jd_text, profile):
    jd_norm = jd_text.lower()
    best = None
    for kind in ("direct", "derivative"):
        for direction in profile.get(kind, []):
            terms = []
            terms += [t.lower() for t in direction.get("titles", [])]
            terms += [k.lower() for k in direction.get("keywords", [])]
            terms.append(direction["occupation"].lower())
            hit = sum(1 for t in terms if t in jd_norm)
            score = hit / max(1, len(set(terms)))
            if best is None or score > best[0]:
                best = (score, direction)
    if best and best[0] > 0.04:
        return best[1]
    return None


def mode_a_result(profile, resume_text, resume_tokens):
    directions = []
    for kind in ("direct", "derivative"):
        for direction in profile.get(kind, []):
            item = score_direction(direction, resume_text, resume_tokens)
            item["kind"] = "对口" if kind == "direct" else "衍生"
            directions.append(item)
    directions.sort(key=lambda d: d["score"], reverse=True)
    coverage = directions[0]["score"] if directions else 0
    return {
        "directions": directions,
        "coverage": coverage,
        "major_fit": 100,
        "major_fit_notice": "模式A：以用户专业画像为基准，专业契合度按基准 100 计。",
        "overall": coverage,
    }


def mode_b_result(profile, resume_text, jd_text):
    resume_tokens = tokenize(resume_text)
    requirements = extract_requirements(jd_text)
    rows = []
    type_values = {t: [] for t in MATCH_WEIGHTS}
    for req in requirements:
        status, hits = judge_requirement(req["text"], resume_tokens, resume_text)
        rows.append(
            {
                "id": req["id"],
                "type": req["type"],
                "typeLabel": TYPE_LABELS[req["type"]],
                "text": req["text"],
                "status": status,
                "evidence": hits,
            }
        )
        if status != "unknown":
            type_values[req["type"]].append({"covered": 1.0, "weak": 0.5, "missing": 0.0}[status])
    subscores = {}
    weighted, active = 0.0, 0.0
    for req_type, weight in MATCH_WEIGHTS.items():
        values = type_values[req_type]
        score = round(sum(values) / len(values) * 100) if values else 0
        subscores[req_type] = {"label": TYPE_LABELS[req_type], "score": score, "count": len(values)}
        if values:
            weighted += weight * score
            active += weight
    coverage = round(weighted / active) if active else 0

    occupation = detect_occupation(jd_text, profile)
    if occupation:
        major_fit = LEVEL_SCORE.get(occupation["level"], 50)
        major_fit_notice = f"JD 命中职业「{occupation['occupation']}」（{occupation['level']}对应）"
    else:
        major_fit = None
        major_fit_notice = "未能识别 JD 对应职业画像，专业契合分暂不计入综合分。"
    overall = round(0.4 * major_fit + 0.6 * coverage) if major_fit is not None else coverage

    gaps = []
    for row in rows:
        if row["status"] in ("covered", "unknown"):
            continue
        priority = "P0" if row["type"] == "hard" else ("P1" if row["type"] == "responsibility" else "P2")
        gaps.append({"level": priority, "text": row["text"], "action": "在简历中补充与该要求直接相关的真实经历、成果或技能证据。"})
    return {
        "requirements": rows,
        "subscores": subscores,
        "coverage": coverage,
        "major_fit": major_fit,
        "major_fit_notice": major_fit_notice,
        "overall": overall,
        "occupation_hit": {"occupation": occupation["occupation"], "level": occupation["level"]} if occupation else None,
        "gaps": gaps,
    }


def common_match_contract(mode_result):
    """Translate F2 display names into the frozen cross-feature match schema."""
    type_aliases = {"bonus": "preferred", "term": "terminology"}
    requirements = []
    for item in mode_result.get("requirements", []):
        normalized = dict(item)
        normalized["type"] = type_aliases.get(normalized.get("type"), normalized.get("type"))
        requirements.append(normalized)

    subscores = {}
    for key, value in mode_result.get("subscores", {}).items():
        subscores[type_aliases.get(key, key)] = value

    return {
        "score_M": mode_result.get("overall"),
        "requirements": requirements,
        "subscores": subscores,
        "gaps": mode_result.get("gaps", []),
    }


def route_api(**kwargs):
    # The old standalone serverless path bypassed the unified consent, quota,
    # ownership and error middleware. Keep only the documented /api/f2/* API.
    if request.path.rstrip("/") in {"/api/f2_major", "/api/f2_major.py"}:
        return api_err("接口不存在。", 404, "not_found")
    route = request.args.get("_route") or request.path
    if route.startswith("f2/"):
        route = route[len("f2/") :]
    if route.startswith("/api/f2/"):
        route = route[len("/api/f2/") :]

    if request.method == "OPTIONS":
        return ("", 204)
    if route == "health":
        return api_ok({"status": "ok", "majors": len(MAJOR_INDEX), "profiles": len(PROFILE_INDEX)})
    if route == "majors/tree" and request.method == "GET":
        return api_ok({"version": MAJORS_DATA["version"], "counts": MAJORS_DATA["counts"], "categories": MAJORS_DATA["categories"]})
    if route == "majors/search" and request.method == "GET":
        q = (request.args.get("q") or "").strip()
        try:
            limit = min(max(int(request.args.get("limit", 30)), 1), 100)
        except (TypeError, ValueError):
            return api_err("limit 必须是 1-100 的整数。", 422, "invalid_limit")
        if not q:
            return api_ok({"items": [], "total": 0})
        if len(q) > MAX_SEARCH_QUERY_CHARS:
            return api_err(
                f"搜索词不能超过 {MAX_SEARCH_QUERY_CHARS} 个字符。",
                422,
                "query_too_long",
            )
        items, total = search_majors_with_total(q, limit=limit)
        return api_ok({"items": items, "total": total})
    if route.startswith("majors/") and request.method == "GET":
        code = route.split("/")[-1]
        info = MAJOR_INDEX.get(code)
        if not info:
            return api_err("专业不存在。", 404, "major_not_found")
        profile = PROFILE_INDEX.get(code)
        result = {"major": info}
        if profile:
            result["profile_status"] = "ready"
            result["profile"] = {
                "summary": profile["summary"],
                "direct": profile["direct"],
                "derivative": profile["derivative"],
                "source": profile.get("source", ""),
            }
        else:
            result["profile_status"] = "building"
            result["profile"] = None
        return api_ok(result)
    if route == "match" and request.method == "POST":
        body = request.get_json(silent=True) or {}
        major_code = str(body.get("majorCode") or "").strip()
        resume_text = (body.get("resumeText") or "").strip()
        jd_text = (body.get("jdText") or "").strip()
        if major_code not in MAJOR_INDEX:
            return api_err("请先选择有效的专业。", 422, "major_required")
        if len(resume_text) < 20:
            return api_err("简历内容过短，请粘贴完整简历。", 422, "resume_too_short")
        profile = PROFILE_INDEX.get(major_code)
        resume_tokens = tokenize(resume_text)
        if jd_text:
            mode_result = mode_b_result(profile or {}, resume_text, jd_text)
            mode_name = "B"
            mode_notice = "模式B：JD 精准匹配（四态 + 专业契合度）。"
        else:
            if profile is None:
                return api_err("该专业画像建设中，请补充 JD 后使用模式B，或稍后再试。", 422, "profile_building")
            mode_result = mode_a_result(profile, resume_text, resume_tokens)
            mode_name = "A"
            mode_notice = "模式A：专业画像匹配（无 JD，按对口/衍生岗位画像推荐方向）。"
        major_info = MAJOR_INDEX[major_code]
        response_payload = {
                "mode": mode_name,
                "mode_notice": mode_notice,
                "modeA": mode_result if mode_name == "A" else None,
                "modeB": mode_result if mode_name == "B" else None,
                "major": {
                    "code": major_code,
                    "name": major_info["name"],
                    "path": f"{major_info['category_name']} / {major_info['class_name']}",
                },
                "profile_status": "ready" if profile else "building",
                "scores": {
                    "major_fit": mode_result.get("major_fit"),
                    "coverage": mode_result.get("coverage"),
                    "overall": mode_result.get("overall"),
                    "major_fit_notice": mode_result.get("major_fit_notice", ""),
                },
            }
        # Expose the common match contract at the top level so F3/F4 and the
        # persistent store do not have to understand mode-specific nesting.
        response_payload.update(common_match_contract(mode_result))
        session_id = str(body.get("session_id") or "").strip()
        if session_id:
            from tools.database import save_match

            score_m = response_payload["score_M"]
            stored = dict(response_payload)
            save_match(session_id, stored, score_m)
            response_payload["session_id"] = session_id
        return api_ok(response_payload)
    if route == "intent" and request.method == "GET":
        q = (request.args.get("q") or "").strip()
        if not q:
            return api_ok({"items": [], "total": 0})
        if len(q) > MAX_SEARCH_QUERY_CHARS:
            return api_err(
                f"搜索词不能超过 {MAX_SEARCH_QUERY_CHARS} 个字符。",
                422,
                "query_too_long",
            )
        items, total = search_majors_with_total(q, limit=12)
        return api_ok({"items": items, "total": total})
    return api_err("接口不存在。", 404, "not_found")


@app.route("/", methods=["GET"])
def serve_index():
    return send_from_directory(str(PROTOTYPE_DIR), "index.html")


@app.route("/<path:path>", methods=["GET"])
def serve_static(path):
    target = PROTOTYPE_DIR / path
    if target.is_file():
        return send_from_directory(str(PROTOTYPE_DIR), path)
    return api_err("页面不存在。", 404, "not_found")


for _rule in (
    "/api/f2/health",
    "/api/f2/majors/tree",
    "/api/f2/majors/search",
    "/api/f2/majors/<code>",
    "/api/f2/match",
    "/api/f2/intent",
):
    app.add_url_rule(_rule, endpoint="f2_" + _rule.replace("/api/f2/", "").replace("/", "_") or "root", view_func=route_api, methods=["GET", "POST", "OPTIONS"])


if __name__ == "__main__":
    port = int(os.environ.get("F2_PORT", "8123"))
    print(f"F2 专业导向岗位匹配服务: http://127.0.0.1:{port}/pages/f2-match.html", file=sys.stderr)
    app.run(host="127.0.0.1", port=port, debug=False)
