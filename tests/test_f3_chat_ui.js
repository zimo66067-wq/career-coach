/* F3 typing-chat UI contract checks: required DOM ids, no voice wiring, mirror sync. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const REQUIRED_IDS = [
  'f3StartBtn',
  'f3SendAnswer',
  'f3EndInterview',
  'f3RetryBtn',
  'f3Answer',
  'turns',
  'f3StreamingBubble',
  'f3Report'
];
const FORBIDDEN = [
  'micBtn',
  'ttsToggle',
  'voice-state-indicator',
  'voice-fallback-area',
  'voice.js',
  'VoiceHandler'
];

test('F3 is a typing chat: required elements present, no voice wiring, mirrors synced', () => {
  for (const dir of ['docs', 'public']) {
    const html = fs.readFileSync(path.join(root, dir, 'pages', 'interview-practice.html'), 'utf8');
    for (const id of REQUIRED_IDS) {
      assert.ok(html.includes('id="' + id + '"'), dir + '/pages/interview-practice.html missing id="' + id + '"');
    }
    for (const bad of FORBIDDEN) {
      assert.ok(!html.includes(bad), dir + ' f3 must not contain voice wiring: ' + bad);
    }
  }
});

test('interview-practice.js exposes the typing conversation API', () => {
  const js = fs.readFileSync(path.join(root, 'public', 'js', 'interview-practice.js'), 'utf8');
  for (const api of ['startInterview', 'submitAnswer', 'finishInterview', 'getState']) {
    assert.ok(js.includes(api), 'interview-practice.js missing ' + api);
  }
  assert.ok(js.includes('f3_session_snapshot_v1'), 'f3 must keep session snapshot');
  assert.ok(js.includes('/api/wf04/stream'), 'f3 must call the SSE stream endpoint');
  assert.ok(js.includes('X-Guest-Token'), 'f3 stream must carry stable guest ownership');
  assert.ok(js.includes('credentials: "include"'), 'f3 stream must carry the login cookie');
  assert.ok(js.includes('_cache.get("jobProfile")'), 'f3 must restore the F2 job profile');
  assert.ok(js.includes('_cache.get("resumeProfile")'), 'f3 must restore the F1 resume profile');
});

test('F5 confirmation actions are native keyboard-accessible buttons', () => {
  const html = fs.readFileSync(path.join(root, 'public', 'pages', 'job-apply.html'), 'utf8');
  assert.match(html, /<button class="btn primary" id="f5Generate" type="button">/);
  assert.match(html, /<button class="btn primary" id="f5Confirm" type="button" disabled>/);
});
