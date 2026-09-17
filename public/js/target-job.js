/* target-job.js · 目标岗位工作区
 *
 * 「分析这个岗位，能不能投」—— 建岗 → 分析 → Decision / 要求对照 / 缺口 / 依据 → 铺开行动。
 *
 * 契约（后端 api/index.py）：
 *   GET    /api/target-jobs                  -> {targetJobs[], total}
 *   POST   /api/target-jobs                  -> {targetJob, requirements[], droppedNonRequirements[]}
 *   GET    /api/target-jobs/{id}             -> {targetJob, requirements[], decision}
 *   POST   /api/target-jobs/{id}/analyse     -> {target_job, requirements[], matches[], gaps[],
 *                                                decision{decision, rationale{citations}},
 *                                                citations[], analysis{score_M, insufficient_evidence, ...}}
 *   DELETE /api/target-jobs/{id}             -> {deleted, id}
 *   POST   /api/actions {targetJobId}        -> {created[], existing[], skipped[]}（幂等）
 *
 * 生产路径规则：接口失败就明确失败，绝不用演示数据或旧结果冒充本次结论。
 */
(function () {
  "use strict";
  var DB = window.DataBridge;
  var $ = function (id) { return document.getElementById(id); };

  var currentJobId = null;
  var lastAnalysis = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function sessionId() {
    try {
      return DB && DB._cache ? DB._cache.get("sessionId") : null;
    } catch (e) { return null; }
  }

  function msg(text, kind) {
    var el = $("tjMsg");
    if (!el) return;
    el.textContent = text || "";
    el.className = "tj-msg" + (kind ? " " + kind : "");
  }

  function setState(state) {
    if (window.APP && typeof window.APP.setState === "function") window.APP.setState(state);
  }

  function fail(message) {
    var banner = $("tjErrorText");
    if (banner) banner.textContent = message || "操作失败，请稍后重试。";
    msg(message || "操作失败，请稍后重试。", "error");
    setState("error");
  }

  // ── 状态徽标 ──────────────────────────────────────────
  var STATUS_LABEL = { covered: "已覆盖", weak: "弱命中", missing: "缺失", unknown: "无法判定" };
  var STATUS_CLASS = { covered: "covered", weak: "weak", missing: "missing", unknown: "unknown" };
  var DECISION_LABEL = { APPLY: "可以投", STRETCH: "够一够再投", PASS: "先别投" };
  var DECISION_CLASS = { APPLY: "covered", STRETCH: "weak", PASS: "missing" };
  var GAP_TYPE_LABEL = { missing: "证据缺失", weak: "证据太弱", unverifiable: "无法核实" };
  var GAP_STATUS_LABEL = { open: "待处理", doing: "进行中", done: "已完成", dropped: "已放弃", cleared: "已消除" };

  function badge(text, cls) {
    return '<span class="badge ' + esc(cls) + '">' + esc(text) + "</span>";
  }

  // ── 渲染 ──────────────────────────────────────────────
  function renderJobs(rows) {
    var box = $("tjJobs");
    if (!box) return;
    if (!rows || !rows.length) {
      box.innerHTML = '<div class="tj-empty">还没有目标岗位。粘贴一份 JD 建岗后，这里会出现你的岗位清单。</div>';
      return;
    }
    box.innerHTML = rows.map(function (row) {
      var title = row.position || row.company || ("岗位 #" + row.id);
      var sub = [row.company, row.position && row.company ? row.position : ""].filter(Boolean).join(" · ");
      var active = String(row.id) === String(currentJobId) ? " active" : "";
      return '<div class="tj-job' + active + '" data-id="' + esc(String(row.id)) + '">' +
        '<div class="tj-job-main">' +
        '<div class="tj-job-title">' + esc(title) + "</div>" +
        '<div class="tj-job-sub">' + esc(sub || "未填写公司 / 职位") + "</div>" +
        "</div>" +
        '<div class="tj-job-ops">' +
        '<button class="tj-btn tj-select" type="button" data-id="' + esc(String(row.id)) + '">选中</button>' +
        '<button class="tj-btn danger tj-del" type="button" data-id="' + esc(String(row.id)) + '">删除</button>' +
        "</div></div>";
    }).join("");

    Array.prototype.forEach.call(box.querySelectorAll(".tj-select"), function (btn) {
      btn.addEventListener("click", function () { select(btn.getAttribute("data-id")); });
    });
    Array.prototype.forEach.call(box.querySelectorAll(".tj-del"), function (btn) {
      btn.addEventListener("click", function () { remove(btn.getAttribute("data-id")); });
    });
  }

  function renderRequirements(rows, analysisRows) {
    var box = $("tjRequirements");
    if (!box) return;
    var statuses = {};
    if (analysisRows && analysisRows.length) {
      analysisRows.forEach(function (row) { statuses[String(row.id)] = row; });
    }
    if (!rows || !rows.length) {
      box.innerHTML = '<div class="tj-empty">这个岗位还没有拆出可核对的要求。</div>';
      return;
    }
    box.innerHTML = rows.map(function (row) {
      var extra = statuses[String(row.id)] || row;
      var status = extra.status || row.status || "unknown";
      var evidence = extra.evidence || row.evidence || "";
      return '<div class="tj-req">' +
        '<div class="tj-req-head">' +
        badge(STATUS_LABEL[status] || status, STATUS_CLASS[status] || "unknown") +
        '<span class="tj-req-key">' + esc(row.req_key || "") + "</span>" +
        '<span class="tj-req-text">' + esc(row.text || "") + "</span>" +
        "</div>" +
        (evidence ? '<div class="tj-req-ev">简历原文：' + esc(evidence) + "</div>" : "") +
        "</div>";
    }).join("");
  }

  function renderGaps(rows) {
    var box = $("tjGaps");
    if (!box) return;
    if (!rows || !rows.length) {
      box.innerHTML = '<div class="tj-empty">当前没有未解决缺口。注意：这不等于能力已达标，只表示本次材料能对上的要求都被覆盖了。</div>';
      return;
    }
    box.innerHTML = rows.map(function (row) {
      var prio = String(row.priority || "").toLowerCase();
      return '<div class="tj-gap">' +
        '<div class="tj-gap-head">' +
        badge(row.priority || "—", prio) +
        badge(GAP_TYPE_LABEL[row.gap_type] || row.gap_type, STATUS_CLASS[row.gap_type] || "unknown") +
        badge(GAP_STATUS_LABEL[row.status] || row.status, "unknown") +
        (row.blocking ? badge("不可短期解决", "missing") : "") +
        "</div>" +
        '<div class="tj-gap-line"><b>差什么</b>' + esc(row.missing_evidence || row.reason || "") + "</div>" +
        (row.action ? '<div class="tj-gap-line"><b>做什么</b>' + esc(row.action) + "</div>" : "") +
        (row.expected_artifact ? '<div class="tj-gap-line"><b>成果物</b>' + esc(row.expected_artifact) + "</div>" : "") +
        (row.retest ? '<div class="tj-gap-line"><b>复测</b>' + esc(row.retest) + "</div>" : "") +
        "</div>";
    }).join("");
  }

  function renderCitations(rows) {
    var box = $("tjCitations");
    if (!box) return;
    if (!rows || !rows.length) {
      box.innerHTML = '<div class="tj-empty">没有可核对的依据。</div>';
      return;
    }
    box.innerHTML = "<ul>" + rows.map(function (line) {
      return "<li>" + esc(line) + "</li>";
    }).join("") + "</ul>";
  }

  function renderDecision(decision, analysis) {
    var box = $("tjDecision");
    var cls = DECISION_CLASS[decision.decision] || "unknown";
    if (box) {
      box.innerHTML = badge(DECISION_LABEL[decision.decision] || decision.decision, cls) +
        '<span class="tj-decision-code">' + esc(decision.decision) + "</span>";
    }
    var rationale = $("tjDecisionRationale");
    if (rationale) {
      var text = decision.rationale && decision.rationale.text
        ? decision.rationale.text
        : (decision.rationale_json || "");
      rationale.textContent = typeof text === "string" ? text : "";
    }
    var score = $("tjScoreM");
    if (score) {
      score.textContent = analysis && analysis.score_M !== undefined && analysis.score_M !== null
        ? String(analysis.score_M)
        : "—";
    }
    var notice = $("tjNotice");
    if (notice) {
      var lines = [];
      if (analysis && analysis.insufficient_evidence) {
        lines.push("材料与该岗位可核对的事实偏少，本次结论的证据强度有限。");
      }
      if (analysis && analysis.match_notice) lines.push(String(analysis.match_notice));
      if (analysis && analysis.new_candidate_evidence) {
        lines.push("本次新产生 " + analysis.new_candidate_evidence + " 条候选证据，需你确认后才算可信事实。");
      }
      notice.textContent = lines.join(" ");
      notice.className = "tj-notice" + (lines.length ? "" : " zy-hidden");
    }
  }

  // ── 动作 ──────────────────────────────────────────────
  function load() {
    if (!DB || typeof DB.listTargetJobs !== "function") return;
    DB.listTargetJobs().then(function (res) {
      if (res.error) { fail(res.message || "目标岗位列表加载失败。"); return; }
      renderJobs(res.targetJobs);
      if (!currentJobId && res.targetJobs && res.targetJobs.length) {
        currentJobId = res.targetJobs[0].id;
        DB.setCurrentTargetJob(currentJobId);
      }
    });
  }

  function select(id) {
    currentJobId = parseInt(id, 10);
    if (!isFinite(currentJobId)) currentJobId = null;
    if (DB && DB.setCurrentTargetJob) DB.setCurrentTargetJob(currentJobId);
    msg("已选中岗位 #" + id + "，可开始分析。");
    load();
  }

  function create() {
    var jdEl = $("tjJdText");
    var jdText = jdEl ? jdEl.value.trim() : "";
    if (!jdText) {
      msg("请先粘贴岗位描述（JD）的「岗位职责 / 任职要求」部分。", "error");
      setState("empty");
      return;
    }
    var companyEl = $("tjCompany");
    var positionEl = $("tjPosition");
    msg("正在拆解岗位要求…");
    setState("processing");
    DB.createTargetJob({
      session_id: sessionId(),
      jdText: jdText,
      company: companyEl ? companyEl.value.trim() : "",
      position: positionEl ? positionEl.value.trim() : ""
    }).then(function (res) {
      if (res.error) { fail(res.message || "建岗失败：" + res.error); return; }
      currentJobId = res.targetJob && res.targetJob.id;
      if (DB.setCurrentTargetJob) DB.setCurrentTargetJob(currentJobId);
      renderRequirements(res.requirements, null);
      renderGaps([]);
      renderCitations([]);
      var drop = $("tjDropped");
      if (drop) {
        var dropped = res.droppedNonRequirements || [];
        drop.textContent = dropped.length
          ? "已忽略 " + dropped.length + " 行非要求文本（如公司介绍）：" + dropped.join("；")
          : "";
        drop.className = "tj-dropped" + (dropped.length ? "" : " zy-hidden");
      }
      msg("已建成岗位 #" + currentJobId + "，共拆出 " + (res.requirements || []).length + " 条要求。下一步点「分析这个岗位」。");
      setState("success");
      load();
    });
  }

  function analyse() {
    if (!currentJobId) { msg("请先建岗或选中一个目标岗位。", "error"); return; }
    msg("正在对照简历分析…");
    setState("processing");
    DB.analyseTargetJob(currentJobId).then(function (res) {
      if (res.error) {
        // insufficient_grounds：依据不足 3 条，后端拒绝给结论。这不是故障，是口径。
        fail(res.message || "分析失败：" + res.error);
        return;
      }
      lastAnalysis = res;
      var decision = res.decision || {};
      renderDecision(decision, res.analysis);
      renderRequirements(res.requirements, res.requirements);
      renderGaps(res.gaps);
      renderCitations(res.citations || (decision.rationale && decision.rationale.citations) || []);
      msg("分析完成：" + (DECISION_LABEL[decision.decision] || decision.decision || "—"));
      setState("success");
    });
  }

  function plan() {
    if (!currentJobId) { msg("请先选中一个目标岗位。", "error"); return; }
    msg("正在把未解决缺口铺成行动…");
    DB.planActionsForTarget(currentJobId).then(function (res) {
      if (res.error) { fail(res.message || "铺开行动失败。"); return; }
      var parts = [
        "新建 " + res.createdCount + " 条",
        "已存在 " + res.existingCount + " 条"
      ];
      if (res.skipped && res.skipped.length) {
        parts.push("跳过 " + res.skipped.length + " 条（" + (res.skipped[0].reason || "不可验证") + "）");
      }
      msg("行动已铺开：" + parts.join("，") + "。到「行动闭环」查看。");
    });
  }

  function remove(id) {
    if (!DB || typeof DB.deleteTargetJob !== "function") return;
    DB.deleteTargetJob(id).then(function (res) {
      if (res.error) { fail(res.message || "删除失败。"); return; }
      if (String(currentJobId) === String(id)) {
        currentJobId = null;
        if (DB.setCurrentTargetJob) DB.setCurrentTargetJob(null);
      }
      msg("已删除岗位 #" + id + " 及其要求、缺口与决策。");
      load();
    });
  }

  function prefillDemo() {
    if (!window.APP || !window.APP.isDemoMode()) return;
    var jdEl = $("tjJdText");
    if (jdEl && !jdEl.value && window.MOCK && window.MOCK.jdText) {
      jdEl.value = window.MOCK.jdText;
    }
  }

  function wire() {
    var createBtn = $("tjCreate");
    if (createBtn) createBtn.addEventListener("click", create);
    var analyseBtn = $("tjAnalyse");
    if (analyseBtn) analyseBtn.addEventListener("click", analyse);
    var planBtn = $("tjPlanActions");
    if (planBtn) planBtn.addEventListener("click", plan);
    var retryBtn = $("tjRetry");
    if (retryBtn) retryBtn.addEventListener("click", analyse);
  }

  wire();
  prefillDemo();
  if (document.readyState !== "loading") load();
  else document.addEventListener("DOMContentLoaded", load);

  window.TARGET_JOB = {
    create: create,
    analyse: analyse,
    plan: plan,
    select: select,
    reload: load,
    _statusLabel: STATUS_LABEL,
    _decisionLabel: DECISION_LABEL
  };
})();
