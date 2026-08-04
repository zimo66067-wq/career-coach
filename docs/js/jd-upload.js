/* F2 JD submission: file selection, drop, and pasted text share one real API flow. */
(function () {
  "use strict";

  var allowedExtensions = ["pdf", "docx", "txt"];
  var MAX_FILE_BYTES = 10 * 1024 * 1024;
  var MIN_TEXT_CHARS = 20;
  var MAX_TEXT_CHARS = 200000;

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

  function prepareJdText(value) {
    var text = String(value || "").replace(/\r\n?/g, "\n").trim();
    if (!text) return { valid: false, message: "请先选择 JD 文件或粘贴 JD 正文。" };
    if (text.length < MIN_TEXT_CHARS) return { valid: false, message: "JD 正文至少需要 20 个字符。" };
    if (text.length > MAX_TEXT_CHARS) return { valid: false, message: "JD 正文不能超过 20 万个字符。" };
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
    if (code === "api_not_configured") return "匹配服务尚未接入此页面，暂时无法处理 JD。";
    if (code === "timeout") return "服务响应超时，请稍后重试。";
    if (code === "http_413" || code === "payload_too_large") return "文件或文本超过服务允许的大小，请精简后重试。";
    if (code === "model_not_configured") return "匹配服务尚未完成模型配置，请联系服务管理员。";
    if (code === "model_unavailable") return "匹配模型暂时不可用，请稍后重试。";
    if (code === "model_output_invalid") return "匹配结果未通过校验，请稍后重试。";
    if (code === "unreadable_file") return "未能读取该文件，请改为可复制文字的 PDF、DOCX、TXT 或直接粘贴正文。";
    if (code === "service_unavailable" || code === "network") return "匹配服务暂不可用，请稍后重试。";
    return (result && result.message) || fallback || "匹配未完成，请稍后重试。";
  }

  function init() {
    var card = document.getElementById("jdUploadCard");
    var dropzone = document.getElementById("jdDropzone");
    var input = document.getElementById("jdFileInput");
    var chooseButton = document.getElementById("chooseJdFile");
    var startButton = document.getElementById("startJdMatch");
    var status = document.getElementById("jdUploadStatus");
    var textButton = document.getElementById("openJdText");
    var textEntry = document.getElementById("jdTextEntry");
    var textInput = document.getElementById("jdTextInput");
    var cancelText = document.getElementById("cancelJdText");
    if (!card || !dropzone || !input || !chooseButton || !startButton || !status) return;

    var selectedFile = null;
    var isSubmitting = false;

    function setStatus(message, isError) {
      status.textContent = message;
      status.classList.toggle("is-error", !!isError);
      status.classList.toggle("is-success", !isError && !!message);
    }

    function showError(message) {
      var errorMessage = document.getElementById("jdErrorMessage");
      if (errorMessage) errorMessage.textContent = message;
      if (window.APP && typeof window.APP.setState === "function") window.APP.setState("error");
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
      setStatus("已选择\u201C" + file.name + "\u201D（" + formatFileSize(file.size) + "），请点击\u201C开始匹配\u201D。", false);
      startButton.hidden = false;
      startButton.disabled = false;
      startButton.focus();
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
    input.addEventListener("change", function () { selectFile(input.files && input.files[0]); });

    function submitFile(file) {
      if (isSubmitting) return;
      isSubmitting = true;
      if (window.APP && typeof window.APP.setState === "function") window.APP.setState("processing");

      var bridge = window.DataBridge;
      if (!bridge || typeof bridge.submitJD !== "function" || isStaticPagesWithoutApi()) {
        isSubmitting = false;
        showError(failureMessage({ error: "api_not_configured" }));
        return;
      }

      var formData = new FormData();
      formData.append("file", file);

      var url = (window.DUMATE_API_BASE || "").replace(/\/+$/, "") + "/api/wf03/jd";
      fetch(url, { method: "POST", body: formData, headers: { "X-Trace-Id": "t" + Date.now() } })
        .then(function (res) { return res.json(); })
        .then(function (res) {
          isSubmitting = false;
          if (res.error) {
            showError(failureMessage(res));
            return;
          }
          if (window.APP && typeof window.APP.setState === "function") window.APP.setState("success");
        })
        .catch(function () {
          isSubmitting = false;
          showError(failureMessage({ error: "network" }));
        });
    }

    function submitText() {
      var parsed = prepareJdText(textInput && textInput.value);
      if (!parsed.valid) {
        setStatus(parsed.message, true);
        if (textInput) textInput.focus();
        return;
      }
      isSubmitting = true;
      if (window.APP && typeof window.APP.setState === "function") window.APP.setState("processing");

      var bridge = window.DataBridge;
      if (!bridge || typeof bridge.submitJD !== "function" || isStaticPagesWithoutApi()) {
        isSubmitting = false;
        showError(failureMessage({ error: "api_not_configured" }));
        return;
      }

      bridge.submitJD(parsed.text).then(function (res) {
        isSubmitting = false;
        if (res.error) {
          showError(failureMessage(res));
          return;
        }
        if (window.APP && typeof window.APP.setState === "function") window.APP.setState("success");
      }).catch(function () {
        isSubmitting = false;
        showError(failureMessage({ error: "network" }));
      });
    }

    startButton.addEventListener("click", function () {
      if (!selectedFile) {
        setStatus("请先选择或拖入一份 JD。", true);
        return;
      }
      setStatus("正在上传\u201C" + selectedFile.name + "\u201D\u2026", false);
      startButton.disabled = true;
      submitFile(selectedFile);
    });

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
  }

  window.JdUpload = {
    validateFile: validateFile,
    formatFileSize: formatFileSize,
    prepareJdText: prepareJdText
  };
  document.addEventListener("DOMContentLoaded", init);
})();
