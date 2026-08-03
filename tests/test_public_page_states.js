/* Public-page state regression checks. Run with: node tests/test_public_page_states.js */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const appSource = fs.readFileSync(path.join(root, 'docs', 'js', 'app.js'), 'utf8');
const bridgeSource = fs.readFileSync(path.join(root, 'docs', 'js', 'data-bridge.js'), 'utf8');

function loadApp(search) {
  const context = {
    location: { search: search, pathname: '/pages/f1-resume.html', hash: '' },
    document: { addEventListener: function () {} }
  };
  context.window = context;
  vm.runInNewContext(appSource, context, { filename: 'app.js' });
  return context.APP;
}

function loadBridge(search) {
  const cache = new Map();
  const context = {
    location: { search: search },
    sessionStorage: {
      getItem: function (key) { return cache.has(key) ? cache.get(key) : null; },
      setItem: function (key, value) { cache.set(key, String(value)); },
      removeItem: function (key) { cache.delete(key); }
    },
    console: { warn: function () {} },
    fetch: function () { return Promise.reject(new Error('offline')); },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    AbortController: class { abort() {} },
    FormData: class { append() {} },
    MOCK: { resumeProfile: { score_R: 73 } }
  };
  context.window = context;
  vm.runInNewContext(bridgeSource, context, { filename: 'data-bridge.js' });
  return context.DataBridge;
}

async function run() {
  assert.strictEqual(loadApp('').getState(), 'empty', 'default product state must be empty');
  assert.strictEqual(loadApp('?state=success').getState(), 'empty', 'state alone must not enter success');
  assert.strictEqual(loadApp('?demo=1&state=success').getState(), 'success', 'explicit demo can show success');

  for (const name of ['f1-resume.html', 'f2-match.html', 'f3-interview.html', 'f4-report.html']) {
    const html = fs.readFileSync(path.join(root, 'docs', 'pages', name), 'utf8');
    assert.ok(html.includes('data-state-view="empty"'), name + ' must retain an empty state');
    assert.ok(html.includes('window.APP.isDemoMode()'), name + ' must guard synthetic success rendering');
  }

  const bridge = loadBridge('');
  const offlineResults = await Promise.all([
    bridge.uploadResume({}),
    bridge.diagnoseResume('candidate supplied text'),
    bridge.matchJD({}, {}),
    bridge.startInterview({}, {}, []),
    bridge.submitAnswer('session', 'candidate supplied answer'),
    bridge.endInterview('session'),
    bridge.getAbility('session'),
    bridge.submitConsent('candidate supplied consent')
  ]);
  offlineResults.forEach(function (result) {
    assert.strictEqual(result.error, 'service_unavailable', 'offline production flow must return an error');
  });
  assert.strictEqual(bridge.getMockData('resumeProfile'), null, 'production code must not read demo data');
  assert.strictEqual(loadBridge('?demo=1').getMockData('resumeProfile').score_R, 73, 'demo data must require explicit opt-in');

  console.log('public page state checks passed');
}

run().catch(function (error) {
  console.error(error.stack || error);
  process.exitCode = 1;
});
