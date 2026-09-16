# phase4-report.md · Phase 4（Action Loop）

- 日期：2026-09-16
- 提交：**`e4b7da3`**（17 文件，+2314 / −15）
- 阶段目标：**F4 → Gap Action Plan + Application 状态回流**。
  Phase 3 只回答"我差什么"和"能不能投"，用户拿到结论之后无事可做；Phase 4 补的是闭环的另一半：
  **把缺口翻成今天就能做的一件事，让做完之后发生的事回流成新证据。**
- 授权：D9 已裁决为**方案 A**（面试新事实由模型抽取，落成待确认证据）
- 结论：**Phase 4 完成（后端 Action Loop）**。8 条新路由、1 个新服务模块、1 份新提示词、1 套新测试（34 项）。
  **新建的前端工作面仍属 Phase 6**，因此"用户能在浏览器里做掉一条行动"尚未成立。

> **口径冲突（需要你知道）**：DoD 表把 **#10 Cover Letter 用 Target Job + Evidence** 也标成 Phase 4，
> 但 `phase3-report.md §9` 对 Phase 4 的定义只有"Gap Action Plan + Application 状态回流"。
> 本阶段按后者的范围执行，**#10 未做**（求职信仍只读 F1 诊断，未接目标岗位与已确认证据）。
> 两个文档的口径需要二选一，见 §10。

---

## 1. 修改摘要

```
17 files changed, 2314 insertions(+), 15 deletions(-)   (e4b7da3)
```

| 新增 | 行数 | 作用 |
| --- | --- | --- |
| `services/action_plan_service.py` | 199 | 缺口 → 可执行行动；幂等开单、生命周期、缺口状态联动 |
| `tests/test_action_loop.py` | 786 | 34 项闭环契约（面试抽取 / 行动计划 / 结果回流 / 生产可达性） |
| `scripts/phase4-http-smoke.py` | 295 | 真端口冒烟（57 项，见 §6） |
| `scripts/sensitive-scan.py` | 53 | 与 CI 步骤 6 同口径的敏感信息扫描 |
| `prompts/interview/evidence.md` | 47 | D9=A 抽取提示词（逐字引文铁律 + 空数组降级） |

| 改造 | 净增 | 要点 |
| --- | --- | --- |
| `api/index.py` | +179 | 8 条新路由 + `wf04/end` 接入 D9=A 抽取 + 能力表 |
| `services/career_evidence_service.py` | +196 | `_interview_turns` / `candidates_from_interview` / `persist_records` / `extract_candidates` |
| `services/apply_service.py` | +76 | `record_outcome_feedback` —— 结果 / 状态 / 证据三本账分开算 |
| `repositories/action.py` | +55 | `find_open_for_gap`、`list_with_gap_context`（LEFT JOIN）、`delete_for_target` |
| `vercel.json` | +12 | 3 条重写（共 44 条） |
| `tools/model_router.py` | +6 | 注册 `interview_evidence` 任务（temperature 0.1 / timeout 30s / 降级空数组） |
| `services/target_job_service.py` | +3 | 删除岗位时一并清掉派生行动（见 §7 缺陷 1） |
| `repositories/target_job.py` | +5 | `get_gap`（行动计划需要 `expected_artifact`） |

文档：`docs/phase4-report.md`（278 行，新建）、`docs/product-scope.md`（+91，DoD 表逐行更新 + §13）、
`docs/domain-model.md`（1 行状态：行动闭环与结果回流从 ⏳ 改为 ✅）、`CHANGELOG.md`（+46，3 条）。

### 路由（8 条）

```
GET    /api/actions                       清单（可按 status 过滤，P0 优先）
POST   /api/actions                       开单：targetJobId 批量铺开 / gapId 单条
GET    /api/actions/<id>                  单条（含缺口上下文）
DELETE /api/actions/<id>
POST   /api/actions/<id>/start            todo → doing
POST   /api/actions/<id>/complete         可同时覆盖 artifact → done
POST   /api/actions/<id>/outcome          记录做完之后发生了什么
POST   /api/actions/<id>/drop             放弃（终态，不关闭缺口）
POST   /api/wf07/applications/<id>/outcome   一次结果：推状态 + 反向写 pending 证据
GET    /api/wf07/applications/<id>/outcomes  结果时间线
```

`POST /api/wf04/end` 新增可选 `targetJobId`：结束后**一次性**抽取面试新事实，
返回 `candidateEvidence: {created, skipped, dropped, degraded, ids}`。

---

## 2. 删除内容

本阶段没有删除功能。删掉的是一处**会留下孤儿数据的错误实现**（§7 缺陷 1）和一段
"看起来可行其实拆不动"的测试写法（§7 测试自查）。

---

## 3. D9 方案 A · 面试何时抽取、抽出什么

### 3.1 实现时机的偏离（重要）

D9 原文是"由模型**在评估轮**顺带抽取"。实现挂在 **`wf04/end` 一次性抽取**，理由三条：

1. **成本是 轮数 × 调用**，而候选最终要用户批量确认 —— 逐轮落库只会让确认列表变长。
2. **同一段经历会在多轮里重复出现**，逐轮抽取必然产生重复候选。
3. **结束时才有完整对话**，抽取质量更高（模型看得到上下文）。

这个偏离已写进 `docs/product-scope.md §12.1`，不是实现时临时决定。

### 3.2 两条路径，一个收口

| 路径 | 触发条件 | 行为 | `degraded` |
| --- | --- | --- | --- |
| 模型判断 | 模型可用且返回结构化 `candidates` | **以模型为准**：它说某轮没有事实就不补；引文对不上原文整条丢弃 | `false` |
| 降级兜底 | 无模型 / 调用失败 / 输出不合形 | 逐轮用引擎的 `answer_quote`（"优先含数字的句子，否则最长句"）留档 | `true` |

两条路径都由 `domain.interview.candidate_evidence()` 收口，因此**不可能产出 confirmed**；
落库再经 `is_substantive_claim` + `is_complete_span`（引文必须是回答的**逐字子串**）双过滤。

**降级 ≠ 照单全收，但也 ≠ 什么都不产。** 与简历路径（Phase 3 定下：规则路径产 0 条）刻意不同：
面试的 `answer_quote` 是**用户原话的完整句子**，不是定长截断窗口，所以可以留档；
而简历路径的 160 字窗口会在词中间截断，拿它当成果就是编造。

### 3.3 脱敏这一层差点漏掉

`turn["answer"]` 是用户**原始**输入 —— 引擎的 `_deidentify_answer` 只用于**外发模型**的入参，
不写回 session。所以证据落库前必须自己再 `deidentify()` 一次（`_interview_turns` 里做）。
后果是**期望行为**：含 PII 的引文脱敏后对不上原文，会被 `is_complete_span` 丢弃，该轮不产证据。

---

## 4. Gap Action Plan · 四条设计约束

```
Gap ──开单──▶ Action(todo) ──start──▶ doing ──complete──▶ done ──outcome──▶ 结果
  │                                                                          │
  └── status: open → doing（开单即进入"未解决"集合，Decision 不变）◀──────────┘
```

1. **开单需要可验证的成果物。** `domain.action.open_from_gap()` 要求缺口带 `expected_artifact`，
   否则拒绝。所以"无法验证的待办"进不了清单 —— 服务层不绕过域层。
   缺成果物的缺口**如实报进 `skipped` 并给原因**，不静默丢弃（否则用户以为都开好单了）。
2. **幂等。** 同一缺口只要还有未关闭行动（`todo` / `doing`）就不重复开单。反复运行分析、
   刷新页面、网络重试都不会让清单膨胀。
3. **开单即让缺口进入 `doing`，但仍是"未解决"。** `doing` 在
   `domain.target_job.OPEN_GAP_STATUSES` 里，所以**开单不会让 Decision 变乐观**。
   缺口只有在**重新分析**发现被覆盖时才变 `cleared`。
4. **完成不等于缺口解决。** 行动 `done` 记的是"我做了这件事"，缺口是否补齐要重新分析才知道。
   这个区分是刻意的 —— 否则"打了个勾"就等于"能力补齐了"，那是假的。
   同理 `drop` 不关闭缺口，只是允许**重新开单**（关闭过的行动不算数）。

行动的 `artifact` 是**用户产出物**的说明（"一页含 3 个量化数字的项目说明"），
不是系统生成的文案，因此不进证据库；它带来的新经历要由用户确认后才成证据。

---

## 5. 投递结果回流 · 三本账分开算

`record_outcome_feedback()` 一次调用做三件事，**互相不连坐**：

| 账 | 规则 | 反例（必须是这个行为） |
| --- | --- | --- |
| **结果** | 始终落库 —— 结果发生过就是事实 | 已 `offer` 再补记 `interview` 是倒流，但那条结果仍然留档 |
| **状态** | 推进可能被拒绝；拒绝时保留原状态并如实回报 `statusApplied=false` | 不得静默改写历史状态，也不得因为状态不动就丢掉结果 |
| **证据** | 只能是 `pending`，`source_type=application_outcome` | "被拒 / 拿 offer"都只是**推断**（我缺什么 / 我强在哪），不能直接当事实 |

`no_response` 不改变状态（`requestedStatus` 为 `null`），但同样产出反向证据。
同一结果配同一段备注 → 引文相同 → 证据按 `(source_id, source_quote)` 去重，不重复写；
而**结果记录本身是历史，允许重复**。

---

## 6. 测试结果

```
pytest                     457 passed（138.59s；Phase 3 为 423，+34）
node --test tests/*.js     36 passed / 0 failed
schema 校验                32 个 fixture 全部 OK
敏感扫描                   249 文件 无发现（与 CI 步骤 6 同口径脚本）
vercel 死路由              44 条重写 / 38 条 API 路由，broken = NONE
git diff --check           干净
双方言 DDL                 各 29 张表，无漂移（`actions` / `application_outcomes` 双方言均在）
真实 HTTP 冒烟             57/57（真进程 + 真端口，含健康、已下线路由 404、预检、同意门、级联删除）
分层静态校验               domain 层 0 处越层 import；新增 service 不 import flask/api
```

新增测试 **34 项**（`tests/test_action_loop.py`），分组：

| 组 | 项数 | 关键断言 |
| --- | --- | --- |
| D9=A 面试抽取 | 9 | 只产 pending；无 `targetJobId` 不抽；重复结束不重复；模型改写引文整条丢弃；**模型说"没有"就等于没有**；抽取失败不影响面试结束；低 ASR 轮次不当证据源 |
| Gap Action Plan | 13 | 幂等；开单后缺口仍属未解决且 Decision 不变；生命周期；未完成不给结果；drop 不关缺口且可重开；缺成果物如实报 `skipped`；重新分析不重开；归属隔离；**删岗位连带删行动** |
| 结果回流 | 7 | 结果 / 状态 / 证据三本账；倒流被拒但留档；终态后仍留档；`no_response` 不动状态；同结果不重复写证据；未知结果 422；归属隔离 |
| 契约 | 3 | 同意门 428、预检 204、**新接口在生产入口有重写**（只在本地注册 = 线上 404） |

### 6.1 门禁运行说明（Token 纪律）

按既有约定「默认只跑相关测试，全量须说理由」，本次跑了**全量**，理由是：
本阶段改动了 `api/index.py` 的路由分派与 `services/target_job_service.py` 的删除链路，
属于**全局面**改动（路由表、预检白名单、能力表、vercel 重写、迁移缓存），
任何一项出错都会让"某个别的阶段的功能"静默 404 —— 单点测试看不见这类回归。
阶段验收门禁本身也是"发布门禁"的定义。

---

## 7. 自查发现并修复的缺陷

### 缺陷 1 · 删岗位留下孤儿行动（真实缺陷，已修）

`delete_target_job` 的契约写得很明确：「用户删除一个目标岗位时，从它派生出来的个人数据必须
一并消失，**不能留下可以反推出岗位与要求的孤儿行**」。原实现删了 requirements / matches /
gaps / decisions，**唯独没删 actions**。

而行动的 `task` / `artifact` 文案正是缺口 `action` / `expected_artifact` 的复制，
也就是**被改写过的 JD 要求**。于是：

```
删除岗位 → gaps 消失 → actions 还在（gap_id 指向不存在的行）
         → LEFT JOIN 让整行照常出现在清单里，task/artifact 明晃晃写着原要求
```

`list_with_gap_context` 用 `LEFT JOIN` 的初衷是"缺口没了也别让行动消失"，这个防御是对的；
但它掩盖了**删除链路该清干净**这件事。修法：新增 `action_repo.delete_for_target()`，
在删 `gaps` **之前**调用（行动靠 `gap_id` 认路，顺序反了就再也认不出来），
并补测试 `test_deleting_a_target_job_also_removes_its_actions`。

**这是我这一阶段自己写出来的漏洞 —— 而且是"测试通过、门禁全绿"的那种。**
`LEFT JOIN` 的容错把数据泄漏伪装成了健壮性，只有照删除契约逐条核对派生数据才发现。

### 缺陷 2 · 冒烟脚本把自己挂死（工具缺陷，已修）

第一版 `phase4-http-smoke.py` 把服务子进程的 stdout 接到 `subprocess.PIPE` 又**不去读**。
Werkzeug 每请求一行日志，缓冲区（Windows ~4KB）写满后子进程直接阻塞在 `write` 上，
表现为"某个请求无故 20s 超时"。改用落文件后 57/57 通过。
**定位依据**：超时只发生在第 ~30 个请求之后，且前面全部正常 —— 典型的管道背压特征，
而不是被调用代码变慢。

### 缺陷 3 · 两处测试自身假设错误（不是产品缺陷）

1. 断言 `len(pending) == 抽取条数` —— 实际 `/analyse` 也会从简历抽候选（D8=A），
   于是把简历来源的 7 条算进了面试那一批。改为按 `source_type` 过滤。
2. 断言 `record["source_id"] == "iv_good"` —— 实际是 `session:turn`（`iv_good:1`），
   精确到轮次，正是"同一场面试不同轮各自去重"所需要的。改断言并加注释。

两处都是**测试写错**，产品行为正确；记录下来是因为"改测试让它变绿"和"发现产品错了"
必须分得清。

---

## 8. 性能结果

Phase 4 新增的都是本地计算（SQLite + 状态机），模型只在 `wf04/end` 触发一次且失败不阻塞。

- 全量门禁 138.59s（Phase 3 为 54.74s / 119.9s 两次）。**注意**：本次 138.59s 与 Phase 3 的
  119.9s 属同一量级波动区，增量主要来自新增 34 项测试（每项建独立数据库）。
- `POST /api/actions`（批量铺开 5 条 + 逐条写库）：亚秒级。
- `POST /api/wf04/end` 新增一次模型调用（`timeout: 30s`，失败降级不抛错）；
  无模型环境下是纯本地计算，无额外延迟。

未做独立 P95 基准（Phase 16 统一做）。

---

## 9. 剩余风险

| # | 风险 | 说明 | 计划 |
| --- | --- | --- | --- |
| 1 | **闭环在界面上仍不可见** | 8 条新路由没有页面消费；导航仍是 F1/F3/F4/F5 代号 | Phase 6 |
| 2 | **模型返回不合形时会退回逐轮留档** | 模型答了但 `candidates` 不是数组 → 视为降级。语义上偏保守（宁可多留 pending），但会让确认列表变长。已通过 `degraded` 标记透出给前端 | 观察真实抽取质量后收紧 |
| 3 | 面试抽取质量未在真模型上验证 | 提示词与降级路径有测试，但**没有真实模型输出的样本**（本机无密钥） | 需要一次真模型抽检 |
| 4 | `blocking` 只覆盖学历与证书两类（沿用 Phase 3） | 其它"不可短期解决"（执业年限、语言等级）会被判 STRETCH | 观察真实数据后扩展 |
| 5 | PostgreSQL 分支未经真机验证 | 双方言 DDL 静态对齐（各 29 表），但本机只有 SQLite | 上线前 |
| 6 | 既有 2 处依赖倒置未修 | `diagnosis_service.py:324`、`interview_service.py:50` | Phase 5 |
| 7 | Coverage 未达标 | 全局仍未到 85/90/75 | Phase 15 |
| 8 | 行动清单上限 200 条 | `list_with_gap_context(limit=200)`，超出的行动静默不显示（无分页） | Phase 6 前端做分页时一并处理 |

---

## 10. 口径（不得对外声称的事）

> **当前可以在后端说"能算出该补什么、并追踪做了什么"，但不能说"用户能拿到一份行动计划"。**
> Phase 4 交付的是后端闭环：8 条路由、领域规则与状态机、三本账分离都已验证，
> 但**没有任何页面消费它们**。因此对外材料中不得出现"面试结束后自动生成行动计划"
> "记一次投递结果就能更新档案"这类描述。

继续有效：F5 单位/职位检索仍无入口（D3 期限 2026-10-13）；`js/job-upload.js` 仍无宿主页面；
DoD #10（Cover Letter 接目标岗位与证据）**未做** —— 它的归属需要在下面二选一。

---

## 11. 下一步

**先要一个裁决（口径冲突）**：DoD 表把 #10 Cover Letter 标为 Phase 4，但 `phase3-report §9`
把 Phase 4 定义为 Action Loop。二者必须选一个：

- **A**：承认 Phase 4 = Action Loop（本报告口径），#10 单列为 "Phase 4b" 或并入 Phase 6；
- **B**：Phase 4 尚未关闭，#10 由我在同一阶段内继续做完再结。

**Phase 5（依赖倒置）已可开始**，它不依赖上面这个裁决：把最后 2 处
`services → api` 反向依赖改为依赖注入，并加静态门禁防止回潮。

D3（单位检索，期限 10-13）、D5/D6（Phase 7 归档）状态不变。
