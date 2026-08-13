/* optimizer.js · 简历优化器前端（阶段4）
 * 为 F1 诊断建议提供"应用建议改写"：优化服务返回候选 -> 人工确认 -> 落库。
 * 候选带 pending_confirm 标记，用户确认后才调用 apply-rewrite 保存。
 */
(function () {
  "use strict";
  var API = String(window.DUMATE_API_BASE || "").replace(/\/+$/, "");
  var modal = null;

  function sessionId() {
    try {
      return window.DataBridge && window.DataBridge._cache
        ? window.DataBridge._cache.get("sessionId") : null;
    } catch (e) { return null; }
  }
  function consentToken() {
    try {
      return window.DataBridge && window.DataBridge._cache
        ? window.DataBridge._cache.get("consentToken") : null;
    } catch (e) { return null; }
  }

  function post(path, body) {
    var headers = { "Content-Type": "application/json" };
    var token = consentToken();
    if (token) headers["X-Consent-Token"] = token;
    return fetch(API + path, {
      method: "POST",
      headers: headers,
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); })
      .catch(function () { return { error: "network", message: "网络错误，请确认后端服务已启动。" }; });
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function ensureModal() {
    if (modal) return modal;
    modal = document.createElement("div");
    modal.className = "zy-modal";
    modal.id = "zyRewriteModal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.innerHTML =
      '<div class="zy-modal-box" style="max-width:560px">' +
      '<button class="zy-modal-close" id="zyRewriteClose" type="button" aria-label="关闭">×</button>' +
      '<h3>改写预览 <span class="badge weak">待确认</span></h3>' +
      '<p style="font-size:13px;color:var(--zy-ink-2)">以下为基于诊断建议生成的改写段落，确认后才会保存到你的记录。</p>' +
      '<div class="opt-candidate" style="background:var(--zy-surface-2);border-radius:8px;padding:12px;font-size:14px;line-height:1.7;margin:10px 0"></div>' +
      '<div style="display:flex;gap:8px;justify-content:flex-end">' +
      '<button class="btn ghost" id="zyRewriteCancel" type="button">取消</button>' +
      '<button class="btn primary" id="zyRewriteConfirm" type="button">确认应用</button>' +
      "</div></div>";
    document.body.appendChild(modal);
    modal.querySelector("#zyRewriteClose").addEventListener("click", close);
    modal.querySelector("#zyRewriteCancel").addEventListener("click", close);
    return modal;
  }

  function open() { ensureModal(); modal.classList.remove("zy-hidden"); }
  function close() { if (modal) modal.classList.add("zy-hidden"); }

  function applyRewrite(rewrite, btn) {
    var sid = sessionId();
    if (!sid) { close(); window.alert("未找到当前会话，请先完成一次简历诊断。"); return; }
    post("/api/wf02/apply-rewrite", {
      session_id: sid,
      suggestion_id: rewrite.suggestion_id || "",
      issue: rewrite.issue || "",
      candidate_text: rewrite.candidate || ""
    }).then(function (res) {
      if (res.error) { close(); window.alert(res.message || "应用失败，请稍后重试。"); return; }
      close();
      if (btn) {
        btn.disabled = true;
        btn.textContent = "已应用";
        btn.classList.add("applied");
      }
    });
  }

  function handleClick(e) {
    var btn = e.target && e.target.closest ? e.target.closest(".rewrite-btn") : null;
    if (!btn) return;
    var suggestionId = btn.getAttribute("data-suggestion-id") || "";
    var sid = sessionId();
    if (!sid) {
      window.alert("请先完成一次简历诊断，再使用建议改写。");
      return;
    }
    post("/api/wf02/optimize", { session_id: sid, suggestion_id: suggestionId }).then(function (res) {
      if (res.error || !res.candidate) {
        window.alert((res && res.message) || "优化服务暂不可用，请确认后端已启动。");
        return;
      }
      var m = ensureModal();
      m.querySelector(".opt-candidate").textContent = res.candidate;
      m.querySelector("#zyRewriteConfirm").onclick = function () { applyRewrite(res, btn); };
      open();
    });
  }

  document.addEventListener("click", handleClick);
})();
