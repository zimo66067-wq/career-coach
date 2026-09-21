# -*- coding: utf-8 -*-
"""Model provider abstraction (phase 5).

MODEL_PROVIDER 环境变量选择 provider：
  - auto（默认）：配置 ZHIPU_API_KEY + 模型名时使用智谱路由，
    否则抛 ApiError，由上层规则降级（与历史行为一致）。
  - mock：返回确定性 MockModelRouter，无 key 全链路可测。
"""
import os

from domain.internal.api_errors import ApiError
from providers.model_router import ZhipuModelRouter


class BaseModelProvider:
    name = "base"

    def call(self, task, user_input, **kwargs):
        raise NotImplementedError


class MockModelProvider(BaseModelProvider):
    name = "mock"

    def call(self, task, user_input, **kwargs):
        if str(task or "") == "resume_diagnosis":
            output = {"subscores": {}, "suggestions": [], "mock": True}
        else:
            output = (
                "这是 Mock 模型生成的确定性文本，用于无 key 场景的链路验证；"
                "请人工确认后使用。"
            )
        return {
            "status": "success",
            "output": output,
            "trace_id": "mock_" + str(task or "generic")[:16],
            "model": "mock",
            "degraded": True,
        }


class MockModelRouter:
    """Router-compatible wrapper around MockModelProvider.

    Accepts both positional (task, user_input) and keyword
    (system=..., user=...) call styles used by existing callers.
    """

    def __init__(self, provider=None):
        self._provider = provider or MockModelProvider()

    def call(self, *args, **kwargs):
        task = args[0] if args else (kwargs.get("task") or "generic")
        if len(args) > 1:
            user_input = args[1]
        else:
            user_input = kwargs.get("user_input") or kwargs.get("user") or ""
        return self._provider.call(task, user_input)


def _chat_model_names():
    """主/备 Chat 模型名的优先级链（唯一一份，供 build_model_router 与状态查询共用）。"""
    primary_model = (
        os.environ.get("DUMATE_MODEL")
        or os.environ.get("ZHIPU_MODEL")
        or os.environ.get("PRIMARY_MODEL")
    )
    fallback_model = os.environ.get("ZHIPU_FALLBACK_MODEL") or os.environ.get("FALLBACK_MODEL")
    return primary_model, fallback_model


def model_config_status():
    """模型配置**是否真的可用**：key 与模型名**缺一不可**。

    为什么要单独有这个：`/api/health` 原来只报 `ZHIPU_API_KEY` 是否存在，而
    `build_model_router()` 要求「key **和** 模型名」都在。于是"key 配了、模型名忘了填"
    时 health 报 `model_configured=True`，每一次诊断却落规则降级 —— 用户拿到的还是
    HTTP 200 加一份看起来正常的规则分数。2026-09-21 在生产上实测到了这个假绿灯。

    `reason` 是**粗粒度**的原因码，只说明"哪一类配置缺失"，不含任何密钥内容。
    """
    provider_name = (os.environ.get("MODEL_PROVIDER") or "auto").strip().lower()
    if provider_name == "mock":
        return {"ready": True, "provider": "mock", "reason": None}
    primary_model, fallback_model = _chat_model_names()
    if not os.environ.get("ZHIPU_API_KEY"):
        return {"ready": False, "provider": "zhipu", "reason": "zhipu_api_key_missing"}
    if not (primary_model or fallback_model):
        return {"ready": False, "provider": "zhipu", "reason": "model_name_missing"}
    return {"ready": True, "provider": "zhipu", "reason": None}


def build_model_router():
    """按 MODEL_PROVIDER 构建模型路由；默认 auto 保持既有行为。"""
    provider_name = (os.environ.get("MODEL_PROVIDER") or "auto").strip().lower()
    if provider_name == "mock":
        return MockModelRouter()
    primary_model, fallback_model = _chat_model_names()
    if not os.environ.get("ZHIPU_API_KEY") or not (primary_model or fallback_model):
        raise ApiError("model_not_configured", "诊断模型尚未配置完成，请联系服务管理员。", 503)
    return ZhipuModelRouter(primary_model=primary_model, fallback_model=fallback_model)
