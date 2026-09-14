"""Database layer for the career-coach service.

Supports two dialects:
- SQLite (local development / tests), path from RESUME_DB_PATH.
- PostgreSQL (production, e.g. Neon on Vercel), connection string from
  DATABASE_URL.  Session data is therefore persistent across cold starts.
"""
import hashlib
import json
import os
import sqlite3
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


def db_path():
    """Resolve the SQLite DB path from the environment on each call."""
    return Path(os.environ.get("RESUME_DB_PATH", "/tmp/resumes.db"))


def dialect():
    """Return 'postgres' when DATABASE_URL is configured, else 'sqlite'."""
    return "postgres" if os.environ.get("DATABASE_URL", "").strip() else "sqlite"


# Tables kept only by features that no longer exist.  They are dropped on
# startup (idempotently) so a database created by an older build does not keep
# storage that no code path reads or writes.
_RETIRED_TABLES = ("tasks",)


def _render(sql):
    """Translate SQLite placeholders to psycopg placeholders."""
    if dialect() == "postgres":
        return sql.replace("?", "%s")
    return sql


class _PsycopgConnection:
    """Minimal psycopg wrapper exposing the sqlite3-style API used here."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        return self._conn.execute(_render(sql), params)

    def close(self):
        self._conn.close()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

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

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    phone         TEXT UNIQUE NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    created_at    TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS history_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    title      TEXT NOT NULL,
    status     TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_history_user ON history_events(user_id, created_at DESC);
CREATE TABLE IF NOT EXISTS resume_rewrites (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL,
    suggestion_id  TEXT,
    issue          TEXT,
    candidate_text TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',
    created_at     TEXT NOT NULL,
    applied_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_rewrites_session ON resume_rewrites(session_id, status);
CREATE TABLE IF NOT EXISTS applications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    owner_key    TEXT NOT NULL,
    company      TEXT NOT NULL,
    position     TEXT NOT NULL,
    cover_letter TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'applied',
    target_job_id INTEGER,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_applications_owner ON applications(owner_key, created_at DESC);

CREATE TABLE IF NOT EXISTS session_owners (
    session_id TEXT PRIMARY KEY,
    owner_key  TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_session_owners_owner ON session_owners(owner_key, updated_at DESC);

CREATE TABLE IF NOT EXISTS usage_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_key     TEXT NOT NULL,
    bucket        TEXT NOT NULL,
    created_epoch INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_events_window ON usage_events(owner_key, bucket, created_epoch);

-- ---------------------------------------------------------------- --
-- F5 unit/job index (plan section 4.1-4.2, phase 1 foundation).
-- Holds only fields a licensed source permits us to store and show.
-- Empty until an authorised data source is configured: nothing here is
-- ever generated by a language model.
-- ---------------------------------------------------------------- --
CREATE TABLE IF NOT EXISTS organizations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_provider   TEXT NOT NULL,
    source_key        TEXT NOT NULL,
    canonical_name    TEXT NOT NULL,
    normalized_name   TEXT NOT NULL DEFAULT '',
    org_type          TEXT NOT NULL DEFAULT 'unknown',
    region            TEXT,
    industry          TEXT,
    unified_id        TEXT,
    status            TEXT NOT NULL DEFAULT 'unknown',
    website           TEXT,
    source_url        TEXT,
    source_updated_at TEXT,
    verified_at       TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_organizations_source ON organizations(source_provider, source_key);
CREATE INDEX IF NOT EXISTS idx_organizations_name ON organizations(normalized_name);
CREATE INDEX IF NOT EXISTS idx_organizations_region ON organizations(region, org_type);

CREATE TABLE IF NOT EXISTS organization_aliases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL,
    alias           TEXT NOT NULL,
    normalized      TEXT NOT NULL,
    alias_type      TEXT NOT NULL DEFAULT 'alias',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_org_aliases_org ON organization_aliases(organization_id);
CREATE INDEX IF NOT EXISTS idx_org_aliases_norm ON organization_aliases(normalized);

CREATE TABLE IF NOT EXISTS organization_profiles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL,
    business_scope  TEXT,
    products        TEXT,
    tech_fields     TEXT,
    size_band       TEXT,
    content_hash    TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_org_profiles_org ON organization_profiles(organization_id);

CREATE TABLE IF NOT EXISTS source_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_provider TEXT NOT NULL,
    source_url      TEXT,
    license_scope   TEXT,
    content_hash    TEXT NOT NULL,
    parser_version  TEXT,
    fetched_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_snapshots_provider ON source_snapshots(source_provider, fetched_at DESC);

CREATE TABLE IF NOT EXISTS job_postings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER,
    source_provider TEXT NOT NULL,
    external_job_id TEXT NOT NULL,
    title           TEXT NOT NULL,
    location        TEXT,
    job_type        TEXT,
    skill_tags      TEXT,
    jd_summary      TEXT,
    source_url      TEXT,
    status          TEXT NOT NULL DEFAULT 'unknown',
    published_at    TEXT,
    expires_at      TEXT,
    last_seen_at    TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_job_postings_source ON job_postings(source_provider, external_job_id);
CREATE INDEX IF NOT EXISTS idx_job_postings_org ON job_postings(organization_id, status);

CREATE TABLE IF NOT EXISTS job_posting_versions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    job_posting_id INTEGER NOT NULL,
    content_hash   TEXT NOT NULL,
    changed_fields TEXT,
    observed_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_job_versions_posting ON job_posting_versions(job_posting_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS job_embeddings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_posting_id  INTEGER,
    organization_id INTEGER,
    content_hash    TEXT NOT NULL,
    model           TEXT,
    vector_json     TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_job_embeddings_org ON job_embeddings(organization_id);

-- ---- Phase 2 · 领域收敛：职业证据 / 目标岗位 / 行动闭环 ----
-- 口径依据 docs/domain-model.md：
--   * CareerEvidence 是个人职业事实的唯一可信来源，必须带可回指的 source_quote
--   * AI 产出的证据只能以 status='pending' 落库，user_confirmed 只能由用户确认置位
--   * 目标岗位决策必须引用 >=3 条 evidence（在 domain 层校验）

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS career_profiles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_key    TEXT NOT NULL UNIQUE,
    display_name TEXT,
    headline     TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS career_evidence (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_key      TEXT NOT NULL,
    evidence_type  TEXT NOT NULL,
    claim          TEXT NOT NULL,
    source_type    TEXT NOT NULL,
    source_id      TEXT,
    source_quote   TEXT NOT NULL,
    confidence     REAL NOT NULL DEFAULT 0.5,
    status         TEXT NOT NULL DEFAULT 'pending',
    user_confirmed INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    confirmed_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_evidence_owner ON career_evidence(owner_key, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_source ON career_evidence(source_type, source_id);

CREATE TABLE IF NOT EXISTS target_jobs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_key        TEXT NOT NULL,
    session_id       TEXT,
    company          TEXT,
    position         TEXT,
    jd_text          TEXT,
    job_profile_json TEXT,
    status           TEXT NOT NULL DEFAULT 'open',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_target_jobs_owner ON target_jobs(owner_key, created_at DESC);

CREATE TABLE IF NOT EXISTS job_requirements (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    target_job_id    INTEGER NOT NULL,
    req_key          TEXT NOT NULL,
    req_type         TEXT NOT NULL,
    text             TEXT NOT NULL,
    ordinal          INTEGER NOT NULL DEFAULT 0,
    source_span_json TEXT,
    created_at       TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_requirements_key ON job_requirements(target_job_id, req_key);

CREATE TABLE IF NOT EXISTS evidence_matches (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    requirement_id INTEGER NOT NULL,
    evidence_id    INTEGER,
    match_status   TEXT NOT NULL,
    rationale      TEXT,
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_matches_req ON evidence_matches(requirement_id);

CREATE TABLE IF NOT EXISTS gaps (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    target_job_id     INTEGER NOT NULL,
    requirement_id    INTEGER,
    gap_type          TEXT NOT NULL,
    priority          TEXT NOT NULL,
    reason            TEXT,
    current_evidence  TEXT,
    missing_evidence  TEXT,
    action            TEXT,
    expected_artifact TEXT,
    retest            TEXT,
    status            TEXT NOT NULL DEFAULT 'open',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gaps_target ON gaps(target_job_id, priority);

CREATE TABLE IF NOT EXISTS target_job_decisions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    target_job_id  INTEGER NOT NULL,
    decision       TEXT NOT NULL,
    rationale_json TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_decisions_target ON target_job_decisions(target_job_id, created_at DESC);

CREATE TABLE IF NOT EXISTS actions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_key  TEXT NOT NULL,
    gap_id     INTEGER,
    task       TEXT NOT NULL,
    artifact   TEXT,
    outcome    TEXT,
    status     TEXT NOT NULL DEFAULT 'todo',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_actions_owner ON actions(owner_key, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS application_outcomes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    outcome        TEXT NOT NULL,
    note           TEXT,
    recorded_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_outcomes_application ON application_outcomes(application_id, recorded_at DESC);
"""


_INIT_SQL_PG = """
CREATE TABLE IF NOT EXISTS resumes (
    id BIGSERIAL PRIMARY KEY, session_id TEXT NOT NULL UNIQUE, client_ip TEXT,
    user_agent TEXT, filename TEXT, file_type TEXT, file_size INTEGER,
    resume_text TEXT, created_at TEXT NOT NULL, has_diagnosis INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_resumes_session ON resumes(session_id);
CREATE INDEX IF NOT EXISTS idx_resumes_created ON resumes(created_at);
CREATE TABLE IF NOT EXISTS matches (
    id BIGSERIAL PRIMARY KEY, session_id TEXT NOT NULL UNIQUE,
    match_json TEXT NOT NULL, score_m DOUBLE PRECISION, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_matches_session ON matches(session_id);
CREATE TABLE IF NOT EXISTS interview_sessions (
    id BIGSERIAL PRIMARY KEY, session_id TEXT NOT NULL UNIQUE, state TEXT NOT NULL,
    payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_session ON interview_sessions(session_id);
CREATE TABLE IF NOT EXISTS abilities (
    id BIGSERIAL PRIMARY KEY, session_id TEXT NOT NULL UNIQUE,
    ability_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_abilities_session ON abilities(session_id);
CREATE TABLE IF NOT EXISTS diagnoses (
    id BIGSERIAL PRIMARY KEY, resume_id BIGINT NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    score_r DOUBLE PRECISION, diagnosis_mode TEXT, diagnosis_notice TEXT,
    model_trace_id TEXT, diagnosis_json TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY, phone TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL, display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL, last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS history_events (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL, event_type TEXT NOT NULL, title TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_user ON history_events(user_id, created_at DESC);
CREATE TABLE IF NOT EXISTS resume_rewrites (
    id BIGSERIAL PRIMARY KEY, session_id TEXT NOT NULL, suggestion_id TEXT,
    issue TEXT, candidate_text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL, applied_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_rewrites_session ON resume_rewrites(session_id, status);
CREATE TABLE IF NOT EXISTS applications (
    id BIGSERIAL PRIMARY KEY, session_id TEXT NOT NULL, owner_key TEXT NOT NULL,
    company TEXT NOT NULL, position TEXT NOT NULL, cover_letter TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'applied', target_job_id BIGINT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_applications_owner ON applications(owner_key, created_at DESC);
CREATE TABLE IF NOT EXISTS session_owners (
    session_id TEXT PRIMARY KEY, owner_key TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session_owners_owner ON session_owners(owner_key, updated_at DESC);
CREATE TABLE IF NOT EXISTS usage_events (
    id BIGSERIAL PRIMARY KEY, owner_key TEXT NOT NULL, bucket TEXT NOT NULL,
    created_epoch BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_events_window ON usage_events(owner_key, bucket, created_epoch);
CREATE TABLE IF NOT EXISTS organizations (
    id BIGSERIAL PRIMARY KEY, source_provider TEXT NOT NULL, source_key TEXT NOT NULL,
    canonical_name TEXT NOT NULL, normalized_name TEXT NOT NULL DEFAULT '',
    org_type TEXT NOT NULL DEFAULT 'unknown', region TEXT,
    industry TEXT, unified_id TEXT, status TEXT NOT NULL DEFAULT 'unknown', website TEXT,
    source_url TEXT, source_updated_at TEXT, verified_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_organizations_source ON organizations(source_provider, source_key);
CREATE INDEX IF NOT EXISTS idx_organizations_name ON organizations(normalized_name);
CREATE INDEX IF NOT EXISTS idx_organizations_region ON organizations(region, org_type);
CREATE TABLE IF NOT EXISTS organization_aliases (
    id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL, alias TEXT NOT NULL,
    normalized TEXT NOT NULL, alias_type TEXT NOT NULL DEFAULT 'alias', created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_org_aliases_org ON organization_aliases(organization_id);
CREATE INDEX IF NOT EXISTS idx_org_aliases_norm ON organization_aliases(normalized);
CREATE TABLE IF NOT EXISTS organization_profiles (
    id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL, business_scope TEXT,
    products TEXT, tech_fields TEXT, size_band TEXT, content_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_org_profiles_org ON organization_profiles(organization_id);
CREATE TABLE IF NOT EXISTS source_snapshots (
    id BIGSERIAL PRIMARY KEY, source_provider TEXT NOT NULL, source_url TEXT,
    license_scope TEXT, content_hash TEXT NOT NULL, parser_version TEXT, fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_source_snapshots_provider ON source_snapshots(source_provider, fetched_at DESC);
CREATE TABLE IF NOT EXISTS job_postings (
    id BIGSERIAL PRIMARY KEY, organization_id BIGINT, source_provider TEXT NOT NULL,
    external_job_id TEXT NOT NULL, title TEXT NOT NULL, location TEXT, job_type TEXT,
    skill_tags TEXT, jd_summary TEXT, source_url TEXT, status TEXT NOT NULL DEFAULT 'unknown',
    published_at TEXT, expires_at TEXT, last_seen_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_job_postings_source ON job_postings(source_provider, external_job_id);
CREATE INDEX IF NOT EXISTS idx_job_postings_org ON job_postings(organization_id, status);
CREATE TABLE IF NOT EXISTS job_posting_versions (
    id BIGSERIAL PRIMARY KEY, job_posting_id BIGINT NOT NULL, content_hash TEXT NOT NULL,
    changed_fields TEXT, observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_versions_posting ON job_posting_versions(job_posting_id, observed_at DESC);
CREATE TABLE IF NOT EXISTS job_embeddings (
    id BIGSERIAL PRIMARY KEY, job_posting_id BIGINT, organization_id BIGINT,
    content_hash TEXT NOT NULL, model TEXT, vector_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_embeddings_org ON job_embeddings(organization_id);

-- ---- Phase 2 · 领域收敛（PostgreSQL 方言，见 docs/domain-model.md）----
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY, applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS career_profiles (
    id BIGSERIAL PRIMARY KEY, owner_key TEXT NOT NULL UNIQUE, display_name TEXT,
    headline TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_career_profiles_owner ON career_profiles(owner_key);
CREATE TABLE IF NOT EXISTS career_evidence (
    id BIGSERIAL PRIMARY KEY, owner_key TEXT NOT NULL, evidence_type TEXT NOT NULL,
    claim TEXT NOT NULL, source_type TEXT NOT NULL, source_id TEXT, source_quote TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5, status TEXT NOT NULL DEFAULT 'pending',
    user_confirmed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL, confirmed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_evidence_owner ON career_evidence(owner_key, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_source ON career_evidence(source_type, source_id);
CREATE TABLE IF NOT EXISTS target_jobs (
    id BIGSERIAL PRIMARY KEY, owner_key TEXT NOT NULL, session_id TEXT, company TEXT,
    position TEXT, jd_text TEXT, job_profile_json TEXT, status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_target_jobs_owner ON target_jobs(owner_key, created_at DESC);
CREATE TABLE IF NOT EXISTS job_requirements (
    id BIGSERIAL PRIMARY KEY, target_job_id BIGINT NOT NULL, req_key TEXT NOT NULL,
    req_type TEXT NOT NULL, text TEXT NOT NULL, ordinal INTEGER NOT NULL DEFAULT 0,
    source_span_json TEXT, created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_requirements_key ON job_requirements(target_job_id, req_key);
CREATE TABLE IF NOT EXISTS evidence_matches (
    id BIGSERIAL PRIMARY KEY, requirement_id BIGINT NOT NULL, evidence_id BIGINT,
    match_status TEXT NOT NULL, rationale TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_matches_req ON evidence_matches(requirement_id);
CREATE TABLE IF NOT EXISTS gaps (
    id BIGSERIAL PRIMARY KEY, target_job_id BIGINT NOT NULL, requirement_id BIGINT,
    gap_type TEXT NOT NULL, priority TEXT NOT NULL, reason TEXT, current_evidence TEXT,
    missing_evidence TEXT, action TEXT, expected_artifact TEXT, retest TEXT,
    status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gaps_target ON gaps(target_job_id, priority);
CREATE TABLE IF NOT EXISTS target_job_decisions (
    id BIGSERIAL PRIMARY KEY, target_job_id BIGINT NOT NULL, decision TEXT NOT NULL,
    rationale_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_target ON target_job_decisions(target_job_id, created_at DESC);
CREATE TABLE IF NOT EXISTS actions (
    id BIGSERIAL PRIMARY KEY, owner_key TEXT NOT NULL, gap_id BIGINT, task TEXT NOT NULL,
    artifact TEXT, outcome TEXT, status TEXT NOT NULL DEFAULT 'todo',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_actions_owner ON actions(owner_key, status, updated_at DESC);
CREATE TABLE IF NOT EXISTS application_outcomes (
    id BIGSERIAL PRIMARY KEY, application_id BIGINT NOT NULL, outcome TEXT NOT NULL,
    note TEXT, recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outcomes_application ON application_outcomes(application_id, recorded_at DESC);
"""


def _utc_iso():
    return datetime.now(timezone.utc).isoformat()


def _get_conn():
    """Return a connection in the configured dialect."""
    if dialect() == "postgres":
        import psycopg
        from psycopg.rows import dict_row

        raw = psycopg.connect(
            os.environ["DATABASE_URL"], autocommit=True, row_factory=dict_row
        )
        return _PsycopgConnection(raw)

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


#: Databases whose schema this process has already created.  Recommended because
#: every repository call goes through ``connection()`` -> ``init_db()``, and the
#: DDL is 29 tables plus their indexes; without this cache a read-only endpoint
#: such as /api/health would replay the whole script on every request.
_INITIALIZED = set()


def init_db():
    """Create tables and indexes if they do not exist.

    Cached per connection target for the life of the process.  The statements are
    all ``CREATE ... IF NOT EXISTS``, so replaying them is only wasted work, never
    a correctness requirement — and tests that point at a fresh database still get
    a real run because the key includes the resolved path.
    """
    key = "postgres" if dialect() == "postgres" else str(db_path())
    if key in _INITIALIZED:
        return
    conn = _get_conn()
    try:
        if dialect() == "postgres":
            for statement in _INIT_SQL_PG.split(";"):
                if statement.strip():
                    conn.execute(statement.strip())
        else:
            conn.executescript(_INIT_SQL)
        # Retire tables whose only consumer was removed.  The asynchronous task
        # queue existed solely to drive the major-based match, so both the
        # feature and its storage are gone; dropping here keeps existing
        # databases from carrying an orphan table nobody reads or writes.
        for retired in _RETIRED_TABLES:
            conn.execute("DROP TABLE IF EXISTS %s" % retired)
    finally:
        conn.close()
    _INITIALIZED.add(key)


def reset_init_cache():
    """Drop the "schema created" cache (tests that reuse a path after wiping it)."""
    _INITIALIZED.clear()


def _insert_returning_id(conn, sql, params):
    """Execute an insert and return its id on SQLite and PostgreSQL."""
    if dialect() == "postgres":
        row = conn.execute(f"{sql.rstrip()} RETURNING id", params).fetchone()
        return row["id"]
    return conn.execute(sql, params).lastrowid


# ------------------------------------------------------------------ #
# Public infrastructure façade
#
# The domain-consolidation layers (repositories/, services/) must not reach for
# the underscore-prefixed helpers above.  These four functions are the supported
# entry points for opening a connection, translating placeholders, inserting a
# row and reading the canonical timestamp, so the private names stay free to
# change without breaking callers.
# ------------------------------------------------------------------ #

def connection():
    """Ensure the schema exists and return an open connection (dialect-aware)."""
    init_db()
    return _get_conn()


def render(sql):
    """Translate ``?`` placeholders for the active dialect."""
    return _render(sql)


def insert_id(conn, sql, params):
    """Insert one row and return its generated id."""
    return _insert_returning_id(conn, sql, params)


def utc_iso():
    """Canonical UTC timestamp string used across every table."""
    return _utc_iso()


def has_column(conn, table, column):
    """True when ``table`` already has ``column`` (works on both dialects)."""
    if dialect() == "postgres":
        row = conn.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = %s",
            (table, column),
        ).fetchone()
        return row is not None
    rows = conn.execute("PRAGMA table_info(%s)" % table).fetchall()
    return any(row[1] == column for row in rows)


def table_names(conn):
    if dialect() == "postgres":
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
        return {row[0] for row in rows}
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def save_resume(session_id, client_ip, user_agent, filename, file_type,
                file_size, resume_text):
    """Persist a de-identified resume upload.  Returns the row id."""
    init_db()
    conn = _get_conn()
    try:
        conn.execute(
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
        row = conn.execute(
            "SELECT id FROM resumes WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row["id"] if row else None
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


def get_session_owner(session_id):
    """Return the server-side owner key bound to a workflow session."""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT owner_key FROM session_owners WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row["owner_key"] if row else None
    finally:
        conn.close()


def bind_session_owner(session_id, owner_key, previous_owner=None):
    """Claim a session or transfer it from an explicitly verified prior owner."""
    init_db()
    conn = _get_conn()
    now = _utc_iso()
    try:
        conn.execute(
            """
            INSERT INTO session_owners (session_id, owner_key, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO NOTHING
            """,
            (session_id, owner_key, now, now),
        )
        row = conn.execute(
            "SELECT owner_key FROM session_owners WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        current = row["owner_key"] if row else None
        if current == owner_key:
            conn.execute(
                "UPDATE session_owners SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            return True
        if previous_owner and current == previous_owner:
            cur = conn.execute(
                """
                UPDATE session_owners SET owner_key = ?, updated_at = ?
                WHERE session_id = ? AND owner_key = ?
                """,
                (owner_key, now, session_id, previous_owner),
            )
            return bool(getattr(cur, "rowcount", 0))
        return False
    finally:
        conn.close()


def transfer_owner_data(previous_owner, new_owner):
    """Move anonymous resources to a user after verified authentication."""
    if not previous_owner or previous_owner == new_owner:
        return 0
    init_db()
    conn = _get_conn()
    changed = 0
    try:
        conn.execute("BEGIN")
        for table in ("session_owners", "applications"):
            cur = conn.execute(
                f"UPDATE {table} SET owner_key = ? WHERE owner_key = ?",
                (new_owner, previous_owner),
            )
            changed += max(0, int(getattr(cur, "rowcount", 0) or 0))
        conn.commit()
        return changed
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def consume_usage(owner_key, bucket, limit, window_seconds, now_epoch=None):
    """Atomically consume one quota unit shared by all application instances."""
    init_db()
    conn = _get_conn()
    now_epoch = int(now_epoch if now_epoch is not None else time.time())
    cutoff = now_epoch - int(window_seconds)
    lock_key = f"{owner_key}:{bucket}"
    try:
        if dialect() == "postgres":
            conn.execute("BEGIN")
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (lock_key,))
        else:
            conn.execute("BEGIN IMMEDIATE")
        # A short-window bucket must never erase events retained by a longer
        # daily window. Cleanup is scoped to the same owner and bucket.
        conn.execute(
            """
            DELETE FROM usage_events
            WHERE owner_key = ? AND bucket = ? AND created_epoch < ?
            """,
            (owner_key, bucket, cutoff),
        )
        row = conn.execute(
            """
            SELECT COUNT(*) AS c, MIN(created_epoch) AS oldest
            FROM usage_events
            WHERE owner_key = ? AND bucket = ? AND created_epoch >= ?
            """,
            (owner_key, bucket, cutoff),
        ).fetchone()
        used = int(row["c"] if row else 0)
        oldest = row["oldest"] if row else None
        if used >= int(limit):
            conn.commit()
            retry_after = max(1, int(window_seconds) - (now_epoch - int(oldest or now_epoch)))
            return {"allowed": False, "remaining": 0, "retry_after": retry_after}
        conn.execute(
            "INSERT INTO usage_events (owner_key, bucket, created_epoch) VALUES (?, ?, ?)",
            (owner_key, bucket, now_epoch),
        )
        conn.commit()
        return {
            "allowed": True,
            "remaining": max(0, int(limit) - used - 1),
            "retry_after": 0,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_session_data(session_id, owner_key=None):
    """WF-06: transactionally remove all data for an owned workflow session."""
    init_db()
    conn = _get_conn()
    try:
        conn.execute("BEGIN")
        owner = conn.execute(
            "SELECT owner_key FROM session_owners WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if owner_key is not None and (not owner or owner["owner_key"] != owner_key):
            conn.rollback()
            return False
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
        conn.execute("DELETE FROM resume_rewrites WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM applications WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM history_events WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM session_owners WHERE session_id = ?", (session_id,))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# Account & history persistence (users / sessions / history_events)
# ------------------------------------------------------------------ #

def create_user(phone, email, password_hash, display_name, role="user"):
    """Insert a new user.  Raises on duplicate phone/email."""
    init_db()
    conn = _get_conn()
    try:
        return _insert_returning_id(
            conn,
            """
            INSERT INTO users (phone, email, password_hash, display_name,
                               role, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (phone, email, password_hash, display_name, role, _utc_iso()),
        )
    finally:
        conn.close()


def get_user_by_identifier(identifier):
    """Return a user by phone or email, or None."""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE phone = ? OR email = ? LIMIT 1",
            (identifier, identifier),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id):
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def touch_last_login(user_id):
    init_db()
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (_utc_iso(), user_id),
        )
    finally:
        conn.close()


def create_session_row(token_hash, user_id, expires_at):
    init_db()
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO sessions (id, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token_hash, user_id, _utc_iso(), expires_at),
        )
    finally:
        conn.close()


def get_session_user_id(token_hash):
    """Return user_id for a live session token, or None."""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT user_id FROM sessions WHERE id = ? AND expires_at > ?",
            (token_hash, _utc_iso()),
        ).fetchone()
        return row["user_id"] if row else None
    finally:
        conn.close()


def delete_session_row(token_hash):
    init_db()
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM sessions WHERE id = ?", (token_hash,))
    finally:
        conn.close()


def add_history_event(user_id, session_id, event_type, title, status):
    init_db()
    conn = _get_conn()
    try:
        return _insert_returning_id(
            conn,
            """
            INSERT INTO history_events (user_id, session_id, event_type,
                                        title, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, session_id, event_type, title, status, _utc_iso()),
        )
    finally:
        conn.close()


def get_history_event(event_id, user_id):
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM history_events WHERE id = ? AND user_id = ?",
            (event_id, user_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_history_events(user_id, limit=50, offset=0, event_type=None):
    init_db()
    conn = _get_conn()
    try:
        if event_type:
            rows = conn.execute(
                """
                SELECT * FROM history_events
                WHERE user_id = ? AND event_type = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, event_type, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM history_events
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def count_history_events(user_id, event_type=None):
    init_db()
    conn = _get_conn()
    try:
        if event_type:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM history_events WHERE user_id = ? AND event_type = ?",
                (user_id, event_type),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM history_events WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return row["c"] if row else 0
    finally:
        conn.close()


def delete_history_event(event_id, user_id):
    init_db()
    conn = _get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM history_events WHERE id = ? AND user_id = ?",
            (event_id, user_id),
        )
        return getattr(cur, "rowcount", 1) or 0
    finally:
        conn.close()

# ------------------------------------------------------------------ #
# Resume rewrites (WF-02 optimizer, phase 4)
# ------------------------------------------------------------------ #

def save_rewrite(session_id, suggestion_id, issue, candidate_text):
    """Persist an optimizer candidate as pending; applied on user confirm."""
    init_db()
    conn = _get_conn()
    try:
        rewrite_id = _insert_returning_id(
            conn,
            """
            INSERT INTO resume_rewrites (session_id, suggestion_id, issue,
                                         candidate_text, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (session_id, suggestion_id, issue, candidate_text, _utc_iso()),
        )
        row = conn.execute(
            "SELECT * FROM resume_rewrites WHERE id = ?", (rewrite_id,)
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def mark_rewrite_applied(rewrite_id, session_id):
    """Flip a pending rewrite to applied (user confirmed)."""
    init_db()
    conn = _get_conn()
    try:
        conn.execute(
            """
            UPDATE resume_rewrites SET status='applied', applied_at=?
            WHERE id=? AND session_id=? AND status='pending'
            """,
            (_utc_iso(), rewrite_id, session_id),
        )
        row = conn.execute(
            "SELECT * FROM resume_rewrites WHERE id = ? AND session_id = ?",
            (rewrite_id, session_id),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def list_rewrites(session_id, status=None):
    """Return rewrites for a session, optionally filtered by status."""
    init_db()
    conn = _get_conn()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM resume_rewrites WHERE session_id = ? AND status = ? "
                "ORDER BY id DESC",
                (session_id, status),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM resume_rewrites WHERE session_id = ? ORDER BY id DESC",
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_application(session_id, owner_key, company, position, cover_letter, status="applied"):
    """Persist a user-confirmed application record (phase 5 apply loop)."""
    init_db()
    conn = _get_conn()
    try:
        application_id = _insert_returning_id(
            conn,
            """
            INSERT INTO applications (session_id, owner_key, company, position,
                                      cover_letter, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, owner_key, company, position, cover_letter, status, _utc_iso()),
        )
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ?", (application_id,)
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def list_applications(owner_key, limit=50, offset=0):
    """Return application records for an owner (login user or guest)."""
    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM applications WHERE owner_key = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (owner_key, int(limit), int(offset)),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_application(app_id, owner_key):
    """Delete one application record owned by the given key; return the deleted row."""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ? AND owner_key = ?",
            (app_id, owner_key),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "DELETE FROM applications WHERE id = ? AND owner_key = ?",
            (app_id, owner_key),
        )
        return dict(row)
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# F5 unit/job index access (plan section 4.1-4.2, phase 1 foundation)
#
# Reference data only: rows arrive from a licensed provider adapter and are
# never produced by a language model.  The index starts empty and stays empty
# until such a provider is configured.
# ------------------------------------------------------------------ #

ORGANIZATION_VERIFICATION_STATES = ("verified", "user_entered", "stale", "unknown")


def normalize_org_name(value):
    """Normalize an organization name/lookup key for exact matching.

    NFKC folds full-width characters, then only alphanumerics survive so that
    spacing, punctuation and bracket differences collapse onto one key.
    """
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return "".join(ch for ch in text if ch.isalnum())


def upsert_organization(record, aliases=None):
    """Insert or update one organization keyed by (source_provider, source_key).

    Only pass fields the data source is licensed to store and display.
    Returns the stored row as a dict, or None when the row could not be read
    back.
    """
    init_db()
    provider = str(record.get("source_provider") or "").strip()
    source_key = str(record.get("source_key") or "").strip()
    name = str(record.get("canonical_name") or "").strip()
    if not provider or not source_key or not name:
        raise ValueError("source_provider, source_key and canonical_name are required")
    now = _utc_iso()
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO organizations (source_provider, source_key, canonical_name,
                normalized_name, org_type, region, industry, unified_id, status,
                website, source_url, source_updated_at, verified_at,
                created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_provider, source_key) DO UPDATE SET
                canonical_name=excluded.canonical_name,
                normalized_name=excluded.normalized_name,
                org_type=excluded.org_type,
                region=excluded.region,
                industry=excluded.industry,
                unified_id=excluded.unified_id,
                status=excluded.status,
                website=excluded.website,
                source_url=excluded.source_url,
                source_updated_at=excluded.source_updated_at,
                verified_at=excluded.verified_at,
                updated_at=excluded.updated_at
            """,
            (
                provider, source_key, name, normalize_org_name(name),
                str(record.get("org_type") or "unknown"),
                record.get("region"), record.get("industry"), record.get("unified_id"),
                str(record.get("status") or "unknown"), record.get("website"),
                record.get("source_url"), record.get("source_updated_at"),
                record.get("verified_at"), now, now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM organizations WHERE source_provider = ? AND source_key = ?",
            (provider, source_key),
        ).fetchone()
        if row is None:
            return None
        org_id = row["id"]
        if aliases is not None:
            conn.execute(
                "DELETE FROM organization_aliases WHERE organization_id = ?", (org_id,)
            )
            seen = set()
            for alias in aliases:
                if isinstance(alias, dict):
                    alias_text = str(alias.get("alias") or "").strip()
                    alias_type = str(alias.get("alias_type") or "alias")
                else:
                    alias_text = str(alias or "").strip()
                    alias_type = "alias"
                normalized = normalize_org_name(alias_text)
                if not alias_text or not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                conn.execute(
                    """
                    INSERT INTO organization_aliases (organization_id, alias,
                                                      normalized, alias_type, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (org_id, alias_text, normalized, alias_type, now),
                )
        return dict(row)
    finally:
        conn.close()


def get_organization(org_id):
    """Return one organization with its aliases and optional profile."""
    init_db()
    conn = _get_conn()
    try:
        try:
            key = int(org_id)
        except (TypeError, ValueError):
            return None
        row = conn.execute(
            "SELECT * FROM organizations WHERE id = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["aliases"] = [
            dict(r) for r in conn.execute(
                "SELECT alias, normalized, alias_type FROM organization_aliases "
                "WHERE organization_id = ? ORDER BY id",
                (result["id"],),
            ).fetchall()
        ]
        profile = conn.execute(
            "SELECT * FROM organization_profiles WHERE organization_id = ?",
            (result["id"],),
        ).fetchone()
        result["profile"] = dict(profile) if profile is not None else None
        return result
    finally:
        conn.close()


def find_organizations_by_name(query, limit=10):
    """Exact normalized lookup over canonical names and aliases.

    Phase 1 deliberately stops at exact matches.  Fuzzy recall, pinyin and
    subject disambiguation belong to phase 2 and arrive together with a
    licensed data source.  Returns [] while the index is empty.
    """
    normalized = normalize_org_name(query)
    if not normalized:
        return []
    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT o.* FROM organizations o
            LEFT JOIN organization_aliases a ON a.organization_id = o.id
            WHERE o.normalized_name = ? OR a.normalized = ?
            ORDER BY o.canonical_name
            LIMIT ?
            """,
            (normalized, normalized, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


_INDEX_TABLES = (
    "organizations",
    "organization_aliases",
    "organization_profiles",
    "source_snapshots",
    "job_postings",
    "job_posting_versions",
    "job_embeddings",
)


def index_counts():
    """Row counts for the F5 index (provider-health endpoint)."""
    init_db()
    conn = _get_conn()
    try:
        counts = {}
        for table in _INDEX_TABLES:
            row = conn.execute("SELECT COUNT(*) AS n FROM %s" % table).fetchone()
            counts[table] = int(row["n"]) if row is not None else 0
        return counts
    finally:
        conn.close()


def save_source_snapshot(provider, source_url, content_hash,
                         license_scope=None, parser_version=None):
    """Record provenance metadata for one fetched source payload."""
    init_db()
    conn = _get_conn()
    try:
        return _insert_returning_id(
            conn,
            """
            INSERT INTO source_snapshots (source_provider, source_url, license_scope,
                                          content_hash, parser_version, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (provider, source_url, license_scope, content_hash, parser_version,
             _utc_iso()),
        )
    finally:
        conn.close()


def upsert_job_posting(record):
    """Insert or update one job posting keyed by (source_provider, external_job_id).

    A row is appended to ``job_posting_versions`` only when the content hash
    changes, so repeated polls do not bloat the audit trail.
    """
    init_db()
    provider = str(record.get("source_provider") or "").strip()
    external_id = str(record.get("external_job_id") or "").strip()
    title = str(record.get("title") or "").strip()
    if not provider or not external_id or not title:
        raise ValueError("source_provider, external_job_id and title are required")
    now = _utc_iso()
    skill_tags = record.get("skill_tags") or []
    if not isinstance(skill_tags, list):
        skill_tags = [str(skill_tags)]
    skill_tags_json = json.dumps([str(t) for t in skill_tags], ensure_ascii=False)
    snapshot = {
        "title": title,
        "location": record.get("location"),
        "job_type": record.get("job_type"),
        "skill_tags": skill_tags_json,
        "jd_summary": record.get("jd_summary"),
        "status": str(record.get("status") or "unknown"),
        "expires_at": record.get("expires_at"),
    }
    digest = hashlib.sha256(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO job_postings (organization_id, source_provider, external_job_id,
                title, location, job_type, skill_tags, jd_summary, source_url, status,
                published_at, expires_at, last_seen_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_provider, external_job_id) DO UPDATE SET
                organization_id=excluded.organization_id,
                title=excluded.title,
                location=excluded.location,
                job_type=excluded.job_type,
                skill_tags=excluded.skill_tags,
                jd_summary=excluded.jd_summary,
                source_url=excluded.source_url,
                status=excluded.status,
                published_at=excluded.published_at,
                expires_at=excluded.expires_at,
                last_seen_at=excluded.last_seen_at,
                updated_at=excluded.updated_at
            """,
            (
                record.get("organization_id"), provider, external_id, title,
                record.get("location"), record.get("job_type"), skill_tags_json,
                record.get("jd_summary"), record.get("source_url"),
                snapshot["status"], record.get("published_at"),
                record.get("expires_at"), record.get("last_seen_at") or now, now, now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM job_postings WHERE source_provider = ? AND external_job_id = ?",
            (provider, external_id),
        ).fetchone()
        if row is None:
            return None
        latest = conn.execute(
            "SELECT content_hash FROM job_posting_versions WHERE job_posting_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (row["id"],),
        ).fetchone()
        if latest is None or latest["content_hash"] != digest:
            changed = (
                [] if latest is None
                else sorted(k for k, v in snapshot.items() if v is not None)
            )
            conn.execute(
                """
                INSERT INTO job_posting_versions (job_posting_id, content_hash,
                                                  changed_fields, observed_at)
                VALUES (?, ?, ?, ?)
                """,
                (row["id"], digest, json.dumps(changed, ensure_ascii=False), now),
            )
        return dict(row)
    finally:
        conn.close()


def list_job_postings(organization_id, limit=20):
    """Return non-closed job postings for one organization."""
    init_db()
    conn = _get_conn()
    try:
        try:
            key = int(organization_id)
        except (TypeError, ValueError):
            return []
        rows = conn.execute(
            """
            SELECT * FROM job_postings
            WHERE organization_id = ? AND status != 'closed'
            ORDER BY COALESCE(published_at, created_at) DESC
            LIMIT ?
            """,
            (key, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
