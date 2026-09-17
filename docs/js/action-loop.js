/* action-loop.js · 行动闭环（缺口 → 可执行行动 → 复测）
 *
 * 「补齐证据，然后复测」—— 把目标岗位的未解决缺口翻成可执行、可验证的行动。
 *
 * 契约（api/index.py + services/action_plan_service.py）：
 *   GET    /api/actions                  -> {actions[], total}
 *   POST   /api/actions {targetJobId}    -> {created[], existing[], skipped[]}（幂等）
 *   GET    /api/actions/{id}             -> {action}
 *   POST   /api/actions/{id}/start       -> todo → doing
 *   POST   /api/actions/{id}/complete    -> doing → done（可带成果物说明）
 *   POST   /api/actions/{id}/outcome     -> 记录"做完之后发生了什么"
 *   POST   /api/actions/{id}/drop        -> 放弃
 *   DELETE /api/actions/{id}             -> 删除
 *
 * 三条口径必须写在界面上，不能含糊（与 action_plan_service 的文档字符串一致）：
 *  1. 行动「已完成」≠ 缺口「已解决」—— 缺口只有在**重新分析**被新证据覆盖后才是 cleared。
 *  2. 缺口缺少可验证成果物（expected_artifact）时**不开单**，后端如实报出被跳过的条数。
 *  3. 「记录结果」要求行动已完成且带成果物说明；不满足时界面不给按钮，不制造 422。
 *
 * 生产路径规则：接口失败就明确失败，绝不用演示数据冒充本次行动清单。
 */
(function () {
  "use strict";

  var DB = window.DataBridge;
  var $ = function (id) { return document.getElementById(id); };

  var STATUS_LABEL = { todo: "待办", doing: "进行中", done: "已完成", dropped: "已放弃" };
  var STATUS_CLASS = { todo: "unknown", doing: "p2", done: "covered", dropped: "unknown" };
  var GAP_STATUS_LABEL = {
    open: "待处理", doing: "处理中", done: "已处理", dropped: "已放弃", cleared: "已被新证据覆盖"
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function msg(text, kind) {
    var el = $("alMsg");
    if (!el) return;
    el.textContent = text || "";
    el.className = "al-msg" + (kind ? " " + kind : "");
  }

  function setState(state) {
    if (window.APP && typeof window.APP.setState === "function") window.APP.setState(state);
  }

  function ask(question) {
    if (typeof window.prompt !== "function") return "";
    var answer = window.prompt(question, "");
    return answer === null ? "" : String(answer).trim();
  }

  function targetJobId() {
    if (!DB || typeof DB.getCurrentTargetJob !== "function") return null;
    try { return DB.getCurrentTargetJob(); } catch (e) { return null; }
  }

  // ── 目标岗位上下文 ─────────────────────────────────────
  function renderTarget(job, decision) {
    var line = $("alTargetLine");
    if (!line) return;
    if (!job) {
      line.textContent = "还没有「当前目标岗位」。行动清单按岗位的缺口生成，" +
        "请先在目标岗位工作区分析一个岗位。";
      return;
    }
    var name = [job.company, job.position].filter(Boolean).join(" · ") || ("岗位 #" + job.id);
    var verdict = decision && decision.decision ? "｜投递判断：" + decision.decision : "";
    line.textContent = "当前目标岗位：" + name + verdict;
  }

  // ── 渲染 ───────────────────────────────────────────────
  function renderSummary(actions) {
    var box = $("alSummary");
    if (!box) return;
    var c = { todo: 0, doing: 0, done: 0, dropped: 0 };
    (actions || []).forEach(function (a) {
      if (c[a.status] !== undefined) c[a.status] += 1;
    });
    box.textContent = "共 " + (actions || []).length + " 条 ｜ 待办 " + c.todo +
      " ｜ 进行中 " + c.doing + " ｜ 已完成 " + c.done + " ｜ 已放弃 " + c.dropped;
  }

  function actionItem(a) {
    var ops = [];
    var id = esc(String(a.id));
    if (a.status === "todo") {
      ops.push('<button class="al-btn" type="button" data-verb="start" data-id="' + id + '">开始</button>');
    }
    if (a.status === "doing") {
      ops.push('<button class="al-btn primary" type="button" data-verb="complete" data-id="' + id + '">标记完成</button>');
    }
    // 域层要求：只有「已完成且带成果物说明」的行动才能记录结果。
    if (a.status === "done" && String(a.artifact || "").trim()) {
      ops.push('<button class="al-btn" type="button" data-verb="outcome" data-id="' + id + '">记录结果</button>');
    }
    if (a.status === "todo" || a.status === "doing") {
      ops.push('<button class="al-btn" type="button" data-verb="drop" data-id="' + id + '">放弃</button>');
    }
    ops.push('<button class="al-btn danger" type="button" data-verb="delete" data-id="' + id + '">删除</button>');

    var head = '<span class="badge ' + esc(STATUS_CLASS[a.status] || "unknown") + '">' +
      esc(STATUS_LABEL[a.status] || a.status) + "</span>";
    if (a.gap_priority) {
      head += '<span class="badge ' + esc(String(a.gap_priority).toLowerCase()) + '">' +
        esc(a.gap_priority) + "</span>";
    }
    var context = [a.target_company, a.target_position].filter(Boolean).join(" · ");
    if (context) head += '<span class="al-ctx">' + esc(context) + "</span>";

    var body = '<div class="al-task">' + esc(a.task || "") + "</div>";
    if (a.artifact) body += '<div class="al-line"><b>成果物</b>' + esc(a.artifact) + "</div>";
    if (a.outcome) body += '<div class="al-line"><b>做完之后</b>' + esc(a.outcome) + "</div>";
    if (a.gap_status) {
      body += '<div class="al-foot">所属缺口：' + esc(GAP_STATUS_LABEL[a.gap_status] || a.gap_status) + "</div>";
    }

    return '<div class="al-item"><div class="al-head">' + head +
      '<span class="al-ops">' + ops.join("") + "</span></div>" + body + "</div>";
  }

  function render(actions) {
    renderSummary(actions);
    var box = $("alList");
    if (!box) return;
    var rows = actions || [];
    if (!rows.length) {
      box.innerHTML = '<div class="al-empty">还没有行动。先在目标岗位工作区分析一个岗位，' +
        "再点上面的「按未解决缺口生成行动清单」。</div>";
      return;
    }
    box.innerHTML = rows.map(actionItem).join("");
  }

  // ── 数据流 ─────────────────────────────────────────────
  function refresh() {
    if (!DB || typeof DB.listActions !== "function") {
      msg("行动清单接口不可用。", "error");
      return Promise.resolve();
    }
    var id = targetJobId();
    var chain = Promise.resolve(null);
    if (id && typeof DB.getTargetJob === "function") {
      chain = DB.getTargetJob(id).then(function (res) {
        if (res && !res.error && res.targetJob) renderTarget(res.targetJob, res.decision);
        return null;
      }).catch(function () { return null; });
    }
    return chain.then(function () {
      if (!id) renderTarget(null, null);
      return DB.listActions();
    }).then(function (res) {
      if (!res || res.error) {
        msg((res && res.message) || "读取行动清单失败。", "error");
        setState("error");
        return;
      }
      render(res.actions || []);
    }).catch(function (err) {
      msg("读取行动清单时出错：" + ((err && err.message) || "未知错误"), "error");
      setState("error");
    });
  }

  function plan() {
    if (!DB || typeof DB.planActionsForTarget !== "function") {
      msg("行动计划接口不可用。", "error");
      return Promise.resolve();
    }
    var id = targetJobId();
    if (!id) {
      msg("还没有「当前目标岗位」。请先在目标岗位工作区分析一个岗位，再回来生成行动清单。", "error");
      return Promise.resolve();
    }
    msg("正在按该岗位的未解决缺口生成行动清单…");
    return DB.planActionsForTarget(id).then(function (res) {
      if (!res || res.error) {
        msg((res && res.message) || "生成行动清单失败。", "error");
        setState("error");
        return;
      }
      var parts = ["新建 " + res.createdCount + " 条", "已有未关闭 " + res.existingCount + " 条"];
      var skippedRows = res.skipped || [];
      if (skippedRows.length) {
        // 缺口缺少可验证成果物时不开单：如实报出条数，不静默丢弃
        parts.push("跳过 " + skippedRows.length + " 条（缺口没有可验证的成果物说明）");
      }
      msg("行动清单已更新：" + parts.join("，") + "。");
      return refresh();
    }).catch(function (err) {
      msg("生成行动清单时出错：" + ((err && err.message) || "未知错误"), "error");
      setState("error");
    });
  }

  function run(id, verb) {
    if (!DB) return Promise.resolve();
    if (verb === "start") return DB.startAction(id);
    if (verb === "drop") return DB.dropAction(id);
    if (verb === "delete") return DB.deleteAction(id);
    if (verb === "complete") {
      var artifact = ask("这条行动产出了什么可验证的成果物？（可留空）");
      return artifact ? DB.completeAction(id, artifact) : DB.completeAction(id);
    }
    if (verb === "outcome") {
      var outcome = ask("做完之后发生了什么？（例如：项目说明补上了 3 个量化数字）");
      if (!outcome) return Promise.resolve({ error: "cancelled", message: "已取消：结果说明不能为空。" });
      return DB.recordActionOutcome(id, outcome);
    }
    return Promise.resolve({ error: "unknown_verb", message: "未知操作。" });
  }

  function onListClick(event) {
    var target = event && event.target;
    var btn = target && typeof target.closest === "function" ? target.closest(".al-btn") : null;
    if (!btn) return;
    var verb = btn.getAttribute("data-verb");
    var id = btn.getAttribute("data-id");
    if (!verb || !id) return;
    msg("正在处理…");
    run(id, verb).then(function (res) {
      if (!res || res.error) {
        msg((res && res.message) || "操作失败，请稍后重试。", "error");
        return;
      }
      if (verb === "complete") msg("已标记完成。注意：行动完成不等于缺口解决，需重新分析才会更新判断。");
      if (verb === "outcome") msg("已记录结果。");
      if (verb === "start") msg("已开始处理。");
      if (verb === "drop") msg("已放弃该行动。缺口不会因此被关闭。");
      if (verb === "delete") msg("已删除该行动；缺口仍留在清单里。");
      return refresh();
    }).catch(function (err) {
      msg("操作出错：" + ((err && err.message) || "未知错误"), "error");
    });
  }

  function wire() {
    var planBtn = $("alPlanBtn");
    if (planBtn) planBtn.addEventListener("click", plan);
    var refreshBtn = $("alRefreshBtn");
    if (refreshBtn) refreshBtn.addEventListener("click", refresh);
    var list = $("alList");
    if (list) list.addEventListener("click", onListClick);
  }

  window.ACTION_LOOP = { refresh: refresh, plan: plan, render: render };

  function boot() { wire(); refresh(); }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
