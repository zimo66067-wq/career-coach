/* evidence.js · 证据对照：点击评分理由 → 高亮原文 source_span（F1/F3 共用） */
(function () {
  function escapeReg(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }

  // 将原文渲染到容器，并返回按 quote 定位高亮的函数
  function renderDoc(containerId, text) {
    var el = document.getElementById(containerId);
    if (!el) return null;
    el.textContent = text;
    var plain = el.innerHTML;
    return function highlight(quote) {
      el.innerHTML = plain;
      if (!quote) return;
      var html = el.innerHTML.replace(new RegExp(escapeReg(quote), "g"), function (m) {
        return "<mark>" + m + "</mark>";
      });
      el.innerHTML = html;
      var mark = el.querySelector("mark");
      if (mark && mark.scrollIntoView) mark.scrollIntoView({ block: "center", behavior: "smooth" });
    };
  }

  function bindReasons(selector, highlight, quoteOf) {
    Array.prototype.forEach.call(document.querySelectorAll(selector), function (item) {
      item.addEventListener("click", function () {
        document.querySelectorAll(selector + ".active").forEach(function (n) { n.classList.remove("active"); });
        item.classList.add("active");
        highlight(quoteOf(item));
      });
    });
  }

  window.EVIDENCE = { renderDoc: renderDoc, bindReasons: bindReasons };
})();
