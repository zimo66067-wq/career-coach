# -*- coding: utf-8 -*-
"""身份、同意与配额（Phase 7c 从 `api/index.py` 逐字拆出）。

三件事在这里合流，因为它们在语义上本来就是一件事 —— **"这次请求算谁的"**：

| 关注点 | 回答的问题 | 载体 |
| --- | --- | --- |
| 账号会话 | 这是哪个登录用户？ | `Authorization: Bearer` / `zy_session` Cookie |
| 同意记录（WF-01 闸门） | 这个人同意过数据处理说明吗？ | `X-Consent-Token`（签名、短时效） |
| 匿名归属 | 没登录的人怎么拥有一份数据？ | `X-Guest-Token`（签名、长时效） |
| 配额 | 这个 owner 最近用超了吗？ | 数据库计数（跨 serverless 实例共享） |

把 owner 的推导（`_owner_context`）和配额（`enforce_usage`）放在一起，是为了让
"所有权的唯一来源"只有一处 —— 配额必须按 owner 计，按 IP 计会在登录前后割裂。

## 打桩点

`consent_serializer` / `guest_serializer` 是**测试的打桩点**：`tests/test_api_boundary.py`
会把它换成"已过期"/"签名错误"的假 serializer，来验证 401 分支真的可达。所以它们是
模块级函数、被同模块的 `require_consent` 以**模块内全局名**调用 —— 打桩必须打在
*本模块*（`api.security.consent_serializer`），打在别处不会生效。
"""
import hashlib
import os
import re
import uuid

from flask import request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from services.account_service import session_user
from domain.internal.api_errors import ApiError
from repositories.database import (
    bind_session_owner,
    consume_usage,
    get_session_owner,
    transfer_owner_data,
)

from api.app_instance import app
from api.constants import (
    CONSENT_TOKEN_SALT,
    DEFAULT_CONSENT_MAX_AGE_SECONDS,
    DEFAULT_GUEST_MAX_AGE_SECONDS,
    GUEST_TOKEN_SALT,
)

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
