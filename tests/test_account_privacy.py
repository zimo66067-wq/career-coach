"""Manual account-erasure safety tests.  All fixtures use an isolated SQLite DB."""

import pytest

from repositories import account_privacy, database


@pytest.fixture
def private_db(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RESUME_DB_PATH", str(tmp_path / "privacy.db"))
    database.reset_init_cache()
    yield
    database.reset_init_cache()


def _seed(user_number):
    user_id = database.create_user(
        "1380000000%d" % user_number,
        "user%d@example.invalid" % user_number,
        "hashed-password",
        "Synthetic user",
    )
    owner = "user:%d" % user_id
    sid = "synthetic-privacy-%d" % user_number
    now = database.utc_iso()
    database.bind_session_owner(sid, owner)
    database.save_resume(sid, "127.0.0.1", "test", "cv.txt", ".txt", 12, "synthetic resume")
    database.save_diagnosis(sid, 70, "rule", "", "", "{}")
    database.save_match(sid, {"score_M": 70}, 70)
    database.save_session(sid, "ASK", {"turns": []})
    database.save_ability(sid, {"baseline": 70})
    database.save_rewrite(sid, "r1", "issue", "synthetic rewrite")
    application_id = database.save_application(sid, owner, "Synthetic Co", "Engineer", "letter")
    conn = database.connection()
    try:
        conn.execute("INSERT INTO application_outcomes (application_id, outcome, recorded_at) VALUES (?, ?, ?)",
                     (application_id["id"], "interview", now))
        conn.execute("INSERT INTO career_profiles (owner_key, created_at, updated_at) VALUES (?, ?, ?)",
                     (owner, now, now))
        evidence_id = conn.execute(
            "INSERT INTO career_evidence (owner_key, evidence_type, claim, source_type, source_quote, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (owner, "project", "synthetic", "resume", "synthetic quote", now, now),
        ).lastrowid
        job_id = conn.execute(
            "INSERT INTO target_jobs (owner_key, session_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (owner, sid, now, now),
        ).lastrowid
        requirement_id = conn.execute(
            "INSERT INTO job_requirements (target_job_id, req_key, req_type, text, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (job_id, "r1", "skill", "synthetic requirement", now),
        ).lastrowid
        conn.execute(
            "INSERT INTO evidence_matches (requirement_id, evidence_id, match_status, created_at) "
            "VALUES (?, ?, ?, ?)", (requirement_id, evidence_id, "weak", now),
        )
        gap_id = conn.execute(
            "INSERT INTO gaps (target_job_id, gap_type, priority, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)", (job_id, "skill", "P1", now, now),
        ).lastrowid
        conn.execute("INSERT INTO actions (owner_key, gap_id, task, created_at, updated_at) "
                     "VALUES (?, ?, ?, ?, ?)", (owner, gap_id, "synthetic action", now, now))
        conn.execute("INSERT INTO target_job_decisions (target_job_id, decision, rationale_json, created_at) "
                     "VALUES (?, ?, ?, ?)", (job_id, "STRETCH", "{}", now))
        conn.execute("INSERT INTO usage_events (owner_key, bucket, created_epoch) VALUES (?, ?, ?)",
                     (owner, "test", 1))
        conn.execute("INSERT INTO history_events (user_id, session_id, event_type, title, status, created_at) "
                     "VALUES (?, ?, ?, ?, ?, ?)",
                     (user_id, sid, "F1", "synthetic history", "done", now))
        conn.execute("INSERT INTO sessions (id, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                     ("token-hash-%d" % user_number, user_id, now, now))
    finally:
        conn.close()
    return user_id, owner, sid


def _user_counts(user_id, owner, sid):
    conn = database.connection()
    try:
        checks = {
            "users": ("id = ?", (user_id,)),
            "sessions": ("user_id = ?", (user_id,)),
            "history_events": ("user_id = ?", (user_id,)),
            "session_owners": ("owner_key = ?", (owner,)),
            "usage_events": ("owner_key = ?", (owner,)),
            "career_profiles": ("owner_key = ?", (owner,)),
            "career_evidence": ("owner_key = ?", (owner,)),
            "target_jobs": ("owner_key = ?", (owner,)),
            "actions": ("owner_key = ?", (owner,)),
            "applications": ("owner_key = ?", (owner,)),
            "resumes": ("session_id = ?", (sid,)),
            "matches": ("session_id = ?", (sid,)),
            "interview_sessions": ("session_id = ?", (sid,)),
            "abilities": ("session_id = ?", (sid,)),
            "resume_rewrites": ("session_id = ?", (sid,)),
        }
        return {
            table: conn.execute("SELECT COUNT(*) AS n FROM %s WHERE %s" % (table, where), params)
            .fetchone()["n"]
            for table, (where, params) in checks.items()
        }
    finally:
        conn.close()


def _dependent_counts():
    conn = database.connection()
    try:
        return {
            table: conn.execute("SELECT COUNT(*) AS n FROM %s" % table).fetchone()["n"]
            for table in ("diagnoses", "application_outcomes", "job_requirements",
                          "evidence_matches", "gaps", "target_job_decisions")
        }
    finally:
        conn.close()


def test_erasure_requires_verified_identity_and_preserves_other_user(private_db):
    victim = _seed(1)
    survivor = _seed(2)
    with pytest.raises(PermissionError):
        account_privacy.erase_verified_user(victim[0])
    assert all(_user_counts(*victim).values())
    assert set(_dependent_counts().values()) == {2}

    result = account_privacy.erase_verified_user(victim[0], identity_verified=True)
    assert result["status"] == "erased"
    assert result["counts"]["users"] == 1
    assert not any(_user_counts(*victim).values())
    assert all(_user_counts(*survivor).values())
    assert set(_dependent_counts().values()) == {1}
    assert account_privacy.erase_verified_user(victim[0], identity_verified=True)["status"] == "not_found"


def test_erasure_rolls_back_if_any_step_fails(private_db, monkeypatch):
    victim = _seed(3)
    original = account_privacy._erase_linked_rows

    def fail_after_delete(conn, user_id, owner_key, counts):
        original(conn, user_id, owner_key, counts)
        raise RuntimeError("simulated transaction failure")

    monkeypatch.setattr(account_privacy, "_erase_linked_rows", fail_after_delete)
    with pytest.raises(RuntimeError, match="simulated transaction failure"):
        account_privacy.erase_verified_user(victim[0], identity_verified=True)
    assert all(_user_counts(*victim).values())
    assert set(_dependent_counts().values()) == {1}


def test_administrative_account_is_not_erased(private_db):
    admin_id = database.create_user("13800000004", "admin@example.invalid", "hash", "Admin", role="admin")
    with pytest.raises(PermissionError, match="Administrative"):
        account_privacy.erase_verified_user(admin_id, identity_verified=True)
    assert database.get_user_by_id(admin_id) is not None
