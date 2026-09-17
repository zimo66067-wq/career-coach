# phase6a-report.md · Phase 6a（前端 canonical 唯一化与死树清理）

- 日期：2026-09-17
- 提交：**`a1586a5`**（46 文件，+749 / −4511；其中 25 项是删除）
- 阶段目标：**DoD #15「前端只有一套 canonical」** + **DoD #25 的前端部分**。
- 依据：`docs/product-scope.md §9` DoD 表 #15 行（原文 "public / docs / ui 三份 → Phase 6"）、
  `docs/dependency-map.md §4.4`（三份前端副本）、`docs/phase1-report.md` 遗留项 #5（`ui/prototype` 陈旧分叉）。
- 结论：**第三棵树整树删除，canonical 口径从"约定"升级为"双向逐字节门禁"**，
  并顺带修掉四处真实偏差（重复样式表、过期能力矩阵、死树自述 README、指向不存在文件的索引项）。

---

## 0. 为什么是"6a"（裁决）

`product-scope.md §7` 与多条 Phase 报告都把 Phase 6 写作"前端工作面"，但它实际包含**四件规模不同的事**：

| 子项 | 内容 | 规模 |
| --- | --- | --- |
| ① canonical 唯一化 | 三棵树收敛、镜像关系门禁化 | 结构，可完全验证 |
| ② IA 收敛 | 导航 ≤4 个一级工作区 + 去除用户可见 F 代号 | 中，需产品口径 |
| ③ 闭环接线 | 目标岗位工作区挂 `job-upload.js`、F5 接 `targetJobId`、Action Loop 消费 8 条路由 | **大**，是真正的用户价值 |
| ④ D7 登录门禁 | 进入即强制注册/登录 | 中，独立 |

一次做完必然注水。而且 ①② **是 ③④ 的前置** —— 改名不能跨着一棵待删的树做，
`public/README.md` 还在描述 `ui/prototype` 的页面清单时也没法谈"目标岗位工作区"。

**故拆为 6a（本轮 · 结构）与 6b（IA 收敛 + 闭环接线 + D7）**。这与 Phase 4/4b 的拆法同源：
先落"可验证的结构结论"，再落"用户可见的能力"。

---

## 1. 修改摘要

```
46 files changed, 749 insertions(+), 4511 deletions(-)    ← 25 项删除：ui/ 24 + scripts/capture_ui.py 1
```

| 动作 | 对象 | 要点 |
| --- | --- | --- |
| **删除** | `ui/`（24 文件） | `prototype/` 21 + `assets/` 3；全部与 `public/` 冗余，见 §2 |
| **删除** | `scripts/capture_ui.py` | 目标树被删，且本就指向 Phase 1 已删的 `f2-match.html` |
| **新增** | `scripts/sync_mirror.py` | 规则化镜像同步/校验，`--check` 退出码 1 报漂移 |
| **新增** | `tests/test_phase6a_contract.js` | 4 项：死树引用、重复引入、自述完整性、判据自检 |
| **重写** | `tests/test_publish_mirror.js` | 硬编码 26 项清单 → 规则驱动 + 双向 + 自检 |
| **重写** | `public/README.md`、`docs/README.md` | 死树自述 → 发布树说明 |
| **修正** | `scripts/sync_sidebar.py` | 来源声明 + 漏掉的 `pages/f5-apply.html` |
| **修正** | `pages/f4-report.html`（两树） | 去掉重复引入的 `css/sidebar.css` |
| **同步** | `public/capability_matrix.md` | 08-05 → 08-06（含实跑证据的那版） |
| **修正** | `public/index.md`、`docs/index.md` | 删掉指向不存在文件的 `voice-test-checklist.md` 行 |
| **更新** | `README.md`、`workflows/wf-05-ability.md`、`wf-06-ops.md`、`docs/dependency-map.md`、`docs/architecture.md` | 指向死树的指引 |

---

## 2. 死树 `ui/` 的证据链：为什么可以整树删

删除前逐条核实，四类证据全部成立：

| # | 证据 | 实测 |
| --- | --- | --- |
| 1 | **不是"有独有内容的原型"** | `ui/prototype/` 的 21 个文件名**全部**已存在于 `public/`，无一独有；12 个逐字节相同，另 9 个内容不同（其中 8 个更小，如 `css/main.css` 20336 vs 32008、`js/data-bridge.js` 29428 vs 31308、`pages/f5-apply.html` 7440 vs 9542；`pages/f3-interview.html` 反而更大，16095 vs 15836）；prototype 侧还**缺** `pages-api-config.js`、`job-upload.js`、`resume-upload.js`，并含 7 处坏引用 |
| 2 | **不是"另一份部署副本"** | `vercel.json` 的静态重写只覆盖 `/`、`/index.html` 与 `css`、`js`、`pages`、`assets` 四类路径，**无 `ui/` 重写** → 从未部署（`dependency-map.md §4.4` 实测 `/ui/prototype/index.html` 404） |
| 3 | **无任何运行期引用** | `public/`、`docs/` 的 HTML/JS/CSS 中零处指向它（只有 `Array.prototype` 这类误命中） |
| 4 | **它自己就是坏的** | 7 处坏引用：6 处指向不存在的 JS（`pages-api-config.js` ×5、`resume-upload.js` ×1）+ `js/radar.js` 里 `../assets/vendor/echarts.min.js` 在 prototype 下失效（真实文件在上一级 `ui/assets/`） |

另外：`ui/assets/`（`favicon.svg` / `logo.svg` / `vendor/echarts.min.js`）与 `public/assets/`
**逐字节完全相同**，是纯重复副本 —— `CHANGELOG.md` 2026-09-13 已把 `/assets/:path*` 重写改到
`/public/assets/:path*` 并把 assets 纳入两棵发布树，`ui/assets` 就此失去唯一性。

> 这一条与 Phase 4 的孤儿行动、Phase 4b 的死路由判据是同一类问题：
> **"看起来还在用"和"真的还在用"之间，只有实测能区分。**

---

## 3. canonical 不变量：从"约定"到"门禁"

### 3.1 关系定死

| 树 | 角色 | 依据 |
| --- | --- | --- |
| `public/` | **唯一 canonical**，Vercel 生产静态根 | `vercel.json` 重写目标 + 线上实测 |
| `docs/` | GitHub Pages 发布镜像 | `docs/architecture.md §12.4`「`pages-build-deployment` 从 `main` 构建 `docs/`」 |

**Pages 到底发布哪棵树，本轮做了实测确认**（因为文档只有一句话，而这句话直接决定 canonical 方向）：
远端 `/index.md` 返回的是 **docs 时代的目录索引**（列着只存在于 `docs/design/` 的文件），
且远端 `/product-scope.md` 404、`/observability.md` 200 —— 与 `docs/` 的文件集吻合、与 `public/` 不吻合。
（Pages 内容偏旧是因为本地领先 `origin/main` 13 个提交、从未推送。）

### 3.2 不变量

> 两棵发布树下所有 **非 `.md`** 文件，必须**集合相同**且**逐字节相同**（双向）。

- 校验：`tests/test_publish_mirror.js`（进 `node --test tests/*.js` 门禁）
- 修复：`python scripts/sync_mirror.py`；`--check` 只校验、退出码 1
- 实测基线：**27 个非 md 文件逐字节一致**

### 3.3 原判据有一个会永久漏检的洞

原测试是**硬编码的 26 项清单**，而 `public/` 下的非 md 文件实际是 **27** 个 ——
漏掉的正是 `blind-test-results/blind-test-summary.json`。

它**当时恰好两边相同**，所以这个洞不会立刻暴露；但只要它漂移，门禁照样全绿。
清单式判据的失效方式不是"误报"，而是**静默漏检** —— 这比误报危险得多。

改成规则驱动（`public/` 下递归收集所有非 `.md` 文件）后，新增文件自动纳入，清单不可能过期。

### 3.4 判据自检

`tests/test_publish_mirror.js` 的第三项 `the mirror check itself can fail`：
把比较逻辑抽成纯函数 `compareTrees(source, mirror)`，喂三组假文件集，
断言「仅源侧有 → missing」「仅镜像侧有 → extra」「内容不同 → differing」**都真的报得出来**，
并断言干净样本报空（防反向失效）。

另加一项 `the mirror rule is not vacuous`：断言规则至少匹配到 20 个文件 ——
**规则若一条都没匹配上，后面所有断言都会"假绿"**，这正是清单版最危险的失效方式。

`tests/test_phase6a_contract.js` 同样带自检：断言路径正则命中 `<script src="../ui/prototype/...">`
与 `<link href="ui/prototype/...">`，同时**不**命中 `Array.prototype.forEach`。

**并且实测过它会红**（不是只写在文档里）：

```
注入 docs/css/tokens.css 内容漂移 + docs/js/quick-demo-orphan.js 孤儿
  → python scripts/sync_mirror.py --check   退出码 1，报「孤儿」「内容不一致」各 1 处
  → node --test tests/test_publish_mirror.js  not ok 2，fail 1
恢复后 → 27 个非 md 文件逐字节一致，全绿

注入 pages/f4-report.html 重复 <link sidebar.css>
  → node --test tests/test_phase6a_contract.js  not ok 2，
    + 'pages/f4-report.html loads ../css/sidebar.css more than once'
恢复后 → 4/4 通过
```

### 3.5 门禁脚本自己也踩了一次同类坑

新门禁的第 9 步第一版写成：

```bash
$PY scripts/sync_mirror.py --check 2>&1 | tail -5 | tee -a "$OUT"
echo "mirror exit=$?"          # ← 取的是管道里 tail 的退出码，永远为 0
```

**这条检查永远不会报错。** 与 §3.3 那个清单漏洞是同一种病：判据看似在工作，实际不可能变红。
改为先把输出与退出码都接住再打印：

```bash
MIRROR_OUT=$($PY scripts/sync_mirror.py --check 2>&1); MIRROR_CODE=$?
printf '%s\n' "$MIRROR_OUT" | tail -5 | tee -a "$OUT"
echo "mirror exit=$MIRROR_CODE" | tee -a "$OUT"
```

实测三种状态都正确回读：正常 `exit=0`、注入 `docs/js/app-drift-probe.js` 孤儿后 `exit=1`、删除后回到 `exit=0`。

> 一句话总结本期的教训：**"检查没报错"和"检查报不了错"在日志上长得一模一样。**

---

## 4. 顺带修掉的四处真实偏差

删除死树时对照"它到底影响了什么"，挖出四处**不是本轮引入、但确实存在**的偏差：

| # | 偏差 | 后果 | 处置 |
| --- | --- | --- | --- |
| 1 | `pages/f4-report.html`（两棵树）在同一个 `<head>` 里**重复引入 `css/sidebar.css`**（第 11 行与第 149 行） | 每访一次白下一次样式表 | 去掉重复项；并加通用契约测试「同一页面不得重复引入任何 css/js」 |
| 2 | `public/capability_matrix.md` 的 N8 行比 `docs/` 那份旧：08-05 vs **08-06**，且后者引 `tests/embedding_full_recall_zhipu-3.json`、`tests/integration_recall_zhipu_embedding_3.json` 与 `deliverables/p0-03-evidence/`（2026-08-06 实跑） | **发布树上的能力声明停在更弱的证据版本** | 核实引用文件与证据目录**都真实存在**后，用 `docs/` 版覆盖 `public/` 版 |
| 3 | `public/README.md` 与 `docs/README.md` **逐字节相同**，整篇是 `ui/prototype` 的自述 | 两棵发布树的自述在介绍一棵即将删除的树；还列着 Phase 1 已删的 `pages/kb.html`、C7 区间带、七天计划 | 两棵都重写为发布树说明（页面清单 / 公开运行规则 / 发布结构与同步约定） |
| 4 | 两份 `index.md` 都索引着**不存在**的 `voice-test-checklist.md` | 文档索引指向死文件（Phase 1 删语音链路时遗留） | 删掉该行 |

另有两处同类问题一并处理：

- `scripts/sync_sidebar.py` 的 docstring 写着 `Source of truth: ui/prototype markup` ——
  删树后这句话变成**假话**，而它恰恰会误导下一个人去改错的树。改为 `public/` 为唯一源。
- 同一脚本的 `PAGES` **漏了 `pages/f5-apply.html`**：实测 6 个页面都已有侧栏，脚本只管 5 个 ——
  即它**不会维护 f5 页的侧栏**，将来改侧栏会漏掉一页。补上后跑一次确认幂等（12 个目标全部 "already ok"）。
- `scripts/capture_mobile_ui.py` 的 `PAGES` 里同样有已删的 `f2-match`，且**缺** `f5-apply` —— 同类修正。

---

## 5. 三件"有意不做"的事

1. **`scripts/p0-06-user-mission.py` / `p0-07-freeze.py` 里的 `ui/prototype` 引用不改。**
   它们是 2026-08-03 G9 提交包证据链的**时点归档脚本**，写的是"当时仓库长什么样"，
   删树后它的引用是**历史事实**而不是错误。改它才是篡改证据。
   **但不得重跑** —— 重跑会生成一份少了 `ui/` 的"冻结清单"，那是错误的证据。已记入本报告。
2. **`.md` 的公开范围不擅自增删。** `docs/` 有 45 份 md、`public/` 有 16 份，两棵都是公开树。
   哪些内部文档（`observability.md`、`remaining-items.md`、`model-baking-log.md` …）应当公开，
   是**产品与隐私决策**，与 D4/D5/D6 同类。本轮只把 `.md` **排除在自动镜像规则之外**并写明理由，
   不代替产品负责人做这个决定。
3. **IA 收敛与闭环接线不动。** 去 F 代号、导航 ≤4、目标岗位工作区、`targetJobId` 接线、
   消费 8 条 `/api/actions`、D7 登录门禁 —— 全部留给 **6b**。本期不碰任何用户可见行为。

---

## 6. 测试结果

```
pytest                     482 passed（Phase 5 为 481，+1 项 ui/ 整树已删断言）
node --test tests/*.js     42 passed / 0 failed（Phase 5 为 36：镜像测试 1→3 项，新增 6a 契约 4 项）
schema 校验                32 个 fixture 全部 OK
敏感扫描                   236 文件，passed（Phase 5 为 253：删除 ui/ 24 文件等）
vercel 死路由              44 条重写 / 38 条 API 路由，broken = 0
git diff --check           干净
双方言 DDL                 15 passed，各 29 张表（本阶段无 schema 变更）
真实 HTTP 冒烟             70/70（本阶段未改路由与冒烟脚本）
**发布镜像不变量**         27 个非 md 文件逐字节一致（新增第 9 步门禁）
**Phase 6a 契约**          4 项（新增）
```

新增/改写的测试：

| 文件 | 项数 | 关键断言 |
| --- | --- | --- |
| `tests/test_publish_mirror.js`（重写） | 3 | 规则非空转；两树非 md 文件集合相同 + 逐字节相同（双向）；**判据自检** |
| `tests/test_phase6a_contract.js`（新增） | 4 | 发布资源不得引用死树 `ui/`；同页面不得重复引入 css/js；自述必须覆盖所有实际页面；**判据自检** |
| `tests/test_phase1_deletions.py`（加 1 项） | +1 | `ui/` **整目录不得复活**（不只是 Phase 1 那三个文件） |

---

## 7. 剩余与口径

1. **DoD #15 达成（前端口径）**：`ui/` 删除 + `public`/`docs` 不变量门禁化。
   判据从"清单"改为"规则"，并把"证明它会红"作为门禁的一部分。
2. **DoD #25 只推进未结清**：剩余 4 个推送脚本（`scripts/push-*`）、5 个未调用 prompt，
   以及 `api/index.py` 单文件 3000+ 行、`tools/` 归并 —— 都属 Phase 7。
3. **口径：用户可见行为零变化。** 本阶段唯一对外可见差异是 `public/capability_matrix.md`
   与 `README.md` 的内容修正（前者纠正了过期的能力声明）。发布说明不得出现"新增能力"。
4. **镜像门禁只覆盖非 `.md`**。这条边界是明说的，不是遗漏：`.md` 的取舍见 §5.2。
   当前 `.md` 侧的已知差异只有 `index.md`（两树各自的目录索引，设计如此）——
   另一处 `capability_matrix.md` 已在本轮同步。

---

## 8. 下一步

- **Phase 6b（前端工作面主体）**：
  ① IA 收敛 —— 导航 5 → 4 个一级工作区（首页从导航项移出、由品牌区回首页），全量去除用户可见 F 代号；
  ② 目标岗位工作区 —— 给孤儿脚本 `js/job-upload.js`（25KB，已实现但**无宿主页面**）建页面，
  接通 `/api/wf03/upload|jd|match`；
  ③ F5 接 `targetJobId` —— 兑现 `phase4b-report.md §7` 的口径，并把"求职信引用了哪些证据"显式呈现；
  ④ Action Loop —— 消费 `/api/actions` 8 条路由（当前**零前端消费**）；
  ⑤ D7 进入即强制注册/登录。
- **Phase 7（目录与文档收尾）**：`tools/` 归并、`api/index.py` 拆文件、`HANDOFF.md` 废弃或重写、
  `.env` 重复变量、`public/*.md` 公开范围决策。
- **D3（单位/职位检索）** 仍封存，期限 **2026-10-13**。
