# -*- coding: utf-8 -*-
"""Phase 2 migration contract.

The schema itself is additive (``CREATE TABLE IF NOT EXISTS``), so creating
tables is not the risky part.  What *is* risky is that an existing production
database already holds rows shaped by the old model, and D4 authorised migrating
them.  These tests therefore build a **genuine legacy database** — the old
``applications`` table without ``target_job_id``, holding status strings the new
7-state model does not accept — and assert that the migration:

* adds the missing column,
* normalises known legacy statuses and records unknown ones instead of guessing,
* is safe to run again (idempotent, and re-runnable with ``force``),
* backfills a CareerProfile per owner but **never invents evidence**,
* reports its state honestly through ``/api/health``.
"""
import sqlite3

import api.index as api_module
import api.startup as api_startup
from domain.application import LEGACY_FALLBACK_STATUS, ApplicationStatus
from repositories import migrations
from repositories import database

# Phase 7c：`_MIGRATION_ERROR` / `migration_status` 从 `api/index.py` 搬到了 `api/startup.py`。
# `api.index` **不再**再导出 `migration_status` —— 7c 的契约判据要求入口的再导出面**双向干净**
# （多留一个没人取的符号就会红），而本文件已经从 `api.startup` 取，于是入口那份没有消费者、
# 属于纯垃圾，被删掉了。所以**打桩必须打在归属地**：重置别处的 `_MIGRATION_ERROR` 不会影响
# `api.startup.migration_status()` 读的那个变量，测试就变成空判。`run_migration_status` 这个
# 别名让下面每一处都看得见打的是谁。
run_migration_status = api_startup.migration_status

VERSION_APPLICATION_STATUS = migrations.VERSION_APPLICATION_STATUS
VERSION_CAREER_PROFILES = migrations.VERSION_CAREER_PROFILES
VERSION_GAP_BLOCKING = migrations.VERSION_GAP_BLOCKING

#: 迁移清单由注册表推导 —— 新增迁移时测试不必跟着改数字。
ALL_VERSIONS = [version for version, _func in migrations.MIGRATIONS]

#: ``applications`` exactly as it looked before Phase 2 (no ``target_job_id``).
LEGACY_APPLICATIONS_DDL = """
CREATE TABLE applications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    owner_key    TEXT NOT NULL,
    company      TEXT NOT NULL,
    position     TEXT NOT NULL,
    cover_letter TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'applied',
    created_at   TEXT NOT NULL
)
"""

LEGACY_ROWS = [
    # (id, session_id, owner_key, company, position, status)
    (1, "sess-a", "owner-1", "示例科技", "后端开发", "submitted"),
    (2, "sess-a", "owner-1", "示例科技", "数据开发", "interviewing"),
    (3, "sess-b", "owner-2", "另一家公司", "前端开发", "saved"),
    (4, "sess-b", "owner-2", "另一家公司", "测试开发", "applied"),      # 已是合法值
    (5, "sess-c", "owner-2", "第三家公司", "运维开发", "weird_value"),   # 未知值
]


def _point_at(path, monkeypatch):
    """按测试给定一个独立数据库，并清掉「已执行」缓存。"""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RESUME_DB_PATH", str(path))
    migrations.reset_cache()
    return path


def _build_legacy_database(path):
    """建一个只含旧结构的库：旧 applications + 旧 session_owners + 一条历史诊断。"""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(LEGACY_APPLICATIONS_DDL)
        conn.execute(
            "CREATE TABLE session_owners (session_id TEXT PRIMARY KEY, owner_key TEXT NOT NULL, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.executemany(
            "INSERT INTO applications (id, session_id, owner_key, company, position, "
            "cover_letter, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, '尊敬的招聘负责人：我希望申请这个岗位。', ?, "
            "'2026-08-01T00:00:00+00:00')",
            LEGACY_ROWS,
        )
        for session_id, owner_key in (("sess-a", "owner-1"), ("sess-b", "owner-2"), ("sess-c", "owner-3")):
            conn.execute(
                "INSERT INTO session_owners (session_id, owner_key, created_at, updated_at) "
                "VALUES (?, ?, '2026-08-01T00:00:00+00:00', '2026-08-01T00:00:00+00:00')",
                (session_id, owner_key),
            )
        conn.commit()
    finally:
        conn.close()


def _applications(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute("SELECT * FROM applications ORDER BY id")]
    finally:
        conn.close()


def _columns(path, table):
    conn = sqlite3.connect(str(path))
    try:
        return [row[1] for row in conn.execute("PRAGMA table_info(%s)" % table)]
    finally:
        conn.close()


def _report(reports, version):
    for item in reports:
        if item.get("version") == version:
            return item
    return None


# ------------------------------------------------------------------ #
# 冷启动与新库
# ------------------------------------------------------------------ #

def test_schema_ddl_is_not_replayed_for_an_initialised_database(tmp_path, monkeypatch):
    """回归：``connection()`` 每次都调 ``init_db()``。

    没有按路径缓存时，每个仓储调用都会重放整套 DDL（29 张表 + 索引，实测冷跑
    75ms），而 ``/api/health`` 会经 ``applied_versions()`` 走一次 —— 读接口因此被拖慢。
    """
    path = _point_at(tmp_path / "initcache.db", monkeypatch)
    database.reset_init_cache()
    database.init_db()
    assert str(path) in database._INITIALIZED

    real = database._get_conn
    touched = {"n": 0}

    def counting():
        touched["n"] += 1
        return real()

    monkeypatch.setattr(database, "_get_conn", counting)

    database.init_db()
    assert touched["n"] == 0, "已初始化的库不应再次执行 DDL"

    # 清缓存后必须真的重跑（否则指向新路径的测试会误跳过建表）
    database.reset_init_cache()
    database.init_db()
    assert touched["n"] == 1


def test_a_fresh_database_applies_every_migration(tmp_path, monkeypatch):
    path = _point_at(tmp_path / "fresh.db", monkeypatch)

    reports = migrations.apply_all()

    assert sorted(item["version"] for item in reports) == sorted(ALL_VERSIONS)
    assert migrations.applied_versions() == set(ALL_VERSIONS)
    assert _columns(path, "applications").count("target_job_id") == 1
    assert _columns(path, "career_evidence")  # 新表由 DDL 建好


def test_migrations_are_idempotent(tmp_path, monkeypatch):
    path = _point_at(tmp_path / "twice.db", monkeypatch)

    migrations.apply_all()
    before = _applications(path)
    second = migrations.apply_all()

    assert second == [], "已应用的迁移不应再次执行"
    assert _applications(path) == before
    assert len(migrations.applied_versions()) == len(ALL_VERSIONS)


def test_ensure_applied_runs_once_per_database(tmp_path, monkeypatch):
    path = _point_at(tmp_path / "cached.db", monkeypatch)

    first = migrations.ensure_applied()
    assert len(first) == len(ALL_VERSIONS), "首个数据库应当执行全部迁移"

    assert migrations.ensure_applied() == [], "同一数据库不应重复执行"

    # 清缓存后会重新「检查」，但版本已记录，因此不会真的再跑
    migrations.reset_cache()
    assert migrations.ensure_applied() == []

    assert migrations.applied_versions() == set(ALL_VERSIONS)
    assert path.exists()


# ------------------------------------------------------------------ #
# 老库：列补齐 + 状态规范化
# ------------------------------------------------------------------ #

def test_legacy_database_gets_the_new_column_and_normalised_statuses(tmp_path, monkeypatch):
    path = _point_at(tmp_path / "legacy.db", monkeypatch)
    _build_legacy_database(path)
    assert "target_job_id" not in _columns(path, "applications")

    reports = migrations.apply_all()

    report = _report(reports, VERSION_APPLICATION_STATUS)
    assert report["column_added"] is True
    # submitted / interviewing / saved / weird_value 四条都需要改写；applied 已是合法值
    assert report["statuses_normalized"] == 4
    assert report["unknown_values"] == ["weird_value"]

    assert "target_job_id" in _columns(path, "applications")

    by_id = {row["id"]: row["status"] for row in _applications(path)}
    assert by_id[1] == ApplicationStatus.APPLIED.value            # submitted
    assert by_id[2] == ApplicationStatus.INTERVIEW.value          # interviewing
    assert by_id[3] == ApplicationStatus.PREPARING.value          # saved
    assert by_id[4] == ApplicationStatus.APPLIED.value            # 原样合法，未被改动
    assert by_id[5] == LEGACY_FALLBACK_STATUS                     # 未知值兜底

    # 迁移后每一行的 status 都在 7 态之内
    valid = {item.value for item in ApplicationStatus}
    assert set(by_id.values()) <= valid


def test_migration_can_be_forced_and_stays_stable(tmp_path, monkeypatch):
    """force=True 用于人工重跑；第二次必须不再改动任何数据，也不重复记版本。"""
    path = _point_at(tmp_path / "force.db", monkeypatch)
    _build_legacy_database(path)

    migrations.apply_all()
    baseline = _applications(path)

    forced = migrations.apply_all(force=True)
    replayed = _report(forced, VERSION_APPLICATION_STATUS)

    assert replayed["statuses_normalized"] == 0, "已经规范化的数据不应再次被改写"
    assert replayed["unknown_values"] == []
    assert _applications(path) == baseline

    # 重跑不得重复插入版本行（否则会撞 schema_migrations 主键）
    conn = sqlite3.connect(str(path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    finally:
        conn.close()
    assert count == len(ALL_VERSIONS)


def test_empty_applications_table_is_handled(tmp_path, monkeypatch):
    path = _point_at(tmp_path / "empty.db", monkeypatch)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(LEGACY_APPLICATIONS_DDL)
        conn.commit()
    finally:
        conn.close()

    report = _report(migrations.apply_all(), VERSION_APPLICATION_STATUS)

    assert report["statuses_normalized"] == 0
    assert report["column_added"] is True


# ------------------------------------------------------------------ #
# 老库：CareerProfile 回填，但绝不生成证据
# ------------------------------------------------------------------ #

def test_profiles_are_backfilled_per_owner_without_inventing_evidence(tmp_path, monkeypatch):
    path = _point_at(tmp_path / "profiles.db", monkeypatch)
    _build_legacy_database(path)

    reports = migrations.apply_all()
    report = _report(reports, VERSION_CAREER_PROFILES)

    # session_owners 给了 owner-1/2/3，applications 给了 owner-1/2 → 去重后 3 个
    assert report["profiles_created"] == 3
    assert report["evidence_created"] == 0

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        owners = {row["owner_key"] for row in conn.execute("SELECT owner_key FROM career_profiles")}
        evidence = conn.execute("SELECT COUNT(*) FROM career_evidence").fetchone()[0]
        profiles = conn.execute("SELECT COUNT(*) FROM career_profiles").fetchone()[0]
    finally:
        conn.close()

    assert owners == {"owner-1", "owner-2", "owner-3"}
    assert profiles == 3
    assert evidence == 0, "迁移不得凭空生成任何证据"


def test_migration_does_not_turn_a_historical_diagnosis_into_evidence(tmp_path, monkeypatch):
    """诊断的 source_spans 常是「实习经历」这类小节标题，变成事实会污染唯一可信源。"""
    path = _point_at(tmp_path / "diagnosis.db", monkeypatch)
    database.init_db()

    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "INSERT INTO resumes (id, session_id, resume_text, created_at, has_diagnosis) "
            "VALUES (1, 'sess-a', '实习经历：负责订单接口开发。', '2026-08-01T00:00:00+00:00', 1)"
        )
        conn.execute(
            "INSERT INTO diagnoses (resume_id, score_r, diagnosis_mode, diagnosis_json, created_at) "
            "VALUES (1, 73.0, 'model', '{\"subscores\": {\"project\": {\"source_spans\": "
            "[{\"text\": \"实习经历\"}]}}}', '2026-08-01T00:00:00+00:00')"
        )
        conn.commit()
    finally:
        conn.close()

    migrations.reset_cache()
    migrations.apply_all()

    conn = sqlite3.connect(str(path))
    try:
        evidence = conn.execute("SELECT COUNT(*) FROM career_evidence").fetchone()[0]
    finally:
        conn.close()

    assert evidence == 0


def test_profile_backfill_is_idempotent(tmp_path, monkeypatch):
    path = _point_at(tmp_path / "profiles2.db", monkeypatch)
    _build_legacy_database(path)

    migrations.apply_all()
    second = _report(migrations.apply_all(force=True), VERSION_CAREER_PROFILES)
    assert second["profiles_created"] == 0, "已有档案的 owner 不应重复建档案"


# ------------------------------------------------------------------ #
# 可观测性：/api/health 如实上报
# ------------------------------------------------------------------ #

def _boom():
    raise RuntimeError("migration exploded")


def test_health_self_heals_a_database_whose_migrations_never_ran(tmp_path, monkeypatch):
    """健康检查必须先补跑未应用的迁移，再上报真实状态。

    否则「换了数据库但启动时已 migrate 过」会让检查继续报 ok —— 那是谎报。
    """
    path = _point_at(tmp_path / "health.db", monkeypatch)
    assert not path.exists(), "测试前提：这是一个全新的数据库"

    state = run_migration_status()

    assert state["ok"] is True
    assert state["error"] is None
    assert sorted(state["applied"]) == sorted(ALL_VERSIONS)
    assert path.exists()
    assert migrations.applied_versions() == set(state["expected"])


def test_health_reports_a_failed_migration_instead_of_pretending_ok(tmp_path, monkeypatch):
    _point_at(tmp_path / "broken.db", monkeypatch)
    monkeypatch.setattr(migrations, "MIGRATIONS", (("2099-01-01-broken", _boom),))
    monkeypatch.setattr(api_startup, "_MIGRATION_ERROR", None)

    state = run_migration_status()

    assert state["ok"] is False
    assert state["expected"] == ["2099-01-01-broken"]
    assert state["applied"] == []
    assert "RuntimeError" in state["error"]
    assert "migration exploded" in state["error"]


def test_health_endpoint_exposes_migration_state(tmp_path, monkeypatch):
    _point_at(tmp_path / "health-api.db", monkeypatch)
    api_module.app.config.update(TESTING=True)
    client = api_module.app.test_client()

    body = client.get("/api/health").json

    assert body["status"] == "ok"
    migrations_state = body["migrations"]
    assert migrations_state["ok"] is True
    assert migrations_state["error"] is None
    assert sorted(migrations_state["applied"]) == sorted(ALL_VERSIONS)


# ------------------------------------------------------------------ #
# Phase 3 · gaps.blocking 补列
# ------------------------------------------------------------------ #

LEGACY_GAPS_DDL = """
CREATE TABLE gaps (
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
)
"""


def test_gap_blocking_is_added_to_a_legacy_gaps_table_without_data_loss(tmp_path, monkeypatch):
    """老库的 gaps 表没有 blocking 列；补列必须成功且不丢行、不误标为阻断。"""
    path = _point_at(tmp_path / "gaps.db", monkeypatch)
    database.init_db()  # 建好其余表
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("DROP TABLE IF EXISTS gaps")
        conn.execute(LEGACY_GAPS_DDL)
        conn.execute(
            "INSERT INTO gaps (target_job_id, gap_type, priority, status, created_at, updated_at) "
            "VALUES (1, 'missing', 'P0', 'open', '2026-09-01T00:00:00+00:00', "
            "'2026-09-01T00:00:00+00:00')"
        )
        conn.commit()
    finally:
        conn.close()
    assert "blocking" not in _columns(path, "gaps")

    migrations.reset_cache()
    report = _report(migrations.apply_all(), VERSION_GAP_BLOCKING)

    assert report["column_added"] is True
    assert "blocking" in _columns(path, "gaps")

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in conn.execute("SELECT * FROM gaps")]
    finally:
        conn.close()

    assert len(rows) == 1, "补列不得丢行"
    # 老行默认 0：无法从旧数据反推当时是否真的不可短期解决，
    # 所以不阻断（重新分析会刷新），而不是猜一个"阻断"
    assert rows[0]["blocking"] == 0
    assert rows[0]["status"] == "open"


def test_gap_blocking_migration_is_idempotent(tmp_path, monkeypatch):
    path = _point_at(tmp_path / "gaps2.db", monkeypatch)
    database.init_db()

    assert _report(migrations.apply_all(), VERSION_GAP_BLOCKING)["column_added"] is False
    forced = _report(migrations.apply_all(force=True), VERSION_GAP_BLOCKING)
    assert forced["column_added"] is False
    assert _columns(path, "gaps").count("blocking") == 1
