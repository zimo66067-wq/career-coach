const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

test('目标岗位页同意过期后必须由用户勾选，且不自动重发原操作', async () => {
  const elements = new Map();
  function el(id) {
    const node = {
      id, checked: false, textContent: '', className: '', innerHTML: '',
      handlers: {}, classes: new Set(['zy-hidden']),
      addEventListener(event, handler) { this.handlers[event] = handler; },
      classList: {
        add(name) { node.classes.add(name); },
        remove(name) { node.classes.delete(name); }
      }
    };
    elements.set(id, node);
    return node;
  }
  for (const id of ['tjConsentRenew', 'tjConsentCheck', 'tjConsentSubmit',
    'tjConsentStatus', 'tjErrorText', 'tjMsg', 'tjJobs', 'tjCreate',
    'tjAnalyse', 'tjPlanActions', 'tjRetry']) el(id);
  let listCalls = 0;
  let consentCalls = 0;
  let createCalls = 0;
  const states = [];
  const bridge = {
    listTargetJobs: async () => ++listCalls === 1
      ? { error: 'consent_expired', message: '同意记录已过期' }
      : { targetJobs: [] },
    submitConsent: async () => { consentCalls++; return { status: 'ACCEPTED' }; },
    createTargetJob: async () => { createCalls++; return {}; }
  };
  const context = {
    window: { DataBridge: bridge, APP: { isDemoMode: () => false, setState: (state) => states.push(state) } },
    document: { readyState: 'complete', getElementById: (id) => elements.get(id) || null },
    console
  };
  vm.createContext(context);
  vm.runInContext(read('public/js/target-job.js'), context);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(elements.get('tjConsentRenew').classes.has('zy-hidden'), false);
  elements.get('tjConsentSubmit').handlers.click();
  assert.equal(consentCalls, 0);
  assert.match(elements.get('tjConsentStatus').textContent, /勾选/);
  elements.get('tjConsentCheck').checked = true;
  elements.get('tjConsentSubmit').handlers.click();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(consentCalls, 1);
  assert.equal(listCalls, 2);
  assert.equal(createCalls, 0);
  assert.equal(elements.get('tjConsentRenew').classes.has('zy-hidden'), true);
  assert.ok(states.includes('empty'));
});

test('面试入口提前引导到简历页确认，不在面试错误态要求补同意', () => {
  const js = read('public/js/interview-practice.js');
  const html = read('public/pages/interview-practice.html');
  const app = read('public/js/app.js');
  assert.doesNotMatch(js, /DB\.submitConsent\(/);
  assert.ok(/ensureInterviewConsent\(\)/.test(js));
  assert.ok(/pauseForConsent\(turn\.answer\)/.test(js));
  assert.ok(/resume-evidence\.html\?continue=interview/.test(app));
  assert.ok(!/目标岗位页<\/a>.*重新确认/.test(html));
});

test('简历入口先呈现完整说明，样例体验不代勾选', () => {
  const html = read('public/pages/resume-evidence.html');
  const quick = read('public/js/quick-demo.js');
  const upload = read('public/js/resume-upload.js');
  assert.ok(html.indexOf('id="data-consent"') < html.indexOf('id="resumeUploadCard"'));
  assert.ok(/id="resumeUploadCard" hidden/.test(html));
  assert.ok(/id="resumeConsent" type="checkbox"/.test(html));
  assert.ok(/id="confirmResumeConsent"/.test(html));
  assert.ok(/面试回答/.test(html));
  assert.ok(!/consent\.checked\s*=\s*true/.test(quick));
  assert.ok(/bridge\.hasCurrentConsent\(\)/.test(quick));
  assert.ok(/consentCheckbox\.checked/.test(upload));
});

test('导航与直达面试都先检查有效同意', () => {
  const handlers = {};
  let allowed = false;
  const location = { pathname: '/pages/target-job.html', search: '', hash: '', href: '', replace(url) { this.href = url; } };
  const document = {
    body: { getAttribute: () => 'target', setAttribute() {}, hasAttribute: () => false },
    querySelector: () => null,
    addEventListener(name, fn) { handlers[name] = fn; }
  };
  const context = { window: { DataBridge: { hasCurrentConsent: () => allowed } }, document, location };
  vm.createContext(context);
  vm.runInContext(read('public/js/app.js'), context);
  handlers.DOMContentLoaded();
  let prevented = false;
  handlers.click({
    target: { closest: () => ({ getAttribute: () => 'interview-practice.html' }) },
    preventDefault() { prevented = true; }
  });
  assert.equal(prevented, true);
  assert.equal(location.href, 'resume-evidence.html?continue=interview#data-consent');
  allowed = true;
  location.href = '';
  prevented = false;
  handlers.click({
    target: { closest: () => ({ getAttribute: () => 'interview-practice.html' }) },
    preventDefault() { prevented = true; }
  });
  assert.equal(prevented, false);
  assert.equal(location.href, '');

  allowed = false;
  location.pathname = '/pages/interview-practice.html';
  document.body.getAttribute = () => 'interview';
  handlers.DOMContentLoaded();
  assert.equal(location.href, 'resume-evidence.html?continue=interview#data-consent');
  location.href = '';
  handlers['zy:auth']();
  assert.equal(location.href, 'resume-evidence.html?continue=interview#data-consent');
});

test('只有服务端签发且未过期的同意令牌可通过前置检查', async () => {
  const storage = new Map();
  const context = {
    sessionStorage: {
      getItem: (key) => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: (key) => storage.delete(key)
    },
    fetch: async () => ({ ok: true, json: async () => ({
      status: 'ACCEPTED', consent_token: 'signed-test-token',
      guest_token: 'guest-test-token', expires_in_seconds: 1800
    }) }),
    FormData: class {}, AbortController: class { abort() {} },
    setTimeout, clearTimeout, Date, Math, JSON, Promise, console,
    location: { search: '', pathname: '/pages/resume-evidence.html' }
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(read('public/js/data-bridge.js'), context);
  const bridge = context.DataBridge;
  assert.equal(bridge.hasCurrentConsent(), false);
  const consent = await bridge.submitConsent('career_workflow');
  assert.equal(consent.status, 'ACCEPTED');
  assert.equal(bridge.hasCurrentConsent(), true);
  bridge._cache.set('consentExpiresAt', Date.now() - 1);
  assert.equal(bridge.hasCurrentConsent(), false);
  bridge.clearConsent();
  assert.equal(bridge._cache.get('consentToken'), null);
});

test('服务端拒绝同意后不能用缓存问题或报告绕过前置检查', async () => {
  const storage = new Map();
  const context = {
    sessionStorage: {
      getItem: (key) => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: (key) => storage.delete(key)
    },
    fetch: async () => ({ ok: false, status: 401,
      json: async () => ({ error: 'consent_expired', message: '请重新确认' }) }),
    FormData: class {}, AbortController: class { abort() {} },
    setTimeout, clearTimeout, Date, Math, JSON, Promise, console,
    location: { search: '', pathname: '/pages/interview-practice.html' }
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(read('public/js/data-bridge.js'), context);
  const bridge = context.DataBridge;
  bridge._cache.set('sessionId', 'old-session');
  bridge._cache.set('firstQuestion', '旧题目');
  bridge._cache.set('interviewReport', { report: '旧报告' });
  const started = await bridge.startInterview({}, {}, []);
  const ended = await bridge.endInterview('old-session');
  assert.equal(started.error, 'consent_expired');
  assert.equal(ended.error, 'consent_expired');
});

test('简历页未勾选不能继续；本人确认成功后才返回模拟面试', async () => {
  const elements = new Map();
  function element(id) {
    const node = {
      id, hidden: false, checked: false, disabled: false, textContent: '',
      handlers: {}, addEventListener(name, fn) { this.handlers[name] = fn; },
      classList: { add() {}, remove() {}, toggle() {} }
    };
    elements.set(id, node);
    return node;
  }
  for (const id of ['resumeUploadCard', 'resumeDropzone', 'resumeFileInput',
    'chooseResumeFile', 'startResumeDiagnosis', 'resumeUploadStatus',
    'resumeConsent', 'data-consent', 'confirmResumeConsent', 'resumeConsentStatus']) element(id);
  let init;
  let valid = false;
  let submitted = 0;
  const location = { search: '?continue=interview', href: '', hostname: 'local.test' };
  const context = {
    window: { location, DataBridge: {
      hasCurrentConsent: () => valid,
      submitConsent: async () => { submitted++; valid = true; return { status: 'ACCEPTED' }; }
    } },
    location,
    document: {
      getElementById: (id) => elements.get(id) || null,
      addEventListener(name, fn) { if (name === 'DOMContentLoaded') init = fn; }
    },
    console
  };
  vm.createContext(context);
  vm.runInContext(read('public/js/resume-upload.js'), context);
  init();
  assert.equal(elements.get('resumeUploadCard').hidden, true);
  assert.equal(elements.get('data-consent').hidden, false);
  await elements.get('confirmResumeConsent').handlers.click();
  assert.equal(submitted, 0);
  assert.match(elements.get('resumeConsentStatus').textContent, /自行勾选/);
  elements.get('resumeConsent').checked = true;
  await elements.get('confirmResumeConsent').handlers.click();
  assert.equal(submitted, 1);
  assert.equal(location.href, 'interview-practice.html');
});

test('面试完成后的 report 状态必须实际显示报告视图', () => {
  const css = read('public/css/states.css');
  const html = read('public/pages/interview-practice.html');
  const js = read('public/js/interview-practice.js');
  assert.match(html, /data-state-view="report"/);
  assert.match(js, /setView\("report"\)/);
  assert.match(css, /body\[data-state="report"\] \[data-state-view="report"\]/);
});

test('行动页提供真实 WF-05 报告入口并替换演示分数', () => {
  const html = read('public/pages/action-loop.html');
  const js = read('public/js/action-loop.js');
  assert.match(html, /id="alGenerateAbilityBtn"/);
  assert.match(js, /DB\.getAbility\(sessionId\)/);
  assert.match(html, /id="alScoreR"/);
  assert.match(html, /id="alScoreM"/);
  assert.match(html, /id="alScoreI"/);
  assert.doesNotMatch(html, /R 73\.00 × 0\.25/);
});

test('能力报告按钮只接受完整后端报告，空响应不能显示成功', async () => {
  const elements = new Map();
  for (const id of ['alAbilityMsg', 'c0num', 'alScoreR', 'alScoreM', 'alScoreI']) {
    elements.set(id, { textContent: '' });
  }
  const states = [];
  const rendered = [];
  let response = { ability: {} };
  const context = {
    window: {
      DataBridge: { _cache: { get: () => 'synthetic-session' }, getAbility: async () => response },
      APP: { setState: (value) => states.push(value) },
      RADAR: { mount: (...args) => rendered.push(args) },
      renderPlan: (...args) => rendered.push(args)
    },
    document: { readyState: 'loading', getElementById: (id) => elements.get(id) || null,
      addEventListener() {} },
    Promise, Number, Array, console
  };
  vm.createContext(context);
  vm.runInContext(read('public/js/action-loop.js'), context);
  await context.window.ACTION_LOOP.generateAbility();
  assert.equal(states.at(-1), 'error');
  assert.equal(rendered.length, 0);
  response = { ability: { baseline: 61.25, resume_score: 70, match_score: 55,
    interview_score: 60, dimensions: Array.from({ length: 6 }, (_, i) => ({ key: String(i), name: '维度', score: 60 })),
    plan: Array.from({ length: 7 }, (_, i) => ({ day: i + 1, focus: '练习', minutes: 30, artifact: '记录' })) } };
  await context.window.ACTION_LOOP.generateAbility();
  assert.equal(states.at(-1), 'success');
  assert.equal(elements.get('c0num').textContent, '61.25');
  assert.equal(rendered.length, 2);
});

test('行动进度拒绝空对象、空数组与空报告', () => {
  const html = read('public/pages/action-loop.html');
  assert.match(html, /if \(!value \|\| typeof value !== "object" \|\| Array\.isArray\(value\)/);
  assert.match(html, /value\.report\.trim\(\)\.length > 0/);
  assert.match(html, /validScore\(value\.analysis\.score_M\)/);
});

test('岗位结论展示可读理由，不把 rationale_json 原文显示给用户', () => {
  const js = read('public/js/target-job.js');
  assert.match(js, /detail\.rationale \|\| detail\.text/);
  assert.doesNotMatch(js, /: \(decision\.rationale_json \|\| ""\)/);
});

test('能力报告缓存不得跨会话使用，空成功响应不得写历史', async () => {
  const storage = new Map();
  let payload = { ability: {} };
  const history = [];
  const context = {
    window: { APP: { isDemoMode: () => false }, ZY_ACCOUNT: { addHistory: (entry) => history.push(entry) } },
    sessionStorage: {
      getItem: (key) => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: (key) => storage.delete(key)
    },
    fetch: async () => ({ ok: true, json: async () => payload }),
    FormData: class { append() {} }, AbortController: class { abort() {} },
    setTimeout, clearTimeout, Date, Math, JSON, Promise, console
  };
  vm.createContext(context);
  vm.runInContext(read('public/js/data-bridge.js'), context);
  const bridge = context.window.DataBridge;
  bridge._cache.set('ability', { baseline: 88 });
  bridge._cache.set('abilitySessionId', 'old-session');
  let result = await bridge.getAbility('new-session');
  assert.equal(result.error, 'service_unavailable');
  assert.equal(history.length, 0);
  payload = { error: 'temporary_failure' };
  result = await bridge.getAbility('new-session');
  assert.equal(result.error, 'service_unavailable');
  assert.equal(result.degraded_reason, 'temporary_failure');
  assert.equal(history.length, 0);
  result = await bridge.getAbility('old-session');
  assert.equal(result.degraded_reason, 'cached');
  bridge._cache.set('diagnoseResult', { score_R: 80 });
  bridge._cache.set('interviewReport', { score_I: 80 });
  payload = { resumeText: '新的合成简历', resumeProfile: {}, session_id: 'fresh-session' };
  await bridge.uploadResume({});
  assert.equal(bridge._cache.get('diagnoseResult'), null);
  assert.equal(bridge._cache.get('interviewReport'), null);
  assert.equal(bridge._cache.get('ability'), null);
});
