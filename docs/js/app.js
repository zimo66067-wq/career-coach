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
    var html = '<div class="t">界面状态演示</div>';
    STATES.forEach(function (s) {
      html += '<a href="javascript:void(0)" data-s="' + s + '"' + (s === cur ? ' class="cur"' : "") + ">" + LABELS[s] + "</a>";
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

  document.addEventListener("DOMContentLoaded", function () {
    var s = getState();
    document.body.setAttribute("data-state", s);
    mountFab();
    mountNav(document.body.getAttribute("data-page"));
  });

  window.APP = { getState: getState, STATES: STATES, LABELS: LABELS };
})();
