(function () {
  'use strict';

  var MAX_FILE_SIZE = 10 * 1024 * 1024;
  var MIN_TEXT_LENGTH = 20;
  var MAX_TEXT_LENGTH = 200000;
  var ALLOWED_EXTENSIONS = { pdf: true, docx: true, txt: true };
  var SUBSCORE_ORDER = ['hard', 'responsibility', 'preferred', 'terminology'];
  var SUBSCORE_META = {
    hard: { label: '硬性要求', weight: '50%' },
    responsibility: { label: '岗位职责', weight: '25%' },
    preferred: { label: '加分项', weight: '15%' },
    terminology: { label: '术语与工具', weight: '10%' }
  };

  function extensionOf(name) {
    var parts = String(name || '').toLowerCase().split('.');
    return parts.length > 1 ? parts.pop() : '';
  }

  function validateFile(file) {
    if (!file || !file.name) {
      return { ok: false, message: '请选择一个 JD 文件。' };
    }
    if (!ALLOWED_EXTENSIONS[extensionOf(file.name)]) {
      return { ok: false, message: '仅支持 PDF、DOCX、TXT 格式的 JD 文件。' };
    }
    if (typeof file.size === 'number' && file.size > MAX_FILE_SIZE) {
      return { ok: false, message: '单个 JD 文件不能超过 10MB。' };
    }
    return { ok: true };
  }

  function prepareJobText(value) {
    var text = String(value || '').replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n').trim();
    if (text.length < MIN_TEXT_LENGTH) {
      return { ok: false, message: '请提供至少 20 个字符的职位描述或招聘要求。' };
    }
    if (text.length > MAX_TEXT_LENGTH) {
      return { ok: false, message: '职位描述过长，请控制在 20 万字符以内。' };
    }
    return { ok: true, text: text };
  }

  function messageFrom(result, fallback) {
    if (result && result.message) return result.message;
    if (result && result.error && result.error.message) return result.error.message;
    return fallback;
  }

  function usableResult(result) {
    return !!(result && !result.error && !result.degraded && !result.demo_data);
  }

  function createSubmissionFlow(options) {
    options = options || {};
    var bridge = options.bridge;
    var getResumeText = options.getResumeText || function () { return ''; };
    var onProcessing = options.onProcessing || function () {};
    var isApiAvailable = options.isApiAvailable || function () {
      return typeof window !== 'undefined' && !!window.DUMATE_API_BASE;
    };

    function prerequisite() {
      var resumeText = String(getResumeText() || '').trim();
      if (resumeText.length < MIN_TEXT_LENGTH) {
        return {
          ok: false,
          error_code: 'f1_required',
          message: '请先完成 F1 简历诊断，再进行岗位匹配。'
        };
      }
      if (!bridge || !isApiAvailable()) {
        return {
          ok: false,
          error_code: 'api_not_configured',
          message: '岗位匹配服务尚未配置或暂不可用，请稍后重试。'
        };
      }
      return { ok: true, resumeText: resumeText };
    }

    async function parseAndMatch(jobText, resumeText) {
      var profileResponse = await bridge.submitJD(jobText);
      var jobProfile = profileResponse && profileResponse.jobProfile;
      if (!usableResult(profileResponse) || !jobProfile || !Array.isArray(jobProfile.requirements)) {
        return {
          ok: false,
          error_code: (profileResponse && profileResponse.error_code) || 'job_parse_failed',
          message: messageFrom(profileResponse, '未能解析职位描述，请检查 JD 内容后重试。')
        };
      }

      var matchResponse = await bridge.matchJD(resumeText, jobProfile);
      var matchResult = matchResponse && (matchResponse.matchResult || matchResponse);
      if (!usableResult(matchResponse) || !matchResult || typeof matchResult.score_M !== 'number') {
        return {
          ok: false,
          error_code: (matchResponse && matchResponse.error_code) || 'match_failed',
          message: messageFrom(matchResponse, '岗位匹配暂未完成，请稍后重试。')
        };
      }

      return { ok: true, jobText: jobText, jobProfile: jobProfile, matchResult: matchResult };
    }

    async function submitText(value) {
      var prepared = prepareJobText(value);
      if (!prepared.ok) return prepared;
      var ready = prerequisite();
      if (!ready.ok) return ready;
      onProcessing();
      return parseAndMatch(prepared.text, ready.resumeText);
    }

    async function submitFile(file) {
      var fileCheck = validateFile(file);
      if (!fileCheck.ok) return fileCheck;
      var ready = prerequisite();
      if (!ready.ok) return ready;
      onProcessing();
      var uploadResponse = await bridge.uploadJD(file);
      var prepared = prepareJobText(uploadResponse && uploadResponse.jdText);
      if (!usableResult(uploadResponse) || !prepared.ok) {
        return {
          ok: false,
          error_code: (uploadResponse && uploadResponse.error_code) || 'job_upload_failed',
          message: usableResult(uploadResponse) ? prepared.message : messageFrom(uploadResponse, 'JD 文件解析失败，请确认文件内容后重试。')
        };
      }
      return parseAndMatch(prepared.text, ready.resumeText);
    }

    return { submitText: submitText, submitFile: submitFile, prerequisite: prerequisite };
  }

  function makeElement(tag, className, content) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined && content !== null) node.textContent = content;
    return node;
  }

  function statusLabel(status) {
    return ({ covered: '已覆盖', weak: '部分匹配', missing: '待补足', unknown: '待核验' })[status] || '待核验';
  }

  function renderMatchResult(result) {
    if (!result || typeof document === 'undefined') return;
    var score = Math.max(0, Math.min(100, Number(result.score_M) || 0));
    var scoreRing = document.getElementById('matchScoreRing');
    var scoreNode = document.getElementById('matchScore');
    var subbars = document.getElementById('matchSubbars');
    var notice = document.getElementById('matchNotice');
    var coverTrack = document.getElementById('coverTrack');
    var reqList = document.getElementById('reqList');
    var gapList = document.getElementById('gapList');
    var requirements = Array.isArray(result.requirements) ? result.requirements : [];
    var subscores = result.subscores || {};
    var statusCounts = { covered: 0, weak: 0, missing: 0, unknown: 0 };

    if (scoreRing) {
      scoreRing.style.setProperty('--pct', score + '%');
      scoreRing.setAttribute('aria-label', '岗位匹配分 ' + score);
    }
    if (scoreNode) scoreNode.textContent = String(Math.round(score));

    if (subbars) {
      subbars.replaceChildren();
      SUBSCORE_ORDER.forEach(function (type) {
        var meta = SUBSCORE_META[type];
        var value = Math.max(0, Math.min(100, Number(subscores[type] && subscores[type].score) || 0));
        var row = makeElement('div', 'subbar-row');
        var label = makeElement('div', 'subbar-label');
        label.append(makeElement('span', '', meta.label + '（权重 ' + meta.weight + '）'));
        label.append(makeElement('strong', '', String(Math.round(value))));
        var track = makeElement('div', 'bar-track');
        var fill = makeElement('div', 'bar-fill');
        fill.style.width = value + '%';
        track.append(fill);
        row.append(label, track);
        subbars.append(row);
      });
    }

    if (notice) {
      var noticeText = String(result.match_notice || '').trim();
      notice.hidden = !noticeText;
      var noticeBody = notice.querySelector ? notice.querySelector('p') : null;
      if (noticeBody) noticeBody.textContent = noticeText;
      else notice.textContent = noticeText;
    }

    requirements.forEach(function (item) {
      var status = item && item.status;
      if (Object.prototype.hasOwnProperty.call(statusCounts, status)) statusCounts[status] += 1;
      else statusCounts.unknown += 1;
    });

    if (coverTrack) {
      coverTrack.replaceChildren();
      var total = requirements.length || 1;
      ['covered', 'weak', 'missing', 'unknown'].forEach(function (status) {
        var count = statusCounts[status];
        if (!count) return;
        var segment = makeElement('div', 'cover-seg ' + status);
        segment.style.width = (count / total * 100) + '%';
        segment.title = statusLabel(status) + '：' + count + ' 项';
        coverTrack.append(segment);
      });
    }

    if (reqList) {
      reqList.replaceChildren();
      if (!requirements.length) {
        reqList.append(makeElement('p', 'empty-result', '未识别到可匹配的岗位要求。'));
      } else {
        requirements.forEach(function (item) {
          var row = makeElement('article', 'req-item');
          var title = makeElement('div', 'req-title');
          title.append(makeElement('span', 'badge ' + (item.status || 'unknown'), statusLabel(item.status)));
          title.append(makeElement('span', 'req-type', item.typeLabel || (SUBSCORE_META[item.type] && SUBSCORE_META[item.type].label) || '岗位要求'));
          title.append(makeElement('span', '', item.text || '未命名要求'));
          row.append(title);
          row.append(makeElement('p', 'evidence', item.evidence ? '简历证据：' + item.evidence : '简历证据：未找到直接证据'));
          reqList.append(row);
        });
      }
    }

    if (gapList) {
      gapList.replaceChildren();
      var gaps = Array.isArray(result.gaps) ? result.gaps : [];
      if (!gaps.length) {
        gapList.append(makeElement('p', 'empty-result', '当前未识别到需要优先补足的要求。'));
      } else {
        gaps.forEach(function (gap) {
          var item = makeElement('article', 'gap-item');
          item.append(makeElement('span', 'badge ' + String(gap.level || 'P2').toLowerCase(), gap.level || 'P2'));
          item.append(makeElement('p', '', gap.text || '待补足项'));
          if (gap.action) item.append(makeElement('p', 'gap-action', '建议：' + gap.action));
          gapList.append(item);
        });
      }
    }
  }

  function mount() {
    var fileInput = document.getElementById('jobFileInput');
    var dropzone = document.getElementById('jobDropzone');
    var chooseButton = document.getElementById('chooseJobFile');
    var startButton = document.getElementById('startJobMatch');
    var fileStatus = document.getElementById('jobFileStatus');
    var uploadCard = document.getElementById('jobUploadCard');
    var openTextButton = document.getElementById('openJobText');
    var textEntry = document.getElementById('jobTextEntry');
    var textInput = document.getElementById('jobTextInput');
    var cancelTextButton = document.getElementById('cancelJobText');
    var retryButton = document.getElementById('retryJobMatch');
    var returnButton = document.getElementById('returnToJobUpload');
    var errorMessage = document.getElementById('matchErrorMessage');
    var selectedFile = null;
    var lastAttempt = null;
    var busy = false;
    var bridge = window.DataBridge;

    if (!fileInput || !dropzone || !bridge) return;

    function setState(name) {
      if (window.APP && typeof window.APP.setState === 'function') window.APP.setState(name);
      else document.body.setAttribute('data-state', name);
    }

    function getResumeText() {
      return bridge._cache && typeof bridge._cache.get === 'function' ? bridge._cache.get('resumeText') : '';
    }

    var flow = createSubmissionFlow({
      bridge: bridge,
      getResumeText: getResumeText,
      onProcessing: function () { setState('processing'); }
    });

    function showFileStatus(message, kind) {
      fileStatus.textContent = message;
      fileStatus.classList.toggle('is-selected', kind === 'selected');
      fileStatus.classList.toggle('is-error', kind === 'error');
    }

    function setSelectedFile(file) {
      var check = validateFile(file);
      if (!check.ok) {
        selectedFile = null;
        uploadCard.classList.remove('has-file');
        startButton.hidden = true;
        startButton.disabled = true;
        showFileStatus(check.message, 'error');
        return;
      }
      selectedFile = file;
      uploadCard.classList.add('has-file');
      startButton.hidden = false;
      startButton.disabled = false;
      showFileStatus('已选择：' + file.name + '（' + Math.max(1, Math.round(file.size / 1024)) + ' KB）', 'selected');
    }

    function fail(result) {
      busy = false;
      errorMessage.textContent = messageFrom(result, '岗位匹配未完成，请稍后重试。');
      setState('error');
    }

    function succeed(result) {
      busy = false;
      if (bridge._cache && typeof bridge._cache.set === 'function') bridge._cache.set('jobText', result.jobText);
      renderMatchResult(result.matchResult);
      setState('success');
    }

    async function submitFile() {
      if (busy || !selectedFile) return;
      busy = true;
      lastAttempt = { type: 'file', file: selectedFile };
      var result = await flow.submitFile(selectedFile);
      if (result.ok) succeed(result); else fail(result);
    }

    async function submitText() {
      if (busy) return;
      busy = true;
      var value = textInput.value;
      lastAttempt = { type: 'text', value: value };
      var result = await flow.submitText(value);
      if (result.ok) succeed(result); else fail(result);
    }

    chooseButton.addEventListener('click', function () { fileInput.click(); });
    dropzone.addEventListener('click', function () { fileInput.click(); });
    dropzone.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        fileInput.click();
      }
    });
    fileInput.addEventListener('change', function () { setSelectedFile(fileInput.files && fileInput.files[0]); });

    ['dragenter', 'dragover'].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropzone.classList.add('is-dragging');
      });
    });
    ['dragleave', 'drop'].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropzone.classList.remove('is-dragging');
      });
    });
    dropzone.addEventListener('drop', function (event) {
      var files = event.dataTransfer && event.dataTransfer.files;
      setSelectedFile(files && files[0]);
    });

    startButton.addEventListener('click', submitFile);
    openTextButton.addEventListener('click', function () {
      textEntry.hidden = false;
      textInput.focus();
    });
    cancelTextButton.addEventListener('click', function () {
      textEntry.hidden = true;
      textInput.value = '';
    });
    textEntry.addEventListener('submit', function (event) {
      event.preventDefault();
      submitText();
    });
    retryButton.addEventListener('click', function () {
      if (!lastAttempt || busy) {
        setState('empty');
        return;
      }
      if (lastAttempt.type === 'file') {
        selectedFile = lastAttempt.file;
        submitFile();
      } else {
        textInput.value = lastAttempt.value;
        submitText();
      }
    });
    returnButton.addEventListener('click', function () {
      busy = false;
      setState('empty');
      dropzone.focus();
    });
  }

  window.JobUpload = {
    validateFile: validateFile,
    prepareJobText: prepareJobText,
    createSubmissionFlow: createSubmissionFlow,
    renderMatchResult: renderMatchResult
  };

  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('DOMContentLoaded', mount);
  }
}());
