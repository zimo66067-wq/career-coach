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


def save(record):
    return update(
        "UPDATE actions SET task = ?, artifact = ?, outcome = ?, status = ?, updated_at = ? "
        "WHERE id = ? AND owner_key = ?",
        (record["task"], record.get("artifact"), record.get("outcome"), record["status"],
         record["updated_at"], record["id"], record["owner_key"]),
    )


def delete_for_owner(owner_key):
    return update("DELETE FROM actions WHERE owner_key = ?", (owner_key,))
