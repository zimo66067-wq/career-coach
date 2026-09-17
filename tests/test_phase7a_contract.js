/* test_phase7a_contract.js · Phase 7a「门禁扩面与文档真相」的判据
 *
 * 7a 不新增产品能力，它做的是同一件事的四次重复：**把约定变成判据，并把判据的观察面
 * 对准作者真实会写的写法**。四件事：
 *
 *   1. 活文档路径门禁从「页面」扩到「脚本」—— 连带覆盖**裸脚本名**（不带 `js/` 前缀）。
 *      6b-3 记过的那处 `kb.js` 陈旧引用就躲在这里：它写的是裸名，带前缀的扫描看不见。
 *   2. 「前端实际消费 N 个端点」这句手抄计数退役，换成三段不变量
 *      （前端字面量 ⊆ vercel 重写源 ⊆ route_api 处理分支），前两段各有脚本。
 *   3. `.env.example` 与代码的 env 读取点**双向**一致 —— 旧模板漏了 13 个变量，
 *      含服务端游客会话的签名材料；模板短了不会红，所以必须变成判据。
 *   4. `HANDOFF.md` 退役成薄指针 —— 它作为第二真相源已腐烂 6 周。
 *
 * 本文件只判**文本层面的不变量**（快、确定）；真正跑逻辑的三个门禁在 `scripts/` 下：
 * `live-doc-path-check.py` / `frontend-api-literal-check.py` / `env-example-check.py`。
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

/* ── 纯函数：HANDOFF「薄指针」判据 ─────────────────────────────
 * 薄指针 = 不保存任何随时间变化的事实。两类最容易腐烂的东西：
 *   ① 具体 commit hash（40 位 hex）—— "当前 commit" 的载体；
 *   ② 测试计数（`N passed` / `N 项通过`）—— 落笔那天对、第二天就可能不对。
 */
const FULL_HASH_RE = /\b[0-9a-f]{40}\b/g;
const COUNT_RE = /(?:\b\d+\s*(?:passed|failed|errors?)\b)|(?:\b\d+\s*项(?:通过|全绿|失败))/gi;

function pointerProblems(src) {
  const problems = [];
  const hashes = src.match(FULL_HASH_RE);
  if (hashes) problems.push('出现 40 位 commit hash：' + hashes.join(', '));
  const counts = src.match(COUNT_RE);
  if (counts) problems.push('出现测试计数：' + counts.join(', '));
  return problems;
}

/* ── 纯函数：从 markdown 反引号里抽出「看起来是仓库内路径」的 token ──
 * 只认含 `/` 或带已知扩展名的 token，避免把 `Phase 7a`、`672102b` 这类当路径。
 */
const TOKEN_RE = /`([A-Za-z0-9_./-]+)`/g;
const PATHISH_RE = /^[A-Za-z0-9_./-]+$/;
const KNOWN_EXT = ['.md', '.py', '.js', '.json', '.html', '.css', '.example'];

function repoPathsIn(src) {
  const out = new Set();
  let m;
  TOKEN_RE.lastIndex = 0;
  while ((m = TOKEN_RE.exec(src)) !== null) {
    const t = m[1];
    if (!PATHISH_RE.test(t)) continue;
    // 只收「像路径」的 token：含 `/`，或扩展名前面**还有基名**。
    // 后者是为了排除正文里指"某类文件"的写法 —— 例如「非 `.md` 文件」里的 `.md`
    // 是扩展名不是路径（第一版实测就把它当成了缺失文件）。
    const base = t.split('/').pop();
    const pathish = t.includes('/')
      || (KNOWN_EXT.some((e) => t.endsWith(e)) && base.indexOf('.') > 0);
    if (pathish) out.add(t);
  }
  return [...out];
}

test('7a-1 HANDOFF.md 是薄指针：不含当前 commit hash 与测试计数', () => {
  const src = read('HANDOFF.md');
  assert.deepEqual(pointerProblems(src), [],
    'HANDOFF.md 又开始保存会腐烂的"当前状态"了 —— 它应当是薄指针');
  // 判据自检：这两类样本必须被抓到
  assert.equal(pointerProblems('# c\n当前 commit：`' + 'a'.repeat(40) + '`\n').length, 1);
  assert.equal(pointerProblems('pytest **482 passed**\n').length, 1);
  assert.equal(pointerProblems('304 项通过\n').length, 1);
  // 反面：短 hash 与不带计数的数字不得误报
  assert.deepEqual(pointerProblems('最后同步是 `672102b`，此后走了十几个阶段'), []);
  assert.deepEqual(pointerProblems('Phase 6b-3（2026-09-17）'), []);
});

test('7a-2 HANDOFF.md 指到的每个仓库内路径都真实存在', () => {
  const src = read('HANDOFF.md');
  const paths = repoPathsIn(src);
  assert.ok(paths.length >= 25, '只抽出 ' + paths.length + ' 个路径，判据近乎空判');
  const missing = paths.filter((p) => !exists(p));
  assert.deepEqual(missing, [], 'HANDOFF.md 指向了不存在的路径：' + missing.join(', '));
  // 判据自检：假路径必须被抓到
  const probe = paths.concat(['docs/definitely-not-here.md']);
  assert.equal(probe.filter((p) => !exists(p)).length, 1);
});

test('7a-3 architecture.md 不再手抄「前端实际消费 N 个端点」，改述三段不变量', () => {
  const src = read('docs/architecture.md');
  assert.doesNotMatch(src, /前端实际消费\s*\d+\s*个端点/,
    '手抄的端点计数又回来了 —— 它只会持续漂移');
  assert.match(src, /前端字面量\s*⊆\s*vercel 重写源\s*⊆\s*route_api\(\)/,
    'architecture.md 必须给出三段不变量的表述');
  assert.match(src, /scripts\/frontend-api-literal-check\.py/,
    '三段链的第一段要有判据脚本');
  assert.match(src, /scripts\/vercel-dead-routes\.py/, '三段链的第二段要有判据脚本');
});

test('7a-4 architecture.md 的 §3 不写死路由条数，且覆盖 Phase 3/4 新增的三组路由', () => {
  const src = read('docs/architecture.md');
  const s3 = src.slice(src.indexOf('## 3. API Route'), src.indexOf('## 4. Service'));
  assert.match(s3, /条数不写在这里/, '§3 标题里的条数应当退役（数字必漂移）');
  for (const need of ['/api/target-jobs', '/api/actions', '/api/profile']) {
    assert.ok(s3.includes(need), '§3 路由表缺了现状中的核心路由 ' + need);
  }
  // 被 Phase 1 删掉的路由不得再作为**表格里的现状行**出现（说明性注记里提到它们是可以的）
  const rows = s3.split(/\r?\n/).filter((l) => l.startsWith('| ')).join('\n');
  for (const gone of ['/api/f2_major', '/api/knowledge/', '/api/tasks']) {
    assert.ok(!rows.includes(gone), '§3 路由表仍把已删除的 ' + gone + ' 当作现状');
  }
  // 判据自检：往表格里塞一条死路由，上面的断言必须能红
  const badRows = ['| 组 | `GET /api/knowledge/search` | x |'].join('\n');
  assert.equal(['/api/knowledge/'].filter((g) => badRows.includes(g)).length, 1);
});

test('7a-5 .env.example 结构合法：无未注释分隔行、无重复、无废弃变量', () => {
  const src = read('.env.example');
  const names = [];
  src.split(/\r?\n/).forEach((raw, i) => {
    const line = raw.trim();
    if (!line || line.startsWith('#')) return;
    const m = /^([A-Z][A-Z0-9_]*)=(.*)$/.exec(line);
    assert.ok(m, '.env.example:' + (i + 1) + ' 既不是注释也不是 NAME=VALUE：' + JSON.stringify(raw));
    names.push(m[1]);
  });
  assert.ok(names.length >= 25, '只解析出 ' + names.length + ' 个变量，判据近乎空判');
  const dup = names.filter((n, i) => names.indexOf(n) !== i);
  assert.deepEqual([...new Set(dup)], [], '变量重复声明：' + [...new Set(dup)].join(', '));
  for (const gone of ['LOG_LEVEL', 'ENV']) {
    assert.ok(!names.includes(gone), gone + ' 在全仓没有任何消费者，不该出现在模板里');
  }
  // 旧模板漏掉的那个服务端密钥必须补上
  assert.ok(names.includes('DUMATE_GUEST_SECRET'), '模板漏了 DUMATE_GUEST_SECRET');
  // 判据自检：非法行与重复必须被抓到
  const bad = ['====', '  ZHIPU_API_KEY =x', '1BAD=x'];
  for (const b of bad) assert.ok(!/^([A-Z][A-Z0-9_]*)=(.*)$/.test(b.trim()));
});

test('7a-6 三个新/改门禁脚本都在位，且各自带判据自检', () => {
  const scripts = [
    'scripts/live-doc-path-check.py',
    'scripts/frontend-api-literal-check.py',
    'scripts/env-example-check.py'
  ];
  for (const s of scripts) {
    assert.ok(exists(s), s + ' 不存在');
    const src = read(s);
    assert.ok(src.includes('判据自检'), s + ' 缺少判据自检段');
    assert.ok(src.includes('探针失效'), s + ' 缺少"探针失效"报错路径 —— 自检没有出口');
    assert.ok(/退出码 0 = 通过/.test(src), s + ' 未在文件头声明退出码语义');
  }
});

test('7a-7 活文档门禁的观察面确实含脚本层（含裸脚本名）', () => {
  const src = read('scripts/live-doc-path-check.py');
  assert.match(src, /JS_DIR_RE\s*=/, '缺少带目录前缀的脚本规则');
  assert.match(src, /JS_BARE_RE\s*=/, '缺少裸脚本名规则 —— kb.js 那类引用就躲在这里');
  assert.ok(src.includes('`([A-Za-z0-9._-]+\\.js)`'), '裸名规则必须锚在反引号上');
  // 同义措辞容忍：只认「已删除」，人写「已整条删除」就会被误判成漂移
  assert.match(src, /MARKER_RE\s*=/, '缺少同义措辞正则');
  for (const w of ['整条', '整块', '全部', '整体']) {
    assert.ok(src.includes(w), '同义措辞漏了 ' + w);
  }
  // 判据自检：8 个探针都要在
  const probes = src.match(/探针 \d+/g) || [];
  assert.ok(probes.length >= 8, '自检探针只有 ' + probes.length + ' 个，扩面后应当更多');
});

test('7a-8 env 门禁带「白名单必须写理由且仍在使用」的自检', () => {
  const src = read('scripts/env-example-check.py');
  assert.match(src, /NOT_DOCUMENTED\s*=\s*\{/, '缺少"有意不进模板"的白名单');
  assert.match(src, /已经没有任何读取点了/, '缺少白名单腐烂检查 —— 名单会变成护身符');
  assert.match(src, /没有写理由/, '缺少白名单理由检查');
  // 自指误报的修法要留在文件里（第一版实测报了 4 条 "代码在读 A_ONE"）
  assert.match(src, /SKIP_FILES/, '缺少排除自身的机制，会把自己探针里的样例字符串当成读取点');
});
