# -*- coding: utf-8 -*-
"""asr.py · ASR provider 抽象（阶段4）

统一语音识别接口：Web Speech 优先（前端 voice.js），后端 ASR 备用通道
按 ASR_PROVIDER 环境变量选择 baidu / dashscope / mock（默认 mock）。

无 key 时 MockASRProvider 返回空文本，由前端 10 秒文字回退兜底，
保证面试主流程不被语音能力阻塞。
"""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class BaseASRProvider:
    """ASR provider 接口契约。"""

    name = "base"

    def transcribe(self, audio_bytes, content_type="audio/wav; rate=16000"):
        """将音频字节转为文本。

        Returns:
            dict: {"text": str, "confidence": float, "provider": str}
        """
        raise NotImplementedError


class MockASRProvider(BaseASRProvider):
    """无 key 降级：不发起外部调用，返回空文本交由文字回退。"""

    name = "mock"

    def transcribe(self, audio_bytes, content_type="audio/wav; rate=16000"):
        return {"text": "", "confidence": 0.0, "provider": "mock", "degraded": True}


class BaiduASRProvider(BaseASRProvider):
    """百度短语音识别（vop.baidu.com/server_api，REST）。

    配置：ASR_API_URL（识别接口地址）+ BAIDU_SPEECH_TOKEN（access_token）。
    """

    name = "baidu"

    def __init__(self, api_url=None, token=None):
        self.api_url = api_url or os.environ.get("ASR_API_URL")
        self.token = token if token is not None else os.environ.get("BAIDU_SPEECH_TOKEN", "")

    def _ensure_ready(self):
        if not self.api_url or not self.token:
            raise RuntimeError(
                "baidu_asr_not_configured: 需要配置 ASR_API_URL 与 BAIDU_SPEECH_TOKEN。"
            )

    def transcribe(self, audio_bytes, content_type="audio/wav; rate=16000"):
        self._ensure_ready()
        url = "%s?cuid=career-coach&token=%s" % (self.api_url, self.token)
        req = Request(url, data=audio_bytes or b"", method="POST")
        req.add_header("Content-Type", content_type)
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError) as exc:
            raise RuntimeError("baidu_asr_network: %s" % exc)
        if data.get("err_no", 0) != 0:
            raise RuntimeError(
                "baidu_asr_error: %s" % data.get("err_msg", "unknown")
            )
        result = data.get("result") or [""]
        return {
            "text": result[0],
            "confidence": 0.85,
            "provider": "baidu",
            "degraded": False,
        }


class DashScopeASRProvider(BaseASRProvider):
    """阿里 DashScope Paraformer 文件转写（同步 REST 占位）。

    配置：DASHSCOPE_API_KEY（dashscope.api-key）。
    """

    name = "dashscope"

    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")

    def _ensure_ready(self):
        if not self.api_key:
            raise RuntimeError(
                "dashscope_asr_not_configured: 需要配置 DASHSCOPE_API_KEY。"
            )

    def transcribe(self, audio_bytes, content_type="audio/wav; rate=16000"):
        self._ensure_ready()
        # 完整实现需接入 dashscope 文件转写工作流（上传->提交->轮询）。
        # 此处保持契约：未配置完整服务时明确报错，由上层降级为文字输入。
        raise RuntimeError(
            "dashscope_asr_workflow_not_ready: 请配置 DASHSCOPE_API_KEY 后使用"
        )


def build_asr_provider():
    """按 ASR_PROVIDER 环境变量构建 provider；默认 mock（无 key 全链路可测）。"""
    name = (os.environ.get("ASR_PROVIDER") or "mock").strip().lower()
    if name == "baidu":
        return BaiduASRProvider()
    if name == "dashscope":
        return DashScopeASRProvider()
    return MockASRProvider()
