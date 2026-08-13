/* kb.js · 面经知识库（阶段4）
 * 检索 + 分类筛选 + 列表渲染；无 embedding key 时后端以 BM25 提供可用检索。
 */
(function () {
  "use strict";
  var API = String(window.DUMATE_API_BASE || "").replace(/\/+$/, "");
  var $ = function (id) { return document.getElementById(id); };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function apiGet(path) {
    return fetch(API + path)
      .then(function (r) { return r.json(); })
      .catch(function () { return { error: "network", message: "网络错误，请确认后端服务已启动。" }; });
  }

  function renderList(items) {
    var box = $("kbResults");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<div class="kb-empty">没有找到相关问题，换个关键词试试。</div>';
      return;
    }
    box.innerHTML = items.map(function (it) {
      return '<article class="card kb-item">' +
        '<div class="kb-meta"><span class="kb-cat">' + esc(it.category) + "</span>" +
        '<span class="kb-score">相关度 ' + (it.score == null ? "--" : it.score) + "</span></div>" +
        "<h3>" + esc(it.question) + "</h3>" +
        '<p class="kb-answer">' + esc(it.answer) + "</p>" +
        (it.tips ? '<p class="kb-tips">提示：' + esc(it.tips) + "</p>" : "") +
        "</article>";
    }).join("");
  }

  function loadAll() {
    apiGet("/api/knowledge/questions").then(function (res) {
      if (res.error) { renderList([]); return; }
      var cats = res.categories || [];
      var chips = $("kbChips");
      if (chips) {
        chips.innerHTML = '<button type="button" class="kb-chip active" data-cat="">全部</button>' +
          cats.map(function (c) {
            return '<button type="button" class="kb-chip" data-cat="' + esc(c.category) + '">' +
              esc(c.category) + "（" + c.count + "）</button>";
          }).join("");
        chips.querySelectorAll(".kb-chip").forEach(function (chip) {
          chip.addEventListener("click", function () {
            chips.querySelectorAll(".kb-chip").forEach(function (c) { c.classList.remove("active"); });
            chip.classList.add("active");
            var q = $("kbQuery").value.trim();
            if (q) { doSearch(q, chip.getAttribute("data-cat")); }
            else { loadByCategory(chip.getAttribute("data-cat")); }
          });
        });
      }
      var notice = $("kbNotice");
      if (notice && res.items && res.items.length) {
        notice.textContent = "共 " + res.total + " 条面经，按 F3 面试场景分类。";
      }
      renderList(res.items);
    });
  }

  function loadByCategory(cat) {
    var path = "/api/knowledge/questions" + (cat ? "?category=" + encodeURIComponent(cat) : "");
    apiGet(path).then(function (res) {
      if (res.error) { renderList([]); return; }
      renderList(res.items);
    });
  }

  function doSearch(q, cat) {
    var path = "/api/knowledge/search?q=" + encodeURIComponent(q) +
      (cat ? "&category=" + encodeURIComponent(cat) : "") + "&limit=10";
    apiGet(path).then(function (res) {
      var notice = $("kbNotice");
      if (notice) notice.textContent = res.notice || "";
      renderList(res.items);
    });
  }

  function wire() {
    var btn = $("kbSearchBtn"), input = $("kbQuery");
    function submit() {
      var q = (input.value || "").trim();
      if (!q) { loadAll(); return; }
      var active = document.querySelector(".kb-chip.active");
      doSearch(q, active ? active.getAttribute("data-cat") : "");
    }
    if (btn) btn.addEventListener("click", submit);
    if (input) input.addEventListener("keydown", function (e) { if (e.key === "Enter") submit(); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    wire();
    loadAll();
  });
})();
