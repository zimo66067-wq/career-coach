"""Vercel API entry point for real resume upload and diagnosis.

The service processes uploaded material only in the current request.  It does
not keep source files, raw resume text, or model outputs on disk after the
response has been returned.
"""
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path

from flask import Flask, jsonify, request
from jsonschema import Draft202012Validator
from werkzeug.exceptions import HTTPException


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.deidentify import deidentify  # noqa: E402
from tools.extract_text import extract_docx, extract_pdf, extract_txt  # noqa: E402
from tools.model_router import ZhipuModelRouter  # noqa: E402
from tools.redflag import JSON_NOISE, RE_NUMBER, RE_PLACEHOLDER  # noqa: E402
from tools.rescore import calc_R, round2  # noqa: E402
from tools.validate_schema import business_rules  # noqa: E402


app = Flask(__name__)

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
MIN_TEXT_CHARS = 20
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
PUBLIC_PAGES_ORIGIN = "https://zimo66067-wq.github.io"
TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,96}$")

# Multipart overhead is allowed here; the file itself is checked separately.
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_BYTES + 1024 * 1024

with (REPOSITORY_ROOT / "contracts" / "resume-profile.schema.json").open(
    encoding="utf-8"
) as schema_file:
    RESUME_PROFILE_VALIDATOR = Draft202012Validator(json.load(schema_file))


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
        return bool(re.fullmatch(r"http://(?:localhost|127\\.0\\.0\\.1)(?::\\d+)?", normalized))
    return False


@app.after_request
def apply_cors(response):
    origin = request.headers.get("Origin", "")
    if origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin.rstrip("/")
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Trace-Id"
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


def request_route():
    """Resolve Vercel rewrite routes while retaining direct local test routes."""
    rewritten = request.args.get("_route")
    if rewritten:
        return rewritten.strip("/")
    if request.path.startswith("/api/"):
        return request.path[len("/api/"):]
    return ""


def validate_text(value):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) < MIN_TEXT_CHARS:
        raise ApiError("invalid_resume_text", "简历正文至少需要 20 个字符。", 422)
    if len(text) > MAX_TEXT_CHARS:
        raise ApiError("payload_too_large", "简历正文不能超过 20 万个字符。", 413)
    return text


def read_uploaded_resume():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        raise ApiError("missing_file", "请选择要上传的 PDF、DOCX 或 TXT 简历。", 422)

    extension = Path(uploaded.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ApiError("unsupported_file_type", "仅支持 PDF、DOCX 或 TXT 格式。", 415)

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temporary_file:
            temporary_path = temporary_file.name
        uploaded.save(temporary_path)
        if os.path.getsize(temporary_path) > MAX_FILE_BYTES:
            raise ApiError("payload_too_large", "文件不能超过 10 MB。", 413)
        if extension == ".pdf":
            text = extract_pdf(temporary_path)
        elif extension == ".docx":
            text = extract_docx(temporary_path)
        else:
            text = extract_txt(temporary_path)
        return validate_text(text)
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


def profile_validation_errors(profile, resume_text):
    errors = []
    for error in sorted(RESUME_PROFILE_VALIDATOR.iter_errors(profile), key=str):
        path = "/".join(str(part) for part in error.absolute_path) or "(root)"
        errors.append("schema:%s" % path)
    try:
        business_rules(profile, errors)
    except (AttributeError, TypeError):
        # Schema diagnostics below remain the user-safe error surfaced to the
        # caller.  Malformed provider output must never escape as a 500.
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


def redflag_errors(profile, resume_text):
    """Apply redflag.py's numeric fact-lock without persisting user content."""
    # Contract metadata (schema version, numeric scores and character offsets)
    # is not a factual claim about the candidate.  Check only generated
    # narrative instead; otherwise any normal score such as 80 would be
    # incorrectly rejected as a fabricated resume fact.
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


def diagnose_resume(resume_text):
    cleaned_text, _mapping = deidentify(resume_text)
    router = build_model_router()
    result = router.call("resume_diagnosis", cleaned_text)
    if result.get("status") != "success" or result.get("degraded") or not isinstance(result.get("output"), dict):
        raise ApiError("model_unavailable", "诊断模型暂时不可用，请稍后重试。", 503)

    profile = result["output"]
    validation_errors = profile_validation_errors(profile, cleaned_text)
    if validation_errors:
        raise ApiError("model_output_invalid", "诊断结果未通过证据校验，请稍后重试。", 502)

    score_r = round2(calc_R({
        key: value["score"] for key, value in profile["subscores"].items()
    }))
    return profile, score_r, result.get("trace_id") or trace_id()


def route_api():
    route = request_route()
    if request.method == "OPTIONS":
        if route in {"wf01/upload", "wf02/diagnose", "health"}:
            return ("", 204)
        raise ApiError("not_found", "接口不存在。", 404)

    if route == "health" and request.method == "GET":
        return api_response({"status": "ok", "model_configured": bool(os.environ.get("ZHIPU_API_KEY"))})
    if route == "wf01/upload" and request.method == "POST":
        source_text = read_uploaded_resume()
        cleaned_text, _mapping = deidentify(source_text)
        return api_response({"resumeText": cleaned_text, "resumeProfile": None})
    if route == "wf02/diagnose" and request.method == "POST":
        if not request.is_json:
            raise ApiError("invalid_content_type", "诊断请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "诊断请求格式无效。", 422)
        profile, score_r, model_trace_id = diagnose_resume(validate_text(body.get("resumeText")))
        return api_response({"resumeProfile": profile, "score_R": score_r, "model_trace_id": model_trace_id})
    raise ApiError("not_found", "接口不存在。", 404)


# Local test routes plus the single Vercel function route used by vercel.json.
for _rule in ("/api", "/api/wf01/upload", "/api/wf02/diagnose", "/api/health"):
    app.add_url_rule(_rule, endpoint="route_" + _rule.replace("/", "_") or "root", view_func=route_api,
                     methods=["GET", "POST", "OPTIONS"])
