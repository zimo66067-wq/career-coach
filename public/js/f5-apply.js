/* f5-apply.js · F5 投递闭环（阶段5）
 * 求职信生成预览（pending_confirm）-> 人工确认 -> 申请跟踪落库。
 * 无外部 key 时后端以规则模板生成，链路全可用。
 */
(function () {
  "use strict";
  var DB = window.DataBridge;
  var $ = function (id) { return document.getElementById(id); };

  function sessionId() {
    try {
      return DB && DB._cache ? DB._cache.get("sessionId") : null;
    } catch (e) { return null; }
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function msg(text, isError) {
    var el = $("f5Msg");
    if (!el) return;
    el.textContent = text || "";
    el.className = "f5-msg" + (isError ? " error" : "");
  }

  function renderList(rows) {
    var list = $("f5Applications");
    if (!list) return;
    list.innerHTML = "";
    if (!rows || !rows.length) {
      list.innerHTML = '<div class="f5-empty">还没有申请记录。生成并确认一封求职信后，记录会出现在这里。</div>';
      return;
    }
    rows.forEach(function (row) {
      var div = document.createElement("div");
      div.className = "f5-item";
      var head = document.createElement("div");
      head.className = "f5-item-head";
      head.innerHTML = "<b>" + esc(row.company || "") + "</b>" +
        '<span class="f5-tag">' + esc(row.position || "") + "</span>" +
        '<button class="f5-del" type="button" data-id="' + esc(String(row.id || "")) + '">删除</button>';
      var body = document.createElement("div");
      body.className = "f5-item-body";
      body.textContent = row.cover_letter || "";
      div.appendChild(head);
      div.appendChild(body);
      list.appendChild(div);
    });
    var dels = list.querySelectorAll(".f5-del");
    Array.prototype.forEach.call(dels, function (btn) {
      btn.addEventListener("click", function () { remove(btn.getAttribute("data-id")); });
    });
  }

  function load() {
    if (!DB || typeof DB.listApplications !== "function") return;
    DB.listApplications().then(function (res) {
      if (res && res.applications) renderList(res.applications);
    });
  }

  function generate() {
    var sid = sessionId();
    if (!sid) { msg("未找到当前会话，请先完成一次简历诊断。", true); return; }
    var company = $("f5Company").value.trim();
    var position = $("f5Position").value.trim();
    if (!company || !position) { msg("请填写目标公司与职位。", true); return; }
    msg("正在生成求职信…");
    DB.generateCoverLetter(sid, company, position).then(function (res) {
      if (res.error || !res.candidate) {
        msg((res && res.message) || "生成失败，请稍后重试。", true);
        return;
      }
      var body = $("f5PreviewBody");
      if (body) body.textContent = res.candidate;
      var confirmBtn = $("f5Confirm");
      if (confirmBtn) {
        confirmBtn.setAttribute("data-company", company);
        confirmBtn.setAttribute("data-position", position);
        confirmBtn.removeAttribute("disabled");
      }
      var preview = $("f5Preview");
      if (preview) preview.classList.remove("zy-hidden");
      msg("求职信已生成，请确认后保存到申请记录。");
    });
  }

  function confirm() {
    var sid = sessionId();
    if (!sid) { msg("未找到当前会话。", true); return; }
    var confirmBtn = $("f5Confirm");
    var company = confirmBtn.getAttribute("data-company") || "";
    var position = confirmBtn.getAttribute("data-position") || "";
    var body = $("f5PreviewBody");
    var text = body ? body.textContent : "";
    DB.saveApplication(sid, company, position, text).then(function (res) {
      if (res.error || !res.application) {
        msg((res && res.message) || "保存失败，请稍后重试。", true);
        return;
      }
      if (confirmBtn) confirmBtn.setAttribute("disabled", "disabled");
      msg("已保存到申请跟踪。");
      load();
    });
  }

  function remove(id) {
    if (!DB || typeof DB.deleteApplication !== "function") return;
    DB.deleteApplication(id).then(function (res) {
      if (res.error) { msg((res && res.message) || "删除失败。", true); return; }
      msg("已删除申请记录。");
      load();
    });
  }

  function wire() {
    var gen = $("f5Generate");
    if (gen) gen.addEventListener("click", generate);
    var confirmBtn = $("f5Confirm");
    if (confirmBtn) confirmBtn.addEventListener("click", confirm);
  }

  wire();
  if (document.readyState !== "loading") {
    load();
  }
})();
