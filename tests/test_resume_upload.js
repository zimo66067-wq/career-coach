const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const scriptPath = 'docs/js/resume-upload.js';
const source = fs.readFileSync(scriptPath, 'utf8');
const apiConfigPath = 'docs/js/pages-api-config.js';
const apiConfigSource = fs.readFileSync(apiConfigPath, 'utf8');
const context = {
  window: {},
  document: { addEventListener() {} },
  console,
  encodeURIComponent,
  isFinite,
  Promise
};
vm.createContext(context);
vm.runInContext(source, context, { filename: scriptPath });

async function run() {
  const configuredApi = { window: {} };
  vm.createContext(configuredApi);
  vm.runInContext(apiConfigSource, configuredApi, { filename: apiConfigPath });
  assert.strictEqual(
    configuredApi.window.DUMATE_API_BASE,
    'https://career-coach-o7eu.vercel.app',
    'GitHub Pages must target the Vercel production API by default'
  );

  const overriddenApi = { window: { DUMATE_API_BASE: 'https://preview.example.test' } };
  vm.createContext(overriddenApi);
  vm.runInContext(apiConfigSource, overriddenApi, { filename: apiConfigPath });
  assert.strictEqual(
    overriddenApi.window.DUMATE_API_BASE,
    'https://preview.example.test',
    'an explicit API override must remain supported'
  );

  const upload = context.window.ResumeUpload;
  assert(upload, 'ResumeUpload should be exposed');
  assert.strictEqual(upload.validateFile({ name: 'resume.PDF', size: 1024 }).valid, true);
  assert.strictEqual(upload.validateFile({ name: 'resume.doc' }).valid, false);
  assert.strictEqual(upload.validateFile({ name: 'large.pdf', size: 11 * 1024 * 1024 }).valid, false);
  assert.strictEqual(upload.prepareResumeText('too short').valid, false);
  assert.strictEqual(upload.prepareResumeText('这是一段足够长的简历正文，用于验证直接粘贴后能够提交到诊断流程。').valid, true);

  const profile = {
    subscores: {
      structure: { score: 80 },
      clarity: { score: 70 },
      achievement_evidence: { score: 60 },
      skill_evidence: { score: 75 },
      ats_readability: { score: 85 }
    }
  };
  const calls = [];
  let processingCount = 0;
  const flow = upload.createSubmissionFlow({
    bridge: {
      async uploadResume(file) {
        calls.push(['upload', file.name]);
        return { resumeText: '张三\n三年前端开发经验，负责多个可量化交付项目。' };
      },
      async diagnoseResume(text) {
        calls.push(['diagnose', text]);
        return { resumeProfile: profile };
      }
    },
    onProcessing() { processingCount += 1; }
  });

  const fileOutcome = await flow.submitFile({ name: 'resume.pdf', size: 2048 });
  assert.strictEqual(fileOutcome.ok, true, 'valid file must complete upload then diagnosis');
  assert.deepStrictEqual(calls.map((call) => call[0]), ['upload', 'diagnose']);
  assert.strictEqual(processingCount, 1);

  calls.length = 0;
  const textOutcome = await flow.submitText('李四\n五年产品运营经验，主导增长项目并完成可衡量的用户转化提升。');
  assert.strictEqual(textOutcome.ok, true, 'pasted text must enter diagnosis directly');
  assert.deepStrictEqual(calls.map((call) => call[0]), ['diagnose']);

  const unavailableFlow = upload.createSubmissionFlow({
    bridge: {
      async uploadResume() { return { resumeText: '旧缓存内容不应被诊断。' }; },
      async diagnoseResume() { return { degraded: true, error: 'service_unavailable' }; }
    }
  });
  const unavailable = await unavailableFlow.submitText('王五\n有足够长度的简历正文，用于验证服务失败时不会显示旧缓存或演示结果。');
  assert.strictEqual(unavailable.ok, false);
  assert.strictEqual(unavailable.error, 'service_unavailable');

  context.window.location = { hostname: 'zimo66067-wq.github.io' };
  const staticFlow = upload.createSubmissionFlow({
    bridge: {
      async diagnoseResume() { throw new Error('static page must not silently continue'); }
    }
  });
  const staticResult = await staticFlow.submitText('赵六\n有足够长度的简历正文，用于验证未配置服务的公开页面会给出明确错误。');
  assert.strictEqual(staticResult.ok, false);
  assert.strictEqual(staticResult.error, 'api_not_configured');
  delete context.window.location;

  const page = fs.readFileSync('docs/pages/f1-resume.html', 'utf8');
  assert(page.includes('id="openResumeText"'), 'paste control must be actionable');
  assert(page.includes('id="startResumeDiagnosis"'), 'selected files must expose a next-step button');
  assert(page.includes('id="resumeTextEntry"'), 'paste form must be present');
  assert(page.includes('id="retryResumeDiagnosis"'), 'error retry must be actionable');
  assert(source.includes('bridge.uploadResume'), 'file flow must call the upload API');
  assert(source.includes('bridge.diagnoseResume'), 'all flows must call the diagnosis API');
  assert(source.includes('is-dragging'), 'dragging must apply the page visual state');
  assert(source.includes('setProperty("--pct"'), 'diagnosis score must update the existing score ring variable');
  assert(source.includes('function selectFile(file)'), 'file selection must be separated from diagnosis submission');
  console.log('resume upload flow tests passed');
}

run().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});
