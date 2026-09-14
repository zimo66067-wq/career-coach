# phase3-report.md · Phase 3（Core Flow）

- 日期：2026-09-14
- 阶段目标：打通 **Resume → Evidence → Target Job → Match → APPLY/STRETCH/PASS → Interview**
- 授权：D8 已决策为**方案 A**（诊断只产候选证据，用户确认后才是事实）
- 结论：**Phase 3 完成（后端闭环）**。6 个新服务函数组、11 条新路由、1 条新迁移、1 套新测试。
  **前端工作面（导航/页面）仍属 Phase 6**，因此"用户能在浏览器里走完闭环"尚未成立。

---

## 1. 修改摘要

```
14 files changed, 2044 insertions(+), 71 deletions(-)
```

| 新增 | 作用 |
| --- | --- |
| `services/career_evidence_service.py`（306 行） | 模型产出 → **候选证据**（pending）→ 用户确认；含实质内容与完整性双过滤 |
| `services/target_job_service.py`（542 行） | JD → 要求 → 匹配 → 缺口 → 决策；含 JD 解析过滤与 `blocking` 判定 |
| `repositories/career_profile.py`（53 行） | CareerProfile 持久化（幂等建档案） |
| `tests/test_career_flow.py`（554 行，31 项） | 端到端闭环契约 |
| 迁移 `2026-09-14-phase3-gap-blocking` | `gaps` 增加 `blocking` |

改造：`api/index.py`（+223，11 条路由 + 2 个错误处理器）、`domain/target_job.py`（+81，缺口类型与判定规则）、
`repositories/target_job.py`（+68，幂等重分析所需的删除/更新原语）、`vercel.json`（+20，5 条重写）。

### 路由（11 条）

```
GET    /api/profile
POST   /api/profile/evidence/candidates
POST   /api/profile/evidence/<id>/{confirm,reject,edit}
DELETE /api/profile/evidence/<id>
GET    /api/target-jobs
POST   /api/target-jobs
GET    /api/target-jobs/<id>
GET    /api/target-jobs/<id>/decision
POST   /api/target-jobs/<id>/analyse
DELETE /api/target-jobs/<id>
```

面试接入：`POST /api/wf04/start` 新增可选 `targetJobId`，出题顺序直接来自该岗位的未解决缺口。

---

## 2. 删除内容

本阶段以新增为主。删除的是**两条错误规则**（不是代码）：

1. `gap_from_requirement` 原本拒绝把 `unknown` 变成缺口 → 改为产出 `unverifiable` 缺口（见 §5 缺陷 2）。
2. `expected_decision` 原本只看优先级 → 改为 `P0 且 blocking` 才 PASS（见 §5 缺陷 3）。

`tests/test_api_boundary.py` 里逐字比对整张能力表的断言被替换为"必需能力可用 + 已下线能力不出现"，
否则每加一个能力都要改测试。

---

## 3. 受影响文件

见 §1 表格。需要单独说明的两个：

- `domain/target_job.py`：`GAP_TYPES` 从 `(missing, weak)` 扩为 `(missing, weak, unverifiable)`；
  `expected_decision` 改成 `blocking` 驱动；`CLEARED_GAP_STATUS` 与 `cleared` 语义写入注释。
- `vercel.json`：41 条重写，死路由校验（静态目标存在 + 每条 `_route` 都有处理器）**全部通过**。

---

## 4. D8 方案 A 的实现要点

```
模型产出 → 候选证据（status=pending, user_confirmed=0） → 用户确认 → 可信事实
```

- HTTP 层**不提供任何**直接写 `confirmed` 的入参；`new_evidence` 在域层对
  `resume / interview / application_outcome` 三个来源强制拒绝 `confirmed`。
- `usable_evidence()` 是下游（改写/匹配/面试/求职信）唯一允许读的入口。
- 已确认证据被改正文会**退回 pending**；`confirmedByUser=True` 的语义是"别退回"，
  不是"把 pending 提升为 confirmed"（这一点在实现时被我写反过，测试已锁）。

### 三道内容过滤（缺一不可）

| 过滤 | 挡掉什么 | 实测依据 |
| --- | --- | --- |
| 子项白名单 | `structure` / `ats_readability` 两个子项完全不产证据 | 它们衡量文档形态，引文是「实习经历」「技能清单」 |
| `is_substantive_claim` | 版块标题、过短片段 | 「实习经历」长度 4、无分句标点 |
| `is_complete_span` | 词中间截断的定长窗口 | 规则降级路径给的是 160 字窗口，结尾是「…引入 Redis 缓存实」，下一字是「现」 |

第三道是最关键的一道：只查"是不是子串"会全部通过（窗口确实在原文里），
于是会把同一段**简历抬头**同时标成"技能证据"和"成果证据"。加上"引文在原文中的下一个字符必须是边界"后才挡得住。

**副作用（已知且刻意）**：规则降级路径（未配置模型时）产出 **0 条**候选证据。
与其把简历抬头包装成成果，不如让用户看到"未从材料中抽取出可核验片段"。

---

## 5. 测试结果

```
pytest                     423 passed（本机两次运行 54.7s / 119.9s，波动来自机器负载）
node --test tests/*.js     36 passed / 0 failed
vercel 死路由              broken static = NONE，unhandled _route = NONE（41 条重写）
schema 校验                resume + job 全部 OK
敏感扫描                   246 文件 无发现
git diff --check           干净
public↔docs web 资产       26 个同名文件，0 处内容差异
双方言 DDL                 各 29 张表，无漂移
真实 HTTP 冒烟             37/37（含闭环、错误码、删除级联、已下线路由仍 404）
```

新增测试 **31 项**（`test_career_flow.py`）+ 迁移新增 2 项 + 域模型改写 5 项。

### 测试自查发现并修复的三个真实缺陷

**缺陷 1 · 无缺口时凑不满 3 条依据 → 拒绝给结论**

`_build_citations` 原本只有"要求判定 + 缺口 + 证据盘点"三类。一个只有 1 条要求的 JD 在
**没有缺口**（= APPLY）时只剩 2 条依据，于是 `insufficient_grounds` 422 —— 把"JD 要求少"
误判成"证据不足"。修法：补一条**匹配概览**依据（`岗位共 N 条要求：已覆盖 X、弱命中 Y、缺失 Z、无法判定 W`），
这是真实可核对的事实，不是凑数。

**缺陷 2 · `unknown` 不产缺口 → 完全没核实也输出 APPLY**

匹配结果 `unknown` 表示"材料完全对不上，无法判定"。原实现把它排除在缺口之外，
于是一条关键硬性要求既不产生缺口也不阻断，最终输出 **APPLY**（"关键要求均有已确认证据支撑"）——
而事实是我们**什么都没能核实**。这是最危险的一类错误：假话伪装成结论。

修法：`unknown` → 缺口类型 `unverifiable`。它不是 `blocking`（补材料即可判定），
所以推 **STRETCH**，同时用户在缺口列表里看得到"这条关键要求我们没找到任何对应材料"。

**缺陷 3 · 三份真实 JD 全部输出 PASS → 规则把所有人都劝退**

初版规则是"存在未解决的 P0 缺口即 PASS"。但 P0 = hard 要求，而**弱命中（weak）也是 P0 缺口**，
于是"材料能对上但强度不足"被判成"不可短期解决"。实测三份 fixture JD 全部 PASS，
分布明显不合理 —— 一个只在一种结论上可用的规则等于没有规则。

修法：引入 `blocking`（该缺口是否不可短期解决），按用户原始口径"**不可短期解决的关键硬性 P0 Gap**"实现：

| 情形 | blocking | 结论 |
| --- | --- | --- |
| 学历门槛高于现有（JD 要硕士、简历本科） | 1 | **PASS** |
| 要求证书/资格，简历无任何相关字样 | 1 | **PASS** |
| 硬性要求只是弱命中（可重写） | 0 | STRETCH |
| 关键要求材料对不上（可补材料） | 0 | STRETCH |
| 无未解决 P0/P1 | — | APPLY |

`blocking` 由服务层判定（只有它拿得到要求原文与简历原文）并**存进 `gaps.blocking`**，
因此 APPLY/STRETCH/PASS 完全可以只从库里复现 —— 这条是"关键判断必须 100% 可解释"的落地方式。
学历比较按**级别**而非关键词：`硕士研究生及以上学历` 在本科简历上会被 BM25 判成 weak
（因为简历里有"学历"二字），只看 gap_type 会错判。

**三个分支都必须可达**已写成专门测试（`test_the_rule_reaches_all_three_verdicts`）。
三份真实 fixture JD 现在都是 STRETCH —— 这份简历整体确实是"材料能对上、强度不足"。

---

## 6. 性能结果

Phase 3 新增的都是本地规则计算（BM25 + 字符串），无外部模型调用。实测：

- 单次 `POST /analyse`（13 条要求 + 11 条候选证据落库）：约 0.5–0.9 秒（含 jieba 预热摊销）。
- 全量门禁 54.74 秒（Phase 2 为 52.13 秒；新增 33 项测试）。
- 最慢用例 3.27 秒（账号限流测试，与本次无关）。

未做独立 P95 基准（Phase 16 统一做）。**注意**：`/analyse` 会写库并调用 BM25，
属于"规则型 API"，Phase 16 的 P95 < 800ms 目标需要届时实测确认。

---

## 7. 剩余风险

| # | 风险 | 说明 | 计划 |
| --- | --- | --- | --- |
| 1 | **闭环在界面上不可见** | 11 条新路由没有页面消费；`js/job-upload.js` 仍无宿主；导航仍是 F1/F3/F4/F5 | Phase 6 |
| 2 | 面试"新事实"提取未接线 | 域层 `candidate_evidence()` 已强制 pending 且有测试，但**引擎目前不产出候选事实**，所以没有端到端路径 | Phase 3/4 后续或 Phase 6 |
| 3 | 规则降级路径产 0 条证据 | 未配置模型时用户无法建立证据档案（只有 JD 匹配路径能产）。语义上诚实，体验上是缺口 | 需要产品决策：是否降低门槛或明确提示 |
| 4 | `blocking` 只覆盖学历与证书两类 | 其它类型的"不可短期解决"（如执业年限、语言等级）未识别，会被判成 STRETCH | 观察真实数据后扩展 |
| 5 | `job_upload` 解析质量仍是规则级 | JD 解析靠分行 + 关键词，未接模型；已加过滤但长尾 JD 仍可能误判 | Phase 3 后续接模型解析 |
| 6 | 既有 2 处依赖倒置未修 | `diagnosis_service.py:324`、`interview_service.py:50` | Phase 5 |
| 7 | PostgreSQL 分支未经真机验证 | 双方言 DDL 已静态对齐（各 29 表），但本机只有 SQLite | 上线前 |
| 8 | Coverage 未达标 | 全局仍未到 85/90/75 | Phase 15 |

---

## 8. 口径（不得对外声称的事）

> **当前可以在后端说"能算出 APPLY/STRETCH/PASS"，但不能说"用户能拿到这个结论"。**
> Phase 3 交付的是后端闭环：11 条路由、领域规则、数据表与迁移都已验证，
> 但**没有任何页面消费它们**（Phase 6 才建导航与目标岗位工作区）。
> 因此对外材料中不得出现"上传简历 + 贴 JD 就能得到投递建议"这类描述。

同时继续有效：F5 单位/职位检索仍无入口（D3 期限 2026-10-13），`js/job-upload.js` 仍无宿主页面。

---

## 9. 下一步（Phase 4 前置）

Phase 4（Action Loop：F4 → Gap Action Plan + Application 状态回流）可以直接开始。需要先定一件事：

**D9（建议新增决策点）· 面试中新发现的经历，由谁抽取？**

- **A（推荐）**：面试回答落库后，由**模型在评估轮**顺带抽取候选事实（claim + 引文），
  走 `candidate_evidence()` 落成 pending。用户在档案页批量确认。
  好处：用户不用手抄；坏处：多一次模型调用，且抽取质量取决于提示词。
- **B**：不做自动抽取，只提供"把某轮回答存为候选证据"的按钮。零模型成本，
  但用户需要自己判断哪一轮值得存。

我倾向 A，因为它与 D8 的"批量确认"体验一致；但 A 需要提示词改造 + 成本评估，
属于产品与成本决策，不替你定。

D3（单位检索，期限 10-13）、D5/D6（Phase 7 归档）状态不变。
