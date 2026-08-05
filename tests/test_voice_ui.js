/* F3 voice UI contract checks: required DOM ids, script wiring, and mirror sync. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const REQUIRED_IDS = [
  'micBtn',
  'ttsToggle',
  'voice-state-indicator',
  'voice-fallback-area',
  'voiceTextFallback',
  'voiceTextSubmit',
  'voiceTextRetryVoice',
  'draftHint'
];

test('F3 voice UI elements and wiring exist in docs and public mirrors', () => {
  for (const dir of ['docs', 'public']) {
    const html = fs.readFileSync(path.join(root, dir, 'pages', 'f3-interview.html'), 'utf8');
    for (const id of REQUIRED_IDS) {
      assert.ok(html.includes('id="' + id + '"'), dir + '/pages/f3-interview.html missing id="' + id + '"');
    }
    assert.ok(html.includes('voice.js'), dir + ' f3 must load voice.js');
    assert.ok(html.includes('window.VoiceHandler'), dir + ' f3 must reference VoiceHandler');
    assert.ok(html.includes('submitAnswer'), dir + ' f3 must wire answer submission');
  }
});

test('voice.js exposes the ASR/TTS/fallback contract', () => {
  const voice = fs.readFileSync(path.join(root, 'public', 'js', 'voice.js'), 'utf8');
  for (const api of ['startASR', 'startTTS', 'cancel', 'fallbackToText', 'getState', 'State']) {
    assert.ok(voice.includes(api), 'voice.js missing ' + api);
  }
  assert.ok(voice.includes('FALLBACK_TIMEOUT = 10000'), 'voice.js must keep the 10s fallback');
  assert.ok(voice.includes('SpeechRecognition') || voice.includes('webkitSpeechRecognition'),
    'voice.js must detect Web Speech API');
});
