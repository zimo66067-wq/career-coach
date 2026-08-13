/* test_phase5_contract.js
 *
 * Phase 5 frontend contract checks:
 *  - data-bridge exposes the F5 apply API (cover letter + application CRUD)
 *  - f5-apply.html contains the apply workflow controls
 *  - f5-apply.js smoke-loads in a stub DOM context
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(root, 'public', rel), 'utf8');
const appSource = read('js/app.js');
const bridgeSource = read('js/data-bridge.js');

function elementStub() {
  return {
    addEventListener: function () {},
    removeEventListener: function () {},
    setAttribute: function () {},
    getAttribute: function () { return null; },
    removeAttribute: function () {},
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
    location: { search: '', pathname: '/pages/f5-apply.html', hash: '' },
    document: {
      readyState: 'complete',
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

function loadBridge() {
  const context = makeContext();
  vm.runInNewContext(appSource, context, { filename: 'app.js' });
  vm.runInNewContext(bridgeSource, context, { filename: 'data-bridge.js' });
  return context.DataBridge;
}

test('data-bridge exposes the F5 apply API and endpoints', () => {
  const bridge = loadBridge();
  assert.equal(typeof bridge.generateCoverLetter, 'function');
  assert.equal(typeof bridge.saveApplication, 'function');
  assert.equal(typeof bridge.listApplications, 'function');
  assert.equal(typeof bridge.deleteApplication, 'function');
  assert.equal(bridge._endpoints.coverLetter, '/api/wf07/cover-letter');
  assert.equal(bridge._endpoints.applications, '/api/wf07/applications');
});

test('f5-apply.html contains the apply workflow controls', () => {
  const html = read('pages/f5-apply.html');
  assert.match(html, /id="f5Company"/);
  assert.match(html, /id="f5Position"/);
  assert.match(html, /id="f5Generate"/);
  assert.match(html, /id="f5Preview"/);
  assert.match(html, /id="f5PreviewBody"/);
  assert.match(html, /id="f5Confirm"/);
  assert.match(html, /id="f5Applications"/);
  assert.match(html, /src="\.\.\/js\/f5-apply\.js"/);
  assert.match(html, /待确认/);
});

test('f5-apply.js smoke-loads without load-time crashes', () => {
  const source = read('js/f5-apply.js');
  const context = makeContext();
  vm.runInNewContext(appSource, context, { filename: 'app.js' });
  vm.runInNewContext(bridgeSource, context, { filename: 'data-bridge.js' });
  assert.doesNotThrow(() => vm.runInNewContext(source, context, { filename: 'f5-apply.js' }));
});

test('all pages expose the F5 navigation entry', () => {
  const pages = ['index.html', 'pages/f1-resume.html', 'pages/f2-match.html',
    'pages/f3-interview.html', 'pages/f4-report.html', 'pages/kb.html', 'pages/f5-apply.html'];
  for (const rel of pages) {
    assert.match(read(rel), /data-page="f5"/, rel);
  }
});
