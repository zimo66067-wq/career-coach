"""Resume database layer.

Lightweight SQLite persistence for anonymized resume submissions and diagnosis
results.  Designed for serverless environments (Vercel) where the DB lives on
/tmp and is ephemeral across cold starts.
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = Path(os.environ.get("RESUME_DB_PATH", "/tmp/resumes.db"))
_INIT_SQL = """
CREATE TABLE IF NOT EXISTS resumes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL UNIQUE,
    client_ip   TEXT,
    user_agent  TEXT,
    filename    TEXT,
    file_type   TEXT,
    file_size   INTEGER,
    resume_text TEXT,                -- de-identified
    created_at  TEXT NOT NULL,
    has_diagnosis INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_resumes_session ON resumes(session_id);
CREATE INDEX IF NOT EXISTS idx_resumes_created ON resumes(created_at);

CREATE TABLE IF NOT EXISTS diagnoses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_id       INTEGER NOT NULL,
    score_r         REAL,
    diagnosis_mode  TEXT,
    diagnosis_notice TEXT,
    model_trace_id  TEXT,
    diagnosis_json  TEXT,            -- JSON string of resumeProfile
    created_at      TEXT NOT NULL,
    FOREIGN KEY (resume_id) REFERENCES resumes(id)
);
"""


def _utc_iso():
    return datetime.now(timezone.utc).isoformat()


def _get_conn():
    """Return a connection; parent dirs are guaranteed to exist in /tmp."""
    conn = sqlite3.connect(str(_DB_PATH), timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


def init_db():
    """Create tables and indexes if they do not exist."""
    try:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    conn = _get_conn()
    try:
        conn.executescript(_INIT_SQL)
    finally:
        conn.close()


def save_resume(session_id, client_ip, user_agent, filename, file_type,
                file_size, resume_text):
    """Persist a de-identified resume upload.  Returns the row id."""
    init_db()
    conn = _get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO resumes (session_id, client_ip, user_agent, filename,
                                 file_type, file_size, resume_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                resume_text=excluded.resume_text,
                filename=excluded.filename,
                file_type=excluded.file_type,
                file_size=excluded.file_size
            """,
            (session_id, client_ip, user_agent, filename, file_type,
             file_size, resume_text, _utc_iso()),
        )
        return cur.lastrowid
    finally:
        conn.close()


def save_diagnosis(session_id, score_r, diagnosis_mode, diagnosis_notice,
                   model_trace_id, diagnosis_json):
    """Attach or update diagnosis for a resume by session_id."""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM resumes WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row:
            return None
        resume_id = row["id"]
        conn.execute(
            """
            INSERT INTO diagnoses (resume_id, score_r, diagnosis_mode,
                                   diagnosis_notice, model_trace_id,
                                   diagnosis_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (resume_id, score_r, diagnosis_mode, diagnosis_notice,
             model_trace_id, diagnosis_json, _utc_iso()),
        )
        conn.execute(
            "UPDATE resumes SET has_diagnosis = 1 WHERE id = ?",
            (resume_id,),
        )
        return resume_id
    finally:
        conn.close()


def list_resumes(limit=100, offset=0):
    """List resume uploads with their latest diagnosis if any."""
    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT
                r.id,
                r.session_id,
                r.filename,
                r.file_type,
                r.file_size,
                r.created_at,
                r.has_diagnosis,
                d.score_r,
                d.diagnosis_mode,
                d.model_trace_id,
                d.created_at AS diag_created_at
            FROM resumes r
            LEFT JOIN (
                SELECT resume_id, score_r, diagnosis_mode, model_trace_id, MAX(created_at) AS created_at
                FROM diagnoses GROUP BY resume_id
            ) d ON d.resume_id = r.id
            ORDER BY r.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def count_resumes():
    """Total number of stored resumes."""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM resumes").fetchone()
        return row["c"] if row else 0
    finally:
        conn.close()


def get_resume_detail(session_id):
    """Return one resume plus its full diagnosis history."""
    init_db()
    conn = _get_conn()
    try:
        resume = conn.execute(
            "SELECT * FROM resumes WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not resume:
            return None
        diags = conn.execute(
            """SELECT score_r, diagnosis_mode, diagnosis_notice,
                      model_trace_id, diagnosis_json, created_at
               FROM diagnoses WHERE resume_id = ? ORDER BY created_at DESC""",
            (resume["id"],),
        ).fetchall()
        return {
            "resume": dict(resume),
            "diagnoses": [dict(d) for d in diags],
        }
    finally:
        conn.close()


def export_all():
    """Return every resume and diagnosis as a serializable dict."""
    init_db()
    conn = _get_conn()
    try:
        resumes = conn.execute(
            "SELECT * FROM resumes ORDER BY created_at DESC"
        ).fetchall()
        diagnoses = conn.execute(
            "SELECT * FROM diagnoses ORDER BY created_at DESC"
        ).fetchall()
        return {
            "resumes": [dict(r) for r in resumes],
            "diagnoses": [dict(d) for d in diagnoses],
            "exported_at": _utc_iso(),
            "db_path": str(_DB_PATH),
        }
    finally:
        conn.close()


def admin_password_ok(password):
    """Check admin password from environment variable."""
    expected = os.environ.get("ADMIN_PASSWORD", "").strip()
    if not expected:
        return False
    # Constant-time comparison to mitigate timing attacks.
    if len(password) != len(expected):
        return False
    result = 0
    for a, b in zip(password, expected):
        result |= ord(a) ^ ord(b)
    return result == 0
