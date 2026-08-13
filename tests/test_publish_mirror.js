const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const mirroredFiles = [
  'index.html',
  'css/main.css',
  'css/sidebar.css',
  'css/states.css',
  'css/tokens.css',
  'css/f2-major.css',
  'js/account.js',
  'js/app.js',
  'js/data-bridge.js',
  'js/evidence.js',
  'js/f2-major.js',
  'js/mock-data.js',
  'js/pages-api-config.js',
  'js/quick-demo.js',
  'js/radar.js',
  'js/voice.js',
  'js/job-upload.js',
  'js/resume-upload.js',
  'pages/f1-resume.html',
  'pages/f2-match.html',
  'js/kb.js',
  'js/f3-interview.js',
  'js/optimizer.js',
  'pages/kb.html',
  'js/f5-apply.js',
  'pages/f5-apply.html',
  'pages/f3-interview.html',
  'pages/f4-report.html',
  'pages/states.html'
];

test('docs and public publish trees keep the workflow assets identical', () => {
  for (const relativePath of mirroredFiles) {
    const docsFile = path.join(root, 'docs', relativePath);
    const publicFile = path.join(root, 'public', relativePath);
    assert.equal(fs.existsSync(docsFile), true, 'missing docs source: ' + relativePath);
    assert.equal(fs.existsSync(publicFile), true, 'missing public mirror: ' + relativePath);
    assert.equal(
      fs.readFileSync(publicFile, 'utf8'),
      fs.readFileSync(docsFile, 'utf8'),
      'publish mirror differs: ' + relativePath
    );
  }
});
