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

test('面试页不得自动代用户同意，错误页提供明确续接入口', () => {
  const js = read('public/js/interview-practice.js');
  const html = read('public/pages/interview-practice.html');
  assert.doesNotMatch(js, /DB\.submitConsent\(/);
  assert.match(js, /if \(!consentToken\(\)\)/);
  assert.match(html, /href="target-job\.html"[^>]*>目标岗位页<\/a>/);
  assert.match(read('public/pages/target-job.html'), /id="tjConsentCheck" type="checkbox"/);
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
