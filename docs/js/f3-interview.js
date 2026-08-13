/* f3-interview.js · F3 模拟面试交互主链路（阶段4）
 * - 生产模式真实调用 /api/wf04/start、/api/wf04/stream（SSE 流式追问）
 * - 会话快照保存到 sessionStorage，刷新/断线后可恢复
 * - 演示模式（?demo=1）不启用，由页面内演示脚本渲染合成数据
 */
(function () {
  "use strict";
  if (window.APP && window.APP.isDemoMode()) return;

  var API = String(window.DUMATE_API_BASE || "").replace(/\/+$/, "");
  var SNAP_KEY = "f3_session_snapshot_v1";
  var $ = function (id) { return document.getElementById(id); };
  var state = { sessionId: null, turns: [], ended: false };

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
    if (window.APP && typeof window.APP.setState === "function") {
      window.APP.setState(name);
    } else {
      document.body.setAttribute("data-state", name);
    }
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
      if (t.followUp && t.followUp.question) {
        html += '<div class="bubble q"><div class="who">面试官 · 追问</div>' + esc(t.followUp.question) +
          (t.followUp.reason ? '<div class="followup"><b>追问理由：</b>' + esc(t.followUp.reason) + "</div>" : "") + "</div>";
      }
    });
    box.innerHTML = html;
  }

  function showStreamed(text) {
    var target = $("f3StreamingBubble");
    if (!target) return;
    target.style.display = "";
    target.innerHTML = '<div class="bubble q"><div class="who">面试官 · 追问（流式）</div>' +
      esc(text) + '<span style="color:var(--zy-primary,#2f5fe8)">▍</span></div>';
  }

  function hideStreamed() {
    var target = $("f3StreamingBubble");
    if (target) target.style.display = "none";
  }

  function maybeAdvance(turn) {
    var no = $("f3TurnNo");
    if (turn.followUp && turn.followUp.question) {
      state.turns.push({
        index: turn.index,
        isFollowUp: true,
        question: turn.followUp.question,
        targets: [],
        answer: null,
        followUp: null,
      });
      if (no) no.textContent = String(turn.index) + "（追问）";
    } else {
      if (no) no.textContent = String((state.turns.length || 0) + 1);
    }
    renderTurns();
    saveSnapshot();
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
          turn.followUp = ev.followUp || null;
          hideStreamed();
          setView("success");
          maybeAdvance(turn);
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

  function submitAnswer() {
    var input = $("f3Answer");
    if (!input || !state.sessionId) return;
    var text = (input.value || "").trim();
    if (!text) return;
    var turn = state.turns[state.turns.length - 1];
    if (!turn) return;
    turn.answer = text;
    input.value = "";
    renderTurns();
    setView("processing");
    streamFollowUp(turn);
  }

  function startInterview() {
    var DB = window.DataBridge;
    if (!DB || typeof DB.startInterview !== "function") return;
    setView("processing");
    DB.startInterview({}, {}, []).then(function (res) {
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
        followUp: null
      }];
      state.ended = false;
      saveSnapshot();
      setView("success");
      renderTurns();
      hideStreamed();
      var no = $("f3TurnNo");
      if (no) no.textContent = "1";
      var input = $("f3Answer");
      if (input) input.value = "";
    }).catch(function (err) {
      setView("error");
      var msg = $("f3ErrorMsg");
      if (msg) msg.textContent = "网络错误：" + (err && err.message ? err.message : "未知错误");
    });
  }

  function endInterview() {
    var DB = window.DataBridge;
    if (DB && typeof DB.endInterview === "function" && state.sessionId) {
      DB.endInterview(state.sessionId).then(function () {
        clearSnapshot();
        setView("empty");
      }).catch(function () {
        clearSnapshot();
        setView("empty");
      });
    } else {
      clearSnapshot();
      setView("empty");
    }
  }

  function wire() {
    var startBtn = $("f3StartBtn");
    if (startBtn) startBtn.addEventListener("click", startInterview);
    var sendBtn = $("f3SendAnswer");
    if (sendBtn) sendBtn.addEventListener("click", submitAnswer);
    var endBtn = $("f3EndInterview");
    if (endBtn) endBtn.addEventListener("click", endInterview);
    var input = $("f3Answer");
    if (input) input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submitAnswer();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    wire();
    var snap = restoreSnapshot();
    if (snap && snap.sessionId && snap.turns && snap.turns.length) {
      state = snap;
      setView("success");
      renderTurns();
      hideStreamed();
      var no = $("f3TurnNo");
      if (no) no.textContent = String(state.turns.length + 1);
    }
  });
})();
