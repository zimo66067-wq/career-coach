/* quick-demo.js · 一键体验（Quick Demo，P0-1）
 *
 * 游客无需注册、无需上传：一键填充样例简历与专业/JD，
 * 优先走真实 API（无模型 key 时后端规则降级），API 不可用时退回演示数据。
 * 任何演示结果都必须显示"演示数据"标注，绝不伪装成用户真实结果。
 *
 * 用法：
 *   <button id="quickDemoF1" type="button">一键体验 F1</button>
 *   <script src="js/quick-demo.js"></script>
 *   或直接访问 f1-resume.html?quick=1 / f2-match.html?quick=1 自动执行。
 */
(function () {
  'use strict';

  var DEMO_JD = [
    '岗位职责：',
    '1. 负责订单中心微服务的设计、开发与维护，保障接口稳定性与响应性能；',
    '2. 参与库存扣减、支付回调等核心链路的方案设计与问题排查；',
    '3. 编写接口文档并推动前后端联调。',
    '任职要求：',
    '1. 本科及以上学历，计算机相关专业；',
    '2. 熟悉 Java 或 Go，了解 Spring Boot / Gin 等框架；',
    '3. 熟悉 MySQL、Redis，理解常用数据结构与基础算法；',
    '4. 了解分布式系统基础知识（锁、消息队列）者优先。'
  ].join('\n');

  function $(id) { return document.getElementById(id); }

  function isQuick() {
    return /[?&]quick=1(?:&|$)/.test(window.location.search || '');
  }

  function hasApiBase() {
    return !!(window.DUMATE_API_BASE || '').replace(/\/+$/, '');
  }

  function enableDemoParam() {
    if (/[?&]demo=1(?:&|$)/.test(window.location.search || '')) return;
    var base = window.location.href.split('#')[0].replace(/[?&]demo=\d*&?/, '').replace(/[?&]$/, '');
    var hash = window.location.href.indexOf('#') >= 0 ? window.location.href.slice(window.location.href.indexOf('#')) : '';
    var sep = base.indexOf('?') >= 0 ? '&' : '?';
    try {
      window.history.replaceState(null, '', base + sep + 'demo=1' + hash);
    } catch (e) { /* 忽略 */ }
  }

  function showDemoBadge() {
    var el = $('demoBadge');
    if (!el) {
      el = document.createElement('div');
      el.id = 'demoBadge';
      el.className = 'demo-badge';
      document.body.appendChild(el);
    }
    el.textContent = '演示数据 · 结果不写入你的历史记录';
    el.classList.add('show');
    document.body.setAttribute('data-demo', '1');
  }

  function resumeText() {
    return window.MOCK && window.MOCK.resumeText ? window.MOCK.resumeText : '';
  }

  // ---------- F1 ----------
  function startF1() {
    var text = resumeText();
    if (!text) { alert('演示数据未加载，请刷新后重试。'); return; }
    var entry = $('resumeTextEntry');
    var input = $('resumeTextInput');
    var consent = $('resumeConsent');
    var textButton = $('openResumeText');

    // 生产页（resume-upload.js）：填充并提交真实流程
    if (entry && input) {
      if (textButton && entry.hidden) textButton.click();
      entry.hidden = false;
      input.value = text;
      if (consent) consent.checked = true;
      if (!hasApiBase()) enableDemoParam();   // 纯静态/本地演示环境退回合成结果
      showDemoBadge();
      entry.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      return;
    }

    // 原型页：直接走 DataBridge，失败回退演示数据
    var DB = window.DataBridge;
    if (!DB) { alert('数据服务未就绪，请稍后重试。'); return; }
    showDemoBadge();
    if (!hasApiBase()) enableDemoParam();
    if (window.APP && window.APP.setState) window.APP.setState('processing');
    function fallback() {
      var mock = DB.getMockData ? DB.getMockData('resumeProfile') : null;
      if (mock) renderResume(mock, text, null);
      else if (window.APP && window.APP.setState) window.APP.setState('error');
    }
    DB.diagnoseResume(text).then(function (res) {
      if (res && !res.error && res.resumeProfile) renderResume(res.resumeProfile, text, res);
      else fallback();
    }).catch(fallback);
  }

  // 原型页使用的紧凑渲染（生产页由 resume-upload.js 负责渲染）
  function renderResume(profile, resumeTextValue, result) {
    var score = profile.score_R != null ? profile.score_R : (result ? result.score_R : null);
    if (window.APP && window.APP.setState) window.APP.setState('success');
    var ring = $('resumeScoreRing');
    var num = $('resumeScore') || (ring ? ring.querySelector('.num') : null);
    if (num) num.textContent = score == null ? '--' : String(score);
    if (ring && score != null) {
      ring.style.setProperty('--pct', score);
      ring.setAttribute('aria-label', '诊断分 R：' + score + ' 分');
    }
    var sub = $('subbars');
    if (sub && profile.subscores) {
      sub.innerHTML = Object.keys(profile.subscores).map(function (k) {
        var s = profile.subscores[k];
        return '<div class="subbar"><div class="meta"><span>' + (s.label || k) + '</span><span>' + s.score + '</span></div>' +
          '<div class="track"><div class="fill" style="width:' + s.score + '%"></div></div></div>';
      }).join('');
    }
    if (window.EVIDENCE && window.EVIDENCE.renderDoc && $('resumeDoc')) {
      window.EVIDENCE.renderDoc('resumeDoc', resumeTextValue);
    } else if ($('resumeDoc')) {
      $('resumeDoc').textContent = resumeTextValue;
    }
    var list = $('reasonList');
    if (list) {
      var html = '';
      Object.keys(profile.subscores || {}).forEach(function (k) {
        var s = profile.subscores[k];
        html += '<div class="reason-item"><b>' + (s.label || k) + ' · ' + s.score + '分</b><br>' +
          (s.rationale || '') + (s.quote ? '<div class="tag">证据：' + s.quote + '</div>' : '') + '</div>';
      });
      (profile.suggestions || []).forEach(function (s) {
        html += '<div class="reason-item"><span class="badge ' + (s.severity || 'P1').toLowerCase() + '">' + (s.severity || 'P1') + '</span> <b>' + s.issue + '</b><br>' +
          '建议：' + s.suggestion + (s.rewrite_draft ? '<br><span class="tag">改写草案：' + s.rewrite_draft + '</span>' : '') + '</div>';
      });
      list.innerHTML = html;
    }
  }

  // ---------- F2 ----------
  function startF2() {
    var text = resumeText();
    if (!text) { alert('演示数据未加载，请刷新后重试。'); return; }
    showDemoBadge();
    if (window.F2Major && typeof window.F2Major.runQuickDemo === 'function') {
      window.F2Major.runQuickDemo('080901', text, (window.MOCK && window.MOCK.jdText) || DEMO_JD);
    } else {
      alert('当前页面不支持 F2 一键体验，请先选择专业后手动上传简历。');
    }
  }

  // ---------- 绑定与自动执行 ----------
  function bind() {
    var b1 = $('quickDemoF1');
    if (b1) b1.addEventListener('click', startF1);
    var b2 = $('quickDemoF2');
    if (b2) b2.addEventListener('click', startF2);
    if (!isQuick()) return;
    var page = (document.body.getAttribute('data-page') || '').toLowerCase();
    if (page.indexOf('f1') === 0) startF1();
    else if (page.indexOf('f2') === 0) startF2();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }

  window.QuickDemo = {
    start: function (t) { if (t === 'f2') { startF2(); } else { startF1(); } },
    startF1: startF1,
    startF2: startF2
  };
})();
