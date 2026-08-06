# -*- coding: utf-8 -*-
"""test_model_router_providers.py · 模型路由 provider 与降级链（异常场景）

覆盖：智谱/千帆 HTTP 错误、非法响应、输出解析变体、模型优先级、
提示词加载、未知任务、主->备->规则降级链、日志内容脱敏。
"""
import json
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from model_router import (
    ModelRouter,
    QianfanModelRouter,
    ZhipuModelRouter,
    extract_system_prompt,
    parse_model_output,
)


def fake_response(body):
    class Response:
        def read(self):
            return json.dumps(body).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    return Response()


@pytest.fixture()
def zhipu(monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "test-key")
    return ZhipuModelRouter(primary_model="glm-test", enable_log=False)


@pytest.fixture()
def qianfan(monkeypatch):
    monkeypatch.setenv("QIANFAN_API_KEY", "test-key")
    return QianfanModelRouter(primary_model="qwen-test", enable_log=False)


PARAMS = {"temperature": 0.1, "max_tokens": 100, "timeout": 5}


# ---------------------------------------------------------------- #
# 智谱 provider
# ---------------------------------------------------------------- #


def test_zhipu_success_parses_json(zhipu):
    body = {"choices": [{"message": {"content": '{"ok": true}'}}]}
    with patch("model_router.urlopen", return_value=fake_response(body)):
        result = zhipu.call("resume_diagnosis", "简历正文")
    assert result["status"] == "success"
    assert result["output"] == {"ok": True}


def test_zhipu_http_error_maps_to_runtime_error(zhipu):
    with patch(
        "model_router.urlopen",
        side_effect=HTTPError("https://x", 401, "Unauthorized", {}, None),
    ):
        with pytest.raises(RuntimeError, match="zhipu_http_401"):
            zhipu._try_call("glm-test", "p", "u", PARAMS, None)


def test_zhipu_network_error_maps(zhipu):
    with patch("model_router.urlopen", side_effect=URLError("offline")):
        with pytest.raises(RuntimeError, match="zhipu_network_error"):
            zhipu._try_call("glm-test", "p", "u", PARAMS, None)


def test_zhipu_invalid_response_shape(zhipu):
    with patch("model_router.urlopen", return_value=fake_response({"choices": []})):
        with pytest.raises(ValueError, match="zhipu_invalid_response"):
            zhipu._try_call("glm-test", "p", "u", PARAMS, None)


def test_zhipu_parse_output_variants():
    assert ZhipuModelRouter._parse_output('```\n{"a": 1}\n```') == {"a": 1}
    assert ZhipuModelRouter._parse_output('分析结果：\n{"a": 1}') == {"a": 1}
    assert ZhipuModelRouter._parse_output("纯文本输出") == "纯文本输出"


# ---------------------------------------------------------------- #
# 千帆 provider
# ---------------------------------------------------------------- #


def test_qianfan_success_parses_json(qianfan):
    body = {"choices": [{"message": {"content": '{"ok": true}'}}]}
    with patch("model_router.urlopen", return_value=fake_response(body)):
        result = qianfan.call("resume_diagnosis", "简历正文")
    assert result["status"] == "success"
    assert result["output"] == {"ok": True}


def test_qianfan_http_error_maps(qianfan):
    with patch(
        "model_router.urlopen",
        side_effect=HTTPError("https://x", 429, "Too Many", {}, None),
    ):
        with pytest.raises(RuntimeError, match="qianfan_http_429"):
            qianfan._try_call("qwen-test", "p", "u", PARAMS, None)


def test_qianfan_network_error_maps(qianfan):
    with patch("model_router.urlopen", side_effect=URLError("offline")):
        with pytest.raises(RuntimeError, match="qianfan_network_error"):
            qianfan._try_call("qwen-test", "p", "u", PARAMS, None)


def test_qianfan_invalid_response_shape(qianfan):
    with patch("model_router.urlopen", return_value=fake_response({"foo": "bar"})):
        with pytest.raises(ValueError, match="qianfan_invalid_response"):
            qianfan._try_call("qwen-test", "p", "u", PARAMS, None)


def test_parse_model_output_variants():
    assert parse_model_output('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_model_output('结果：{"a": 1}') == {"a": 1}
    assert parse_model_output("[1, 2, 3]") == [1, 2, 3]
    assert parse_model_output("普通文本") == "普通文本"


# ---------------------------------------------------------------- #
# 基类路由与降级链
# ---------------------------------------------------------------- #


def test_unknown_task_type_fails():
    router = ModelRouter(enable_log=False)
    result = router.call("no_such_task", "输入")
    assert result["status"] == "failed"
    assert result["error_type"] == "unknown_task_type"


def test_model_priority_param_over_env(monkeypatch):
    monkeypatch.setenv("DUMATE_MODEL", "env-model")
    router = ModelRouter(primary_model="arg-model")
    assert router.primary_model == "arg-model"
    router2 = ModelRouter()
    assert router2.primary_model == "env-model"


def test_prompt_file_loaded_with_fact_lock():
    router = ModelRouter()
    prompt = router._load_prompt("resume_diagnosis")
    assert "事实锁" in prompt
    assert router._load_prompt("") == ""


def test_prompt_only_contains_system_section():
    """回归：系统提示不得包含文件标题、用法说明或模板占位符，
    否则模型会把元说明当指令，输出闲聊文本而非合同 JSON。"""
    router = ModelRouter()
    prompt = router._load_prompt("resume_diagnosis")
    assert prompt.startswith("你是简历诊断抽取器")
    assert "# prompts/" not in prompt
    assert "## 系统提示" not in prompt
    assert "## 用户输入" not in prompt
    assert "{deidentified_resume_text}" not in prompt


def test_extract_system_prompt_edge_cases():
    assert extract_system_prompt("") == ""
    assert extract_system_prompt("没有标记的纯文本") == "没有标记的纯文本"
    assert extract_system_prompt("## 系统提示\n\n系统正文\n\n## 用户输入\n{x}") == "系统正文"


def test_fallback_model_success_is_degraded():
    class FirstFail(ModelRouter):
        def _try_call(self, model, *_args, **_kwargs):
            if model == "primary":
                raise RuntimeError("primary down")
            return {"ok": True}

    router = FirstFail(primary_model="primary", fallback_model="fallback", enable_log=False)
    result = router.call("resume_diagnosis", "输入")
    assert result["status"] == "success"
    assert result["degraded"] is True
    assert result["model"] == "fallback"


def test_all_models_fail_rule_degraded():
    class AlwaysFail(ModelRouter):
        def _try_call(self, *_args, **_kwargs):
            raise RuntimeError("down")

    router = AlwaysFail(primary_model="primary", fallback_model="fallback", enable_log=False)
    result = router.call("resume_diagnosis", "输入")
    assert result["status"] == "degraded"
    assert result["model"] == "rule_degraded"
    assert result["output"].get("degraded") is True


def test_log_does_not_contain_user_content(capsys):
    router = ModelRouter(enable_log=True)
    router.call("no_such_task", "SECRET-INPUT-不要入库")
    captured = capsys.readouterr().out
    assert "SECRET-INPUT" not in captured
    assert "sha256:" in captured
