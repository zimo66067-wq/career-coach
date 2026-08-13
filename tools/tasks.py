"""tasks.py · 任务中心服务层（阶段3）

客户端驱动分片推进：任务不在函数内常驻执行。每次 POST /tasks/:id/next
由上层传入 handler(step, payload, result)，处理一个分片并更新进度，
最终状态机：pending -> running -> done / failed。

安全：
  - owner_key 由服务端派生（登录用户 user:<id>，游客 guest:<consent hash>）。
  - 越权访问统一由路由层按 404 处理，不泄露任务存在性。
"""
import json
import uuid
from datetime import datetime, timezone

from tools import database


def _utc_iso():
    return datetime.now(timezone.utc).isoformat()


def _row_to_task(row):
    task = dict(row)
    for key in ("payload", "result_json"):
        raw = task.get(key)
        if isinstance(raw, str) and raw:
            try:
                task[key] = json.loads(raw)
            except (ValueError, TypeError):
                task[key] = {}
        elif not raw:
            task[key] = {}
    return task


def create_task(task_type, owner_key, payload=None, idempotency_key=None, total_steps=1):
    """创建任务；同 owner_key + idempotency_key 返回既有任务（幂等）。"""
    database.init_db()
    conn = database._get_conn()
    try:
        if idempotency_key:
            row = conn.execute(
                "SELECT * FROM tasks WHERE owner_key=? AND idempotency_key=?",
                (owner_key, idempotency_key),
            ).fetchone()
            if row is not None:
                return _row_to_task(row)
        task_id = "task_" + uuid.uuid4().hex[:16]
        now = _utc_iso()
        conn.execute(
            """
            INSERT INTO tasks (id, task_type, idempotency_key, owner_key, state,
                               progress, total_steps, current_step, payload,
                               created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', 0, ?, 0, ?, ?, ?)
            """,
            (
                task_id,
                task_type,
                idempotency_key,
                owner_key,
                max(1, int(total_steps or 1)),
                json.dumps(payload or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        return get_task(task_id)
    finally:
        conn.close()


def get_task(task_id):
    database.init_db()
    conn = database._get_conn()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return _row_to_task(row) if row is not None else None
    finally:
        conn.close()


def advance_task(task_id, owner_key, handler):
    """推进一个分片。

    handler(step, payload, result) 必须返回
    (progress:int, fragment:dict, done:bool, total_steps_override:int|None)。

    返回 (task, status)：status 为 ok / forbidden / not_found / failed / already_done。
    """
    database.init_db()
    conn = database._get_conn()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            return None, "not_found"
        task = _row_to_task(row)
        if task["owner_key"] != owner_key:
            return task, "forbidden"
        if task["state"] == "done":
            return task, "already_done"
        if task["state"] == "failed":
            return task, "failed"
        step = task["current_step"]
        payload = task.get("payload") or {}
        result = task.get("result_json") or {}
        try:
            progress, fragment, done, total_override = handler(step, payload, result)
        except Exception as exc:  # noqa: BLE001
            conn.execute(
                "UPDATE tasks SET state='failed', error_code=?, error_message=?, updated_at=? WHERE id=?",
                ("task_failed", str(exc)[:500], _utc_iso(), task_id),
            )
            return get_task(task_id), "failed"
        merged = dict(result)
        if isinstance(fragment, dict):
            merged.update(fragment)
        new_step = step + 1
        state = "done" if done else "running"
        conn.execute(
            """
            UPDATE tasks SET current_step=?, progress=?, state=?, total_steps=?,
                             result_json=?, updated_at=?
            WHERE id=?
            """,
            (
                new_step,
                max(0, min(100, int(progress or 0))),
                state,
                max(1, int(total_override or task["total_steps"] or 1)),
                json.dumps(merged, ensure_ascii=False),
                _utc_iso(),
                task_id,
            ),
        )
        return get_task(task_id), "ok"
    finally:
        conn.close()
