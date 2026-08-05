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


def db_path():
    """Resolve the DB path from the environment on each call (test-friendly)."""
    return Path(os.environ.get("RESUME_DB_PATH", "/tmp/resumes.db"))

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

CREATE TABLE IF NOT EXISTS matches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL UNIQUE,
    match_json  TEXT NOT NULL,
    score_m     REAL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_matches_session ON matches(session_id);

CREATE TABLE IF NOT EXISTS interview_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL UNIQUE,
    state       TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_session ON interview_sessions(session_id);

CREATE TABLE IF NOT EXISTS abilities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL UNIQUE,
    ability_json TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_abilities_session ON abilities(session_id);

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
    path = db_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    conn = sqlite3.connect(str(path), timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


def init_db():
    """Create tables and indexes if they do not exist."""
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
            "db_path": str(db_path()),
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


# ------------------------------------------------------------------ #
# F2/F3/F4/F5 session-level persistence
# ------------------------------------------------------------------ #

def save_match(session_id, match_json, score_m):
    """Persist a JD match result for a session (upsert)."""
    init_db()
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO matches (session_id, match_json, score_m, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                match_json=excluded.match_json,
                score_m=excluded.score_m
            """,
            (session_id, json.dumps(match_json, ensure_ascii=False)[:500000],
             score_m, _utc_iso()),
        )
        return True
    finally:
        conn.close()


def load_match(session_id):
    """Return the latest match payload for a session, or None."""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT match_json, score_m FROM matches WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["match_json"])
        except (TypeError, ValueError):
            payload = {}
        payload.setdefault("score_M", row["score_m"])
        return payload
    finally:
        conn.close()


def save_session(session_id, state, payload):
    """Create or replace an interview session record."""
    init_db()
    conn = _get_conn()
    now = _utc_iso()
    try:
        conn.execute(
            """
            INSERT INTO interview_sessions (session_id, state, payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                state=excluded.state, payload=excluded.payload, updated_at=excluded.updated_at
            """,
            (session_id, state, json.dumps(payload, ensure_ascii=False), now, now),
        )
        return True
    finally:
        conn.close()


def load_session(session_id):
    """Return (state, payload) for an interview session, or (None, None)."""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT state, payload FROM interview_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None, None
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            payload = {}
        return row["state"], payload
    finally:
        conn.close()


def update_session(session_id, state, payload):
    """Update an existing interview session record."""
    return save_session(session_id, state, payload)


def save_ability(session_id, ability_json):
    """Persist an AbilityProfile for a session (upsert)."""
    init_db()
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO abilities (session_id, ability_json, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET ability_json=excluded.ability_json
            """,
            (session_id, json.dumps(ability_json, ensure_ascii=False), _utc_iso()),
        )
        return True
    finally:
        conn.close()


def load_ability(session_id):
    """Return the AbilityProfile for a session, or None."""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT ability_json FROM abilities WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["ability_json"])
        except (TypeError, ValueError):
            return None
    finally:
        conn.close()


def delete_session_data(session_id):
    """WF-06: remove all session data (resume, diagnosis, match, interview, ability)."""
    init_db()
    conn = _get_conn()
    try:
        resume_row = conn.execute(
            "SELECT id FROM resumes WHERE session_id = ?", (session_id,)
        ).fetchone()
        if resume_row:
            conn.execute(
                "DELETE FROM diagnoses WHERE resume_id = ?", (resume_row["id"],)
            )
            conn.execute(
                "DELETE FROM resumes WHERE id = ?", (resume_row["id"],)
            )
        conn.execute("DELETE FROM matches WHERE session_id = ?", (session_id,))
        conn.execute(
            "DELETE FROM interview_sessions WHERE session_id = ?", (session_id,)
        )
        conn.execute("DELETE FROM abilities WHERE session_id = ?", (session_id,))
        return True
    finally:
        conn.close()
