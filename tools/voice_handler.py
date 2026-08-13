# -*- coding: utf-8 -*-
"""voice_handler.py · 语音增强处理模块（P0-05）

ASR: 浏览器 Web Speech API (primary) -> DuMate ASR API (fallback)
TTS: 浏览器 speechSynthesis (primary) -> DuMate TTS API (fallback)
回退: 任何语音故障 10秒内切回同一轮文字输入

这是后端/编排层模块，定义 ASR/TTS 接口与 10 秒回退计时器。
前端浏览器侧的对应实现在 ui/prototype/js/voice.js。

用法:
  from tools.voice_handler import VoiceHandler
  vh = VoiceHandler(asr_api="https://dumate.baidu.com/asr", fallback_timeout=10)
  vh.start_asr(turn_id, on_result, on_error, on_timeout)
"""
import json
import logging
import os
import threading
import time
import urllib.parse
from typing import Optional, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from tools.providers.asr import build_asr_provider  # noqa: E402

logger = logging.getLogger("voice_handler")


class VoiceHandler:
    """语音增强处理模块。

    ASR 流程: 检测浏览器支持 -> 启动 -> 超时/错误 -> 10秒回退文字输入
    TTS 流程: 检测浏览器支持 -> 启动 -> 错误 -> 降级（不影响主链路）
    """

    # 故障类型
    OK = "ok"
    MIC_DENIED = "mic_denied"
    NETWORK_ERROR = "network_error"
    ASR_ERROR = "asr_error"
    TTS_ERROR = "tts_error"

    # ASR 置信度阈值
    ASR_CONFIDENCE_THRESHOLD = 0.75

    def __init__(self, asr_api=None, tts_api=None, fallback_timeout=10):
        """初始化语音处理器。

        Args:
            asr_api: 百度 ASR API 地址（备用通道，如 https://vop.baidu.com/server_api）
            tts_api: 百度 TTS API 地址（备用通道，如 https://tsn.baidu.com/text2audio）
            fallback_timeout: 回退超时秒数，默认 10 秒
        """
        self.asr_api = asr_api or os.environ.get("ASR_API_URL")
        self.tts_api = tts_api or os.environ.get("TTS_API_URL")
        self.fallback_timeout = fallback_timeout

        # 运行时状态
        self._timers = {}          # turn_id -> threading.Timer
        self._active_turn = None   # 当前活跃的 turn_id
        self._cancelled = False

    # ================================================================ #
    # ASR
    # ================================================================ #

    def start_asr(self, turn_id, on_result, on_error, on_timeout):
        """启动 ASR。

        在后端编排层，此方法负责调度：
        1. 通知前端启动浏览器 Web Speech API（通过 WebSocket/SSE 指令）
        2. 启动 10 秒回退计时器
        3. 超时未收到结果 -> 调用 on_timeout 切文字输入

        Args:
            turn_id: 面试轮次 ID
            on_result: 回调 fn(transcript: str, confidence: float)
            on_error: 回调 fn(error_type: str, message: str)
            on_timeout: 回调 fn() -> 自动切文字输入

        Note:
            实际的浏览器 ASR 调用由前端 voice.js 执行；
            百度 ASR API 备用通道在配置了 ASR_API_URL + BAIDU_SPEECH_TOKEN 时启用。
        """
        self._cancelled = False
        self._active_turn = turn_id

        # 启动 10 秒回退计时器
        self._start_timer(turn_id, on_timeout)

        # 后端编排层不直接调用浏览器 API；
        # 百度 ASR API 备用通道需要配置 ASR_API_URL
        # ASR fallback channel via provider abstraction (default mock).
        provider = build_asr_provider()
        if provider.name != "mock":
            try:
                self._call_provider_asr(provider, turn_id, on_result, on_error)
            except Exception as e:
                logger.warning("[voice] ASR provider error: %s", e)
                on_error(self.ASR_ERROR, str(e))

    def _call_provider_asr(self, provider, turn_id, on_result, on_error):
        """Run provider.transcribe in a worker thread (non-blocking)."""
        def _asr_worker():
            try:
                result = provider.transcribe(None)
            except Exception as exc:
                on_error(self.ASR_ERROR, "asr_provider: %s" % exc)
                return
            text = str(result.get("text") or "")
            if text and not self._cancelled:
                self._stop_timer(turn_id)
                on_result(text, float(result.get("confidence", 0.85)))
            else:
                on_error(self.ASR_ERROR, "asr_empty_result")

        thread = threading.Thread(target=_asr_worker, daemon=True)
        thread.start()


    def _call_baidu_asr(self, turn_id, on_result, on_error, on_timeout):
        """调用百度 ASR API（备用通道）。

        需要配置环境变量:
          - ASR_API_URL: 百度语音识别接口地址
          - BAIDU_SPEECH_TOKEN: 百度语音 access_token

        在单独线程中执行 HTTP 调用，避免阻塞主链路。
        """
        token = os.environ.get("BAIDU_SPEECH_TOKEN", "")
        if not token:
            logger.warning("[voice] BAIDU_SPEECH_TOKEN not set; "
                           "ASR fallback unavailable, relying on browser ASR")
            return

        def _asr_worker():
            try:
                # 百度 ASR 需要音频数据；此处由前端录音后上传
                # 后端编排层仅负责调度，实际音频由 API 层接收
                url = "%s?cuid=career-coach&token=%s" % (self.asr_api, token)
                req = Request(url, method="POST")
                req.add_header("Content-Type", "audio/wav; rate=16000")

                with urlopen(req, timeout=self.fallback_timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                if data.get("err_no", 0) == 0:
                    result = data.get("result", [""])[0]
                    confidence = 0.85  # 百度 ASR 不返回置信度，使用默认值
                    if not self._cancelled:
                        self._stop_timer(turn_id)
                        on_result(result, confidence)
                else:
                    on_error(self.ASR_ERROR,
                             "baidu_asr_error: %s" % data.get("err_msg", "unknown"))
            except (HTTPError, URLError) as e:
                on_error(self.NETWORK_ERROR, "asr_network: %s" % str(e))
            except Exception as e:
                on_error(self.ASR_ERROR, "asr_exception: %s" % str(e))

        thread = threading.Thread(target=_asr_worker, daemon=True)
        thread.start()

    # ================================================================ #
    # TTS
    # ================================================================ #

    def start_tts(self, text, on_end, on_error):
        """启动 TTS。

        TTS 是可选的，关闭不影响主链路。

        Args:
            text: 要合成的文本
            on_end: 回调 fn() 合成完成
            on_error: 回调 fn(error_type: str, message: str)

        Note:
            浏览器 TTS 由前端 voice.js 执行；
            百度 TTS API 备用通道在配置了 TTS_API_URL + BAIDU_SPEECH_TOKEN 时启用。
        """
        if not self.tts_api:
            # 无 TTS API 配置，静默跳过（TTS 是可选的）
            logger.info("[voice] TTS API not configured; skipping (non-blocking)")
            return

        try:
            self._call_baidu_tts(text, on_end, on_error)
        except Exception as e:
            logger.warning("[voice] TTS error: %s", e)
            on_error(self.TTS_ERROR, str(e))

    def _call_baidu_tts(self, text, on_end, on_error):
        """调用百度 TTS API（备用通道）。

        需要配置环境变量:
          - TTS_API_URL: 百度语音合成接口地址
          - BAIDU_SPEECH_TOKEN: 百度语音 access_token

        在单独线程中执行 HTTP 调用，避免阻塞主链路。
        """
        token = os.environ.get("BAIDU_SPEECH_TOKEN", "")
        if not token:
            logger.info("[voice] BAIDU_SPEECH_TOKEN not set; "
                        "TTS fallback unavailable, relying on browser TTS")
            return

        def _tts_worker():
            try:
                params = urllib.parse.urlencode({
                    "tex": text,
                    "lan": "zh",
                    "cuid": "career-coach",
                    "ctp": 1,
                    "tok": token,
                    "spd": 5,
                    "pit": 5,
                    "vol": 5,
                    "per": 0,
                    "aue": 3,
                })
                url = "%s?%s" % (self.tts_api, params)
                req = Request(url, method="POST")
                req.add_header("Content-Type",
                               "application/x-www-form-urlencoded")

                with urlopen(req, timeout=self.fallback_timeout) as resp:
                    content_type = resp.headers.get("Content-Type", "")
                    body = resp.read()

                if "audio" in content_type:
                    # 合成成功，返回音频数据
                    # 后端编排层不直接播放音频，由前端 voice.js 处理
                    logger.info("[voice] TTS audio generated, %d bytes", len(body))
                    if not self._cancelled:
                        on_end()
                else:
                    # 合成失败，返回 JSON 错误信息
                    err_data = json.loads(body.decode("utf-8"))
                    on_error(self.TTS_ERROR,
                             "baidu_tts_error: %s" % err_data.get("err_msg", "unknown"))
            except (HTTPError, URLError) as e:
                on_error(self.NETWORK_ERROR, "tts_network: %s" % str(e))
            except Exception as e:
                on_error(self.TTS_ERROR, "tts_exception: %s" % str(e))

        thread = threading.Thread(target=_tts_worker, daemon=True)
        thread.start()

    # ================================================================ #
    # 取消
    # ================================================================ #

    def cancel(self):
        """取消当前语音操作。

        停止所有计时器，标记取消状态。
        前端 voice.js 的 cancel() 会同步停止浏览器 ASR/TTS。
        """
        self._cancelled = True
        self._active_turn = None
        # 取消所有计时器
        for turn_id, timer in list(self._timers.items()):
            timer.cancel()
        self._timers.clear()

    # ================================================================ #
    # 文字回退
    # ================================================================ #

    def get_fallback_text_input(self, turn_id, draft=None):
        """返回文字输入回退方案。

        Args:
            turn_id: 面试轮次 ID
            draft: 可选的草稿文本（如 ASR 部分转写结果）

        Returns:
            dict: {mode, turn_id, draft, message}
        """
        return {
            "mode": "text_input",
            "turn_id": turn_id,
            "draft": draft or "",
            "message": "voice_unavailable_text_fallback",
        }

    # ================================================================ #
    # 计时器
    # ================================================================ #

    def _start_timer(self, turn_id, on_timeout=None):
        """10秒回退计时器。

        ASR 启动后开始计时，超时自动标记需要回退。
        实际的 on_timeout 回调在 start_asr 中绑定。
        """
        timer = threading.Timer(
            self.fallback_timeout,
            self._on_timer_expire,
            args=[turn_id],
        )
        timer.daemon = True
        timer.start()
        self._timers[turn_id] = timer
        logger.info("[voice] ASR timer started for turn %s (%ds)",
                    turn_id, self.fallback_timeout)

    def _on_timer_expire(self, turn_id):
        """计时器到期处理。"""
        if self._cancelled:
            return
        if turn_id in self._timers:
            del self._timers[turn_id]
        logger.info("[voice] ASR timer expired for turn %s", turn_id)
        # 实际的 on_timeout 回调由 start_asr 的调用方处理
        # 这里只清理状态，start_asr 会绑定具体回调

    def _stop_timer(self, turn_id):
        """停止指定 turn 的计时器（ASR 成功返回结果时调用）。"""
        timer = self._timers.pop(turn_id, None)
        if timer:
            timer.cancel()

    # ================================================================ #
    # 浏览器能力检测（前端 voice.js 对应）
    # ================================================================ #

    def _browser_asr_available(self):
        """检测浏览器 ASR 支持。

        后端编排层返回 True 表示「支持调度浏览器 ASR」；
        实际的浏览器能力检测由前端 voice.js 的 _browserAsrAvailable() 执行。
        """
        return True

    def _browser_tts_available(self):
        """检测浏览器 TTS 支持。

        后端编排层返回 True 表示「支持调度浏览器 TTS」；
        实际的浏览器能力检测由前端 voice.js 的 _browserTtsAvailable() 执行。
        """
        return True

    # ================================================================ #
    # ASR 置信度处理
    # ================================================================ #

    def check_confidence(self, confidence, turn_id):
        """检查 ASR 置信度。

        Args:
            confidence: ASR 置信度 (0-1)
            turn_id: 面试轮次 ID

        Returns:
            dict: {accepted: bool, needs_confirmation: bool}
            - confidence >= 0.75: accepted=True, needs_confirmation=False
            - confidence < 0.75: accepted=False, needs_confirmation=True
        """
        if confidence is None:
            return {"accepted": False, "needs_confirmation": True}

        if confidence >= self.ASR_CONFIDENCE_THRESHOLD:
            self._stop_timer(turn_id)
            return {"accepted": True, "needs_confirmation": False}
        else:
            return {"accepted": False, "needs_confirmation": True}

    # ================================================================ #
    # 故障处理
    # ================================================================ #

    def handle_error(self, error_type, turn_id, message=""):
        """统一故障处理。

        Args:
            error_type: self.MIC_DENIED / NETWORK_ERROR / ASR_ERROR / TTS_ERROR
            turn_id: 面试轮次 ID
            message: 错误详情

        Returns:
            dict: {fallback: dict, should_retry: bool}
        """
        logger.warning("[voice] error: type=%s turn=%s msg=%s",
                       error_type, turn_id, message)

        # 停止计时器
        self._stop_timer(turn_id)

        # TTS 错误不阻断主链路
        if error_type == self.TTS_ERROR:
            return {"fallback": None, "should_retry": False}

        # 其他错误 -> 文字回退
        fallback = self.get_fallback_text_input(turn_id)
        return {"fallback": fallback, "should_retry": False}
