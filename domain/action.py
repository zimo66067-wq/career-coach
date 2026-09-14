# -*- coding: utf-8 -*-
"""domain.action · 行动闭环：Gap → Action → Artifact → Outcome

    Action
    ├── Gap       要补的缺口
    ├── Task      具体动作（可直接照做的一句）
    ├── Artifact  当天/当次必须产出的**可验证成果物**
    └── Outcome   做完之后发生了什么（并能反向影响证据）

规则：

* 没有 artifact 的动作不算闭环 —— ``open_from_gap()`` 要求缺口里带 expected_artifact。
* 只有 ``done`` 且带 artifact 的动作才允许记录 outcome；否则抛 DomainError。
  （避免"没做任何东西，但记录了一个结果"。）
* Action 的 artifact 是**用户产出物**的说明，不是系统生成的文案，因此不进入证据；
  它带来的新经历要由用户确认后才会成为证据（见 domain.evidence）。
"""
from datetime import datetime, timezone
from enum import Enum

from domain.errors import DomainError


class ActionStatus(str, Enum):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"
    DROPPED = "dropped"


#: 允许的迁移。
#:
#: ``todo → done`` 是允许的：行动闭环的意义就是"今天做掉一件小事"，强制先经过
#: ``doing`` 只是多余的仪式感（``open_from_gap`` 建出来就是 todo，若不允许直连，
#: 用户当天做完也无法标记完成）。``done → doing`` 表示返工；``dropped`` 是终态。
TRANSITIONS = {
    ActionStatus.TODO.value: {ActionStatus.DOING.value, ActionStatus.DONE.value, ActionStatus.DROPPED.value},
    ActionStatus.DOING.value: {ActionStatus.DONE.value, ActionStatus.TODO.value, ActionStatus.DROPPED.value},
    ActionStatus.DONE.value: {ActionStatus.DOING.value},
    ActionStatus.DROPPED.value: set(),
}


def _utc_iso():
    return datetime.now(timezone.utc).isoformat()


def _status(value):
    raw = value.value if isinstance(value, Enum) else str(value or "").strip()
    allowed = {item.value for item in ActionStatus}
    if raw not in allowed:
        raise DomainError(
            "invalid_action_status",
            "动作状态必须是 %s 之一，收到 %r。" % (" / ".join(sorted(allowed)), value),
        )
    return raw


def transition(current, target):
    current = _status(current)
    target = _status(target)
    if current == target:
        return target
    if target not in TRANSITIONS.get(current, set()):
        raise DomainError(
            "invalid_transition",
            "动作状态不允许从 %s 直接变为 %s。" % (current, target),
        )
    return target


def open_from_gap(owner_key, gap, task=None, now=None):
    """由缺口开出一个动作。缺口必须带 ``expected_artifact`` 才算可执行。"""
    owner = str(owner_key or "").strip()
    if not owner:
        raise DomainError("missing_owner_key", "owner_key 不能为空。")
    if not gap:
        raise DomainError("gap_required", "缺少缺口。")
    artifact = str(gap.get("expected_artifact") or "").strip()
    if not artifact:
        raise DomainError(
            "artifact_required",
            "缺口没有 expected_artifact，无法形成可验证的闭环动作。",
        )
    body = str(task or gap.get("action") or "").strip()
    if not body:
        raise DomainError("task_required", "动作缺少内容（task / gap.action 均为空）。")
    stamp = now or _utc_iso()
    return {
        "owner_key": owner,
        "gap_id": gap.get("id"),
        "task": body,
        "artifact": artifact,
        "outcome": None,
        "status": ActionStatus.TODO.value,
        "created_at": stamp,
        "updated_at": stamp,
    }


def record_outcome(action, outcome, now=None):
    """记录动作结果。只有 ``done`` 且带 artifact 的动作可以记录。"""
    if not action:
        raise DomainError("action_required", "缺少动作。")
    if action.get("status") != ActionStatus.DONE.value:
        raise DomainError(
            "action_not_done",
            "只有已完成（done）的动作才能记录结果，当前状态是 %s。" % action.get("status"),
        )
    if not str(action.get("artifact") or "").strip():
        raise DomainError("artifact_required", "动作缺少成果物，不能记录结果。")
    text = str(outcome or "").strip()
    if not text:
        raise DomainError("invalid_outcome", "结果不能为空。")
    updated = dict(action)
    updated["outcome"] = text
    updated["updated_at"] = now or _utc_iso()
    return updated


def complete(action, artifact=None, now=None):
    """把动作标记为完成；可用 ``artifact`` 覆盖成果物描述。"""
    updated = dict(action or {})
    if artifact is not None:
        value = str(artifact).strip()
        if not value:
            raise DomainError("artifact_required", "成果物不能为空。")
        updated["artifact"] = value
    updated["status"] = transition(updated.get("status"), ActionStatus.DONE.value)
    updated["updated_at"] = now or _utc_iso()
    return updated
