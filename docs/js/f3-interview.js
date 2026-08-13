/* f3-interview.js · F3 打字式对话面试主链路
 * - 生产模式真实调用 /api/wf04/start、/api/wf04/stream（SSE 流式追问/下一题）
 * - 每轮输出即时反馈（优点/不足/追问），结束生成综合报告（I 分/优点/不足/下一步）
 * - 会话快照保存到 sessionStorage，刷新后可恢复
 * - 演示模式（?demo=1）不启用，由页面内演示脚本渲染合成数据
 */
(function () {
  "use strict";
  if (window.APP && window.APP.isDemoMode()) return;

  var API = String(window.DUMATE_API_BASE || "").replace(/\/+$/, "");
  var SNAP_KEY = "f3_session_snapshot_v1";
  var $ = function (id) { return document.getElementById(id); };
  var state = { sessionId: null, turns: [], ended: false, report: null };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function consentToken() {
    try {
      return window.DataBridge && window.DataBridge._cache
        ? window.DataBridge._cache.get("consentToken") : null;
    } catch (e) { return null; }
  }

  function saveSnapshot() {
    try { sessionStorage.setItem(SNAP_KEY, JSON.stringify(state)); } catch (e) {}
  }
  function restoreSnapshot() {
    try {
      var raw = sessionStorage.getItem(SNAP_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }
  function clearSnapshot() {
    try { sessionStorage.removeItem(SNAP_KEY); } catch (e) {}
  }

  function setView(name) {
    // 生产模式直接设置 body data-state（绕过 APP 状态白名单，支持 report 视图）
    if (window.APP && window.APP.isDemoMode && window.APP.isDemoMode()) {
      if (window.APP.setState) window.APP.setState(name);
      return;
    }
    document.body.setAttribute("data-state", name);
  }

  function renderTurns() {
    var box = $("turns");
    if (!box) return;
    var html = "";
    state.turns.forEach(function (t) {
      var label = t.isFollowUp ? "面试官 · 追问" : "面试官 · 第" + t.index + "题";
      var targets = (!t.isFollowUp && t.targets && t.targets.length)
        ? "（考察：" + esc(t.targets.join(" / ")) + "）" : "";
      html += '<div class="bubble q"><div class="who">' + label + targets + "</div>" + esc(t.question) + "</div>";
      if (t.answer) {
        html += '<div class="bubble a"><div class="who">你</div>' + esc(t.answer) + "</div>";
      }
      if (t.evaluation) {
        html += renderEvaluation(t.evaluation);
      }
    });
    box.innerHTML = html;
    box.scrollTop = box.scrollHeight;
  }

  function renderEvaluation(ev) {
    var s = '<div class="bubble fb"><div class="who">AI 即时评估</div>';
    if (ev.strengths && ev.strengths.length) {
      s += '<div class="fb-line"><b>优点：</b>' + ev.strengths.map(function (x) {
        return '<span class="chip ok">' + esc(x) + "</span>";
      }).join("") + "</div>";
    }
    if (ev.weaknesses && ev.weaknesses.length) {
      s += '<div class="fb-line"><b>待补充：</b>' + ev.weaknesses.map(function (x) {
        return '<span class="chip warn">' + esc(x) + "</span>";
      }).join("") + "</div>";
    }
    var sc = ev.subscores;
    if (sc) {
      s += '<div class="fb-line sub">结构 ' + (sc.structure != null ? sc.structure : "-") +
        " ｜ 相关 " + (sc.relevance != null ? sc.relevance : "-") +
        " ｜ 具体 " + (sc.specificity != null ? sc.specificity : "-") +
        " ｜ 追问适应 " + (sc.followup_adaptation != null ? sc.followup_adaptation : "-") +
        " ｜ 清晰 " + (sc.clarity != null ? sc.clarity : "-") + "</div>";
    }
    return s + "</div>";
  }

  function showStreamed(text) {
    var target = $("f3StreamingBubble");
    if (!target) return;
    target.style.display = "";
    target.innerHTML = '<div class="bubble q"><div class="who">面试官 · 正在输入</div>' +
      esc(text) + '<span class="caret">▍</span></div>';
  }

  function hideStreamed() {
    var target = $("f3StreamingBubble");
    if (target) target.style.display = "none";
  }

  function updateProgress() {
    var no = $("f3TurnNo");
    var mainCount = state.turns.filter(function (t) { return !t.isFollowUp; }).length;
    if (no) no.textContent = String(Math.max(1, mainCount));
  }

  function applyDone(turn, ev) {
    if (ev && ev.evaluation) turn.evaluation = ev.evaluation;
    if (ev && ev.nextQuestion && ev.nextQuestion.done) {
      renderTurns();
      hideStreamed();
      setView("success");
      finishInterview();
      return;
    }
    if (ev && ev.nextQuestion && ev.nextQuestion.question) {
      state.turns.push({
        index: state.turns.filter(function (t) { return !t.isFollowUp; }).length + 1,
        isFollowUp: false,
        question: ev.nextQuestion.question,
        targets: ev.nextQuestion.targets || [],
        answer: null,
        evaluation: null
      });
    } else if (ev && ev.followUp && ev.followUp.question) {
      state.turns.push({
        index: state.turns[state.turns.length - 1].index,
        isFollowUp: true,
        question: ev.followUp.question,
        targets: [],
        answer: null,
        evaluation: null
      });
    }
    renderTurns();
    saveSnapshot();
    updateProgress();
    setView("success");
  }

  function streamFollowUp(turn) {
    var url = API + "/api/wf04/stream";
    var headers = { "Content-Type": "application/json" };
    var token = consentToken();
    if (token) headers["X-Consent-Token"] = token;
    fetch(url, {
      method: "POST",
      headers: headers,
      body: JSON.stringify({ session_id: state.sessionId, answer_text: turn.answer })
    }).then(function (r) {
      if (!r.ok || !r.body) { throw new Error("HTTP " + r.status); }
      var reader = r.body.getReader();
      var decoder = new TextDecoder("utf-8");
      var buf = "";
      var streamed = "";
      function handleEvent(block) {
        var dataLine = block.split("\n").filter(function (l) {
          return l.indexOf("data: ") === 0;
        }).join("\n").slice(6);
        if (!dataLine) return;
        var ev;
        try { ev = JSON.parse(dataLine); } catch (e) { return; }
        if (ev.type === "fragment") {
          streamed += ev.text || "";
          showStreamed(streamed);
        } else if (ev.type === "done") {
          hideStreamed();
          applyDone(turn, ev);
        }
      }
      function pump() {
        return reader.read().then(function (res) {
          if (res.done) {
            hideStreamed();
            setView("success");
            renderTurns();
            saveSnapshot();
            return;
          }
          buf += decoder.decode(res.value, { stream: true });
          var parts = buf.split("\n\n");
          buf = parts.pop();
          parts.forEach(handleEvent);
          return pump();
        });
      }
      return pump();
    }).catch(function (err) {
      console.warn("[F3] 流式追问失败:", err);
      hideStreamed();
      setView("success");
      renderTurns();
    });
  }

  function submitAnswer(text) {
    var input = $("f3Answer");
    if (!state.sessionId) return;
    text = (text !== undefined && text !== null ? String(text) : (input ? input.value : "")).trim();
    if (!text) return;
    var turn = state.turns[state.turns.length - 1];
    if (!turn) return;
    turn.answer = text;
    if (input) input.value = "";
    renderTurns();
    setView("processing");
    streamFollowUp(turn);
  }

  function ensureConsent(DB) {
    if (consentToken() || !DB || typeof DB.submitConsent !== "function") return Promise.resolve();
    return DB.submitConsent().then(function (r) {
      if (!r || r.error) console.warn("[F3] 自动同意未成功，继续尝试开始面试:", r && r.message);
    }).catch(function (err) {
      console.warn("[F3] 自动同意失败，继续尝试开始面试:", err);
    });
  }

  function startInterview() {
    var DB = window.DataBridge;
    if (!DB || typeof DB.startInterview !== "function") return;
    setView("processing");
    ensureConsent(DB).then(function () {
      return DB.startInterview({}, {}, []);
    }).then(function (res) {
      if (!res || res.error || !res.firstQuestion) {
        setView("error");
        var msg = $("f3ErrorMsg");
        if (msg) msg.textContent = (res && res.message) || "未能开始面试，请稍后重试。";
        return;
      }
      state.sessionId = res.session_id;
      state.turns = [{
        index: 1,
        isFollowUp: false,
        question: res.firstQuestion,
        targets: res.targets || [],
        answer: null,
        evaluation: null
      }];
      state.ended = false;
      state.report = null;
      saveSnapshot();
      renderTurns();
      hideStreamed();
      updateProgress();
      setView("success");
      var input = $("f3Answer");
      if (input) input.value = "";
    }).catch(function (err) {
      setView("error");
      var msg = $("f3ErrorMsg");
      if (msg) msg.textContent = "网络错误：" + (err && err.message ? err.message : "未知错误");
    });
  }

  function renderReport(res) {
    var box = $("f3Report");
    if (!box) return;
    state.report = res || null;
    saveSnapshot();
    var html = '<div class="card"><h3>面试综合报告</h3>';
    if (res) {
      html += '<div class="score-line">I 分：<b>' + (res.score_I != null ? esc(String(res.score_I)) : "—") +
        '</b><span class="muted">（满分 100）</span></div>';
      var ss = res.i_subscores || {};
      var dims = [
        ["structure", "结构完整度"], ["relevance", "内容相关性"], ["specificity", "具体程度"],
        ["followup_adaptation", "追问适应度"], ["clarity", "表达清晰度"]
      ];
      dims.forEach(function (d) {
        var v = ss[d[0]];
        if (v == null) return;
        html += '<div class="bar-row"><span class="bar-label">' + d[1] + "</span>" +
          '<span class="bar"><span class="bar-fill" style="width:' + Math.max(0, Math.min(100, v)) + '%"></span></span>' +
          '<span class="bar-val">' + esc(String(v)) + "</span></div>";
      });
      html += '<div class="report-md">' + esc(res.report || "暂无报告") + "</div>";
    } else {
      html += '<p class="muted">报告生成失败，请重试。</p>';
    }
    html += '<div class="report-actions"><button class="btn primary" id="f3RestartBtn" type="button">再练一次</button></div></div>';
    box.innerHTML = html;
    var restart = $("f3RestartBtn");
    if (restart) restart.addEventListener("click", function () {
      clearSnapshot();
      state = { sessionId: null, turns: [], ended: false, report: null };
      setView("empty");
    });
  }

  function finishInterview() {
    var DB = window.DataBridge;
    if (!DB || typeof DB.endInterview !== "function" || !state.sessionId) {
      renderReport(null);
      setView("report");
      return;
    }
    setView("processing");
    DB.endInterview(state.sessionId).then(function (res) {
      state.ended = true;
      saveSnapshot();
      renderReport(res);
      setView("report");
    }).catch(function (err) {
      console.warn("[F3] 报告生成失败:", err);
      renderReport(null);
      setView("report");
    });
  }

  function wire() {
    var startBtn = $("f3StartBtn");
    if (startBtn) startBtn.addEventListener("click", startInterview);
    var sendBtn = $("f3SendAnswer");
    if (sendBtn) sendBtn.addEventListener("click", function () { submitAnswer(); });
    var endBtn = $("f3EndInterview");
    if (endBtn) endBtn.addEventListener("click", finishInterview);
    var retryBtn = $("f3RetryBtn");
    if (retryBtn) retryBtn.addEventListener("click", startInterview);
    var input = $("f3Answer");
    if (input) input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submitAnswer();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    wire();
    var snap = restoreSnapshot();
    if (snap && snap.sessionId) {
      state = snap;
      if (state.ended && state.report) {
        renderReport(state.report);
        setView("report");
        return;
      }
      if (state.turns && state.turns.length) {
        setView("success");
        renderTurns();
        hideStreamed();
        updateProgress();
      }
    }
  });

  window.F3Interview = {
    startInterview: startInterview,
    submitAnswer: submitAnswer,
    finishInterview: finishInterview,
    getState: function () { return state; }
  };
})();
