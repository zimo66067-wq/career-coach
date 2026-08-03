const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'docs', 'js', 'job-upload.js'), 'utf8');

function loadUploadModule(apiBase) {
  const context = {
    window: { DUMATE_API_BASE: apiBase || '', console },
    console,
    document: undefined
  };
  vm.createContext(context);
  vm.runInContext(source, context, { filename: 'job-upload.js' });
  return context.window.JobUpload;
}

test('F2 JD 文件只接受与 F1 相同的 PDF、DOCX、TXT 格式和 10MB 限制', () => {
  const upload = loadUploadModule('https://api.example.test');
  assert.equal(upload.validateFile({ name: 'backend.pdf', size: 1024 }).ok, true);
  assert.equal(upload.validateFile({ name: 'backend.docx', size: 1024 }).ok, true);
  assert.equal(upload.validateFile({ name: 'backend.txt', size: 1024 }).ok, true);
  assert.match(upload.validateFile({ name: 'backend.exe', size: 1024 }).message, /PDF、DOCX、TXT/);
  assert.match(upload.validateFile({ name: 'large.pdf', size: 10 * 1024 * 1024 + 1 }).message, /10MB/);
});

test('F2 JD 文本与文件都会走真实的解析和匹配接口', async () => {
  const upload = loadUploadModule('https://api.example.test');
  const calls = [];
  const bridge = {
    async uploadJD(file) {
      calls.push(['uploadJD', file.name]);
      return { jdText: '岗位职责：负责 Python API 开发\n任职要求：熟悉 Flask、SQL 与 Redis。' };
    },
    async submitJD(text) {
      calls.push(['submitJD', text]);
      return {
        jobProfile: {
          requirements: [{ id: 'req-1', type: 'hard', text: '熟悉 Flask 与 SQL' }]
        }
      };
    },
    async matchJD(resumeText, profile) {
      calls.push(['matchJD', resumeText, profile.requirements.length]);
      return {
        matchResult: {
          score_M: 86,
          subscores: {},
          requirements: [],
          gaps: [],
          match_notice: '本次使用基于简历原文的规则关键词匹配；未调用模型。'
        }
      };
    }
  };
  const flow = upload.createSubmissionFlow({
    bridge,
    getResumeText: () => '我具有 Python、Flask、SQL 和 Redis 的后端 API 开发经验。',
    isApiAvailable: () => true
  });

  const textResult = await flow.submitText('岗位职责：负责 Python API 开发\n任职要求：熟悉 Flask、SQL 与 Redis。');
  assert.equal(textResult.ok, true);
  assert.equal(textResult.matchResult.score_M, 86);

  const fileResult = await flow.submitFile({ name: 'backend.docx', size: 2048 });
  assert.equal(fileResult.ok, true);
  assert.deepEqual(calls.map((item) => item[0]), ['submitJD', 'matchJD', 'uploadJD', 'submitJD', 'matchJD']);
});

test('F2 会在 F1 未完成或服务未配置时阻止匹配并给出明确原因', async () => {
  const upload = loadUploadModule('');
  const noResume = upload.createSubmissionFlow({
    bridge: {},
    getResumeText: () => '',
    isApiAvailable: () => true
  });
  const noResumeResult = await noResume.submitText('岗位职责：负责后端开发，要求掌握 Python 与 SQL。');
  assert.equal(noResumeResult.error_code, 'f1_required');

  const noApi = upload.createSubmissionFlow({
    bridge: {},
    getResumeText: () => '我具备 Python 后端开发、接口设计和 SQL 数据库项目经验。',
    isApiAvailable: () => false
  });
  const noApiResult = await noApi.submitText('岗位职责：负责后端开发，要求掌握 Python 与 SQL。');
  assert.equal(noApiResult.error_code, 'api_not_configured');
});
