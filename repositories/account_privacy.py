"""Account-data inventory and verified manual erasure primitives.

No public endpoint or scheduled job calls these functions.  In particular,
the 12-month inactivity policy must not run until advance notice is deliverable
and the production backup retention period has been verified.
"""

from repositories.database import connection, dialect


def _owned_sessions(conn, user_id, owner_key):
    rows = conn.execute(
        """
        SELECT session_id FROM session_owners WHERE owner_key = ?
        UNION SELECT session_id FROM history_events WHERE user_id = ?
        UNION SELECT session_id FROM applications WHERE owner_key = ?
        UNION SELECT session_id FROM target_jobs
              WHERE owner_key = ? AND session_id IS NOT NULL
        """,
        (owner_key, user_id, owner_key, owner_key),
    ).fetchall()
    return [row["session_id"] for row in rows if row["session_id"]]


def _owned_job_ids(conn, owner_key):
    return [row["id"] for row in conn.execute(
        "SELECT id FROM target_jobs WHERE owner_key = ?", (owner_key,)
    ).fetchall()]


def _delete(conn, table, where, params, counts):
    cursor = conn.execute("DELETE FROM %s WHERE %s" % (table, where), params)
    counts[table] = counts.get(table, 0) + max(cursor.rowcount, 0)


def _erase_linked_rows(conn, user_id, owner_key, counts):
    session_ids = _owned_sessions(conn, user_id, owner_key)
    job_ids = _owned_job_ids(conn, owner_key)

    # Delete children first.  Several relationships predate FK constraints,
    # so ON DELETE CASCADE alone cannot establish complete account erasure.
    for job_id in job_ids:
        _delete(conn, "actions", "gap_id IN (SELECT id FROM gaps WHERE target_job_id = ?)",
                (job_id,), counts)
        _delete(conn, "evidence_matches",
                "requirement_id IN (SELECT id FROM job_requirements WHERE target_job_id = ?)",
                (job_id,), counts)
        for table in ("gaps", "target_job_decisions", "job_requirements"):
            _delete(conn, table, "target_job_id = ?", (job_id,), counts)
        _delete(conn, "target_jobs", "id = ?", (job_id,), counts)

    _delete(conn, "evidence_matches",
            "evidence_id IN (SELECT id FROM career_evidence WHERE owner_key = ?)",
            (owner_key,), counts)
    _delete(conn, "career_evidence", "owner_key = ?", (owner_key,), counts)
    _delete(conn, "career_profiles", "owner_key = ?", (owner_key,), counts)
    _delete(conn, "actions", "owner_key = ?", (owner_key,), counts)

    _delete(conn, "application_outcomes",
            "application_id IN (SELECT id FROM applications WHERE owner_key = ?)",
            (owner_key,), counts)
    _delete(conn, "applications", "owner_key = ?", (owner_key,), counts)

    for session_id in session_ids:
        _delete(conn, "diagnoses",
                "resume_id IN (SELECT id FROM resumes WHERE session_id = ?)",
                (session_id,), counts)
        for table in ("resumes", "matches", "interview_sessions", "abilities",
                      "resume_rewrites"):
            _delete(conn, table, "session_id = ?", (session_id,), counts)
        _delete(conn, "history_events", "session_id = ? AND user_id = ?",
                (session_id, user_id), counts)
        _delete(conn, "session_owners", "session_id = ? AND owner_key = ?",
                (session_id, owner_key), counts)

    _delete(conn, "history_events", "user_id = ?", (user_id,), counts)
    _delete(conn, "session_owners", "owner_key = ?", (owner_key,), counts)
    _delete(conn, "usage_events", "owner_key = ?", (owner_key,), counts)
    _delete(conn, "sessions", "user_id = ?", (user_id,), counts)
    _delete(conn, "users", "id = ?", (user_id,), counts)


def erase_verified_user(user_id, *, identity_verified=False):
    """Erase a manually verified *ordinary* account in one DB transaction.

    This is deliberately not reachable from HTTP.  The caller must perform and
    document identity verification independently; a request email alone is not
    proof of ownership because registration email addresses are unverified.
    """
    if not identity_verified:
        raise PermissionError("Identity verification is required before erasure")
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("A positive numeric user ID is required")

    conn = connection()
    try:
        conn.execute("BEGIN")
        lock = " FOR UPDATE" if dialect() == "postgres" else ""
        user = conn.execute(
            "SELECT id, role FROM users WHERE id = ?" + lock, (user_id,)
        ).fetchone()
        if not user:
            conn.rollback()
            return {"status": "not_found", "counts": {}}
        if user["role"] != "user":
            raise PermissionError("Administrative accounts require separate review")

        counts = {}
        _erase_linked_rows(conn, user_id, "user:%d" % user_id, counts)
        conn.commit()
        return {"status": "erased", "counts": counts}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
