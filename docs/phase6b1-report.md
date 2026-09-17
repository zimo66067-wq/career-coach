# phase6b1-report.md · Phase 6b-1（目标岗位工作区 + 退役 wf03 前端路径）

- 日期：2026-09-17
- 提交：**`<待回填>`**（25 文件，+1991 / −1652）
- 阶段目标：`product-scope.md §7` 的 **Target Job Workspace** ——
  「分析这个岗位，能不能投」（建岗 → 拆要求 → 对照简历 → APPLY/STRETCH/PASS + 依据），
  以及它依赖的 **Action Loop 接线**（`/api/actions` 从零前端消费到有消费方）。
- 依据：`docs/product-scope.md §7`（目标信息架构）、`§15`（6a 报告给出的 6b 拆解）、
  `docs/phase3-report.md` 遗留项 #1（「闭环在界面上不可见」）、`docs/domain-model.md` §（11 条路由零消费）。
- 结论：**闭环第一次真正到了用户面前** —— 目标岗位工作区上线，`/api/target-jobs`（5 条）
  与 `/api/actions`（8 条）从"零前端消费"变为有消费方；孤儿脚本 `js/job-upload.js` 退役。

---

## 0. 为什么 6b 还要再拆一刀（裁决）

`docs/phase6a-report.md §8` 把 6b 定义为五件事：① IA 收敛 ② 目标岗位工作区 ③ F5 接 `targetJobId`
④ Action Loop 消费 8 条路由 ⑤ D7 登录门禁。侦察后发现两条**硬顺序约束**，所以 6b 再拆为 6b-1 / 6b-2：

| 约束 | 内容 | 后果 |
| --- | --- | --- |
| **A. 一级工作区 ≤ 4 是产品门禁，不是工程口味** | `tests/test_phase1_deletions.py::test_user_navigation_has_no_retired_entries` 把 `public/index.html` 的导航标签**写死**为 `["首页","F1 简历诊断","F3 模拟面试","F4 能力报告","F5 投递"]`，并注明"不得超过 DoD 的 4 项上限 + 首页" | 6b-1 **不能**顺手往导航里塞第 6 项 |
| **B. IA 收敛要等四个工作区都真的存在** | §7 的四个一级工作区是「Career Evidence / Target Job / Interview Practice / Action Loop」，其中 Action Loop = "F4 重构为 Gap & Action Plan + Retest"，即 `f4-report.html` 要**先**长出行动清单，才能改名叫「行动闭环」 | 6b-1 只能先把页面做好并从别处链入；改导航留给 6b-2 |

**故 6b-1 = 把事情做出来（页面 + 契约 + 接线），6b-2 = 把界面收敛（导航 5→4 + 去 F 代号 + Action Loop 落位）。**
6b-1 结束时导航**一个字符都没改** —— 这不是遗漏，是遵守约束 A 的结果。

另一个必然结果：目标岗位页面**不能**成为孤儿。它通过
① 首页功能卡 ② F5 投递页的引导链接进入，二者都进了本轮判据（见 §4）。

---

## 1. 修改摘要

```
25 files changed, 1991 insertions(+), 1652 deletions(-)
```

| 动作 | 对象 | 要点 |
| --- | --- | --- |
| **新增** | `public/pages/target-job.html` | 宿主页面：建岗表单 + 岗位清单 + 五状态结果区（empty/processing/success/error/degraded） |
| **新增** | `public/js/target-job.js` | 控制器：建岗 → 分析 → 渲染 Decision / 要求对照 / 缺口 / 依据 → 铺行动 |
| **新增** | `tests/test_phase6b_contract.js` | 5 条门禁：坏引用、退役路径不得复活、接线正确、页面可达、判据自检 |
| **重写** | `public/js/data-bridge.js` | 退役 4 个 wf03 包装器；新增目标岗位 7 + 行动闭环 9 + 档案 1 个方法 |
| **删除** | `public/js/job-upload.js`、`docs/js/job-upload.js`、`tests/test_job_upload.js` | 绑定的契约产不出 Decision/Gap，见 §2 |
| **清理** | `.job-upload-layout` CSS（两棵树） | 实测无任何 HTML 引用，随脚本一并退役 |
| **修订** | `tests/test_frontend_chain.js` | 链路断言由 `/api/wf03/*` 改为 `/api/target-jobs` + `/api/actions` |
| **修订** | `tests/test_upload_progress.js` | 删去 JD 进度上传与 job-upload 两条用例（路径已退役） |
| **修订** | `docs/product-scope.md §5`、`docs/architecture.md` | 按新证据改写「刻意未删 job-upload.js」这条旧裁决 |
| **同步** | `scripts/sync_sidebar.py`、`scripts/capture_mobile_ui.py`、两份 `README.md` | 新页面登记与自述 |

---

## 2. 决策反转：`job-upload.js` 为什么是退役而不是重新挂载

`product-scope.md §5` 原文写着「**刻意未删**：`js/job-upload.js` …… 它们属于要保留的 Target Job
Analysis …… 需要在目标岗位工作区里重新挂载，而不是删除」。Phase 6a 的 6b 计划
（`product-scope.md §15`、`docs/phase6a-report.md §8`）也沿用这个说法："给孤儿脚本 `js/job-upload.js` 建页面"。

**侦察把这条理由推翻了。** `job-upload.js` 的通路是
`uploadJD → submitJD → matchJD`，即 `/api/wf03/{upload,jd,match}`：

| 它产出 | 目标岗位工作区需要 |
| --- | --- |
| `jobProfile`（要求清单） | ✅ |
| `matchResult`（`score_M` + `gaps`） | ⚠️ 只有分数，**没有落库的 Gap** |
| —— | ❌ **Decision（APPLY/STRETCH/PASS）** |
| —— | ❌ **JobRequirement / EvidenceMatch 的持久化** |
| —— | ❌ **Gap → Action 的闭环** |

它的契约里根本没有 Decision 与 Gap 这两个概念。换句话说，**即使给它建了宿主页面，它也交不出
§7 要求的 Target Job Workspace**。此外它跨 6 个状态依赖 **29 个 DOM id**，其中多个来自已删的
`f2-match.html` 布局 —— 复用它等于把已删页面的布局契约重新引回 canonical 树。

**四个证据类**（与 6a 删 `ui/` 时的判法同源）：

| 证据 | 实测 |
| --- | --- |
| 是否无人挂载 | 全部 6 个页面的 `<script>` 都未引用它（Phase 1 起就如此） |
| 是否唯一调用方 | `submitJD` / `matchJD` 在全前端**只有它一个调用方**；`uploadJD*` 亦然 |
| 它的契约是否还成立 | ❌ 绑定 `/api/wf03/*`，产不出 Decision/Gap |
| 它自己是否已坏 | ❌ 依赖已删页面的 29 个 DOM id |

**处置**：新建 `pages/target-job.html` + `js/target-job.js` 走 `/api/target-jobs` + `/api/actions`；
退役 4 个桥接包装器与端点映射；后端 `/api/wf03/upload|jd|match` 三条路由**刻意保留**
（`tests/test_api.py`、`scripts/run-rehearsal.py` 仍覆盖），前端消费方归零这件事记入 Phase 7 待办。

---

## 3. 新接线：从"零消费"到有消费方

### 3.1 桥接层新增表面

| 分组 | 方法 | 端点 |
| --- | --- | --- |
| 目标岗位 | `listTargetJobs` / `createTargetJob` / `getTargetJob` / `analyseTargetJob` / `deleteTargetJob` | `/api/target-jobs`（GET/POST）、`/{id}`（GET/DELETE）、`/{id}/analyse`（POST） |
| 跨页口径 | `setCurrentTargetJob` / `getCurrentTargetJob` | 会话缓存 `currentTargetJobId` |
| 行动闭环 | `listActions` / `planActionsForTarget` / `openAction` / `getAction` / `startAction` / `completeAction` / `recordActionOutcome` / `dropAction` / `deleteAction` | `/api/actions`（GET/POST）、`/{id}`（GET/DELETE）、`/{id}/{start,complete,outcome,drop}`（POST） |
| 证据档案 | `getProfile` | `/api/profile` |

**「当前目标岗位」是这一轮引入的关键概念。** 在此之前，「我分析的是哪个岗位」这件事在前端不存在 ——
F3 靠 `matchResult` 缓存里的 `gaps` 出题（而 `matchResult` 已随 wf03 退役，必然为空）。
现在 F5 投递与 F3 出题共读同一个 `currentTargetJobId`，口径不再可能分叉。

### 3.2 后端本就支持，缺的只是前端

`api/index.py:1437` 起，`/api/wf04/start` **已经**接受 `targetJobId`：
拿该岗位的未解决缺口按 P0→P1→P2 排序出题（DoD #11 的落地方式），并回传 `questionPlan`。
6b-1 让 `data-bridge.startInterview()` 真的把这个参数递过去（未显式指定则取当前目标岗位）。

### 3.3 页面把后端的口径原样呈现，不美化

- **Decision 三值**：`APPLY` → 可以投 / `STRETCH` → 够一够再投 / `PASS` → 先别投。
- **要求四态**：`covered` / `weak` / `missing` / `unknown`，复用既有 `.badge` 变体。
- **依据不足是结论，不是故障**：后端在可核对事实 < 3 条时返回 `insufficient_grounds(422)`，
  页面**原样显示这条消息**，不给分数、不给结论 —— 这正是 DoD #9 要求的行为。
- **`insufficient_evidence` 与 `match_notice` 显式展示**，并把"新产生 N 条候选证据（需你确认）"告知用户，
  对应 D8 方案 A 的 `pending → 用户确认 → confirmed`。
- **空缺口不等于达标**：缺口为空时页面写明"这不等于能力已达标，只表示本次材料能对上的要求都被覆盖了"。

---

## 4. 三个判据缺陷（本轮修掉，都是"判据自己不可靠"这一类）

### 4.1 判据误报：把注释当接线

新写的 `test_phase6b_contract.js` 最初用 `/\/api\/wf03/` 扫 `data-bridge.js` 全文，
结果**被我自己写的说明性注释命中**（注释里解释了 wf03 为何退役）。
判据必须只看**接线**，不看散文 —— 改为解析 `ENDPOINTS` 映射的**值**
（`^\s+\w+\s*:\s*'([^']+)'`），并断言取值数 ≥10（防"整块被删空导致假通过"）。

### 4.2 判据空转：`git diff --check` 不看已暂存

9 步门禁的第 6 步一直是 `git diff --check`。但本流程的惯例是**先 `git add -A` 再跑门禁**，
而 `git diff --check` 只检查**未暂存**差异 —— 于是这一步恒为 0。

**实证**（临时仓库，注入行尾空白）：

| 命令 | 注入后 | 结论 |
| --- | --- | --- |
| `git diff --check`（全部已暂存） | `exit 0` | **空转** |
| `git diff --check HEAD` | `exit 2` + 报出 `a.txt:2: trailing whitespace.` | 有效 |

已改为 `git diff --check HEAD`（覆盖"相对 HEAD 的全部改动面"）。这与 6a 修掉的
`cmd \| tail -5; echo $?` 是同一类错误：**判据的观察面与实际改动面不重合**。

### 4.3 补丁脚本不幂等：`new` 包含 `old` 时重复追加

本轮为对抗工作区被清空（见 §5），把全部前端改动收进可重跑的 `patch6b.py`。
第一版幂等判据写成 `if new in text and old not in text: skipped` ——
对**追加型**补丁（`new = old + 新增行`）永远不成立，于是第二次运行把
`"pages/target-job.html",` 在两份 `PAGES` 清单里各插了两遍。
改为 `if new in text: skipped` 后幂等成立（已实测：第二次运行 39 项全部 skipped）。

**教训**：为"可重跑"而写的脚本，本身必须先被重跑验证一次。

---

## 5. 事故：工作区三棵树被外部进程清空（已完整恢复）

本轮中途发现 `public/`、`docs/`、`tests/` 三棵树在磁盘上消失。
`git status` 显示这些文件全部是**第二列 ` D`（工作区删除、未入暂存）**，而 `HEAD` 与索引完好。

**判定方法**（与 6a 那次 `scripts/` 事件同源）：`git rm` 会产生**已暂存**的删除（第一列 `D`）；
只有工作区被删、索引未动，才会出现第一列空白。据此确定是外部进程所为，而非命令写错。

**恢复**：`git checkout -- public docs tests`（从索引还原），随后逐个文件用
`git hash-object` 与 `git rev-parse HEAD:<path>` 比对，确认还原后与 `HEAD` **逐字节一致**
（`git diff --stat HEAD` 只列出本轮**有意**的 3 项删除）。

**损失与代价**：恢复点是"最后一次 `git add`"，因此**未暂存**的编辑会丢。
本轮丢了 5 个文件的编辑（`data-bridge.js` + 6 页导航 + 两个新文件），代价约十几分钟。

**因此本轮的工程对策**：

1. 全部前端改动收敛到 `work/patch6b.py`（幂等、可重跑、锚点缺失即报错），
   任何一步丢失后重跑即可复原；
2. 每完成一个可验证的小段就 `git add -A` —— **索引在本环境中未被清空**，暂存即是持久化；
3. 不再在两次暂存之间堆积大段未暂存工作。

---

## 6. 测试结果（9 步门禁全绿）

| # | 步骤 | 结果 |
| --- | --- | --- |
| 1 | pytest 全量 | **482 passed** |
| 2 | node 契约测试 | **40 / 40** |
| 3 | schema 校验 | **32 / 32 VALID** |
| 4 | 敏感扫描 | 238 文件，**通过** |
| 5 | vercel 死路由（逐条重写按方法探） | 重写 44 / API 重写 38 / **死路由 0** |
| 6 | `git diff --check HEAD` | **clean**（判据已修，见 §4.2） |
| 7 | 双方言 DDL | **15 passed** |
| 8 | 真实 HTTP 冒烟 | **70 / 70** |
| 9 | 发布镜像不变量 | **28 个非 md 文件逐字节相同**，exit 0 |

node 用例数由 42 变为 40：删去 `tests/test_job_upload.js`（3 条）与
`test_upload_progress.js` 的两条 JD 用例（−5），新增 `test_phase6b_contract.js`（+5），
并新增 1 条（`data-bridge 暴露带进度上传方法` 里断言退役方法为 `undefined`）。

---

## 7. 有意未做（口径）

| 事项 | 为什么 |
| --- | --- |
| **导航一个字符都没改** | 一级工作区 ≤4 是产品门禁，且 IA 收敛要等 Action Loop 真的存在，见 §0 |
| **F 代号未去除** | 同属 IA 收敛，留给 6b-2。本轮新页面**不带** F 代号（「目标岗位工作区」） |
| **F5 未接 `targetJobId`** | 后端 `/api/wf07/cover-letter` 目前按 `(session_id, company, position)` 取材料；改为按目标岗位取，需先定 `phase4b-report.md §7` 的落地口径 —— 属 6b-2 |
| **F3 未改为消费 `questionPlan`** | 桥接层已把 `targetJobId` 递过去，但页面渲染 `questionPlan` 属 6b-2 |
| **`/api/wf03/*` 后端路由未删** | `tests/test_api.py`、`scripts/run-rehearsal.py` 仍覆盖；去留是独立决议，记入 Phase 7 |
| **`/api/profile` 有方法无页面** | `getProfile` 已接好，证据档案界面（候选确认 / 编辑 / 删除）属 6b-2 之后 |
| **`public/*.md` 公开范围** | 未擅自动 —— 仍是产品/隐私决策（Phase 7） |

**口径**：本阶段是**能力新增**（此前界面上不存在目标岗位分析与行动闭环），
不是"性能提升"或"体验优化"。发布说明应写"新增目标岗位工作区"，且不得宣传为"能自动替你投递"。

---

## 8. 下一步

**6b-2**：IA 收敛到 4 个一级工作区（简历证据 / 目标岗位 / 模拟面试 / 行动闭环）+ 全量去除用户可见 F 代号
+ Action Loop 落位到 `f4-report.html`（消费 `/api/actions` 清单与状态流转）+ F5 接入当前目标岗位口径
+ F3 渲染 `questionPlan`。

**6b-3**：D7 进入即强制注册/登录门禁（`product-scope.md §10.3`、`docs/architecture.md` D7 ⏳）。

**Phase 7**：`tools/` → `domain/` + `providers/` 合并、`api/index.py`（3000+ 行）拆分、
`/api/wf03/*` 后端路由去留、`HANDOFF.md` 去留、`.env` 重复变量、`public/*.md` 公开范围。
**D3 期限 2026-10-13。**
