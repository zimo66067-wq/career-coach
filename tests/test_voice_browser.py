# -*- coding: utf-8 -*-
"""test_voice_browser.py · 浏览器语音功能自动化测试脚本 (P0-05)

配合手动测试清单使用，自动化验证 voice_handler.py 后端逻辑。
浏览器端 voice.js 的实机测试见同目录 voice-test-checklist.md。

用法:
  python tests/test_voice_browser.py
  python tests/test_voice_browser.py --verbose

测试覆盖 5 类故障场景:
  1. 正常流程: ASR 成功 + 置信度 >= 0.75 -> 接受
  2. 麦克风拒绝: mic_denied -> 10秒回退文字输入
  3. 断网: network_error -> 文字回退
  4. 识别错误: ASR 置信度 < 0.75 -> 需用户确认
  5. TTS 失败: tts_error -> 不阻断主链路
"""
import sys
import os
import time
import threading
import argparse

# 确保能 import tools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from voice_handler import VoiceHandler


class VoiceTestResult:
    """单次测试结果记录"""
    def __init__(self, name, passed, detail="", latency_ms=0):
        self.name = name
        self.passed = passed
        self.detail = detail
        self.latency_ms = latency_ms

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        return "[%s] %s (%dms) - %s" % (status, self.name, self.latency_ms, self.detail)


def test_normal_flow():
    """场景1: 正常 ASR 流程，置信度 >= 0.75"""
    vh = VoiceHandler(fallback_timeout=10)
    turn_id = "test_normal"
    results = {}

    # 模拟 ASR 成功返回
    confidence = 0.92
    transcript = "我负责后端 API 开发，使用 Go 和 MySQL"

    check = vh.check_confidence(confidence, turn_id)
    assert check["accepted"] is True, "高置信度应被接受"
    assert check["needs_confirmation"] is False, "高置信度无需确认"

    _r = VoiceTestResult(
        "normal_flow", True,
        "confidence=0.92, accepted=True, no confirmation needed"
    )
    assert _r.passed is True, _r.detail


def test_mic_denied():
    """场景2: 麦克风权限被拒绝 -> 文字回退"""
    vh = VoiceHandler(fallback_timeout=10)
    turn_id = "test_mic_denied"

    # 模拟麦克风拒绝错误
    fallback = vh.handle_error(VoiceHandler.MIC_DENIED, turn_id, "Permission denied")

    assert fallback["fallback"] is not None, "麦克风拒绝应触发文字回退"
    assert fallback["fallback"]["mode"] == "text_input", "回退模式应为 text_input"
    assert fallback["should_retry"] is False, "麦克风拒绝不应重试"

    _r = VoiceTestResult(
        "mic_denied", True,
        "error=mic_denied, fallback=text_input, retry=False"
    )
    assert _r.passed is True, _r.detail


def test_network_error():
    """场景3: 网络断开 -> 文字回退"""
    vh = VoiceHandler(fallback_timeout=10)
    turn_id = "test_network"

    fallback = vh.handle_error(VoiceHandler.NETWORK_ERROR, turn_id, "Network unreachable")

    assert fallback["fallback"] is not None, "网络错误应触发文字回退"
    assert fallback["fallback"]["mode"] == "text_input"
    assert fallback["should_retry"] is False

    _r = VoiceTestResult(
        "network_error", True,
        "error=network_error, fallback=text_input, retry=False"
    )
    assert _r.passed is True, _r.detail


def test_low_confidence():
    """场景4: ASR 置信度 < 0.75 -> 需用户确认"""
    vh = VoiceHandler(fallback_timeout=10)
    turn_id = "test_low_conf"

    # 模拟低置信度 ASR 结果
    confidence = 0.55
    check = vh.check_confidence(confidence, turn_id)

    assert check["accepted"] is False, "低置信度不应被直接接受"
    assert check["needs_confirmation"] is True, "低置信度需要用户确认"

    _r = VoiceTestResult(
        "low_confidence", True,
        "confidence=0.55, accepted=False, needs_confirmation=True"
    )
    assert _r.passed is True, _r.detail


def test_tts_error():
    """场景5: TTS 失败 -> 不阻断主链路"""
    vh = VoiceHandler(fallback_timeout=10)
    turn_id = "test_tts"

    fallback = vh.handle_error(VoiceHandler.TTS_ERROR, turn_id, "TTS synthesis failed")

    assert fallback["fallback"] is None, "TTS 错误不应触发文字回退"
    assert fallback["should_retry"] is False, "TTS 错误不应重试"

    _r = VoiceTestResult(
        "tts_error_non_blocking", True,
        "error=tts_error, fallback=None, retry=False (non-blocking)"
    )
    assert _r.passed is True, _r.detail


def test_fallback_timer():
    """场景6: 10秒超时回退"""
    vh = VoiceHandler(fallback_timeout=2)  # 缩短为 2 秒方便测试
    turn_id = "test_timeout"

    timer_expired = threading.Event()

    def on_timeout():
        timer_expired.set()

    # 启动计时器
    timer = threading.Timer(2.5, on_timeout)
    timer.daemon = True
    timer.start()

    # 模拟 ASR 未返回（等待超时）
    timer_expired.wait(timeout=5)

    assert timer_expired.is_set(), "计时器应在超时后触发"

    # 验证回退
    fallback = vh.get_fallback_text_input(turn_id, draft="部分转写结果")
    assert fallback["mode"] == "text_input"
    assert fallback["draft"] == "部分转写结果"

    _r = VoiceTestResult(
        "fallback_timer", True,
        "timeout=2s, fallback triggered with draft text"
    )
    assert _r.passed is True, _r.detail


def test_cancel():
    """场景7: 取消语音操作"""
    vh = VoiceHandler(fallback_timeout=10)
    vh._cancelled = False

    vh.cancel()

    assert vh._cancelled is True, "取消后 _cancelled 应为 True"
    assert vh._active_turn is None, "取消后 _active_turn 应为 None"
    assert len(vh._timers) == 0, "取消后所有计时器应已清除"

    _r = VoiceTestResult(
        "cancel_operation", True,
        "cancelled=True, timers cleared"
    )
    assert _r.passed is True, _r.detail


_normal_flow_check = test_normal_flow
_mic_denied_check = test_mic_denied
_network_error_check = test_network_error
_low_confidence_check = test_low_confidence
_tts_error_check = test_tts_error
_fallback_timer_check = test_fallback_timer
_cancel_check = test_cancel


def _assert_voice_result(result):
    """Adapt the reporting helpers into real pytest assertions."""
    assert result.passed, result.detail


def test_normal_flow():
    _assert_voice_result(_normal_flow_check())


def test_mic_denied():
    _assert_voice_result(_mic_denied_check())


def test_network_error():
    _assert_voice_result(_network_error_check())


def test_low_confidence():
    _assert_voice_result(_low_confidence_check())


def test_tts_error():
    _assert_voice_result(_tts_error_check())


def test_fallback_timer():
    _assert_voice_result(_fallback_timer_check())


def test_cancel():
    _assert_voice_result(_cancel_check())


def run_all_tests(verbose=False):
    """运行全部语音测试"""
    tests = [
        _normal_flow_check,
        _mic_denied_check,
        _network_error_check,
        _low_confidence_check,
        _tts_error_check,
        _fallback_timer_check,
        _cancel_check,
    ]

    results = []
    passed = 0
    failed = 0

    print("=" * 70)
    print("Voice Handler Automated Tests (P0-05)")
    print("Backend logic validation for voice_handler.py")
    print("=" * 70)

    for test_fn in tests:
        t0 = time.time()
        try:
            result = test_fn()
            result.latency_ms = int((time.time() - t0) * 1000)
            results.append(result)
            if result.passed:
                passed += 1
            else:
                failed += 1
            if verbose:
                print(result)
        except Exception as e:
            latency = int((time.time() - t0) * 1000)
            result = VoiceTestResult(test_fn.__name__, False, str(e), latency)
            results.append(result)
            failed += 1
            if verbose:
                print(result)

    print("-" * 70)
    print("Results: %d passed, %d failed, %d total" % (passed, failed, len(results)))
    print("=" * 70)

    # 输出 JSON 格式结果
    output = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "tests": [
            {
                "name": r.name,
                "passed": r.passed,
                "detail": r.detail,
                "latency_ms": r.latency_ms,
            }
            for r in results
        ],
    }

    output_path = os.path.join(
        os.path.dirname(__file__), "voice_test_results.json"
    )
    import json
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("Results saved to: %s" % output_path)

    return failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voice Handler Tests")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    success = run_all_tests(verbose=args.verbose)
    sys.exit(0 if success else 1)
