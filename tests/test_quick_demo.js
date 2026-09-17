/* Quick Demo (P0-1) 契约检查。运行：node tests/test_quick_demo.js */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');

test('F1 页面含一键体验按钮、演示标注与脚本引用', () => {
  const html = read('docs/pages/resume-evidence.html');
  assert.match(html, /id="quickDemoF1"/);
  assert.match(html, /quick-demo\.js/);
  assert.match(html, /demo-badge|演示数据/);
});

test('首页提供 Quick Demo 入口', () => {
  const html = read('docs/index.html');
  assert.match(html, /hero-cta/);
  assert.match(html, /resume-evidence\.html\?quick=1/);
  assert.match(html, /quick-demo\.js/);
});

test('quick-demo.js 暴露 QuickDemo.start 且必须标注演示数据', () => {
  const source = read('docs/js/quick-demo.js');
  const els = new Map();
  const context = {
    console,
    location: { search: '', href: 'https://example.test/pages/resume-evidence.html' },
    history: { replaceState: function () {} },
    document: {
      readyState: 'loading',
      addEventListener: function (ev, fn) { if (ev === 'DOMContentLoaded') this._fn = fn; },
      getElementById: function (id) { return els.get(id) || null; },
      createElement: function () { return { id: '', className: '', textContent: '', classList: { add: function () {} } }; },
      body: { appendChild: function () {}, setAttribute: function () {}, getAttribute: function () { return 'f1'; } }
    },
    alert: function () {},
    Event: function () {},
    MOCK: { resumeText: '样例' },
    DataBridge: { diagnoseResume: async function () { return { error: 'offline' }; }, getMockData: function () { return null; } },
    APP: { setState: function () {} },
    DUMATE_API_BASE: 'https://api.example.test'
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(source, context, { filename: 'quick-demo.js' });
  assert.equal(typeof context.window.QuickDemo.start, 'function');
  assert.equal(typeof context.window.QuickDemo.startF1, 'function');
  assert.match(source, /演示数据/);
  assert.match(source, /showDemoBadge/);
});

test('mock-data.js 提供样例 JD（jdText）', () => {
  const source = read('docs/js/mock-data.js');
  assert.match(source, /jdText/);
  assert.match(source, /岗位职责/);
});
