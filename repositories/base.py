# -*- coding: utf-8 -*-
"""repositories · 数据访问层（Routes → Services → Domain → **Repositories**）

本层是唯一直接拼 SQL 的地方。约定：

* 只依赖 ``repositories.database`` 的公共门面（``connection`` / ``render`` / ``insert_id`` /
  ``utc_iso`` / ``has_column`` / ``table_names``），不 import 私有 helper。
* 每条语句都走 ``database.render()``，因此 SQLite 的 ``?`` 在 PostgreSQL 下自动变成 ``%s``。
  **SQL 里不要出现字面量 ``%``**（psycopg 会把它当占位符）。
* 所有查询都必须带 ``owner_key`` 条件（除按主键取单行且调用方已校验归属的情况），
  归属隔离在数据层兜底，不依赖调用方自觉。
* 返回值统一是普通 dict，与 domain 层的记录形状一致。
"""
from contextlib import contextmanager

from repositories import database


@contextmanager
def cursor():
    conn = database.connection()
    try:
        yield conn
    finally:
        conn.close()


def one(sql, params=()):
    with cursor() as conn:
        row = conn.execute(database.render(sql), params).fetchone()
        return dict(row) if row is not None else None


def many(sql, params=()):
    with cursor() as conn:
        return [dict(row) for row in conn.execute(database.render(sql), params).fetchall()]


def scalar(sql, params=()):
    with cursor() as conn:
        row = conn.execute(database.render(sql), params).fetchone()
        return None if row is None else row[0]


def insert(statement, params, returning=True):
    """Insert one row; return the new id (or rowcount when ``returning`` is False)."""
    with cursor() as conn:
        if returning:
            return database.insert_id(conn, database.render(statement), params)
        cur = conn.execute(database.render(statement), params)
        return getattr(cur, "rowcount", None)


def update(statement, params):
    with cursor() as conn:
        cur = conn.execute(database.render(statement), params)
        return getattr(cur, "rowcount", 0)


def run(statements):
    """Execute a list of raw statements (migrations only). Each runs once, in order."""
    executed = 0
    with cursor() as conn:
        for statement in statements:
            if statement and statement.strip():
                conn.execute(statement)
                executed += 1
    return executed
