# -*- coding: utf-8 -*-
"""Model provider abstraction (phase 5).

MODEL_PROVIDER 环境变量选择 provider：
  - auto（默认）：配置 ZHIPU_API_KEY + 模型名时使用智谱路由，
    否则抛 ApiError，由上层规则降级（与历史行为一致）。
  - mock：返回确定性 MockModelRouter，无 key 全链路可测。
"""
import os

from tools.api_errors import ApiError
from tools.model_router import ZhipuModelRouter


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


def build_model_router():
    """按 MODEL_PROVIDER 构建模型路由；默认 auto 保持既有行为。"""
    provider_name = (os.environ.get("MODEL_PROVIDER") or "auto").strip().lower()
    if provider_name == "mock":
        return MockModelRouter()
    primary_model = (
        os.environ.get("DUMATE_MODEL")
        or os.environ.get("ZHIPU_MODEL")
        or os.environ.get("PRIMARY_MODEL")
    )
    fallback_model = os.environ.get("ZHIPU_FALLBACK_MODEL") or os.environ.get("FALLBACK_MODEL")
    if not os.environ.get("ZHIPU_API_KEY") or not (primary_model or fallback_model):
        raise ApiError("model_not_configured", "诊断模型尚未配置完成，请联系服务管理员。", 503)
    return ZhipuModelRouter(primary_model=primary_model, fallback_model=fallback_model)
