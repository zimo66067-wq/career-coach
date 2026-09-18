/* test_phase6b3_contract.js · D7「进入即强制注册/登录」的门禁判据
 *
 * 为什么要有这组判据：D7 的两半都不在既有判据的观察面内。
 *   - 前端一半：`account.js` 从来没有被任何 JS 测试加载过（链路测试只 load app.js +
 *     data-bridge.js），所以"弹窗能不能被关掉""服务端不响应时会不会放行"没人看。
 *   - 后端一半：D7 明说"不得因加门禁而回退既有安全性质"，那些性质（HttpOnly、限流）
 *     散在 `api/index.py` 里，改前端时很容易顺手碰坏却无人察觉。
 *
 * 两层判据：
 *   ① 合同层（扫文本）：装配、原生 dialog、三态载体、豁免名单、强制不可关的兜底
 *   ② 行为层（VM 跑 auth-gate.js 的纯函数）：四象限决策 + 三态映射 + "只有服务端能放行"
 *
 * 每层都带自检与探针：判据本身失效要能被发现（见最后两个 test）。
 *
 * 6b-3 首轮跑出 5 红，其中 4 项是**判据自己的缺陷**（扫注释、跨 realm 比较、
 * 漏算 init 基线、断言写错文件），只有 1 项是产品接口隐患（plan/decide 共用 gate 键）。
 * 三个工具因此被抽出来：codeOnly()（只扫代码）、flat()（跨 realm 比较）、
 * trappingStorage()（把"不读本地存储"从读源码变成可证伪）。
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const TREES = ['public', 'docs'];
const PAGES = [
  'index.html',
  'pages/resume-evidence.html',
  'pages/target-job.html',
  'pages/interview-practice.html',
  'pages/action-loop.html',
  'pages/job-apply.html',
  'pages/states.html'
];

function read(tree, rel) {
  return fs.readFileSync(path.join(root, tree, rel), 'utf8');
}

// Phase 7c：后端入口拆成了 24 个模块（`api/index.py` 只剩分发器 + 路由表），
// 所以「这几条安全性质还在不在后端」**不能再只读 api/index.py**：
//   httponly / samesite        → api/security.py
//   enforce_usage 限流调用     → api/handlers/account.py
//   auth 四条路由名            → api/handlers/account.py
// 观察面跟着实现一起搬，否则判据会从"检查实现"退化成"检查搬家后剩下的空壳"。
function apiPackageSource() {
  const out = [];
  (function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === '__pycache__') continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith('.py')) out.push(fs.readFileSync(full, 'utf8'));
    }
  })(path.join(root, 'api'));
  return out.join('\n');
}

// 判据只应观察**代码**，不该把注释里的说明当成实现。
// 直接 includes() 会连注释一起扫，于是"本文件不读 localStorage"这句安全说明
// 反倒把判据扫红 —— 逼人去删掉最该留下的那句话。
// 这里做一次字符串感知的注释剥离：保留字符串字面量的内容（真用了 tokens 仍会被抓到），
// 只去掉行注释与块注释。（6b-1 已在 data-bridge.js 上踩过一次同款：说明性注释命中判据。）
function codeOnly(src) {
  let out = '';
  let state = 'code';
  for (let i = 0; i < src.length; i++) {
    const c = src[i], d = src[i + 1];
    if (state === 'code') {
      if (c === '/' && d === '/') { state = 'line'; i++; continue; }
      if (c === '/' && d === '*') { state = 'block'; i++; continue; }
      if (c === "'" || c === '"' || c === '`') state = c;
      out += c; continue;
    }
    if (state === 'line') { if (c === '\n') { state = 'code'; out += c; } continue; }
    if (state === 'block') { if (c === '*' && d === '/') { state = 'code'; i++; } continue; }
    if (c === '\\') { out += c + (d === undefined ? '' : d); i++; continue; }
    if (c === state) state = 'code';
    out += c;
  }
  return out;
}

// vm 里跑出来的对象属于**另一个 realm**，其 Object.prototype 与宿主那份不是同一个，
// 于是 assert.deepStrictEqual 会以"结构相同但引用不等"报错 —— 这是判据的锅，不是产品的锅。
// 复制进宿主对象再比（数组按元素复制，因为 Array.isArray 是跨 realm 安全的）。
function flat(v) {
  if (Array.isArray(v)) return v.map(flat);
  if (v && typeof v === 'object') return Object.assign({}, v);
  return v;
}

// ── ① 装配：七个产品页都要挂政策层，且排在机制层之后 ────────────────

test('每个产品页都挂 auth-gate.js，且排在 account.js 之后', () => {
  for (const tree of TREES) {
    for (const rel of PAGES) {
      const text = read(tree, rel);
      const order = [...text.matchAll(/src="[^"]*js\/(account|auth-gate)\.js"/g)].map(m => m[1]);
      assert.deepEqual(order, ['account', 'auth-gate'],
        tree + '/' + rel + ' 的脚本顺序不对：政策层必须能拿到 window.ZY_ACCOUNT');
    }
  }
});

test('弹窗是原生 <dialog>，不再有 div 版弹窗残留', () => {
  for (const tree of TREES) {
    for (const rel of PAGES) {
      const text = read(tree, rel);
      assert.match(text, /<dialog class="zy-modal" id="zyAuthModal"[^>]*aria-labelledby="zyAuthTitle"[^>]*aria-describedby="zyAuthWhy"/,
        tree + '/' + rel + ' 的弹窗必须是原生 <dialog> 且关联标题与说明');
      assert.ok(!/<div class="zy-modal[^"]*" id="zyAuthModal"/.test(text),
        tree + '/' + rel + ' 还留着 div 版弹窗 —— 原生 dialog 才自带焦点陷阱与 Esc');
      assert.ok(!/class="zy-modal zy-hidden"/.test(text),
        tree + '/' + rel + ' 的弹窗仍靠 .zy-hidden 显隐（原生 dialog 用 open 属性）');
    }
  }
});

test('三态各有可见载体，状态区是可访问的 live region', () => {
  for (const tree of TREES) {
    for (const rel of PAGES) {
      const text = read(tree, rel);
      assert.match(text, /id="zyAuthWhy"/, tree + '/' + rel + ' 缺门禁说明（为什么必须登录）');
      assert.match(text, /<p class="zy-gate-status" id="zyGateStatus" role="status" aria-live="polite">/,
        tree + '/' + rel + ' 的状态区必须是 role=status + aria-live=polite');
      assert.match(text, /id="zyGateRetry"/, tree + '/' + rel + ' 缺「重新连接」（error 态出口）');
    }
  }
  const css = read('public', 'css/sidebar.css');
  for (const sel of ['.zy-modal::backdrop', '.zy-modal[data-forced="true"] .zy-modal-close',
                     '.zy-gate-status.err', '.zy-btn[disabled]']) {
    assert.ok(css.includes(sel), 'sidebar.css 缺样式：' + sel);
  }
});

// ── ② 豁免名单：刻意只有一项，且必须锁住不让它悄悄扩容 ──────────────

function exemptList(tree) {
  const src = read(tree, 'js/auth-gate.js');
  const m = src.match(/var EXEMPT = (\[[^\]]*\]);/);
  assert.ok(m, tree + '/js/auth-gate.js 里找不到 EXEMPT 名单（判据锚点失效）');
  return JSON.parse(m[1].replace(/'/g, '"'));
}

test('门禁豁免名单恰好是内部 QA 状态墙一项', () => {
  for (const tree of TREES) {
    const list = exemptList(tree);
    assert.deepEqual(list, ['/pages/states.html'],
      tree + ' 的豁免名单变了：加一项就等于放一个产品页出去，必须是有意为之');
    // 豁免的页面必须真实存在，否则名单是死的
    const rel = list[0].replace(/^\//, '');
    assert.ok(fs.existsSync(path.join(root, tree, rel)), tree + ' 豁免了一个不存在的页面：' + rel);
  }
});

// ── ③ 安全口径：登录态只认服务端；服务端不可用判为拦下 ──────────────

test('auth-gate.js 不以本地存储判定登录态', () => {
  for (const tree of TREES) {
    // 只看**代码**。文件头的注释里必然写着"本文件不读 localStorage"——那是安全口径的
    // 说明，判据若连注释一起扫，就会逼人删掉最该留下的那句话。
    const code = codeOnly(read(tree, 'js/auth-gate.js'));
    for (const bad of ['localStorage', 'sessionStorage', 'document.cookie']) {
      assert.ok(!code.includes(bad),
        tree + '/js/auth-gate.js 出现了 ' + bad + ' —— 本地标记能伪造的门禁不是门禁');
    }
    assert.ok(!/window\.ZY_ACCOUNT\s*=/.test(code),
      tree + '/js/auth-gate.js 不得自己造一个账号模块（登录态只能来自 account.js 的转交）');
  }
  // 真正的 /api/auth/me 调用在 account.js（政策层只经 refreshAuth() 转交）。
  // 这条断言过去写在 auth-gate.js 上，而那个文件里根本没有这个字面量 ——
  // 它是靠注释里的 "GET /api/auth/me" 凑巧通过的，属空判。
  for (const tree of TREES) {
    assert.match(codeOnly(read(tree, 'js/account.js')), /['"]\/auth\/me['"]/,
      tree + '/js/account.js 必须真的去请求服务端 /auth/me');
  }
});

test('D7 不得回退既有服务端安全性质（HttpOnly / 限流 / 四个 auth 端点）', () => {
  const api = apiPackageSource();
  assert.match(api, /httponly=True/, '会话 Cookie 必须是 HttpOnly —— 加门禁不能把它降级');
  assert.match(api, /samesite="None" if secure else "Lax"/, 'SameSite 口径被改动');
  assert.match(api, /enforce_usage\("auth_register", 5, 3600/, '注册限流（5 次/小时）被移除或改动');
  assert.match(api, /enforce_usage\("auth_login", 10, 900/, '登录限流（10 次/15 分钟）被移除或改动');
  for (const route of ['auth/register', 'auth/login', 'auth/logout', 'auth/me']) {
    assert.ok(api.includes('"' + route + '"'), '后端缺 auth 路由：' + route);
  }
});

// ── ④ 强制不可关：三层兜底都要在 ────────────────────────────────

test('强制态在 JS 与 CSS 两层都关不掉', () => {
  for (const tree of TREES) {
    const gate = read(tree, 'js/auth-gate.js');
    const account = read(tree, 'js/account.js');
    const css = read(tree, 'css/sidebar.css');
    assert.match(gate, /classList\.toggle\('zy-hidden', result\.forced\)/,
      tree + ' 的 auth-gate.js 必须在强制态隐藏关闭按钮');
    assert.match(account, /if \(forced && !currentUser\)/,
      tree + ' 的 account.js 必须在强制态拒绝关闭');
    assert.match(account, /addEventListener\('cancel'/,
      tree + ' 的 account.js 必须处理原生 dialog 的 cancel（Esc）事件');
    assert.match(account, /if \(forced && !currentUser\) ev\.preventDefault\(\)/,
      tree + ' 的 Esc 必须在强制态被拦下');
    assert.match(css, /\[data-forced="true"\] \.zy-modal-close \{ display: none; \}/,
      tree + ' 的 CSS 缺兜底：JS 没跑到位时关闭按钮仍会露出来');
  }
});

// ── ⑤ 行为层：在 VM 里跑 auth-gate.js 的纯函数 ────────────────────

const IDS = ['zyAuthModal', 'zyAuthClose', 'zyGateStatus', 'zyGateRetry'];

// 带存取陷阱的假存储：键名故意起得像真的。政策层只要碰过一次就会被记下来，
// 于是"本地标记能不能开门"这条可以被**证伪**，而不是只靠读源码断言。
function trappingStorage(touch) {
  const store = { zy_logged_in: '1', zy_user: '{"name":"伪造"}', token: 'fake', logged_in: 'true' };
  return new Proxy(store, {
    get(t, k) { touch.push('get:' + String(k)); return t[k]; },
    has(t, k) { touch.push('has:' + String(k)); return k in t; },
    ownKeys(t) { touch.push('ownKeys'); return Reflect.ownKeys(t); }
  });
}

function makeDom(touch) {
  const els = {};
  const listeners = {};
  function mk(id) {
    const classes = new Set();
    return {
      id: id, textContent: '', disabled: false, open: false, attrs: {}, focused: false,
      className: '',
      classList: {
        add: c => classes.add(c),
        remove: c => classes.delete(c),
        toggle: (c, on) => { const v = on === undefined ? !classes.has(c) : !!on; v ? classes.add(c) : classes.delete(c); return v; },
        contains: c => classes.has(c)
      },
      setAttribute: (k, v) => { els[id].attrs[k] = String(v); },
      getAttribute: k => (Object.prototype.hasOwnProperty.call(els[id].attrs, k) ? els[id].attrs[k] : null),
      addEventListener: (ev, fn) => { (listeners[id + ':' + ev] = listeners[id + ':' + ev] || []).push(fn); },
      focus: () => { els[id].focused = true; }
    };
  }
  IDS.forEach(id => { els[id] = mk(id); });
  const doc = {
    readyState: 'complete',
    getElementById: id => els[id] || null,
    addEventListener: (ev, fn) => { (listeners['doc:' + ev] = listeners['doc:' + ev] || []).push(fn); },
    dispatchEvent: ev => { (listeners['doc:' + ev.type] || []).forEach(fn => fn(ev)); return true; },
    // document.cookie 也是"本地标记"的一个入口，同样要能被证伪
    get cookie() { touch.push('cookie'); return 'zy_logged_in=1'; }
  };
  return { doc: doc, els: els, listeners: listeners };
}

function loadGate(opts) {
  opts = opts || {};
  const src = read('public', 'js/auth-gate.js');
  const touched = [];
  const dom = makeDom(touched);
  const calls = [];
  const context = {
    location: { pathname: opts.pathname || '/pages/resume-evidence.html' },
    document: dom.doc,
    console: console,
    Promise: Promise,
    Object: Object,
    JSON: JSON,
    String: String,
    Array: Array,
    CustomEvent: class { constructor(type, init) { this.type = type; this.detail = (init || {}).detail; } }
  };
  context.window = context;
  let meCalls = 0;
  context.window.ZY_ACCOUNT = {
    refreshAuth: function () {
      meCalls += 1;
      if (opts.me === 'throw') return Promise.reject(new Error('boom'));
      return Promise.resolve(opts.me);
    },
    openAuth: function (tab, o) { calls.push({ action: 'open', tab: tab, forced: !!(o && o.forced) }); },
    closeAuth: function () { calls.push({ action: 'close' }); }
  };
  if (opts.trapStorage) {
    context.localStorage = trappingStorage(touched);
    context.sessionStorage = trappingStorage(touched);
  }
  vm.runInNewContext(src, context, { filename: 'auth-gate.js' });
  return { gate: context.window.ZY_GATE, dom: dom, calls: calls, touched: touched,
           meCalls: () => meCalls, listeners: dom.listeners };
}

test('decide()：四象限，且「拿不到服务端答复」判为拦下', () => {
  const { gate } = loadGate();
  // 必须过 flat()：decide() 的返回值来自 vm realm，直接 deepStrictEqual 会因原型不同而报错
  assert.deepEqual(flat(gate.decide('/pages/resume-evidence.html', { ok: true, logged_in: true, user: { name: 'a' } })),
    { gate: false, reason: 'authed' });
  assert.deepEqual(flat(gate.decide('/pages/resume-evidence.html', { ok: true, logged_in: false, user: null })),
    { gate: true, reason: 'anonymous' });
  assert.deepEqual(flat(gate.decide('/pages/resume-evidence.html', { ok: false, reason: '断网' })),
    { gate: true, reason: 'unavailable' });
  assert.deepEqual(flat(gate.decide('/pages/states.html', { ok: false, reason: '断网' })),
    { gate: false, reason: 'exempt' });
  // 关键反例：logged_in 为真但没有 user 对象 —— 半截答复不算登录
  assert.equal(gate.decide('/pages/resume-evidence.html', { ok: true, logged_in: true, user: null }).gate, true);
  // 关键反例：me 为 null / undefined（上游忘了转交）也必须拦
  assert.equal(gate.decide('/pages/resume-evidence.html', null).reason, 'unavailable');
});

test('decide()：路径归一，带查询串/站点前缀都仍然拦', () => {
  const { gate } = loadGate();
  assert.equal(gate.normalize('/index.html'), '/index.html');
  assert.equal(gate.normalize('/'), '/index.html');
  assert.equal(gate.normalize('/pages/target-job.html?demo=1&state=success'), '/pages/target-job.html');
  assert.equal(gate.normalize('/career-coach/pages/action-loop.html'), '/pages/action-loop.html');
  assert.equal(gate.decide('/', { ok: true, logged_in: false }).gate, true, '首页也要拦');
  assert.equal(gate.decide('/pages/states.html?v=1', { ok: true, logged_in: false }).gate, false,
    '豁免页带参数仍应豁免');
});

test('plan()：三态映射正确（empty / error / disabled）', () => {
  const { gate } = loadGate();
  const anon = gate.plan({ gate: true, reason: 'anonymous' });
  assert.equal(anon.action, 'open');
  assert.equal(anon.gateState, 'empty');
  assert.equal(anon.forced, true);
  assert.equal(anon.retry, false);

  const bad = gate.plan({ gate: true, reason: 'unavailable' }, { reason: '服务端未响应' });
  assert.equal(bad.gateState, 'error');
  assert.equal(bad.retry, true, 'error 态必须给出「重新连接」这个出口');
  assert.ok(bad.status.includes('无法确认登录状态'), 'error 文案要说清是连不上，不是账号问题');

  const busy = gate.plan({ gate: true, reason: 'anonymous' }, { busy: true });
  assert.equal(busy.gateState, 'disabled');
  assert.ok(busy.status.includes('正在提交'));

  const ok = gate.plan({ gate: false, reason: 'authed' });
  assert.equal(ok.action, 'close');
  assert.equal(ok.forced, false);

  const exempt = gate.plan({ gate: false, reason: 'exempt' });
  assert.equal(exempt.action, 'none');
  assert.equal(exempt.forced, false, '豁免页不得被强制');
});

test('apply()：匿名时开强制弹窗、已登录时关；error 态给出重试入口', async () => {
  // 注意：脚本加载时 init() 会**自己**问一次服务端并装配弹窗（异步落地）。
  // 所以每条用例先 await 一个 microtask 把它清掉，再断言"手动 apply 做了什么"。
  const anon = loadGate({ me: { ok: true, logged_in: false, user: null } });
  await Promise.resolve();
  anon.gate.apply(anon.gate.decide('/pages/resume-evidence.html', { ok: true, logged_in: false }), {});
  assert.deepEqual(anon.calls[anon.calls.length - 1], { action: 'open', tab: null, forced: true });
  assert.equal(anon.dom.els.zyAuthModal.getAttribute('data-forced'), 'true');
  assert.equal(anon.dom.els.zyAuthModal.getAttribute('data-gate-state'), 'empty');

  const authed = loadGate({ me: { ok: true, logged_in: true, user: { name: '小张' } } });
  await Promise.resolve();
  authed.gate.apply(authed.gate.decide('/pages/resume-evidence.html', { ok: true, logged_in: true, user: {} }), {});
  assert.equal(authed.calls[authed.calls.length - 1].action, 'close');
  assert.equal(authed.dom.els.zyAuthModal.getAttribute('data-gate'), 'authed');

  const dead = loadGate({ me: { ok: false, reason: '断网' } });
  await Promise.resolve();
  const before = dead.calls.length;
  const result = dead.gate.apply(dead.gate.decide('/pages/resume-evidence.html', { ok: false, reason: '断网' }), { reason: '断网' });
  assert.equal(result.gateState, 'error');
  assert.equal(dead.dom.els.zyGateRetry.classList.contains('zy-hidden'), false, 'error 态必须露出重试按钮');
  assert.equal(dead.calls.length, before + 1, '拿不到登录态时也要开弹窗（不是放行）');
});

test('check() 走服务端：断网不放行，重试会再问一次服务端', async () => {
  const offline = loadGate({ me: { ok: false, reason: '断网' } });
  // 基线不是 0：脚本加载时 init() 自己就会问一次。这条基线本身也是判据 ——
  // 首屏必须**主动**问一次服务端，否则"问之前"就是一段不受控的画面。
  assert.equal(offline.meCalls(), 1, '政策层加载时就该向服务端问一次登录态');
  await Promise.resolve();

  const decision = await offline.gate.check();
  assert.equal(decision.gate, true, '服务端不可用时必须拦下');
  assert.equal(decision.reason, 'unavailable');
  assert.equal(offline.meCalls(), 2);

  // 点「重新连接」→ 必须重新问一次服务端（而不是拿本地状态糊过去）
  const handler = offline.listeners['zyGateRetry:click'][0];
  handler();
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(offline.meCalls(), 3, '重试没有重新请求服务端');

  const online = loadGate({ me: { ok: true, logged_in: true, user: { name: '小张' } } });
  await Promise.resolve();
  const before = online.calls.length;
  const ok = await online.gate.check();
  assert.equal(ok.gate, false);
  assert.equal(ok.reason, 'authed');
  assert.ok(online.calls.length > before, '拿到已登录答复后必须关掉弹窗');
  assert.equal(online.calls[online.calls.length - 1].action, 'close');
});

test('只有服务端答复能放行：本地塞满标记也没用', async () => {
  // 这条是 D7 的安全底线。用**行为**锁，而不是读源码：
  // 政策层拿到的是带存取陷阱的假存储（键名故意起得像真的），
  // 只要它读过一次就会被记下来。服务端说未登录时，仍然必须被拦。
  const env = loadGate({ me: { ok: true, logged_in: false, user: null }, trapStorage: true });
  const decision = await env.gate.check();
  assert.equal(decision.gate, true, '本地标记必须无法放行');
  assert.equal(decision.reason, 'anonymous');
  assert.equal(env.calls[env.calls.length - 1].forced, true, '仍然必须是强制弹窗');
  // 最强的形式：不是"读了但没用"，而是**一次都没碰过**
  assert.deepEqual(env.touched.filter(t => t !== 'ownKeys'), [],
    '政策层碰过本地存储 / cookie：' + env.touched.join(','));
});

test('豁免页（内部 QA 状态墙）不弹门禁，但仍加载同一套装配', async () => {
  const exempt = loadGate({ pathname: '/pages/states.html', me: { ok: true, logged_in: false, user: null } });
  const decision = await exempt.gate.check();
  assert.equal(decision.reason, 'exempt');
  assert.equal(decision.gate, false, '豁免 = 不拦');
  assert.equal(decision.mode, 'exempt', 'check() 同时给出计划的 mode（键名与 gate 错开）');
  assert.equal(exempt.calls.length, 0, '豁免页不该打开弹窗');
  assert.equal(exempt.dom.els.zyAuthModal.getAttribute('data-gate'), 'exempt');
  assert.equal(exempt.dom.els.zyAuthModal.getAttribute('data-gate-state'), 'disabled');
});

// ── ⑥ 判据自检：这些检查必须能失败 ──────────────────────────────

test('这一组判据本身不是空转', () => {
  // 页面集合与文件都真实存在
  assert.ok(PAGES.length === 7, '页面集合变了，判据的覆盖面要重新确认：' + PAGES.length);
  for (const rel of PAGES) {
    assert.ok(fs.existsSync(path.join(root, 'public', rel)), 'public/' + rel + ' 不存在');
    assert.ok(fs.existsSync(path.join(root, 'docs', rel)), 'docs/' + rel + ' 不存在');
  }
  // 豁免名单解析不是空集，也不是硬编码在判据里（真的来自 auth-gate.js）
  assert.deepEqual(exemptList('public'), ['/pages/states.html']);
  // 探针：假的 auth-gate.js 内容必须让解析与断言失败
  const fake = 'var EXEMPT = [];';
  const m = fake.match(/var EXEMPT = (\[[^\]]*\]);/);
  assert.deepEqual(JSON.parse(m[1]), [], '探针失效：解析器读不出空名单');
  assert.notDeepEqual(JSON.parse(m[1]), ['/pages/states.html'], '探针失效：空名单竟等于期望值');
  // 探针：脚本顺序探针确实能区分顺序
  const wrongOrder = [...'<script src="../js/auth-gate.js"></script><script src="../js/account.js"></script>'
    .matchAll(/src="[^"]*js\/(account|auth-gate)\.js"/g)].map(x => x[1]);
  assert.deepEqual(wrongOrder, ['auth-gate', 'account'], '探针失效：顺序扫描看不出反序');

  // 探针：codeOnly 必须**剥掉注释**、但**保留字符串与代码**
  assert.equal(codeOnly('// 本文件不读 localStorage').includes('localStorage'), false,
    '探针失效：行注释里的 localStorage 没被剥掉（判据会误报）');
  assert.equal(codeOnly('/* localStorage 在这里也只是说明 */').includes('localStorage'), false,
    '探针失效：块注释里的 localStorage 没被剥掉');
  assert.ok(codeOnly('var x = localStorage.getItem("k");').includes('localStorage'),
    '探针失效：真用了 localStorage 却没被抓到（判据会永远全绿）');
  assert.ok(codeOnly("var u = '/auth/me';").includes('/auth/me'),
    '探针失效：字符串字面量被当成注释剥掉了');
  assert.ok(codeOnly('var a = "http://x";').includes('http://x'),
    '探针失效：字符串里的 // 被误当行注释');
  assert.ok(codeOnly('/* c */ var y = 1; /* d */').includes('var y = 1;'),
    '探针失效：块注释剥离把注释之间的代码也吃掉了');

  // 探针：vm realm 的对象确实与宿主不同原型 —— 这是 flat() 存在的前提，
  // 若哪天不再成立，flat() 就是在给一个不存在的问题打补丁，得重新想。
  const vmV = new vm.Script('({ gate: false, reason: "authed" })').runInNewContext();
  assert.notEqual(Object.getPrototypeOf(vmV), Object.prototype,
    '探针失效：vm 里的对象竟与宿主同原型（flat() 的前提不成立，判据需重审）');
  assert.ok(Object.getPrototypeOf(flat(vmV)) === Object.prototype,
    '探针失效：flat() 没能把对象带回宿主 realm');
  assert.equal(flat(vmV).reason, 'authed', '探针失效：flat() 丢了字段');

  // 探针：陷阱存储真的会记录访问（否则 #13 的"一次都没碰过"是空判）
  const seen = [];
  const trapped = trappingStorage(seen);
  void trapped.zy_logged_in; void trapped.token;
  assert.deepEqual(seen, ['get:zy_logged_in', 'get:token'],
    '探针失效：陷阱存储没有记录访问');
});
