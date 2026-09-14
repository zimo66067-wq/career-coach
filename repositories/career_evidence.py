# -*- coding: utf-8 -*-
"""repositories.career_evidence · CareerEvidence 的持久化"""
from repositories.base import insert, many, one, update

TABLE = "career_evidence"

UPDATE_FIELDS = ("claim", "source_quote", "confidence", "status", "user_confirmed", "confirmed_at")


def create(record):
    """插入一条证据记录（record 由 ``domain.evidence.new_evidence`` 产出）。"""
    new_id = insert(
        """
        INSERT INTO career_evidence (owner_key, evidence_type, claim, source_type, source_id,
                                     source_quote, confidence, status, user_confirmed,
                                     created_at, updated_at, confirmed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["owner_key"], record["evidence_type"], record["claim"], record["source_type"],
            record.get("source_id"), record["source_quote"], record["confidence"],
            record["status"], int(record.get("user_confirmed") or 0),
            record["created_at"], record["updated_at"], record.get("confirmed_at"),
        ),
    )
    return get(new_id)


def get(evidence_id):
    return one("SELECT * FROM %s WHERE id = ?" % TABLE, (evidence_id,))


def get_for_owner(evidence_id, owner_key):
    return one(
        "SELECT * FROM %s WHERE id = ? AND owner_key = ?" % TABLE, (evidence_id, owner_key)
    )


def list_for_owner(owner_key, status=None, evidence_type=None, limit=200):
    sql = "SELECT * FROM %s WHERE owner_key = ?" % TABLE
    params = [owner_key]
    if status:
        sql += " AND status = ?"
        params.append(status)
    if evidence_type:
        sql += " AND evidence_type = ?"
        params.append(evidence_type)
    sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
    params.append(int(limit))
    return many(sql, tuple(params))


def save(record):
    """UPDATE 一条已存在的记录；只写 domain 允许变更的字段。"""
    assignments = ", ".join("%s = ?" % field for field in UPDATE_FIELDS)
    params = [record.get(field) for field in UPDATE_FIELDS]
    params.append(record["updated_at"])
    params.extend([record["id"], record["owner_key"]])
    return update(
        "UPDATE %s SET %s, updated_at = ? WHERE id = ? AND owner_key = ?" % (TABLE, assignments),
        tuple(params),
    )


def delete(evidence_id, owner_key):
    return update(
        "DELETE FROM %s WHERE id = ? AND owner_key = ?" % TABLE, (evidence_id, owner_key)
    )


def delete_for_owner(owner_key):
    return update("DELETE FROM %s WHERE owner_key = ?" % TABLE, (owner_key,))


def counts(owner_key):
    rows = many(
        "SELECT status, COUNT(*) AS n FROM %s WHERE owner_key = ? GROUP BY status" % TABLE,
        (owner_key,),
    )
    result = {"total": 0, "pending": 0, "confirmed": 0, "rejected": 0}
    for row in rows:
        result[row["status"]] = int(row["n"])
        result["total"] += int(row["n"])
    return result


def exists_for_source(owner_key, source_type, source_id, source_quote):
    """幂等检查：同一来源 + 同一引文是否已有证据（迁移与重复抽取都要用）。"""
    row = one(
        "SELECT id FROM %s WHERE owner_key = ? AND source_type = ? AND source_id = ? "
        "AND source_quote = ? LIMIT 1" % TABLE,
        (owner_key, source_type, source_id, source_quote),
    )
    return row is not None
