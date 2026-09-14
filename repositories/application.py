# -*- coding: utf-8 -*-
"""repositories.application · 投递记录（7 态）+ 结果

与既有 ``tools/database.save_application`` 并存：本模块是 Phase 2 之后的正式入口
（带状态机校验与 ``target_job_id``），旧函数保留给尚未迁移的 F5 接口，Phase 3 收敛。
"""
from repositories.base import insert, many, one, update


def create(record):
    new_id = insert(
        """
        INSERT INTO applications (session_id, owner_key, company, position, cover_letter,
                                  status, target_job_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (record["session_id"], record["owner_key"], record["company"], record["position"],
         record["cover_letter"], record["status"], record.get("target_job_id"),
         record["created_at"]),
    )
    return one("SELECT * FROM applications WHERE id = ?", (new_id,))


def get_for_owner(application_id, owner_key):
    return one(
        "SELECT * FROM applications WHERE id = ? AND owner_key = ?",
        (application_id, owner_key),
    )


def list_for_owner(owner_key, limit=50, offset=0):
    return many(
        "SELECT * FROM applications WHERE owner_key = ? ORDER BY id DESC LIMIT ? OFFSET ?",
        (owner_key, int(limit), int(offset)),
    )


def set_status(application_id, owner_key, status):
    return update(
        "UPDATE applications SET status = ? WHERE id = ? AND owner_key = ?",
        (status, application_id, owner_key),
    )


def link_target_job(application_id, owner_key, target_job_id):
    return update(
        "UPDATE applications SET target_job_id = ? WHERE id = ? AND owner_key = ?",
        (target_job_id, application_id, owner_key),
    )


def distinct_owner_keys():
    """迁移用：历史上出现过的全部 owner_key（游客 token 与登录账号）。"""
    rows = many("SELECT DISTINCT owner_key FROM applications WHERE owner_key IS NOT NULL")
    return sorted(row["owner_key"] for row in rows)


def add_outcome(record):
    new_id = insert(
        """
        INSERT INTO application_outcomes (application_id, outcome, note, recorded_at)
        VALUES (?, ?, ?, ?)
        """,
        (record["application_id"], record["outcome"], record.get("note"), record["recorded_at"]),
    )
    return one("SELECT * FROM application_outcomes WHERE id = ?", (new_id,))


def list_outcomes(application_id):
    return many(
        "SELECT * FROM application_outcomes WHERE application_id = ? ORDER BY id DESC",
        (application_id,),
    )


def delete_for_owner(owner_key):
    """删除归属者名下的申请及其结果（DoD #22：删除链路必须可验证）。"""
    with_rows = many(
        "SELECT id FROM applications WHERE owner_key = ?", (owner_key,)
    )
    removed = 0
    for row in with_rows:
        removed += update("DELETE FROM application_outcomes WHERE application_id = ?", (row["id"],))
    removed += update("DELETE FROM applications WHERE owner_key = ?", (owner_key,))
    return removed
