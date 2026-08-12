/* account.js · 个人账号 + 历史记录（真实后端 API 客户端）
 *
 * 数据来源：/api/auth/* 与 /api/history/*。
 * 可见性规则：
 *   - 未登录游客：不展示任何历史记录；
 *   - 已登录用户：仅展示本人记录；
 *   - 演示数据：仅服务端在 role=admin 且 DEV_DEMO=1 时注入（不落库）。
 */
(function () {
  'use strict';

  var API_BASE = window.DUMATE_API_BASE || 'https://career-coach-omega-three.vercel.app';
  var KEY_COLLAPSED = 'zy_sidebar_collapsed';
  var currentUser = null;

  var inPages = /\/pages\//.test(location.pathname);
  var pageBase = inPages ? '' : 'pages/';

  function $(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function fmtDate(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    var p = function (n) { return n < 10 ? '0' + n : '' + n; };
    return (d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function setMsg(text, ok) {
    var el = $('zyAuthMsg');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'zy-form-msg ' + (ok ? 'ok' : text ? 'err' : '');
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

  function api(path, options) {
    options = options || {};
    var opts = {
      method: options.method || 'GET',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' }
    };
    if (options.body) opts.body = JSON.stringify(options.body);
    return fetch(API_BASE + '/api' + path, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok || data.error) {
          var err = new Error((data && data.message) || ('请求失败（' + res.status + '）'));
          err.code = (data && data.error) || 'request_failed';
          throw err;
        }
        return data;
      });
    });
  }

  /* ---------- 用户卡 ---------- */
  function renderUser(user) {
    currentUser = user || null;
    var avatar = $('zyAvatar'), name = $('zyUserName'), sub = $('zyUserSub');
    var loginBtn = $('zyLoginBtn'), logoutBtn = $('zyLogoutBtn');
    if (!avatar || !name || !sub) return;
    if (user) {
      avatar.textContent = (user.name || '我').charAt(0);
      name.textContent = user.name;
      var maskedPhone = String(user.phone || '').replace(/(\d{3})\d{4}(\d{4})/, '$1****$2');
      sub.textContent = maskedPhone + ' · ' + user.email + (user.role === 'admin' ? '（管理员）' : '');
      if (loginBtn) loginBtn.classList.add('zy-hidden');
      if (logoutBtn) logoutBtn.classList.remove('zy-hidden');
    } else {
      avatar.textContent = '访';
      name.textContent = '未登录游客';
      sub.textContent = '登录后历史可长期保存';
      if (loginBtn) loginBtn.classList.remove('zy-hidden');
      if (logoutBtn) logoutBtn.classList.add('zy-hidden');
    }
  }

  /* ---------- 历史列表 ---------- */
  function renderHistory(items) {
    var list = $('zyHistoryList'), empty = $('zyHistoryEmpty');
    if (!list) return;
    items = items || [];
    if (!items.length) {
      list.innerHTML = '';
      if (empty) empty.classList.remove('zy-hidden');
      return;
    }
    if (empty) empty.classList.add('zy-hidden');
    list.innerHTML = items.slice(0, 50).map(function (it) {
      var st = it.status === 'done' ? '已完成' : it.status === 'partial' ? '进行中' : '失败';
      var isDemo = typeof it.id === 'number' && it.id < 0;
      var type = it.event_type || it.type || '';
      return '<li class="zy-history-item" data-id="' + esc(it.id) + '">' +
        '<span class="zy-badge">' + esc(type) + '</span>' +
        '<span class="zy-history-meta">' +
          '<span class="zy-history-title-line">' + esc(it.title) + '</span>' +
          '<span class="zy-history-time">' + esc(fmtDate(it.created_at)) + ' · ' + st + '</span>' +
        '</span>' +
        (isDemo ? '' : '<button type="button" class="zy-history-del" title="删除该条记录">×</button>') +
      '</li>';
    }).join('');

    list.querySelectorAll('.zy-history-del').forEach(function (btn) {
      btn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        var li = btn.closest('.zy-history-item');
        var id = li.getAttribute('data-id');
        api('/history/' + encodeURIComponent(id), { method: 'DELETE' }).then(function () {
          loadHistory();
          toast('记录已删除');
        }).catch(function (err) {
          toast(err.message || '删除失败');
        });
      });
    });
    list.querySelectorAll('.zy-history-item').forEach(function (li) {
      li.addEventListener('click', function () {
        var id = li.getAttribute('data-id');
        var it = (items || []).filter(function (x) { return String(x.id) === id; })[0];
        if (!it || (typeof it.id === 'number' && it.id < 0)) return;
        var target = pageBase + {
          F1: 'f1-resume.html', F2: 'f2-match.html', F3: 'f3-interview.html', F4: 'f4-report.html'
        }[it.event_type];
        if (!target) return;
        location.href = target + '?session=' + encodeURIComponent(it.session_id);
      });
    });
  }

  function loadHistory() {
    api('/history?limit=50').then(function (data) {
      renderHistory(data.items || []);
    }).catch(function () {
      renderHistory([]);
    });
  }

  function refreshAuth() {
    return api('/auth/me').then(function (data) {
      var user = data.logged_in ? data.user : null;
      renderUser(user);
      if (user) loadHistory(); else renderHistory([]);
      return user;
    }).catch(function () {
      renderUser(null);
      renderHistory([]);
      return null;
    });
  }

  /* ---------- 账号弹窗 ---------- */
  function openModal(tab) {
    var modal = $('zyAuthModal');
    if (!modal) return;
    modal.classList.remove('zy-hidden');
    switchTab(tab || (currentUser ? 'login' : 'register'));
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
    var loginForm = $('zyLoginForm'), regForm = $('zyRegisterForm');
    if (loginForm) loginForm.classList.toggle('zy-hidden', tab !== 'login');
    if (regForm) regForm.classList.toggle('zy-hidden', tab !== 'register');
    setMsg('', false);
  }

  function handleSubmit(ev) {
    ev.preventDefault();
    var f = ev.target;
    var isRegister = f.id === 'zyRegisterForm';
    var payload;
    if (isRegister) {
      payload = {
        phone: f.phone.value.trim(),
        email: f.email.value.trim(),
        password: f.emailPwd.value,
        name: f.name.value.trim()
      };
    } else {
      payload = { account: f.account.value.trim(), password: f.password.value };
    }
    api(isRegister ? '/auth/register' : '/auth/login', { method: 'POST', body: payload })
      .then(function (user) {
        setMsg('', false);
        closeModal();
        refreshAuth();
        toast(isRegister ? '注册成功，欢迎你，' + user.name + ' 🎉' : '已登录：' + user.name);
        f.reset();
      })
      .catch(function (err) {
        setMsg(err.message, false);
      });
  }

  function logout() {
    api('/auth/logout', { method: 'POST' }).catch(function () { /* ignore */ })
      .then(function () {
        renderUser(null);
        renderHistory([]);
        toast('已退出登录');
      });
  }

  function toggleSidebar() {
    if (window.innerWidth <= 900) {
      document.body.classList.toggle('zy-drawer-open');
    } else {
      document.body.classList.toggle('zy-sidebar-collapsed');
      try {
        localStorage.setItem(KEY_COLLAPSED, document.body.classList.contains('zy-sidebar-collapsed') ? '1' : '0');
      } catch (e) { /* ignore */ }
    }
  }

  function showRecallBar() {
    var sid = new URLSearchParams(location.search).get('session');
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

  function addHistory(item) {
    if (!currentUser) {
      toast('注册登录后，检测记录可长期保存');
      return Promise.resolve(false);
    }
    return api('/history', { method: 'POST', body: item }).then(function () {
      loadHistory();
      return true;
    }).catch(function () {
      return false;
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

    var note = $('zyDemoNote');
    if (note) note.classList.add('zy-hidden');
    var addBtn = $('zyAddRecord');
    if (addBtn) addBtn.classList.add('zy-hidden');

    renderUser(null);
    renderHistory([]);
    refreshAuth();
    showRecallBar();

    var toggle = $('zySidebarToggle');
    if (toggle) toggle.addEventListener('click', toggleSidebar);
    var backdrop = $('zySidebarBackdrop');
    if (backdrop) backdrop.addEventListener('click', function () { document.body.classList.remove('zy-drawer-open'); });
    var loginBtn = $('zyLoginBtn');
    if (loginBtn) loginBtn.addEventListener('click', function () { openModal('login'); });
    var logoutBtn = $('zyLogoutBtn');
    if (logoutBtn) logoutBtn.addEventListener('click', logout);
    var closeBtn = $('zyAuthClose');
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    var modal = $('zyAuthModal');
    if (modal) modal.addEventListener('click', function (ev) { if (ev.target === modal) closeModal(); });
    document.querySelectorAll('.zy-tab').forEach(function (b) {
      b.addEventListener('click', function () { switchTab(b.getAttribute('data-tab')); });
    });
    var loginForm = $('zyLoginForm');
    if (loginForm) loginForm.addEventListener('submit', handleSubmit);
    var regForm = $('zyRegisterForm');
    if (regForm) regForm.addEventListener('submit', handleSubmit);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.ZY_ACCOUNT = {
    addHistory: addHistory,
    refreshAuth: refreshAuth,
    currentUser: function () { return currentUser; }
  };
})();
