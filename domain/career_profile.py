# -*- coding: utf-8 -*-
"""domain.career_profile · CareerProfile：职业证据的长期容器

    CareerProfile
    ├── Evidence      全部证据（唯一可信来源）
    ├── Experience    evidence_type = experience
    ├── Skill         evidence_type = skill
    ├── Achievement   evidence_type = achievement
    ├── Story         evidence_type = story
    └── Preference    evidence_type = preference

后五项不是独立的表，而是**同一批证据按类别分出的视图**（``buckets()``）。这样
"我的经历/技能/成就"永远等于"证据里对应类别的那部分"，不会出现两套互相矛盾的事实。

对外只暴露一个"可用"概念：``usable_evidence()`` 只返回已确认证据。改写、匹配、
面试、求职信都必须走这个入口（Phase 3 接线）。
"""
from datetime import datetime, timezone

from domain.errors import DomainError
from domain.evidence import (
    EvidenceType,
    is_usable,
    new_evidence,
    pending,
    usable,
)

BRANCH_ORDER = (
    EvidenceType.EXPERIENCE.value,
    EvidenceType.SKILL.value,
    EvidenceType.ACHIEVEMENT.value,
    EvidenceType.STORY.value,
    EvidenceType.PREFERENCE.value,
)

BRANCH_LABELS = {
    EvidenceType.EXPERIENCE.value: "经历",
    EvidenceType.SKILL.value: "技能",
    EvidenceType.ACHIEVEMENT.value: "成果",
    EvidenceType.STORY.value: "故事",
    EvidenceType.PREFERENCE.value: "偏好",
}


def new_profile(owner_key, display_name=None, headline=None, now=None):
    owner = str(owner_key or "").strip()
    if not owner:
        raise DomainError("missing_owner_key", "owner_key 不能为空。")
    stamp = now or datetime.now(timezone.utc).isoformat()
    return {
        "owner_key": owner,
        "display_name": (str(display_name).strip() or None) if display_name else None,
        "headline": (str(headline).strip() or None) if headline else None,
        "created_at": stamp,
        "updated_at": stamp,
    }


def buckets(records):
    """把证据按五个分支归类。未确认的证据同样列出（用 status 区分），避免用户看不到待确认项。"""
    grouped = {key: [] for key in BRANCH_ORDER}
    for record in records or []:
        kind = record.get("evidence_type")
        if kind in grouped:
            grouped[kind].append(record)
    return grouped


def usable_evidence(records):
    return usable(records)


def pending_evidence(records):
    return pending(records)


def summary(records):
    """给页面/接口用的结构化概览：每类总数、已确认数、待确认数。"""
    grouped = buckets(records)
    items = []
    for key in BRANCH_ORDER:
        rows = grouped[key]
        confirmed = [row for row in rows if is_usable(row)]
        items.append({
            "type": key,
            "label": BRANCH_LABELS[key],
            "total": len(rows),
            "confirmed": len(confirmed),
            "pending": len([row for row in rows if row.get("status") == "pending"]),
        })
    return {
        "total": sum(item["total"] for item in items),
        "confirmed": sum(item["confirmed"] for item in items),
        "pending": sum(item["pending"] for item in items),
        "branches": items,
    }


def add_evidence(profile, **kwargs):
    """构造一条属于 ``profile`` 的证据。

    ``owner_key`` 强制取自 profile（调用方传了也会被覆盖），杜绝跨账号写入。
    """
    if not profile or not profile.get("owner_key"):
        raise DomainError("profile_required", "缺少职业档案。")
    kwargs.pop("owner_key", None)
    return new_evidence(profile["owner_key"], **kwargs)
