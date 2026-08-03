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
import logging
import threading
import time
from typing import Optional, Callable

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
            asr_api: DuMate ASR API 地址（备用通道）
            tts_api: DuMate TTS API 地址（备用通道）
            fallback_timeout: 回退超时秒数，默认 10 秒
        """
        self.asr_api = asr_api
        self.tts_api = tts_api
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
            DuMate ASR API 调用需要真实 API，此处标注 NotImplementedError。
        """
        self._cancelled = False
        self._active_turn = turn_id

        # 启动 10 秒回退计时器
        self._start_timer(turn_id, on_timeout)

        # 后端编排层不直接调用浏览器 API；
        # DuMate ASR API 备用通道需要真实 API 实现
        if self.asr_api:
            try:
                self._call_dumate_asr(turn_id, on_result, on_error, on_timeout)
            except NotImplementedError:
                logger.warning("[voice] DuMate ASR API not implemented; "
                               "relying on browser ASR + text fallback")
            except Exception as e:
                logger.warning("[voice] ASR API error: %s", e)
                on_error(self.ASR_ERROR, str(e))

    def _call_dumate_asr(self, turn_id, on_result, on_error, on_timeout):
        """调用 DuMate ASR API（备用通道）。

        需要 DuMate 平台 ASR SDK 接入。
        """
        raise NotImplementedError(
            "DuMate ASR API call not implemented yet. "
            "Wire up DuMate platform ASR SDK here."
        )

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
            DuMate TTS API 调用需要真实 API，此处标注 NotImplementedError。
        """
        if not self.tts_api:
            # 无 TTS API 配置，静默跳过（TTS 是可选的）
            logger.info("[voice] TTS API not configured; skipping (non-blocking)")
            return

        try:
            self._call_dumate_tts(text, on_end, on_error)
        except NotImplementedError:
            logger.info("[voice] DuMate TTS API not implemented; "
                        "relying on browser TTS or skipping")
        except Exception as e:
            logger.warning("[voice] TTS error: %s", e)
            on_error(self.TTS_ERROR, str(e))

    def _call_dumate_tts(self, text, on_end, on_error):
        """调用 DuMate TTS API（备用通道）。

        需要 DuMate 平台 TTS SDK 接入。
        """
        raise NotImplementedError(
            "DuMate TTS API call not implemented yet. "
            "Wire up DuMate platform TTS SDK here."
        )

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
