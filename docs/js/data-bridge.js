/* data-bridge.js · 真实数据接口层
 * 生产路径：API -> 当前会话缓存 -> 明确错误；MOCK 仅限显式演示模式。
 * 不将合成简历、面试或报告伪装成用户结果。
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

  var SUBSCORE_LABELS = {
    structure: '结构完整度',
    clarity: '表达清晰度',
    achievement_evidence: '成果证据',
    skill_evidence: '技能证据',
    ats_readability: 'ATS可读性'
  };

  // 后端合同使用 source_spans[]；原型视图历史上读取 quote/label。
  // 此适配器只生成视图副本，绝不改写后端合同对象或伪造证据。
  function normalizeResumeProfile(profile) {
    if (!profile || !profile.subscores) return profile;
    var view = JSON.parse(JSON.stringify(profile));
    Object.keys(view.subscores).forEach(function (key) {
      var item = view.subscores[key] || {};
      var spans = Array.isArray(item.source_spans) ? item.source_spans : [];
      if (!item.quote && spans.length) item.quote = spans[0].quote || '';
      if (!item.label) item.label = SUBSCORE_LABELS[key] || key;
    });
    (view.suggestions || []).forEach(function (item) {
      var spans = Array.isArray(item.source_spans) ? item.source_spans : [];
      if (!item.quote && spans.length) item.quote = spans[0].quote || '';
    });
    return view;
  }

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

  function isDemoMode() {
    if (window.APP && typeof window.APP.isDemoMode === 'function') return window.APP.isDemoMode();
    return /[?&]demo=1(?:&|$)/.test(location.search);
  }

  function unavailable(traceId, reason) {
    console.warn('[DataBridge] 服务不可用；不会显示合成数据' + (reason ? ' (' + reason + ')' : ''));
    return {
      error: 'service_unavailable',
      message: '服务暂不可用，请稍后重试。未展示演示数据。',
      trace_id: traceId,
      degraded: true,
      degraded_reason: reason || 'api_unavailable'
    };
  }

  // ── 演示辅助：仅 ?demo=1 可返回合成数据 ───────────────
  function demoData(mockKey, traceId, reason) {
    if (!isDemoMode()) return unavailable(traceId, reason);
    console.warn('[DataBridge] 使用演示数据: ' + mockKey + (reason ? ' (' + reason + ')' : ''));
    if (!window.MOCK || !window.MOCK[mockKey]) {
      return { error: 'no_demo_data', message: '演示数据不存在: ' + mockKey, trace_id: traceId, degraded: true };
    }
    // 深拷贝避免污染原始 MOCK
    var data = JSON.parse(JSON.stringify(window.MOCK[mockKey]));
    return { data: data, degraded: true, degraded_reason: reason || 'demo_mock', demo_data: true, trace_id: traceId };
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

    // 降级: 当前会话缓存 -> 显式错误；只有演示模式才可使用合成样本。
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
    var demoText = demoData('resumeText', traceId, res.error);
    var demoProfile = demoData('resumeProfile', traceId, res.error);
    if (demoText.error || demoProfile.error) return demoText.error ? demoText : demoProfile;
    return {
      resumeText: demoText.data,
      resumeProfile: demoProfile.data,
      degraded: true,
      degraded_reason: 'demo_mock',
      demo_data: true,
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
      var normalized = normalizeResumeProfile(res.resumeProfile);
      var normalizedResult = Object.assign({}, res, { resumeProfile: normalized });
      setCache('resumeProfile', normalized);
      setCache('diagnoseResult', normalizedResult);
      return {
        resumeProfile: normalized,
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

    // 演示模式才可显示合成诊断。
    var demo = demoData('resumeProfile', traceId, res.error);
    if (demo.error) return demo;
    var profile = normalizeResumeProfile(demo.data);
    return {
      resumeProfile: profile,
      score_R: profile.score_R,
      suggestions: profile.suggestions,
      degraded: true,
      degraded_reason: 'demo_mock',
      demo_data: true,
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

    var demo = demoData('matchResult', traceId, res.error);
    if (demo.error) return demo;
    return {
      matchResult: demo.data,
      degraded: true,
      degraded_reason: 'demo_mock',
      demo_data: true,
      trace_id: traceId
    };
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
      setCache('firstQuestion', res.firstQuestion);
      return {
        session_id: res.session_id,
        firstQuestion: res.firstQuestion,
        trace_id: res.trace_id || traceId
      };
    }

    // 缓存
    var cachedSid = getCache('sessionId');
    var cachedQuestion = getCache('firstQuestion');
    if (cachedSid && cachedQuestion) {
      console.warn('[DataBridge] 使用缓存数据: sessionId / firstQuestion');
      return {
        session_id: cachedSid,
        firstQuestion: cachedQuestion,
        degraded: true,
        degraded_reason: 'cached',
        trace_id: traceId
      };
    }

    var demo = demoData('interviews', traceId, res.error);
    if (demo.error) return demo;
    return {
      session_id: 'mock_session_' + traceId,
      firstQuestion: demo.data[0].question,
      degraded: true,
      degraded_reason: 'demo_mock',
      demo_data: true,
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

    // 每次回答不同，没有可安全复用的缓存；生产态返回明确错误。
    var demo = demoData('interviews', traceId, res.error);
    if (demo.error) return demo;
    var turnCount = parseInt(sessionStorage.getItem('cb_mock_turn') || '0', 10);
    var idx = turnCount % demo.data.length;
    sessionStorage.setItem('cb_mock_turn', String(turnCount + 1));
    var mockTurn = demo.data[idx];
    return {
      turn: mockTurn,
      followUp: mockTurn.follow_up,
      degraded: true,
      degraded_reason: 'demo_mock',
      demo_data: true,
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

    var demoInterviews = demoData('interviews', traceId, res.error);
    var demoScore = demoData('score_I', traceId, res.error);
    if (demoInterviews.error || demoScore.error) return demoInterviews.error ? demoInterviews : demoScore;
    return {
      report: demoInterviews.data,
      score_I: demoScore.data,
      turns: demoInterviews.data.length,
      degraded: true,
      degraded_reason: 'demo_mock',
      demo_data: true,
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

    var demo = demoData('ability', traceId, res.error);
    if (demo.error) return demo;
    return {
      ability: demo.data,
      degraded: true,
      degraded_reason: 'demo_mock',
      demo_data: true,
      trace_id: traceId
    };
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

    if (!isDemoMode()) return unavailable(traceId, res.error);
    console.warn('[DataBridge] 演示模式：使用合成 consent 结果');
    return {
      consent_id: 'demo_consent_' + traceId,
      status: 'ACCEPTED',
      degraded: true,
      degraded_reason: 'demo_mock',
      demo_data: true,
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

    // 获取演示数据（生产路径一律返回 null）
    getMockData: function (key) {
      if (!isDemoMode()) {
        console.warn('[DataBridge] 已阻止在生产路径读取演示数据');
        return null;
      }
      console.warn('[DataBridge] 使用演示数据: ' + key);
      return window.MOCK ? window.MOCK[key] : null;
    },

    // 会话状态
    isSessionDeleted: isSessionDeleted,

    // 缓存工具
    _cache: { get: getCache, set: setCache },

    // 契约适配器（供离线验收；不修改后端 source_spans 结构）
    _normalizeResumeProfile: normalizeResumeProfile,

    // 端点配置（便于调试）
    _endpoints: ENDPOINTS
  };
})();
