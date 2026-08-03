/* app.js · 公共逻辑：?state= 参数解析 + 状态切换悬浮器 */
(function () {
  var STATES = ["empty", "processing", "success", "error", "degraded"];
  var LABELS = { empty: "空态", processing: "处理中", success: "成功", error: "失败", degraded: "降级" };

  function getState() {
    var m = /[?&]state=([a-z]+)/.exec(location.search);
    var s = m && STATES.indexOf(m[1]) >= 0 ? m[1] : "success";
    return s;
  }

  function setState(s) {
    var url = location.pathname + "?state=" + s + location.hash;
    location.href = url;
  }

  function mountFab() {
    if (document.body.hasAttribute("data-no-fab")) return;
    var cur = getState();
    var fab = document.createElement("div");
    fab.className = "state-fab";
    fab.setAttribute("role", "group");
    fab.setAttribute("aria-label", "界面状态演示切换器");
    var html = '<div class="t">界面状态演示</div>';
    STATES.forEach(function (s) {
      html += '<a href="javascript:void(0)" data-s="' + s + '" aria-label="切换到' + LABELS[s] + '状态"' +
        (s === cur ? ' class="cur" aria-current="true"' : "") + ">" + LABELS[s] + "</a>";
    });
    fab.innerHTML = html;
    fab.addEventListener("click", function (e) {
      var t = e.target;
      if (t && t.getAttribute("data-s")) setState(t.getAttribute("data-s"));
    });
    document.body.appendChild(fab);
  }

  function mountNav(active) {
    var nav = document.querySelector(".topnav");
    if (!nav) return;
    nav.querySelectorAll("a.nav").forEach(function (a) {
      if (a.getAttribute("data-page") === active) a.classList.add("active");
    });
  }

  /* 导航滚动平滑压缩（表现层增强，不改动导航 DOM 契约） */
  function mountNavCompress() {
    var nav = document.querySelector(".topnav");
    if (!nav) return;
    var ticking = false;
    function onScroll() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        nav.classList.toggle("scrolled", window.scrollY > 24);
        ticking = false;
      });
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* Toast 轻量反馈（表现层工具；type: info|success|error） */
  function toast(msg, type) {
    var wrap = document.querySelector(".toast-wrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "toast-wrap";
      wrap.setAttribute("aria-live", "polite");
      document.body.appendChild(wrap);
    }
    var el = document.createElement("div");
    el.className = "toast " + (type || "info");
    el.textContent = msg;
    wrap.appendChild(el);
    setTimeout(function () {
      el.classList.add("out");
      setTimeout(function () { el.remove(); }, 320);
    }, 2600);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var s = getState();
    document.body.setAttribute("data-state", s);
    mountFab();
    mountNav(document.body.getAttribute("data-page"));
    mountNavCompress();
  });

  window.APP = { getState: getState, STATES: STATES, LABELS: LABELS, toast: toast };
})();
