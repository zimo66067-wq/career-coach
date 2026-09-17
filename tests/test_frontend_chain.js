/* test_frontend_chain.js · 前端数据链集成测试（F1 → 目标岗位 → 行动闭环 + 降级 + 删除）
 *
 * 读取 public/js/app.js 与 data-bridge.js，在 VM 中模拟浏览器环境：
 *  - 正常路径：同意 -> 上传简历 -> 诊断 -> 建岗 -> 分析（Decision/Gap/依据）-> 铺开行动
 *  - 降级路径：服务不可用时生产态明确报错、演示态才允许合成数据
 *  - 删除路径：清除本地会话缓存并标记删除
 *
 * Phase 6b-1 更新：链路从 `/api/wf03/{upload,jd,match}`（只产匹配分数）改为
 * `/api/target-jobs` + `/api/actions`（产 Decision / Gap / Action），
 * 与目标岗位工作区的实际接线保持一致。
 *
 * Phase 6b-2a 更新：链路补上三段"跨页认同一个岗位"的接线 ——
 *   F5 求职信带 `targetJobId`（DoD #10）、F3 面试带 `targetJobId` 并回传 `questionPlan`（DoD #11）、
 *   行动状态流转打到各自子路由。这三段共用同一个"当前目标岗位"口径。
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const appSource = fs.readFileSync(path.join(root, 'public', 'js', 'app.js'), 'utf8');
const bridgeSource = fs.readFileSync(path.join(root, 'public', 'js', 'data-bridge.js'), 'utf8');

function makeContext(search, fetchImpl, initialStorage, apiBase) {
  const storage = Object.assign({}, initialStorage || {});
  const sessionStorage = Object.assign({
    getItem: function (k) { return Object.prototype.hasOwnProperty.call(storage, k) ? storage[k] : null; },
    setItem: function (k, v) { storage[k] = String(v); },
    removeItem: function (k) { delete storage[k]; }
  }, storage);
  const context = {
    location: { search: search || '', pathname: '/pages/f1-resume.html', hash: '' },
    document: { addEventListener: function () {} },
    sessionStorage: sessionStorage,
    console: { warn: function () {}, log: function () {}, error: function () {} },
    fetch: fetchImpl || function () { return Promise.reject(new Error('offline')); },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    AbortController: class { abort() {} },
    FormData: class { append() {} },
    MOCK: {
      resumeText: '合成简历',
      resumeProfile: { score_R: 73 },
      jdText: '合成 JD'
    },
    Date: Date,
    JSON: JSON,
    Math: Math,
    Promise: Promise
  };
  context.window = context;
  if (apiBase) context.window.DUMATE_API_BASE = apiBase;
  return { context: context, storage: storage };
}

function loadApp(search) {
  const env = makeContext(search);
  vm.runInNewContext(appSource, env.context, { filename: 'app.js' });
  return env.context.APP;
}

function loadBridge(search, fetchImpl, initialStorage, apiBase) {
  const env = makeContext(search, fetchImpl, initialStorage, apiBase);
  vm.runInNewContext(appSource, env.context, { filename: 'app.js' });
  vm.runInNewContext(bridgeSource, env.context, { filename: 'data-bridge.js' });
  return { bridge: env.context.DataBridge, storage: env.storage, context: env.context };
}

function routeResponse(url, method) {
  const verb = method || 'POST';
  if (url.endsWith('/api/wf01/consent')) {
    return { status: 'ACCEPTED', consent_token: 'tok-123', guest_token: 'guest-123', expires_in_seconds: 120 };
  }
  if (url.endsWith('/api/wf01/upload')) {
    return { resumeText: '我的简历正文，长度满足诊断要求。', resumeProfile: null };
  }
  if (url.endsWith('/api/wf02/diagnose')) {
    return { resumeProfile: { score_R: 75.5, subscores: {} }, score_R: 75.5, diagnosis_mode: 'model' };
  }
  if (/\/api\/target-jobs$/.test(url)) {
    return verb === 'GET'
      ? { targetJobs: [{ id: 7, company: '示例公司', position: '后端开发工程师', status: 'open' }], total: 1 }
      : {
          targetJob: { id: 7, company: '示例公司', position: '后端开发工程师', status: 'open' },
          requirements: [{ id: 1, req_key: 'req_01', req_type: 'hard', text: '熟悉 Python', ordinal: 0 }],
          droppedNonRequirements: ['公司简介一行']
        };
  }
  if (/\/api\/target-jobs\/\d+\/analyse$/.test(url)) {
    return {
      target_job: { id: 7, company: '示例公司', position: '后端开发工程师' },
      requirements: [{
        id: 1, req_key: 'req_01', req_type: 'hard', text: '熟悉 Python', ordinal: 0,
        status: 'weak', type_label: '硬性要求', evidence: '用 Python 做过订单系统'
      }],
      matches: [{ requirement_id: 1, evidence_id: 3, match_status: 'weak' }],
      gaps: [{
        id: 11, target_job_id: 7, requirement_id: 1, gap_type: 'weak', priority: 'P1',
        reason: '只有弱证据', missing_evidence: '量化成果', action: '补一个量化数字',
        expected_artifact: '一页含 3 个量化数字的项目说明', retest: '重新分析',
        status: 'open', blocking: 0
      }],
      decision: {
        id: 5, target_job_id: 7, decision: 'STRETCH',
        rationale: { text: '关键要求强度不足。', citations: ['依据一', '依据二', '依据三'] }
      },
      citations: ['依据一', '依据二', '依据三'],
      analysis: {
        score_M: 60, match_mode: 'rule', match_notice: '规则匹配',
        insufficient_evidence: false, new_candidate_evidence: 1
      }
    };
  }
  if (/\/api\/actions\/\d+\/(start|complete|outcome|drop)$/.test(url)) {
    const verbName = url.split('/').pop();
    const next = { start: 'doing', complete: 'done', outcome: 'done', drop: 'dropped' }[verbName];
    return { action: { id: Number(url.split('/').slice(-2)[0]), gap_id: 11, status: next, task: '补一个量化数字' } };
  }
  if (url.endsWith('/api/wf07/cover-letter')) {
    return {
      candidate: '尊敬的招聘负责人：您好！我是「后端开发工程师」岗位的求职者。',
      pending_confirm: true,
      basis: 'rule',
      grounding: 'target_job+evidence',
      session_id: 'sess',
      company: '示例公司',
      position: '后端开发工程师',
      evidence: [{ id: 3, claim: '用 Python 做过订单系统' }],
      requirements: [{ id: 1, text: '熟悉 Python', priority: 'P0' }],
      gaps: [{ id: 11, priority: 'P1' }],
      notice: '正文中的经历只来自你已确认的 1 条职业证据，未确认的候选证据未被引用。'
    };
  }
  if (url.endsWith('/api/wf04/start')) {
    return {
      session_id: 'iv_abc',
      firstQuestion: '请讲讲你用 Python 做过的订单系统。',
      targets: [],
      questionPlan: [{ kind: 'p1_gap', gap_id: 11, priority: 'P1' }],
      targetJobId: 7
    };
  }
  if (url.endsWith('/api/actions')) {
    return verb === 'GET'
      ? { actions: [{ id: 21, gap_id: 11, task: '补一个量化数字', status: 'todo', gap_priority: 'P1' }], total: 1 }
      : {
          targetJobId: 7,
          created: [{ id: 21, gap_id: 11, status: 'todo' }],
          existing: [], skipped: [], createdCount: 1, existingCount: 0
        };
  }
  return { error: 'not_found' };
}

test('生产态默认空态且演示数据被阻断', () => {
  assert.equal(loadApp('').getState(), 'empty');
  assert.equal(loadApp('?state=success').getState(), 'empty');
  assert.equal(loadApp('?demo=1&state=success').getState(), 'success');
});

test('F1 → 目标岗位 → 行动闭环 全流程：同意令牌传递、调用顺序与缓存', async () => {
  const calls = [];
  const fetchImpl = function (url, opts) {
    calls.push({ url: url, opts: opts });
    return Promise.resolve({
      ok: true,
      json: function () { return Promise.resolve(routeResponse(url, opts && opts.method)); }
    });
  };
  const env = loadBridge('', fetchImpl, {}, 'https://api.example.test');
  const DB = env.bridge;

  const consent = await DB.submitConsent('session');
  assert.equal(consent.status, 'ACCEPTED');

  const uploaded = await DB.uploadResume({ name: 'resume.txt', size: 1024 });
  assert.ok(!uploaded.error);
  const diagnosed = await DB.diagnoseResume(uploaded.resumeText);
  assert.equal(diagnosed.score_R, 75.5);

  // 建岗：JD 以文本提交，拆出可核对的要求
  const created = await DB.createTargetJob({
    jdText: '岗位职责：负责后端开发。任职要求：熟悉 Python。',
    company: '示例公司'
  });
  assert.equal(created.targetJob.id, 7);
  assert.equal(created.requirements.length, 1);
  assert.deepEqual(created.droppedNonRequirements, ['公司简介一行']);
  assert.equal(DB.getCurrentTargetJob(), 7, '建岗后当前目标岗位必须被记住（F5/F3 共用这个口径）');

  // 分析：产出 Decision / Gap / 可回查依据
  const analysed = await DB.analyseTargetJob(7);
  assert.equal(analysed.decision.decision, 'STRETCH');
  assert.equal(analysed.gaps.length, 1);
  assert.equal(analysed.gaps[0].expected_artifact.length > 0, true);
  assert.equal(analysed.citations.length, 3, 'DoD #9：至少 3 条依据');
  assert.equal(analysed.analysis.score_M, 60);

  // 行动闭环：把未解决缺口铺成行动（幂等），再走一次状态流转
  const listed = await DB.listActions();
  assert.equal(listed.total, 1);
  const planned = await DB.planActionsForTarget(7);
  assert.equal(planned.createdCount, 1);
  assert.equal(planned.existingCount, 0);

  const started = await DB.startAction(21);
  assert.equal(started.action.status, 'doing');
  const completed = await DB.completeAction(21, '一页含 3 个量化数字的项目说明');
  assert.equal(completed.action.status, 'done');
  const outcome = await DB.recordActionOutcome(21, '面试中被追问时答得更具体了');
  assert.equal(outcome.action.status, 'done');

  assert.deepEqual(
    calls.map((call) => call.url.replace('https://api.example.test', '')),
    ['/api/wf01/consent', '/api/wf01/upload', '/api/wf02/diagnose',
     '/api/target-jobs', '/api/target-jobs/7/analyse', '/api/actions', '/api/actions',
     '/api/actions/21/start', '/api/actions/21/complete', '/api/actions/21/outcome']
  );
  assert.equal(JSON.parse(env.storage['cb_cache_resumeText']).data, '我的简历正文，长度满足诊断要求。');
  assert.equal(JSON.parse(env.storage['cb_cache_currentTargetJobId']).data, 7);
  assert.equal(env.storage['cb_cache_targetJobAnalysis'] !== undefined, true);
  assert.equal(DB.getSessionContext().guestToken, 'guest-123');
  assert.ok(calls.slice(1).every((call) => call.opts.credentials === 'include'));
  assert.ok(calls.slice(1).every((call) => call.opts.headers['X-Guest-Token'] === 'guest-123'));
  assert.equal(DB.getMockData('resumeProfile'), null, '生产态禁止读取演示数据');
});

test('降级路径：生产态明确报错，演示态才返回合成数据', async () => {
  const offline = loadBridge('', null, {}, 'https://api.example.test');
  const failed = await offline.bridge.diagnoseResume('候选文本，用于验证服务不可用时不伪造结果。');
  assert.equal(failed.error, 'service_unavailable');
  assert.equal(offline.bridge.getMockData('resumeProfile'), null);

  const demo = loadBridge('?demo=1', null, {}, 'https://api.example.test');
  const degraded = await demo.bridge.diagnoseResume('候选文本，用于验证演示模式降级数据。');
  assert.equal(degraded.demo_data, true);
  assert.equal(degraded.degraded, true);
});

test('删除路径：服务端不可用时代理清除本地缓存并标记', async () => {
  const fetchImpl = function () {
    return Promise.resolve({
      ok: false,
      json: function () { return Promise.resolve({ error: 'workflow_not_configured' }); }
    });
  };
  const env = loadBridge(
    '',
    fetchImpl,
    { 'cb_cache_resumeText': 'x', 'cb_cache_targetJobAnalysis': 'y', 'other_key': 'keep' },
    'https://api.example.test'
  );
  const result = await env.bridge.deleteAllData('session');
  assert.equal(result.status, 'LOCAL_DELETED');
  assert.equal(env.storage['cb_cache_resumeText'], undefined);
  assert.equal(env.storage['cb_cache_targetJobAnalysis'], undefined);
  assert.equal(env.storage['other_key'], 'keep');
  assert.equal(env.bridge.isSessionDeleted(), true);
});

test('求职信接当前目标岗位：请求带 targetJobId，响应回带引用依据（DoD #10）', async () => {
  const calls = [];
  const fetchImpl = function (url, opts) {
    calls.push({ url: url, opts: opts });
    return Promise.resolve({
      ok: true,
      json: function () { return Promise.resolve(routeResponse(url, opts && opts.method)); }
    });
  };
  const env = loadBridge('', fetchImpl, {}, 'https://api.example.test');
  const DB = env.bridge;

  await DB.createTargetJob({ jdText: '任职要求：熟悉 Python。', company: '示例公司' });
  assert.equal(DB.getCurrentTargetJob(), 7);

  // 不显式传 targetJobId：必须回退到"当前目标岗位"，否则 F5 会与 F3 / F4 各说各话
  const letter = await DB.generateCoverLetter('sess', '示例公司', '后端开发工程师');
  const body = JSON.parse(calls[calls.length - 1].opts.body);
  assert.equal(body.targetJobId, 7, 'F5 必须把当前目标岗位递给 /api/wf07/cover-letter');
  assert.equal(letter.grounding, 'target_job+evidence');
  assert.equal(letter.evidence.length, 1, '响应必须带回"引用了哪些证据"');
  assert.equal(letter.requirements[0].priority, 'P0');
  assert.ok(letter.notice.length > 0, '必须回带依据说明，页面不能只给一封光秃秃的信');
});

test('面试按目标岗位出题：startInterview 带 targetJobId 并回传 questionPlan（DoD #11）', async () => {
  const calls = [];
  const fetchImpl = function (url, opts) {
    calls.push({ url: url, opts: opts });
    return Promise.resolve({
      ok: true,
      json: function () { return Promise.resolve(routeResponse(url, opts && opts.method)); }
    });
  };
  const env = loadBridge('', fetchImpl, {}, 'https://api.example.test');
  const DB = env.bridge;

  await DB.createTargetJob({ jdText: '任职要求：熟悉 Python。', company: '示例公司' });
  const started = await DB.startInterview({}, {}, [], DB.getCurrentTargetJob());
  const body = JSON.parse(calls[calls.length - 1].opts.body);
  assert.equal(body.targetJobId, 7, 'F3 必须把当前目标岗位递给 /api/wf04/start');
  assert.equal(started.questionPlan.length, 1);
  assert.equal(started.questionPlan[0].kind, 'p1_gap');
  assert.equal(started.questionPlan[0].priority, 'P1');
});

test('行动状态流转：start / complete / outcome / drop 打到各自子路由', async () => {
  const calls = [];
  const fetchImpl = function (url, opts) {
    calls.push({ url: url, opts: opts });
    return Promise.resolve({
      ok: true,
      json: function () { return Promise.resolve(routeResponse(url, opts && opts.method)); }
    });
  };
  const env = loadBridge('', fetchImpl, {}, 'https://api.example.test');
  const DB = env.bridge;

  await DB.startAction(21);
  await DB.completeAction(21, '一页含 3 个量化数字的项目说明');
  await DB.recordActionOutcome(21, '面试中被追问时答得更具体了');
  await DB.dropAction(22);

  assert.deepEqual(
    calls.map((call) => call.url.replace('https://api.example.test', '')),
    ['/api/actions/21/start', '/api/actions/21/complete',
     '/api/actions/21/outcome', '/api/actions/22/drop']
  );
  assert.equal(JSON.parse(calls[1].opts.body).artifact, '一页含 3 个量化数字的项目说明');
  assert.equal(JSON.parse(calls[2].opts.body).outcome, '面试中被追问时答得更具体了');
});
