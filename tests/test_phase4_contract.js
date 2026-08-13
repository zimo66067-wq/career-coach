/* test_phase4_contract.js
 *
 * Phase 4 frontend contract checks:
 *  - kb.html + kb.js (knowledge base search/list, BM25 fallback notice)
 *  - f3-interview.html + f3-interview.js (SSE follow-up stream, session snapshot)
 *  - f1-resume.html + optimizer.js (rewrite preview modal, apply flow)
 * All scripts are also smoke-loaded in a stub DOM context to catch load-time crashes.
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
    location: { search: '', pathname: '/pages/kb.html', hash: '' },
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

test('kb.html wires the knowledge base and includes kb.js', () => {
  const html = read('pages/kb.html');
  assert.match(html, /id="kbSearchBtn"/);
  assert.match(html, /id="kbQuery"/);
  assert.match(html, /id="kbResults"/);
  assert.match(html, /id="kbChips"/);
  assert.match(html, /id="kbNotice"/);
  assert.match(html, /src="\.\.\/js\/kb\.js"/);
});

test('kb.js calls the knowledge endpoints and renders lists', () => {
  const src = read('js/kb.js');
  assert.match(src, /\/api\/knowledge\/search/);
  assert.match(src, /\/api\/knowledge\/questions/);
  assert.match(src, /function renderList/);
  assert.match(src, /function doSearch/);
  assert.match(src, /bm25|BM25/);
  smokeLoad('kb.js', 'js/kb.js');
});

test('f3-interview.html contains the streamed interview controls', () => {
  const html = read('pages/f3-interview.html');
  assert.match(html, /id="f3StartBtn"/);
  assert.match(html, /id="f3Answer"/);
  assert.match(html, /id="f3SendAnswer"/);
  assert.match(html, /id="f3EndInterview"/);
  assert.match(html, /id="f3StreamingBubble"/);
  assert.match(html, /id="f3TurnNo"/);
  assert.match(html, /src="\.\.\/js\/f3-interview\.js"/);
});

test('f3-interview.js streams SSE follow-ups and snapshots the session', () => {
  const src = read('js/f3-interview.js');
  assert.match(src, /\/api\/wf04\/stream/);
  assert.match(src, /f3_session_snapshot_v1/);
  assert.match(src, /getReader/);
  assert.match(src, /function streamFollowUp/);
  assert.match(src, /"fragment"/);
  assert.match(src, /"done"/);
  smokeLoad('f3-interview.js', 'js/f3-interview.js');
});

test('f1-resume.html includes optimizer.js and the rewrite button markup', () => {
  const html = read('pages/f1-resume.html');
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
