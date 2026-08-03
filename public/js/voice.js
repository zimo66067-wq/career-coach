/* voice.js · 浏览器语音增强
 * ASR: Web Speech API SpeechRecognition
 * TTS: speechSynthesis
 * 10秒回退: 任何语音故障10秒内切文字输入
 */
(function () {
  'use strict';

  var FALLBACK_TIMEOUT = 10000; // 10秒

  var State = {
    IDLE: 'idle',
    LISTENING: 'listening',
    PROCESSING: 'processing',
    SPEAKING: 'speaking',
    ERROR: 'error',
    FALLBACK_TEXT: 'fallback_text'
  };

  var currentState = State.IDLE;
  var recognition = null;
  var timer = null;
  var currentTurnId = null;
  var currentDraft = '';

  // ── 浏览器支持检测 ────────────────────────────────────
  function isASRSupported() {
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  }

  function isTTSSupported() {
    return 'speechSynthesis' in window;
  }

  // ── 获取 SpeechRecognition 构造器 ──────────────────────
  function getRecognitionCtor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition;
  }

  // ── 清理计时器 ────────────────────────────────────────
  function clearTimer() {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  }

  // ── 启动 ASR ──────────────────────────────────────────
  // callbacks: {onResult(transcript, confidence), onError(type, msg), onTimeout()}
  function startASR(turnId, callbacks) {
    callbacks = callbacks || {};
    currentTurnId = turnId;
    currentDraft = '';

    // 1. 检测支持
    if (!isASRSupported()) {
      console.warn('[VoiceHandler] ASR 不被当前浏览器支持');
      currentState = State.ERROR;
      if (callbacks.onError) callbacks.onError('not_supported', '当前浏览器不支持语音识别');
      _triggerFallback(turnId, '', callbacks);
      return;
    }

    // 如已有 recognition 在运行，先停掉
    if (recognition) {
      try { recognition.abort(); } catch (e) { /* noop */ }
      recognition = null;
    }

    var Ctor = getRecognitionCtor();
    recognition = new Ctor();

    // 3. 设置参数
    recognition.lang = 'zh-CN';
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    // 4. 启动 10 秒计时器
    clearTimer();
    timer = setTimeout(function () {
      console.warn('[VoiceHandler] ASR 超时 (' + FALLBACK_TIMEOUT + 'ms)，触发回退');
      try { recognition.stop(); } catch (e) { /* noop */ }
      currentState = State.ERROR;
      if (callbacks.onTimeout) callbacks.onTimeout();
      _triggerFallback(turnId, currentDraft, callbacks);
    }, FALLBACK_TIMEOUT);

    // 5. onresult
    recognition.onresult = function (event) {
      var transcript = '';
      var confidence = 0;
      for (var i = event.resultIndex; i < event.results.length; i++) {
        var r = event.results[i];
        if (r.isFinal) {
          transcript += r[0].transcript;
          confidence = r[0].confidence || 0.8;
        } else {
          transcript += r[0].transcript;
          confidence = 0.5;
        }
      }
      currentDraft = transcript;
      if (callbacks.onResult) callbacks.onResult(transcript, confidence, !event.results[event.results.length - 1].isFinal);
    };

    // 6. onerror
    recognition.onerror = function (event) {
      clearTimer();
      var errType = event.error || 'unknown';
      var msg = '';
      switch (errType) {
        case 'not-allowed':
        case 'service-not-allowed':
          msg = '麦克风权限被拒绝';
          errType = 'mic_denied';
          break;
        case 'network':
          msg = '语音识别网络错误';
          break;
        case 'no-speech':
          msg = '未检测到语音输入';
          break;
        case 'aborted':
          msg = '语音识别被中止';
          break;
        case 'audio-capture':
          msg = '麦克风硬件不可用';
          break;
        default:
          msg = '语音识别错误: ' + errType;
      }
      console.warn('[VoiceHandler] ASR 错误: ' + errType + ' - ' + msg);
      currentState = State.ERROR;
      if (callbacks.onError) callbacks.onError(errType, msg);
      // no-speech 和 aborted 是正常停止，其他触发回退
      if (errType !== 'aborted') {
        _triggerFallback(turnId, currentDraft, callbacks);
      }
    };

    // 7. onend
    recognition.onend = function () {
      clearTimer();
      if (currentState === State.LISTENING) {
        currentState = State.IDLE;
      }
      if (callbacks.onEnd) callbacks.onEnd(currentDraft);
    };

    // 8. 更新状态并启动
    currentState = State.LISTENING;
    try {
      recognition.start();
      console.log('[VoiceHandler] ASR 已启动, turnId=' + turnId);
    } catch (e) {
      clearTimer();
      console.warn('[VoiceHandler] ASR 启动失败:', e);
      currentState = State.ERROR;
      if (callbacks.onError) callbacks.onError('start_failed', e.message || 'ASR 启动失败');
      _triggerFallback(turnId, '', callbacks);
    }
  }

  // ── 启动 TTS ──────────────────────────────────────────
  // callbacks: {onEnd(), onError(msg)}
  function startTTS(text, callbacks) {
    callbacks = callbacks || {};

    // 1. 检测支持
    if (!isTTSSupported()) {
      console.warn('[VoiceHandler] TTS 不被当前浏览器支持');
      if (callbacks.onError) callbacks.onError('not_supported', '当前浏览器不支持语音合成');
      return;
    }

    // 取消之前的播放
    window.speechSynthesis.cancel();

    // 2. 创建 utterance
    var utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'zh-CN';
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    utterance.volume = 1.0;

    // 尝试选择中文语音
    var voices = window.speechSynthesis.getVoices();
    var zhVoice = null;
    for (var i = 0; i < voices.length; i++) {
      if (voices[i].lang && voices[i].lang.indexOf('zh') === 0) {
        zhVoice = voices[i];
        break;
      }
    }
    if (zhVoice) utterance.voice = zhVoice;

    // 3-4. 回调
    utterance.onend = function () {
      currentState = State.IDLE;
      if (callbacks.onEnd) callbacks.onEnd();
    };

    utterance.onboundary = function () {
      // 可用于同步字幕高亮
    };

    utterance.onerror = function (event) {
      console.warn('[VoiceHandler] TTS 错误:', event.error);
      currentState = State.ERROR;
      if (callbacks.onError) callbacks.onError(event.error || 'tts_error', '语音合成失败');
    };

    // 6. 更新状态并播放
    currentState = State.SPEAKING;
    window.speechSynthesis.speak(utterance);
    console.log('[VoiceHandler] TTS 已启动, 文本长度=' + text.length);
  }

  // ── 取消所有语音 ──────────────────────────────────────
  function cancel() {
    if (recognition) {
      try { recognition.abort(); } catch (e) { /* noop */ }
      recognition = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    clearTimer();
    currentState = State.IDLE;
    console.log('[VoiceHandler] 已取消所有语音');
  }

  // ── 内部: 触发文字回退 ────────────────────────────────
  function _triggerFallback(turnId, draft, callbacks) {
    fallbackToText(turnId, draft);
    if (callbacks.onFallback) callbacks.onFallback(turnId, draft);
  }

  // ── 回退到文字输入 ────────────────────────────────────
  function fallbackToText(turnId, draft) {
    // 1. cancel 所有语音
    if (recognition) {
      try { recognition.abort(); } catch (e) { /* noop */ }
      recognition = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    clearTimer();

    // 2. 显示文字输入框（由页面监听 state 变化处理 UI）
    var container = document.getElementById('voice-fallback-area');
    if (container) {
      container.style.display = 'block';
      var input = container.querySelector('textarea');
      if (input) {
        // 3. 如果有 draft（部分识别结果），填入输入框
        if (draft) {
          input.value = draft;
          input.focus();
          // 光标移到末尾
          var len = input.value.length;
          input.setSelectionRange(len, len);
        } else {
          input.focus();
        }
      }
    }

    // 4. 更新状态指示器
    var indicator = document.getElementById('voice-state-indicator');
    if (indicator) {
      indicator.textContent = '已切换文字输入';
      indicator.className = 'voice-indicator fallback';
    }

    currentState = State.FALLBACK_TEXT;
    console.log('[VoiceHandler] 已回退到文字输入, turnId=' + turnId + ', draft=' + (draft ? '"' + draft.slice(0, 30) + '..."' : '空'));
  }

  // ── 获取状态 ──────────────────────────────────────────
  function getState() {
    return currentState;
  }

  // ── 获取当前草稿 ──────────────────────────────────────
  function getDraft() {
    return currentDraft;
  }

  // ── 重置状态 ──────────────────────────────────────────
  function reset() {
    cancel();
    currentTurnId = null;
    currentDraft = '';
    currentState = State.IDLE;
  }

  // ── 停止 ASR 采集（触发 onend，不触发回退） ────────────
  function stopASR() {
    clearTimer();
    if (recognition) {
      try { recognition.stop(); } catch (e) { /* noop */ }
    }
  }

  // ── 暴露接口 ──────────────────────────────────────────
  window.VoiceHandler = {
    startASR: startASR,
    stopASR: stopASR,
    startTTS: startTTS,
    cancel: cancel,
    fallbackToText: fallbackToText,
    getState: getState,
    getDraft: getDraft,
    reset: reset,
    isASRSupported: isASRSupported,
    isTTSSupported: isTTSSupported,
    State: State
  };
})();
