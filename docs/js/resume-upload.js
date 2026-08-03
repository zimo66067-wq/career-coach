/* Resume-file intake for the F1 empty state. No file is sent until a later analysis action explicitly uses it. */
(function () {
  "use strict";

  var allowedExtensions = ["pdf", "docx", "txt"];

  function fileExtension(fileName) {
    var lastDot = String(fileName || "").lastIndexOf(".");
    return lastDot === -1 ? "" : String(fileName).slice(lastDot + 1).toLowerCase();
  }

  function validateFile(file) {
    if (!file || !file.name) {
      return { valid: false, message: "未检测到可用文件，请重新选择。" };
    }
    if (allowedExtensions.indexOf(fileExtension(file.name)) === -1) {
      return { valid: false, message: "仅支持 PDF、DOCX 或 TXT 格式的简历。" };
    }
    return { valid: true };
  }

  function formatFileSize(bytes) {
    if (typeof bytes !== "number" || bytes < 0) return "大小未知";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function init() {
    var card = document.getElementById("resumeUploadCard");
    var dropzone = document.getElementById("resumeDropzone");
    var input = document.getElementById("resumeFileInput");
    var chooseButton = document.getElementById("chooseResumeFile");
    var status = document.getElementById("resumeUploadStatus");
    var selectedFile = null;

    if (!card || !dropzone || !input || !chooseButton || !status) return;

    function setStatus(message, type) {
      status.textContent = message;
      status.classList.toggle("is-error", type === "error");
      status.classList.toggle("is-selected", type === "selected");
    }

    function openFilePicker() {
      input.value = "";
      input.click();
    }

    function acceptFile(file) {
      var check = validateFile(file);
      dropzone.classList.remove("is-dragging");

      if (!check.valid) {
        selectedFile = null;
        card.classList.remove("has-file");
        dropzone.setAttribute("aria-label", "简历文件投放区域");
        setStatus(check.message, "error");
        return;
      }

      selectedFile = file;
      card.classList.add("has-file");
      dropzone.setAttribute("aria-label", "已选择简历文件：" + file.name);
      setStatus("已选择：" + file.name + "（" + formatFileSize(file.size) + "）", "selected");
      document.dispatchEvent(new CustomEvent("resume-file-selected", { detail: { file: selectedFile } }));
    }

    function acceptFiles(files) {
      if (!files || !files.length) {
        acceptFile(null);
        return;
      }
      if (files.length > 1) {
        dropzone.classList.remove("is-dragging");
        setStatus("请一次选择或拖入一份简历。", "error");
        return;
      }
      acceptFile(files[0]);
    }

    ["dragenter", "dragover", "dragleave", "drop"].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        event.stopPropagation();
      });
    });
    dropzone.addEventListener("dragenter", function () { dropzone.classList.add("is-dragging"); });
    dropzone.addEventListener("dragover", function () { dropzone.classList.add("is-dragging"); });
    dropzone.addEventListener("dragleave", function () { dropzone.classList.remove("is-dragging"); });
    dropzone.addEventListener("drop", function (event) { acceptFiles(event.dataTransfer.files); });
    dropzone.addEventListener("click", openFilePicker);
    dropzone.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openFilePicker();
      }
    });
    chooseButton.addEventListener("click", openFilePicker);
    input.addEventListener("change", function () { acceptFiles(input.files); });

    window.ResumeUpload = {
      getSelectedFile: function () { return selectedFile; },
      validateFile: validateFile,
      formatFileSize: formatFileSize
    };
  }

  window.ResumeUpload = {
    validateFile: validateFile,
    formatFileSize: formatFileSize
  };
  document.addEventListener("DOMContentLoaded", init);
})();
