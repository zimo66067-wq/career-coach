const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const SOURCE = path.join(root, 'public');
const MIRROR = path.join(root, 'docs');

// 规则（不硬编码清单）：public/ 与 docs/ 下的**非 .md** 文件必须集合相同、逐字节相同。
// 排除 .md 的理由：docs/ 合法地多出内部文档（phase*-report.md / product-scope.md …），
// 它们是文档树而非前端资源。详见 scripts/sync_mirror.py 与 docs/phase6a-report.md。
// 旧版本硬编码 26 项清单，漏掉了 blind-test-results/blind-test-summary.json ——
// 恰好当时两边相同，所以那处漂移永远不会被发现。规则化就是为了消灭这种覆盖洞。
const EXCLUDED_SUFFIX = '.md';

function collectAssets(dir, prefix) {
  const out = new Map();
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix ? prefix + '/' + entry.name : entry.name;
    const absolute = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      for (const [key, value] of collectAssets(absolute, rel)) out.set(key, value);
    } else if (!rel.toLowerCase().endsWith(EXCLUDED_SUFFIX)) {
      out.set(rel, fs.readFileSync(absolute));
    }
  }
  return out;
}

// 纯函数，便于用假数据自检（与 tests/test_layering.py 的判据自检同一思路）
function compareTrees(source, mirror) {
  const missing = [];
  const extra = [];
  const differing = [];
  for (const [rel, content] of source) {
    if (!mirror.has(rel)) missing.push(rel);
    else if (!mirror.get(rel).equals(content)) differing.push(rel);
  }
  for (const rel of mirror.keys()) {
    if (!source.has(rel)) extra.push(rel);
  }
  return { missing: missing.sort(), extra: extra.sort(), differing: differing.sort() };
}

test('the mirror rule is not vacuous', () => {
  const source = collectAssets(SOURCE, '');
  const mirror = collectAssets(MIRROR, '');
  // 规则若匹配不到文件，后面所有断言都会"假绿"——这正是旧清单版最危险的失效方式。
  assert.ok(source.size >= 20, 'expected public/ to expose at least 20 non-markdown assets, got ' + source.size);
  assert.ok(mirror.size >= 20, 'expected docs/ to expose at least 20 non-markdown assets, got ' + mirror.size);
});

test('docs/ is a byte-exact mirror of public/ for every non-markdown asset', () => {
  const source = collectAssets(SOURCE, '');
  const mirror = collectAssets(MIRROR, '');
  const { missing, extra, differing } = compareTrees(source, mirror);
  assert.deepEqual(missing, [], 'docs/ is missing publish assets that exist in public/');
  assert.deepEqual(extra, [], 'docs/ has publish assets that public/ does not — mirror-only orphans');
  assert.deepEqual(differing, [], 'publish mirror differs from the source tree');
});

test('the mirror check itself can fail', () => {
  const source = new Map([
    ['index.html', Buffer.from('same')],
    ['js/app.js', Buffer.from('source-version')],
    ['js/new.js', Buffer.from('only-in-source')]
  ]);
  const mirror = new Map([
    ['index.html', Buffer.from('same')],
    ['js/app.js', Buffer.from('mirror-version')],
    ['js/orphan.js', Buffer.from('only-in-mirror')]
  ]);

  const { missing, extra, differing } = compareTrees(source, mirror);
  assert.deepEqual(missing, ['js/new.js'], 'a file present only in the source tree must be reported missing');
  assert.deepEqual(extra, ['js/orphan.js'], 'a mirror-only file must be reported as an orphan');
  assert.deepEqual(differing, ['js/app.js'], 'a byte difference must be reported');

  // 干净样本必须报空，防止"永远报错"式的反向失效
  const clean = compareTrees(source, new Map(source));
  assert.deepEqual(clean, { missing: [], extra: [], differing: [] });
});
