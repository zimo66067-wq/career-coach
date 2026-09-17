# phase7b-report.md · Phase 7b「wf03 路由去留 + 公开文档范围」

- 日期：2026-09-17
- 范围：Phase 7 的**第二个子阶段**。**不含** `api/index.py` 拆分（7c）与
  `tools/` → `domain/` + `providers/` 归并（7d）。
- 口径：**没有新能力**，对外行为零变化。改的是两处「已经挂起过两次的问题」，以及它们的判据。
- 上一阶段：`docs/phase7a-report.md`（门禁扩面与文档真相）

---

## 1. 一句话

7b 的两件事都先是**把问题问对，再动手**：

| # | 上一轮的表述 | 7b 先问的那一句 | 结论 |
| --- | --- | --- | --- |
| 1 | 「`/api/wf03/*` 前端消费方归零，**去留**待定」 | 消费者**是谁**？ | **保留** —— 消费者是 DuMate 工作流层，不是浏览器 |
| 2 | 「哪些内部文档该公开**属产品/隐私决策**」 | 这个集合**现在是什么**、有没有人看着？ | 16 份，且**此前没有任何人看着** |

两处都在 6a / 6b-1 各被挂起过一次。**挂起不是决定，而且挂起没有触发条件** ——
所以两处都在 7b 第三次出现。这正是 7a §8.3 第 3 条说的那件事：不给判据，它只会漂。

---

## 2. `/api/wf03/*` 的去留 → **保留**

### 2.1 上一轮的推理链断在哪

6b-1 的表述是：`js/job-upload.js` 退役 → 它绑定的 `/api/wf03/{upload,jd,match}` 前端路径归零
→ 后端路由"去留是独立决议"。

前三步都对。断的是最后一步的**隐含前提**：「前端没人调」被读成了「没人调」。
实测消费者有三个，全在浏览器之外：

| 消费者 | 证据 |
| --- | --- |
| **DuMate 工作流层** | `wf01`~`wf07` 是产品自己的分类法；`GET /api/health` 的 `workflows` 段逐项报告 `"wf03": "available"`；`/api/wfNN/*` 就是它在 HTTP 上的体现 |
| **公开能力声明** | `capability_matrix.md` 的 **N7**（BM25 四态匹配）与 **N9**（注入 JD 被置 flag）把 WF-03 标为**已验证**；`dumate-workflow-sop.md` 有 WF-03 搭建节 |
| **彩排链** | `scripts/run-rehearsal.py`：consent → diagnose → **jd → match** → interview → ability → delete |

另有 `tests/test_api.py` 的多条直接用例（`/api/wf03/jd`、`/api/wf03/match`
连同 `user_confirmed` 门禁的断言）。

### 2.2 与 7a 那条教训同形

> **判据的观察面（前端）窄于它要判的语义（有没有消费者）。**

7a 是「观察面太窄会把正确的东西判成错的」，7b 是「观察面太窄会让一个活接口被当成死代码删掉」。
两者同源：**观察面不等于语义面**。所以 7b 在删任何东西之前先做了一次"消费者是谁"的枚举 ——
这一步没有写进判据（它是一次性的判断），但它的结论写进了判据（7b-1 / 7b-2）。

### 2.3 判据（不是"记一笔"）

| 判据 | 内容 |
| --- | --- |
| `7b-1` | 3 条 vercel 重写 + 3 条 `route_api()` 处理分支 + 3 条本地 Flask 规则 + health 的 `wf03` 条目，四者都在 |
| `7b-2` | WF-03 的公开证据链在位：N7/N9 行仍标**已验证**、证据编号 `[CAP-00x]` 仍在、`dumate-workflow-sop.md` 的 WF-03 节仍在、彩排链仍走它、`tests/test_api.py` 仍覆盖它；**反面**断言 `data-bridge.js` 仍**不**写死 wf03（保留 ≠ 前端又接回来了） |

### 2.4 写这条判据时自己踩的坑（值得记）

第一版 7b-2 断言「WF-03 的证据行指向 `tests/test_api.py`」—— **判据红了，而错的是判据**。
去看那一行：

```
| N7 | WF-03 JD 匹配 | BM25 四态匹配 | 输出 covered/weak/missing/unknown | 已验证 | 2026-08-01 | `[CAP-008]` |
```

WF-03 的证据列是 `[CAP-008]` / `[CAP-010]`（证据编号）+ N8 的 `tests/*.json`（召回实测），
**不是** `tests/test_api.py` —— 那是 WF-02（N5）与 WF-04（N10）两行的写法。
我把自己从别处看到的模式顺手填进了证据列。

修法两条：断言改成"证据编号仍在 + 至少一条 tests/ 证据"，并把 `tests/test_api.py` 的覆盖
挪到它真正成立的断言位置（路由的**直接用例**，那是删路由会立刻伤到的东西）。
`docs/architecture.md` 里我写的同一句错话也一并改了 —— **判据抓出了正文的事实错误**，
这是判据除了防回归之外的第二种价值。

---

## 3. `public/*.md` 的公开范围 → **显式清单 + 冻结判据**

### 3.1 为什么这个集合此前没人管

Vercel 静态根是 `public/`（实测 200）。于是：

> **把一份文档放进 `public/`，与把这份文档发布出去，是同一个动作。**
> 没有中间态：没有 `internal/` 与 `published/` 的区分，没有构建期过滤，没有确认点。

后果不是"某份文档被误发"，而是**"公开范围"这件事根本没有一个可以去判的对象** ——
`public/index.md` 只索引 12 份、`dependency-map.md §4.5` 只列了 7 份、镜像判据
（`scripts/sync_mirror.py`）明确排除 `.md`。三处都不构成"当前公开集合是什么"的答案。

所以 6a 与 6b-1 只能写"属产品/隐私决策" —— 这不是推诿，是**当时确实没有可判的对象**。
7b 先把它造出来。

### 3.2 实测的公开集合

**16 份 md**（15 份在 `public/` 顶层 + 1 份在 `public/blind-test-results/`）：

| 用途分类 | 份数 | 文件 |
| --- | --- | --- |
| 发布树自述 | 2 | `README.md`、`index.md` |
| 赛事能力证据 | 2 | `capability_matrix.md`、`defense-evidence-index.md` |
| 平台搭建手册 | 1 | `dumate-workflow-sop.md` |
| 技术选型证据 | 3 | `embedding-model-comparison.md`、`qianfan-embedding-test-report.md`、`model-baking-log.md` |
| 盲测证据 | 1 | `blind-test-results/blind-test-report.md` |
| 工程规范 | 1 | `observability.md` |
| 测试方法与模板 | 2 | `mobile-accessibility-testing.md`、`user-research-template.md` |
| 交付与改版记录 | 1 | `redesign-v2-visual.md` |
| 过程追踪 | 3 | `p0-02-automation-alternatives.md`、`remaining-items.md`、`remaining-items-2026-08-02-fixed.md` |

**没有发现泄露**：`scripts/sensitive-scan.py`（门禁第 4 步）对全部 249 个文件无发现；
这批 md 是赛事提交物与过程证据，评委要通过分享 URL 读到它们，**公开是有意的**。
所以 7b 的动作**不是**撤下任何一份。

### 3.3 那 7b 做了什么

把「有意的」这个**结论**变成**可判的对象**：

| 物 | 角色 |
| --- | --- |
| `contracts/publish-scope.json` | 逐份记录：路径 + 用途分类 + **公开的理由**（每份都要写，缺 reason 判据红）。改它 = 一次有记录的公开范围变更，在 diff 里就是几行 |
| `scripts/publish-scope-check.py` | 全向比对 `public/**/*.md` 与清单：树里多出一份未记录的、或清单里有而文件没了的，都 exit 1。含**空判防线**（集合为空时拒绝执行，否则所有断言假绿）与 8 项自检探针 |
| `tests/test_phase7b_contract.js` 7b-4/7b-5 | 清单结构合法性（每份有分类、有理由、有评审时点）+ **独立复算**一遍集合一致性 —— 两条实现互不调用，不是把脚本的断言抄一遍 |

判据的观察面写在脚本文件头，**并明确写出它不看什么**（非 md 文件归镜像判据管、
`docs/` 侧的 md 不在发布树、md 的内容归敏感扫描与人工 review）——
不写清楚，下一个人会以为它管得比实际宽。

### 3.4 顺带修掉的一个真缺陷：`public/index.md` 是自己的树之外的索引

`public/index.md` 的标题是「**docs** 文档目录索引」，内容是 `docs/index.md` 的**真子集**
（少了 `design/*` 6 行、`design-and-tech-path.md`、`iteration-3-plan-*.md`、`test-report.md`）。
它坐在发布树里，却自称是另一棵树的索引，并且**漏掉了自己树里 4 份 md**
（`README.md`、`index.md`、`redesign-v2-visual.md`、`blind-test-results/blind-test-report.md`）。

这与 6a 修掉的「死树自述」是同一类：**自述文件描述的不是它所在的那棵树。**
现在它叫「职跃AI · 公开文档索引」，列全本树 15 份（不含自身），并在末尾点明
「新增文档还要同步公开范围清单」—— 那是下一个人一定会读到的地方。

---

## 4. 判据自检与变异测试

### 4.1 自检探针

| 判据 | 探针数 | 关键探针 |
| --- | --- | --- |
| `scripts/publish-scope-check.py` | 8 | 空判防线必须拦下；增 / 删**两个方向**都要红；前导 `./` 与反斜杠要归一（假阳性会让人删掉判据）；子目录要被遍历到；缺 reason / 分类不在白名单 / path 归一后重复，三类结构错误都要报 |
| `tests/test_phase7b_contract.js` | 8 个 test | 挂起语正则三种真实写法正反各验；清单两方向差异自检；递归未进子目录要红；`data-bridge.js` 的反面断言 |

### 4.2 变异注入

见 `work/mutate7b.py`。原则不变：**全绿本身不构成证据**，必须逐个确认对应用例会红，
再回放快照恢复。恢复一律用**快照回放**，不用 `git checkout`。

### 4.3 变异结果

| 注入的违规 | 应变红的判据 | 结果 |
| --- | --- | --- |
| 删掉 `vercel.json` 的一条 wf03 重写 | 7b-1 | ✅ |
| `api/index.py` 的 `wf03/match` 处理分支改名 | 7b-1 | ✅ |
| `health` 的 workflows 段去掉 `wf03` | 7b-1 | ✅ |
| `capability_matrix.md` 的 N9 行状态由「已验证」改成「待验证」 | 7b-2 | ✅ |
| `run-rehearsal.py` 的 match 步改走 `/api/target-jobs` | 7b-2 | ✅ |
| `public/README.md` 恢复「去留见 Phase 7 决议」 | 7b-3 | ✅ |
| 两棵树的 `README.md` 改成不一致 | 7b-3（一致性断言） | ✅ |
| 往 `public/` 放一份未记录的 md | `publish-scope-check.py` + 7b-5 | ✅ |
| 从 `public/` 删一份清单在案的 md | `publish-scope-check.py` + 7b-5 | ✅ |
| 清单里一条 entry 去掉 `reason` | `publish-scope-check.py` + 7b-4 | ✅ |
| `publish-scope-check.py` 去掉空判防线 | 该脚本探针 1 | ✅ |
| `public/index.md` 标题改回「docs 文档目录索引」 | 7b-7 | ✅ |

---

## 5. 门禁结果

门禁从 **12 步增至 13 步**（新增第 13 步公开范围校验）。全绿：

| # | 步骤 | 结果 | 与 7a 对比 |
| --- | --- | --- | --- |
| 1 | `pytest tests/ -q` | **482 passed** | 不变（本轮判据都在 node 侧） |
| 2 | `node --test tests/*.js` | **85 passed / 0 failed** | 77 → 85（+8：`test_phase7b_contract.js`） |
| 3 | schema 校验 | 32 OK / 0 FAIL | 不变 |
| 4 | 敏感扫描 | 252 文件，passed | 249 → 252（+3：脚本 / 契约测试 / 公开范围清单） |
| 5 | vercel 死路由 | 44 条重写 / 38 条 API 重写，**dead = 0** | 不变（wf03 三条仍在，逐条探过） |
| 6 | `git diff --check HEAD` | clean | 不变 |
| 7 | 双方言 DDL | 15 passed | 不变 |
| 8 | 真实 HTTP 冒烟 | 70 / 70 | 不变 |
| 9 | 发布镜像不变量 | 30 个非 md 文件逐字节相同 | 不变（本轮动的 md 不在镜像范围内） |
| 10 | 活文档路径 | 全部可解析 | 不变 |
| 11 | 前端写死的 API 路径 | 22 个全部命中重写源 | 不变 |
| 12 | `.env.example` 双向一致 | 29 个变量 | 不变 |
| 13 | 公开范围（**新增**） | **16 份 md 与清单一致**，exit 0 | — |

**口径**：第 8 项冒烟数量不变是预期（零路由改动）；第 1 项 pytest 数字不变同样是预期。

---

## 6. 遗留与口径

### 6.1 Phase 7 还剩两段

| 段 | 内容 | 规模（实测） |
| --- | --- | --- |
| **7c** | `api/index.py` 拆分 | **1621 行**（非文档所说的 3000+，见 7a §5 勘误） |
| **7d** | `tools/` → `domain/` + `providers/` 归并 | `tools/` **6252 行** / 20+ 模块，全部 import 需重写 |

`dependency-map.md`「Phase 5 验收」第 4 条写明 `tools/` 的"保留期不超过两个 Phase"，
**现已到期**，7d 不能再往后推。

### 6.2 本轮明确不动的

- **`public/*.md` 一份没撤** —— 实测无泄露，且它们是赛事提交物。撤出公网现在是**一步**的事：
  删文件 + 改清单。**要不要撤是产品决定，7b 只把"当前是什么"变成可判的。**
- **`/api/wf03/*` 一行没删、也没改** —— 保留决议，判据锁住。
- **`docs/design/` 历史设计文档未归并** —— `architecture.md` 顶部标为"已过期，Phase 7 归并"，
  属 7b/7d 的收尾，本轮没做。
- **不改写历史报告** —— 沿用既定口径。

### 6.3 可复用的三条

1. **删任何东西之前，先枚举"谁在用"。** 7b 差点把一份公开能力声明（WF-03）当死代码删掉，
   因为在 6b-1 的推理里"消费方"被默认等价于"浏览器"。**观察面窄于语义面**这个错误，
   7a 的表现是判错文案，7b 的表现是删掉活接口 —— 后者代价更大。
2. **一个集合要能被判，先要有一个对象。** 6a 与 6b-1 写"属产品/隐私决策"并不算推诿：
   当时确实没有"当前公开集合"这个对象。**造对象（清单）比下结论（撤哪份）更该先做** ——
   造好之后，下结论变成一行 diff。
3. **判据会抓出正文的事实错误。** 7b-2 第一次红，错的是我写进 `architecture.md` 的证据指向
   （把 `[CAP-008]` 写成了 `tests/test_api.py`）。判据的价值不只在防回归。

### 6.4 下一步

Phase 7c —— `api/index.py` 拆分（实测 1621 行）。
`D3`（单位 / 职位检索）期限 **2026-10-13** 不变。
