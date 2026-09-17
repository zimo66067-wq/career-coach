const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const PUBLIC = path.join(root, 'public');

function walk(dir, prefix, out) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix ? prefix + '/' + entry.name : entry.name;
    const absolute = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(absolute, rel, out);
    else out.push(rel);
  }
  return out;
}

const publishFiles = walk(PUBLIC, '', []);
const textFiles = publishFiles.filter((rel) => /\.(html|js|css)$/.test(rel));

function read(rel) {
  return fs.readFileSync(path.join(PUBLIC, rel), 'utf8');
}

test('no publish asset references the retired ui/ tree', () => {
  // 路径位置匹配，避免 Array.prototype 这类误命中。
  // Phase 6a 删掉了 ui/（陈旧分叉 + assets 重复副本）；它不得通过任何相对路径复活。
  const reference = /(?:src|href)\s*=\s*["'](?:\.\.?\/)*(?:ui|prototype)\//;
  const offenders = textFiles.filter((rel) => reference.test(read(rel)));
  assert.deepEqual(offenders, [], 'these publish assets still point at the retired ui/ tree');
});

test('no page loads the same stylesheet or script twice', () => {
  // Phase 6a 修掉 public/pages/action-loop.html 里重复的 sidebar.css <link>。
  const offenders = [];
  for (const rel of publishFiles.filter((name) => name.endsWith('.html'))) {
    const html = read(rel);
    for (const attribute of ['href', 'src']) {
      const pattern = new RegExp(attribute + '\\s*=\\s*["\']([^"\']+\\.(?:css|js))["\']', 'g');
      const seen = new Set();
      for (const match of html.matchAll(pattern)) {
        const target = match[1];
        if (seen.has(target)) offenders.push(rel + ' loads ' + target + ' more than once');
        seen.add(target);
      }
    }
  }
  assert.deepEqual(offenders, []);
});

test('the publish tree self-description lists every page that ships', () => {
  // README 的页面清单必须覆盖真正存在的页面，否则自述会随页面增删静默漂移。
  // 注意只断言"完整性"，不断言"不许多提"——README 里的「已下线」提示会提到已删页面。
  const readme = read('README.md');
  const pages = publishFiles
    .filter((rel) => rel === 'index.html' || /^pages\/.+\.html$/.test(rel))
    .sort();
  assert.ok(pages.length >= 5, 'expected at least 5 published pages, got ' + pages.length);
  const missing = pages.filter((rel) => !readme.includes(rel));
  assert.deepEqual(missing, [], 'public/README.md does not mention these shipped pages');
});

test('the phase 6a checks themselves can fail', () => {
  const reference = /(?:src|href)\s*=\s*["'](?:\.\.?\/)*(?:ui|prototype)\//;
  assert.ok(reference.test('<script src="../ui/prototype/js/app.js"></script>'));
  assert.ok(reference.test('<link rel="stylesheet" href="ui/prototype/css/main.css">'));
  // 干净样本与常见误命中必须不被报出来
  assert.ok(!reference.test('Array.prototype.forEach.call(items, fn)'));
  assert.ok(!reference.test('<script src="../js/app.js"></script>'));

  const scan = (html) => {
    const pattern = /(?:href|src)\s*=\s*["']([^"']+\.(?:css|js))["']/g;
    const seen = new Set();
    const duplicates = [];
    for (const match of html.matchAll(pattern)) {
      if (seen.has(match[1])) duplicates.push(match[1]);
      seen.add(match[1]);
    }
    return duplicates;
  };
  assert.deepEqual(scan('<link href="a.css"><link href="a.css">'), ['a.css']);
  assert.deepEqual(scan('<link href="a.css"><script src="a.js"></script>'), []);
});
