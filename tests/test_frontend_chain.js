/* test_frontend_chain.js · 前端数据链集成测试（F1 -> F2 全流程 + 降级 + 删除）
 *
 * 读取 public/js/app.js 与 data-bridge.js，在 VM 中模拟浏览器环境：
 *  - 正常路径：同意 -> 上传简历 -> 诊断 -> 上传 JD -> 解析 -> 匹配
 *  - 降级路径：服务不可用时生产态明确报错、演示态才允许合成数据
 *  - 删除路径：清除本地会话缓存并标记删除
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
      matchResult: { score_M: 60 }
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

function routeResponse(url) {
  if (url.endsWith('/api/wf01/consent')) {
    return { status: 'ACCEPTED', consent_token: 'tok-123', expires_in_seconds: 120 };
  }
  if (url.endsWith('/api/wf01/upload')) {
    return { resumeText: '我的简历正文，长度满足诊断要求。', resumeProfile: null };
  }
  if (url.endsWith('/api/wf02/diagnose')) {
    return { resumeProfile: { score_R: 75.5, subscores: {} }, score_R: 75.5, diagnosis_mode: 'model' };
  }
  if (url.endsWith('/api/wf03/upload')) {
    return { jdText: '岗位职责：负责后端开发。任职要求：熟悉 Python。' };
  }
  if (url.endsWith('/api/wf03/jd')) {
    return { jobProfile: { requirements: [{ id: 'J1', type: 'hard', text: '熟悉 Python' }], user_confirmed: false } };
  }
  if (url.endsWith('/api/wf03/match')) {
    return { score_M: 60, subscores: {}, requirements: [], gaps: [], match_notice: '规则匹配' };
  }
  return { error: 'not_found' };
}

test('生产态默认空态且演示数据被阻断', () => {
  assert.equal(loadApp('').getState(), 'empty');
  assert.equal(loadApp('?state=success').getState(), 'empty');
  assert.equal(loadApp('?demo=1&state=success').getState(), 'success');
});

test('F1->F2 全流程：同意令牌传递、调用顺序与缓存', async () => {
  const calls = [];
  const fetchImpl = function (url) {
    calls.push(url);
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve(routeResponse(url)); } });
  };
  const env = loadBridge('', fetchImpl, {}, 'https://api.example.test');
  const DB = env.bridge;

  const consent = await DB.submitConsent('session');
  assert.equal(consent.status, 'ACCEPTED');

  const uploaded = await DB.uploadResume({ name: 'resume.txt', size: 1024 });
  assert.ok(!uploaded.error);
  const diagnosed = await DB.diagnoseResume(uploaded.resumeText);
  assert.equal(diagnosed.score_R, 75.5);

  const jdUploaded = await DB.uploadJD({ name: 'jd.txt', size: 1024 });
  assert.ok(!jdUploaded.error);
  const parsed = await DB.submitJD(jdUploaded.jdText);
  assert.equal(parsed.jobProfile.requirements.length, 1);
  const confirmed = Object.assign({}, parsed.jobProfile, { user_confirmed: true });
  const matched = await DB.matchJD(uploaded.resumeText, confirmed);
  assert.equal(matched.matchResult.score_M, 60);

  assert.deepEqual(
    calls.map((u) => u.replace('https://api.example.test', '')),
    ['/api/wf01/consent', '/api/wf01/upload', '/api/wf02/diagnose',
     '/api/wf03/upload', '/api/wf03/jd', '/api/wf03/match']
  );
  assert.equal(JSON.parse(env.storage['cb_cache_resumeText']).data, '我的简历正文，长度满足诊断要求。');
  assert.equal(env.storage['cb_cache_jobProfile'] !== undefined, true);
  assert.equal(env.storage['cb_cache_matchResult'] !== undefined, true);
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
    { 'cb_cache_resumeText': 'x', 'cb_cache_matchResult': 'y', 'other_key': 'keep' },
    'https://api.example.test'
  );
  const result = await env.bridge.deleteAllData('session');
  assert.equal(result.status, 'LOCAL_DELETED');
  assert.equal(env.storage['cb_cache_resumeText'], undefined);
  assert.equal(env.storage['cb_cache_matchResult'], undefined);
  assert.equal(env.storage['other_key'], 'keep');
  assert.equal(env.bridge.isSessionDeleted(), true);
});
