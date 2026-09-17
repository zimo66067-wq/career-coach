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
    diagnoseResume:  '/api/wf02/diagnose',
    // Phase 6b：目标岗位工作区走 /api/target-jobs（产出 Decision / Gap），
    // 行动闭环走 /api/actions，证据档案走 /api/profile。
    // 旧的 /api/wf03/{upload,jd,match} 前端路径已退役：它只产出匹配分数，
    // 产不出 Decision 与 Gap，无法支撑目标岗位工作区（后端路由仍保留，见 Phase 7 决议）。
    profile:         '/api/profile',
    targetJobs:      '/api/target-jobs',
    actions:         '/api/actions',
    startInterview:  '/api/wf04/start',
    submitAnswer:    '/api/wf04/answer',
    endInterview:    '/api/wf04/end',
    getAbility:      '/api/wf05/ability',
    deleteData:      '/api/wf06/delete',
    consent:         '/api/wf01/consent',
    coverLetter:     '/api/wf07/cover-letter',
    applications:    '/api/wf07/applications'
  };

  // 当前目标岗位：F5 投递、F3 面试出题都要认同一个岗位，
  // 否则"我投的是哪个岗位"和"我练的是哪个岗位的缺口"会对不上。
  var CURRENT_TARGET_KEY = 'currentTargetJobId';

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
    var guestToken = getCache('guestToken');
    if (guestToken) headers['X-Guest-Token'] = guestToken;
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

      var fetchOpts = { method: options.method || 'POST', headers: headers, body: body, credentials: 'include' };
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

  // ── F5: 投递闭环（求职信 + 申请跟踪） ───────────────────
  function generateCoverLetter(sessionId, company, position) {
    return request(ENDPOINTS.coverLetter, {
      method: 'POST',
      body: { session_id: sessionId, company: company, position: position }
    });
  }

  function saveApplication(sessionId, company, position, coverLetter) {
    return request(ENDPOINTS.applications, {
      method: 'POST',
      body: {
        session_id: sessionId,
        company: company,
        position: position,
        cover_letter: coverLetter
      }
    });
  }

  function listApplications() {
    return request(ENDPOINTS.applications, { method: 'GET' });
  }

  function deleteApplication(appId) {
    return request(ENDPOINTS.applications + '?id=' + encodeURIComponent(String(appId)), {
      method: 'DELETE'
    });
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
    // 错配给当前用户材料。生产路径直接透传服务端明确错误（含 scanned_pdf 等具体错误码），演示模式才允许样本数据。
    if (!isDemoMode()) return res;
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
  //  目标岗位工作区（Target Job）
  //  "分析这个岗位，能不能投" —— 建岗 → 分析 → Decision / 要求 / 缺口 / 依据
  // ============================================================

  // 当前目标岗位 ID：跨页面认同一个岗位（F5 投递、F3 出题都读它）
  function setCurrentTargetJob(targetJobId) {
    if (targetJobId === null || targetJobId === undefined || targetJobId === '') {
      try { sessionStorage.removeItem(CACHE_PREFIX + CURRENT_TARGET_KEY); } catch (e) { /* ignore */ }
      return null;
    }
    var id = parseInt(targetJobId, 10);
    if (!isFinite(id)) return null;
    setCache(CURRENT_TARGET_KEY, id);
    return id;
  }

  function getCurrentTargetJob() {
    var id = getCache(CURRENT_TARGET_KEY);
    return typeof id === 'number' ? id : null;
  }

  // 目标岗位列表 -> {targetJobs: [], total}
  async function listTargetJobs() {
    var res = await request(ENDPOINTS.targetJobs, { method: 'GET' });
    if (res.error) return res;
    return {
      targetJobs: res.targetJobs || [],
      total: res.total !== undefined ? res.total : (res.targetJobs || []).length,
      trace_id: res.trace_id
    };
  }

  // 建岗 -> {targetJob, requirements[], droppedNonRequirements[]}
  // 只接受 jdText 或已确认的 jobProfile，二者都缺时后端 422（不伪造空岗位）。
  async function createTargetJob(payload) {
    payload = payload || {};
    var traceId = genTraceId();
    var body = {
      session_id: payload.session_id || getCache('sessionId') || undefined,
      jdText: payload.jdText || undefined,
      jobProfile: payload.jobProfile || undefined,
      company: payload.company || undefined,
      position: payload.position || undefined
    };
    var res = await request(ENDPOINTS.targetJobs, { method: 'POST', body: body, _traceId: traceId });
    if (res.error) return res;
    if (res.targetJob && res.targetJob.id !== undefined) setCurrentTargetJob(res.targetJob.id);
    recordHistory(
      'TargetJob',
      '目标岗位 · ' + ((res.targetJob && (res.targetJob.position || res.targetJob.company)) || '未命名'),
      getCache('sessionId') || traceId,
      'done'
    );
    return {
      targetJob: res.targetJob,
      requirements: res.requirements || [],
      droppedNonRequirements: res.droppedNonRequirements || [],
      trace_id: res.trace_id || traceId
    };
  }

  // 单个岗位（含要求 + 最近一次决策）-> {targetJob, requirements[], decision}
  async function getTargetJob(targetJobId) {
    var res = await request(ENDPOINTS.targetJobs + '/' + encodeURIComponent(String(targetJobId)), { method: 'GET' });
    if (res.error) return res;
    return {
      targetJob: res.targetJob,
      requirements: res.requirements || [],
      decision: res.decision || null,
      trace_id: res.trace_id
    };
  }

  // 完整分析 -> {target_job, requirements[], matches[], gaps[], decision, citations[], analysis{}}
  // 依据不足 3 条时后端返回 insufficient_grounds(422)，这里原样透传，不编造结论。
  async function analyseTargetJob(targetJobId, resumeText) {
    var traceId = genTraceId();
    var body = {};
    if (resumeText) body.resumeText = resumeText;
    var res = await request(
      ENDPOINTS.targetJobs + '/' + encodeURIComponent(String(targetJobId)) + '/analyse',
      { method: 'POST', body: body, _traceId: traceId }
    );
    if (res.error) return res;
    setCurrentTargetJob(targetJobId);
    setCache('targetJobAnalysis', res);
    recordHistory(
      'TargetJob',
      '岗位分析 · ' + ((res.decision && res.decision.decision) || ''),
      getCache('sessionId') || traceId,
      'done'
    );
    return res;
  }

  async function deleteTargetJob(targetJobId) {
    var res = await request(ENDPOINTS.targetJobs + '/' + encodeURIComponent(String(targetJobId)), { method: 'DELETE' });
    if (res.error) return res;
    if (getCurrentTargetJob() === parseInt(targetJobId, 10)) setCurrentTargetJob(null);
    return { deleted: res.deleted !== false, id: targetJobId, trace_id: res.trace_id };
  }

  // ============================================================
  //  行动闭环（Gap Action Plan）
  //  "补齐证据，然后复测" —— 缺口翻成可执行、可验证的行动
  // ============================================================

  // 行动清单（含所属缺口的优先级与岗位），P0 优先
  async function listActions(status) {
    var endpoint = ENDPOINTS.actions;
    if (status) endpoint += '?status=' + encodeURIComponent(String(status));
    var res = await request(endpoint, { method: 'GET' });
    if (res.error) return res;
    return {
      actions: res.actions || [],
      total: res.total !== undefined ? res.total : (res.actions || []).length,
      trace_id: res.trace_id
    };
  }

  // 按岗位未解决缺口整体铺开（幂等）-> {created[], existing[], skipped[]}
  async function planActionsForTarget(targetJobId) {
    var res = await request(ENDPOINTS.actions, {
      method: 'POST',
      body: { targetJobId: parseInt(targetJobId, 10) }
    });
    if (res.error) return res;
    return {
      targetJobId: res.targetJobId,
      created: res.created || [],
      existing: res.existing || [],
      skipped: res.skipped || [],
      createdCount: res.createdCount !== undefined ? res.createdCount : (res.created || []).length,
      existingCount: res.existingCount !== undefined ? res.existingCount : (res.existing || []).length,
      trace_id: res.trace_id
    };
  }

  // 单条缺口开单 -> {action, opened}
  async function openAction(gapId) {
    var res = await request(ENDPOINTS.actions, {
      method: 'POST',
      body: { gapId: parseInt(gapId, 10) }
    });
    if (res.error) return res;
    return { action: res.action, opened: res.opened === true, trace_id: res.trace_id };
  }

  async function getAction(actionId) {
    var res = await request(ENDPOINTS.actions + '/' + encodeURIComponent(String(actionId)), { method: 'GET' });
    if (res.error) return res;
    return { action: res.action, trace_id: res.trace_id };
  }

  // 状态推进：start（todo→doing）/ complete（doing→done，可带成果物说明）
  // / outcome（done 后记录"做完发生了什么"）/ drop（→dropped）
  function advanceAction(actionId, verb, body) {
    return request(ENDPOINTS.actions + '/' + encodeURIComponent(String(actionId)) + '/' + verb, {
      method: 'POST',
      body: body || {}
    }).then(function (res) {
      if (res.error) return res;
      return { action: res.action, trace_id: res.trace_id };
    });
  }

  function startAction(actionId) { return advanceAction(actionId, 'start'); }
  function completeAction(actionId, artifact) { return advanceAction(actionId, 'complete', artifact ? { artifact: artifact } : {}); }
  function recordActionOutcome(actionId, outcome) { return advanceAction(actionId, 'outcome', { outcome: outcome }); }
  function dropAction(actionId) { return advanceAction(actionId, 'drop'); }

  async function deleteAction(actionId) {
    var res = await request(ENDPOINTS.actions + '/' + encodeURIComponent(String(actionId)), { method: 'DELETE' });
    if (res.error) return res;
    return { deleted: res.deleted !== false, id: actionId, trace_id: res.trace_id };
  }

  // ============================================================
  //  职业证据档案（Career Evidence）
  //  D8 方案 A：模型只产候选（pending），用户确认后才成为可信事实
  // ============================================================

  async function getProfile() {
    var res = await request(ENDPOINTS.profile, { method: 'GET' });
    if (res.error) return res;
    return res;
  }

  // ── 带进度上传（XHR onprogress）─────────────────────────
  function uploadWithXhr(endpoint, file, onProgress, traceId) {
    return new Promise(function (resolve) {
      var timedOut = false;
      try {
        var xhr = new XMLHttpRequest();
        xhr.open('POST', API_BASE + endpoint, true);
        if (endpoint !== ENDPOINTS.consent) {
          var consentToken = getCache('consentToken');
          if (consentToken) xhr.setRequestHeader('X-Consent-Token', consentToken);
        }
        var guestToken = getCache('guestToken');
        if (guestToken) xhr.setRequestHeader('X-Guest-Token', guestToken);
        xhr.setRequestHeader('X-Trace-Id', traceId);
        if (typeof onProgress === 'function' && xhr.upload) {
          xhr.upload.addEventListener('progress', function (ev) {
            if (ev.lengthComputable) {
              onProgress({ loaded: ev.loaded, total: ev.total, percent: Math.round(ev.loaded / ev.total * 100) });
            }
          });
        }
        var timer = setTimeout(function () {
          timedOut = true;
          try { xhr.abort(); } catch (e) { /* ignore */ }
          console.warn('[DataBridge] 上传超时 (' + TIMEOUT_MS + 'ms): ' + endpoint);
          resolve({ error: 'timeout', message: '上传超时，请检查网络后重试', trace_id: traceId, degraded: true });
        }, TIMEOUT_MS);
        xhr.onload = function () {
          clearTimeout(timer);
          var json = {};
          try { json = JSON.parse(xhr.responseText || '{}'); } catch (e) { /* ignore */ }
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(json);
          } else {
            resolve({
              error: json.error || 'http_' + xhr.status,
              message: json.message || ('服务器返回 ' + xhr.status),
              trace_id: json.trace_id || traceId,
              degraded: true
            });
          }
        };
        xhr.onerror = function () {
          clearTimeout(timer);
          if (timedOut) return;
          console.warn('[DataBridge] 上传失败: ' + endpoint);
          resolve({ error: 'network', message: '网络错误，请稍后重试', trace_id: traceId, degraded: true });
        };
        xhr.onabort = function () {
          clearTimeout(timer);
          if (timedOut) return;
          resolve({ error: 'network', message: '上传已中断', trace_id: traceId, degraded: true });
        };
        var formData = new FormData();
        formData.append('file', file);
        xhr.send(formData);
      } catch (err) {
        resolve({ error: 'network', message: '上传失败：' + ((err && err.message) || '未知错误'), trace_id: traceId, degraded: true });
      }
    });
  }

  // 上传简历（带进度）-> {resumeText, resumeProfile, trace_id}
  async function uploadResumeWithProgress(file, onProgress) {
    var traceId = genTraceId();
    var res = await uploadWithXhr(ENDPOINTS.uploadResume, file, onProgress, traceId);
    if (!res.error) {
      setCache('resumeText', res.resumeText);
      setCache('resumeProfile', res.resumeProfile);
      setCache('sessionId', res.session_id || traceId);
      return { resumeText: res.resumeText, resumeProfile: res.resumeProfile, trace_id: res.trace_id || traceId, session_id: res.session_id || traceId };
    }
    if (!isDemoMode()) return res;
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

  // ============================================================
  //  F3: 面试
  // ============================================================
  // ============================================================
  //  F3: 面试
  // ============================================================

  // 开始面试 -> {session_id, firstQuestion, targets, questionPlan, trace_id}
  // 传 targetJobId 时出题顺序直接来自该岗位的未解决缺口（P0 → P1 → P2），
  // 这是 DoD #11「按 Gap 定向出题」的接通点。未指定则回退到当前目标岗位。
  async function startInterview(jobProfile, resumeProfile, matchGaps, targetJobId) {
    var traceId = genTraceId();
    var sessionId = getCache('sessionId') || traceId;
    jobProfile = jobProfile && Object.keys(jobProfile).length ? jobProfile : (getCache('jobProfile') || {});
    resumeProfile = resumeProfile && Object.keys(resumeProfile).length ? resumeProfile : (getCache('resumeProfile') || {});
    var resolvedTarget = targetJobId !== undefined && targetJobId !== null
      ? parseInt(targetJobId, 10)
      : getCurrentTargetJob();
    if (!isFinite(resolvedTarget)) resolvedTarget = null;
    var body = {
      session_id: sessionId,
      jobProfile: jobProfile,
      resumeProfile: resumeProfile,
      matchGaps: Array.isArray(matchGaps) ? matchGaps : []
    };
    if (resolvedTarget !== null) body.targetJobId = resolvedTarget;
    var res = await request(ENDPOINTS.startInterview, {
      body: body,
      _traceId: traceId
    });

    if (!res.error) {
      setCache('sessionId', res.session_id);
      setCache('firstQuestion', res.firstQuestion);
      if (res.targetJobId !== undefined) setCurrentTargetJob(res.targetJobId);
      return {
        session_id: res.session_id,
        firstQuestion: res.firstQuestion,
        targets: res.targets || [],
        questionPlan: res.questionPlan || null,
        targetJobId: res.targetJobId !== undefined ? res.targetJobId : resolvedTarget,
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
        i_subscores: res.i_subscores || {},
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
      body: {
        accepted: true,
        consent_version: '1',
        guest_token: getCache('guestToken') || ''
      },
      _traceId: traceId
    });

    if (!res.error) {
      if (res.consent_token) setCache('consentToken', res.consent_token);
      if (res.guest_token) setCache('guestToken', res.guest_token);
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
    // F1 简历
    uploadResume: uploadResume,
    uploadResumeWithProgress: uploadResumeWithProgress,
    diagnoseResume: diagnoseResume,

    // 目标岗位工作区
    listTargetJobs: listTargetJobs,
    createTargetJob: createTargetJob,
    getTargetJob: getTargetJob,
    analyseTargetJob: analyseTargetJob,
    deleteTargetJob: deleteTargetJob,
    setCurrentTargetJob: setCurrentTargetJob,
    getCurrentTargetJob: getCurrentTargetJob,

    // 行动闭环
    listActions: listActions,
    planActionsForTarget: planActionsForTarget,
    openAction: openAction,
    getAction: getAction,
    startAction: startAction,
    completeAction: completeAction,
    recordActionOutcome: recordActionOutcome,
    dropAction: dropAction,
    deleteAction: deleteAction,

    // 职业证据档案
    getProfile: getProfile,

    // F3 面试
    startInterview: startInterview,
    submitAnswer: submitAnswer,
    endInterview: endInterview,

    // F4 能力报告
    getAbility: getAbility,

    // 隐私
    submitConsent: submitConsent,
    deleteAllData: deleteAllData,

    // F5 投递
    generateCoverLetter: generateCoverLetter,
    saveApplication: saveApplication,
    listApplications: listApplications,
    deleteApplication: deleteApplication,

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
    getSessionContext: function () {
      return {
        sessionId: getCache('sessionId'),
        consentToken: getCache('consentToken'),
        guestToken: getCache('guestToken')
      };
    },

    // 缓存工具
    _cache: { get: getCache, set: setCache },

    // 契约适配器（供离线验收；不修改后端 source_spans 结构）
    _normalizeResumeProfile: normalizeResumeProfile,

    // 端点配置（便于调试）
    _endpoints: ENDPOINTS
  };
})();
