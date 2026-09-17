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
    const html = read(tree, 'pages/f4-report.html');
    assert.ok(html.includes('js/action-loop.js'), tree + ' must load the action-loop controller');
    for (const id of ['actionLoopCard', 'alTargetLine', 'alPlanBtn', 'alRefreshBtn', 'alMsg', 'alSummary', 'alList']) {
      assert.ok(hasId(tree, 'pages/f4-report.html', id), tree + ' is missing #' + id);
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

    const page = read(tree, 'pages/f5-apply.html');
    for (const id of ['f5TargetLine', 'f5Grounding', 'f5BasisBadge', 'f5EvidenceList', 'f5Notice']) {
      assert.ok(hasId(tree, 'pages/f5-apply.html', id), tree + ' is missing #' + id);
    }
    assert.ok(page.includes('js/f5-apply.js'));

    const controller = read(tree, 'js/f5-apply.js');
    // 依据来自响应，不得在前端自造经历
    assert.ok(/res\.evidence/.test(controller), tree + '/js/f5-apply.js must render the server-provided evidence list');
    assert.ok(/res\.requirements/.test(controller) && /res\.gaps/.test(controller),
      tree + '/js/f5-apply.js must show the requirement base and the uncovered gaps');
    assert.ok(/getCurrentTargetJob/.test(controller),
      tree + '/js/f5-apply.js must read the current target job');
    // 没有证据时必须明说"没有引用任何个人经历"，不能留白
    assert.ok(/没有引用任何个人经历/.test(controller),
      tree + '/js/f5-apply.js must state the zero-evidence case explicitly');
  }
});

// ── ③ 出题计划（DoD #11） ────────────────────────────────────────

test('the interview page renders questionPlan and its labels cover the domain kinds', () => {
  const kinds = questionKindsFromDomain();
  for (const tree of TREES) {
    assert.ok(hasId(tree, 'pages/f3-interview.html', 'f3QuestionPlan'),
      tree + '/pages/f3-interview.html is missing the question-plan panel');
    const controller = read(tree, 'js/f3-interview.js');
    assert.ok(/res\.questionPlan/.test(controller), tree + '/js/f3-interview.js must read questionPlan');
    const block = controller.slice(
      controller.indexOf('QUESTION_KIND_LABEL = {'),
      controller.indexOf('}', controller.indexOf('QUESTION_KIND_LABEL = {'))
    );
    assert.ok(block.length > 50, 'QUESTION_KIND_LABEL scan looks vacuous');
    for (const kind of kinds) {
      assert.ok(block.includes(kind + ':'), tree + '/js/f3-interview.js must label the kind ' + kind);
    }
    // 出题口径必须来自目标岗位，所以岗位 id 要真的递过去
    assert.ok(/DB\.startInterview\([^)]*targetId\s*\)/.test(controller),
      tree + '/js/f3-interview.js must pass the current target job to startInterview');
  }
});

// ── ④ 诚实性：限定语不得被删 ─────────────────────────────────────

test('the honesty caveats stay on the page', () => {
  for (const tree of TREES) {
    const report = read(tree, 'pages/f4-report.html');
    // "行动完成不等于缺口解决"必须写在界面上
    assert.ok(/行动「已完成」不等于缺口「已解决」/.test(report),
      tree + '/pages/f4-report.html must keep the "done ≠ resolved" caveat');
    assert.ok(/没有可验证成果物的缺口不会开单/.test(report),
      tree + '/pages/f4-report.html must keep the "no artifact, no action" caveat');
    // 缺口不写进求职信正文，也不得被声称具备
    const apply = read(tree, 'js/f5-apply.js');
    assert.ok(/缺口不写进正文/.test(apply),
      tree + '/js/f5-apply.js must state that gaps stay out of the letter body');
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
  assert.ok(!hasId('public', 'pages/f4-report.html', 'definitelyNotAnId'));
  assert.ok(hasId('public', 'pages/f4-report.html', 'alList'));
});
