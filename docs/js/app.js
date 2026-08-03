/* app.js · 公共逻辑：生产默认空态；演示需 ?demo=1&state= */
(function () {
  var STATES = ["empty", "processing", "success", "error", "degraded"];
  var LABELS = { empty: "空态", processing: "处理中", success: "成功", error: "失败", degraded: "降级" };

  function isDemoMode() {
    return /[?&]demo=1(?:&|$)/.test(location.search);
  }

  function getState() {
    // 生产访问绝不能仅靠 URL 参数进入含合成数据的成功态。
    if (!isDemoMode()) return "empty";
    var m = /[?&]state=([a-z]+)/.exec(location.search);
    var s = m && STATES.indexOf(m[1]) >= 0 ? m[1] : "empty";
    return s;
  }

  function setState(s) {
    if (STATES.indexOf(s) < 0) return;
    if (!isDemoMode()) {
      document.body.setAttribute("data-state", s);
      return;
    }
    var url = location.pathname + "?demo=1&state=" + s + location.hash;
    location.href = url;
  }

  function mountFab() {
    if (!isDemoMode() || document.body.hasAttribute("data-no-fab")) return;
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

  function mountDemoNotice() {
    if (!isDemoMode()) return;
    document.body.setAttribute("data-demo", "true");
    var notice = document.createElement("div");
    notice.className = "demo-notice";
    notice.setAttribute("role", "status");
    notice.textContent = "演示数据：合成样本，仅用于界面预览";
    document.body.appendChild(notice);
  }

  function mountNav(active) {
    var nav = document.querySelector(".topnav");
    if (!nav) return;
    nav.querySelectorAll("a.nav").forEach(function (a) {
      if (a.getAttribute("data-page") === active) a.classList.add("active");
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var s = getState();
    document.body.setAttribute("data-state", s);
    mountDemoNotice();
    mountFab();
    mountNav(document.body.getAttribute("data-page"));
  });

  window.APP = {
    getState: getState,
    setState: setState,
    isDemoMode: isDemoMode,
    STATES: STATES,
    LABELS: LABELS
  };
})();
