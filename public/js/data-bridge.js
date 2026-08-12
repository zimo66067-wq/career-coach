/* data-bridge.js · 真实数据接口层
 * 生产路径：API -> 当前会话缓存 -> 明确错误；MOCK 仅限显式演示模式。
 * 不将合成简历、面试或报告伪装成用户结果。
 */
(function () {
  'use strict';

  // ── API 端点配置 ──────────────────────────────────────
  // 生产环境由 pages-api-config.js 注入独立后端的 HTTPS 地址；
  // 不配置时保持空值，让页面明确显示未接入，而不是尝试调用 Pages 自身。
  var API_BASE = String(window.DUMATE_API_BASE || '').replace(/\/+$/, '');
  var ENDPOINTS = {
    uploadResume:    '/api/wf01/upload',
    uploadJD:        '/api/wf03/upload',
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

  // 后端会依次尝试主模型与备用模型（Vercel 函数上限为 60 秒）。
  // 30 秒会在后端完成可用的规则降级前提前中断请求。
  var TIMEOUT_MS = 55000;

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

  // 历史记录钩子：登录用户检测完成后自动落库；失败不影响主流程。
  function recordHistory(eventType, title, sessionId, status) {
    try {
      if (window.ZY_ACCOUNT && typeof window.ZY_ACCOUNT.addHistory === 'function') {
        window.ZY_ACCOUNT.addHistory({
          event_type: eventType,
          title: title,
          session_id: sessionId || genTraceId(),
          status: status || 'done'
        });
      }
    } catch (e) { /* ignore */ }
  }

  // ── 通用请求方法（fetch + timeout + trace_id） ─────────
  function request(endpoint, options) {
    options = options || {};
    var traceId = options._traceId || genTraceId();
    var url = API_BASE + endpoint;
    var headers = Object.assign({}, options.headers || {});
    // Only the server-issued, short-lived token is sent.  Source material and
    // consent wording remain out of headers and server-side storage.
    if (endpoint !== ENDPOINTS.consent) {
      var consentToken = getCache('consentToken');
      if (consentToken) headers['X-Consent-Token'] = consentToken;
    }
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
            return res.json().catch(function () { return {}; }).then(function (json) {
              resolve({
                error: json.error || 'http_' + res.status,
                message: json.message || ('服务器返回 ' + res.status),
                trace_id: json.trace_id || traceId,
                degraded: true
              });
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
          resolve(unavailable(traceId, 'network'));
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
      setCache('sessionId', res.session_id || traceId);
      return { resumeText: res.resumeText, resumeProfile: res.resumeProfile, trace_id: res.trace_id || traceId, session_id: res.session_id || traceId };
    }

    // 新上传的简历绝不能在接口失败时回退到上一份会话缓存；否则会把旧结果
    // 错配给当前用户材料。生产路径直接返回明确错误，演示模式才允许样本数据。
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
    var sessionId = getCache('sessionId') || traceId;
    var res = await request(ENDPOINTS.diagnoseResume, {
      body: { resumeText: resumeText, session_id: sessionId },
      _traceId: traceId
    });

    if (!res.error) {
      var normalized = normalizeResumeProfile(res.resumeProfile);
      var normalizedResult = Object.assign({}, res, { resumeProfile: normalized });
      setCache('resumeProfile', normalized);
      setCache('diagnoseResult', normalizedResult);
      setCache('sessionId', res.session_id || traceId);
      recordHistory(
        'F1',
        '简历诊断 · R' + (res.score_R !== undefined ? res.score_R : ''),
        res.session_id || traceId,
        'done'
      );
      return {
        resumeProfile: normalized,
        score_R: res.score_R !== undefined ? res.score_R : (res.resumeProfile ? res.resumeProfile.score_R : null),
        suggestions: res.suggestions || (res.resumeProfile ? res.resumeProfile.suggestions : []),
        trace_id: res.trace_id || traceId,
        session_id: res.session_id || traceId
      };
    }

    // 对当前提交的材料，失败时不得回退到上一份诊断缓存。
    // 演示模式才可显示合成诊断。
    var demo = demoData('resumeProfile', traceId, res.error);
    if (demo.error) return demo;
    var profile = normalizeResumeProfile(demo.data);
    recordHistory('F1', '简历诊断（演示模式）', traceId, 'partial');
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

  // 上传 JD 文件 -> {jdText, trace_id}
  async function uploadJD(file) {
    var traceId = genTraceId();
    var formData = new FormData();
    formData.append('file', file);
    var res = await request(ENDPOINTS.uploadJD, {
      body: formData,
      _traceId: traceId
    });

    // JD 与简历一样不能在当前文件上传失败时复用旧会话内容，
    // 否则可能把上一份岗位要求错配给用户的新职位。
    if (res.error) return res;
    setCache('jobText', res.jdText);
    return { jdText: res.jdText, trace_id: res.trace_id || traceId };
  }

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

    // 岗位要求是本次输入的直接依据；失败时必须明确失败，不能使用旧 JD
    // 或伪造空的本地解析结果继续匹配。
    return res;
  }

  // 匹配 JD -> {matchResult, trace_id}
  async function matchJD(resumeText, jobProfile) {
    var traceId = genTraceId();
    var res = await request(ENDPOINTS.matchJD, {
      body: { resumeText: resumeText, jobProfile: jobProfile },
      _traceId: traceId
    });

    if (!res.error) {
      setCache('matchResult', res);
      recordHistory(
        'F2',
        '岗位匹配 · M' + (res.score_M !== undefined ? res.score_M : ''),
        res.session_id || getCache('sessionId') || traceId,
        'done'
      );
      return { matchResult: res, trace_id: res.trace_id || traceId };
    }

    // 当前简历和 JD 的组合发生变化时，不允许复用旧匹配结果。
    return res;
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
      recordHistory('F3', '模拟面试 · 已完成', sessionId || traceId, 'done');
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
      recordHistory('F3', '模拟面试（缓存）', sessionId || traceId, 'partial');
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
    recordHistory('F3', '模拟面试（演示模式）', sessionId || traceId, 'partial');
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
      recordHistory(
        'F4',
        '能力报告 · C0=' + (res.ability && res.ability.baseline !== undefined ? res.ability.baseline : ''),
        sessionId || traceId,
        'done'
      );
      return { ability: res.ability, trace_id: res.trace_id || traceId };
    }

    // 缓存
    var cached = getCache('ability');
    if (cached) {
      console.warn('[DataBridge] 使用缓存数据: ability');
      recordHistory('F4', '能力报告（缓存）', sessionId || traceId, 'partial');
      return { ability: cached, degraded: true, degraded_reason: 'cached', trace_id: traceId };
    }

    var demo = demoData('ability', traceId, res.error);
    if (demo.error) return demo;
    recordHistory('F4', '能力报告（演示模式）', sessionId || traceId, 'partial');
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

  // 提交同意书 -> {status, consent_token}
  async function submitConsent(consentText) {
    var traceId = genTraceId();
    var res = await request(ENDPOINTS.consent, {
      body: { accepted: true, consent_version: '1' },
      _traceId: traceId
    });

    if (!res.error) {
      if (res.consent_token) setCache('consentToken', res.consent_token);
      sessionStorage.removeItem('cb_session_deleted');
      return {
        consent_id: res.consent_id,
        consent_token: res.consent_token,
        status: res.status || 'ACCEPTED',
        expires_in_seconds: res.expires_in_seconds,
        trace_id: res.trace_id || traceId
      };
    }

    if (!isDemoMode()) return res.error ? res : unavailable(traceId, 'invalid_consent_response');
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

  // 删除全部数据 -> {status: 'DELETED' | 'LOCAL_DELETED', deleted_at}
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

    // 没有可删除的服务端存储时，不能把浏览器缓存清除表述为服务端删除。
    console.warn('[DataBridge] 仅完成本地会话删除');
    markDeleted();
    return {
      status: 'LOCAL_DELETED',
      deleted_at: new Date().toISOString(),
      degraded: true,
      degraded_reason: 'server_delete_unavailable',
      message: '已清除当前浏览器会话；服务端删除功能尚未配置。',
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
    uploadJD: uploadJD,
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
