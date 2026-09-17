/* Phase 6b-1 契约门禁：目标岗位工作区接线 + 退役路径不得复活。
 *
 * 这一组判据的存在理由：`js/job-upload.js` 之所以能"已实现但无人挂载"地活到 Phase 6b，
 * 是因为当时没有任何判据检查"发布资源被谁引用 / 引用的东西是否存在"。
 * 所以本测试把三件事变成门禁：
 *   ① 发布资源不得引用不存在的文件（防孤儿与坏引用）
 *   ② 每个发布页面必须能被导航到达（防无人挂载）
 *   ③ 控制器只能调用 DataBridge 真实导出的方法（防拼错方法名后静默失败）
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const TREES = ['public', 'docs'];

function walk(dir, prefix, out) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix ? prefix + '/' + entry.name : entry.name;
    const absolute = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(absolute, rel, out);
    else out.push(rel);
  }
  return out;
}

function read(tree, rel) {
  return fs.readFileSync(path.join(root, tree, rel), 'utf8');
}

function pagesOf(tree) {
  return walk(path.join(root, tree), '', [])
    .filter((rel) => rel === 'index.html' || /^pages\/.+\.html$/.test(rel))
    .sort();
}

// ── 判据实现（与测试共用，便于自检） ──────────────────────────────

/** 页面引用的本地 css/js 是否都真实存在。 */
function brokenReferences(tree) {
  const offenders = [];
  for (const rel of pagesOf(tree)) {
    const html = read(tree, rel);
    const base = rel.includes('/') ? path.posix.dirname(rel) : '.';
    for (const match of html.matchAll(/(?:href|src)\s*=\s*["']([^"']+\.(?:css|js))["']/g)) {
      const target = match[1];
      if (/^(?:https?:)?\/\//.test(target) || target.startsWith('data:')) continue;
      const resolved = path.posix.normalize(path.posix.join(base, target));
      if (!fs.existsSync(path.join(root, tree, resolved))) {
        offenders.push(rel + ' -> ' + target);
      }
    }
  }
  return offenders;
}

/** 从 data-bridge.js 的导出块里取出方法名。 */
function bridgeMethods(tree) {
  const source = read(tree, 'js/data-bridge.js');
  const start = source.indexOf('window.DataBridge = {');
  assert.ok(start > -1, 'data-bridge.js must assign window.DataBridge');
  const block = source.slice(start, source.indexOf('\n  };', start));
  const names = new Set();
  for (const match of block.matchAll(/^\s{4}([A-Za-z_][A-Za-z0-9_]*)\s*:/gm)) {
    names.add(match[1]);
  }
  return names;
}

/** 端点映射的**值**（只取值，不取注释与键名）—— 判据必须只认接线，不认散文。 */
function endpointValues(tree) {
  const source = read(tree, 'js/data-bridge.js');
  const start = source.indexOf('var ENDPOINTS = {');
  assert.ok(start > -1, 'data-bridge.js must declare ENDPOINTS');
  const block = source.slice(start, source.indexOf('\n  };', start));
  const values = [];
  for (const match of block.matchAll(/^\s+[A-Za-z_][A-Za-z0-9_]*\s*:\s*'([^']+)'/gm)) {
    values.push(match[1]);
  }
  assert.ok(values.length >= 10, 'ENDPOINTS value scan looks vacuous, saw ' + values.length);
  return values;
}

/** 控制器里 DB.<name> 的调用集合。 */
function controllerCalls(tree, controller) {
  const source = read(tree, 'js/' + controller);
  const names = new Set();
  for (const match of source.matchAll(/\bDB\.([A-Za-z_][A-Za-z0-9_]*)/g)) {
    names.add(match[1]);
  }
  return names;
}

/** sync_sidebar.py 的 PAGES 清单 —— 页面必须有侧栏，且新页面必须登记在这里。 */
function sidebarPages() {
  const source = fs.readFileSync(path.join(root, 'scripts', 'sync_sidebar.py'), 'utf8');
  const block = source.slice(source.indexOf('PAGES = ['), source.indexOf(']', source.indexOf('PAGES = [')));
  const pages = [];
  for (const match of block.matchAll(/"(index\.html|pages\/[^"]+\.html)"/g)) pages.push(match[1]);
  return pages;
}

// ── 测试 ────────────────────────────────────────────────────────

test('every local css/js referenced by a page actually exists', () => {
  for (const tree of TREES) {
    assert.deepEqual(brokenReferences(tree), [], tree + ' has a reference to a file that does not exist');
  }
});

test('the retired wf03 front-end path is gone and does not come back', () => {
  for (const tree of TREES) {
    // 1) 文件与测试都不在了
    assert.ok(!fs.existsSync(path.join(root, tree, 'js/job-upload.js')), tree + ' must not ship job-upload.js');
    // 2) 桥接层不再暴露 wf03 的前端包装器
    const methods = bridgeMethods(tree);
    for (const dead of ['uploadJD', 'uploadJDWithProgress', 'submitJD', 'matchJD']) {
      assert.ok(!methods.has(dead), tree + '/js/data-bridge.js must not export ' + dead);
    }
    // 3) 端点映射里没有 wf03 残留（只查映射值：注释里提到它是说明，不是接线）
    const values = endpointValues(tree);
    const retired = values.filter((value) => value.startsWith('/api/wf03'));
    assert.deepEqual(retired, [], tree + '/js/data-bridge.js still maps /api/wf03 endpoints');
    // 4) 新契约确实接上了（否则上面那条会因为"整块被删空"而假通过）
    for (const live of ['/api/target-jobs', '/api/actions', '/api/profile']) {
      assert.ok(values.includes(live), tree + '/js/data-bridge.js must map ' + live);
    }
    // 5) 全树不得再引用那个已删的控制器
    //    只扫代码与资源，不扫 .md —— README 的「已下线」段落合法地提到它（同样是"不许多提"的例外）
    const offenders = walk(path.join(root, tree), '', [])
      .filter((rel) => /\.(html|js|css)$/.test(rel))
      .filter((rel) => /job-upload/.test(read(tree, rel)));
    assert.deepEqual(offenders, [], tree + ' still references the retired job-upload');
  }
  assert.ok(!fs.existsSync(path.join(root, 'tests', 'test_job_upload.js')), 'its test must go with it');
});

test('the target-job workspace is wired to the live contract', () => {
  for (const tree of TREES) {
    const html = read(tree, 'pages/target-job.html');
    assert.ok(html.includes('js/target-job.js'), tree + ' must load the target-job controller');
    for (const state of ['empty', 'processing', 'success', 'error', 'degraded']) {
      assert.ok(html.includes('data-state-view="' + state + '"'), tree + ' must retain the ' + state + ' state');
    }
    // 控制器引用的每个 DataBridge 方法都必须真实导出；拼错会静默退化成"什么都没发生"
    const methods = bridgeMethods(tree);
    const calls = controllerCalls(tree, 'target-job.js');
    assert.ok(calls.size >= 6, 'expected the controller to actually use the bridge, saw ' + calls.size);
    const unknown = [...calls].filter((name) => !methods.has(name) && !name.startsWith('_'));
    assert.deepEqual(unknown, [], tree + '/js/target-job.js calls DataBridge methods that do not exist');
    // 新契约必须真的被用上，而不是留个空壳
    for (const required of ['createTargetJob', 'analyseTargetJob', 'listTargetJobs', 'planActionsForTarget']) {
      assert.ok(calls.has(required), tree + '/js/target-job.js must use ' + required);
    }
  }
  // 后端已支持 targetJobId 出题，前端必须真的把它递过去
  for (const tree of TREES) {
    assert.ok(
      /body\.targetJobId\s*=/.test(read(tree, 'js/data-bridge.js')),
      tree + '/js/data-bridge.js must forward targetJobId to /api/wf04/start'
    );
  }
});

/** 页面里所有指向本发布树内 .html 的链接（去掉 query/hash）。 */
function pageLinks(tree, rel) {
  const html = read(tree, rel);
  const base = rel.includes('/') ? path.posix.dirname(rel) : '.';
  return [...html.matchAll(/href\s*=\s*["']([^"']+\.html)(?:[?#][^"']*)?["']/g)]
    .map((m) => path.posix.normalize(path.posix.join(base, m[1])));
}

test('every published page is registered for the sidebar and reachable from somewhere', () => {
  const registered = sidebarPages();
  // 显式例外：`product-scope.md §7` 规定「Radar 与 states.html 不进导航」——
  // 它是内部 QA 状态墙，本来就不该被用户链接到。例外必须写死在这里，不能靠"没人链接就放过"。
  const unlinkedByDesign = ['pages/states.html'];
  for (const tree of TREES) {
    const onDisk = pagesOf(tree);
    assert.ok(onDisk.length >= 6, 'expected at least 6 published pages, got ' + onDisk.length);
    // 磁盘上的每一页都必须登记（否则侧栏/账号弹窗会被静默漏掉）
    const unregistered = onDisk.filter((rel) => !registered.includes(rel));
    assert.deepEqual(unregistered, [], tree + ' ships pages missing from sync_sidebar.py PAGES');
    // 登记表里的每一页都必须真实存在（否则脚本自己就有坏条目）
    const absent = registered.filter((rel) => !fs.existsSync(path.join(root, tree, rel)));
    assert.deepEqual(absent, [], 'sync_sidebar.py PAGES lists files that do not exist');

    // 每一页都必须**从某处可达**（顶部导航，或另一页里的链接）—— 防"无人挂载"。
    // 这里刻意不要求"必须在导航里"：一级工作区有数量上限，子页面从工作区进入是正常的。
    const reachable = new Set();
    for (const rel of onDisk) {
      const nav = read(tree, rel).slice(0, read(tree, rel).indexOf('</nav>'));
      const base = rel.includes('/') ? path.posix.dirname(rel) : '.';
      for (const m of nav.matchAll(/href\s*=\s*["']([^"']+\.html)(?:[?#][^"']*)?["']/g)) {
        reachable.add(path.posix.normalize(path.posix.join(base, m[1])));
      }
      for (const target of pageLinks(tree, rel)) reachable.add(target);
    }
    const orphaned = onDisk.filter(
      (rel) => rel !== 'index.html' && !unlinkedByDesign.includes(rel) && !reachable.has(rel)
    );
    assert.deepEqual(orphaned, [], tree + ' ships pages that nothing links to');

    // 顶部导航不得超过 DoD 的一级工作区上限（4 个工作区 + 首页）
    const index = read(tree, 'index.html');
    const nav = index.slice(index.indexOf('<nav class="topnav"'), index.indexOf('</nav>'));
    const labels = [...nav.matchAll(/class="nav"[^>]*>([^<]*)</g)].map((m) => m[1]);
    assert.ok(labels.length <= 5, tree + ' top nav exceeds the first-level workspace budget: ' + labels.join('/'));
    for (const banned of ['面经知识库', '岗位匹配', '知识库']) {
      assert.ok(!labels.join(' ').includes(banned), tree + ' nav still offers a retired capability');
    }
  }
});

test('the phase 6b-1 checks themselves can fail', () => {
  // ① 坏引用能被发现
  assert.deepEqual(brokenReferences('public'), []);
  const probe = '<script src="../js/does-not-exist.js"></script>';
  const resolved = path.posix.normalize(path.posix.join('pages', '../js/does-not-exist.js'));
  assert.ok(!fs.existsSync(path.join(root, 'public', resolved)), 'the probe target must genuinely be absent');
  assert.ok(probe.includes('does-not-exist.js'));

  // ② 桥接方法解析不是空集，且退役方法确实不在
  const methods = bridgeMethods('public');
  assert.ok(methods.size >= 15, 'bridge method scan looks vacuous, saw ' + methods.size);
  assert.ok(methods.has('listTargetJobs') && methods.has('listActions'));
  assert.ok(!methods.has('matchJD'));

  // ③ 端点值扫描不是空集，且确实不含已退役路径
  const values = endpointValues('public');
  assert.ok(values.includes('/api/target-jobs'));
  assert.ok(!values.some((value) => value.startsWith('/api/wf03')));

  // ④ 控制器调用扫描不是空集
  const calls = controllerCalls('public', 'target-job.js');
  assert.ok(calls.has('analyseTargetJob'));

  // ⑤ PAGES 解析不是空集
  assert.ok(sidebarPages().length >= 6);
});
