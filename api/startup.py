# -*- coding: utf-8 -*-
"""领域收敛迁移的冷启动引导与状态上报（Phase 7c 从 `api/index.py` 拆出）。

## 为什么从"import 期副作用"改成显式 `bootstrap()`

原文把 `ensure_applied()` 写在模块顶层，于是"跑一次迁移"这件事发生在 **import 的时刻**，
谁都不需要写它 —— 也没有人看得出它发生了。拆出来之后这个形态有个具体代价：
入口要"保证迁移跑过"，就只能写一个**导入了但不用**的 import（`from api import startup`），
而那正是 `tests/test_phase7c_contract.py` 7c-5 要判成"垃圾再导出"的形状。

改成显式调用后：

* 入口写 `bootstrap()`，一眼看得出"冷启动做了一件事"；
* 这个 import 是**被用的**，不需要任何豁免名单；
* 迁移不再挂在 import 顺序上（原来它只保证"比 index 的后续代码晚"）。

行为不变：仍然只在入口 import 时尝试一次，仍然幂等，失败仍然不阻断服务。

## `_MIGRATION_ERROR` 是打桩点，必须留在模块级

`tests/test_migrations.py` 会把它重置为 `None` 再调 `migration_status()`，验证"失败照实
上报、不假装 ok、不被重试掩盖"。所以它不能挪进函数局部或变成只读常量。
"""
from api.app_instance import app

# ---- Phase 2：领域收敛迁移 ----------------------------------------------------
# 建表本身是加法（CREATE TABLE IF NOT EXISTS），但"历史数据要落到新模型"必须显式迁移。
# 迁移幂等；冷启动执行一次，失败不阻断服务（新表已由 DDL 建好，迁移只做列补齐与状态
# 规范化），但必须可见 —— /api/health 的 migrations 字段会如实上报。
#
# 这里刻意只 import 模块本身而不是三个函数：/api/health 必须报告**当前**数据库的真实
# 状态（补跑未应用的迁移后再上报），否则换了数据库之后健康检查会继续报旧结论。
from repositories import migrations as _migrations  # noqa: E402

_MIGRATION_ERROR = None


def bootstrap():
    """冷启动尝试一次迁移。幂等；失败不抛，记进 `_MIGRATION_ERROR` 由 health 上报。

    `_MIGRATION_ERROR` 一旦被这次失败写上，就**不会**再被后续调用抹掉 —— 这是有意的：
    冷启动的问题要一直可见，不能被"后来某次成功了"掩盖。
    """
    global _MIGRATION_ERROR
    if _MIGRATION_ERROR is not None:
        return _MIGRATION_ERROR
    try:
        _migrations.ensure_applied()
    except Exception as exc:  # pragma: no cover - 故障路径由 /api/health 上报
        _MIGRATION_ERROR = "%s: %s" % (type(exc).__name__, exc)
        app.logger.exception("phase-2 domain migration failed")
    return _MIGRATION_ERROR


def migration_status():
    """给 /api/health 用的迁移状态：先补跑未应用的迁移，再如实上报。

    冷启动时的失败会记在 ``_MIGRATION_ERROR`` 里并一直上报，不会被重试掩盖。
    """
    expected = [version for version, _func in _migrations.MIGRATIONS]
    error = _MIGRATION_ERROR
    if error is None:
        try:
            _migrations.ensure_applied()
        except Exception as exc:  # pragma: no cover - 故障路径
            error = "%s: %s" % (type(exc).__name__, exc)
    applied = []
    try:
        applied = sorted(_migrations.applied_versions())
    except Exception as exc:  # pragma: no cover - 故障路径
        if error is None:
            error = "%s: %s" % (type(exc).__name__, exc)
    return {
        "ok": error is None and all(version in applied for version in expected),
        "applied": applied,
        "expected": expected,
        "error": error,
    }
