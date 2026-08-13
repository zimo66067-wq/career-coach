/* test_tasks_contract.js ? ??3????????????????
 *
 * ???
 *  - data-bridge ?? createTask / getTask / advanceTask / pollTask ? ENDPOINTS.tasks=/api/tasks
 *  - createTask ?? task_type/payload/idempotency_key ??? res.task
 *  - pollTask ? pending->running->done ?????????
 *  - f2-major.js ?????????createTask/pollTask???????????
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const appSource = fs.readFileSync(path.join(root, 'public', 'js', 'app.js'), 'utf8');
const bridgeSource = fs.readFileSync(path.join(root, 'public', 'js', 'data-bridge.js'), 'utf8');
const f2Source = fs.readFileSync(path.join(root, 'public', 'js', 'f2-major.js'), 'utf8');
const f2Html = fs.readFileSync(path.join(root, 'public', 'pages', 'f2-match.html'), 'utf8');

function makeContext(fetchImpl) {
  const storage = {
    cb_cache_consentToken: JSON.stringify({ data: 't-consent', ts: Date.now() })
  };
  const sessionStorage = {
    getItem: function (k) { return Object.prototype.hasOwnProperty.call(storage, k) ? storage[k] : null; },
    setItem: function (k, v) { storage[k] = String(v); },
    removeItem: function (k) { delete storage[k]; }
  };
  const context = {
    location: { search: '', pathname: '/pages/f2-match.html', hash: '' },
    document: { addEventListener: function () {}, getElementById: function () { return null; } },
    sessionStorage: sessionStorage,
    localStorage: sessionStorage,
    console: { warn: function () {}, log: function () {}, error: function () {} },
    fetch: fetchImpl || function () { return Promise.reject(new Error('offline')); },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    AbortController: class { abort() {} },
    FormData: class { append() {} },
    XMLHttpRequest: function () {},
    MOCK: { resumeText: 'x', resumeProfile: {}, matchResult: {} },
    Date: Date,
    JSON: JSON,
    Math: Math,
    Promise: Promise
  };
  context.window = context;
  return context;
}

function loadBridge(fetchImpl) {
  const context = makeContext(fetchImpl);
  vm.runInNewContext(appSource, context, { filename: 'app.js' });
  vm.runInNewContext(bridgeSource, context, { filename: 'data-bridge.js' });
  return context.DataBridge;
}

function okJson(payload) {
  return Promise.resolve({ ok: true, status: 200, json: function () { return Promise.resolve(payload); } });
}

test('bridge exposes task API and endpoint', () => {
  const bridge = loadBridge();
  assert.equal(typeof bridge.createTask, 'function');
  assert.equal(typeof bridge.getTask, 'function');
  assert.equal(typeof bridge.advanceTask, 'function');
  assert.equal(typeof bridge.pollTask, 'function');
  assert.equal(bridge._endpoints.tasks, '/api/tasks');
});

test('createTask posts payload and returns res.task', async () => {
  const calls = [];
  const bridge = loadBridge(function (url, opts) {
    calls.push({ url: url, opts: opts });
    return okJson({ task: { id: 'task_x', state: 'pending', progress: 0 } });
  });
  const task = await bridge.createTask('f2_match', { major_code: '080901' }, 'idem-1');
  assert.equal(task.id, 'task_x');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/tasks');
  const body = JSON.parse(calls[0].opts.body);
  assert.equal(body.task_type, 'f2_match');
  assert.equal(body.payload.major_code, '080901');
  assert.equal(body.idempotency_key, 'idem-1');
  assert.equal(calls[0].opts.headers['X-Consent-Token'], 't-consent');
});

test('pollTask advances until done and reports progress', async () => {
  const states = [
    { id: 'task_p', state: 'pending', progress: 0 },
    { id: 'task_p', state: 'running', progress: 35 },
    { id: 'task_p', state: 'running', progress: 70 },
    { id: 'task_p', state: 'done', progress: 100 }
  ];
  const bridge = loadBridge(function (url) {
    if (url === '/api/tasks/task_p') {
      return okJson({ task: states[0] });
    }
    if (url === '/api/tasks/task_p/next') {
      return okJson({ task: states.shift() === undefined ? states[states.length - 1] : states[0] });
    }
    return Promise.resolve({ ok: false, status: 404, json: function () { return Promise.resolve({ error: 'not_found' }); } });
  });
  const seen = [];
  const task = await bridge.pollTask('task_p', function (t) { seen.push(t.progress); });
  assert.equal(task.state, 'done');
  assert.equal(task.progress, 100);
  assert.deepEqual(seen, [0, 35, 70, 100]);
});

test('f2-major.js integrates task matching and page shows progress UI', () => {
  assert.match(f2Source, /createTask\("f2_match"/);
  assert.match(f2Source, /pollTask\(task\.id/);
  assert.match(f2Source, /startMatchTask\(/);
  assert.match(f2Html, /id="f2TaskProgress"/);
  assert.match(f2Html, /id="f2TaskProgressBar"/);
  assert.match(f2Html, /id="f2TaskProgressText"/);
});
