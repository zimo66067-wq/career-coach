/* Resume upload intake checks. Run with: node tests/test_resume_upload.js */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const pageSource = fs.readFileSync(path.join(root, 'docs', 'pages', 'f1-resume.html'), 'utf8');
const cssSource = fs.readFileSync(path.join(root, 'docs', 'css', 'main.css'), 'utf8');
const uploadSource = fs.readFileSync(path.join(root, 'docs', 'js', 'resume-upload.js'), 'utf8');

const context = {
  document: { addEventListener: function () {} }
};
context.window = context;
vm.runInNewContext(uploadSource, context, { filename: 'resume-upload.js' });

assert.ok(pageSource.includes('id="resumeFileInput"'), 'F1 must expose a native file input');
assert.ok(pageSource.includes('id="resumeDropzone"'), 'F1 must expose a drop target');
assert.ok(pageSource.includes('../js/resume-upload.js'), 'F1 must load drag-and-drop behavior');
assert.ok(pageSource.includes('accept=".pdf,.docx,.txt'), 'F1 must limit picker types to supported resume files');
assert.ok(cssSource.includes('.resume-dropzone.is-dragging'), 'dragging must have visible feedback');
assert.strictEqual(context.ResumeUpload.validateFile({ name: 'resume.PDF' }).valid, true, 'PDF must be accepted case-insensitively');
assert.strictEqual(context.ResumeUpload.validateFile({ name: 'resume.docx' }).valid, true, 'DOCX must be accepted');
assert.strictEqual(context.ResumeUpload.validateFile({ name: 'resume.txt' }).valid, true, 'TXT must be accepted');
assert.strictEqual(context.ResumeUpload.validateFile({ name: 'resume.png' }).valid, false, 'unsupported files must be rejected');
assert.strictEqual(context.ResumeUpload.formatFileSize(1536), '1.5 KB', 'file size display must be human-readable');

console.log('resume upload intake checks passed');
