/* auth-gate.js · D7「进入即强制注册/登录」的政策层
 *
 * 分工：account.js 是**机制**（弹窗、表单、/api/auth/* 调用），本文件是**政策**
 * （谁被拦、什么时候拦、能不能关掉）。这样分工是为了可判据化：政策全收在
 * decide() / plan() 两个**纯函数**里，不碰 DOM 就能驱动与断言。
 *
 * 两层返回值的键名**刻意错开**，不要合并回一个 `gate`：
 *   decide() → { gate: 布尔, reason: 'authed' | 'anonymous' | 'unavailable' | 'exempt' }
 *   plan()   → { action, mode: 'exempt' | 'authed' | 'forced', gateState, forced, retry, status }
 *   check()  → 决策本体（gate 布尔 + reason）+ 计划的呈现字段（mode / gateState / forced）
 * 早先两层同用一个 `gate` 键、语义还相反：豁免页 plan().gate === 'exempt' 是**真值**，
 * 而 decide().gate === false 意思是"别拦"。同一个键两种语义是等着被踩的坑（6b-3 修）。
 *
 * 安全口径（D7 不得回退的性质，全部留在服务端，本层不参与实现）：
 *   - 登录态**只**由服务端 GET /api/auth/me 判定。本文件不读 localStorage /
 *     sessionStorage，也不做任何"本地有标记即已登录"的短路 —— 前端一句
 *     `loggedIn = true` 就能绕过的门禁不是门禁。
 *   - 拿不到服务端答复时**判为拦下**（unavailable），不判为放行：
 *     "不知道"与"是游客"是两件事，把前者当后者等于给断网开了后门。
 *   - HttpOnly Session / 密码哈希 / 授权校验 / 归属隔离 / 删除链路 / 限流
 *     一律由服务端保证，本层不放宽任何一条。
 *
 * 可访问性（product-scope.md §10.3）：
 *   - 弹窗是**原生 `<dialog>`**：showModal() 自带焦点陷阱、Esc、::backdrop；
 *   - 强制态下拦下 Esc（cancel 事件）并隐藏关闭按钮 —— 门禁必须关不掉；
 *   - 但**页面本身始终可见**，不清空、不报错：门禁只把交互挡在后面，
 *     满足"不得让任何页面在未登录时出现空白或不可用"。
 *   - 三种状态显式存在并可断言：empty（默认）/ error（拿不到登录态）/
 *     disabled（提交中，或该页门禁关闭）。
 */
(function () {
  'use strict';

  /* 豁免名单：**刻意**只有一项 —— 内部 QA 状态墙（不进导航、不含任何用户数据，
   * 且它的用途就是预览包含 empty 在内的六种界面状态，加门禁会让自己不可用）。
   * 有判据把这个名单锁成"恰好 ['/pages/states.html']"，防止它被随手扩容。 */
  var EXEMPT = ['/pages/states.html'];

  var DIALOG_ID = 'zyAuthModal';

  /* 把任意 URL/路径归一成 /index.html 或 /pages/xxx.html 形式，便于比对豁免名单。 */
  function normalize(pathname) {
    var p = String(pathname == null ? '/' : pathname).split('?')[0].split('#')[0];
    var i = p.indexOf('/pages/');
    if (i >= 0) return p.slice(i);
    if (p === '' || p === '/' || /\/index\.html$/.test(p)) return '/index.html';
    return p;
  }

  function isExempt(pathname) {
    return EXEMPT.indexOf(normalize(pathname)) >= 0;
  }

  /* 纯决策：`me` 是 account.js 从服务端拿到并**原样**转交的答复。
   *   { ok: true,  logged_in: true,  user: {...} }  → authed（放行）
   *   { ok: true,  logged_in: false, user: null  }  → anonymous（拦下）
   *   { ok: false, reason: '...' }                  → unavailable（拦下，且是"不知道"）
   */
  function decide(pathname, me) {
    if (isExempt(pathname)) return { gate: false, reason: 'exempt' };
    if (!me || me.ok !== true) return { gate: true, reason: 'unavailable' };
    if (me.logged_in === true && me.user) return { gate: false, reason: 'authed' };
    return { gate: true, reason: 'anonymous' };
  }

  /* 纯计划：把决策翻译成"该对弹窗做什么"。DOM 只由 apply() 写，
   * 判据直接测这一层即可（不需要浏览器）。
   * 注意返回的 `mode` 不是 `decide()` 的 `gate`：前者是给 data-gate 用的**模式名**
   * （字符串，'exempt' / 'authed' / 'forced'），后者是"要不要拦"的**布尔**。
   * opts: { reason: 失败原因文本, busy: 表单是否正在提交 } */
  function plan(decision, opts) {
    opts = opts || {};
    if (decision.reason === 'exempt') {
      return { action: 'none', mode: 'exempt', gateState: 'disabled', forced: false,
               retry: false, status: '' };
    }
    if (decision.reason === 'authed') {
      return { action: 'close', mode: 'authed', gateState: 'empty', forced: false,
               retry: false, status: '' };
    }
    if (decision.reason === 'unavailable') {
      return { action: 'open', mode: 'forced', gateState: 'error', forced: true, retry: true,
               status: '无法确认登录状态：' + (opts.reason || '服务端未响应') +
                       '。这不是你的账号问题，请点「重新连接」。' };
    }
    if (opts.busy) {
      return { action: 'open', mode: 'forced', gateState: 'disabled', forced: true, retry: false,
               status: '正在提交…' };
    }
    return { action: 'open', mode: 'forced', gateState: 'empty', forced: true, retry: false,
             status: '首次使用：手机号、邮箱、密码、账户名四项即可注册，约 30 秒。' };
  }

  /* ---------------- 以下为 DOM 应用层（判据不依赖它） ---------------- */

  var state = { busy: false, decision: null, reason: '' };

  function el(id) {
    return document.getElementById(id);
  }

  function apply(decision, opts) {
    opts = opts || {};
    state.decision = decision;
    var result = plan(decision, opts);
    var dialog = el(DIALOG_ID);
    if (!dialog) return result;

    dialog.setAttribute('data-gate', result.mode);
    dialog.setAttribute('data-gate-state', result.gateState);
    dialog.setAttribute('data-forced', result.forced ? 'true' : 'false');

    var status = el('zyGateStatus');
    if (status) {
      status.textContent = result.status;
      status.className = 'zy-gate-status' + (result.gateState === 'error' ? ' err' : '');
    }
    var retry = el('zyGateRetry');
    if (retry) retry.classList.toggle('zy-hidden', !result.retry);
    var closeBtn = el('zyAuthClose');
    if (closeBtn) closeBtn.classList.toggle('zy-hidden', result.forced);

    var account = window.ZY_ACCOUNT;
    if (result.action === 'open' && account && typeof account.openAuth === 'function') {
      account.openAuth(null, { forced: result.forced });
    } else if (result.action === 'close' && account && typeof account.closeAuth === 'function') {
      account.closeAuth();
    }
    return result;
  }

  function readMe() {
    var account = window.ZY_ACCOUNT;
    if (!account || typeof account.refreshAuth !== 'function') {
      return Promise.resolve({ ok: false, reason: '账号模块未加载' });
    }
    return account.refreshAuth();
  }

  function check() {
    return readMe().then(function (me) {
      state.reason = (me && me.ok === true) ? '' : ((me && me.reason) || '服务端未响应');
      var decision = decide(location.pathname, me);
      var result = apply(decision, { reason: state.reason, busy: state.busy });
      /* 返回**决策**（能不能进 + 为什么），而不是计划（怎么摆弹窗）。
       * 调用方问的是"这页能不能进"；计划是实现细节。两层键名已错开，
       * 所以合并没有覆盖风险（gate 是布尔、mode 是字符串）。 */
      return Object.assign({}, decision, {
        mode: result.mode, gateState: result.gateState,
        forced: result.forced, action: result.action
      });
    });
  }

  function notify(ev) {
    if (typeof CustomEvent !== 'function') return;
    document.dispatchEvent(new CustomEvent(ev, { detail: state }));
  }

  function bind() {
    var retry = el('zyGateRetry');
    if (retry) {
      retry.addEventListener('click', function () {
        retry.disabled = true;
        check().finally(function () { retry.disabled = false; });
      });
    }
    // 登录/注册成功 → 重新判定（不必让页面自己再查一次）
    document.addEventListener('zy:auth', function () { check(); });
    // 表单提交中 → Disabled 态
    document.addEventListener('zy:auth-busy', function (ev) {
      state.busy = !!(ev && ev.detail && ev.detail.busy);
      if (state.decision) apply(state.decision, { reason: state.reason, busy: state.busy });
    });
  }

  function init() {
    bind();
    notify('zy:gate-ready');
    return check();
  }

  window.ZY_GATE = {
    EXEMPT: EXEMPT,
    normalize: normalize,
    isExempt: isExempt,
    decide: decide,
    plan: plan,
    apply: apply,
    check: check,
    init: init,
    state: function () { return state; }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
