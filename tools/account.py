"""Account & history domain logic for the career-coach service.

Passwords are hashed with werkzeug.security (never stored in plaintext).
Sessions are opaque random tokens stored hashed in the database; the client
receives the token in an HttpOnly cookie and/or the response body.
"""
import hashlib
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from tools.database import (
    add_history_event,
    count_history_events,
    create_session_row,
    create_user,
    delete_history_event,
    delete_session_data,
    delete_session_row,
    get_history_event,
    get_session_user_id,
    get_user_by_id,
    get_user_by_identifier,
    list_history_events,
    touch_last_login,
)


class AccountError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _utc_iso(dt=None):
    return (dt or datetime.now(timezone.utc)).isoformat()


def hash_password(password):
    return generate_password_hash(password, method="pbkdf2:sha256")


def verify_password(password, password_hash):
    try:
        return check_password_hash(password_hash, password)
    except (TypeError, ValueError):
        return False


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def register_user(phone, email, password, display_name, role="user"):
    """Create a user; raises AccountError on duplicate phone/email."""
    if get_user_by_identifier(phone):
        raise AccountError("phone_taken", "该手机号已注册，请直接登录。", 409)
    if get_user_by_identifier(email):
        raise AccountError("email_taken", "该邮箱已注册，请直接登录。", 409)
    user_id = create_user(
        phone, email, hash_password(password), display_name, role=role
    )
    return get_user_by_id(user_id)


def authenticate(identifier, password):
    user = get_user_by_identifier(identifier)
    if not user or not verify_password(password, user["password_hash"]):
        return None
    touch_last_login(user["id"])
    return user


def create_session(user_id, ttl_days=30):
    token = secrets.token_urlsafe(32)
    expires_at = _utc_iso(datetime.now(timezone.utc) + timedelta(days=ttl_days))
    create_session_row(_token_hash(token), user_id, expires_at)
    return token, expires_at


def session_user(token):
    if not token:
        return None
    user_id = get_session_user_id(_token_hash(token))
    return get_user_by_id(user_id) if user_id else None


def end_session(token):
    if token:
        delete_session_row(_token_hash(token))


def public_user(user):
    """De-identified user view for API responses."""
    return {
        "id": user["id"],
        "phone": user["phone"],
        "email": user["email"],
        "name": user["display_name"],
        "role": user["role"],
        "created_at": user["created_at"],
        "last_login_at": user.get("last_login_at"),
    }


DEMO_HISTORY = [
    {"event_type": "F1", "title": "后端开发简历诊断 · R82", "status": "done"},
    {"event_type": "F2", "title": "后端开发工程师（校招）匹配", "status": "done"},
    {"event_type": "F3", "title": "3 轮模拟面试 · 追问 4 次", "status": "partial"},
    {"event_type": "F4", "title": "六维能力报告 · C0=68.3", "status": "done"},
    {"event_type": "F1", "title": "数据分析简历诊断 · R74", "status": "done"},
    {"event_type": "F2", "title": "数据分析师 JD 匹配 · 缺口 3 项", "status": "partial"},
]


def list_history(user_id, limit=50, offset=0, event_type=None, role="user"):
    items = list_history_events(user_id, limit=limit, offset=offset, event_type=event_type)
    total = count_history_events(user_id, event_type=event_type)
    # 演示数据仅对开发者（role=admin）且 DEV_DEMO=1 可见，且不落库。
    if (
        role == "admin"
        and os.environ.get("DEV_DEMO", "").strip() == "1"
        and offset == 0
        and not event_type
    ):
        now = _utc_iso()
        demo = [
            {
                "id": -1 - i,
                "user_id": user_id,
                "session_id": "demo-" + str(i),
                "event_type": item["event_type"],
                "title": item["title"] + "（演示）",
                "status": item["status"],
                "created_at": now,
            }
            for i, item in enumerate(DEMO_HISTORY)
        ]
        items = demo + items
        total += len(demo)
    return items, total


def add_history(user_id, session_id, event_type, title, status):
    return add_history_event(user_id, session_id, event_type, title, status)


def delete_history(user_id, event_id):
    event = get_history_event(event_id, user_id)
    if not event:
        raise AccountError("not_found", "记录不存在或无权访问。", 404)
    delete_session_data(event["session_id"])
    delete_history_event(event_id, user_id)


# ------------------------------------------------------------------ #
# Lightweight rate limiting (in-memory; soft limit per instance)
# ------------------------------------------------------------------ #
_RATE_BUCKETS = {}


def check_rate(key, limit=5, window=60):
    now = time.monotonic()
    bucket = _RATE_BUCKETS.get(key, [])
    bucket = [t for t in bucket if now - t < window]
    if len(bucket) >= limit:
        _RATE_BUCKETS[key] = bucket
        raise AccountError(
            "rate_limited", "操作过于频繁，请稍后再试。", 429
        )
    bucket.append(now)
    _RATE_BUCKETS[key] = bucket
