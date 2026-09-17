/* test_phase5_contract.js
 *
 * Phase 5 frontend contract checks:
 *  - data-bridge exposes the F5 apply API (cover letter + application CRUD)
 *  - job-apply.html contains the apply workflow controls
 *  - job-apply.js smoke-loads in a stub DOM context
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
    location: { search: '', pathname: '/pages/job-apply.html', hash: '' },
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

test('job-apply.html contains the apply workflow controls', () => {
  const html = read('pages/job-apply.html');
  assert.match(html, /id="f5Company"/);
  assert.match(html, /id="f5Position"/);
  assert.match(html, /id="f5Generate"/);
  assert.match(html, /id="f5Preview"/);
  assert.match(html, /id="f5PreviewBody"/);
  assert.match(html, /id="f5Confirm"/);
  assert.match(html, /id="f5Applications"/);
  assert.match(html, /src="\.\.\/js\/job-apply\.js"/);
  assert.match(html, /待确认/);
});

test('job-apply.html states the current organization-search boundary', () => {
  const html = read('pages/job-apply.html');
  assert.match(html, /id="f5CapabilityBoundary"/);
  assert.match(html, /当前不提供公司或单位搜索/);
  assert.match(html, /不会核验单位主体、招聘状态或职位真伪/);
  assert.match(html, /题库只作为模拟面试引擎的内部数据源.+不是单位或职位数据库/);
  assert.match(html, /模型不会被当作企业事实来源/);
});

test('job-apply.html declares the F5 index as unconfigured and never as working search', () => {
  const html = read('pages/job-apply.html');
  const docsHtml = fs.readFileSync(path.join(root, 'docs', 'pages', 'job-apply.html'), 'utf8');

  assert.equal(html, docsHtml, 'public/docs F5 page must stay mirrored');
  assert.match(html, /id="f5OrgSearchStatus"/);
  assert.match(html, /尚未接入授权数据源/);
  assert.match(html, /当前不提供单位搜索或职位检索，也不会生成任何单位信息/);
  assert.match(html, /语言模型不参与生成单位事实/);
  // the five business decisions that gate phase 2/3
  assert.match(html, /覆盖地域与单位类型/);
  assert.match(html, /单位数据授权方案/);
  assert.match(html, /实时职位来源/);
  assert.match(html, /月度外部数据预算/);
  assert.match(html, /虚假招聘复核责任人/);
  // manual entry must stay explicitly unverified
  assert.match(html, /id="f5ManualNotice"/);
  assert.match(html, /未经平台核验/);
  // and there must be no organization search control claiming to work
  assert.doesNotMatch(html, /id="f5Org(Search|Query|Keyword)"/);
});

test('job-apply.js smoke-loads without load-time crashes', () => {
  const source = read('js/job-apply.js');
  const context = makeContext();
  vm.runInNewContext(appSource, context, { filename: 'app.js' });
  vm.runInNewContext(bridgeSource, context, { filename: 'data-bridge.js' });
  assert.doesNotThrow(() => vm.runInNewContext(source, context, { filename: 'job-apply.js' }));
});

test('投递页不再是导航项，但它必须仍然可达', () => {
  // §7 把 Cover Letter / Application / Outcome 划归 Target Job 工作区 —— 所以投递页
  // 从一级导航退出，成为目标岗位的子页。退出导航意味着它唯一的入口没了，
  // 因此这里同时锁死"可达"，否则它会静默变成孤儿页。
  const pages = ['index.html', 'pages/resume-evidence.html', 'pages/target-job.html',
    'pages/interview-practice.html', 'pages/action-loop.html', 'pages/job-apply.html'];
  for (const rel of pages) {
    const html = read(rel);
    assert.doesNotMatch(html, /data-page="f5"/, rel + ' 不应再出现 F5 一级导航项');
    for (const page of ['resume', 'target', 'interview', 'action']) {
      assert.match(html, new RegExp('data-page="' + page + '"'),
        rel + ' 缺少一级工作区导航项 ' + page);
    }
  }
  assert.match(read('pages/target-job.html'), /href="job-apply\.html"/,
    '投递子页必须能从目标岗位工作区进入');
});
