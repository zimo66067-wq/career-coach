# -*- coding: utf-8 -*-
"""repositories.action · Action 的持久化"""
from repositories.base import insert, many, one, update


def create(record):
    new_id = insert(
        """
        INSERT INTO actions (owner_key, gap_id, task, artifact, outcome, status,
                             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (record["owner_key"], record.get("gap_id"), record["task"], record.get("artifact"),
         record.get("outcome"), record.get("status", "todo"), record["created_at"],
         record["updated_at"]),
    )
    return get_for_owner(new_id, record["owner_key"])


def get_for_owner(action_id, owner_key):
    return one("SELECT * FROM actions WHERE id = ? AND owner_key = ?", (action_id, owner_key))


def list_for_owner(owner_key, status=None, limit=200):
    sql = "SELECT * FROM actions WHERE owner_key = ?"
    params = [owner_key]
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
    params.append(int(limit))
    return many(sql, tuple(params))


def find_open_for_gap(gap_id, owner_key, open_statuses):
    """该缺口是否已有**未关闭**的行动 —— 行动计划幂等的判定依据。

    关闭过的行动不算：用户放弃过一次之后，应当允许重新开单。
    """
    placeholders = ", ".join("?" for _ in open_statuses)
    return one(
        "SELECT * FROM actions WHERE gap_id = ? AND owner_key = ? AND status IN (%s) "
        "ORDER BY id DESC LIMIT 1" % placeholders,
        tuple([gap_id, owner_key] + list(open_statuses)),
    )


def list_with_gap_context(owner_key, status=None, limit=200):
    """行动清单 + 它所属缺口的优先级与岗位。

    用一次 join 取上下文，避免逐条回查（行动数上限 200，但仍没必要 N+1）。
    ``LEFT JOIN``：缺口被删掉时行动仍在，只是没有上下文，不能让整行消失。
    """
    sql = (
        "SELECT a.*, g.priority AS gap_priority, g.gap_type AS gap_type, "
        "       g.target_job_id AS target_job_id, g.status AS gap_status, "
        "       t.position AS target_position, t.company AS target_company "
        "FROM actions a "
        "LEFT JOIN gaps g ON g.id = a.gap_id "
        "LEFT JOIN target_jobs t ON t.id = g.target_job_id "
        "WHERE a.owner_key = ?"
    )
    params = [owner_key]
    if status:
        sql += " AND a.status = ?"
        params.append(status)
    sql += " ORDER BY COALESCE(g.priority, 'P9') ASC, a.updated_at DESC, a.id DESC LIMIT ?"
    params.append(int(limit))
    return many(sql, tuple(params))


def delete_one(action_id, owner_key):
    return update("DELETE FROM actions WHERE id = ? AND owner_key = ?", (action_id, owner_key))


def delete_for_target(target_job_id, owner_key):
    """删除该岗位下由缺口派生的全部行动。

    必须在删除 ``gaps`` **之前**调用。行动的 ``task`` / ``artifact`` 文案来自缺口的
    ``action`` / ``expected_artifact``，本质上是被改写过的 JD 要求；岗位删掉而行动留下，
    就是一条能反推出原要求的孤儿行 —— 这正是 ``delete_target_job`` 契约要禁止的。
    """
    return update(
        "DELETE FROM actions WHERE owner_key = ? AND gap_id IN "
        "(SELECT id FROM gaps WHERE target_job_id = ?)",
        (owner_key, target_job_id),
    )


def save(record):
    return update(
        "UPDATE actions SET task = ?, artifact = ?, outcome = ?, status = ?, updated_at = ? "
        "WHERE id = ? AND owner_key = ?",
        (record["task"], record.get("artifact"), record.get("outcome"), record["status"],
         record["updated_at"], record["id"], record["owner_key"]),
    )


def delete_for_owner(owner_key):
    return update("DELETE FROM actions WHERE owner_key = ?", (owner_key,))
