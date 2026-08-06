"""Vercel API entry point for the unified career-coach workflows (WF-01~06).

The service processes uploaded material only in the current request and stores
only de-identified, anonymized session data in a lightweight SQLite store
(/tmp by default; ephemeral on Vercel).  Real resumes, JD texts and model
outputs are never logged verbatim.
"""
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path

from flask import Flask, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from jsonschema import Draft202012Validator
from werkzeug.exceptions import HTTPException


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.database import (  # noqa: E402
    admin_password_ok,
    count_resumes,
    delete_session_data,
    export_all,
    get_resume_detail,
    list_resumes,
    load_ability,
    load_match,
    load_session,
    save_ability,
    save_diagnosis,
    save_match,
    save_resume,
    save_session,
    update_session,
)
from tools.deidentify import deidentify  # noqa: E402
from tools.extract_text import extract_docx, extract_pdf, extract_txt  # noqa: E402
from tools.interview_engine import InterviewEngine  # noqa: E402
from tools.match_requirements import (  # noqa: E402
    Bm25Matcher,
    judge,
    split_sentences,
    tokenize,
    unigrams,
)
from tools.model_router import ZhipuModelRouter  # noqa: E402
from tools.radar_adapter import build_option  # noqa: E402
from tools.redflag import JSON_NOISE, RE_NUMBER, RE_PLACEHOLDER  # noqa: E402
from tools.rescore import calc_R, compute as rescore_compute, round2  # noqa: E402
from tools.validate_schema import business_rules  # noqa: E402


app = Flask(__name__)

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
MIN_TEXT_CHARS = 20
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
PUBLIC_PAGES_ORIGIN = "https://zimo66067-wq.github.io"
TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,96}$")
CONSENT_TOKEN_SALT = "career-coach-consent-v1"
DEFAULT_CONSENT_MAX_AGE_SECONDS = 1800
SUBSCORE_DEFAULTS = {
    "structure": "结构完整度",
    "clarity": "表达清晰度",
    "achievement_evidence": "成果证据",
    "skill_evidence": "技能证据",
    "ats_readability": "ATS 可读性",
}

# Multipart overhead is allowed here; the file itself is checked separately.
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_BYTES + 1024 * 1024

with (REPOSITORY_ROOT / "contracts" / "resume-profile.schema.json").open(
    encoding="utf-8"
) as schema_file:
    RESUME_PROFILE_VALIDATOR = Draft202012Validator(json.load(schema_file))

with (REPOSITORY_ROOT / "contracts" / "job-profile.schema.json").open(
    encoding="utf-8"
) as schema_file:
    JOB_PROFILE_VALIDATOR = Draft202012Validator(json.load(schema_file))


class ApiError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def trace_id():
    candidate = request.headers.get("X-Trace-Id", "")
    if TRACE_ID_PATTERN.fullmatch(candidate):
        return candidate
    return "api_" + uuid.uuid4().hex[:16]


def configured_origins():
    values = os.environ.get("DUMATE_ALLOWED_ORIGINS", PUBLIC_PAGES_ORIGIN)
    return {origin.strip().rstrip("/") for origin in values.split(",") if origin.strip()}


def origin_allowed(origin):
    if not origin:
        return False
    normalized = origin.rstrip("/")
    if normalized in configured_origins():
        return True
    if os.environ.get("APP_ENV", "production").lower() != "production":
        return bool(re.fullmatch(r"http://(?:localhost|127\.0\.0\.1)(?::\d+)?", normalized))
    return False


@app.after_request
def apply_cors(response):
    origin = request.headers.get("Origin", "")
    if origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin.rstrip("/")
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, X-Trace-Id, X-Consent-Token"
        )
        response.headers["Access-Control-Max-Age"] = "600"
        existing_vary = response.headers.get("Vary", "")
        response.headers["Vary"] = ", ".join(filter(None, [existing_vary, "Origin"]))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(ApiError)
def handle_api_error(error):
    return jsonify({"error": error.code, "message": error.message, "trace_id": trace_id()}), error.status


@app.errorhandler(413)
def handle_content_too_large(_error):
    return jsonify({
        "error": "payload_too_large",
        "message": "文件或文本超过服务允许的大小，请精简后重试。",
        "trace_id": trace_id(),
    }), 413


@app.errorhandler(HTTPException)
def handle_http_error(error):
    """Keep ordinary routing and method errors out of the 500 handler."""
    if error.code == 404:
        return jsonify({
            "error": "not_found",
            "message": "接口不存在。",
            "trace_id": trace_id(),
        }), 404
    if error.code == 405:
        return jsonify({
            "error": "method_not_allowed",
            "message": "请求方法不被允许。",
            "trace_id": trace_id(),
        }), 405
    return jsonify({
        "error": "http_error",
        "message": "请求无法处理。",
        "trace_id": trace_id(),
    }), error.code or 500


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    # Do not return provider details, local paths, or user material to browsers.
    app.logger.exception("Unhandled API error: %s", type(error).__name__)
    return jsonify({
        "error": "internal_error",
        "message": "诊断服务暂时不可用，请稍后重试。",
        "trace_id": trace_id(),
    }), 500


def api_response(payload, status=200):
    payload.setdefault("trace_id", trace_id())
    return jsonify(payload), status


# ------------------------------------------------------------------ #
# Consent (WF-01 gate)
# ------------------------------------------------------------------ #

def consent_ttl_seconds():
    """Return a bounded, short-lived consent-token lifetime."""
    try:
        configured = int(os.environ.get("DUMATE_CONSENT_MAX_AGE_SECONDS", DEFAULT_CONSENT_MAX_AGE_SECONDS))
    except (TypeError, ValueError):
        configured = DEFAULT_CONSENT_MAX_AGE_SECONDS
    return min(max(configured, 60), 86_400)


def consent_serializer():
    """Build a signer without storing the consent body or source material."""
    signing_material = os.environ.get("DUMATE_CONSENT_SECRET")
    if not signing_material:
        if app.config.get("TESTING") or os.environ.get("APP_ENV", "production").lower() != "production":
            signing_material = "development-consent-token-for-tests"
        else:
            raise ApiError(
                "consent_not_configured",
                "服务尚未配置同意记录签名密钥，暂不能处理材料。",
                503,
            )
    return URLSafeTimedSerializer(signing_material, salt=CONSENT_TOKEN_SALT)


def issue_consent():
    if not request.is_json:
        raise ApiError("invalid_content_type", "同意请求必须使用 JSON 格式。", 415)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("invalid_request", "同意请求格式无效。", 422)
    accepted = body.get("accepted") is True or bool(str(body.get("consent_text", "")).strip())
    if not accepted:
        raise ApiError("consent_required", "请先明确同意本次会话的数据处理说明。", 422)
    consent_id = "consent_" + uuid.uuid4().hex[:16]
    token = consent_serializer().dumps({"accepted": True, "version": "1"})
    return {
        "status": "ACCEPTED",
        "consent_token": token,
        "consent_id": consent_id,
        "expires_in_seconds": consent_ttl_seconds(),
    }


def require_consent():
    token = request.headers.get("X-Consent-Token", "").strip()
    if not token:
        raise ApiError("consent_required", "请先阅读并同意本次会话的数据处理说明。", 428)
    try:
        payload = consent_serializer().loads(token, max_age=consent_ttl_seconds())
    except SignatureExpired:
        raise ApiError("consent_expired", "同意记录已过期，请重新确认后再继续。", 401)
    except BadSignature:
        raise ApiError("invalid_consent", "同意记录无效，请重新确认后再继续。", 401)
    if not isinstance(payload, dict) or payload.get("accepted") is not True or payload.get("version") != "1":
        raise ApiError("invalid_consent", "同意记录无效，请重新确认后再继续。", 401)


def request_route():
    """Resolve Vercel rewrite routes while retaining direct local test routes."""
    rewritten = request.args.get("_route")
    if rewritten:
        return rewritten.strip("/")
    if request.path.startswith("/api/"):
        return request.path[len("/api/"):]
    return ""


# ------------------------------------------------------------------ #
# Input validation and file extraction
# ------------------------------------------------------------------ #

def validate_document_text(value, label, error_code):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) < MIN_TEXT_CHARS:
        raise ApiError(error_code, "%s正文至少需要 20 个字符。" % label, 422)
    if len(text) > MAX_TEXT_CHARS:
        raise ApiError("payload_too_large", "%s正文不能超过 20 万个字符。" % label, 413)
    return text


def validate_text(value):
    return validate_document_text(value, "简历", "invalid_resume_text")


def validate_job_text(value):
    return validate_document_text(value, "职位说明（JD）", "invalid_jd_text")


def read_uploaded_document(label, error_code):
    """Extract and validate an uploaded PDF/DOCX/TXT. Returns (text, filename, ext, size)."""
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        raise ApiError("missing_file", "请选择要上传的 PDF、DOCX 或 TXT %s。" % label, 422)

    extension = Path(uploaded.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ApiError("unsupported_file_type", "仅支持 PDF、DOCX 或 TXT 格式。", 415)

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temporary_file:
            temporary_path = temporary_file.name
        uploaded.save(temporary_path)
        file_size = os.path.getsize(temporary_path)
        if file_size > MAX_FILE_BYTES:
            raise ApiError("payload_too_large", "文件不能超过 10 MB。", 413)
        if extension == ".pdf":
            text = extract_pdf(temporary_path)
        elif extension == ".docx":
            text = extract_docx(temporary_path)
        else:
            text = extract_txt(temporary_path)
        return validate_document_text(text, label, error_code), uploaded.filename, extension, file_size
    except ApiError:
        raise
    except SystemExit:
        raise ApiError("unreadable_file", "未能读取该文件，请改为可复制文字的 PDF、DOCX、TXT 或直接粘贴正文。", 422)
    except Exception:
        raise ApiError("unreadable_file", "未能读取该文件，请确认文件未损坏后重试。", 422)
    finally:
        if temporary_path:
            try:
                os.remove(temporary_path)
            except OSError:
                pass


def read_uploaded_resume():
    return read_uploaded_document("简历", "invalid_resume_text")


def read_uploaded_job():
    return read_uploaded_document("职位说明（JD）", "invalid_jd_text")


def build_model_router():
    primary_model = (
        os.environ.get("DUMATE_MODEL")
        or os.environ.get("ZHIPU_MODEL")
        or os.environ.get("PRIMARY_MODEL")
    )
    fallback_model = os.environ.get("ZHIPU_FALLBACK_MODEL") or os.environ.get("FALLBACK_MODEL")
    if not os.environ.get("ZHIPU_API_KEY") or not (primary_model or fallback_model):
        raise ApiError("model_not_configured", "诊断模型尚未配置完成，请联系服务管理员。", 503)
    return ZhipuModelRouter(primary_model=primary_model, fallback_model=fallback_model)


# ------------------------------------------------------------------ #
# Resume profile normalization and validation (F1 / WF-02)
# ------------------------------------------------------------------ #

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
# F2 JD parsing and matching (WF-03)
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
# F3 Interview session endpoints (WF-04)
# ------------------------------------------------------------------ #

def build_interview_router():
    """Return a router when configured; None otherwise (question-bank fallback)."""
    try:
        return build_model_router()
    except ApiError:
        return None


def start_interview(body):
    engine = InterviewEngine(model_router=build_interview_router())
    job_profile = body.get("jobProfile") if isinstance(body.get("jobProfile"), dict) else {}
    resume_profile = body.get("resumeProfile") if isinstance(body.get("resumeProfile"), dict) else {}
    match_gaps = body.get("matchGaps") if isinstance(body.get("matchGaps"), list) else []
    session = engine.start(job_profile, resume_profile, match_gaps)
    first = engine.next_question(session)
    if not first or first.get("question") is None:
        raise ApiError("interview_not_started", "未能生成面试问题，请稍后重试。", 503)
    session_id = body.get("session_id") or ("iv_" + uuid.uuid4().hex[:16])
    save_session(session_id, "ASK", session)
    return {
        "session_id": session_id,
        "firstQuestion": first.get("question"),
        "targets": first.get("targets", []),
        "state": session.get("state", "ASK"),
    }


def answer_interview(body):
    session_id = body.get("session_id", "")
    if not session_id:
        raise ApiError("session_required", "缺少面试会话标识。", 422)
    state, payload = load_session(session_id)
    if not payload:
        raise ApiError("session_not_found", "面试会话不存在或已过期。", 404)
    engine = InterviewEngine(model_router=build_interview_router())
    engine.start(
        payload.get("job_profile", {}),
        payload.get("resume_profile", {}),
        payload.get("match_gaps", []),
    )
    # Rebuild the engine session object from the stored payload in-place.
    engine_session = payload
    answer_text = str(body.get("answer_text", "") or "").strip()
    if len(answer_text) < 1:
        raise ApiError("invalid_answer", "回答内容不能为空。", 422)
    asr_confidence = body.get("asr_confidence")
    result = engine.submit_answer(engine_session, answer_text, asr_confidence)
    update_session(session_id, engine_session.get("state", "ASK"), engine_session)
    return {
        "session_id": session_id,
        "turn": result,
        "followUp": result.get("follow_up"),
    }


def end_interview(body):
    session_id = body.get("session_id", "")
    if not session_id:
        raise ApiError("session_required", "缺少面试会话标识。", 422)
    state, payload = load_session(session_id)
    if not payload:
        raise ApiError("session_not_found", "面试会话不存在或已过期。", 404)
    engine = InterviewEngine(model_router=build_interview_router())
    engine_session = payload
    report = engine.end_session(engine_session)
    update_session(session_id, engine_session.get("state", "REPORT"), engine_session)
    return {
        "session_id": session_id,
        "report": report.get("report", ""),
        "score_I": report.get("score_I"),
        "turns": report.get("turns", []),
        "i_subscores": report.get("i_subscores", {}),
    }


# ------------------------------------------------------------------ #
# F4 Ability report (WF-05)
# ------------------------------------------------------------------ #

PLAN_TEMPLATE = [
    (1, "为三条核心经历补充量化证据，无法确认的数字用「待用户核实：」占位", 40, "修订后的三段经历文本"),
    (2, "针对 P0 缺口整理项目复盘笔记", 35, "一页复盘笔记"),
    (3, "按 STAR 结构重写两个面试高频回答", 40, "两份 STAR 回答稿"),
    (4, "针对岗位术语做概念速学并自测", 30, "术语自测清单"),
    (5, "完成一轮五题文字模拟面试并复盘 missing_elements", 45, "面试复盘记录"),
    (6, "根据复盘改写简历自我评价与技能描述", 35, "简历修订版 v2"),
    (7, "复测诊断与匹配，对比 C0 变化并记录真实提升", 40, "复测对比表"),
]

ABILITY_DIMENSIONS = [
    ("job_fit", "岗位契合"),
    ("achievement_evidence", "成果证据"),
    ("professional_expression", "专业表达"),
    ("structured_answer", "结构化回答"),
    ("job_depth", "岗位深度"),
    ("followup_adaptation", "追问适应"),
]


def _latest_diagnosis(session_id):
    detail = get_resume_detail(session_id)
    if not detail or not detail.get("diagnoses"):
        return None
    return detail["diagnoses"][0]


def build_ability_profile(session_id):
    """Aggregate stored R/M/I and produce AbilityProfile + radar option."""
    diag = _latest_diagnosis(session_id)
    match = load_match(session_id)
    state, payload = load_session(session_id)
    turns = (payload or {}).get("turns", []) or []

    if not diag or not match or not turns:
        missing = []
        if not diag:
            missing.append("F1 简历诊断")
        if not match:
            missing.append("F2 岗位匹配")
        if not turns:
            missing.append("F3 模拟面试")
        raise ApiError(
            "insufficient_evidence",
            "能力报告需要先完成：%s。" % "、".join(missing),
            422,
        )

    try:
        profile = json.loads(diag.get("diagnosis_json") or "{}")
    except (TypeError, ValueError):
        profile = {}
    r_subscores = {}
    for key in SUBSCORE_DEFAULTS:
        item = (profile.get("subscores") or {}).get(key)
        r_subscores[key] = item.get("score") if isinstance(item, dict) else None
    r_score = diag.get("score_r")
    if r_score is None:
        try:
            r_score = round2(calc_R(r_subscores))
        except (ValueError, TypeError):
            r_score = None

    m_score = match.get("score_M")
    m_requirements = [
        {"type": item.get("type", "hard"), "status": item.get("status", "unknown")}
        for item in match.get("requirements", [])
        if isinstance(item, dict)
    ]
    m_categories = {}
    for key in MATCH_WEIGHTS:
        item = (match.get("subscores") or {}).get(key)
        m_categories[key] = item.get("score") if isinstance(item, dict) else None

    i_keys = ["structure", "relevance", "specificity", "followup_adaptation", "clarity"]
    sums = {k: 0.0 for k in i_keys}
    counts = {k: 0 for k in i_keys}
    for turn in turns:
        sc = turn.get("subscores")
        if not isinstance(sc, dict):
            continue
        quote = turn.get("answer_quote", "")
        answer = turn.get("answer", "")
        if not quote or not answer or quote not in answer:
            continue
        for k in i_keys:
            v = sc.get(k)
            if isinstance(v, (int, float)):
                sums[k] += v
                counts[k] += 1
    i_subscores = {
        k: round(sums[k] / counts[k], 2) if counts[k] else None
        for k in i_keys
    }
    if not any(v is not None for v in i_subscores.values()):
        raise ApiError("insufficient_evidence", "面试回合证据不足，无法生成能力报告。", 422)

    score_input = {"R": r_subscores, "M": {"requirements": m_requirements}, "I": i_subscores}
    try:
        result = rescore_compute(score_input)
    except (ValueError, KeyError):
        result = {"insufficient_evidence": True}
    if result.get("insufficient_evidence"):
        raise ApiError("insufficient_evidence", "综合证据不足，无法计算 C0；请先完成 F1-F3。", 422)

    c0 = result["C0"]
    dims = []
    for key, name in ABILITY_DIMENSIONS:
        if key == "job_fit":
            value = m_score if m_score is not None else (m_categories.get("hard") or 0)
        elif key == "achievement_evidence":
            value = r_subscores.get("achievement_evidence") or 0
        elif key == "professional_expression":
            value = round(((r_subscores.get("clarity") or 0) + (i_subscores.get("clarity") or 0)) / 2, 1)
        elif key == "structured_answer":
            value = i_subscores.get("structure") or 0
        elif key == "job_depth":
            value = round(((m_categories.get("responsibility") or 0) + (i_subscores.get("relevance") or 0)) / 2, 1)
        else:
            value = i_subscores.get("followup_adaptation") or 0
        dims.append({
            "key": key,
            "name": name,
            "score": round(max(0, min(100, float(value))), 1),
            "evidence": ["F1-F3 规则复算结果"],
        })

    plan = [
        {"day": day, "focus": focus, "minutes": minutes, "artifact": artifact}
        for day, focus, minutes, artifact in PLAN_TEMPLATE
    ]
    ability = {
        "version": "1.0",
        "resume_score": round(r_score, 2) if r_score is not None else None,
        "match_score": round(m_score, 2) if m_score is not None else None,
        "interview_score": round(result["I"], 2),
        "dimensions": dims,
        "baseline": round(c0, 2),
        "scenario_day7": {
            "low": result["C7_low"],
            "high": result["C7_high"],
            "assumptions": [
                "0.30 与 0.70 为 MVP 演示假设，非统计学习参数",
                "假设用户按计划完成每天 30-45 分钟训练并产出 artifact",
                "第七天复测结果才是真实变化",
            ],
        },
        "plan": plan,
    }
    save_ability(session_id, ability)
    return ability, result


# ------------------------------------------------------------------ #
# Routing
# ------------------------------------------------------------------ #

def route_api():
    route = request_route()
    if request.method == "OPTIONS":
        if route in {
            "wf01/consent", "wf01/upload", "wf02/diagnose",
            "wf03/upload", "wf03/jd", "wf03/match",
            "wf04/start", "wf04/answer", "wf04/end",
            "wf05/ability", "wf06/delete", "health",
            "admin/resumes", "admin/export",
        }:
            return ("", 204)
        raise ApiError("not_found", "接口不存在。", 404)

    if route == "health" and request.method == "GET":
        return api_response({
            "status": "ok",
            "model_configured": bool(os.environ.get("ZHIPU_API_KEY")),
            "workflows": {
                "wf01": "available", "wf02": "available", "wf03": "available",
                "wf04": "available", "wf05": "available", "wf06": "available",
            },
        })
    if route == "wf01/consent" and request.method == "POST":
        return api_response(issue_consent())

    if route == "wf01/upload" and request.method == "POST":
        require_consent()
        source_text, filename, extension, file_size = read_uploaded_resume()
        cleaned_text, _mapping = deidentify(source_text)
        session_id = request.headers.get("X-Trace-Id", uuid.uuid4().hex)
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
    if route == "wf02/diagnose" and request.method == "POST":
        require_consent()
        if not request.is_json:
            raise ApiError("invalid_content_type", "诊断请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "诊断请求格式无效。", 422)
        resume_text = validate_text(body.get("resumeText"))
        session_id = body.get("session_id") or request.headers.get("X-Trace-Id", uuid.uuid4().hex)
        # A diagnosis must always be attachable: ensure a resume row exists even
        # when the client diagnoses pasted text without a preceding upload.
        if get_resume_detail(session_id) is None:
            cleaned_text, _mapping = deidentify(resume_text)
            try:
                save_resume(
                    session_id=session_id,
                    client_ip=request.remote_addr or "",
                    user_agent=request.headers.get("User-Agent", "")[:500],
                    filename="pasted-resume.txt",
                    file_type="paste",
                    file_size=len(resume_text),
                    resume_text=cleaned_text[:100000],
                )
            except Exception:
                app.logger.exception("DB save resume failed")
        profile, score_r, model_trace_id, diagnosis_mode, diagnosis_notice = diagnose_resume(
            resume_text
        )
        try:
            save_diagnosis(
                session_id=session_id,
                score_r=score_r,
                diagnosis_mode=diagnosis_mode,
                diagnosis_notice=diagnosis_notice,
                model_trace_id=model_trace_id,
                diagnosis_json=json.dumps(profile, ensure_ascii=False)[:500000],
            )
        except Exception:
            app.logger.exception("DB save diagnosis failed")
        return api_response({
            "resumeProfile": profile,
            "score_R": score_r,
            "model_trace_id": model_trace_id,
            "diagnosis_mode": diagnosis_mode,
            "diagnosis_notice": diagnosis_notice,
            "session_id": session_id,
        })

    if route == "wf03/upload" and request.method == "POST":
        require_consent()
        source_text, _filename, _ext, _size = read_uploaded_job()
        session_id = request.headers.get("X-Trace-Id", uuid.uuid4().hex)
        return api_response({"jdText": source_text, "jobProfile": None, "session_id": session_id})
    if route == "wf03/jd" and request.method == "POST":
        require_consent()
        session_id = request.headers.get("X-Trace-Id", uuid.uuid4().hex)
        if request.files.get("file"):
            jd_text, _filename, _ext, _size = read_uploaded_job()
        else:
            if not request.is_json:
                raise ApiError("invalid_content_type", "JD 解析请求必须使用 JSON 格式。", 415)
            body = request.get_json(silent=True)
            if not isinstance(body, dict):
                raise ApiError("invalid_request", "JD 解析请求格式无效。", 422)
            jd_text = validate_job_text(body.get("jdText"))
        return api_response({"jobProfile": build_job_profile(jd_text), "session_id": session_id})
    if route == "wf03/match" and request.method == "POST":
        require_consent()
        if not request.is_json:
            raise ApiError("invalid_content_type", "岗位匹配请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "岗位匹配请求格式无效。", 422)
        session_id = body.get("session_id") or request.headers.get("X-Trace-Id", uuid.uuid4().hex)
        match = match_job_profile(
            validate_text(body.get("resumeText")),
            validate_job_profile(body.get("jobProfile")),
        )
        try:
            save_match(session_id, match, match.get("score_M"))
        except Exception:
            app.logger.exception("DB save match failed")
        return api_response(dict(match, session_id=session_id))

    if route == "wf04/start" and request.method == "POST":
        require_consent()
        if not request.is_json:
            raise ApiError("invalid_content_type", "面试请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "面试请求格式无效。", 422)
        return api_response(start_interview(body))
    if route == "wf04/answer" and request.method == "POST":
        require_consent()
        if not request.is_json:
            raise ApiError("invalid_content_type", "面试请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "面试请求格式无效。", 422)
        return api_response(answer_interview(body))
    if route == "wf04/end" and request.method == "POST":
        require_consent()
        if not request.is_json:
            raise ApiError("invalid_content_type", "面试请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "面试请求格式无效。", 422)
        return api_response(end_interview(body))

    if route == "wf05/ability" and request.method == "POST":
        require_consent()
        if not request.is_json:
            raise ApiError("invalid_content_type", "能力报告请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "能力报告请求格式无效。", 422)
        session_id = body.get("session_id", "")
        if not session_id:
            raise ApiError("session_required", "缺少会话标识。", 422)
        ability, result = build_ability_profile(session_id)
        return api_response({
            "ability": ability,
            "radar_option": build_option(ability),
            "score_R": ability["resume_score"],
            "score_M": ability["match_score"],
            "score_I": ability["interview_score"],
            "C0": ability["baseline"],
            "C7_low": result["C7_low"],
            "C7_high": result["C7_high"],
            "session_id": session_id,
        })

    if route == "wf06/delete" and request.method == "POST":
        require_consent()
        if not request.is_json:
            raise ApiError("invalid_content_type", "删除请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "删除请求格式无效。", 422)
        session_id = body.get("session_id", "")
        if not session_id:
            raise ApiError("session_required", "缺少会话标识。", 422)
        try:
            delete_session_data(session_id)
        except Exception:
            app.logger.exception("DB delete session failed")
        return api_response({
            "status": "DELETED",
            "deleted_at": __import__("datetime").datetime.now().isoformat(),
            "session_id": session_id,
        })

    if route == "admin/resumes" and request.method == "GET":
        password = request.headers.get("X-Admin-Password", "")
        if not admin_password_ok(password):
            raise ApiError("forbidden", "访问被拒绝。", 403)
        try:
            limit = min(int(request.args.get("limit", 100)), 500)
            offset = max(int(request.args.get("offset", 0)), 0)
        except ValueError:
            limit, offset = 100, 0
        return api_response({
            "total": count_resumes(),
            "limit": limit,
            "offset": offset,
            "items": list_resumes(limit=limit, offset=offset),
            "warning": "Vercel /tmp 是临时文件系统；服务重启后数据会丢失。请定期导出。",
        })
    if route == "admin/export" and request.method == "GET":
        password = request.headers.get("X-Admin-Password", "")
        if not admin_password_ok(password):
            raise ApiError("forbidden", "访问被拒绝。", 403)
        return api_response(export_all())

    raise ApiError("not_found", "接口不存在。", 404)


# Local test routes plus the single Vercel function route used by vercel.json.
for _rule in (
    "/api", "/api/wf01/consent", "/api/wf01/upload", "/api/wf02/diagnose",
    "/api/wf03/upload", "/api/wf03/jd", "/api/wf03/match",
    "/api/wf04/start", "/api/wf04/answer", "/api/wf04/end",
    "/api/wf05/ability", "/api/wf06/delete", "/api/health",
    "/api/admin/resumes", "/api/admin/export",
):
    app.add_url_rule(_rule, endpoint="route_" + _rule.replace("/", "_") or "root", view_func=route_api,
                     methods=["GET", "POST", "OPTIONS"])
