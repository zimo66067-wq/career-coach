/* test_phase4_contract.js
 *
 * Phase 4 frontend contract checks:
 *  - interview-practice.html + interview-practice.js (SSE follow-up stream, session snapshot)
 *  - resume-evidence.html + optimizer.js (rewrite preview modal, apply flow)
 * All scripts are also smoke-loaded in a stub DOM context to catch load-time crashes.
 *
 * 2026-09-13：kb.html / kb.js 的独立「面经知识库」产品页已下线（Phase 1），
 * 相应契约一并移除；题库数据保留为 Interview Engine 的内部数据源（domain/knowledge.py）。
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(root, 'public', rel), 'utf8');

function elementStub() {
  const el = {
    addEventListener: function () {},
    removeEventListener: function () {},
    setAttribute: function () {},
    getAttribute: function () { return null; },
    appendChild: function () {},
    removeChild: function () {},
    querySelector: function () { return elementStub(); },
    querySelectorAll: function () { return []; },
    closest: function () { return null; },
    focus: function () {},
    click: function () {},
    style: {},
    classList: { add: function () {}, remove: function () {}, toggle: function () {}, contains: function () { return false; } },
    textContent: '',
    value: '',
    innerHTML: '',
    disabled: false,
    checked: false
  };
  return el;
}

function makeContext() {
  const storage = {
    cb_cache_consentToken: JSON.stringify({ data: 't-consent', ts: Date.now() })
  };
  const sessionStorage = {
    getItem: function (k) { return Object.prototype.hasOwnProperty.call(storage, k) ? storage[k] : null; },
    setItem: function (k, v) { storage[k] = String(v); },
    removeItem: function (k) { delete storage[k]; }
  };
  const context = {
    location: { search: '', pathname: '/pages/resume-evidence.html', hash: '' },
    document: {
      addEventListener: function () {},
      getElementById: function () { return elementStub(); },
      querySelector: function () { return elementStub(); },
      querySelectorAll: function () { return []; },
      createElement: function () { return elementStub(); },
      body: elementStub()
    },
    sessionStorage: sessionStorage,
    localStorage: sessionStorage,
    console: { warn: function () {}, log: function () {}, error: function () {} },
    fetch: function () { return Promise.reject(new Error('offline')); },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    AbortController: class { abort() {} },
    FormData: class { append() {} },
    XMLHttpRequest: function () {},
    MOCK: { resumeText: 'x', resumeProfile: {}, matchResult: {} },
    TextDecoder: TextDecoder,
    Date: Date,
    JSON: JSON,
    Math: Math,
    Promise: Promise
  };
  context.window = context;
  return context;
}

function smokeLoad(name, rel) {
  const source = read(rel);
  const context = makeContext();
  // app.js defines window.APP / window.DataBridge contracts used by page scripts
  try { vm.runInNewContext(read('js/app.js'), context, { filename: 'app.js' }); } catch (e) { /* app stub optional */ }
  try { vm.runInNewContext(read('js/data-bridge.js'), context, { filename: 'data-bridge.js' }); } catch (e) { /* bridge stub optional */ }
  assert.doesNotThrow(() => vm.runInNewContext(source, context, { filename: name }));
}

test('interview-practice.html contains the streamed interview controls', () => {
  const html = read('pages/interview-practice.html');
  assert.match(html, /id="f3StartBtn"/);
  assert.match(html, /id="f3Answer"/);
  assert.match(html, /id="f3SendAnswer"/);
  assert.match(html, /id="f3EndInterview"/);
  assert.match(html, /id="f3StreamingBubble"/);
  assert.match(html, /id="f3TurnNo"/);
  assert.match(html, /src="\.\.\/js\/interview-practice\.js"/);
});

test('interview-practice.js streams SSE follow-ups and snapshots the session', () => {
  const src = read('js/interview-practice.js');
  assert.match(src, /\/api\/wf04\/stream/);
  assert.match(src, /f3_session_snapshot_v1/);
  assert.match(src, /getReader/);
  assert.match(src, /function streamFollowUp/);
  assert.match(src, /"fragment"/);
  assert.match(src, /"done"/);
  smokeLoad('interview-practice.js', 'js/interview-practice.js');
});

test('resume-evidence.html includes optimizer.js and the rewrite button markup', () => {
  const html = read('pages/resume-evidence.html');
  assert.match(html, /src="\.\.\/js\/optimizer\.js"/);
  assert.match(html, /data-suggestion-id/);
  assert.match(html, /应用建议改写/);
});

test('optimizer.js previews and applies a pending rewrite', () => {
  const src = read('js/optimizer.js');
  assert.match(src, /\/api\/wf02\/optimize/);
  assert.match(src, /\/api\/wf02\/apply-rewrite/);
  assert.match(src, /rewrite-btn/);
  assert.match(src, /pending_confirm/);
  assert.match(src, /待确认/);
  smokeLoad('optimizer.js', 'js/optimizer.js');
});
