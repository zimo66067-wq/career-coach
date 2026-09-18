# -*- coding: utf-8 -*-
"""健康检查：模型配置、数据库方言、各工作流可用性、迁移状态。

Phase 7c：本文件从 `api/index.py` 拆出。**分支体是按行号逐字搬过来的，逻辑未改写**，
改的只有外壳 —— 原 `if route == ...` 们被包进一个函数，末尾补 `return UNHANDLED` 表示
「本族没接住，交给下一个」。

为什么末尾要 `return UNHANDLED` 而不是 `return None`：None 是合法返回值（虽然现在没人返回
它），用哨兵才能让"没接住"和"故意返回 None"区分开。哨兵见 `api/dispatch.py`。

打桩点：本模块只用 `from providers import model as model_provider` 后做属性查找，
不绑定 `build_model_router`（见 `tests/test_layering.py` 规则 5）。
"""

import os

from flask import request

from repositories.database import dialect

from api.http_layer import api_response
from api.sentinel import UNHANDLED
from api.startup import migration_status


def handle_health(route):
    if route == "health" and request.method == "GET":
        return api_response({
            "status": "ok",
            "model_configured": bool(os.environ.get("ZHIPU_API_KEY")),
            "database": dialect(),
            "workflows": {
                "wf01": "available", "wf02": "available", "wf03": "available",
                "wf04": "available", "wf05": "available", "wf06": "available",
                "wf07": "available",
                "profile": "available", "target_jobs": "available", "actions": "available",
            },
            # 领域收敛迁移的可观测性：迁移失败不静默（见 repositories/migrations.py）
            "migrations": migration_status(),
        })

    return UNHANDLED
