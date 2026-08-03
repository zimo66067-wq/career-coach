/* F1 resume submission: file selection, drop, and pasted text share one real API flow. */
(function () {
  "use strict";

  var allowedExtensions = ["pdf", "docx", "txt"];
  var MAX_FILE_BYTES = 10 * 1024 * 1024;
  var MIN_TEXT_CHARS = 20;
  var MAX_TEXT_CHARS = 200000;
  var scoreLabels = {
    structure: "结构完整度",
    clarity: "表达清晰度",
    achievement_evidence: "成果证据",
    skill_evidence: "技能证据",
    ats_readability: "ATS 可读性"
  };
  var scoreWeights = {
    structure: 15,
    clarity: 20,
    achievement_evidence: 25,
    skill_evidence: 20,
    ats_readability: 20
  };

  function fileExtension(name) {
    var parts = String(name || "").split(".");
    return parts.length > 1 ? parts.pop().toLowerCase() : "";
  }

  function validateFile(file) {
    if (!file || !file.name) {
      return { valid: false, message: "未检测到可上传的文件。" };
    }
    if (allowedExtensions.indexOf(fileExtension(file.name)) === -1) {
      return { valid: false, message: "仅支持 PDF、DOCX 或 TXT 格式。" };
    }
    if (typeof file.size === "number" && file.size > MAX_FILE_BYTES) {
      return { valid: false, message: "文件不能超过 10 MB。" };
    }
    return { valid: true };
  }

  function formatFileSize(size) {
    if (typeof size !== "number" || size < 0) return "";
    if (size < 1024) return size + " B";
    if (size < 1024 * 1024) return (size / 1024).toFixed(1) + " KB";
    return (size / (1024 * 1024)).toFixed(1) + " MB";
  }

  function prepareResumeText(value) {
    var text = String(value || "").replace(/\r\n?/g, "\n").trim();
    if (!text) return { valid: false, message: "请先选择简历文件或粘贴简历正文。" };
    if (text.length < MIN_TEXT_CHARS) return { valid: false, message: "简历正文至少需要 20 个字符。" };
    if (text.length > MAX_TEXT_CHARS) return { valid: false, message: "简历正文不能超过 20 万个字符。" };
    return { valid: true, text: text };
  }

  function isStaticPagesWithoutApi() {
    var location = window.location || {};
    return /\.github\.io$/i.test(location.hostname || "") && !window.DUMATE_API_BASE;
  }

  function isRealResponse(result) {
    return !!result && !result.error && !result.degraded && !result.demo_data;
  }

  function failureMessage(result, fallback) {
    var code = result && result.error;
    if (code === "api_not_configured") return "诊断服务尚未接入此页面，暂时无法处理简历。";
    if (code === "timeout") return "服务响应超时，请稍后重试。";
    if (code === "http_413" || code === "payload_too_large") return "文件或文本超过服务允许的大小，请精简后重试。";
    if (code === "model_not_configured") return "诊断服务尚未完成模型配置，请联系服务管理员。";
    if (code === "model_unavailable") return "诊断模型暂时不可用，请稍后重试。";
    if (code === "model_output_invalid") return "诊断结果未通过证据校验，请稍后重试。";
    if (code === "unreadable_file") return "未能读取该文件，请改为可复制文字的 PDF、DOCX、TXT 或直接粘贴正文。";
    if (code === "service_unavailable" || code === "network") return "诊断服务暂不可用，请稍后重试。";
    return (result && result.message) || fallback || "诊断未完成，请稍后重试。";
  }

  function createSubmissionFlow(options) {
    options = options || {};
    var bridge = options.bridge;
    var onProcessing = typeof options.onProcessing === "function" ? options.onProcessing : function () {};
    var ensureConsent = typeof options.ensureConsent === "function" ? options.ensureConsent : async function () { return { ok: true }; };

    function unavailable() {
      return { ok: false, error: "api_not_configured", message: failureMessage({ error: "api_not_configured" }) };
    }

    async function diagnose(text) {
      var result;
      try {
        result = await bridge.diagnoseResume(text);
      } catch (error) {
        return { ok: false, error: "network", message: failureMessage({ error: "network" }) };
      }
      if (!isRealResponse(result)) {
        return { ok: false, error: (result && result.error) || "service_unavailable", message: failureMessage(result) };
      }
      if (!result.resumeProfile || !result.resumeProfile.subscores) {
        return { ok: false, error: "invalid_response", message: "诊断服务返回的数据不完整，请稍后重试。" };
      }
      return { ok: true, resumeText: text, diagnosis: result };
    }

    async function confirmConsent() {
      var result;
      try {
        result = await ensureConsent();
      } catch (error) {
        return { ok: false, error: "consent_unavailable", message: "无法确认数据处理同意，请稍后重试。" };
      }
      if (result === true || (result && result.ok)) return null;
      return {
        ok: false,
        error: (result && (result.error || result.error_code)) || "consent_required",
        message: (result && result.message) || "请先阅读并勾选数据处理说明。"
      };
    }

    return {
      submitFile: async function (file) {
        var validation = validateFile(file);
        if (!validation.valid) return { ok: false, error: "invalid_file", message: validation.message };
        if (isStaticPagesWithoutApi() || !bridge || typeof bridge.uploadResume !== "function" || typeof bridge.diagnoseResume !== "function") return unavailable();
        var consentError = await confirmConsent();
        if (consentError) return consentError;

        onProcessing();
        var uploaded;
        try {
          uploaded = await bridge.uploadResume(file);
        } catch (error) {
          return { ok: false, error: "network", message: failureMessage({ error: "network" }) };
        }
        if (!isRealResponse(uploaded)) {
          return { ok: false, error: (uploaded && uploaded.error) || "service_unavailable", message: failureMessage(uploaded) };
        }
        var parsed = prepareResumeText(uploaded.resumeText);
        if (!parsed.valid) {
          return { ok: false, error: "invalid_upload", message: "上传完成，但未能读取到有效的简历正文。" };
        }
        return diagnose(parsed.text);
      },
      submitText: async function (value) {
        var parsed = prepareResumeText(value);
        if (!parsed.valid) return { ok: false, error: "invalid_text", message: parsed.message };
        if (isStaticPagesWithoutApi() || !bridge || typeof bridge.diagnoseResume !== "function") return unavailable();
        var consentError = await confirmConsent();
        if (consentError) return consentError;

        onProcessing();
        return diagnose(parsed.text);
      }
    };
  }

  function boundedScore(value) {
    var score = Number(value);
    if (!isFinite(score)) return null;
    return Math.max(0, Math.min(100, Math.round(score)));
  }

  function scoreFromDiagnosis(diagnosis) {
    var profile = diagnosis.resumeProfile || {};
    var direct = boundedScore(diagnosis.score_R);
    if (direct !== null) return direct;
    direct = boundedScore(profile.score_R);
    if (direct !== null) return direct;

    var weighted = 0;
    var weightTotal = 0;
    Object.keys(scoreWeights).forEach(function (key) {
      var score = boundedScore(profile.subscores && profile.subscores[key] && profile.subscores[key].score);
      if (score !== null) {
        weighted += score * scoreWeights[key];
        weightTotal += scoreWeights[key];
      }
    });
    return weightTotal ? Math.round(weighted / weightTotal) : null;
  }

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function renderSubscores(profile) {
    var container = document.getElementById("subbars");
    if (!container) return;
    container.textContent = "";
    Object.keys(scoreWeights).forEach(function (key) {
      var item = profile.subscores && profile.subscores[key];
      var score = boundedScore(item && item.score);
      if (score === null) return;
      var row = element("div", "subbar");
      var meta = element("div", "meta");
      meta.appendChild(element("span", "", (scoreLabels[key] || key) + "（权重 " + scoreWeights[key] + "%）"));
      meta.appendChild(element("b", "", String(score)));
      var track = element("div", "track");
      var fill = element("div", "fill");
      fill.style.width = score + "%";
      track.appendChild(fill);
      row.appendChild(meta);
      row.appendChild(track);
      container.appendChild(row);
    });
  }

  function renderReasons(profile, suggestions) {
    var list = document.getElementById("reasonList");
    if (!list) return;
    list.textContent = "";
    Object.keys(scoreWeights).forEach(function (key) {
      var item = profile.subscores && profile.subscores[key];
      if (!item) return;
      var reason = element("div", "reason-item");
      var quote = item.evidence_quote || item.evidence || item.quote || "";
      reason.dataset.quote = encodeURIComponent(String(quote));
      reason.tabIndex = 0;
      reason.appendChild(element("b", "", scoreLabels[key] || key));
      reason.appendChild(element("div", "reason-text", item.reason || item.suggestion || "已完成该维度评估。"));
      if (item.suggestion) reason.appendChild(element("span", "tag", item.suggestion));
      list.appendChild(reason);
    });
    (profile.suggestions && profile.suggestions.length ? profile.suggestions : (suggestions || [])).forEach(function (suggestion) {
      var reason = element("div", "reason-item");
      reason.dataset.quote = encodeURIComponent(String(suggestion.evidence_quote || suggestion.quote || ""));
      reason.tabIndex = 0;
      reason.appendChild(element("b", "", suggestion.title || "修改建议"));
      reason.appendChild(element("div", "reason-text", suggestion.text || suggestion.suggestion || ""));
      list.appendChild(reason);
    });
  }

  function renderDiagnosis(result, resumeText) {
    var profile = result.diagnosis.resumeProfile;
    var noticeNode = document.getElementById("resumeDiagnosisNotice");
    var noticeText = result.diagnosis.diagnosis_notice;
    if (noticeNode) {
      var noticeBody = noticeNode.querySelector("p");
      if (noticeBody) noticeBody.textContent = typeof noticeText === "string" ? noticeText : "";
      noticeNode.hidden = !noticeText;
    }
    var score = scoreFromDiagnosis(result.diagnosis);
    var scoreText = score === null ? "--" : String(score);
    var scoreNode = document.getElementById("resumeScore");
    var ring = document.getElementById("resumeScoreRing");
    if (scoreNode) scoreNode.textContent = scoreText;
    if (ring && score !== null) {
      ring.style.setProperty("--pct", score);
      ring.setAttribute("aria-label", "诊断分 R：" + score + " 分");
    }
    renderSubscores(profile);
    renderReasons(profile, result.diagnosis.suggestions);
    if (window.EVIDENCE && typeof window.EVIDENCE.renderDoc === "function") {
      window.EVIDENCE.renderDoc("resumeDoc", resumeText);
      if (typeof window.EVIDENCE.bindReasons === "function") window.EVIDENCE.bindReasons();
    }
  }

  function init() {
    var card = document.getElementById("resumeUploadCard");
    var dropzone = document.getElementById("resumeDropzone");
    var input = document.getElementById("resumeFileInput");
    var chooseButton = document.getElementById("chooseResumeFile");
    var startButton = document.getElementById("startResumeDiagnosis");
    var status = document.getElementById("resumeUploadStatus");
    var textButton = document.getElementById("openResumeText");
    var textEntry = document.getElementById("resumeTextEntry");
    var textInput = document.getElementById("resumeTextInput");
    var cancelText = document.getElementById("cancelResumeText");
    var retryButton = document.getElementById("retryResumeDiagnosis");
    var returnButton = document.getElementById("returnToResumeUpload");
    var consentCheckbox = document.getElementById("resumeConsent");
    if (!card || !dropzone || !input || !chooseButton || !startButton || !status) return;

    var selectedFile = null;
    var lastAttempt = null;
    var isSubmitting = false;
    var flow = createSubmissionFlow({
      bridge: window.DataBridge,
      onProcessing: function () {
        if (window.APP && typeof window.APP.setState === "function") window.APP.setState("processing");
      },
      ensureConsent: async function () {
        if (!consentCheckbox || !consentCheckbox.checked) {
          return { ok: false, error: "consent_required", message: "请先阅读并勾选数据处理说明。" };
        }
        if (!window.DataBridge || typeof window.DataBridge.submitConsent !== "function") {
          return { ok: false, error: "consent_unavailable", message: "同意记录服务暂不可用，请稍后重试。" };
        }
        var consent = await window.DataBridge.submitConsent("resume_session");
        if (consent && !consent.error && consent.status === "ACCEPTED") return { ok: true };
        return {
          ok: false,
          error: (consent && consent.error) || "consent_unavailable",
          message: (consent && consent.message) || "同意记录服务暂不可用，请稍后重试。"
        };
      }
    });

    function setStatus(message, isError) {
      status.textContent = message;
      status.classList.toggle("is-error", !!isError);
      status.classList.toggle("is-success", !isError && !!message);
    }

    function showError(message) {
      var errorMessage = document.getElementById("resumeErrorMessage");
      if (errorMessage) errorMessage.textContent = message;
      if (window.APP && typeof window.APP.setState === "function") window.APP.setState("error");
    }

    function finish(outcome) {
      isSubmitting = false;
      if (!outcome || !outcome.ok) {
        showError((outcome && outcome.message) || "诊断未完成，请稍后重试。");
        return;
      }
      renderDiagnosis(outcome, outcome.resumeText);
      if (window.APP && typeof window.APP.setState === "function") window.APP.setState("success");
    }

    function submit(promiseFactory) {
      if (isSubmitting) return;
      isSubmitting = true;
      Promise.resolve().then(promiseFactory).then(finish).catch(function () {
        finish({ ok: false, error: "network", message: failureMessage({ error: "network" }) });
      });
    }

    function selectFile(file) {
      var validation = validateFile(file);
      if (!validation.valid) {
        setStatus(validation.message, true);
        startButton.hidden = true;
        startButton.disabled = true;
        return;
      }
      selectedFile = file;
      card.classList.add("has-file");
      setStatus("已选择“" + file.name + "”（" + formatFileSize(file.size) + "），请点击“开始诊断”。", false);
      lastAttempt = { type: "file", value: file };
      startButton.hidden = false;
      startButton.disabled = false;
      startButton.focus();
    }

    function submitSelectedFile() {
      if (!selectedFile) {
        setStatus("请先选择或拖入一份简历。", true);
        return;
      }
      setStatus("正在上传“" + selectedFile.name + "”…", false);
      startButton.disabled = true;
      submit(function () { return flow.submitFile(selectedFile); });
    }

    function submitText() {
      var parsed = prepareResumeText(textInput && textInput.value);
      if (!parsed.valid) {
        setStatus(parsed.message, true);
        if (textInput) textInput.focus();
        return;
      }
      setStatus("正在提交文本简历…", false);
      lastAttempt = { type: "text", value: parsed.text };
      submit(function () { return flow.submitText(parsed.text); });
    }

    function openFilePicker() {
      input.value = "";
      input.click();
    }

    ["dragenter", "dragover"].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropzone.classList.add("is-dragging");
      });
    });
    ["dragleave", "drop"].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropzone.classList.remove("is-dragging");
      });
    });
    dropzone.addEventListener("drop", function (event) {
      selectFile(event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0]);
    });
    dropzone.addEventListener("click", function (event) {
      if (event.target.closest && event.target.closest("button, textarea, label, form")) return;
      openFilePicker();
    });
    dropzone.addEventListener("keydown", function (event) {
      if (event.target !== dropzone) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openFilePicker();
      }
    });
    chooseButton.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      openFilePicker();
    });
    startButton.addEventListener("click", function () { submitSelectedFile(); });
    input.addEventListener("change", function () { selectFile(input.files && input.files[0]); });

    if (textButton && textEntry && textInput) {
      textButton.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        textEntry.hidden = false;
        startButton.hidden = true;
        textInput.focus();
      });
      textEntry.addEventListener("submit", function (event) {
        event.preventDefault();
        submitText();
      });
    }
    if (cancelText && textEntry) {
      cancelText.addEventListener("click", function () {
        textEntry.hidden = true;
        startButton.hidden = !selectedFile;
        setStatus("", false);
      });
    }
    if (retryButton) {
      retryButton.addEventListener("click", function () {
        if (!lastAttempt) {
          showError("请先选择简历文件或粘贴简历正文。 ");
          return;
        }
        if (lastAttempt.type === "file") {
          selectFile(lastAttempt.value);
          submitSelectedFile();
        }
        else if (textInput) {
          textInput.value = lastAttempt.value;
          submitText();
        }
      });
    }
    if (returnButton) {
      returnButton.addEventListener("click", function () {
        if (window.APP && typeof window.APP.setState === "function") window.APP.setState("empty");
        setStatus("可重新选择文件、拖入文件或粘贴文本。", false);
      });
    }

    window.ResumeUpload.getSelectedFile = function () { return selectedFile; };
  }

  window.ResumeUpload = {
    validateFile: validateFile,
    formatFileSize: formatFileSize,
    prepareResumeText: prepareResumeText,
    createSubmissionFlow: createSubmissionFlow
  };
  document.addEventListener("DOMContentLoaded", init);
})();
