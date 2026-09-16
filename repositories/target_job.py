# -*- coding: utf-8 -*-
"""repositories.target_job · TargetJob 及其子实体（要求 / 匹配 / 缺口 / 决策）的持久化"""
import json

from repositories.base import insert, many, one, update


def create_target_job(record):
    new_id = insert(
        """
        INSERT INTO target_jobs (owner_key, session_id, company, position, jd_text,
                                 job_profile_json, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["owner_key"], record.get("session_id"), record.get("company"),
            record.get("position"), record.get("jd_text"), record.get("job_profile_json"),
            record.get("status", "open"), record["created_at"], record["updated_at"],
        ),
    )
    return get_target_job(new_id)


def get_target_job(target_job_id):
    return one("SELECT * FROM target_jobs WHERE id = ?", (target_job_id,))


def get_target_job_for_owner(target_job_id, owner_key):
    return one(
        "SELECT * FROM target_jobs WHERE id = ? AND owner_key = ?", (target_job_id, owner_key)
    )


def list_target_jobs(owner_key, limit=50):
    return many(
        "SELECT * FROM target_jobs WHERE owner_key = ? ORDER BY id DESC LIMIT ?",
        (owner_key, int(limit)),
    )


def delete_target_job(target_job_id, owner_key):
    """删除岗位本身；调用方负责先清掉其子记录（要求 / 匹配 / 缺口 / 决策）。"""
    return update("DELETE FROM target_jobs WHERE id = ? AND owner_key = ?", (target_job_id, owner_key))


def set_job_profile(target_job_id, owner_key, job_profile, now):
    return update(
        "UPDATE target_jobs SET job_profile_json = ?, updated_at = ? WHERE id = ? AND owner_key = ?",
        (json.dumps(job_profile, ensure_ascii=False), now, target_job_id, owner_key),
    )


def set_position(target_job_id, owner_key, position, now):
    return update(
        "UPDATE target_jobs SET position = ?, updated_at = ? WHERE id = ? AND owner_key = ?",
        (position, now, target_job_id, owner_key),
    )


# ------------------------------------------------------------------ #
# JobRequirement
# ------------------------------------------------------------------ #

def replace_requirements(target_job_id, requirements):
    """按 ``(target_job_id, req_key)`` 幂等写入要求；返回写入条数。

    重复解析同一份 JD 不会产生重复要求，只会刷新内容。
    """
    written = 0
    for record in requirements:
        existing = one(
            "SELECT id FROM job_requirements WHERE target_job_id = ? AND req_key = ?",
            (target_job_id, record["req_key"]),
        )
        if existing:
            update(
                "UPDATE job_requirements SET req_type = ?, text = ?, ordinal = ?, "
                "source_span_json = ? WHERE id = ?",
                (record["req_type"], record["text"], record["ordinal"],
                 record.get("source_span_json"), existing["id"]),
            )
        else:
            insert(
                """
                INSERT INTO job_requirements (target_job_id, req_key, req_type, text,
                                              ordinal, source_span_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (target_job_id, record["req_key"], record["req_type"], record["text"],
                 record["ordinal"], record.get("source_span_json"), record["created_at"]),
            )
        written += 1
    return written


def list_requirements(target_job_id):
    return many(
        "SELECT * FROM job_requirements WHERE target_job_id = ? ORDER BY ordinal, id",
        (target_job_id,),
    )


def delete_requirements_for_target(target_job_id):
    return update("DELETE FROM job_requirements WHERE target_job_id = ?", (target_job_id,))


# ------------------------------------------------------------------ #
# EvidenceMatch
# ------------------------------------------------------------------ #

def add_evidence_match(record):
    new_id = insert(
        """
        INSERT INTO evidence_matches (requirement_id, evidence_id, match_status, rationale, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (record["requirement_id"], record.get("evidence_id"), record["match_status"],
         record.get("rationale"), record["created_at"]),
    )
    return one("SELECT * FROM evidence_matches WHERE id = ?", (new_id,))


def list_matches_for_target(target_job_id):
    return many(
        "SELECT m.* FROM evidence_matches m "
        "JOIN job_requirements r ON r.id = m.requirement_id "
        "WHERE r.target_job_id = ? ORDER BY r.ordinal, m.id",
        (target_job_id,),
    )


def delete_matches_for_target(target_job_id):
    """删除该岗位下的全部匹配行。

    匹配是**派生数据**（由当前简历 + 要求重算得出），不含用户状态，因此重新分析时
    整体替换是安全的；缺口则不同（见 ``find_gap`` 的说明）。
    """
    return update(
        "DELETE FROM evidence_matches WHERE requirement_id IN "
        "(SELECT id FROM job_requirements WHERE target_job_id = ?)",
        (target_job_id,),
    )


# ------------------------------------------------------------------ #
# Gap
# ------------------------------------------------------------------ #

def create_gap(record):
    new_id = insert(
        """
        INSERT INTO gaps (target_job_id, requirement_id, gap_type, priority, reason,
                          current_evidence, missing_evidence, action, expected_artifact,
                          retest, status, blocking, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (record["target_job_id"], record.get("requirement_id"), record["gap_type"],
         record["priority"], record.get("reason"), record.get("current_evidence"),
         record.get("missing_evidence"), record.get("action"), record.get("expected_artifact"),
         record.get("retest"), record.get("status", "open"), int(record.get("blocking") or 0),
         record["created_at"], record["updated_at"]),
    )
    return one("SELECT * FROM gaps WHERE id = ?", (new_id,))


def list_gaps(target_job_id, status=None):
    sql = "SELECT * FROM gaps WHERE target_job_id = ?"
    params = [target_job_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY priority, id"
    return many(sql, tuple(params))


def find_gap(target_job_id, requirement_id, gap_type):
    return one(
        "SELECT * FROM gaps WHERE target_job_id = ? AND requirement_id = ? AND gap_type = ? "
        "ORDER BY id DESC LIMIT 1",
        (target_job_id, requirement_id, gap_type),
    )


def get_gap(gap_id):
    """按主键取单条缺口 —— 行动计划需要它的 ``expected_artifact`` 才能开单。"""
    return one("SELECT * FROM gaps WHERE id = ?", (gap_id,))


def update_gap_content(gap_id, record):
    """刷新缺口的说明字段，但**不动 status**。

    缺口带着用户进度（``doing`` / ``done`` / 用户已产出的 artifact），重新分析时
    覆盖状态等于把用户做过的事抹掉，所以这里只更新推导出来的文案。
    """
    return update(
        "UPDATE gaps SET priority = ?, reason = ?, current_evidence = ?, missing_evidence = ?, "
        "action = ?, expected_artifact = ?, retest = ?, blocking = ?, updated_at = ? WHERE id = ?",
        (record["priority"], record.get("reason"), record.get("current_evidence"),
         record.get("missing_evidence"), record.get("action"), record.get("expected_artifact"),
         record.get("retest"), int(record.get("blocking") or 0), record["updated_at"], gap_id),
    )


def set_gap_status(gap_id, status, now):
    return update("UPDATE gaps SET status = ?, updated_at = ? WHERE id = ?", (status, now, gap_id))


def delete_gaps_for_target(target_job_id):
    return update("DELETE FROM gaps WHERE target_job_id = ?", (target_job_id,))


# ------------------------------------------------------------------ #
# Decision
# ------------------------------------------------------------------ #

def create_decision(record):
    new_id = insert(
        "INSERT INTO target_job_decisions (target_job_id, decision, rationale_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        (record["target_job_id"], record["decision"], record["rationale_json"], record["created_at"]),
    )
    return one("SELECT * FROM target_job_decisions WHERE id = ?", (new_id,))


def latest_decision(target_job_id):
    return one(
        "SELECT * FROM target_job_decisions WHERE target_job_id = ? ORDER BY id DESC LIMIT 1",
        (target_job_id,),
    )


def delete_decisions_for_target(target_job_id):
    return update("DELETE FROM target_job_decisions WHERE target_job_id = ?", (target_job_id,))
