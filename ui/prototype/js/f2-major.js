/* f2-major.js · F2 专业导向岗位匹配向导（迭代一：选专业→画像→上传→双分报告） */
(function () {
  "use strict";

  var API = "";
  var RECENT_KEY = "f2_recent_majors";
  var QUICK_CODES = [
    ["080901", "计算机科学与技术"],
    ["080902", "软件工程"],
    ["080717", "人工智能"],
    ["080910", "数据科学与大数据技术"],
    ["120203", "会计学"],
    ["020301", "金融学"],
    ["030101", "法学"],
    ["050201", "英语"],
    ["080701", "电子信息工程"],
    ["080601", "电气工程及其自动化"],
    ["100201", "临床医学"],
    ["130508", "数字媒体艺术"]
  ];

  var $ = function (id) { return document.getElementById(id); };
  var state = {
    tree: null,
    selected: null,          // {code,name,path,profileStatus}
    profile: null,
    lastResult: null
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function fmtDate() {
    var d = new Date();
    function p(n) { return n < 10 ? "0" + n : "" + n; }
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
  }

  function showError(msg) {
    $("f2ErrorMsg").textContent = msg;
    $("f2Error").classList.remove("zy-hidden");
    $("f2Loading").classList.add("zy-hidden");
  }

  function setStep(n) {
    for (var i = 1; i <= 4; i++) {
      var panel = $("f2Step" + i);
      var step = document.querySelector('.f2-steps li[data-step="' + i + '"]');
      panel.classList.toggle("zy-hidden", i !== n);
      if (step) {
        step.classList.toggle("on", i === n);
        step.classList.toggle("done", i < n);
      }
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function saveRecent(code, name) {
    var recents = [];
    try { recents = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch (e) { recents = []; }
    recents = recents.filter(function (r) { return r.code !== code; });
    recents.unshift({ code: code, name: name });
    recents = recents.slice(0, 6);
    localStorage.setItem(RECENT_KEY, JSON.stringify(recents));
    renderRecents();
  }

  function renderRecents() {
    var recents = [];
    try { recents = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch (e) { recents = []; }
    var wrap = $("f2RecentWrap");
    if (!recents.length) { wrap.classList.add("zy-hidden"); return; }
    wrap.classList.remove("zy-hidden");
    $("f2RecentChips").innerHTML = recents.map(function (r) {
      return '<button type="button" class="f2-chip" data-code="' + esc(r.code) + '">' + esc(r.name) + "</button>";
    }).join("");
    bindChips($("f2RecentChips"));
  }

  function renderQuick() {
    $("f2QuickChips").innerHTML = QUICK_CODES.map(function (q) {
      return '<button type="button" class="f2-chip" data-code="' + esc(q[0]) + '">' + esc(q[1]) + "</button>";
    }).join("");
    bindChips($("f2QuickChips"));
  }

  function bindChips(root) {
    root.querySelectorAll(".f2-chip").forEach(function (chip) {
      chip.addEventListener("click", function () {
        var info = findMajor(chip.getAttribute("data-code"));
        if (info) selectMajor(info);
      });
    });
  }

  function findMajor(code) {
    if (!state.tree) return null;
    for (var i = 0; i < state.tree.categories.length; i++) {
      var cat = state.tree.categories[i];
      for (var j = 0; j < cat.classes.length; j++) {
        var cls = cat.classes[j];
        for (var k = 0; k < cls.majors.length; k++) {
          var m = cls.majors[k];
          if (m.code === code) {
            return { code: m.code, name: m.name, path: cat.name + " / " + cls.name };
          }
        }
      }
    }
    return null;
  }

  function buildTree() {
    var catSel = $("f2Cat");
    catSel.innerHTML = '<option value="">请选择门类</option>' + state.tree.categories.map(function (c) {
      return '<option value="' + esc(c.code) + '">' + esc(c.code) + " " + esc(c.name) + "</option>";
    }).join("");
  }

  function onCatChange() {
    var catCode = $("f2Cat").value;
    var clsSel = $("f2Cls"), majSel = $("f2Major");
    majSel.innerHTML = '<option value="">先选专业类</option>';
    majSel.disabled = true;
    if (!catCode) {
      clsSel.innerHTML = '<option value="">先选门类</option>';
      clsSel.disabled = true;
      return;
    }
    var cat = state.tree.categories.find(function (c) { return c.code === catCode; });
    clsSel.innerHTML = '<option value="">请选择专业类</option>' + cat.classes.map(function (cl) {
      return '<option value="' + esc(cl.code) + '">' + esc(cl.code) + " " + esc(cl.name) + "</option>";
    }).join("");
    clsSel.disabled = false;
  }

  function onClsChange() {
    var catCode = $("f2Cat").value, clsCode = $("f2Cls").value;
    var majSel = $("f2Major");
    if (!clsCode) {
      majSel.innerHTML = '<option value="">先选专业类</option>';
      majSel.disabled = true;
      return;
    }
    var cat = state.tree.categories.find(function (c) { return c.code === catCode; });
    var cls = cat.classes.find(function (c) { return c.code === clsCode; });
    majSel.innerHTML = '<option value="">请选择专业</option>' + cls.majors.map(function (m) {
      return '<option value="' + esc(m.code) + '">' + esc(m.code) + (m.flags ? " " + esc(m.flags) : "") + " " + esc(m.name) + "</option>";
    }).join("");
    majSel.disabled = false;
  }

  function onMajorChange() {
    var code = $("f2Major").value;
    if (!code) return;
    var info = findMajor(code);
    if (info) selectMajor(info);
  }

  function selectMajor(info) {
    state.selected = info;
    state.profile = null;
    saveRecent(info.code, info.name);
    $("f2Selected").innerHTML =
      '<b>' + esc(info.name) + "</b>" +
      '<div class="meta">' + esc(info.path) + " · 专业代码 " + esc(info.code) + "</div>";
    $("f2Selected").classList.remove("zy-hidden");
    $("f2Next1").disabled = false;
    setStep(2);
    loadProfile(info);
  }

  function loadProfile(info) {
    $("f2ProfileTitle").textContent = info.name;
    $("f2ProfileBody").innerHTML = '<div class="ai-status"><span class="ai-orb"></span>正在加载岗位画像…</div>';
    $("f2ProfileSummary").textContent = "";
    fetch(API + "/api/f2/majors/" + encodeURIComponent(info.code))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) throw new Error(data.message || "加载失败");
        state.selected.profileStatus = data.profile_status;
        renderProfile(data);
      })
      .catch(function (err) {
        $("f2ProfileBody").innerHTML =
          '<div class="f2-notice">画像加载失败：' + esc(err.message) + "。请确认后端服务已启动。</div>";
      });
  }

  function renderProfile(data) {
    var p = data.profile;
    if (!p) {
      $("f2ProfileSummary").textContent = "该专业暂未生成画像（建设中）。";
      $("f2ProfileBody").innerHTML =
        '<div class="f2-notice">「' + esc(data.major.name) + "」画像建设中。可继续上传简历并填写 JD，使用模式B（JD 精准匹配）；未覆盖专业均保留此降级路径。</div>";
      return;
    }
    $("f2ProfileSummary").textContent = p.summary;
    var html = "";
    html += '<div class="f2-subsec">对口方向（专业强相关）</div>';
    html += renderDirs(p.direct, "direct");
    html += '<div class="f2-subsec">衍生方向（可迁移）</div>';
    html += renderDirs(p.derivative, "derivative");
    html += '<div class="f2-notice">数据来源：' + esc(p.source || "人社部《职业信息与教育培训项目（专业）信息对应指引（2023年版）》") + "。每个方向含常见岗位与技能关键词，后续匹配将据此计算覆盖度。</div>";
    $("f2ProfileBody").innerHTML = html;
  }

  function renderDirs(dirs, kind) {
    return dirs.map(function (d) {
      var skills = (d.skills || []).map(function (s) {
        return '<span class="f2-kw"><span class="hit">' + esc(s) + "</span></span>";
      }).join("");
      return '<div class="f2-dir">' +
        '<div class="f2-dir-head">' +
          '<span class="f2-badge ' + (kind === "direct" ? "direct" : "derivative") + '">' + (kind === "direct" ? "对口" : "衍生") + "</span>" +
          '<span class="f2-badge lv-' + esc(d.level) + '">' + esc(d.level) + "对应</span>" +
          '<span class="occ">' + esc(d.occupation) + "</span>" +
        "</div>" +
        '<div class="titles">常见岗位：' + esc((d.titles || []).join(" / ")) + "</div>" +
        '<div style="font-size:13px;color:var(--zy-ink-2)">' + esc(d.description || "") + "</div>" +
        '<div class="f2-kw">' + skills + "</div>" +
      "</div>";
    }).join("");
  }

  var searchTimer = null;
  function onSearchInput() {
    clearTimeout(searchTimer);
    var q = $("f2Search").value.trim();
    if (!q) { $("f2SearchResults").classList.add("zy-hidden"); return; }
    searchTimer = setTimeout(function () {
      fetch(API + "/api/f2/majors/search?q=" + encodeURIComponent(q) + "&limit=20")
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var box = $("f2SearchResults");
          if (!data.items || !data.items.length) {
            box.innerHTML = '<div class="no-result">未找到匹配专业</div>';
          } else {
            box.innerHTML = data.items.map(function (m) {
              return '<button type="button" data-code="' + esc(m.code) + '">' +
                esc(m.name) + ' <span class="p">' + esc(m.code) + " · " + esc(m.category_name) + " / " + esc(m.class_name) + "</span></button>";
            }).join("");
            box.querySelectorAll("button").forEach(function (b) {
              b.addEventListener("click", function () {
                box.classList.add("zy-hidden");
                $("f2Search").value = "";
                var info = findMajor(b.getAttribute("data-code"));
                if (info) selectMajor(info);
              });
            });
          }
          box.classList.remove("zy-hidden");
        })
        .catch(function () {});
    }, 220);
  }

  var intentTimer = null;
  function onIntentInput() {
    clearTimeout(intentTimer);
    var q = $("f2Intent").value.trim();
    var box = $("f2IntentResults");
    if (!q) { box.innerHTML = ""; return; }
    intentTimer = setTimeout(function () {
      fetch(API + "/api/f2/intent?q=" + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          box.innerHTML = data.items.map(function (m) {
            return '<button type="button" class="f2-chip" data-code="' + esc(m.code) + '">' +
              esc(m.name) + (m.has_profile ? "" : "（画像建设中）") +
              "<small>" + esc(m.path) + "</small></button>";
          }).join("");
          box.querySelectorAll("button").forEach(function (b) {
            b.addEventListener("click", function () {
              box.innerHTML = "";
              $("f2Intent").value = "";
              var info = findMajor(b.getAttribute("data-code"));
              if (info) selectMajor(info);
            });
          });
        })
        .catch(function () {});
    }, 220);
  }

  function onModeInput() {
    var hasJd = $("f2Jd").value.trim().length > 0;
    $("f2ModeTag").textContent = hasJd ? "模式B：JD精准匹配" : "模式A：专业画像匹配";
    var resumeOk = $("f2Resume").value.trim().length >= 20;
    var building = state.selected && state.selected.profileStatus === "building";
    $("f2StartMatch").disabled = !(resumeOk && (!building || hasJd));
  }

  function startMatch() {
    var major = state.selected;
    if (!major) { showError("请先选择专业。"); return; }
    var resumeText = $("f2Resume").value.trim();
    var jdText = $("f2Jd").value.trim();
    if (resumeText.length < 20) { showError("简历内容过短，请粘贴完整简历（建议 ≥20 字）。"); return; }
    $("f2Error").classList.add("zy-hidden");
    $("f2Loading").classList.remove("zy-hidden");
    fetch(API + "/api/f2/match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ majorCode: major.code, resumeText: resumeText, jdText: jdText })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        $("f2Loading").classList.add("zy-hidden");
        if (data.error) { showError(data.message || "匹配失败"); return; }
        state.lastResult = data;
        renderReport(data);
        setStep(4);
        saveHistory(data);
      })
      .catch(function (err) {
        $("f2Loading").classList.add("zy-hidden");
        showError("网络错误：" + err.message + "（请确认后端服务运行在 8123 端口）");
      });
  }

  function ring(id, pct, num, label) {
    var el = $(id);
    el.style.setProperty("--pct", pct == null ? 0 : pct);
    el.querySelector(".num").textContent = num == null ? "--" : num;
    el.querySelector(".lbl").textContent = label;
  }

  function renderReport(data) {
    var s = data.scores || {};
    ring("f2FitRing", s.major_fit, s.major_fit == null ? "--" : s.major_fit, "专业契合");
    ring("f2CoverRing", s.coverage, s.coverage == null ? "--" : s.coverage, "岗位覆盖");
    $("f2OverallNum").textContent = s.overall == null ? "--" : s.overall;
    $("f2ModeLine").textContent = data.mode === "B" ? "模式B · JD 精准匹配" : "模式A · 专业画像匹配";

    var html = "";
    if (data.mode === "A") {
      html += '<h3>方向推荐与画像覆盖度</h3>';
      html += '<p class="f2-hint">' + esc(data.major.name) + " · " + esc(data.major.path) + "</p>";
      html += data.modeA.directions.map(function (d) {
        var kws = [];
        d.matched.forEach(function (k) { kws.push('<span class="hit">' + esc(k) + "</span>"); });
        d.gaps.forEach(function (k) { kws.push('<span class="miss">' + esc(k) + "</span>"); });
        return '<div class="f2-dir">' +
          '<div class="f2-dir-head">' +
            '<span class="f2-badge ' + (d.kind === "对口" ? "direct" : "derivative") + '">' + d.kind + "</span>" +
            '<span class="f2-badge lv-' + esc(d.level) + '">' + esc(d.level) + "对应</span>" +
            '<span class="occ">' + esc(d.occupation) + "</span>" +
            '<span class="f2-dir-score">' + d.score + "</span>" +
          "</div>" +
          '<div class="titles">常见岗位：' + esc((d.titles || []).join(" / ")) + "</div>" +
          '<div class="bar"><i style="width:' + d.score + '%"></i></div>' +
          '<div class="f2-kw">' + (kws.length ? kws.join("") : '<span style="color:var(--zy-ink-3);font-size:12px">未命中画像关键词</span>') + "</div>" +
          '<div class="ev">' + esc(d.description || "") + "</div>" +
        "</div>";
      }).join("");
      html += '<div class="f2-notice">' + esc(data.mode_notice || "") + " ｜ " + esc(data.scores.major_fit_notice || "") + "</div>";
    } else {
      var occ = data.modeB.occupation_hit;
      html += '<h3>JD 逐条要求四态判定' + (occ ? ' <span class="f2-tag">职业命中：' + esc(occ.occupation) + "（" + esc(occ.level) + "对应）</span>" : "") + "</h3>";
      html += '<div class="f2-subs">';
      var order = ["hard", "responsibility", "bonus", "term"];
      order.forEach(function (t) {
        var sub = data.modeB.subscores[t];
        if (!sub) return;
        html += '<div class="subbar"><div class="meta"><span>' + esc(sub.label) + (sub.count ? "（" + sub.count + "条）" : "") + "</span><span>" + sub.score + "</span></div>" +
          '<div class="track"><div class="fill" style="width:' + sub.score + '%"></div></div></div>';
      });
      html += "</div>";
      html += data.modeB.requirements.map(function (r) {
        var labels = { covered: "covered", weak: "weak", missing: "missing", unknown: "unknown" };
        return '<div class="req-item"><span class="badge ' + r.status + '">' + labels[r.status] + "</span>" +
          '<span class="txt"><b>[' + esc(r.typeLabel) + "]</b> " + esc(r.text) +
          (r.evidence && r.evidence.length ? '<span class="ev">证据命中：' + esc(r.evidence.join("、")) + "</span>" : "") +
          "</span></div>";
      }).join("");
      html += '<div class="f2-subsec">缺口分级与行动建议</div>';
      html += (data.modeB.gaps && data.modeB.gaps.length ? data.modeB.gaps.map(function (g) {
        return '<div class="req-item"><span class="badge ' + g.level.toLowerCase() + '">' + g.level + "</span>" +
          '<span class="txt">' + esc(g.text) + '<span class="ev">建议：' + esc(g.action) + "</span></span></div>";
      }).join("") : '<div class="f2-notice">无缺口，继续保持。</div>');
      html += '<div class="f2-notice">' + esc(data.mode_notice || "") + " ｜ " + esc(data.scores.major_fit_notice || "") + "</div>";
    }
    $("f2ReportBody").innerHTML = html;
  }

  function saveHistory(data) {
    if (!window.ZY_ACCOUNT) return;
    var title = data.major.name + " · " + (data.mode === "B" ? "JD匹配" : "画像匹配") + " " + (data.scores.overall == null ? "--" : data.scores.overall) + "分";
    window.ZY_ACCOUNT.addHistory({
      id: "f2-" + Date.now(),
      title: title,
      date: fmtDate(),
      status: "done",
      type: "F2"
    });
  }

  function wireFileDrop() {
    var drop = $("f2Drop"), file = $("f2File");
    drop.addEventListener("click", function () { file.click(); });
    drop.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); file.click(); }
    });
    file.addEventListener("change", function () { if (file.files[0]) readFile(file.files[0]); });
    ["dragenter", "dragover"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("over"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("over"); });
    });
    drop.addEventListener("drop", function (e) {
      var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) readFile(f);
    });
  }

  function readFile(f) {
    if (/\.(docx|pdf)$/i.test(f.name)) {
      $("f2Drop").innerHTML = '<svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 16V4m0 0L8 8m4-4l4 4M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3"/></svg><span>演示版支持 .txt 直接读取；.docx/.pdf 请在下方粘贴文本，正式版将接入服务端解析</span>';
      return;
    }
    var reader = new FileReader();
    reader.onload = function () { $("f2Resume").value = String(reader.result || "").trim(); onModeInput(); };
    reader.onerror = function () { showError("文件读取失败，请改为粘贴文本。"); };
    reader.readAsText(f, "utf-8");
  }

  function init() {
    renderQuick();
    renderRecents();
    $("f2Next1").addEventListener("click", function () { setStep(2); });
    $("f2Back1").addEventListener("click", function () { setStep(1); });
    $("f2Next2").addEventListener("click", function () { setStep(3); onModeInput(); });
    $("f2Back2").addEventListener("click", function () { setStep(2); });
    $("f2Back3").addEventListener("click", function () { setStep(3); });
    $("f2Restart").addEventListener("click", function () {
      $("f2Resume").value = "";
      $("f2Jd").value = "";
      setStep(1);
      onModeInput();
    });
    $("f2StartMatch").addEventListener("click", startMatch);
    $("f2ErrorRetry").addEventListener("click", startMatch);
    $("f2Search").addEventListener("input", onSearchInput);
    $("f2Search").addEventListener("blur", function () {
      setTimeout(function () { $("f2SearchResults").classList.add("zy-hidden"); }, 180);
    });
    $("f2Cat").addEventListener("change", onCatChange);
    $("f2Cls").addEventListener("change", onClsChange);
    $("f2Major").addEventListener("change", onMajorChange);
    $("f2Intent").addEventListener("input", onIntentInput);
    $("f2Resume").addEventListener("input", onModeInput);
    $("f2Jd").addEventListener("input", onModeInput);
    wireFileDrop();
    onModeInput();

    fetch(API + "/api/f2/majors/tree")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) throw new Error(data.message || "加载失败");
        state.tree = data;
        buildTree();
      })
      .catch(function (err) {
        showError("专业目录加载失败：" + err.message + "。请通过后端服务访问本页面（http://127.0.0.1:8123/pages/f2-match.html）。");
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
