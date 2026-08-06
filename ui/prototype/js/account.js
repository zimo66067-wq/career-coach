/* account.js · 个人账号 + 历史记录（演示原型，数据仅存 localStorage） */
(function () {
  'use strict';

  var KEY_ACCOUNT = 'zy_account';
  var KEY_HISTORY = 'zy_history';
  var KEY_COLLAPSED = 'zy_sidebar_collapsed';
  var TYPES = { F1: '简历诊断', F2: '岗位匹配', F3: '模拟面试', F4: '能力报告' };

  var seed = [
    { id: 's1', type: 'F1', title: '后端开发简历诊断 · R82', date: ago(2), status: 'done' },
    { id: 's2', type: 'F2', title: '后端开发工程师（校招）匹配', date: ago(2), status: 'done' },
    { id: 's3', type: 'F3', title: '3 轮模拟面试 · 追问 4 次', date: ago(1), status: 'partial' },
    { id: 's4', type: 'F4', title: '六维能力报告 · C0=68.3', date: ago(1), status: 'done' },
    { id: 's5', type: 'F1', title: '数据分析简历诊断 · R74', date: ago(0), status: 'done' },
    { id: 's6', type: 'F2', title: '数据分析师 JD 匹配 · 缺口 3 项', date: ago(0), status: 'partial' }
  ];
  var extraTitles = [
    ['F1', '产品经理简历诊断 · R68'],
    ['F2', '测试工程师 JD 匹配'],
    ['F3', '算法岗模拟面试 · 追问 2 次'],
    ['F4', '能力报告 · C0=71.4']
  ];
  var extraIdx = 0;
  var inPages = /\/pages\//.test(location.pathname);
  var pageBase = inPages ? '' : 'pages/';

  function ago(days) {
    var d = new Date(Date.now() - days * 864e5);
    var p = function (n) { return n < 10 ? '0' + n : '' + n; };
    return (d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function load(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      if (raw === null) return fallback;
      return JSON.parse(raw);
    } catch (e) { return fallback; }
  }

  function save(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* ignore */ }
  }

  function account() { return load(KEY_ACCOUNT, null); }
  function history() {
    var h = load(KEY_HISTORY, null);
    if (h === null) { h = seed.slice(); save(KEY_HISTORY, h); }
    return h;
  }

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function setMsg(text, ok) {
    var el = $('zyAuthMsg');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'zy-form-msg ' + (ok ? 'ok' : text ? 'err' : '');
  }

  /* ---------- 用户卡 ---------- */
  function renderUser() {
    var acc = account();
    var avatar = $('zyAvatar'), name = $('zyUserName'), sub = $('zyUserSub');
    var loginBtn = $('zyLoginBtn'), logoutBtn = $('zyLogoutBtn');
    if (!avatar) return;
    if (acc) {
      avatar.textContent = (acc.name || '我').charAt(0);
      name.textContent = acc.name;
      sub.textContent = acc.phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2') + ' · ' + acc.email;
      loginBtn.classList.add('zy-hidden');
      logoutBtn.classList.remove('zy-hidden');
    } else {
      avatar.textContent = '访';
      name.textContent = '未登录游客';
      sub.textContent = '登录后历史可长期保存';
      loginBtn.classList.remove('zy-hidden');
      logoutBtn.classList.add('zy-hidden');
    }
  }

  /* ---------- 历史列表 ---------- */
  function renderHistory() {
    var list = $('zyHistoryList'), empty = $('zyHistoryEmpty'), note = $('zyDemoNote');
    if (!list) return;
    var items = history();
    list.innerHTML = items.slice(0, 50).map(function (it) {
      var st = it.status === 'done' ? '已完成' : it.status === 'partial' ? '进行中' : '失败';
      return '<li class="zy-history-item" data-id="' + esc(it.id) + '">' +
        '<span class="zy-badge">' + esc(it.type) + '</span>' +
        '<span class="zy-history-meta">' +
          '<span class="zy-history-title-line">' + esc(it.title) + '</span>' +
          '<span class="zy-history-time">' + esc(it.date) + ' · ' + st + '</span>' +
        '</span>' +
        '<button type="button" class="zy-history-del" title="删除该条记录">×</button>' +
      '</li>';
    }).join('');
    empty.classList.toggle('zy-hidden', items.length > 0);
    note.classList.toggle('zy-hidden', items.length > 0);
    list.querySelectorAll('.zy-history-del').forEach(function (btn) {
      btn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        var li = btn.closest('.zy-history-item');
        var id = li.getAttribute('data-id');
        save(KEY_HISTORY, history().filter(function (x) { return x.id !== id; }));
        renderHistory();
      });
    });
    list.querySelectorAll('.zy-history-item').forEach(function (li) {
      li.addEventListener('click', function () {
        var id = li.getAttribute('data-id');
        var it = history().filter(function (x) { return x.id === id; })[0];
        if (!it) return;
        var target = pageBase + {
          F1: 'f1-resume.html', F2: 'f2-match.html', F3: 'f3-interview.html', F4: 'f4-report.html'
        }[it.type];
        location.href = target + '?session=' + encodeURIComponent(id);
      });
    });
  }

  function addMockRecord() {
    var pick = extraTitles[extraIdx % extraTitles.length];
    extraIdx += 1;
    var items = history();
    items.unshift({
      id: 'm' + Date.now(),
      type: pick[0],
      title: pick[1],
      date: ago(0),
      status: Math.random() > 0.3 ? 'done' : 'partial'
    });
    save(KEY_HISTORY, items);
    renderHistory();
  }

  /* ---------- 账号弹窗 ---------- */
  function openModal(tab) {
    var modal = $('zyAuthModal');
    if (!modal) return;
    modal.classList.remove('zy-hidden');
    switchTab(tab || (account() ? 'login' : 'register'));
  }
  function closeModal() {
    var modal = $('zyAuthModal');
    if (modal) modal.classList.add('zy-hidden');
    setMsg('', false);
  }

  function switchTab(tab) {
    document.querySelectorAll('.zy-tab').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-tab') === tab);
    });
    $('zyLoginForm').classList.toggle('zy-hidden', tab !== 'login');
    $('zyRegisterForm').classList.toggle('zy-hidden', tab !== 'register');
    setMsg('', false);
  }

  function register(ev) {
    ev.preventDefault();
    var f = ev.target;
    var phone = f.phone.value.trim();
    var email = f.email.value.trim();
    var pwd = f.emailPwd.value;
    var name = f.name.value.trim();
    if (!/^1\d{10}$/.test(phone)) return setMsg('手机号格式不正确（11 位，1 开头）', false);
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return setMsg('邮箱格式不正确', false);
    if (pwd.length < 8 || !/[A-Za-z]/.test(pwd) || !/\d/.test(pwd)) return setMsg('密码至少 8 位且需包含字母和数字', false);
    if (name.length < 2 || name.length > 16) return setMsg('账户名需 2-16 个字符', false);
    save(KEY_ACCOUNT, { name: name, phone: phone, email: email, pwd: pwd, created_at: new Date().toISOString() });
    renderUser();
    closeModal();
    toast('注册成功，欢迎你，' + name + ' 🎉');
  }

  function login(ev) {
    ev.preventDefault();
    var f = ev.target;
    var acc = account();
    var input = f.account.value.trim();
    var pwd = f.password.value;
    if (!acc) return setMsg('还没有账户，请先切换到「注册」', false);
    var okAccount = input === acc.phone || input === acc.email;
    if (!okAccount || pwd !== acc.pwd) return setMsg('手机号/邮箱或密码不正确', false);
    acc.last_login_at = new Date().toISOString();
    save(KEY_ACCOUNT, acc);
    renderUser();
    closeModal();
    toast('已登录：' + acc.name);
  }

  function logout() {
    var acc = account();
    save(KEY_ACCOUNT, null);
    renderUser();
    toast(acc ? '已退出登录' : '当前为游客状态');
  }

  /* ---------- 顶栏开关 / 抽屉 / 回看条 ---------- */
  function toggleSidebar() {
    if (window.innerWidth <= 900) {
      document.body.classList.toggle('zy-drawer-open');
    } else {
      document.body.classList.toggle('zy-sidebar-collapsed');
      try { localStorage.setItem(KEY_COLLAPSED, document.body.classList.contains('zy-sidebar-collapsed') ? '1' : '0'); } catch (e) { /* ignore */ }
    }
  }

  function toast(text) {
    var bar = $('zyToast');
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'zyToast';
      bar.style.cssText = 'position:fixed;left:50%;transform:translateX(-50%);top:70px;z-index:90;background:#161e34;color:#fff;font-size:13px;padding:10px 16px;border-radius:999px;box-shadow:0 8px 24px rgba(15,20,38,.3);transition:opacity .2s ease;';
      document.body.appendChild(bar);
    }
    bar.textContent = text;
    bar.style.opacity = '1';
    clearTimeout(bar._t);
    bar._t = setTimeout(function () { bar.style.opacity = '0'; }, 2600);
  }

  function showRecallBar() {
    var params = new URLSearchParams(location.search);
    var sid = params.get('session');
    if (!sid) return;
    var bar = document.createElement('div');
    bar.className = 'zy-recall-bar';
    bar.innerHTML = '正在回看记录 <b>' + esc(sid) + '</b>' +
      '<button type="button" id="zyRecallClose">退出回看</button>';
    document.body.appendChild(bar);
    $('zyRecallClose').addEventListener('click', function () {
      location.href = location.pathname;
    });
  }

  /* ---------- 初始化 ---------- */
  function init() {
    document.body.classList.add('zy-has-sidebar');
    try {
      if (localStorage.getItem(KEY_COLLAPSED) === '1' && window.innerWidth > 900) {
        document.body.classList.add('zy-sidebar-collapsed');
      }
    } catch (e) { /* ignore */ }
    renderUser();
    renderHistory();
    showRecallBar();

    var toggle = $('zySidebarToggle');
    if (toggle) toggle.addEventListener('click', toggleSidebar);
    var backdrop = $('zySidebarBackdrop');
    if (backdrop) backdrop.addEventListener('click', function () { document.body.classList.remove('zy-drawer-open'); });
    var loginBtn = $('zyLoginBtn');
    if (loginBtn) loginBtn.addEventListener('click', function () { openModal('login'); });
    var logoutBtn = $('zyLogoutBtn');
    if (logoutBtn) logoutBtn.addEventListener('click', logout);
    var addBtn = $('zyAddRecord');
    if (addBtn) addBtn.addEventListener('click', addMockRecord);
    var clearBtn = $('zyHistoryClear');
    if (clearBtn) clearBtn.addEventListener('click', function () {
      save(KEY_HISTORY, []);
      renderHistory();
      toast('历史已清空');
    });
    var closeBtn = $('zyAuthClose');
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    var modal = $('zyAuthModal');
    if (modal) modal.addEventListener('click', function (ev) { if (ev.target === modal) closeModal(); });
    document.querySelectorAll('.zy-tab').forEach(function (b) {
      b.addEventListener('click', function () { switchTab(b.getAttribute('data-tab')); });
    });
    var loginForm = $('zyLoginForm');
    if (loginForm) loginForm.addEventListener('submit', login);
    var regForm = $('zyRegisterForm');
    if (regForm) regForm.addEventListener('submit', register);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.ZY_ACCOUNT = {
    addHistory: function (item) {
      var h = history();
      h.unshift(item);
      save(KEY_HISTORY, h.slice(0, 50));
      renderHistory();
    }
  };
})();
