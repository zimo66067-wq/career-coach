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

  // ── 目标岗位上下文（DoD #10：求职信只引用岗位要求 + 已确认证据）──
  function targetJobId() {
    try {
      return DB && typeof DB.getCurrentTargetJob === "function" ? DB.getCurrentTargetJob() : null;
    } catch (e) { return null; }
  }

  var GROUNDING_LABEL = {
    "target_job+evidence": "目标岗位要求 + 已确认职业证据",
    "target_job_no_evidence": "仅目标岗位要求（尚无已确认职业证据）",
    "diagnosis": "简历诊断原文片段（未接目标岗位）"
  };
  var BASIS_LABEL = { model: "AI 生成", rule: "规则模板生成" };

  function setTargetLine(text) {
    var el = $("f5TargetLine");
    if (el) el.textContent = text || "";
  }

  // 载入时把「当前目标岗位」摆出来：本页与 F3 出题、F4 行动清单共用同一岗位口径。
  function loadTargetContext() {
    var id = targetJobId();
    if (!id || !DB || typeof DB.getTargetJob !== "function") {
      setTargetLine("当前未选定目标岗位：生成的求职信只会引用简历诊断的原文片段。" +
        "建议先去目标岗位工作区分析该岗位。");
      return;
    }
    setTargetLine("当前目标岗位 #" + id + "（读取中…）");
    DB.getTargetJob(id).then(function (res) {
      if (!res || res.error || !res.targetJob) {
        setTargetLine("当前目标岗位 #" + id + "（详情读取失败，仍会按该岗位生成）。");
        return;
      }
      var job = res.targetJob;
      var name = [job.company, job.position].filter(Boolean).join(" · ") || ("岗位 #" + id);
      var companyEl = $("f5Company");
      var positionEl = $("f5Position");
      if (companyEl && !companyEl.value) companyEl.value = job.company || "";
      if (positionEl && !positionEl.value) positionEl.value = job.position || "";
      setTargetLine("当前目标岗位 #" + id + "：" + name +
        "。已带入公司 / 职位（可修改）；求职信会引用该岗位要求与你已确认的职业证据。");
    }).catch(function () {
      setTargetLine("当前目标岗位 #" + id + "（详情读取失败，仍会按该岗位生成）。");
    });
  }

  // 显式呈现"这封信引用了哪些依据"—— 依据不足时也要看得见，不能只给一封光秃秃的信。
  function renderGrounding(res, appliedTargetId) {
    var box = $("f5Grounding");
    if (!box) return;
    var badge = $("f5BasisBadge");
    var list = $("f5EvidenceList");
    var notice = $("f5Notice");

    if (badge) {
      badge.textContent = (BASIS_LABEL[res.basis] || res.basis || "—") + " · " +
        (GROUNDING_LABEL[res.grounding] || res.grounding || "—");
    }
    if (appliedTargetId) {
      setTargetLine("本次求职信已接入目标岗位 #" + appliedTargetId + "：" +
        (res.company || "") + " · " + (res.position || ""));
    }

    if (list) {
      var evidence = Array.isArray(res.evidence) ? res.evidence : [];
      var requirements = Array.isArray(res.requirements) ? res.requirements : [];
      var gaps = Array.isArray(res.gaps) ? res.gaps : [];
      var html = '<p class="f5-ground-item"><b>引用的已确认证据（' + evidence.length + " 条）</b></p>";
      if (evidence.length) {
        html += evidence.map(function (item) {
          return '<p class="f5-ground-item">· ' + esc(item.claim || "") + "</p>";
        }).join("");
      } else {
        html += '<p class="f5-ground-item">· 无 —— 正文没有引用任何个人经历。</p>';
      }
      if (requirements.length) {
        var shown = requirements.slice(0, 5).map(function (item) {
          return esc((item.priority ? item.priority + " " : "") + (item.text || ""));
        }).join("；");
        html += '<p class="f5-ground-item"><b>岗位要求底座（前 ' + Math.min(5, requirements.length) +
          " / 共 " + requirements.length + " 条）</b></p>";
        html += '<p class="f5-ground-item">· ' + shown + "</p>";
      }
      if (gaps.length) {
        var byPriority = {};
        gaps.forEach(function (item) {
          var key = item.priority || "—";
          byPriority[key] = (byPriority[key] || 0) + 1;
        });
        var desc = Object.keys(byPriority).sort().map(function (k) {
          return k + " ×" + byPriority[k];
        }).join("、");
        html += '<p class="f5-ground-item"><b>未覆盖的缺口（' + gaps.length + " 条）</b>：" +
          esc(desc) + " —— 缺口不写进正文，也不会被声称具备。</p>";
      }
      list.innerHTML = html;
    }
    if (notice) notice.textContent = res.notice || "";
    box.classList.remove("zy-hidden");
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
    var tid = targetJobId();
    var company = $("f5Company").value.trim();
    var position = $("f5Position").value.trim();
    if (!company || !position) { msg("请填写目标公司与职位。", true); return; }
    msg(tid ? "正在按目标岗位 #" + tid + " 的要求与你的已确认证据生成求职信…" : "正在生成求职信…");
    DB.generateCoverLetter(sid, company, position, tid).then(function (res) {
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
      renderGrounding(res, tid);
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
    loadTargetContext();
    load();
  } else {
    document.addEventListener("DOMContentLoaded", loadTargetContext);
  }
})();
