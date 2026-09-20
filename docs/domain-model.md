# domain-model.md · Career Coach 领域模型（Phase 2）

- 日期：2026-09-14
- 状态：**已实现**（`domain/` + `repositories/`），尚未接入 HTTP 路由（Phase 3）
- 范围：CareerEvidence / CareerProfile / TargetJob / InterviewSession / Action / Application
- 配套：`docs/architecture.md`（现状清点）、`docs/product-scope.md`（产品裁决）、
  `docs/dependency-map.md`（依赖与缺陷）、`docs/phase1-report.md`（Phase 1 报告）

---

## 1. 为什么要有一层 domain

Phase 1 之前，"什么算合法"这件事散落在三个地方：`api/index.py` 的参数校验、
`services/*.py` 的编排、`tools/*.py` 的纯函数。结果是同一条规则有两个版本，而
"职业事实"没有任何地方定义过 —— 简历诊断的分数、JD 匹配的证据、面试评估的引用块
各说各话，没有一个能被回溯的实体。

Phase 2 把这层抽出来：`domain/` 只回答"什么算合法"，不做任何 I/O；`repositories/`
是唯一拼 SQL 的地方。分层方向：

```
Routes  →  Services  →  Domain  →  Repositories / Providers
```

**反向依赖零容忍**：`domain/` 不 import Flask、不 import `tools.database`、
不 import `services`。这一条让域规则可以在没有数据库、没有网络的情况下被测试
（`tests/test_domain_model.py`，46 项，0.7 秒跑完）。

**Phase 5 起这条规则由门禁强制**（`tests/test_layering.py`，8 项，进 pytest）：
`services/` 不得 import `api.*` 或 Flask（含函数体内），`domain/` 与 `services/` 不得
**传递依赖** Flask（只按模块级 import 计算），`build_model_router` 只允许一处定义且
无人重新绑定。判据本身也有自检（喂假源码证明它会红）。

---

## 2. 实体关系

```
CareerProfile                     长期容器，owner 唯一
├── Evidence                      唯一可信来源（career_evidence）
├── Experience                    evidence_type = experience
├── Skill                         evidence_type = skill
├── Achievement                   evidence_type = achievement
├── Story                         evidence_type = story
└── Preference                    evidence_type = preference

TargetJob                         一个目标岗位
├── JobRequirement                JD 拆出的要求（hard / responsibility / preferred / terminology）
├── EvidenceMatch                 要求 ↔ 证据的四态判定（covered / weak / missing / unknown）
├── Gap                           未满足的要求 → 可执行补强（P0 / P1 / P2）
├── Decision                      APPLY / STRETCH / PASS（至少 3 条依据）
└── Application                   投递记录（7 态）

InterviewSession
├── TargetJob / Gap               出题依据
├── Question                      含类型与优先级来源
├── Answer                        含逐字引文
├── Evaluation                    训练指标（必须标注）
└── NewEvidence                   面试新经历 → **必须经用户确认**

Action                            Gap → Action → Artifact → Outcome
```

**后五个分支不是五张表。** `Profile.buckets()` 是同一批证据按
`evidence_type` 分出的视图。这样"我的经历"永远等于"证据里 experience 那部分"，
不会出现两套互相矛盾的事实。`Profile.summary()` 给出每类的 总数/已确认/待确认。

---

## 3. 三条贯穿全部实体的不变量

### 3.1 任何职业事实都必须能回指来源

`new_evidence()` 要求 `source_quote` 非空；当调用方提供了 `source_text`（来源原文）
时，**引文必须是原文的逐字子串**，否则抛 `quote_not_verbatim`。这与 F1 诊断的
`source_span` 事实锁是同一个口径，`verify_quote()` 可在落库后复查。

`source_type` 是白名单，只有四个值：

| source_type | 含义 | 是否允许直接 confirmed |
| --- | --- | --- |
| `resume` | 从简历抽取 | ❌ 只能 pending |
| `interview` | 面试回答中抽取 | ❌ 只能 pending |
| `application_outcome` | 由投递结果推断 | ❌ 只能 pending |
| `user_input` | 用户本人陈述 | ✅ 允许 |

需要外部定位对象的来源（前三个）**必须带 `source_id`**，否则无法回指，直接
拒绝（`missing_source_id`）。

### 3.2 AI 不能把推测写成已确认事实

这是产品的立身之本，也是零容忍项（DoD #17）。实现上是三处防护：

1. **创建时**：`resume` / `interview` / `application_outcome` 三个来源显式传
   `status="confirmed"` 会被拒绝（`evidence_requires_confirmation`），默认只会
   落成 `pending`。
2. **确认时**：只有 `confirm()` 能把 `pending` 翻成 `confirmed` 并置
   `user_confirmed=1`、写 `confirmed_at`。`confirm()` 是用户动作，不是模型动作。
3. **修改时**：已确认证据的正文被改动会**退回 pending**，除非调用方显式声明
   `confirmed_by_user=True`（即"这次修改就是用户本人做的"）。这防止"确认过的旧
   文案被悄悄替换成新说法"。

`is_usable()` 是唯一判据：`status == confirmed` **且** `user_confirmed == 1`。
改写、匹配、面试、求职信都必须走 `usable_evidence()`，不得直接读全部证据。

### 3.3 关键判断必须可解释（≥3 条依据）

`decide()` 生成一条 Decision 时校验：至少 3 条依据、不得为空串、不得重复。

更重要的是**判定规则透明**：`decide()` 接受 `gaps`，会独立算一遍
`expected_decision()`，与调用方给的结论不一致就直接拒绝（`decision_inconsistent`）。
**不允许手写结论**。

---

## 4. APPLY / STRETCH / PASS 的规则

规则写成可读谓词，不是权重求和。优先级由 `priority_for()` 唯一决定：
`hard → P0`、`responsibility → P1`、`preferred/terminology → P2`。

| Decision | 条件 |
| --- | --- |
| **PASS** | 存在未解决的 **P0 缺口且该缺口 `blocking`** —— 短期无法补齐的关键门槛 |
| **STRETCH** | 其余存在未解决 P0/P1 缺口的情形 |
| **APPLY** | 不存在未解决的 P0/P1 缺口 |

"未解决" = `status ∈ {open, doing}`。`done` / `dropped` / `cleared` 不参与判定。

### 4.1 `blocking` —— 为什么必须有这个字段

`blocking` 表示**该缺口是否不可短期解决**，对应产品口径里的"不可短期解决的关键硬性 P0 Gap"。
先看不用它会怎样（Phase 3 实测到的两次错判）：

- 只看"有 P0 缺口就 PASS"：**弱命中（weak）也是一种 P0 缺口**，于是"材料能对上但强度不足"
  被判成"不可短期解决"。实测三份真实 JD **全部输出 PASS** —— 等于劝所有人都别投。
- 只看 `req_type == hard`（Phase 2 的旧写法）：`gaps` 表不存 `req_type`，取不到就误判。

判定由**服务层**给出（只有它拿得到要求原文与简历原文），存进 `gaps.blocking`，域层只消费。
这样 APPLY/STRETCH/PASS 可以**只从库里的数据复现**，满足"关键判断 100% 可解释"。

只有两种情形算"不可短期解决"：

| 情形 | blocking |
| --- | --- |
| 要求了高于现有学历的门槛（JD 要硕士、简历只有本科） | 1 |
| 要求了证书/资格，而简历里没有任何相关字样 | 1 |
| 硬性要求只是弱命中（改简历即可改善） | 0 |
| 材料完全对不上（补材料即可判定） | 0 |

学历必须比**级别**而不是比关键词：「硕士研究生及以上学历」在一份本科简历上会被 BM25
判成 `weak`（因为简历里有"学历"二字），只看 `gap_type` 依然会错。

`blocking` 只有落在 **P0** 上才推进 PASS —— P2 的证书要求不该让人放弃投递。

### 4.2 `unknown` 必须算缺口

匹配结果 `unknown` 表示"材料完全对不上，无法判定"。它会产出一个
`gap_type='unverifiable'` 的缺口（非 `blocking` → STRETCH）。

**不能把它当作无事发生**：那样一条关键硬性要求就既不产生缺口也不阻断，最终输出 APPLY
（"关键要求均有已确认证据支撑"），而事实是我们什么都没能核实 —— 假话伪装成结论。

### 4.3 至少 3 条依据，而且必须是真事实

`decide()` 要求 ≥3 条互不重复的依据。依据由四类**可核对事实**拼出：要求判定、匹配概览、
缺口、已确认证据盘点。刻意保持四类，否则一个只有 1 条要求的 JD 在"没有缺口"（= APPLY）时
只剩 2 条依据，就会被迫返回 `insufficient_grounds` —— 那是把"JD 要求少"误判成"证据不足"。

> **实现说明（Phase 2 修正）**：初版实现额外做了一层"要求类型过滤"
> （P0 且 `req_type == hard` 才算 PASS）。这是错的 —— `priority_for` 已经把
> `hard` 唯一映射成 `P0`，而缺口记录里不保存 `req_type`，于是"P0 硬性缺口"会被
> 误判成 STRETCH。该过滤已删除，改为 `blocking` 驱动。

---

## 5. 申请 7 态状态机

```
considering → preparing → applied → interview → offer
                                   ↘ rejected
任意状态 → withdrawn
```

- `rejected` / `withdrawn` 是**终态**，不能再迁出。
- 非法迁移抛 `invalid_transition`（例如 `considering → applied`、
  `offer → rejected`、`applied → preparing`）。
- **新建默认是 `preparing`，不是 `applied`。** 原实现默认 `applied` 会凭空断言
  "已经投递"。只有投出去之后才应由用户显式确认。
- 结果（`ApplicationOutcome`）会反向影响 Career Profile：
  `evidence_from_outcome()` 产出一条 `source_type='application_outcome'` 的
  **待确认**证据 —— "被拒说明我缺 X"是推断，不是用户陈述。

结果类型：`applied / interview / offer / rejected / withdrawn / no_response`。
其中 `no_response` 不改变申请状态。

---

## 6. 行动闭环

```
Gap → Reason → Current Evidence → Missing Evidence → Action → Expected Artifact → Retest
```

两条规则保证"闭环"不是空话：

1. `open_from_gap()` 要求缺口带 `expected_artifact`，否则拒绝
   （`artifact_required`）—— 没有可验证成果物的动作不算闭环。
2. `record_outcome()` 只接受 `status == done` **且**带 artifact 的动作，否则拒绝
   （`action_not_done`）—— 避免"什么都没做，但记录了一个结果"。

动作状态：`todo → doing → done`，允许 `todo → done`（当天做掉一件小事是主场景，
强制先标 `doing` 只是多余仪式），允许 `done → doing`（返工），`dropped` 是终态。

---

## 7. 面试出题优先级与训练指标

出题顺序（`domain/interview.py`）：

```
P0 Gap > P1 Gap > 关键证据验证 > 行为问题 > 通用题库
```

`plan_question_order()` 只做排序，不生成文案；已关闭的缺口不出题。

**评分必须标注为训练指标**：`evaluation()` 返回的记录里 `is_training_metric=True`
且带 `notice`（"本轮评分为训练指标……不代表真实招聘结果或录用概率"）。这是产品
口径，不是可选文案。

面试中发现的新经历走 `candidate_evidence()`，它的 `source_type='interview'`，
因此**必然落成 pending**，且 `quote` 必须是回答原文的逐字子串。

---

## 8. 数据表（Phase 2 新增 10 张，库内共 30 张）

SQLite 与 PostgreSQL 两份 DDL 同步维护（`repositories/database.py`）；`schema_migrations`
由 `repositories/migrations.py` 建，其余 9 张在 DDL 里。

| 表 | 用途 |
| --- | --- |
| `schema_migrations` | 迁移版本记录 |
| `career_profiles` | owner 唯一的职业档案容器 |
| `career_evidence` | 证据（唯一可信来源） |
| `target_jobs` | 目标岗位 |
| `job_requirements` | JD 拆出的要求（保留 source_span） |
| `evidence_matches` | 要求 ↔ 证据四态判定 |
| `gaps` | 缺口（P0/P1/P2 + 行动四段 + `blocking`） |
| `target_job_decisions` | Decision 与其依据（JSON） |
| `actions` | 行动闭环 |
| `application_outcomes` | 投递结果 |

另：`applications` 增加 `target_job_id`（列补齐走迁移，见下）。

---

## 9. 迁移（D4：已授权迁移生产数据）

`repositories/migrations.py` 提供最小可用的版本化迁移：

| 版本 | 内容 |
| --- | --- |
| `2026-09-13-phase2-application-status` | `applications` 补 `target_job_id`；历史 `status` 规范到 7 态 |
| `2026-09-13-phase2-career-profiles` | 为历史上出现过的 owner_key 补建 CareerProfile |
| `2026-09-14-phase3-gap-blocking` | `gaps` 补 `blocking`（老行默认 0，不阻断；重新分析会刷新） |

性质：

- **幂等**：重复执行不改变结果；`force=True` 可人工重跑，且不会重复记版本。
- **冷启动执行一次**，失败不阻断服务（新表已由 DDL 建好），但会在 `/api/health`
  的 `migrations` 字段里如实上报 `ok / applied / expected / error`。
- 健康检查**先补跑未应用的迁移再上报**，避免"换了数据库却继续报 ok"。
- 未知历史状态值兜底为最保守的 `applied`，并在报告里记入 `unknown_values`，
  不猜测。

> **刻意不做的事**：不从既有 `diagnoses` 反向生成证据。诊断的 `source_spans`
> 引文多为"实习经历"这类小节标题，把它变成"职业事实"会直接污染唯一可信源。
> 证据必须由用户确认后进入，迁移不代替用户做这件事。这条有专门测试
> （`test_migration_does_not_turn_a_historical_diagnosis_into_evidence`）。

---

## 10. 测试

| 文件 | 项数 | 覆盖 |
| --- | --- | --- |
| `tests/test_domain_model.py` | 49 | 三条不变量、Decision 规则与 `blocking`、状态机、行动闭环、出题优先级 |
| `tests/test_migrations.py` | 15 | 新库冷启动、幂等、**真实老库**（旧 applications 无新列 + 脏状态；旧 gaps 无 blocking）、档案回填不造证据、health 自愈与如实上报 |
| `tests/test_career_flow.py` | 31 | 端到端闭环（HTTP 层）：候选证据、解析过滤、三种结论、归属隔离、删除级联、面试定向出题 |
| `tests/test_layering.py` | 8 | **分层门禁**（Phase 5）：跨层 import（含函数体内）、传递 Flask 依赖、`build_model_router` 单一归属地、判据自检 |

迁移测试不是拿新库跑一遍就完事：它用手写的旧 DDL 建**真的缺列、且枚举值是脏数据**的库，
再断言迁移结果。

---

## 11. 接线进度

| 能力 | 状态 |
| --- | --- |
| CareerProfile 读写（`/api/profile`） | ✅ Phase 3 |
| TargetJob 全链路（JD → Requirements → EvidenceMatch → Gap → Decision） | ✅ Phase 3 |
| 面试按缺口定向出题（`targetJobId` → `questionPlan`） | ✅ Phase 3 |
| 面试**新事实自动抽取** | ✅ Phase 4（D9=方案 A）：`wf04/end` 一次性抽取，域层 `candidate_evidence()` 强制只产 pending |
| 行动闭环与结果回流 | ✅ Phase 4 完成（2026-09-16） |
| 求职信接地（Target Job + 已确认证据） | ✅ Phase 4b 完成（2026-09-17，后端）；前端 F5 尚未传 `targetJobId` |
| 前端消费（导航 / 目标岗位工作区 / 行动闭环） | ✅ Phase 6b-1 完成（2026-09-17） |

**口径**：后端闭环已可用，**且前端已消费** —— 目标岗位工作区落在
`public/pages/target-job.html` + `public/js/target-job.js`（走 `/api/target-jobs`），
行动闭环落在 `public/pages/action-loop.html` + `public/js/action-loop.js`（走 `/api/actions`）。

原 `public/js/job-upload.js`（**已于 Phase 6b-1 退役**）绑定的是只产匹配分数、产不出 Decision 与 Gap
的旧接口，其替代实现见 `docs/architecture.md` 头部的 Phase 3 更新行。
因此「上传简历 + 贴 JD → 拿到投递建议」这条主路径**现在是成立的** ——
本行在 Phase 6b-1 之前写的"任何页面都没消费、不得对外描述"的禁令随之解除。
