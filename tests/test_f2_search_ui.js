const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const publicSource = fs.readFileSync(path.join(root, 'public', 'js', 'f2-major.js'), 'utf8');
const docsSource = fs.readFileSync(path.join(root, 'docs', 'js', 'f2-major.js'), 'utf8');
const publicHtml = fs.readFileSync(path.join(root, 'public', 'pages', 'f2-match.html'), 'utf8');
const docsHtml = fs.readFileSync(path.join(root, 'docs', 'pages', 'f2-match.html'), 'utf8');

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise(function (onResolve, onReject) {
    resolve = onResolve;
    reject = onReject;
  });
  return { promise, resolve, reject };
}

function response(payload, ok) {
  return {
    ok: ok !== false,
    json: function () { return Promise.resolve(payload); }
  };
}

function makeClassList(initial) {
  const values = new Set(initial || []);
  return {
    add: function (name) { values.add(name); },
    remove: function (name) { values.delete(name); },
    contains: function (name) { return values.has(name); },
    toggle: function (name, force) {
      if (force === undefined) {
        if (values.has(name)) values.delete(name);
        else values.add(name);
        return values.has(name);
      }
      if (force) values.add(name);
      else values.delete(name);
      return force;
    }
  };
}

function makeElement(id) {
  const listeners = new Map();
  return {
    id: id,
    value: '',
    innerHTML: '',
    textContent: '',
    disabled: false,
    hidden: false,
    files: [],
    style: {},
    classList: makeClassList(id === 'f2SearchResults' ? ['zy-hidden'] : []),
    addEventListener: function (name, handler) { listeners.set(name, handler); },
    emit: function (name, event) {
      const handler = listeners.get(name);
      if (handler) handler(event || {});
    },
    querySelectorAll: function () { return []; },
    getAttribute: function () { return null; },
    setAttribute: function () {}
  };
}

function makeHarness() {
  const elements = new Map();
  const requests = [];
  let timerId = 0;
  const storage = new Map();

  function element(id) {
    if (!elements.has(id)) elements.set(id, makeElement(id));
    return elements.get(id);
  }

  const context = {
    console: { warn: function () {}, log: function () {}, error: function () {} },
    location: { search: '', pathname: '/pages/f2-match.html', hash: '' },
    history: { replaceState: function () {} },
    document: {
      readyState: 'complete',
      addEventListener: function () {},
      getElementById: element,
      querySelector: function () { return null; }
    },
    localStorage: {
      getItem: function (key) { return storage.has(key) ? storage.get(key) : null; },
      setItem: function (key, value) { storage.set(key, String(value)); }
    },
    fetch: function (url, options) {
      if (url.includes('/api/f2/majors/tree')) {
        return Promise.resolve(response({ categories: [] }));
      }
      const pending = deferred();
      requests.push({ url: url, options: options || {}, pending: pending });
      return pending.promise;
    },
    setTimeout: function (handler) { handler(); timerId += 1; return timerId; },
    clearTimeout: function () {},
    setInterval: function () { timerId += 1; return timerId; },
    clearInterval: function () {},
    AbortController: class {
      constructor() { this.signal = { aborted: false }; }
      abort() { this.signal.aborted = true; }
    },
    FileReader: function () {}
  };
  context.window = context;
  context.scrollTo = function () {};
  vm.createContext(context);
  vm.runInContext(publicSource, context, { filename: 'f2-major.js' });
  return { context, element, requests };
}

function search(harness, query) {
  const input = harness.element('f2Search');
  input.value = query;
  input.emit('input');
}

function intentSearch(harness, query) {
  const input = harness.element('f2Intent');
  input.value = query;
  input.emit('input');
}

function settle() {
  return new Promise(function (resolve) { setImmediate(resolve); });
}

test('F2 published search assets stay mirrored and explain supported query styles', () => {
  assert.equal(publicSource, docsSource);
  assert.equal(publicHtml, docsHtml);
  assert.match(publicHtml, /placeholder="[^"]*专业代码[^"]*错字[^"]*求职方向/);
  assert.match(publicHtml, /id="f2Search"[^>]*maxlength="64"/);
  assert.match(publicHtml, /id="f2Intent"[^>]*maxlength="64"/);
});

test('F2 search renders the backend match reason and profile status safely', async () => {
  const harness = makeHarness();
  search(harness, '计算机科学与技木');
  assert.equal(harness.requests.length, 1);
  harness.requests[0].pending.resolve(response({
    items: [{
      code: '080901',
      name: '计算机科学与技术',
      category_name: '工学',
      class_name: '计算机类',
      match_reason: '专业名称近似<img src=x>',
      has_profile: false
    }]
  }));
  await settle();

  const html = harness.element('f2SearchResults').innerHTML;
  assert.match(html, /专业名称近似/);
  assert.match(html, /画像建设中/);
  assert.doesNotMatch(html, /<img src=x>/);
  assert.match(html, /&lt;img src=x&gt;/);
});

test('a late stale response cannot overwrite the latest F2 query', async () => {
  const harness = makeHarness();
  search(harness, '计算');
  search(harness, '软件');
  assert.equal(harness.requests.length, 2);
  assert.equal(harness.requests[0].options.signal.aborted, true);

  harness.requests[1].pending.resolve(response({
    items: [{
      code: '080902', name: '软件工程', category_name: '工学',
      class_name: '计算机类', match_reason: '专业名称相关', has_profile: true
    }]
  }));
  await settle();
  assert.match(harness.element('f2SearchResults').innerHTML, /软件工程/);

  harness.requests[0].pending.resolve(response({
    items: [{
      code: '080901', name: '计算机科学与技术', category_name: '工学',
      class_name: '计算机类', match_reason: '专业名称相关', has_profile: true
    }]
  }));
  await settle();
  const html = harness.element('f2SearchResults').innerHTML;
  assert.match(html, /软件工程/);
  assert.doesNotMatch(html, /计算机科学与技术/);
});

test('F2 search gives actionable empty and failure states', async () => {
  const harness = makeHarness();
  search(harness, '不存在的专业');
  harness.requests[0].pending.resolve(response({ items: [] }));
  await settle();
  assert.match(harness.element('f2SearchResults').innerHTML, /未找到相关专业/);
  assert.match(harness.element('f2SearchResults').innerHTML, /专业代码、近似名称或求职方向/);

  search(harness, '写代码');
  harness.requests[1].pending.reject(new Error('offline'));
  await settle();
  assert.match(harness.element('f2SearchResults').innerHTML, /搜索暂不可用/);

  search(harness, '');
  assert.equal(harness.element('f2SearchResults').innerHTML, '');
  assert.equal(harness.element('f2SearchResults').classList.contains('zy-hidden'), true);
});

test('F2 main search distinguishes business errors from network failures', async () => {
  const harness = makeHarness();

  search(harness, 'x'.repeat(65));
  harness.requests[0].pending.resolve(response(
    { error: 'query_too_long', message: '搜索词不能超过 64 个字符。' }, false
  ));
  await settle();
  let html = harness.element('f2SearchResults').innerHTML;
  assert.match(html, /搜索词不能超过 64 个字符/);
  assert.doesNotMatch(html, /检查网络/);

  search(harness, '写代码');
  harness.requests[1].pending.reject(new Error('offline'));
  await settle();
  html = harness.element('f2SearchResults').innerHTML;
  assert.match(html, /搜索暂不可用，请检查网络后重试/);
});

test('a slow F2 response cannot reopen the dropdown after blur', async () => {
  const harness = makeHarness();
  const input = harness.element('f2Search');

  input.emit('focus');
  input.value = '计算机';
  input.emit('input');
  assert.equal(harness.requests.length, 1);
  const pending = harness.requests[0].pending;

  input.emit('blur');
  pending.resolve(response({
    items: [{
      code: '080901', name: '计算机科学与技术', category_name: '工学',
      class_name: '计算机类', match_reason: '专业名称相关', has_profile: true
    }]
  }));
  await settle();

  const box = harness.element('f2SearchResults');
  assert.equal(box.classList.contains('zy-hidden'), true);
  assert.doesNotMatch(box.innerHTML, /计算机科学与技术/);
});

test('F2 intent input handles stale responses, business errors and empty results', async () => {
  const harness = makeHarness();

  intentSearch(harness, '程序');
  intentSearch(harness, '程序员');
  assert.equal(harness.requests.length, 2);
  assert.equal(harness.requests[0].options.signal.aborted, true);

  harness.requests[1].pending.resolve(response({
    items: [{
      code: '080901', name: '计算机科学与技术', path: '工学 / 计算机类',
      match_reason: '求职意向相关', has_profile: true
    }]
  }));
  await settle();
  assert.match(harness.element('f2IntentResults').innerHTML, /计算机科学与技术/);
  assert.match(harness.element('f2IntentResults').innerHTML, /求职意向相关/);

  harness.requests[0].pending.resolve(response({
    items: [{ code: '080902', name: '软件工程', path: '工学 / 计算机类', has_profile: true }]
  }));
  await settle();
  const html = harness.element('f2IntentResults').innerHTML;
  assert.match(html, /计算机科学与技术/);
  assert.doesNotMatch(html, /软件工程/);

  intentSearch(harness, 'y'.repeat(65));
  harness.requests[2].pending.resolve(response(
    { error: 'query_too_long', message: '搜索词不能超过 64 个字符。' }, false
  ));
  await settle();
  const errorHtml = harness.element('f2IntentResults').innerHTML;
  assert.match(errorHtml, /搜索词不能超过 64 个字符/);
  assert.doesNotMatch(errorHtml, /检查网络/);

  intentSearch(harness, '不存在的方向');
  harness.requests[3].pending.resolve(response({ items: [], total: 0 }));
  await settle();
  assert.match(harness.element('f2IntentResults').innerHTML, /未找到相关专业方向/);

  intentSearch(harness, '写代码');
  harness.requests[4].pending.reject(new Error('offline'));
  await settle();
  assert.match(harness.element('f2IntentResults').innerHTML, /岗位方向搜索暂不可用/);
});

test('F2 intent input clears when the query becomes empty', async () => {
  const harness = makeHarness();
  intentSearch(harness, '程序员');
  assert.equal(harness.requests.length, 1);
  intentSearch(harness, '');
  assert.equal(harness.element('f2IntentResults').innerHTML, '');
});
