# -*- coding: utf-8 -*-
"""organization.py · 单位/职位数据源 provider 抽象（F5 阶段 1）

F5 的单位与职位检索必须建立在**已获得终端展示与必要缓存授权**的数据源之上
（规划 `docs/f5-organization-job-search-plan-2026-09-11.md` 第 3 节）。

本模块只定义契约与默认的「未配置」实现，**不包含任何真实数据源**：

- 默认 `UnconfiguredOrganizationProvider` 不返回任何单位，也绝不生成单位事实；
- 每个结果都必须带来源与核验元数据（`RESULT_REQUIRED_FIELDS`），
  否则 `eligible_results()` 会把它剔除——没有可追溯来源的结果比没有结果更糟，
  因为它会被求职者当成已核验事实；
- 通过 `ORG_DATA_PROVIDER` 环境变量选择已注册的 provider，未设置即为未配置。
"""
import os

# 每条单位/职位结果必须携带的来源与核验字段（规划第 7 节）
RESULT_REQUIRED_FIELDS = (
    "source_provider",
    "source_url",
    "source_updated_at",
    "verified_at",
    "verification_state",
)

VERIFICATION_STATES = ("verified", "user_entered", "stale", "unknown")


class BaseOrganizationProvider:
    """单位/职位数据源接口契约。"""

    name = "base"

    def is_configured(self):
        """仅当凭据与展示授权都齐备时返回 True。"""
        return False

    def license_notice(self):
        """描述本数据源授权范围的说明文案。"""
        return ""

    def search_organizations(self, query, limit=10):
        """按名称检索单位。

        Returns:
            list[dict]: 每项需带 `RESULT_REQUIRED_FIELDS`，以及
            `source_key`、`canonical_name`、`org_type`。
        """
        raise NotImplementedError

    def search_jobs(self, organization_source_key, limit=20):
        """检索某单位当前有效的职位。"""
        raise NotImplementedError


class UnconfiguredOrganizationProvider(BaseOrganizationProvider):
    """默认 provider：尚未接入任何获得授权的数据源。

    它返回空集合而不是猜测。在规划第 10 节列出的五项业务决策确定之前，
    F5 就靠这个实现保持诚实。
    """

    name = "unconfigured"

    def is_configured(self):
        return False

    def license_notice(self):
        return "尚未接入任何获得终端展示与缓存授权的单位或职位数据源。"

    def search_organizations(self, query, limit=10):
        return []

    def search_jobs(self, organization_source_key, limit=20):
        return []


# 已注册的数据源：新增 provider 时在此登记，并在构建时校验授权状态。
PROVIDER_REGISTRY = {
    UnconfiguredOrganizationProvider.name: UnconfiguredOrganizationProvider,
}


def eligible_results(items):
    """剔除缺少授权/溯源元数据的结果。

    规划第 7 节要求所有返回项都带 `source_provider`、`source_url`、
    `source_updated_at`、`verified_at`、`verification_state`；缺任何一项都
    不能对外展示。
    """
    kept = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if any(not str(item.get(field) or "").strip() for field in RESULT_REQUIRED_FIELDS):
            continue
        if str(item.get("verification_state")) not in VERIFICATION_STATES:
            continue
        kept.append(item)
    return kept


def build_organization_provider():
    """返回已配置的 provider；未配置或配置无效时返回安全的默认实现。"""
    key = os.environ.get("ORG_DATA_PROVIDER", "").strip()
    factory = PROVIDER_REGISTRY.get(key)
    if factory is None:
        return UnconfiguredOrganizationProvider()
    provider = factory()
    if not provider.is_configured():
        return UnconfiguredOrganizationProvider()
    return provider
