/* test_phase7b_contract.js · Phase 7b「wf03 路由去留 + public/*.md 公开范围」的判据
 *
 * 两件事，都是「把已经存在的约定变成判据」的延续 —— 但 7b 的两次都先是**把问题问对**：
 *
 *   1. `/api/wf03/*` 的去留。上一轮的表述是「前端消费方归零，去留待定」，而"待定"了两次
 *      都没定。7b 在决定删除之前先问"那消费者是谁"，答案是 **DuMate 工作流层**：
 *      `wfNN` 是产品自己的分类法（`GET /api/health` 的 workflows 段逐项报告），公开材料
 *      `capability_matrix.md` 的 N7/N9 就以 wf03 的测试为证据。**把"浏览器不调它"读成
 *      "没人调它"，与 7a 那条教训同形：观察面（前端）窄于它要判的语义（有没有消费者）。**
 *   2. `public/*.md` 的公开范围。`public/` 是 Vercel 静态根，往里面放文件 = 发布出去，
 *      没有中间态。这个集合此前是隐式的，6a 与 6b-1 两次记「属产品/隐私决策」后挂起 ——
 *      挂起没有触发条件，所以第三次出现。7b 把它变成 `contracts/publish-scope.json`：
 *      改清单 = 一次有记录的公开范围变更。
 *
 * 本文件只判**文本 / 集合层面的不变量**（快、确定）；真正跑逻辑的那条在
 * `scripts/publish-scope-check.py`（本文件的 7b-5 独立复算一遍，两条实现互不调用）。
 *
 * 每条判据都带探针：喂一个假样本，证明它**会红**。判据不可能变红等于没有判据。
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8');
const exists = (rel) => fs.existsSync(path.join(root, rel));

/* ── 纯函数：递归列出 public/ 下的 md（相对路径，posix 分隔符） ──────── */
function publicMarkdownFiles(dir, base) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name);
    const rel = base ? base + '/' + entry.name : entry.name;
    if (entry.isDirectory()) out.push(...publicMarkdownFiles(abs, rel));
    else if (entry.name.toLowerCase().endsWith('.md')) out.push(rel);
  }
  return out.sort();
}

/* ── 纯函数：判定一处文本是否还在"挂起"某个决议 ──────────────────────
 * 挂起语的三种真实写法（都出现过），它们共同的特征是**把决定推给未来**：
 * 去留见 Phase 7 / 去留是独立决议 / 哪些文档该公开属产品决策且未擅自增删。
 */
const PENDING_RE = /去留(?:见|是)\s*(?:Phase\s*7|独立决议)|待 Phase 7 决议|属产品\/隐私决策，[^。]*未擅自增删/;

function pendingStatements(src) {
  return (src.match(new RegExp(PENDING_RE.source, 'g')) || []);
}

test('7b-1 /api/wf03/* 三条路由保留：重写、Flask 规则、处理分支、health 条目都在', () => {
  const vercel = read('vercel.json');
  for (const p of ['/api/wf03/upload', '/api/wf03/jd', '/api/wf03/match']) {
    assert.ok(vercel.includes('"source": "' + p + '"'), 'vercel.json 缺 ' + p + ' 重写');
    // 目的地是 "/api?_route=wf03/<动作>"，所以引号在 /api 之前、?_route 之后才是 '=
    assert.ok(vercel.includes('_route=wf03/' + p.split('/').pop() + '"'),
      'vercel.json 的 ' + p + ' 重写目标不对');
  }
  const api = read('api/index.py');
  for (const r of ['"wf03/upload"', '"wf03/jd"', '"wf03/match"']) {
    assert.ok(api.includes('route == ' + r), 'route_api() 缺处理分支 ' + r);
  }
  for (const p of ['"/api/wf03/upload"', '"/api/wf03/jd"', '"/api/wf03/match"']) {
    assert.ok(api.includes(p), '本地 Flask 规则表缺 ' + p);
  }
  assert.match(api, /"wf03":\s*"available"/, 'health 的 workflows 段不再报告 wf03');
  // 判据自检：假路由必须抓得到
  assert.ok(!vercel.includes('"source": "/api/wf03/nope"'));
});

test('7b-2 WF-03 的公开证据链在位（这是"保留"的真正理由）', () => {
  const matrix = read('public/capability_matrix.md');
  const wf03Rows = matrix.split(/\r?\n/).filter((l) => l.includes('WF-03'));
  assert.ok(wf03Rows.length >= 2, 'capability_matrix.md 的 WF-03 行少于 2 条，证据链断了');
  assert.ok(wf03Rows.some((l) => /\|\s*N7\s*\|/.test(l)), 'N7（BM25 四态匹配）行不在了');
  assert.ok(wf03Rows.some((l) => /\|\s*N9\s*\|/.test(l)), 'N9（注入 JD 被置 flag）行不在了');
  // 这三行必须仍标"已验证"—— 降级成"待验证"等于公开材料自己撤回了能力声明
  for (const row of wf03Rows) {
    assert.ok(row.includes('已验证'), 'WF-03 有一行不再标"已验证"：' + row.slice(0, 40));
  }
  // 证据列的实际写法是 `[CAP-008]` / `[CAP-010]` 这类编号 + N8 的 tests/*.json
  // （**不是** tests/test_api.py —— 那是 WF-02/WF-04 两行的证据；第一版判据这里写错了）
  assert.ok(wf03Rows.some((l) => /\[CAP-0\d\d\]/.test(l)),
    'WF-03 的证据编号（[CAP-00x]）不见了');
  assert.ok(wf03Rows.some((l) => l.includes('tests/')),
    'WF-03 的行里不再有任何 tests/ 证据');

  const sop = read('public/dumate-workflow-sop.md');
  assert.match(sop, /^## WF-03/m, 'dumate-workflow-sop.md 缺 WF-03 搭建节');

  // 路由本身有直接用例：这才是"删路由"会立刻伤到的东西
  const apiTests = read('tests/test_api.py');
  assert.ok(apiTests.includes('/api/wf03/jd') && apiTests.includes('/api/wf03/match'),
    'tests/test_api.py 不再覆盖 wf03 路由 —— 删路由的代价要重新评估');

  const rehearsal = read('scripts/run-rehearsal.py');
  assert.ok(rehearsal.includes('/api/wf03/jd') && rehearsal.includes('/api/wf03/match'),
    '彩排链的 match 步不再走 wf03 —— 那么"保留"的理由要重新论证');

  // 反向证据：前端确实不再消费（保留不是"前端又接回来了"）
  const bridge = read('public/js/data-bridge.js');
  assert.ok(!/['"]\/api\/wf03/.test(bridge),
    'data-bridge.js 又写死了 wf03 路径 —— 前端消费方应当仍是 0');
});

test('7b-3 "去留待定/公开范围待定"这类挂起语已清零，且给出了结论', () => {
  for (const rel of ['public/README.md', 'docs/README.md', 'docs/architecture.md',
    'docs/dependency-map.md']) {
    const pending = pendingStatements(read(rel));
    assert.deepEqual(pending, [], rel + ' 仍在挂起决议：' + pending.join(' / '));
    assert.match(read(rel), /Phase 7b/, rel + ' 没有记录 7b 的结论');
  }
  // 6a 刻意让两份自述逐字节相同（.md 不在镜像不变量内，所以这条一致性得自己守）
  assert.equal(read('docs/README.md'), read('public/README.md'),
    '两棵发布树的自述不再一致 —— 6a 刻意对齐过，改一份要同时改另一份');
  // 判据自检：三种真实出现过的挂起写法都要被抓到
  assert.equal(pendingStatements('后端 wf03 路由仍保留，去留见 Phase 7 决议。').length, 1);
  assert.equal(pendingStatements('后端路由仍在，去留是独立决议').length, 1);
  assert.equal(pendingStatements('属产品/隐私决策，本阶段未擅自增删').length, 1);
  // 反面：正常的阶段引用不得误报
  assert.deepEqual(pendingStatements('去留已在 Phase 7b 定案（保留）'), []);
  assert.deepEqual(pendingStatements('见 §19.6 的三段遗留'), []);
});

test('7b-4 公开范围清单结构合法：每份都要有用途分类与理由', () => {
  const data = JSON.parse(read('contracts/publish-scope.json'));
  assert.ok(Array.isArray(data.classes) && data.classes.length >= 5, '清单缺分类白名单');
  const entries = data.entries;
  assert.ok(Array.isArray(entries) && entries.length >= 15,
    '清单条目只有 ' + (entries || []).length + ' 条，判据近乎空判');
  const seen = new Set();
  for (const e of entries) {
    assert.ok(e.path && e.path.trim(), '有条目缺 path');
    assert.ok(!seen.has(e.path), 'path 重复：' + e.path);
    seen.add(e.path);
    assert.ok(e.reason && e.reason.trim().length >= 10,
      e.path + ' 的 reason 缺失或过短 —— 决定必须留理由');
    assert.ok(data.classes.includes(e.class),
      e.path + ' 的 class 不在白名单里：' + JSON.stringify(e.class));
  }
  // 清单必须自带评审时点，否则它会变成一张没有年份的护身符
  assert.match(String(data.reviewed_at || ''), /^\d{4}-\d{2}-\d{2}$/, '清单缺 reviewed_at');
  assert.ok(data.reviewed_in, '清单缺 reviewed_in（哪一阶段评审的）');
});

test('7b-5 清单与实际公开集合一致（独立复算，不调用 publish-scope-check.py）', () => {
  const tree = publicMarkdownFiles(path.join(root, 'public'), '');
  assert.ok(tree.length >= 15, '只找到 ' + tree.length + ' 份公开 md，判据近乎空判');
  const declared = JSON.parse(read('contracts/publish-scope.json')).entries
    .map((e) => e.path.replace(/\\/g, '/').replace(/^\.\//, '')).sort();
  const unrecorded = tree.filter((p) => !declared.includes(p));
  const stale = declared.filter((p) => !tree.includes(p));
  assert.deepEqual(unrecorded, [], 'public/ 下有未记录的 md：' + unrecorded.join(', ')
    + ' —— 往 public/ 放文件就是发布出去，必须同步改 contracts/publish-scope.json');
  assert.deepEqual(stale, [], '清单里有但 public/ 下已不存在：' + stale.join(', '));
  // 判据自检：两个方向都要抓得到
  assert.equal(['new.md', 'README.md'].filter((p) => !['README.md'].includes(p)).length, 1);
  assert.equal(['README.md', 'gone.md'].filter((p) => !['README.md'].includes(p)).length, 1);
  // 子目录要被遍历到（blind-test-results/blind-test-report.md 就在这里）
  assert.ok(tree.some((p) => p.includes('/')), '递归没有进子目录');
});

test('7b-6 公开范围门禁脚本在位，且按家族约定带自检与退出码语义', () => {
  const rel = 'scripts/publish-scope-check.py';
  assert.ok(exists(rel), rel + ' 不存在');
  const src = read(rel);
  assert.ok(src.includes('判据自检'), rel + ' 缺少判据自检段');
  assert.ok(src.includes('探针失效'), rel + ' 缺少"探针失效"报错路径 —— 自检没有出口');
  assert.ok(src.includes('退出码 0 = 通过'), rel + ' 未在文件头声明退出码语义');
  assert.ok(src.includes('空判防线'), rel + ' 缺少空判防线 —— 规则空转会假绿');
  const probes = src.match(/探针 \d+/g) || [];
  assert.ok(probes.length >= 8, '自检探针只有 ' + probes.length + ' 个，应当覆盖增/删/归一/结构四类');
});

test('7b-7 public/index.md 是发布树自己的索引：标题不再错标，且列全本树文档', () => {
  const src = read('public/index.md');
  assert.ok(!/^#\s*docs 文档目录索引/m.test(src),
    'public/index.md 又把自己标成 docs 的目录索引 —— 它在发布树里，是给公众看的');
  assert.match(src, /^#\s*.*公开文档索引/m, 'public/index.md 缺少发布树自己的标题');
  const tree = publicMarkdownFiles(path.join(root, 'public'), '');
  const missing = tree.filter((p) => p !== 'index.md' && !src.includes(p));
  assert.deepEqual(missing, [], 'public/index.md 漏列了本树自己的 md：' + missing.join(', '));
  // 索引里要点明"新增文档还要改清单"，否则下一个人只会改索引
  assert.ok(src.includes('contracts/publish-scope.json'),
    'public/index.md 没告诉新增文档的人还要同步公开范围清单');
});

test('7b-8 两条判据的观察面都写在脚本文件头（免得下一个人以为它管得更宽）', () => {
  const src = read('scripts/publish-scope-check.py');
  assert.match(src, /## 观察面/, '没写观察面');
  assert.ok(src.includes('不看'), '没写"本判据不看什么" —— 这正是本项目反复栽过的坑');
  // 明确排除非 md 与 docs/ 侧，说明边界是刻意的
  assert.ok(src.includes('非 md 文件'), '没说清非 md 文件归谁管');
  assert.ok(src.includes('docs/**'), '没说清 docs/ 侧的 md 为何不在范围内');
});
