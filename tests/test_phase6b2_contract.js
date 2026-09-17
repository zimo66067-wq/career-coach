/* Phase 6b-2 契约门禁：行动闭环 / 求职信接地 / 出题计划三处接线。
 *
 * 这一组判据的存在理由：§7 的四个一级工作区里，Action Loop 在 6b 之前是**零前端消费**
 * （`/api/actions` 8 条路由没有任何页面调用）；F5 的 `targetJobId` 在 DoD #10 里标着
 * "前端尚未传"；F3 的 `questionPlan` 后端算了却没人显示。三者都是"后端已就绪、
 * 界面上看不见"的同一类缺陷 —— 所以判据不能只看"函数存在"，必须看**接线存在**。
 *
 * 四类判据：
 *   ① 面板存在（页面有宿主元素，控制器被真的加载）
 *   ② 调用真实（控制器只调用 DataBridge 真实导出的方法，且不得用演示数据兜底）
 *   ③ 口径一致（前端显示状态/题型时，取值集合必须与后端域层一致）
 *   ④ 诚实性（"完成 ≠ 缺口解决""没有证据就不引用"这些限定必须在界面上出现，不能被删掉）
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

function pageFiles(tree) {
  return walk(path.join(root, tree), '', [])
    .filter((rel) => rel === 'index.html' || /^pages\/.+\.html$/.test(rel))
    .sort();
}

/** 页面里"用户真正看得见"的文字：去掉脚本、样式、注释与全部标签（属性值随之消失）。 */
function visibleText(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/g, ' ')
    .replace(/<style[\s\S]*?<\/style>/g, ' ')
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/<[^>]+>/g, ' ');
}

/** 顶部导航的标签序列。 */
function navLabels(tree, rel) {
  const html = read(tree, rel);
  const start = html.indexOf('<nav class="topnav"');
  assert.ok(start > -1, rel + ' must declare the top nav');
  const nav = html.slice(start, html.indexOf('</nav>', start));
  return [...nav.matchAll(/class="nav"[^>]*>([^<]*)</g)].map((m) => m[1]);
}

/** 页面内联脚本 getElementById 到的、但页面上不存在的 id。 */
function danglingIds(tree, rel) {
  const html = read(tree, rel);
  const declared = new Set([...html.matchAll(/id="([^"]+)"/g)].map((m) => m[1]));
  const inline = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)]
    .map((m) => m[1]).join('\n');
  const used = [...inline.matchAll(/getElementById\(\s*['"]([^'"]+)['"]/g)].map((m) => m[1]);
  return [...new Set(used)].filter((id) => !declared.has(id)).sort();
}


function read(tree, rel) {
  return fs.readFileSync(path.join(root, tree, rel), 'utf8');
}

function source(rel) {
  return fs.readFileSync(path.join(root, rel), 'utf8');
}

/** 从 data-bridge.js 的导出块里取出方法名。 */
function bridgeMethods(tree) {
  const text = read(tree, 'js/data-bridge.js');
  const start = text.indexOf('window.DataBridge = {');
  assert.ok(start > -1, 'data-bridge.js must assign window.DataBridge');
  const block = text.slice(start, text.indexOf('\n  };', start));
  const names = new Set();
  for (const match of block.matchAll(/^\s{4}([A-Za-z_][A-Za-z0-9_]*)\s*:/gm)) names.add(match[1]);
  return names;
}

/** 控制器里 DB.<name> 的调用集合。 */
function controllerCalls(tree, controller) {
  const text = read(tree, 'js/' + controller);
  const names = new Set();
  for (const match of text.matchAll(/\bDB\.([A-Za-z_][A-Za-z0-9_]*)/g)) names.add(match[1]);
  return names;
}

/** 某个元素 id 是否出现在页面里。 */
function hasId(tree, rel, id) {
  return read(tree, rel).includes('id="' + id + '"');
}

/** domain/interview.py 里的题型枚举 —— 前端的题型标签必须覆盖它。 */
function questionKindsFromDomain() {
  const text = source(path.join('domain', 'interview.py'));
  const start = text.indexOf('QUESTION_PRIORITY = (');
  assert.ok(start > -1, 'domain/interview.py must declare QUESTION_PRIORITY');
  const block = text.slice(start, text.indexOf(')', start));
  const kinds = [...block.matchAll(/"([a-z0-9_]+)"/g)].map((m) => m[1]);
  assert.ok(kinds.length >= 5, 'QUESTION_PRIORITY scan looks vacuous, saw ' + kinds.length);
  return kinds;
}

/** 域层的行动状态枚举 —— 前端显示行动状态时的取值集合。 */
function actionStatusesFromDomain() {
  const text = source(path.join('domain', 'action.py'));
  const start = text.indexOf('class ActionStatus');
  assert.ok(start > -1, 'domain/action.py must declare ActionStatus');
  const block = text.slice(start, start + 600);
  const values = [...block.matchAll(/=\s*"([a-z]+)"/g)].map((m) => m[1]);
  assert.ok(values.length >= 4, 'ActionStatus scan looks vacuous, saw ' + values.length);
  return values;
}

// ── ① 行动闭环面板存在且接线 ─────────────────────────────────────

test('the action loop panel exists on the report page and loads its controller', () => {
  for (const tree of TREES) {
    const html = read(tree, 'pages/action-loop.html');
    assert.ok(html.includes('js/action-loop.js'), tree + ' must load the action-loop controller');
    for (const id of ['actionLoopCard', 'alTargetLine', 'alPlanBtn', 'alRefreshBtn', 'alMsg', 'alSummary', 'alList']) {
      assert.ok(hasId(tree, 'pages/action-loop.html', id), tree + ' is missing #' + id);
    }
    // 面板必须在所有 state view 之外（否则 empty/error 态下行动清单会消失）
    const panelIndex = html.indexOf('id="actionLoopCard"');
    assert.ok(panelIndex > -1);
    assert.ok(!/data-state-view/.test(html.slice(panelIndex, panelIndex + 400)),
      'the action loop panel must not be nested inside a data-state-view block');
  }
});

test('the action loop controller only calls bridge methods that exist', () => {
  for (const tree of TREES) {
    const methods = bridgeMethods(tree);
    const calls = controllerCalls(tree, 'action-loop.js');
    assert.ok(calls.size >= 6, 'expected the action loop to actually use the bridge, saw ' + calls.size);
    const unknown = [...calls].filter((name) => !methods.has(name) && !name.startsWith('_'));
    assert.deepEqual(unknown, [], tree + '/js/action-loop.js calls DataBridge methods that do not exist');
    // 8 条路由必须真的用上：清单 / 按岗位铺开 / 四种状态流转 / 删除
    for (const required of [
      'listActions', 'planActionsForTarget', 'startAction', 'completeAction',
      'recordActionOutcome', 'dropAction', 'deleteAction'
    ]) {
      assert.ok(calls.has(required), tree + '/js/action-loop.js must use ' + required);
    }
    // 生产路径不得用演示数据兜底
    const text = read(tree, 'js/action-loop.js');
    assert.ok(!/window\.MOCK|demoData\s*\(/.test(text),
      tree + '/js/action-loop.js must not fall back to demo data');
  }
});

test('the action status vocabulary matches the domain enum', () => {
  const statuses = actionStatusesFromDomain();
  for (const tree of TREES) {
    const text = read(tree, 'js/action-loop.js');
    const block = text.slice(text.indexOf('STATUS_LABEL = {'), text.indexOf('}', text.indexOf('STATUS_LABEL = {')));
    for (const status of statuses) {
      assert.ok(block.includes(status + ':'), tree + '/js/action-loop.js must label the status ' + status);
    }
  }
});

// ── ② 求职信接地（DoD #10） ──────────────────────────────────────

test('the cover letter request carries targetJobId and shows its grounding', () => {
  for (const tree of TREES) {
    const bridge = read(tree, 'js/data-bridge.js');
    const block = bridge.slice(
      bridge.indexOf('function generateCoverLetter'),
      bridge.indexOf('function saveApplication')
    );
    assert.ok(block.includes('function generateCoverLetter(sessionId, company, position, targetJobId)'),
      tree + '/js/data-bridge.js must accept targetJobId');
    assert.ok(/body\.targetJobId\s*=/.test(block),
      tree + '/js/data-bridge.js must forward targetJobId to /api/wf07/cover-letter');

    const page = read(tree, 'pages/job-apply.html');
    for (const id of ['f5TargetLine', 'f5Grounding', 'f5BasisBadge', 'f5EvidenceList', 'f5Notice']) {
      assert.ok(hasId(tree, 'pages/job-apply.html', id), tree + ' is missing #' + id);
    }
    assert.ok(page.includes('js/job-apply.js'));

    const controller = read(tree, 'js/job-apply.js');
    // 依据来自响应，不得在前端自造经历
    assert.ok(/res\.evidence/.test(controller), tree + '/js/job-apply.js must render the server-provided evidence list');
    assert.ok(/res\.requirements/.test(controller) && /res\.gaps/.test(controller),
      tree + '/js/job-apply.js must show the requirement base and the uncovered gaps');
    assert.ok(/getCurrentTargetJob/.test(controller),
      tree + '/js/job-apply.js must read the current target job');
    // 没有证据时必须明说"没有引用任何个人经历"，不能留白
    assert.ok(/没有引用任何个人经历/.test(controller),
      tree + '/js/job-apply.js must state the zero-evidence case explicitly');
  }
});

// ── ③ 出题计划（DoD #11） ────────────────────────────────────────

test('the interview page renders questionPlan and its labels cover the domain kinds', () => {
  const kinds = questionKindsFromDomain();
  for (const tree of TREES) {
    assert.ok(hasId(tree, 'pages/interview-practice.html', 'f3QuestionPlan'),
      tree + '/pages/interview-practice.html is missing the question-plan panel');
    const controller = read(tree, 'js/interview-practice.js');
    assert.ok(/res\.questionPlan/.test(controller), tree + '/js/interview-practice.js must read questionPlan');
    const block = controller.slice(
      controller.indexOf('QUESTION_KIND_LABEL = {'),
      controller.indexOf('}', controller.indexOf('QUESTION_KIND_LABEL = {'))
    );
    assert.ok(block.length > 50, 'QUESTION_KIND_LABEL scan looks vacuous');
    for (const kind of kinds) {
      assert.ok(block.includes(kind + ':'), tree + '/js/interview-practice.js must label the kind ' + kind);
    }
    // 出题口径必须来自目标岗位，所以岗位 id 要真的递过去
    assert.ok(/DB\.startInterview\([^)]*targetId\s*\)/.test(controller),
      tree + '/js/interview-practice.js must pass the current target job to startInterview');
  }
});

// ── ④ 诚实性：限定语不得被删 ─────────────────────────────────────

test('the honesty caveats stay on the page', () => {
  for (const tree of TREES) {
    const report = read(tree, 'pages/action-loop.html');
    // "行动完成不等于缺口解决"必须写在界面上
    assert.ok(/行动「已完成」不等于缺口「已解决」/.test(report),
      tree + '/pages/action-loop.html must keep the "done ≠ resolved" caveat');
    assert.ok(/没有可验证成果物的缺口不会开单/.test(report),
      tree + '/pages/action-loop.html must keep the "no artifact, no action" caveat');
    // 缺口不写进求职信正文，也不得被声称具备
    const apply = read(tree, 'js/job-apply.js');
    assert.ok(/缺口不写进正文/.test(apply),
      tree + '/js/job-apply.js must state that gaps stay out of the letter body');
  }
});

// ── ⑤ 判据自检：这些检查必须能失败 ───────────────────────────────

test('the phase 6b-2 checks themselves can fail', () => {
  // ① 桥接方法扫描不是空集
  const methods = bridgeMethods('public');
  assert.ok(methods.size >= 15, 'bridge method scan looks vacuous, saw ' + methods.size);
  assert.ok(methods.has('listActions') && methods.has('planActionsForTarget'));

  // ② 控制器调用扫描确实能看到方法名（不是空集，也不含不存在的名字）
  const calls = controllerCalls('public', 'action-loop.js');
  assert.ok(calls.has('planActionsForTarget'));
  assert.ok(!calls.has('thisMethodDoesNotExist'));

  // ③ 域层枚举解析不是空集，且确实来自源码而不是硬编码
  const kinds = questionKindsFromDomain();
  assert.ok(kinds.includes('p0_gap') && kinds.includes('generic_bank'), kinds.join('/'));
  const statuses = actionStatusesFromDomain();
  assert.ok(statuses.includes('todo') && statuses.includes('dropped'), statuses.join('/'));

  // ④ 探测一个真实不存在的 id：判据必须能区分
  assert.ok(!hasId('public', 'pages/action-loop.html', 'definitelyNotAnId'));
  assert.ok(hasId('public', 'pages/action-loop.html', 'alList'));
});

// ── ⑥ IA 收敛：导航恰好 4 个一级工作区、去 F 代号、页面路径无代号 ──

test('一级导航恰好是 4 个一级工作区，首页由品牌区进入', () => {
  const expected = ['简历证据', '目标岗位', '模拟面试', '行动闭环'];
  for (const tree of TREES) {
    for (const rel of pageFiles(tree)) {
      assert.deepEqual(navLabels(tree, rel), expected,
        tree + '/' + rel + ' 的导航不是 4 个一级工作区');
      assert.match(read(tree, rel), /<a class="brand" href="[^"]*index\.html">职跃AI<\/a>/,
        tree + '/' + rel + ' 的品牌区必须能回首页');
    }
  }
});

test('no user-visible F codename survives in the publish trees', () => {
  for (const tree of TREES) {
    for (const rel of pageFiles(tree)) {
      const text = visibleText(read(tree, rel));
      const hit = text.match(/\bF[1-5]\b/);
      // 提示必须能定位到上下文，但只在真的命中时才构造（否则 hit 为 null 会先炸）
      const where = hit ? text.slice(Math.max(0, hit.index - 30), hit.index + 30) : '';
      assert.ok(!hit, tree + '/' + rel + ' 的可见文本仍有 F 代号：' + where);
    }
  }
  // URL 也是用户可见面：发布路径不得带 F 代号（.md 是历史记录，不在范围内）
  for (const tree of TREES) {
    const offenders = walk(path.join(root, tree), '', [])
      .filter((rel) => !rel.endsWith('.md') && /f[1-5][-._]/i.test(rel));
    assert.deepEqual(offenders, [], tree + ' 仍有带 F 代号的发布路径');
  }
});

test('inline page scripts never address DOM ids the page does not declare', () => {
  // f4-report.html 原来带一个进度追踪器，引用 6 个早已不存在的 id —— 每次加载抛
  // TypeError，而且它自己也携带 F 代号。这条判据把"内联脚本引用的 id 必须存在"锁住。
  for (const tree of TREES) {
    for (const rel of pageFiles(tree)) {
      assert.deepEqual(danglingIds(tree, rel), [],
        tree + '/' + rel + ' 的内联脚本引用了不存在的 id');
    }
  }
});

test('the phase 6b-2b checks themselves can fail', () => {
  // ① 可见文本探测器：能发现文案里的代号，且不会把属性值当文案
  assert.ok(/\bF[1-5]\b/.test(visibleText('<div class="fno">F1 · 简历诊断</div>')),
    'the visible-text scan must catch a codename in page copy');
  assert.ok(!/\bF[1-5]\b/.test(visibleText('<button id="quickDemoF1" type="button"></button>')),
    'the visible-text scan must ignore attribute values');
  // ② 导航解析不是空集
  assert.deepEqual(navLabels('public', 'index.html'), ['简历证据', '目标岗位', '模拟面试', '行动闭环']);
  assert.deepEqual(navLabels('public', 'pages/resume-evidence.html'),
    ['简历证据', '目标岗位', '模拟面试', '行动闭环']);
  // ③ 悬挂 id 探测器：注入一个不存在的 id 必须被抓到
  const probe = '<script>document.getElementById("definitelyNotAnId");</script>';
  const declared = new Set([...'<div id="real"></div>'.matchAll(/id="([^"]+)"/g)].map((m) => m[1]));
  const used = [...probe.matchAll(/getElementById\(\s*['"]([^'"]+)['"]/g)].map((m) => m[1]);
  assert.deepEqual(used.filter((id) => !declared.has(id)), ['definitelyNotAnId']);
  // ④ 路径扫描的判据本身有效：旧名确实匹配
  assert.ok(/f[1-5][-._]/i.test('pages/f4-report.html'));
  assert.ok(!/f[1-5][-._]/i.test('pages/action-loop.html'));
});
