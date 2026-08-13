/* test_upload_progress.js · 阶段2：上传进度（XHR onprogress）+ 错误码映射契约
 *
 * 覆盖：
 *  - data-bridge 暴露 uploadResumeWithProgress / uploadJDWithProgress
 *  - 进度回调百分比、成功落缓存、scanned_pdf 错误映射
 *  - resume-upload / job-upload 优先使用进度上传且不破坏旧契约
 *  - 页面包含进度条元素（F1/F2）
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const appSource = fs.readFileSync(path.join(root, 'public', 'js', 'app.js'), 'utf8');
const bridgeSource = fs.readFileSync(path.join(root, 'public', 'js', 'data-bridge.js'), 'utf8');

function makeContext(search, fetchImpl, initialStorage, apiBase, xhrClass) {
  const storage = Object.assign({}, initialStorage || {});
  const sessionStorage = {
    getItem: function (k) { return Object.prototype.hasOwnProperty.call(storage, k) ? storage[k] : null; },
    setItem: function (k, v) { storage[k] = String(v); },
    removeItem: function (k) { delete storage[k]; }
  };
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
    XMLHttpRequest: xhrClass,
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

function loadBridge(search, fetchImpl, initialStorage, apiBase, xhrClass) {
  const env = makeContext(search, fetchImpl, initialStorage, apiBase, xhrClass);
  vm.runInNewContext(appSource, env.context, { filename: 'app.js' });
  vm.runInNewContext(bridgeSource, env.context, { filename: 'data-bridge.js' });
  return { bridge: env.context.DataBridge, storage: env.storage, context: env.context };
}

// 模拟 XHR：send 时按队列触发 progress 与 onload
function xhrQueueFactory(responses) {
  let index = 0;
  return class FakeXHR {
    constructor() {
      this.upload = { addEventListener: (type, cb) => { this.upload._progressCb = cb; } };
      this.headers = {};
      this.sent = false;
      this.aborted = false;
    }
    open(method, url) {
      this.method = method;
      this.url = url;
    }
    setRequestHeader(k, v) {
      this.headers[k] = v;
    }
    send(body) {
      this.sent = true;
      this.body = body;
      const spec = responses[Math.min(index, responses.length - 1)];
      index += 1;
      if (spec.onSend) spec.onSend(this);
      if (spec.progress && this.upload._progressCb) {
        this.upload._progressCb({ lengthComputable: true, loaded: spec.progress.loaded, total: spec.progress.total });
      }
      this.status = spec.status;
      this.responseText = JSON.stringify(spec.json);
      if (this.onload) this.onload();
    }
    abort() {
      this.aborted = true;
      if (this.onabort) this.onabort();
    }
    get uploadProgressHandler() {
      return this.upload._progressCb;
    }
    set uploadProgressHandler(cb) {
      this.upload._progressCb = cb;
    }
  };
}

test('data-bridge 暴露带进度上传方法', () => {
  const env = loadBridge('', null, {}, 'https://api.example.test', class FakeXHR {
    open() {}
    setRequestHeader() {}
    send() {}
    abort() {}
  });
  assert.equal(typeof env.bridge.uploadResumeWithProgress, 'function');
  assert.equal(typeof env.bridge.uploadJDWithProgress, 'function');
});

test('uploadResumeWithProgress：进度回调 + 成功缓存', async () => {
  const XHR = xhrQueueFactory([
    { progress: { loaded: 512, total: 1024 }, status: 200, json: { resumeText: '张三，三年后端开发经验，负责订单系统。', session_id: 'sess-1', trace_id: 't-1' } }
  ]);
  const env = loadBridge('', null, {}, 'https://api.example.test', XHR);
  const progressEvents = [];
  const result = await env.bridge.uploadResumeWithProgress(
    { name: 'resume.pdf', size: 1024 },
    function (p) { progressEvents.push(p); }
  );
  assert.equal(result.resumeText.includes('张三'), true);
  assert.equal(progressEvents.length >= 1, true);
  assert.equal(progressEvents[progressEvents.length - 1].percent, 50);
  assert.equal(env.storage['cb_cache_resumeText'] !== undefined, true);
});

test('uploadResumeWithProgress：scanned_pdf 错误码透传', async () => {
  const XHR = xhrQueueFactory([
    { status: 422, json: { error: 'scanned_pdf', message: '该 PDF 是扫描件/图片型，无法直接提取文字。', trace_id: 't-2' } }
  ]);
  const env = loadBridge('', null, {}, 'https://api.example.test', XHR);
  const result = await env.bridge.uploadResumeWithProgress({ name: 'scan.pdf', size: 2048 }, function () {});
  assert.equal(result.error, 'scanned_pdf');
  assert.equal(result.message.includes('扫描件'), true);
});

test('uploadJDWithProgress：进度 + 成功', async () => {
  const XHR = xhrQueueFactory([
    { progress: { loaded: 640, total: 1024 }, status: 200, json: { jdText: '岗位职责：负责后端开发。任职要求：熟悉 Python 与 MySQL。', trace_id: 't-3' } }
  ]);
  const env = loadBridge('', null, {}, 'https://api.example.test', XHR);
  const progressEvents = [];
  const result = await env.bridge.uploadJDWithProgress(
    { name: 'jd.pdf', size: 1024 },
    function (p) { progressEvents.push(p); }
  );
  assert.equal(result.jdText.includes('后端开发'), true);
  assert.equal(progressEvents[0].percent, 63);
});

test('resume-upload 流程优先使用带进度上传，不破坏旧契约', async () => {
  const source = fs.readFileSync(path.join(root, 'docs', 'js', 'resume-upload.js'), 'utf8');
  const context = {
    window: {},
    document: { addEventListener() {} },
    console,
    encodeURIComponent,
    isFinite,
    Promise
  };
  vm.createContext(context);
  vm.runInContext(source, context, { filename: 'resume-upload.js' });

  const calls = [];
  let progressSeen = null;
  const profile = { subscores: { structure: { score: 80 }, clarity: { score: 70 }, achievement_evidence: { score: 60 }, skill_evidence: { score: 75 }, ats_readability: { score: 85 } } };
  const flow = context.window.ResumeUpload.createSubmissionFlow({
    bridge: {
      uploadResumeWithProgress(file, onProgress) {
        calls.push(['progress', file.name]);
        onProgress({ percent: 100 });
        return Promise.resolve({ resumeText: '张三，三年后端开发经验，主导订单与支付系统建设，具备完整的项目交付与团队协作能力。' });
      },
      uploadResume(file) { calls.push(['plain', file.name]); return Promise.resolve({ resumeText: 'x' }); },
      async diagnoseResume(text) { calls.push(['diagnose', text]); return { resumeProfile: profile }; }
    },
    onUploadProgress(p) { progressSeen = p; }
  });
  const outcome = await flow.submitFile({ name: 'resume.pdf', size: 2048 });
  assert.equal(outcome.ok, true);
  assert.equal(calls[0][0], 'progress');
  assert.deepStrictEqual(calls.map((c) => c[0]), ['progress', 'diagnose']);
  assert.equal(progressSeen.percent, 100);

  // 无进度方法时回退旧上传契约
  const plainCalls = [];
  const plainFlow = context.window.ResumeUpload.createSubmissionFlow({
    bridge: {
      uploadResume(file) { plainCalls.push(file.name); return Promise.resolve({ resumeText: '李四，五年产品运营经验，主导增长项目并完成可衡量的用户转化提升。' }); },
      async diagnoseResume() { return { resumeProfile: profile }; }
    }
  });
  const plainOutcome = await plainFlow.submitFile({ name: 'r2.pdf', size: 1024 });
  assert.equal(plainOutcome.ok, true);
  assert.deepStrictEqual(plainCalls, ['r2.pdf']);
});

test('job-upload 流程优先使用 uploadJDWithProgress', async () => {
  const source = fs.readFileSync(path.join(root, 'docs', 'js', 'job-upload.js'), 'utf8');
  const context = {
    window: {},
    document: { addEventListener() {} },
    console,
    encodeURIComponent,
    isFinite,
    Promise
  };
  vm.createContext(context);
  vm.runInContext(source, context, { filename: 'job-upload.js' });

  const calls = [];
  const flow = context.window.JobUpload.createSubmissionFlow({
    bridge: {
      uploadJDWithProgress(file, onProgress) {
        calls.push(['progress', file.name]);
        onProgress({ percent: 40 });
        return Promise.resolve({ jdText: '岗位职责：负责后端开发。任职要求：熟悉 Python。' });
      },
      uploadJD(file) { calls.push(['plain', file.name]); return Promise.resolve({ jdText: 'x' }); },
      async submitJD() { return { jobProfile: { requirements: [{ id: 'J1', type: 'hard', text: '熟悉 Python' }] } }; },
      async matchJD() { return { score_M: 60, subscores: {}, requirements: [], gaps: [] }; }
    },
    getResumeText() { return '张三，三年后端开发经验，主导订单与支付系统建设，具备完整的项目交付与团队协作能力。'; },
    isApiAvailable() { return true; }
  });
  const outcome = await flow.submitFile({ name: 'jd.pdf', size: 1024 });
  assert.equal(outcome.ok, true);
  assert.equal(calls[0][0], 'progress');
});

test('页面包含上传进度元素与错误映射', () => {
  const f1 = fs.readFileSync(path.join(root, 'docs', 'pages', 'f1-resume.html'), 'utf8');
  assert.equal(f1.includes('id="resumeUploadProgress"'), true);
  assert.equal(f1.includes('id="resumeUploadProgressBar"'), true);
  assert.equal(f1.includes('id="resumeUploadProgressText"'), true);

  const f2 = fs.readFileSync(path.join(root, 'docs', 'pages', 'f2-match.html'), 'utf8');
  assert.equal(f2.includes('id="f2FileStatus"'), true);
  assert.equal(f2.includes('id="f2UploadProgress"'), true);

  const f2Major = fs.readFileSync(path.join(root, 'docs', 'js', 'f2-major.js'), 'utf8');
  assert.equal(f2Major.includes('uploadResumeWithProgress'), true);
  assert.equal(f2Major.includes('scanned_pdf'), true);

  const resumeUpload = fs.readFileSync(path.join(root, 'docs', 'js', 'resume-upload.js'), 'utf8');
  assert.equal(resumeUpload.includes('uploadResumeWithProgress'), true);
  const jobUpload = fs.readFileSync(path.join(root, 'docs', 'js', 'job-upload.js'), 'utf8');
  assert.equal(jobUpload.includes('uploadJDWithProgress'), true);
});
