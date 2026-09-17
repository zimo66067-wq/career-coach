# phase4b-report.md · Phase 4b（DoD #10 · 求职信接地）

- 日期：2026-09-17
- 提交：**`<待回填>`**（<待回填> 文件，<待回填>）
- 阶段目标：**DoD #10 —— 求职信必须接目标岗位（Target Job）与已确认职业证据（Career Evidence），
  且每项事实可映射 Evidence ID。**
- 前置：Phase 4 收尾时留了一处口径冲突（`product-scope.md §13.4`），裁决为**方案 A**：
  承认 Phase 4 = Action Loop，**#10 另立 Phase 4b**。本阶段就是这次裁决的兑现。
- 背景：DoD #10 不是"再写一版提示词"，而是**换掉事实底座**。旧路径读的是 F1 诊断里
  模型抽的 span 引文 —— 那些**不是已确认事实**，只是"模型觉得相关"的简历片段。
  求职信是发给雇主的对外材料，事实底座错了，写得再漂亮也是替用户编经历。
- 结论：**DoD #10 达成（后端口径）**。`/api/wf07/cover-letter` 新增可选 `targetJobId`，
  带它即走接地路径；不带则**字节级保持旧行为**。前端工作面仍属 Phase 6，
  因此"用户能在页面上选一个目标岗位生成求职信"目前**尚不成立**（见 §7 口径）。

---

## 1. 修改摘要

```
4 files changed, 296 insertions(+), 5 deletions(-)   (工作区；tests/ 新文件另计 <待回填>)
```

| 改造 | 净增 | 要点 |
| --- | --- | --- |
| `services/apply_service.py` | +213 | DoD #10 区块：`_letter_context` / `_grounded_prompt` / `_grounded_template` / `_grounded_letter` / `_letter_notice`；`generate_cover_letter` 双路径分派 |
| `api/index.py` | +12 | `wf07/cover-letter` 解析 `targetJobId`（int 校验，坏值 422）并透传 `owner_key` |
| `scripts/phase4-http-smoke.py` | +43 | 真端口冒烟追加 13 项（接地路径 / 未确认证据不进正文 / 会话与岗位两道归属各测一次 / 旧路径未动） |
| `prompts/apply/cover-letter.md` | +33 | 写明 A（接地）/ B（旧）两种输入结构与接地路径的三条硬约束 |

| 新建 | 行数 | 作用 |
| --- | --- | --- |
| `tests/test_cover_letter_grounding.py` | <待回填> | **16 项**契约：只引用已确认证据 / 缺口不得声称 / 模型三道门 / 归属隔离 / 旧路径兼容 |
| `scripts/vercel-dead-routes.py` | 106 | **实证**的死路由检查（见 §5.3，本阶段把 Phase 4 那次没留档的一次性命令固化下来） |

### 1.1 接口契约（唯一一处对外变化）

```
POST /api/wf07/cover-letter
  { session_id, company?, position?, targetJobId? }

  · 不带 targetJobId  → 旧行为不变（读 F1 诊断），新增字段 grounding = "diagnosis"
  · 带   targetJobId  → 接地路径：
      company / position 缺省时从岗位记录取（都没有 → 422 apply_info_required）
      返回新增字段：
        grounding    "target_job+evidence" | "target_job_no_evidence"
        evidence     [{id, claim}]        —— 只含 confirmed，最多 3 条
        requirements [{id, text, priority}] —— 正文回应的要求，P0→P1→P2，最多 5 条
        gaps         [{id, priority}]      —— 未覆盖要求，**只进元数据，不进正文**
        notice       人读提示（用了哪几条证据 / 有几条要求没声称）
```

对旧调用方是完全兼容的：**不传 `targetJobId`，返回体与 Phase 4 完全一致**，
只有 `grounding` 是新增键（用于前端区分两条路，取值 `"diagnosis"`）。

---

## 2. 三条不可让步的规则

接地路径的全部设计都为这三条服务（`services/apply_service.py` 顶部注释同样写明）。

### 规则 1 · 没有已确认证据，就不请模型写

只给岗位要求、不给事实底座，模型一定会替用户编经历 —— 因为它收到的信号是"要匹配这个 JD"。
所以 `_grounded_letter` 里 `build_model_router()` **只在 `evidence` 非空时才调用**：

```python
router = None
if evidence:                        # 事实底座为空 → 连模型都不请
    try:
        router = build_model_router()
    except ApiError:
        router = None
```

没有证据时直接给规则模板，正文里留一个**明确占位**（`（请在正文中补充 1-2 个可量化的项目成果）`），
并在 `notice` 里说清"你还没有确认任何职业证据"。**宁可给框架，不给编造。**

正面证明写成了测试：`test_the_model_is_not_even_asked_when_there_is_no_confirmed_evidence`
（替身路由必须记录到 **0 次调用**），而不是只断言"输出里没有假话"。

### 规则 2 · 未覆盖的要求是"禁止声称"名单，不是写作素材

缺口（`gaps`）只出现在接口元数据里，供界面提示用户"这条要求你还没有证据支撑"。
**它不进正文** —— 正文是给雇主看的，"我在这条上还欠缺"不该出现在求职信里，
但更不能反过来声称具备。测试直接拿 `missing_evidence` 原文去正文里搜，确认搜不到。

### 规则 3 · 正文每段经历都要能回指一条已确认证据

模型路径复用既有的 `_grounded_in_evidence`（四字片段级校验，中文不做分词也能挡住整段虚构）；
过不了就**退回规则模板**，而不是放行一段无法核验的漂亮话。
校验用的引文是 `quote or claim`（引文缺失时退到 claim 本身），避免"有事实但没有引文"时误杀。

---

## 3. 事实底座怎么拼

`_letter_context(target_job_id, owner_key, company, position)` 一次取齐四样东西：

| 取什么 | 从哪取 | 约束 |
| --- | --- | --- |
| 岗位记录 | `target_job_service.get_target_job(id, owner_key)` | **第一步就做归属校验**，非本人直接 404 |
| 要求 | `target_job_service.requirements_of()` | 按 `priority_for(req_type)` 排序（P0→P1→P2），**截断到 5 条** |
| 缺口 | `target_job_repo.list_gaps()`，只留 `OPEN_GAP_STATUSES` | 排序后进元数据，不进正文 |
| 证据 | `career_evidence_service.usable_evidence(owner_key)` | Phase 3 定下的**下游唯一入口** = 只返回 `confirmed`，**截断到 3 条** |

两处截断（5 条要求 / 3 条证据）不是随意定的：200 字的正文塞不下十几条要求，
贪多只会得到"我十分符合"这类空话；证据多于 3 条时，模板会把它们堆成一句长句，可读性反而崩掉。

> **归属校验放在最前面**，是因为后面每一样数据都要用 `owner_key` 去查。先确认"这个岗位是不是你的"，
> 再谈取数，顺序反了就有回显他人数据的口子。冒烟里专门验了这一条（§6）。

---

## 4. 旧路径为什么必须原样保留

`generate_cover_letter` 现在有两个入口，分派点只有一行：

```python
if target_job_id is not None:
    ...
    return _grounded_letter(session_id, context)
# 以下为旧路径，未改动
```

保留而不是替换，有三个具体理由：

1. **旧路径不依赖目标岗位。** 用户可以先诊断简历、直接投一家小公司，不必先在系统里建岗位记录。
   强制两步会把这个场景堵死。
2. **兼容成本极低。** 旧路径的实现、提示词与降级模板一行未改，只多了一个 `grounding: "diagnosis"` 键。
3. **两条路的事实底座质量不同，必须在响应里看得出来。** 前端若把两条路混在一起，
   用户会以为"诊断里抽的片段"和"我确认过的经历"是一回事 —— 而后者才敢写进求职信。
   `grounding` 字段就是给界面区分用的。

---

## 5. 自查发现的问题（都不是产品缺陷）

### 5.1 归属隔离的断言写错了错误码

第一版断言 `error == "not_found"`，实际是 **`target_job_not_found`**（`TargetJobError` 的码）。
这不是产品错：`/api/target-jobs/*` 全套接口用的都是这个码，复用它对前端更友好（一个分支搞定）。
**改测试，不改产品。** 顺带把断言加强为"报错不得回显他人岗位内容"：
另一方请求里刻意填**别的**公司与职位，这样只要响应里出现岗位记录里的公司/职位名，就说明校验失败后仍在回显。

### 5.2 旧路径要的是 F1 诊断，不是面试会话

第一版用 `wf04/start` 建会话就去调求职信，得到 422 `diagnosis_required`。
**产品行为是对的**（旧路径读的就是诊断记录，没有诊断就该 422，`test_phase5.py` 早就锁了这个契约），
问题在我的测试夹具把"会话"当成了"诊断"。修正为 `_legacy_session()`：走
`wf01/upload` → `wf02/diagnose`，与旧路径真实的前置一致。

> 这两处都属于"测试自己假设错了"，与 Phase 4 的缺陷 3 同类。记在这里是为了说明：
> **门禁第一次红灯不一定意味着产品坏了** —— 但也不能反过来假定产品一定是对的，
> 每一处都要落到"产品语义是什么"上再判断改哪边。

### 5.3 死路由判据本身是错的（Phase 4 遗留的一次性命令）

Phase 4 报的"死路由 = 0"是**静态比对**得出的：拿 `_route` 值去比对分派表的
OPTIONS 白名单 + 前缀族。问题是 `history/$1` 这类**参数化重写**能命中 `history/` 前缀，
于是被判为"接上了"—— 这个判据**永远发现不了**"参数化路由只有特定方法才进分支"这类问题。

本阶段改成**实证**：对每条重写逐方法（GET/POST/DELETE/PUT/PATCH）发一次请求，
看它是否落到 `route_api()` 的兜底 `not_found`（兜底 message 固定是"接口不存在。"，
用它把"路由没接上"和"路由接上了、只是这个 id 不存在"区分开）。

过程中确实先得到一条"死路由"：`/api/history/(.*)`。排查后确认是**探针的错**：
`/api/history/<id>` 只接 DELETE，用 GET/POST 探当然落兜底。加上逐方法探测后归零：

```
重写总数 44 / API 重写 38 / 死路由 0
```

判据写进了 `scripts/vercel-dead-routes.py`（Phase 4 那条命令没留档，只留了个数字，
这一轮为它付了一次返工 —— 所以这次固化下来）。

### 5.4 冒烟里"他人借岗位"的期望写错了（两道归属校验）

冒烟第一版用**同一个 session_id** + 另一个 owner 的令牌去打求职信，期望
`target_job_not_found`，实际拿到 `session_not_found`。**产品是对的**：

```
ensure_session_access(session_id)      ← 第一道：会话是不是你的
  → _letter_context() → get_target_job(id, owner_key)   ← 第二道：岗位是不是你的
```

会话归属先于岗位归属，所以"拿别人的 session_id"必然先被第一道拦下（这本身是好事：
连"这个会话存在"都不该透露）。修正为两个检查各测一次：借会话 → `session_not_found`；
自建会话 + 借岗位 → `target_job_not_found`。**两道都测，才算真的验过归属隔离。**

---

## 6. 测试结果

```
pytest                     473 passed（508.70s；Phase 4 为 457，+16）
node --test tests/*.js     36 passed / 0 failed
schema 校验                32 个 fixture 全部 OK
敏感扫描                   252 文件 无发现（与 CI 步骤 6 同口径脚本）
vercel 死路由              44 条重写 / 38 条 API 路由，broken = 0（实证逐方法探测）
git diff --check           干净
双方言 DDL                 test_migrations.py 15 项全绿（各 29 张表，本阶段无 schema 变更）
真实 HTTP 冒烟             70/70（真进程 + 真端口，本阶段追加 13 项）
```

新增测试 **16 项**（`tests/test_cover_letter_grounding.py`），分组：

| 组 | 项数 | 关键断言 |
| --- | --- | --- |
| 只引用已确认证据 | 6 | 正文必须真的用上那条已确认证据；**未确认候选的 claim 与引文一个字都不能进正文**；无已确认证据时报 `target_job_no_evidence`；**连档案行都还没有的新用户也照样出框架**（不许 500）；公司/职位可从岗位兜底；职位缺失才轮到调用方参数 |
| 要求与缺口 | 2 | 要求按 P0→P1→P2 排序且 ≤5 条；缺口原文不出现在正文 |
| 模型三道门 | 3 | 接地输出被采用（且提示词里同时含要求清单与证据清单）；**编造经历的模型输出被拒并退规则**；无已确认证据时模型调用次数为 0 |
| 归属 / 参数 / 旧路径 | 5 | 他人借岗位 404 且不回显他人数据；坏 `targetJobId` 422；旧路径 `grounding=diagnosis` 且不报 `evidence`；旧路径仍要求公司与职位；同意门 428 + 预检 204 |

### 6.1 门禁仍然跑全量的理由

与 Phase 4 相同：本阶段改了 `api/index.py` 的路由入参与 `services/apply_service.py` 的公共函数，
属**全局面**改动。任何一处出错都会让"别的阶段的功能"静默 404 或静默换行为 ——
单点测试看不见这类回归。阶段验收门禁本身就是"发布门禁"的定义。

---

## 7. 口径（不得对外声称的事）

- **求职信接地是后端能力。** 前端 F5 页面（`public/js/f5-apply.js`）当前只提交
  `session_id / company / position`，**不会传 `targetJobId`**；因此本次发布后，
  用户在页面上生成的求职信**仍走旧路径**。"求职信会自动引用你的目标岗位与已确认经历"
  这句话在 Phase 6 接线之前**不得对外说**。
- **`target_job_no_evidence` 是正常状态，不是错误。** 用户没确认过任何证据时，
  系统给的是**带占位的框架**，不是失败。文案不得写成"生成失败"。
- **缺口没有被"补上"。** 本阶段只做"不声称"。缺口是否解决仍只由**重新分析**决定
  （Phase 4 §13.2 的口径不变）。

---

## 8. 剩余风险

1. **前端未接线**（见 §7）：能力已实测可达（冒烟真端口验证），但没有页面入口。
   → Phase 6 排期；届时需同时处理"当前目标岗位"这个上下文在 F5 页面怎么传。
2. **`_grounded_in_evidence` 是四字片段匹配。** 它能挡住整段虚构，但挡不住"把已确认经历
   张冠李戴到别的项目"这类改写。当前靠提示词约束 + 人工确认兜底；若要更硬，需要证据级
   ID 引用（模型输出里带 `[E1]` 标记并校验），属后续增强。
3. **`usable_evidence` 的截断是全量取回后再切 3 条。** 当前证据规模（个人用户）无问题，
   证据量上百后再考虑下推 limit 到仓储层。
4. **`HANDOFF.md` 已经过期。** 它最后更新停在 2026-08-01（G7→G8 阶段），
   "下一唯一任务"仍写着"接通千帆 embedding"，而这轮收敛式重构（Phase 0-4b）完全没有反映进去。
   本阶段**没有擅自重写**这份 132 行的交接文件（历史交接记录不该被顺手覆盖）——
   但下次做跨路径交接前必须先决定它是"废弃"还是"重写"，否则它只会继续误导接手的人。

---

## 9. 下一步

- **Phase 5（依赖倒置）**：清掉剩余 2 处 `service → api` 倒置，把分层静态校验接进 CI。
- **Phase 6（前端工作面）**：F5 接 `targetJobId`，并把"求职信引用了哪些证据"显式呈现给用户
  （这是本阶段刻意留在响应里的 `evidence` / `gaps` / `notice` 三个字段的用途）。
- **D3（单位/职位检索）** 仍封存，期限 **2026-10-13**。
