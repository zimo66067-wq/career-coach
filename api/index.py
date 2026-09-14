"""Vercel API entry point for the unified career-coach workflows (WF-01~06).

The service processes uploaded material only in the current request and stores
only de-identified, anonymized session data in a lightweight SQLite store
(/tmp by default; ephemeral on Vercel).  Real resumes, JD texts and model
outputs are never logged verbatim.
"""
import hashlib
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, request, stream_with_context
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from jsonschema import Draft202012Validator
from werkzeug.exceptions import HTTPException


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.database import (  # noqa: E402
    admin_password_ok,
    bind_session_owner,
    consume_usage,
    count_resumes,
    delete_session_data,
    dialect,
    export_all,
    get_resume_detail,
    get_session_owner,
    list_resumes,
    load_ability,
    load_match,
    load_session,
    save_ability,
    save_diagnosis,
    save_match,
    save_resume,
    save_session,
    transfer_owner_data,
    update_session,
    list_rewrites,
    mark_rewrite_applied,
    save_rewrite,
)
from tools.account import (  # noqa: E402
    AccountError,
    add_history,
    authenticate,
    create_session,
    delete_history,
    end_session,
    list_history,
    public_user,
    register_user,
    session_user,
)
from tools.deidentify import deidentify  # noqa: E402
from tools.extract_text import extract_docx, extract_pdf, extract_txt  # noqa: E402
from tools.ocr_provider import ocr_pdf  # noqa: E402
from tools.optimizer import rewrite_suggestion  # noqa: E402
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



# ---- Phase 5: shared modules + service layer ----
from domain.errors import DomainError  # noqa: E402
from services.apply_service import (  # noqa: E402
    create_application,
    delete_application,
    generate_cover_letter,
    list_applications_for,
)
from services import career_evidence_service as evidence_service  # noqa: E402
from services import target_job_service  # noqa: E402
from services.target_job_service import TargetJobError  # noqa: E402
from services.diagnosis_service import (  # noqa: E402
    build_rule_based_resume_profile,
    diagnose_resume,
)
from services.interview_service import (  # noqa: E402
    _advance_interview,
    _coerce_asr_confidence,
    _validated_answer_text,
    answer_interview,
    build_ability_profile,
    build_interview_router,
    build_turn_evaluation,
    end_interview,
    start_interview,
)
from services.match_service import (  # noqa: E402
    build_job_profile,    match_job_profile,
    validate_job_profile,
)
from services.organization_service import (  # noqa: E402
    discover_organizations,
    get_organization,
    list_jobs_for,
    provider_status,
    suggest_organizations,
)
from tools.api_errors import ApiError  # noqa: E402
from tools.contracts import MAX_TEXT_CHARS, MIN_TEXT_CHARS  # noqa: E402
from tools.providers.model import build_model_router  # noqa: E402
from tools.trace import trace_id  # noqa: E402
from tools.upload_security import UploadSecurityError, validate_upload  # noqa: E402



app = Flask(__name__)

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
MIN_TEXT_CHARS = 20
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
PUBLIC_PAGES_ORIGIN = "https://zimo66067-wq.github.io"
TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,96}$")
CONSENT_TOKEN_SALT = "career-coach-consent-v1"
GUEST_TOKEN_SALT = "career-coach-guest-v1"
DEFAULT_CONSENT_MAX_AGE_SECONDS = 1800
DEFAULT_GUEST_MAX_AGE_SECONDS = 365 * 86400

# Multipart overhead is allowed here; the file itself is checked separately.
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_BYTES + 1024 * 1024


# ---- Phase 2：领域收敛迁移 ----------------------------------------------------
# 建表本身是加法（CREATE TABLE IF NOT EXISTS），但"历史数据要落到新模型"必须显式迁移。
# 迁移幂等；冷启动执行一次，失败不阻断服务（新表已由 DDL 建好，迁移只做列补齐与状态
# 规范化），但必须可见 —— /api/health 的 migrations 字段会如实上报。
#
# 这里刻意只 import 模块本身而不是三个函数：/api/health 必须报告**当前**数据库的真实
# 状态（补跑未应用的迁移后再上报），否则换了数据库之后健康检查会继续报旧结论。
from repositories import migrations as _migrations  # noqa: E402

_MIGRATION_ERROR = None
try:
    _migrations.ensure_applied()
except Exception as exc:  # pragma: no cover - 故障路径由 /api/health 上报
    _MIGRATION_ERROR = "%s: %s" % (type(exc).__name__, exc)
    app.logger.exception("phase-2 domain migration failed")


def migration_status():
    """给 /api/health 用的迁移状态：先补跑未应用的迁移，再如实上报。

    冷启动时的失败会记在 ``_MIGRATION_ERROR`` 里并一直上报，不会被重试掩盖。
    """
    expected = [version for version, _func in _migrations.MIGRATIONS]
    error = _MIGRATION_ERROR
    if error is None:
        try:
            _migrations.ensure_applied()
        except Exception as exc:  # pragma: no cover - 故障路径
            error = "%s: %s" % (type(exc).__name__, exc)
    applied = []
    try:
        applied = sorted(_migrations.applied_versions())
    except Exception as exc:  # pragma: no cover - 故障路径
        if error is None:
            error = "%s: %s" % (type(exc).__name__, exc)
    return {
        "ok": error is None and all(version in applied for version in expected),
        "applied": applied,
        "expected": expected,
        "error": error,
    }



def configured_origins():
    values = os.environ.get("DUMATE_ALLOWED_ORIGINS", PUBLIC_PAGES_ORIGIN)
    return {origin.strip().rstrip("/") for origin in values.split(",") if origin.strip()}


def origin_allowed(origin):
    if not origin:
        return False
    normalized = origin.rstrip("/")
    if normalized == request.host_url.rstrip("/"):
        return True
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
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, X-Trace-Id, X-Consent-Token, X-Guest-Token, Authorization"
        )
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Max-Age"] = "600"
        existing_vary = response.headers.get("Vary", "")
        response.headers["Vary"] = ", ".join(filter(None, [existing_vary, "Origin"]))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.before_request
def reject_cross_site_writes():
    """Reject browser state changes from an untrusted Origin.

    Header-authenticated guest requests need the same protection as cookie
    sessions: a leaked consent/guest token must not make a hostile browser
    origin acceptable. Non-browser clients that omit Origin remain supported.
    """
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    origin = request.headers.get("Origin", "").strip()
    if origin and not origin_allowed(origin):
        raise ApiError("csrf_rejected", "请求来源未获授权。", 403)
    return None


# ------------------------------------------------------------------ #
# Account session helpers
# ------------------------------------------------------------------ #

def current_session():
    """Return (user, token) from the Authorization header or session cookie."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
    else:
        token = ""
    if not token:
        token = request.cookies.get("zy_session", "")
    return session_user(token), token


def require_login():
    user, _token = current_session()
    if not user:
        raise ApiError("auth_required", "请先登录。", 401)
    return user


def _session_ttl_days():
    try:
        return min(max(int(os.environ.get("SESSION_TTL_DAYS", 30)), 1), 90)
    except (TypeError, ValueError):
        return 30


def _set_session_cookie(response, token):
    secure = os.environ.get("APP_ENV", "production").lower() == "production"
    response.set_cookie(
        "zy_session",
        token,
        max_age=_session_ttl_days() * 86400,
        httponly=True,
        secure=secure,
        samesite="None" if secure else "Lax",
        path="/",
    )


def _clear_session_cookie(response):
    response.delete_cookie("zy_session", path="/")


@app.errorhandler(ApiError)
def handle_api_error(error):
    payload = {"error": error.code, "message": error.message, "trace_id": trace_id()}
    retry_after = getattr(error, "retry_after", None)
    if retry_after:
        payload["retry_after_seconds"] = int(retry_after)
    response = jsonify(payload)
    response.status_code = error.status
    if retry_after:
        response.headers["Retry-After"] = str(int(retry_after))
    return response


@app.errorhandler(DomainError)
def handle_domain_error(error):
    """领域规则被违反 → 422，并把领域层的机器可读 code 原样带出。

    领域错误是"这个请求不合法"，不是"服务坏了"，所以不能落到 500 处理器；
    集中在 App 层翻译一次，路由里就不必逐个 try/except。
    """
    return jsonify({
        "error": error.code,
        "message": str(error),
        "trace_id": trace_id(),
    }), 422


@app.errorhandler(TargetJobError)
def handle_target_job_error(error):
    return jsonify({
        "error": error.code,
        "message": error.message,
        "trace_id": trace_id(),
    }), error.status


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


def require_json_object(label="请求"):
    """Return a JSON object and reject malformed or array-shaped bodies."""
    if not request.is_json:
        raise ApiError("invalid_content_type", f"{label}必须使用 JSON 格式。", 415)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("invalid_request", f"{label}格式无效。", 422)
    return body


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


def guest_serializer():
    """Build the independent signer used for stable anonymous ownership."""
    signing_material = os.environ.get("DUMATE_GUEST_SECRET") or os.environ.get("DUMATE_CONSENT_SECRET")
    if not signing_material:
        if app.config.get("TESTING") or os.environ.get("APP_ENV", "production").lower() != "production":
            signing_material = "development-guest-token-for-tests"
        else:
            raise ApiError(
                "guest_identity_not_configured",
                "服务尚未配置匿名会话签名密钥，暂不能处理材料。",
                503,
            )
    return URLSafeTimedSerializer(signing_material, salt=GUEST_TOKEN_SALT)


def guest_ttl_seconds():
    try:
        configured = int(os.environ.get("DUMATE_GUEST_MAX_AGE_SECONDS", DEFAULT_GUEST_MAX_AGE_SECONDS))
    except (TypeError, ValueError):
        configured = DEFAULT_GUEST_MAX_AGE_SECONDS
    return min(max(configured, 86400), 2 * 365 * 86400)


def _guest_id_from_token(token, strict=True):
    if not token:
        return None
    try:
        payload = guest_serializer().loads(token, max_age=guest_ttl_seconds())
    except (SignatureExpired, BadSignature):
        if strict:
            raise ApiError("invalid_guest_identity", "匿名会话身份无效，请重新确认数据处理说明。", 401)
        return None
    if not isinstance(payload, dict) or payload.get("version") != "1":
        if strict:
            raise ApiError("invalid_guest_identity", "匿名会话身份无效，请重新确认数据处理说明。", 401)
        return None
    guest_id = str(payload.get("guest_id") or "")
    if not re.fullmatch(r"[a-f0-9]{32}", guest_id):
        if strict:
            raise ApiError("invalid_guest_identity", "匿名会话身份无效，请重新确认数据处理说明。", 401)
        return None
    return guest_id


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
    prior_guest_token = str(body.get("guest_token") or request.headers.get("X-Guest-Token") or "").strip()
    guest_id = _guest_id_from_token(prior_guest_token, strict=False) or uuid.uuid4().hex
    # Include a nonce so independently issued consent tokens cannot collapse to
    # the same signed value when they are created within the same second.
    token = consent_serializer().dumps({
        "accepted": True,
        "version": "1",
        "consent_id": consent_id,
    })
    guest_token = guest_serializer().dumps({"guest_id": guest_id, "version": "1"})
    return {
        "status": "ACCEPTED",
        "consent_token": token,
        "guest_token": guest_token,
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


def _owner_context():
    """Return the primary owner and an optional verified guest predecessor."""
    guest_token = request.headers.get("X-Guest-Token", "").strip()
    guest_id = _guest_id_from_token(guest_token) if guest_token else None
    consent = request.headers.get("X-Consent-Token", "")
    guest_owner = (
        "guest:" + guest_id
        if guest_id
        else "guest:legacy:" + hashlib.sha256(consent.encode("utf-8")).hexdigest()[:24]
    )
    user, _token = current_session()
    if user:
        return "user:%s" % user["id"], guest_owner
    return guest_owner, None


def _task_owner_key():
    return _owner_context()[0]


def ensure_session_access(session_id, allow_create=False):
    """Bind or verify a workflow session without revealing another owner's data."""
    session_id = str(session_id or "").strip()
    if not session_id or len(session_id) > 128 or not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
        raise ApiError("invalid_session", "会话标识无效。", 422)
    primary, guest_predecessor = _owner_context()
    current = get_session_owner(session_id)
    if current is None and allow_create:
        if bind_session_owner(session_id, primary):
            return session_id
        current = get_session_owner(session_id)
    if current == primary:
        return session_id
    if guest_predecessor and current == guest_predecessor:
        if bind_session_owner(session_id, primary, previous_owner=guest_predecessor):
            return session_id
    raise ApiError("session_not_found", "会话不存在或无权访问。", 404)


def enforce_usage(bucket, limit, window_seconds, owner_key=None):
    """Apply a database-backed limit shared across serverless instances."""
    owner = owner_key or _task_owner_key()
    result = consume_usage(owner, bucket, limit, window_seconds)
    if not result["allowed"]:
        error = ApiError("rate_limited", "操作过于频繁，请稍后再试。", 429)
        error.retry_after = result.get("retry_after", 1)
        raise error
    return result


def _client_rate_key():
    """Hash the network identifier before using it as a quota owner key."""
    source = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    source = source or request.remote_addr or "anonymous"
    return "ip:" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]


def _claim_guest_resources(user_id):
    """Transfer only resources backed by a valid guest token after login."""
    token = request.headers.get("X-Guest-Token", "").strip()
    guest_id = _guest_id_from_token(token, strict=False)
    if guest_id:
        transfer_owner_data("guest:" + guest_id, "user:%s" % user_id)


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
        validate_upload(temporary_path, extension)
        if extension == ".pdf":
            text = extract_pdf(temporary_path)
        elif extension == ".docx":
            text = extract_docx(temporary_path)
        else:
            text = extract_txt(temporary_path)
        safe_filename = ("resume" if error_code == "invalid_resume_text" else "job-description") + extension
        return validate_document_text(text, label, error_code), safe_filename, extension, file_size
    except ApiError:
        raise
    except UploadSecurityError as exc:
        raise ApiError(exc.code, exc.message, 422)
    except SystemExit:
        if extension == ".pdf":
            # 扫描件 OCR 兜底：配置 OCR_API_KEY/OCR_SECRET_KEY 时自动逐页识别
            try:
                ocr_result = ocr_pdf(temporary_path)
            except Exception:  # noqa: BLE001
                ocr_result = {"ok": False, "error": "ocr_failed", "message": "OCR 处理异常"}
            if ocr_result.get("ok") and str(ocr_result.get("text") or "").strip():
                text = str(ocr_result["text"]).strip()
                return validate_document_text(text, label, error_code), uploaded.filename, extension, file_size
            detail = str(ocr_result.get("message") or "")
            raise ApiError(
                "scanned_pdf",
                "该 PDF 是扫描件/图片型，无法直接提取文字。%s请改为可复制文字的 PDF、DOCX、TXT 或直接粘贴正文。" % (detail + ("，" if detail else "")),
                422,
            )
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


# Routing
# ------------------------------------------------------------------ #

def route_api(**_ignored):
    route = request_route()
    if request.method == "OPTIONS":
        if route in {
            "wf01/consent", "wf01/upload", "wf02/diagnose",
            "wf03/upload", "wf03/jd", "wf03/match",
            "wf04/start", "wf04/answer", "wf04/end",
            "wf05/ability", "wf06/delete", "health",
            "admin/resumes", "admin/export",
            "auth/register", "auth/login", "auth/logout", "auth/me",
            "history",
            "wf04/stream",
            "wf02/optimize", "wf02/apply-rewrite",
            "wf07/cover-letter", "wf07/applications",
            "f5/organizations/status", "f5/organizations/suggest",
            "f5/organizations/discover", "f5/organizations/detail",
            "f5/organizations/jobs",
            "profile", "profile/evidence/candidates", "target-jobs",
        } or (route.startswith("history/") or route.startswith("f5/")
              or route.startswith("profile/evidence/") or route.startswith("target-jobs/")):
            return ("", 204)
        raise ApiError("not_found", "接口不存在。", 404)

    # ---- Phase 3 · 核心闭环：职业证据档案 + 目标岗位分析 ------------------------
    # D8 方案 A：模型抽取只产出**候选证据**（pending），用户确认后才成为可信事实。
    # 这里不提供任何"直接写 confirmed"的入参 —— 见 services/career_evidence_service.py。
    if route == "profile" and request.method == "GET":
        require_consent()
        owner = _task_owner_key()
        evidence_service.ensure_profile(owner)
        return api_response(evidence_service.profile_payload(owner))

    if route == "profile/evidence/candidates" and request.method == "POST":
        require_consent()
        enforce_usage("evidence_candidates_hour", 30, 3600)
        body = require_json_object("候选证据请求")
        session_id = str(body.get("session_id") or "")
        ensure_session_access(session_id)
        detail = get_resume_detail(session_id)
        resume_text = str((detail or {}).get("resume_text") or "")
        if not resume_text:
            raise ApiError("resume_required", "请先上传并完成简历诊断。", 422)
        resume_profile = body.get("resumeProfile")
        requirements = body.get("requirements")
        owner = _task_owner_key()
        evidence_service.ensure_profile(owner)
        created, skipped, considered = evidence_service.collect_candidates(
            owner,
            session_id,
            resume_text,
            resume_profile=resume_profile if isinstance(resume_profile, dict) else None,
            requirements=requirements if isinstance(requirements, list) else None,
        )
        return api_response({
            "created": created,
            "createdCount": len(created),
            "skippedExisting": skipped,
            "considered": len(considered),
            "profile": evidence_service.profile_payload(owner),
        }, 201)

    if route.startswith("profile/evidence/") and request.method in ("POST", "DELETE"):
        require_consent()
        parts = route.split("/")
        if len(parts) not in (3, 4):
            raise ApiError("not_found", "接口不存在。", 404)
        try:
            evidence_id = int(parts[2])
        except (TypeError, ValueError):
            raise ApiError("invalid_request", "证据 ID 无效。", 422)
        action = parts[3] if len(parts) == 4 else ""
        owner = _task_owner_key()
        try:
            if request.method == "DELETE" and not action:
                evidence_service.delete(owner, evidence_id)
                return api_response({"deleted": True, "id": evidence_id})
            if request.method == "POST" and action == "confirm":
                return api_response({"evidence": evidence_service.confirm(owner, evidence_id)})
            if request.method == "POST" and action == "reject":
                return api_response({"evidence": evidence_service.reject(owner, evidence_id)})
            if request.method == "POST" and action == "edit":
                body = require_json_object("证据修改请求")
                return api_response({"evidence": evidence_service.edit(
                    owner,
                    evidence_id,
                    claim=body.get("claim"),
                    source_quote=body.get("sourceQuote"),
                    confirmed_by_user=bool(body.get("confirmedByUser")),
                )})
        except LookupError:
            raise ApiError("evidence_not_found", "证据不存在。", 404)
        raise ApiError("not_found", "接口不存在。", 404)

    if route == "target-jobs" and request.method == "GET":
        require_consent()
        items = target_job_service.list_target_jobs(_task_owner_key())
        return api_response({"targetJobs": items, "total": len(items)})

    if route == "target-jobs" and request.method == "POST":
        require_consent()
        enforce_usage("target_job_create_hour", 20, 3600)
        body = require_json_object("目标岗位请求")
        session_id = str(body.get("session_id") or "")
        if session_id:
            ensure_session_access(session_id)
        job_profile = body.get("jobProfile")
        jd_text = str(body.get("jdText") or "").strip()
        if not isinstance(job_profile, dict):
            job_profile = None
        if job_profile is None and not jd_text:
            raise ApiError("jd_required", "请提供 JD 文本或已确认的岗位画像。", 422)
        if len(jd_text) > MAX_TEXT_CHARS:
            raise ApiError("payload_too_large", "JD 文本超过服务允许的长度。", 413)
        record = target_job_service.create_target_job(
            owner_key=_task_owner_key(),
            session_id=session_id or None,
            company=str(body.get("company") or "").strip() or None,
            position=str(body.get("position") or "").strip() or None,
            jd_text=jd_text or None,
            job_profile=job_profile,
        )
        return api_response({
            "targetJob": record,
            "requirements": target_job_service.requirements_of(record["id"]),
            "droppedNonRequirements": record.get("dropped_non_requirements") or [],
        }, 201)

    if route.startswith("target-jobs/") and request.method in ("GET", "POST", "DELETE"):
        require_consent()
        parts = route.split("/")
        if len(parts) not in (2, 3):
            raise ApiError("not_found", "接口不存在。", 404)
        try:
            target_job_id = int(parts[1])
        except (TypeError, ValueError):
            raise ApiError("invalid_request", "目标岗位 ID 无效。", 422)
        action = parts[2] if len(parts) == 3 else ""
        owner = _task_owner_key()

        if request.method == "GET" and not action:
            record = target_job_service.get_target_job(target_job_id, owner)
            return api_response({
                "targetJob": record,
                "requirements": target_job_service.requirements_of(target_job_id),
                "decision": target_job_service.decision_of(target_job_id, owner),
            })

        if request.method == "GET" and action == "decision":
            return api_response({
                "decision": target_job_service.decision_of(target_job_id, owner),
            })

        if request.method == "POST" and action == "analyse":
            enforce_usage("target_job_analyse_hour", 30, 3600)
            body = require_json_object("分析请求") if request.data else {}
            resume_text = str(body.get("resumeText") or "").strip()
            if not resume_text:
                session_id = str(body.get("session_id") or "")
                if not session_id:
                    record = target_job_service.get_target_job(target_job_id, owner)
                    session_id = str(record.get("session_id") or "")
                if not session_id:
                    raise ApiError("resume_required", "请先上传并完成简历诊断。", 422)
                ensure_session_access(session_id)
                detail = get_resume_detail(session_id)
                resume_text = str((detail or {}).get("resume_text") or "")
            if not resume_text:
                raise ApiError("resume_required", "请先上传并完成简历诊断。", 422)
            if len(resume_text) > MAX_TEXT_CHARS:
                raise ApiError("payload_too_large", "简历文本超过服务允许的长度。", 413)
            return api_response(target_job_service.analyse(target_job_id, owner, resume_text))

        if request.method == "DELETE" and not action:
            target_job_service.delete_target_job(target_job_id, owner)
            return api_response({"deleted": True, "id": target_job_id})

        raise ApiError("not_found", "接口不存在。", 404)

    # F5 unit/job index (phase 1 foundation: contract + explicit degrade only).
    if route.startswith("f5/organizations/"):
        if request.method == "GET":
            enforce_usage("f5_catalog_read", 240, 600, owner_key=_client_rate_key())
        else:
            require_consent()
            enforce_usage("f5_discover", 30, 3600)
        if route == "f5/organizations/status" and request.method == "GET":
            return api_response(provider_status())
        if route == "f5/organizations/suggest" and request.method == "GET":
            return api_response(
                suggest_organizations(
                    request.args.get("q", ""),
                    limit=request.args.get("limit", 10),
                )
            )
        if route == "f5/organizations/discover" and request.method == "POST":
            body = require_json_object("单位发现请求")
            return api_response(discover_organizations(body))
        if route == "f5/organizations/detail" and request.method == "GET":
            return api_response(get_organization(request.args.get("id", "")))
        if route == "f5/organizations/jobs" and request.method == "GET":
            return api_response(
                list_jobs_for(
                    request.args.get("organization_id", ""),
                    limit=request.args.get("limit", 20),
                )
            )
        raise ApiError("not_found", "接口不存在。", 404)

    if route == "auth/register" and request.method == "POST":
        body = require_json_object("注册请求")
        phone = str(body.get("phone") or "").strip()
        email = str(body.get("email") or "").strip()
        password = str(body.get("password") or "")
        name = str(body.get("name") or "").strip()
        if not re.fullmatch(r"1\d{10}", phone):
            raise ApiError("invalid_phone", "手机号格式不正确（11 位，1 开头）。", 422)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ApiError("invalid_email", "邮箱格式不正确。", 422)
        if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            raise ApiError("weak_password", "密码至少 8 位且需包含字母和数字。", 422)
        if not (2 <= len(name) <= 16):
            raise ApiError("invalid_name", "账户名需 2-16 个字符。", 422)
        enforce_usage("auth_register", 5, 3600, owner_key=_client_rate_key())
        try:
            user = register_user(phone, email, password, name)
        except AccountError as err:
            raise ApiError(err.code, err.message, err.status)
        token, _expires = create_session(user["id"], _session_ttl_days())
        _claim_guest_resources(user["id"])
        resp, status = api_response(public_user(user), 201)
        _set_session_cookie(resp, token)
        return resp, status

    if route == "auth/login" and request.method == "POST":
        body = require_json_object("登录请求")
        identifier = str(body.get("account") or "").strip()
        password = str(body.get("password") or "")
        if not identifier or not password:
            raise ApiError("invalid_request", "请输入手机号/邮箱和密码。", 422)
        enforce_usage("auth_login", 10, 900, owner_key=_client_rate_key())
        user = authenticate(identifier, password)
        if not user:
            raise ApiError("bad_credentials", "手机号/邮箱或密码不正确。", 401)
        token, _expires = create_session(user["id"], _session_ttl_days())
        _claim_guest_resources(user["id"])
        resp, status = api_response(public_user(user))
        _set_session_cookie(resp, token)
        return resp, status

    if route == "auth/logout" and request.method == "POST":
        _user, token = current_session()
        end_session(token)
        resp, status = api_response({"status": "LOGGED_OUT"})
        _clear_session_cookie(resp)
        return resp, status

    if route == "auth/me" and request.method == "GET":
        user, _token = current_session()
        if not user:
            return api_response({"logged_in": False})
        return api_response({"logged_in": True, "user": public_user(user)})

    if route == "history" and request.method == "GET":
        user = require_login()
        try:
            limit = min(max(int(request.args.get("limit", 50)), 1), 100)
            offset = max(int(request.args.get("offset", 0)), 0)
        except ValueError:
            limit, offset = 50, 0
        event_type = (request.args.get("type") or "").strip() or None
        if event_type and event_type not in ("F1", "F2", "F3", "F4"):
            raise ApiError("invalid_type", "历史类型仅支持 F1-F4。", 422)
        items, total = list_history(
            user["id"],
            limit=limit,
            offset=offset,
            event_type=event_type,
            role=user["role"],
        )
        return api_response({
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        })

    if route == "history" and request.method == "POST":
        user = require_login()
        body = require_json_object("历史记录请求")
        session_id = str(body.get("session_id") or "").strip()
        event_type = str(body.get("event_type") or "").strip()
        title = str(body.get("title") or "").strip()
        status = str(body.get("status") or "done").strip()
        if not session_id:
            raise ApiError("session_required", "缺少会话标识。", 422)
        ensure_session_access(session_id, allow_create=True)
        if event_type not in ("F1", "F2", "F3", "F4"):
            raise ApiError("invalid_type", "历史类型仅支持 F1-F4。", 422)
        if status not in ("done", "partial", "failed"):
            raise ApiError("invalid_status", "状态仅支持 done/partial/failed。", 422)
        if not (1 <= len(title) <= 200):
            raise ApiError("invalid_title", "标题长度需在 1-200 字符之间。", 422)
        history_id = add_history(user["id"], session_id, event_type, title, status)
        return api_response({"id": history_id, "status": "CREATED"}, 201)

    if route.startswith("history/") and request.method == "DELETE":
        user = require_login()
        try:
            event_id = int(route.split("/", 1)[1])
        except (IndexError, ValueError):
            raise ApiError("invalid_id", "历史记录标识无效。", 422)
        try:
            delete_history(user["id"], event_id)
        except AccountError as err:
            raise ApiError(err.code, err.message, err.status)
        return api_response({"status": "DELETED"})

    if route == "wf04/stream" and request.method == "POST":
        require_consent()
        enforce_usage("interview_turn_hour", 120, 3600)
        body = require_json_object("面试请求")
        session_id = str(body.get("session_id") or "")
        if not session_id:
            raise ApiError("session_required", "缺少面试会话标识。", 422)
        ensure_session_access(session_id)
        state, payload = load_session(session_id)
        if not payload:
            raise ApiError("session_not_found", "面试会话不存在或已过期。", 404)
        engine = InterviewEngine(model_router=build_interview_router())
        engine_session = payload
        answer_text = _validated_answer_text(body)
        asr_confidence = _coerce_asr_confidence(body.get("asr_confidence"))

        # 打字对话状态机（与 /wf04/answer 共用同一编排）：
        # 1) 有待回答追问 -> 本次输入为追问回答，记录后进入下一主问题；
        # 2) 主回答生成追问 -> 等待用户回答追问；
        # 3) 主回答无追问 -> 直接进入下一主问题；
        # 4) 低 ASR 置信度 -> 不记录、不追问、不推进，只要求用户确认转写。
        result, next_question = _advance_interview(
            engine, engine_session, answer_text, asr_confidence
        )
        update_session(session_id, engine_session.get("state", "ASK"), engine_session)

        needs_confirmation = bool(result.get("needs_confirmation"))
        follow_up = result.get("follow_up") if isinstance(result.get("follow_up"), dict) else None
        if needs_confirmation:
            full_text = (
                "这次语音转写的置信度偏低，为避免误记你的回答，我没有把它计入本轮。"
                "请确认或修改转写文本后重新提交。"
            )
        elif next_question:
            if next_question.get("done"):
                full_text = "本轮面试已完成，正在生成综合报告…"
            else:
                full_text = str(next_question.get("question") or "").strip()
        else:
            full_text = str((follow_up or {}).get("question") or "").strip()
        if not full_text:
            full_text = "已收到回答，请继续。"

        evaluation = build_turn_evaluation(result)

        def _sse_gen():
            chunk_size = 32
            for i in range(0, len(full_text), chunk_size):
                chunk = full_text[i:i + chunk_size]
                yield "data: " + json.dumps(
                    {"type": "fragment", "text": chunk, "done": False},
                    ensure_ascii=False,
                ) + "\n\n"
            yield "data: " + json.dumps(
                {"type": "done", "turn": result, "followUp": follow_up,
                 "evaluation": evaluation, "nextQuestion": next_question,
                 "needs_confirmation": needs_confirmation, "done": True},
                ensure_ascii=False,
            ) + "\n\n"

        stream_resp = Response(
            stream_with_context(_sse_gen()), mimetype="text/event-stream"
        )
        stream_resp.headers["Cache-Control"] = "no-cache"
        stream_resp.headers["X-Accel-Buffering"] = "no"
        return stream_resp

    if route == "wf02/optimize" and request.method == "POST":
        require_consent()
        enforce_usage("model_generation_hour", 20, 3600)
        enforce_usage("model_generation_day", 60, 86400)
        body = require_json_object("简历优化请求")
        session_id = str(body.get("session_id") or "")
        if not session_id:
            raise ApiError("session_required", "缺少会话标识。", 422)
        ensure_session_access(session_id)
        detail = get_resume_detail(session_id)
        if not detail or not detail.get("diagnoses"):
            raise ApiError("diagnosis_required", "请先完成 F1 简历诊断。", 422)
        profile = {}
        diag = detail["diagnoses"][0]
        try:
            profile = json.loads(diag.get("diagnosis_json") or "{}")
        except (TypeError, ValueError):
            profile = {}
        suggestions = profile.get("suggestions") if isinstance(profile, dict) else []
        suggestion_id = str(body.get("suggestion_id") or "")
        suggestion = None
        for item in suggestions:
            if str(item.get("id") or "") == suggestion_id:
                suggestion = item
                break
        if suggestion is None and suggestions:
            suggestion = suggestions[0]
        if suggestion is None:
            raise ApiError("suggestion_required", "暂无可用诊断建议。", 422)
        try:
            router = build_model_router()
        except ApiError:
            router = None
        return api_response(
            rewrite_suggestion(suggestion, resume_profile=profile, model_router=router)
        )

    if route == "wf02/apply-rewrite" and request.method == "POST":
        require_consent()
        body = require_json_object("改写确认请求")
        session_id = str(body.get("session_id") or "")
        candidate = str(body.get("candidate_text") or "").strip()
        suggestion_id = str(body.get("suggestion_id") or "")
        issue = str(body.get("issue") or "")
        if not session_id or len(candidate) < 5:
            raise ApiError("invalid_request", "缺少会话标识或改写内容。", 422)
        ensure_session_access(session_id)
        saved = save_rewrite(session_id, suggestion_id, issue, candidate)
        if saved is None:
            raise ApiError("save_failed", "改写内容保存失败。", 500)
        applied = mark_rewrite_applied(saved["id"], session_id)
        return api_response({"rewrite": applied, "status": "APPLIED"}, 201)

    if route == "wf07/cover-letter" and request.method == "POST":
        require_consent()
        enforce_usage("model_generation_hour", 20, 3600)
        enforce_usage("model_generation_day", 60, 86400)
        body = require_json_object("求职信请求")
        session_id = str(body.get("session_id") or "")
        if not session_id:
            raise ApiError("session_required", "缺少会话标识。", 422)
        ensure_session_access(session_id)
        return api_response(
            generate_cover_letter(
                session_id,
                company=body.get("company", ""),
                position=body.get("position", ""),
            )
        )

    if route == "wf07/applications" and request.method == "GET":
        require_consent()
        return api_response({"applications": list_applications_for(_task_owner_key())})

    if route == "wf07/applications" and request.method == "POST":
        require_consent()
        body = require_json_object("申请记录请求")
        session_id = str(body.get("session_id") or "")
        ensure_session_access(session_id)
        application = create_application(
            session_id=session_id,
            owner_key=_task_owner_key(),
            company=body.get("company", ""),
            position=body.get("position", ""),
            cover_letter=body.get("cover_letter", ""),
        )
        return api_response({"application": application}, 201)

    if route == "wf07/applications" and request.method == "DELETE":
        require_consent()
        app_id = request.args.get("id", "")
        try:
            app_id = int(app_id)
        except (TypeError, ValueError):
            raise ApiError("invalid_request", "缺少有效的申请记录 ID。", 422)
        deleted = delete_application(app_id, _task_owner_key())
        return api_response({"application": deleted, "status": "DELETED"})

    if route == "health" and request.method == "GET":
        return api_response({
            "status": "ok",
            "model_configured": bool(os.environ.get("ZHIPU_API_KEY")),
            "database": dialect(),
            "workflows": {
                "wf01": "available", "wf02": "available", "wf03": "available",
                "wf04": "available", "wf05": "available", "wf06": "available",
                "wf07": "available",
                "profile": "available", "target_jobs": "available",
            },
            # 领域收敛迁移的可观测性：迁移失败不静默（见 repositories/migrations.py）
            "migrations": migration_status(),
        })
    if route == "wf01/consent" and request.method == "POST":
        enforce_usage("consent_hour", 30, 3600, owner_key=_client_rate_key())
        return api_response(issue_consent())

    if route == "wf01/upload" and request.method == "POST":
        require_consent()
        enforce_usage("upload_hour", 20, 3600)
        source_text, filename, extension, file_size = read_uploaded_resume()
        cleaned_text, _mapping = deidentify(source_text)
        session_id = trace_id()
        ensure_session_access(session_id, allow_create=True)
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
        enforce_usage("model_generation_hour", 20, 3600)
        enforce_usage("model_generation_day", 60, 86400)
        if not request.is_json:
            raise ApiError("invalid_content_type", "诊断请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "诊断请求格式无效。", 422)
        resume_text = validate_text(body.get("resumeText"))
        session_id = body.get("session_id") or trace_id()
        ensure_session_access(session_id, allow_create=True)
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
        enforce_usage("upload_hour", 20, 3600)
        source_text, _filename, _ext, _size = read_uploaded_job()
        session_id = request.form.get("session_id") or trace_id()
        ensure_session_access(session_id, allow_create=True)
        return api_response({"jdText": source_text, "jobProfile": None, "session_id": session_id})
    if route == "wf03/jd" and request.method == "POST":
        require_consent()
        session_id = trace_id()
        if request.files.get("file"):
            jd_text, _filename, _ext, _size = read_uploaded_job()
            session_id = request.form.get("session_id") or session_id
        else:
            if not request.is_json:
                raise ApiError("invalid_content_type", "JD 解析请求必须使用 JSON 格式。", 415)
            body = request.get_json(silent=True)
            if not isinstance(body, dict):
                raise ApiError("invalid_request", "JD 解析请求格式无效。", 422)
            jd_text = validate_job_text(body.get("jdText"))
            session_id = body.get("session_id") or session_id
        ensure_session_access(session_id, allow_create=True)
        return api_response({"jobProfile": build_job_profile(jd_text), "session_id": session_id})
    if route == "wf03/match" and request.method == "POST":
        require_consent()
        if not request.is_json:
            raise ApiError("invalid_content_type", "岗位匹配请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "岗位匹配请求格式无效。", 422)
        session_id = body.get("session_id") or trace_id()
        ensure_session_access(session_id, allow_create=True)
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
        enforce_usage("interview_start_hour", 20, 3600)
        if not request.is_json:
            raise ApiError("invalid_content_type", "面试请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "面试请求格式无效。", 422)
        body["session_id"] = body.get("session_id") or ("iv_" + uuid.uuid4().hex[:16])
        ensure_session_access(body["session_id"], allow_create=True)

        # 通过 targetJobId 把面试接到目标岗位上：出题顺序直接来自该岗位的未解决缺口
        # （P0 → P1 → P2），这就是"按 Gap 定向出题"的落地方式。
        target_job_id = body.get("targetJobId")
        plan = None
        if target_job_id is not None:
            try:
                target_job_id = int(target_job_id)
            except (TypeError, ValueError):
                raise ApiError("invalid_request", "目标岗位 ID 无效。", 422)
            owner = _task_owner_key()
            gaps = target_job_service.interview_gaps(target_job_id, owner)
            if not body.get("matchGaps"):
                body["matchGaps"] = gaps
            plan = target_job_service.question_plan(target_job_id, owner)

        result = start_interview(body)
        if plan is not None:
            result["questionPlan"] = plan
            result["targetJobId"] = target_job_id
        return api_response(result)
    if route == "wf04/answer" and request.method == "POST":
        require_consent()
        enforce_usage("interview_turn_hour", 120, 3600)
        if not request.is_json:
            raise ApiError("invalid_content_type", "面试请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "面试请求格式无效。", 422)
        if not body.get("session_id"):
            raise ApiError("session_required", "缺少面试会话标识。", 422)
        ensure_session_access(body.get("session_id"))
        return api_response(answer_interview(body))
    if route == "wf04/end" and request.method == "POST":
        require_consent()
        if not request.is_json:
            raise ApiError("invalid_content_type", "面试请求必须使用 JSON 格式。", 415)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError("invalid_request", "面试请求格式无效。", 422)
        if not body.get("session_id"):
            raise ApiError("session_required", "缺少面试会话标识。", 422)
        ensure_session_access(body.get("session_id"))
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
        # A never-seen/deleted id contains no data and may be safely bound so
        # the domain layer can return its existing "insufficient evidence" response.
        ensure_session_access(session_id, allow_create=True)
        ability, result = build_ability_profile(session_id)
        return api_response({
            "ability": ability,
            "radar_option": build_option(ability),
            "score_R": ability["resume_score"],
            "score_M": ability["match_score"],
            "score_I": ability["interview_score"],
            "C0": ability["baseline"],
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
        ensure_session_access(session_id)
        owner_key = _task_owner_key()
        try:
            deleted = delete_session_data(session_id, owner_key=owner_key)
        except Exception:
            app.logger.exception("DB delete session failed")
            raise ApiError("delete_failed", "数据删除失败，请稍后重试。", 500)
        if not deleted:
            raise ApiError("session_not_found", "会话不存在或无权访问。", 404)
        return api_response({
            "status": "DELETED",
            "deleted_at": __import__("datetime").datetime.now().isoformat(),
            "session_id": session_id,
        })

    if route == "admin/resumes" and request.method == "GET":
        enforce_usage("admin_read", 10, 900, owner_key=_client_rate_key())
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
        enforce_usage("admin_export", 3, 3600, owner_key=_client_rate_key())
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
    "/api/auth/register", "/api/auth/login", "/api/auth/logout", "/api/auth/me",
    "/api/history", "/api/history/<id>",
    "/api/wf04/stream",
    "/api/wf02/optimize", "/api/wf02/apply-rewrite",
    "/api/wf07/cover-letter", "/api/wf07/applications",
    "/api/f5/organizations/status", "/api/f5/organizations/suggest",
    "/api/f5/organizations/discover", "/api/f5/organizations/detail",
    "/api/f5/organizations/jobs",
    # Phase 3 · 核心闭环：职业证据档案 + 目标岗位分析
    "/api/profile",
    "/api/profile/evidence/candidates",
    "/api/profile/evidence/<id>",
    "/api/profile/evidence/<id>/confirm",
    "/api/profile/evidence/<id>/reject",
    "/api/profile/evidence/<id>/edit",
    "/api/target-jobs",
    "/api/target-jobs/<id>",
    "/api/target-jobs/<id>/analyse",
    "/api/target-jobs/<id>/decision",
):
    app.add_url_rule(_rule, endpoint="route_" + _rule.replace("/", "_") or "root", view_func=route_api,
                     methods=["GET", "POST", "DELETE", "OPTIONS"])
