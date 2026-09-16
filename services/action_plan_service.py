# -*- coding: utf-8 -*-
"""action_plan_service · 缺口 → 可执行行动（Gap Action Plan）

缺口是"差什么"，行动是"做什么"。本模块把前者翻译成后者，并让行动的进展留在缺口上，
使"我做过什么"和"我还差什么"始终对得上。

四条设计约束：

1. **开单需要可验证的成果物** —— ``domain.action.open_from_gap`` 要求缺口带
   ``expected_artifact``，否则拒绝。所以"无法验证的待办"进不了清单，这里不绕过它。
2. **幂等**：同一缺口只要还有未关闭的行动（``todo`` / ``doing``）就不重复开单。
   反复运行分析不会让行动清单膨胀。
3. **开单即让缺口进入 ``doing``**：``doing`` 仍属"未解决"（见
   ``domain.target_job.OPEN_GAP_STATUSES``），所以开单**不会**让 Decision 变乐观 ——
   缺口只有在**重新分析**中被覆盖才会变成 ``cleared``。
4. **完成不等于缺口解决**：行动 ``done`` 记的是"我做了这件事"，缺口是否被覆盖要重新
   分析才知道。这个区分是刻意的 —— 否则"打了个勾"就等于"能力补齐了"，那是假的。

行动的 ``artifact`` 是**用户产出物**的说明（例如"一页含 3 个量化数字的项目说明"），
不是系统生成的文案，因此不进入证据库；它带来的新经历要由用户确认后才成证据。
"""
import logging

from domain.action import ActionStatus
from domain.action import complete as domain_complete
from domain.action import open_from_gap
from domain.action import record_outcome as domain_record_outcome
from domain.action import transition as domain_transition
from domain.errors import DomainError
from domain.target_job import OPEN_GAP_STATUSES
from repositories import action as action_repo
from repositories import target_job as target_job_repo
from services import target_job_service
from tools import database
from tools.api_errors import ApiError

logger = logging.getLogger(__name__)

#: 未关闭的行动状态 —— 幂等判定的依据。
OPEN_ACTION_STATUSES = (ActionStatus.TODO.value, ActionStatus.DOING.value)

#: 缺 ``expected_artifact`` 的缺口不开单。如实报出被跳过的条数与原因，
#: 而不是静默丢弃（否则用户会以为"我的缺口都开好单了"）。
NO_ARTIFACT_REASON = "该缺口没有可验证的成果物说明，无法形成闭环行动。"


def _owned_action(action_id, owner_key):
    record = action_repo.get_for_owner(action_id, owner_key)
    if record is None:
        # 归属隔离：不是自己的行动一律按"不存在"处理，不泄漏它是否存在
        raise ApiError("action_not_found", "行动不存在或不属于当前用户。", 404)
    return record


def _owned_gap(gap_id, owner_key):
    gap = target_job_repo.get_gap(gap_id)
    if gap is None:
        raise ApiError("gap_not_found", "缺口不存在。", 404)
    # 缺口挂在目标岗位上，岗位挂在 owner 上 —— 沿这条路做归属校验
    target_job_service.get_target_job(gap["target_job_id"], owner_key)
    return gap


def _mark_gap_doing(gap):
    """开单即让缺口进入 ``doing``。仍在"未解决"集合内，不改变 Decision。

    注意这里是**缺口**的状态，与行动自身的 ``doing`` 同名不同物（缺口的状态集合是
    ``open / doing / done / dropped / cleared``），所以不借用 ``ActionStatus``。
    """
    if gap.get("status") != "open":
        return
    target_job_repo.set_gap_status(gap["id"], "doing", database.utc_iso())


def _create_from_gap(gap, owner_key):
    try:
        draft = open_from_gap(owner_key, gap)
    except DomainError as error:
        # 缺 expected_artifact / task 时域层拒绝 —— 原样翻译成 422，不吞掉
        raise ApiError(error.code, error.message, 422)
    record = action_repo.create(draft)
    _mark_gap_doing(gap)
    return record


def open_action(gap_id, owner_key):
    """由一条缺口开出一个行动。已有未关闭行动时返回既有的那条（``opened=False``）。"""
    gap = _owned_gap(gap_id, owner_key)
    existing = action_repo.find_open_for_gap(gap_id, owner_key, OPEN_ACTION_STATUSES)
    if existing:
        return existing, False
    return _create_from_gap(gap, owner_key), True


def plan_for_target(target_job_id, owner_key):
    """把该岗位**未解决**的缺口整体转成行动清单（幂等）。

    已解决（``done`` / ``dropped`` / ``cleared``）的缺口不再开单 —— 行动清单是
    "接下来做什么"，不是历史账本。
    """
    target_job_service.get_target_job(target_job_id, owner_key)

    created, existing, skipped = [], [], []
    for gap in target_job_repo.list_gaps(target_job_id):
        if gap.get("status") not in OPEN_GAP_STATUSES:
            continue
        if not str(gap.get("expected_artifact") or "").strip():
            skipped.append({
                "gap_id": gap["id"],
                "priority": gap.get("priority"),
                "reason": NO_ARTIFACT_REASON,
            })
            continue
        current = action_repo.find_open_for_gap(gap["id"], owner_key, OPEN_ACTION_STATUSES)
        if current:
            existing.append(current)
            continue
        created.append(_create_from_gap(gap, owner_key))

    return {
        "target_job_id": target_job_id,
        "created": created,
        "existing": existing,
        "skipped": skipped,
    }


def list_actions(owner_key, status=None):
    """行动清单（含所属缺口的优先级与岗位），P0 优先排序。"""
    return action_repo.list_with_gap_context(owner_key, status=status)


def get_action(action_id, owner_key):
    """单条行动（含缺口上下文）。"""
    record = dict(_owned_action(action_id, owner_key))
    gap = target_job_repo.get_gap(record["gap_id"]) if record.get("gap_id") else None
    if gap:
        record["gap_priority"] = gap.get("priority")
        record["gap_type"] = gap.get("gap_type")
        record["gap_status"] = gap.get("status")
        record["target_job_id"] = gap.get("target_job_id")
    return record


def _advance(action_id, owner_key, mutate):
    record = _owned_action(action_id, owner_key)
    try:
        updated = mutate(record)
    except DomainError as error:
        raise ApiError(error.code, error.message, 422)
    action_repo.save(updated)
    return _owned_action(action_id, owner_key)


def start_action(action_id, owner_key):
    """标记为处理中（``todo`` → ``doing``）。"""

    def mutate(record):
        updated = dict(record)
        updated["status"] = domain_transition(record["status"], ActionStatus.DOING.value)
        updated["updated_at"] = database.utc_iso()
        return updated

    return _advance(action_id, owner_key, mutate)


def complete_action(action_id, owner_key, artifact=None):
    """标记完成。可同时用 ``artifact`` 覆盖成果物描述。"""

    def mutate(record):
        return domain_complete(record, artifact=artifact, now=database.utc_iso())

    return _advance(action_id, owner_key, mutate)


def record_action_outcome(action_id, owner_key, outcome):
    """记录做完之后发生了什么。域层要求动作已 ``done`` 且带 artifact。"""

    def mutate(record):
        return domain_record_outcome(record, outcome, now=database.utc_iso())

    return _advance(action_id, owner_key, mutate)


def drop_action(action_id, owner_key):
    """放弃该行动（终态）。缺口不会因此被关闭 —— 它仍然没被解决。"""

    def mutate(record):
        updated = dict(record)
        updated["status"] = domain_transition(record["status"], ActionStatus.DROPPED.value)
        updated["updated_at"] = database.utc_iso()
        return updated

    return _advance(action_id, owner_key, mutate)


def delete_action(action_id, owner_key):
    _owned_action(action_id, owner_key)
    return action_repo.delete_one(action_id, owner_key)
