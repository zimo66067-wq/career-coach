# -*- coding: utf-8 -*-
"""repositories.career_profile · CareerProfile 的持久化

档案只是"证据的归属容器"，本身不存职业事实；所有事实都在 ``career_evidence``。
"""

from repositories.base import insert, many, one, update

TABLE = "career_profiles"


def create(record):
    new_id = insert(
        "INSERT INTO %s (owner_key, display_name, headline, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)" % TABLE,
        (record["owner_key"], record.get("display_name"), record.get("headline"),
         record["created_at"], record["updated_at"]),
    )
    return get_by_id(new_id)


def get_by_id(profile_id):
    return one("SELECT * FROM %s WHERE id = ?" % TABLE, (profile_id,))


def get_for_owner(owner_key):
    return one("SELECT * FROM %s WHERE owner_key = ?" % TABLE, (owner_key,))


def list_all(limit=500):
    return many("SELECT * FROM %s ORDER BY id LIMIT ?" % TABLE, (int(limit),))


def ensure_for_owner(record):
    """幂等建档案：已存在则原样返回，不覆盖用户填写的 display_name / headline。"""
    existing = get_for_owner(record["owner_key"])
    if existing is not None:
        return existing
    return create(record)


def update_display(owner_key, display_name=None, headline=None, now=None):
    existing = get_for_owner(owner_key)
    if existing is None:
        return None
    return update(
        "UPDATE %s SET display_name = ?, headline = ?, updated_at = ? WHERE owner_key = ?" % TABLE,
        (display_name, headline, now or existing["updated_at"], owner_key),
    )


def delete_for_owner(owner_key):
    return update("DELETE FROM %s WHERE owner_key = ?" % TABLE, (owner_key,))
