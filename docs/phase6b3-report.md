# phase6b3-report.md · Phase 6b-3（D7 进入即强制注册/登录）

- 日期：2026-09-17
- 提交：**`<待回填>`**（功能与判据）＋ **`<待回填>`**（文档与回填）
- 阶段目标：把 `product-scope.md §10.3` 的 D7 要求落地 —— 用户点进产品即**强制注册/登录**，
  以弹窗形式呈现；同时**不得回退**既有安全性质，不得让任何页面在未登录时出现空白或不可用。
- 依据：`docs/product-scope.md §10.3`（D7 四条要求）、`§8`/`§10.4`（D7 行）、
  `docs/phase6b2-report.md §7`（6b-3 的下一步）、DoD #18（≤3 分钟到第一个 Target Job Decision）。
- 结论：D7 落地为**政策层 + 机制层**的分工（`js/auth-gate.js` + `js/account.js`）与
  **原生 `<dialog>`** 弹窗。服务端安全实现一行未改。首轮门禁 15 项里红了 5 项，
  **其中 4 项是判据自己的缺陷**、1 项是产品接口隐患 —— 两半都已修，并用**变异测试**证明
  6 个关键判据真的会红。

---

## 0. D7 为什么单独立一个阶段

6b-2 结束后，`product-scope.md §7` 的四个一级工作区与"去内部代号"都已成立，但 D7 一直挂着 ⏳。
它与其他前端工作的性质不同：

| | IA 收敛（6b-2） | D7 门禁（6b-3） |
| --- | --- | --- |
| 改动对象 | 导航、文件名、页面结构 | 进入产品的**准入判定** |
| 失败后果 | 用户多绕一步 | **未登录用户能浏览到产品内有价值的内容**（或反过来：服务器故障时把所有人挡在外面） |
| 可验性 | 静态可扫（标签、路径） | 必须验**行为**：断网会不会放行、本地标记能不能绕过 |

第三种差异是关键：D7 的核心性质**无法靠读源码断言**。所以本阶段的第一个设计决定不是"怎么写弹窗"，
而是"怎么让这些性质可判据化"。

---

## 1. 修改摘要

```
<待回填>
```

### 1.1 分层：政策与机制分开（本阶段的主要设计决定）

| 文件 | 角色 | 内容 |
| --- | --- | --- |
| `public/js/account.js`（修订） | **机制** | 弹窗、表单、`/api/auth/*` 调用。新增：`unknown` 登录态分支、`refreshAuth()` 返回三态、`setBusy()`、`notify()` 事件广播、原生 `<dialog>` 的 `openAuth()` / `closeAuth()` |
| `public/js/auth-gate.js`（新增） | **政策** | `decide()` / `plan()` 两个**纯函数**决定"谁被拦、何时拦、能否关掉"；`apply()` 是唯一的 DOM 写入点；`check()` 串起"问服务端 → 决策 → 应用" |
| `public/css/sidebar.css`（修订） | — | `.zy-modal` 改为原生 dialog 形态 + `::backdrop`；新增 `.zy-gate-why` / `.zy-gate-status`(+`.err`) / `.zy-gate-retry` / `.zy-btn[disabled]` |
| 7 个页面（两树各 7 个） | — | 弹窗由 `<div class="zy-modal zy-hidden">` 改为 `<dialog class="zy-modal">`；补上说明文案、`role="status"` 状态区、「重新连接」按钮；脚本装配在 `account.js` 之后插入 `auth-gate.js` |
| `scripts/sync_sidebar.py`（修订） | — | 侧栏模板同步为 dialog 形态；注入分支在 `account.js` 之后追加 `auth-gate.js`（保持"`public/` 为唯一源"的契约） |
| `tests/test_phase6b3_contract.js`（新增） | — | **15 项**：装配 / 原生 dialog / 三态载体 / 豁免名单 / 安全口径 / 三层兜底 / 行为层四象限 / 五条判据自检与探针 |
| `work/mutate6b3.sh`（新增） | — | 变异测试：6 个关键判据逐个注入违规、确认变红、快照回放恢复 |

### 1.2 政策层的接口形状

```
decide(pathname, me) → { gate: 布尔, reason: 'authed' | 'anonymous' | 'unavailable' | 'exempt' }
plan(decision, opts) → { action, mode: 'exempt' | 'authed' | 'forced', gateState, forced, retry, status }
check()              → 决策本体（gate 布尔 + reason）＋ 计划的呈现字段（mode / gateState / forced）
```

`me` 是 `account.js` 从服务端拿到、**原样**转交的答复，三种可区分形态：

| 服务端答复 | decide 结果 | 行为 |
| --- | --- | --- |
| `{ ok: true, logged_in: true, user: {...} }` | `authed` | 关弹窗，放行 |
| `{ ok: true, logged_in: false, user: null }` | `anonymous` | 强制弹窗（`empty` 态） |
| `{ ok: false, reason: '...' }` | `unavailable` | 强制弹窗（`error` 态）+ 「重新连接」 |

**为什么必须把第三行单独拿出来**：把"不知道"与"是游客"合并，等于给服务器故障开了一道后门 ——
断网时所有人都直接进入产品。反过来若合并到"已登录"，则服务器故障时无人可用。两者都不能接受，
所以三态是**必须**的，不是锦上添花。

---

## 2. 三条不可回退的安全口径

1. **登录态只认服务端。** 政策层不读 `localStorage` / `sessionStorage` / `document.cookie`，
   只经 `ZY_ACCOUNT.refreshAuth()` 取 `GET /api/auth/me` 的答复。前端一句 `loggedIn = true`
   不该能开门。
2. **拿不到答复一律拦下。** 见 §1.2 的第三行。
3. **强制态关不掉，三层兜底。**

| 层 | 位置 | 内容 |
| --- | --- | --- |
| ① 政策层 | `auth-gate.js` | `classList.toggle('zy-hidden', result.forced)` 隐藏关闭按钮 |
| ② 机制层 | `account.js` | `closeAuth()` 在 `forced && !currentUser` 时直接拒绝 |
| ③ 样式兜底 | `sidebar.css` | `[data-forced="true"] .zy-modal-close { display: none }` —— JS 没跑到时按钮也不露出来 |

`Esc` 走原生 `<dialog>` 的 `cancel` 事件，在强制态被 `preventDefault()` 拦下。

**可访问性与"不出现空白页"**：`showModal()` 自带焦点陷阱与 `::backdrop`；三态
（`empty` / `error` / `disabled`）显式存在且可断言，状态区是
`role="status" aria-live="polite"`；门禁只把交互挡在弹窗后面，**页面本身始终可见**，
不清空也不报错。注册弹窗只有四项（手机号、邮箱、密码、账户名），满足 DoD #18。

---

## 3. 首轮五红的成因（本阶段最值钱的部分）

15 项判据首轮跑出 **10 绿 5 红**。逐个查完后发现：**4 项是判据自己的缺陷，1 项是产品接口隐患。**

| # | 症状 | 真因 | 归属 |
| --- | --- | --- | --- |
| 5 | "出现了 localStorage" | `includes()` 扫**全文**，命中的是文件头那句"本文件不读 localStorage" | 判据 |
| 8 | "结构相同但引用不等" | `deepStrictEqual` 比较 **VM realm** 与宿主 realm 的对象原型 | 判据 |
| 12 | `'forced' !== true` | `check()` 返回的是 `plan()` 结果（`gate` 是**字符串**），测试以为返回决策（`gate` 是**布尔**） | **产品** |
| 13 | 同上 | 同上 | **产品** |
| 14 | `data-gate` 是 `undefined` | 同上（`plan()` 结果里没有 `reason` 字段），以及 `check()` 未写 `data-gate` 的连带 | **产品** |

### 3.1 判据缺陷一：把注释当成实现

`auth-gate.js` 的文件头写着：

```
 *   - 登录态**只**由服务端 GET /api/auth/me 判定。本文件不读 localStorage /
 *     sessionStorage，也不做任何"本地有标记即已登录"的短路
```

判据 `!src.includes('localStorage')` 被这句**安全说明**扫红。**判据在逼人删掉最该留下的那句话。**
这与 6b-1 踩过的是同一件事（`/\/api\/wf03/` 扫 `data-bridge.js` 被自己的说明性注释命中）。

修法：新增 `codeOnly(src)` —— 字符串感知的注释剥离器，剥掉行注释与块注释、**保留字符串字面量的内容**
（真的用了 tokens 仍会被抓到）。

**连锁发现**：同一测试里的 `assert.match(src, /\/auth\/me/)` 写在 `auth-gate.js` 上，
但那个文件里**根本没有这个字面量** —— 真正的调用是 `account.js` 的 `api('/auth/me')`。
它是靠注释里的 "GET /api/auth/me" **凑巧通过**的，同样是空判。断言已挪到 `account.js`，
并要求命中**引号内的字面量**。

### 3.2 判据缺陷二：跨 realm 比较

`vm.runInNewContext` 里造出的对象，其 `Object.prototype` 与宿主那份**不是同一个**，
于是 `assert.deepStrictEqual`（在 `node:assert/strict` 下 `assert.deepEqual` 即它）
报"structure but not reference-equal"。**这是判据的锅，不是产品的锅。**

修法：`flat(v)` 把对象复制进宿主 realm 再比。并加一条探针断言
`Object.getPrototypeOf(vmObj) !== Object.prototype` —— 若哪天不再成立，说明 `flat()`
是在给一个不存在的问题打补丁，判据需要重审。

### 3.3 产品缺陷：`gate` 一个键、两种语义

`decide()` 返回 `gate: 布尔`（要不要拦），`plan()` 返回 `gate: 'exempt' | 'authed' | 'forced'`
（给 `data-gate` 用的模式名）。**同一个键、语义还相反**：豁免页 `plan().gate === 'exempt'`
是**真值**，而 `decide().gate === false` 意思是"别拦"。任何写 `if (plan.gate) …` 的调用方
在豁免页上都会拿到完全相反的行为。

修法：`plan()` 的键改为 `mode`，`check()` 返回**决策本体**（`gate` 布尔 + `reason`）
并附带计划的呈现字段。两层键名刻意错开，并在文件头写明不要在合并回去。

### 3.4 判据缺陷三：漏算了 init 基线

政策层在脚本加载时会**自己**问一次服务端（`init()` → `check()`），所以
"调用次数 = 1"的期望没把这条基线算进去 —— 实测是 2。

顺带发现同类的时序陷阱：`apply()` 的用例在两棵树里**同步**执行时能过，但它依赖的
`init()` 落地是**异步**的。这类"今天刚好过"的判据迟早会在改动后变成假红或假绿。
修法：把基线写成**显式断言**（`assert.equal(offline.meCalls(), 1, '政策层加载时就该问一次')`），
并让 `apply()` 的用例先 `await Promise.resolve()` 清掉 init 的异步落地。

### 3.5 这一族错误的第四个变体

| 阶段 | 判据 | 观察面比语义宽在哪里 |
| --- | --- | --- |
| 6a | `cmd \| tail -5; echo $?` | 取的是管道里 `tail` 的退出码 |
| 6b-1 | `git diff --check` | 只查未暂存，而流程是先 `git add -A` |
| 6b-2 | 活文档路径判据的"历史语境"窗口 ±10 行 | 窗口比"同一行或本节标题"宽 |
| 6b-3 | `includes('localStorage')` | 把**注释**也算进观察面 |

共同点：**判据的观察面比它要判的那个语义宽。** 四次的修法也同构：把观察面收窄到语义本身。

---

## 4. 判据可证伪性的证明（变异测试）

这个项目已经四次栽在"判据不可能变红"上，所以**全绿本身不构成证据**。本轮对 6 个关键判据
各注入一次违规，逐个确认对应用例真的变红，再回放快照恢复：

| # | 注入的违规 | 应变红的用例 | 结果 |
| --- | --- | --- | --- |
| M1 | 政策层真读一次 `localStorage` | 5 · 不得以本地存储判定登录态 | ✓ |
| M2 | 把 `unavailable` 判为放行（断网即放行） | 8 · decide 四象限 | ✓ |
| M3 | `check()` 退回返回计划（`gate` 键又变字符串） | 14 · 豁免页 | ✓ |
| M4 | 去掉 CSS 强制态兜底 | 7 · 三层兜底 | ✓ |
| M5 | 豁免名单悄悄扩容一项 | 4 · 名单恰好一项 | ✓ |
| M6 | 产品页不再挂政策层 | 1 · 装配顺序 | ✓ |

**6/6 全部被抓到**，恢复后回到全绿。脚本：`work/mutate6b3.sh`。

M1 与 M2 值得单独看：它们对应的正是 D7 最该守的两条（本地标记不能绕过、不知道不能当放行）。
这两条过去只写在文档里，现在是**会失败的门禁**。

### 4.1 事故：变异脚本用 `git checkout` 恢复，冲掉了未提交的改动

变异脚本第一版对 `public/index.html` 的恢复写的是 `git checkout -- public/index.html`。
那条命令回到的是 **HEAD**（6b-2 状态），把本轮**尚未提交**的 `<dialog>` 改造一起冲掉了。

- 受损范围经核对**只有这一个文件**（其余 6 页与 `docs/` 侧完好）
- 已从镜像树逐字节还原（`docs/index.html` 未被变异触及），`git hash-object` 两侧一致
- 修法：变异脚本对**每个**被改文件都先快照到工作副本，恢复时从快照回放

> 教训：**变异脚本面对的永远是未提交的工作区，git 在这里不是安全网。**
> `git checkout -- <path>` 的语义是"回到索引/HEAD"，不是"回到我改之前"。

（6b-2 那次变异测试也用了 `git checkout` 恢复，能成功是因为当时的改动全部已被幂等补丁脚本
覆盖、可以重放。这属于**侥幸**，不是方法。）

---

## 5. 门禁

| # | 步骤 | 结果 |
| --- | --- | --- |
| 1 | `pytest tests/` | **482 passed**（167.10s） |
| 2 | `node --test tests/*.js` | **69 passed / 0 failed** |
| 3 | schema 校验 | **OK=32 FAIL=0** |
| 4 | 敏感扫描 | **246 文件无发现** |
| 5 | vercel 死路由（实证逐方法探测） | **0**（44 条重写 / 38 条 API） |
| 6 | `git diff --check HEAD` | **clean** |
| 7 | 双方言 DDL | **15 passed** |
| 8 | 真实 HTTP 冒烟 | **70 / 70** |
| 9 | 发布镜像不变量 | **30 个非 md 文件逐字节相同** |
| 10 | 活文档页面路径 | **46 处页面引用**全部可解析（25 处存在 + 21 处带历史标记） |

`gate6b3 exit=0`。node 用例数 **54 → 69**（+15，全部来自 `tests/test_phase6b3_contract.js`）。
镜像文件数 29 → **30**（+`js/auth-gate.js`）。pytest 保持 **482**（本阶段不新增 Python 判据）；
敏感扫描 243 → **246** 文件（新增 js/md 各一 + 报告）。

---

## 6. 有意未做（口径）

| 事项 | 为什么 |
| --- | --- |
| **`docs/architecture.md:121` 里 `js/kb.js` 的陈旧引用未改** | 该文件已不存在，但活文档路径门禁**只覆盖 `pages/*.html`**，`js/*.js` 不在观察面内。改它会牵动"前端实际消费 N 个端点"的计数口径，属独立决议 → Phase 7：**把该门禁的范围从"页面"扩到"脚本"** |
| **`/api/wf03/*` 后端路由仍未删** | 前端消费方已归零，`tests/test_api.py` 与 `run-rehearsal.py` 仍覆盖，去留见 Phase 7（沿用 6b-1/6b-2 口径） |
| **证据档案界面未做** | `getProfile` 已接好，但候选证据的确认 / 编辑 / 删除是独立工作区 |
| **`public/*.md` 公开范围未动** | 产品与隐私决策（Phase 7） |
| **`HANDOFF.md`、`.env` 重复变量、`tools/` 归并、`api/index.py` 拆分** | 均为 Phase 7 范围，本阶段不扩大改动面 |
| **历史文档里的旧名未批量改写** | `CHANGELOG.md`、各 `phaseN-report.md`、`handoffs/`、`deliverables/` 记录的是"当时是什么样"，改写等于伪造审计记录 |

**口径**：本阶段是**准入能力的落地**，不是账号体系重构。发布说明可以写"进入产品需先注册/登录"，
但**不得**写成"我们重做了账号系统"或"增强了安全性"—— 服务端安全实现一行未改，
门禁只是加在它前面的一层政策。

---

## 7. 进度与下一步

- **DoD #18 的约束已满足**：注册弹窗四项、无多余步骤。
- **D7 由 ⏳ 待实现 → ✅ 已实现**（`product-scope.md §8` / `§10.4` 两处表格同步）。
- 主阶段 **7/8**（Phase 0–5 完成，Phase 6 的 6a / 6b-1 / 6b-2 / 6b-3 全部完成）。

**下一步**：Phase 7 —— `tools/` → `domain/` + `providers/` 归并、`api/index.py` 拆分（3000+ 行）、
`/api/wf03/*` 后端路由去留、`HANDOFF.md` 去留、`.env` 重复变量、`public/*.md` 公开范围、
活文档路径门禁范围扩到脚本。**D3（单位/职位检索）期限 2026-10-13。**
