/* data-bridge.js · 真实数据接口层
 * 三级降级: API -> 缓存 -> MOCK(标注)
 * 不破坏现有 MOCK 接口，MOCK 降级为演示缓存
 */
(function () {
  'use strict';

  // ── API 端点配置 ──────────────────────────────────────
  var API_BASE = window.DUMATE_API_BASE || '';
  var ENDPOINTS = {
    uploadResume:    '/api/wf01/upload',
    diagnoseResume:  '/api/wf02/diagnose',
    submitJD:        '/api/wf03/jd',
    matchJD:         '/api/wf03/match',
    startInterview:  '/api/wf04/start',
    submitAnswer:    '/api/wf04/answer',
    endInterview:    '/api/wf04/end',
    getAbility:      '/api/wf05/ability',
    deleteData:      '/api/wf06/delete',
    consent:         '/api/wf01/consent'
  };

  var TIMEOUT_MS = 30000;

  // ── 内存缓存（SessionStorage 持久化） ─────────────────
  var CACHE_PREFIX = 'cb_cache_';

  function setCache(key, data) {
    try {
      sessionStorage.setItem(CACHE_PREFIX + key, JSON.stringify({
        data: data,
        ts: Date.now()
      }));
    } catch (e) {
      console.warn('[DataBridge] 缓存写入失败:', key, e);
    }
  }

  function getCache(key, maxAge) {
    try {
      var raw = sessionStorage.getItem(CACHE_PREFIX + key);
      if (!raw) return null;
      var entry = JSON.parse(raw);
      var age = Date.now() - entry.ts;
      if (maxAge && age > maxAge) return null;
      return entry.data;
    } catch (e) {
      return null;
    }
  }

  // ── trace_id 生成 ─────────────────────────────────────
  function genTraceId() {
    return 't' + Date.now() + Math.random().toString(36).substr(2, 6);
  }

  // ── 通用请求方法（fetch + timeout + trace_id） ─────────
  function request(endpoint, options) {
    options = options || {};
    var traceId = options._traceId || genTraceId();
    var url = API_BASE + endpoint;
    var headers = options.headers || {};
    headers['X-Trace-Id'] = traceId;

    var body = options.body;
    // FormData 不设 Content-Type，浏览器自动加 boundary
    if (body && !(body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
      if (typeof body === 'object') body = JSON.stringify(body);
    }

    return new Promise(function (resolve) {
      var timedOut = false;
      var controller = null;

      // AbortController 优先
      if (typeof AbortController !== 'undefined') {
        controller = new AbortController();
      }

      var timer = setTimeout(function () {
        timedOut = true;
        if (controller) controller.abort();
        console.warn('[DataBridge] 请求超时 (' + TIMEOUT_MS + 'ms): ' + endpoint);
        resolve({ error: 'timeout', message: '请求超时', trace_id: traceId, degraded: true });
      }, TIMEOUT_MS);

      var fetchOpts = { method: options.method || 'POST', headers: headers, body: body };
      if (controller) fetchOpts.signal = controller.signal;

      fetch(url, fetchOpts)
        .then(function (res) {
          clearTimeout(timer);
          if (!res.ok) {
            console.warn('[DataBridge] HTTP ' + res.status + ': ' + endpoint);
            return res.text().then(function () {
              resolve({ error: 'http_' + res.status, message: '服务器返回 ' + res.status, trace_id: traceId, degraded: true });
            });
          }
          return res.json().then(function (json) {
            resolve(json);
          }).catch(function () {
            resolve({ error: 'parse', message: '响应解析失败', trace_id: traceId, degraded: true });
          });
        })
        .catch(function (err) {
          clearTimeout(timer);
          if (timedOut) return; // 已由 timer 处理
          console.warn('[DataBridge] 请求失败: ' + endpoint, err);
          resolve({ error: 'network', message: err.message || '网络错误', trace_id: traceId, degraded: true });
        });
    });
  }

  // ── 降级辅助：返回 MOCK 数据并标注 degraded ───────────
  function degrade(mockKey, traceId, reason) {
    console.warn('[DataBridge] 降级到 MOCK 数据: ' + mockKey + (reason ? ' (' + reason + ')' : ''));
    if (!window.MOCK || !window.MOCK[mockKey]) {
      return { error: 'no_mock', message: 'MOCK 数据不存在: ' + mockKey, trace_id: traceId, degraded: true };
    }
    // 深拷贝避免污染原始 MOCK
    var data = JSON.parse(JSON.stringify(window.MOCK[mockKey]));
    return { data: data, degraded: true, degraded_reason: reason || 'fallback_to_mock', trace_id: traceId };
  }

  // ── 从降级结果中提取 data ──────────────────────────────
  function unwrap(result, fallbackKeys) {
    if (result.error) return result;
    if (result.data !== undefined) return result.data;
    return result;
  }

  // ============================================================
  //  F1: 简历上传与诊断
  // ============================================================

  // 上传简历文件 -> {resumeText, resumeProfile, trace_id}
  async function uploadResume(file) {
    var traceId = genTraceId();

    // 尝试 API
    var formData = new FormData();
    formData.append('file', file);
    var res = await request(ENDPOINTS.uploadResume, {
      body: formData,
      _traceId: traceId
    });

    if (!res.error) {
      // 缓存结果
      setCache('resumeText', res.resumeText);
      setCache('resumeProfile', res.resumeProfile);
      return { resumeText: res.resumeText, resumeProfile: res.resumeProfile, trace_id: res.trace_id || traceId };
    }

    // 降级: 缓存 -> MOCK
    var cached = getCache('resumeText');
    if (cached) {
      console.warn('[DataBridge] 使用缓存数据: resumeText');
      return {
        resumeText: cached,
        resumeProfile: getCache('resumeProfile'),
        degraded: true,
        degraded_reason: 'cached',
        trace_id: traceId
      };
    }
    return {
      resumeText: window.MOCK.resumeText,
      resumeProfile: window.MOCK.resumeProfile,
      degraded: true,
      degraded_reason: 'fallback_to_mock',
      trace_id: traceId
    };
  }

  // 诊断简历 -> {resumeProfile, score_R, suggestions, trace_id}
  async function diagnoseResume(resumeText) {
    var traceId = genTraceId();
    var res = await request(ENDPOINTS.diagnoseResume, {
      body: { resumeText: resumeText },
      _traceId: traceId
    });

    if (!res.error) {
      setCache('resumeProfile', res.resumeProfile);
      setCache('diagnoseResult', res);
      return {
        resumeProfile: res.resumeProfile,
        score_R: res.score_R !== undefined ? res.score_R : (res.resumeProfile ? res.resumeProfile.score_R : null),
        suggestions: res.suggestions || (res.resumeProfile ? res.resumeProfile.suggestions : []),
        trace_id: res.trace_id || traceId
      };
    }

    // 缓存
    var cached = getCache('diagnoseResult');
    if (cached) {
      console.warn('[DataBridge] 使用缓存数据: diagnoseResult');
      return {
        resumeProfile: cached.resumeProfile,
        score_R: cached.score_R,
        suggestions: cached.suggestions,
        degraded: true,
        degraded_reason: 'cached',
        trace_id: traceId
      };
    }

    // MOCK
    var profile = window.MOCK.resumeProfile;
    return {
      resumeProfile: profile,
      score_R: profile.score_R,
      suggestions: profile.suggestions,
      degraded: true,
      degraded_reason: 'fallback_to_mock',
      trace_id: traceId
    };
  }

  // ============================================================
  //  F2: JD 匹配
  // ============================================================

  // 提交 JD -> {jobProfile, trace_id}
  async function submitJD(jdText) {
    var traceId = genTraceId();
    var res = await request(ENDPOINTS.submitJD, {
      body: { jdText: jdText },
      _traceId: traceId
    });

    if (!res.error) {
      setCache('jobProfile', res.jobProfile);
      return { jobProfile: res.jobProfile, trace_id: res.trace_id || traceId };
    }

    // 缓存
    var cached = getCache('jobProfile');
    if (cached) {
      console.warn('[DataBridge] 使用缓存数据: jobProfile');
      return { jobProfile: cached, degraded: true, degraded_reason: 'cached', trace_id: traceId };
    }

    // 降级: 返回结构化 JD（从 JD 文本提取基础结构）
    console.warn('[DataBridge] 降级到本地 JD 解析');
    var jobProfile = {
      source: jdText,
      requirements: [],
      degraded: true,
      degraded_reason: 'local_parse'
    };
    return { jobProfile: jobProfile, degraded: true, degraded_reason: 'local_parse', trace_id: traceId };
  }

  // 匹配 JD -> {matchResult, trace_id}
  async function matchJD(resumeProfile, jobProfile) {
    var traceId = genTraceId();
    var res = await request(ENDPOINTS.matchJD, {
      body: { resumeProfile: resumeProfile, jobProfile: jobProfile },
      _traceId: traceId
    });

    if (!res.error) {
      setCache('matchResult', res.matchResult);
      return { matchResult: res.matchResult, trace_id: res.trace_id || traceId };
    }

    // 缓存
    var cached = getCache('matchResult');
    if (cached) {
      console.warn('[DataBridge] 使用缓存数据: matchResult');
      return { matchResult: cached, degraded: true, degraded_reason: 'cached', trace_id: traceId };
    }

    // MOCK
    var result = degrade('matchResult', traceId, res.error);
    return { matchResult: result.data, degraded: true, degraded_reason: 'fallback_to_mock', trace_id: traceId };
  }

  // ============================================================
  //  F3: 面试
  // ============================================================

  // 开始面试 -> {session_id, firstQuestion, trace_id}
  async function startInterview(jobProfile, resumeProfile, matchGaps) {
    var traceId = genTraceId();
    var res = await request(ENDPOINTS.startInterview, {
      body: {
        jobProfile: jobProfile,
        resumeProfile: resumeProfile,
        matchGaps: matchGaps || []
      },
      _traceId: traceId
    });

    if (!res.error) {
      setCache('sessionId', res.session_id);
      return {
        session_id: res.session_id,
        firstQuestion: res.firstQuestion,
        trace_id: res.trace_id || traceId
      };
    }

    // 缓存
    var cachedSid = getCache('sessionId');
    if (cachedSid) {
      console.warn('[DataBridge] 使用缓存数据: sessionId');
      return {
        session_id: cachedSid,
        firstQuestion: window.MOCK.interviews[0].question,
        degraded: true,
        degraded_reason: 'cached',
        trace_id: traceId
      };
    }

    // MOCK
    console.warn('[DataBridge] 降级到 MOCK 面试数据');
    return {
      session_id: 'mock_session_' + traceId,
      firstQuestion: window.MOCK.interviews[0].question,
      degraded: true,
      degraded_reason: 'fallback_to_mock',
      trace_id: traceId
    };
  }

  // 提交回答 -> {turn, followUp, trace_id}
  async function submitAnswer(sessionId, answerText, asrConfidence) {
    var traceId = genTraceId();
    var res = await request(ENDPOINTS.submitAnswer, {
      body: {
        session_id: sessionId,
        answer_text: answerText,
        asr_confidence: asrConfidence !== undefined ? asrConfidence : null
      },
      _traceId: traceId
    });

    if (!res.error) {
      return {
        turn: res.turn,
        followUp: res.followUp,
        trace_id: res.trace_id || traceId
      };
    }

    // 缓存: 无缓存策略（每次回答不同），直接 MOCK 轮次
    console.warn('[DataBridge] 降级到 MOCK 面试轮次');
    var turnCount = parseInt(sessionStorage.getItem('cb_mock_turn') || '0', 10);
    var idx = turnCount % window.MOCK.interviews.length;
    sessionStorage.setItem('cb_mock_turn', String(turnCount + 1));
    var mockTurn = window.MOCK.interviews[idx];
    return {
      turn: mockTurn,
      followUp: mockTurn.follow_up,
      degraded: true,
      degraded_reason: 'fallback_to_mock',
      trace_id: traceId
    };
  }

  // 结束面试 -> {report, score_I, turns, trace_id}
  async function endInterview(sessionId) {
    var traceId = genTraceId();
    var res = await request(ENDPOINTS.endInterview, {
      body: { session_id: sessionId },
      _traceId: traceId
    });

    if (!res.error) {
      setCache('interviewReport', res);
      return {
        report: res.report,
        score_I: res.score_I,
        turns: res.turns,
        trace_id: res.trace_id || traceId
      };
    }

    // 缓存
    var cached = getCache('interviewReport');
    if (cached) {
      console.warn('[DataBridge] 使用缓存数据: interviewReport');
      return {
        report: cached.report,
        score_I: cached.score_I,
        turns: cached.turns,
        degraded: true,
        degraded_reason: 'cached',
        trace_id: traceId
      };
    }

    // MOCK
    console.warn('[DataBridge] 降级到 MOCK 面试报告');
    return {
      report: window.MOCK.interviews,
      score_I: window.MOCK.score_I,
      turns: window.MOCK.interviews.length,
      degraded: true,
      degraded_reason: 'fallback_to_mock',
      trace_id: traceId
    };
  }

  // ============================================================
  //  F4: 能力雷达
  // ============================================================

  // 获取能力报告 -> {ability, trace_id}
  async function getAbility(sessionId) {
    var traceId = genTraceId();
    var res = await request(ENDPOINTS.getAbility, {
      body: { session_id: sessionId },
      _traceId: traceId
    });

    if (!res.error) {
      setCache('ability', res.ability);
      return { ability: res.ability, trace_id: res.trace_id || traceId };
    }

    // 缓存
    var cached = getCache('ability');
    if (cached) {
      console.warn('[DataBridge] 使用缓存数据: ability');
      return { ability: cached, degraded: true, degraded_reason: 'cached', trace_id: traceId };
    }

    // MOCK
    var result = degrade('ability', traceId, res.error);
    return { ability: result.data, degraded: true, degraded_reason: 'fallback_to_mock', trace_id: traceId };
  }

  // ============================================================
  //  WF-06: 隐私
  // ============================================================

  // 提交同意书 -> {consent_id, status}
  async function submitConsent(consentText) {
    var traceId = genTraceId();
    var res = await request(ENDPOINTS.consent, {
      body: { consent_text: consentText },
      _traceId: traceId
    });

    if (!res.error) {
      return { consent_id: res.consent_id, status: res.status || 'ACCEPTED', trace_id: res.trace_id || traceId };
    }

    console.warn('[DataBridge] 降级: consent');
    return {
      consent_id: 'mock_consent_' + traceId,
      status: 'ACCEPTED',
      degraded: true,
      degraded_reason: 'fallback_to_mock',
      trace_id: traceId
    };
  }

  // 删除全部数据 -> {status: 'DELETED', deleted_at}
  async function deleteAllData(sessionId) {
    var traceId = genTraceId();

    // 即使 API 不可用也标记本地删除
    function markDeleted() {
      sessionStorage.setItem('cb_session_deleted', 'true');
      // 清理缓存
      Object.keys(sessionStorage)
        .filter(function (k) { return k.indexOf(CACHE_PREFIX) === 0; })
        .forEach(function (k) { sessionStorage.removeItem(k); });
    }

    var res = await request(ENDPOINTS.deleteData, {
      body: { session_id: sessionId },
      _traceId: traceId
    });

    if (!res.error) {
      markDeleted();
      return { status: 'DELETED', deleted_at: res.deleted_at || new Date().toISOString(), trace_id: res.trace_id || traceId };
    }

    // 降级: 本地标记删除
    console.warn('[DataBridge] 降级: 本地标记删除');
    markDeleted();
    return {
      status: 'DELETED',
      deleted_at: new Date().toISOString(),
      degraded: true,
      degraded_reason: 'local_delete',
      trace_id: traceId
    };
  }

  // ── 会话已删除检查 ────────────────────────────────────
  function isSessionDeleted() {
    return sessionStorage.getItem('cb_session_deleted') === 'true';
  }

  // ── 暴露接口 ──────────────────────────────────────────
  window.DataBridge = {
    uploadResume: uploadResume,
    diagnoseResume: diagnoseResume,
    submitJD: submitJD,
    matchJD: matchJD,
    startInterview: startInterview,
    submitAnswer: submitAnswer,
    endInterview: endInterview,
    getAbility: getAbility,
    submitConsent: submitConsent,
    deleteAllData: deleteAllData,

    // 降级检查
    isDegraded: function (result) {
      return result && result.degraded === true;
    },

    // 获取 MOCK 数据（明确标注为演示缓存）
    getMockData: function (key) {
      console.warn('[DataBridge] 使用 MOCK 数据作为演示缓存');
      return window.MOCK ? window.MOCK[key] : null;
    },

    // 会话状态
    isSessionDeleted: isSessionDeleted,

    // 缓存工具
    _cache: { get: getCache, set: setCache },

    // 端点配置（便于调试）
    _endpoints: ENDPOINTS
  };
})();
