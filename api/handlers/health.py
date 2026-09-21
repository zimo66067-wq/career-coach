# -*- coding: utf-8 -*-
"""健康检查：模型配置、数据库方言、各工作流可用性、迁移状态。

`model_configured` 与 `model_ready` **不是一回事**，两个都留着：
前者报"有没有 `ZHIPU_API_KEY`"（历史语义，别改，`tests/test_api.py` 在断言它），
后者报"`build_model_router()` 会不会成功"（`providers/model.py::model_config_status`，
与工厂同口径）。2026-09-21 生产实测：只给 key、不给模型名时前者为真、后者为假，
而每一次诊断都落规则降级且响应仍是 200 —— 只看前者就会把这种部署判成"已就绪"。

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
from providers import model as model_provider


def handle_health(route):
    if route == "health" and request.method == "GET":
        config = model_provider.model_config_status()
        return api_response({
            "status": "ok",
            "model_configured": bool(os.environ.get("ZHIPU_API_KEY")),
            # `model_configured` 只回答"有没有 key"；它**不等于**"能不能调模型"。
            # 路由还要求模型名，两者缺一都会让每次诊断落规则降级 —— 而响应仍是 200。
            # 所以这里额外报一个与 `build_model_router()` **同口径**的判据。
            "model_ready": config["ready"],
            "model_reason": config["reason"],
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
