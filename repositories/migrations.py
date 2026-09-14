# -*- coding: utf-8 -*-
"""repositories.migrations · 版本化数据迁移

项目的 schema 由 ``tools.database.init_db()`` 以 ``CREATE TABLE IF NOT EXISTS`` 维护，
因此**建表是加法**；但"已有数据要变成新模型"必须显式迁移，否则老库会留下语义不一致的行。
本模块提供最小可用的迁移框架：

* ``schema_migrations`` 表记录已执行的版本，每个版本只跑一次；
* 每个迁移都必须是**幂等**的（重复执行不改变结果），因为 CI 与冷启动都会调用；
* 迁移只做"数据/列的形态转换"，不改变业务口径；口径由 ``domain/`` 定义。

当前版本：

1. ``2026-09-13-phase2-application-status`` —— ``applications`` 增加 ``target_job_id``，
   并把历史 status 规范到 7 态模型（D4：产品负责人已授权迁移生产数据）。
2. ``2026-09-13-phase2-career-profiles`` —— 为历史上出现过的 owner_key 补建 CareerProfile。

**刻意不做的事**：不从既有 `diagnoses` 反向生成证据。诊断的 ``source_spans`` 引文多为
"实习经历"这类小节标题，把它变成"职业事实"会直接污染唯一可信源。证据必须由用户确认后进入，
迁移不代替用户做这件事。
"""
import sys
from datetime import datetime, timezone

from domain.application import LEGACY_FALLBACK_STATUS, LEGACY_STATUS_MAP, ApplicationStatus
from repositories.base import cursor, insert, many, one
from tools import database

VERSION_APPLICATION_STATUS = "2026-09-13-phase2-application-status"
VERSION_CAREER_PROFILES = "2026-09-13-phase2-career-profiles"

VALID_STATUSES = tuple(item.value for item in ApplicationStatus)

#: 每个进程只对每个数据库执行一次（冷启动/多测试库都要便宜）。
_ENSURED = set()
_LAST_REPORT = []


def _utc_iso():
    return datetime.now(timezone.utc).isoformat()


def _ensure_table(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )


def applied_versions():
    with cursor() as conn:
        _ensure_table(conn)
        rows = many("SELECT version FROM schema_migrations ORDER BY version")
    return {row["version"] for row in rows}


def _mark(version):
    """记录版本；已记录时幂等跳过。

    ``apply_all(force=True)`` 会重跑迁移函数，若这里不判重就会撞 ``version`` 主键，
    让整条「人工重跑排障」路径直接失败。
    """
    if version in applied_versions():
        return False
    insert(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (version, _utc_iso()),
        returning=False,
    )
    return True


# ------------------------------------------------------------------ #
# Migrations
# ------------------------------------------------------------------ #

def migrate_application_status():
    """``applications``：补列 + 把历史 status 规范到 7 态。"""
    report = {"version": VERSION_APPLICATION_STATUS, "column_added": False,
              "statuses_normalized": 0, "unknown_values": []}

    with cursor() as conn:
        _ensure_table(conn)
        if not database.has_column(conn, "applications", "target_job_id"):
            conn.execute("ALTER TABLE applications ADD COLUMN target_job_id INTEGER")
            report["column_added"] = True
        rows = conn.execute("SELECT id, status FROM applications").fetchall()

        for row in rows:
            raw = (row["status"] or "").strip()
            if raw in VALID_STATUSES:
                continue
            normalized = LEGACY_STATUS_MAP.get(raw.lower())
            if normalized is None:
                normalized = LEGACY_FALLBACK_STATUS
                if raw not in report["unknown_values"]:
                    report["unknown_values"].append(raw)
            conn.execute("UPDATE applications SET status = ? WHERE id = ?", (normalized, row["id"]))
            report["statuses_normalized"] += 1

    return report


def migrate_career_profiles():
    """为历史上出现过的 owner_key 补建 CareerProfile（不生成任何证据）。"""
    from domain.career_profile import new_profile
    from repositories.base import insert as repo_insert

    report = {"version": VERSION_CAREER_PROFILES, "profiles_created": 0, "evidence_created": 0}

    with cursor() as conn:
        _ensure_table(conn)
        rows = conn.execute(
            "SELECT owner_key FROM session_owners WHERE owner_key IS NOT NULL "
            "UNION SELECT owner_key FROM applications WHERE owner_key IS NOT NULL"
        ).fetchall()

    owner_keys = sorted({(row["owner_key"] or "").strip() for row in rows} - {""})
    for owner_key in owner_keys:
        existing = one("SELECT id FROM career_profiles WHERE owner_key = ?", (owner_key,))
        if existing:
            continue
        record = new_profile(owner_key)
        repo_insert(
            "INSERT INTO career_profiles (owner_key, display_name, headline, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (record["owner_key"], record["display_name"], record["headline"],
             record["created_at"], record["updated_at"]),
            returning=False,
        )
        report["profiles_created"] += 1

    # 明确记录：本迁移不创建任何证据（证据只能由用户确认后进入）。
    report["evidence_created"] = 0
    return report


MIGRATIONS = (
    (VERSION_APPLICATION_STATUS, migrate_application_status),
    (VERSION_CAREER_PROFILES, migrate_career_profiles),
)


def apply_all(force=False):
    """执行所有未应用的迁移；返回本次执行的报告列表。"""
    done = applied_versions()
    reports = []
    for version, func in MIGRATIONS:
        if version in done and not force:
            continue
        report = func()
        _mark(version)
        reports.append(report)
    global _LAST_REPORT
    _LAST_REPORT = reports
    return reports


def last_report():
    return list(_LAST_REPORT)


def ensure_applied():
    """按数据库连接目标缓存一次；冷启动与多测试库都不重复跑。"""
    key = database.db_path() if database.dialect() == "sqlite" else "postgres"
    key = str(key)
    if key in _ENSURED:
        return []
    database.init_db()
    reports = apply_all()
    _ENSURED.add(key)
    return reports


def reset_cache():
    """测试用：清掉"已执行"缓存，强制下次重新检查。"""
    _ENSURED.clear()


if __name__ == "__main__":
    verbose = "-v" in sys.argv
    for item in apply_all():
        print("[migrate] %s %s" % (item["version"], item))
    if not verbose:
        print("[migrate] done")
