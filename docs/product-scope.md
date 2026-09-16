# product-scope.md · career-coach 收敛式重构产品范围

- 生成日期：2026-09-13
- 范围：Phase 0 只读审计产物，**未修改任何业务代码**
- 基线 commit：`44986ac1159a0db53c8740f437a87ef675855a20`（`main`）
- 配套文档：`docs/architecture.md`、`docs/dependency-map.md`
- 目标形态：**「证据驱动的 AI 求职教练」**，闭环
  `Career Evidence → Target Job → Gap Analysis → Interview Practice → Action → Outcome → Career Evidence 更新`

---

## 1. 当前用户可见信息架构（实测）

`public/index.html` 与所有页面的侧边栏导航**审计时**实测为 **7 项，其中 5 项直接用内部代号命名**；D1 已移除 F2 一项，现为 **6 项、4 项带代号**（完整 IA 重构见 Phase 6）：

```
首页 | F1 简历诊断 | F3 模拟面试 | F4 能力报告 | F5 投递 | 面经知识库
```

| 代号 | 页面 | 行数 | 用户看到的名称 | D1 后 |
| --- | --- | --- | --- | --- |
| — | `public/index.html` | 127 | 首页 | 保留 |
| F1 | `public/pages/f1-resume.html` | 235 | F1 简历诊断 | 保留 |
| ~~F2~~ | ~~`public/pages/f2-match.html`~~ | 214 | ~~F2 岗位匹配~~ | **已删除** |
| F3 | `public/pages/f3-interview.html` | 296 | F3 模拟面试 | 保留 |
| F4 | `public/pages/f4-report.html` | 483 | F4 能力报告 | 保留（行程节点改为不可点击） |
| F5 | `public/pages/f5-apply.html` | 138 | F5 投递 | 保留 |
| KB | `public/pages/kb.html` | 105 | 面经知识库 | 保留 |
| — | `public/pages/states.html` | 116 | （状态样例页，非业务） | 保留 |

- **6 项 > DoD 要求的 ≤4**（D1 净减 1）。
- **F1/F3/F4/F5 仍直接出现在用户导航里**，违反 DoD #2，Phase 6 统一改名。
- KB 是独立一级产品页，违反 DoD #5。

### 1.1 首屏到第一个决策的路径（实测判断）

首页 → F1 上传简历 → 诊断；再到匹配需要「填 JD → 匹配」（专业导向入口已于 D1 移除）。**没有**任何一步产出 `APPLY / STRETCH / PASS`，所以「3 分钟内获得第一个 Target Job Decision」当前**不可能达成**。

---

## 2. 功能清单与价值裁决

判据（来自工作纪律）：*它是否直接提高 Target Job Decision、Evidence Quality、Interview Performance 或 Outcome Feedback？* 答案不是明确 Yes 的，一律不保留。

| # | 已上线功能 | 判据 | 裁决 |
| --- | --- | --- | --- |
| 1 | 简历解析 + PII 脱敏（`wf01/upload`、`deidentify`、`extract_text`、`upload_security`） | Evidence Quality ✅ | **保留并强化** |
| 2 | 简历诊断 5 维打分（`wf02/diagnose` + `rescore.calc_R`） | 部分：分数本身无决策价值，Evidence Inventory 有价值 | **重构**：去掉「为给分而给分」，输出 Evidence Inventory / Missing / Weak Claims / Structural Problems / Rewrite Candidates |
| 3 | 简历改写（`wf02/optimize`、`wf02/apply-rewrite`、`optimizer.py`） | Evidence Quality ✅ | **保留**，补 Target-Job-Aware 模式 |
| 4 | JD 匹配四态（`wf03/jd`、`wf03/match`、`match_service`） | Target Job Decision ✅ | **保留**，升级为 Target Job Analysis + APPLY/STRETCH/PASS |
| 5 | 专业→职业匹配 F2（`f2/match`、`f2/majors/*`、`f2/intent`、`api/f2_major.py` 703 行、`data/f2/*.json` 175 KB） | 与 #4 概念冲突；占用一级导航 | **已整块删除**（D1，2026-09-13，见 §10） |
| 6 | 文字模拟面试（`wf04/start|answer|end|stream`） | Interview Performance ✅ | **保留**，改为按 Gap 定向出题 |
| 7 | 面试语音（`/api/wf04/asr`、`tools/voice_handler.py`、`tools/providers/asr.py`、`public/js/voice.js`） | 链路已断，前端 0 引用 | ✅ **已整条删除**（2026-09-13，见 §4） |
| 8 | 能力报告 + 雷达图（`wf05/ability`、`radar_adapter`、`public/js/radar.js`） | 雷达图无决策价值 | 预测部分 ✅ **已删除**；Radar 已降为可选可视化（只画当前快照）；**Gap & Action Plan 重构留 Phase 4** |
| 9 | 七天竞争力情景推演 C7_low / C7_high（0.3 / 0.7 假设） | 预测型，无真实依据 | ✅ **已彻底删除**（2026-09-13，见 §3） |
| 10 | 面经知识库（`knowledge/search`、`knowledge/questions`、`public/pages/kb.html`、`tools/knowledge.py` 333 行、24 条问答） | 通用百科，与个人证据无关 | 导航/独立页/API ✅ **已删除**；`tools/knowledge.py` 保留为内部题库（待 Phase 3 接线）；**Ask My Career Evidence 留 Phase 3/4** |
| 11 | 求职信（`wf07/cover-letter`、`apply_service.generate_cover_letter`） | Outcome ✅ | **保留并重构**：输入必须含 TargetJob requirements + EvidenceMatch + Career Evidence，且每项事实可映射 Evidence ID |
| 12 | 申请记录（`wf07/applications`、`applications` 表） | Outcome Feedback ✅ | **保留并重构**：并入 Target Job Workspace；状态扩展为 7 态；Outcome 反写 Career Profile |
| 13 | 单位/职位检索（`/api/f5/organizations/*`、7 张新表、`organization_service`、`providers/organization.py`） | 无授权数据源，索引恒空 | ✅ **已不暴露**：首页/导航/用户入口均无入口（实测导航 5 项无此项）；API 保留为显式降级状态；**表与 provider 的存废取决于 D3**（见 §6） |
| 14 | 账号系统（`auth/register|login|logout|me`、`history`） | 支撑隔离与留存 | **保留**（D2 已决策：**不去手机号**，注册仍要求手机号 + 邮箱）；另新增「进入即强制注册/登录弹窗」要求，见 §10 |
| 15 | 异步任务（`tasks` 路由 + `task_service` + `tools/tasks.py`） | 仅服务 F2 大文件匹配 | **已随 #5 一并删除**（该子系统在删除前只支持 `task_type="f2_match"`，无其它调用方） |
| 16 | 管理接口（`admin/resumes`、`admin/export`） | 运维需要 | **保留**（非用户功能） |
| 17 | 状态样例页 `states.html` | 设计走查用 | **保留为非导航页** |
| 18 | 观察性文档 `public/observability.md` 等 20+ md 在 web 根 | 无用户价值且对外暴露 | **移出 public 根** |

---

## 3. F4 的预测属性：必须删除 —— ✅ 已于 2026-09-13 执行

`tools/rescore.py` 计算并对外返回：

- `C7_low` / `C7_high` —— 基于固定 **0.30 / 0.70** 假设参数
- 前端 `f4-report.html` 与 `radar.js` 展示「七天情景推演区间 low ~ high」
- `README.md:32` 仍写着「不得称『预测』」——只是换了措辞，**预测能力本身还在**

裁决：

| 动作 | 对象 |
| --- | --- |
| **删除** | `C7_low`、`C7_high` 的对外返回与展示；`0.3 / 0.7` 假设参数；「七天后竞争力达到 XX」类文案 |
| **保留** | `C0` 与六维分作为**当前证据快照**，但必须标注「不代表就业概率」 |
| **重构为** | `Gap & Action Plan`：`Gap → Reason → Current Evidence → Missing Evidence → Action → Expected Artifact → Retest` |
| **降级** | Radar 从一级功能改为可选 Visualization Component |

影响面：`tools/rescore.py`、`tools/radar_adapter.py`、`services/interview_service.py`（`build_ability_profile`）、`api/index.py`（`wf05/ability` 响应含 `C7_low`/`C7_high`）、`public/pages/f4-report.html`、`public/js/radar.js`、`contracts/ability-profile.schema.json`、以及 6 个引用 `C7_low/C7_high` 的测试文件。

---

## 4. 旧语音能力：整条链路已断，代码全留 —— ✅ 已于 2026-09-13 整条删除

证据（全部实测）：

| 资产 | 规模 | 证据 |
| --- | --- | --- |
| `public/js/voice.js` | 318 行 | **无任何页面 `<script>` 引用**（已逐页核对 8 个页面） |
| `tools/voice_handler.py` | 398 行 | 生产代码 **0 引用**；仅被 `tests/test_new_tools.py`、`tests/test_voice_browser.py` import |
| `tools/providers/asr.py` | 113 行 | 仅服务 `/api/wf04/asr` 这个死路由 |
| `/api/wf04/asr` | 路由 | `public/` 与 `ui/` 全树 0 处引用 |
| `ASR_API_URL` / `TTS_API_URL` / `BAIDU_SPEECH_TOKEN` | 3 个 env | 仅上述两个模块消费 |
| `scripts/p0-04-voice-validation.py` | 216 行 | 语音验证脚本 |
| `public/voice-test-checklist.md` | 251 行 | 且**公网可读** |
| 语音相关测试 | 约 5 个文件 | 为死代码保活 |

即：前端早就不走语音（`voice.js` 用的是浏览器 Web Speech API，且该文件无人加载），后端语音入口从没被前端调用。**这是一整块已死功能，占着代码、配置、脚本、文档、测试。**

裁决：全部删除（Phase 1），含死路由、两个模块、3 个 env、脚本、清单文档、只服务它们的测试。

---

## 5. F2 概念冲突的处置 —— ✅ D1 已整块删除

**冲突事实**：`/api/wf03/match`（JD 四态匹配）与 `/api/f2/match`（专业画像 Mode A/B + `LEVEL_SCORE` 强/较强/较弱/弱）**共用「F2」这个名字**，但语义、输入、输出、权重全不同。代码层有两套独立实现（见 `dependency-map.md` §3.4）。

裁决：

1. **主产品只保留一个概念：Target Job Analysis**（`wf03` 血脉），输出 Requirements / Evidence Matches / Missing Gaps / Weak Gaps / P0-P1-P2 / **APPLY-STRETCH-PASS**。
2. **专业→职业匹配撤出一级导航**，不得再叫 F2，不得与 JD 匹配并列。
3. 保留形态：`Career Profile onboarding` 里的 **Optional Career Exploration**（一次性的「我还能投什么方向」探索），复用现有 `data/f2/*.json` 与 `search_majors`，但不占主导航、不进入主闭环。
4. 若 30 天内无真实使用证据 → 连同 `api/f2_major.py`、`data/f2/*.json`、`f2/*` 路由、`f2-major.js/js/css`、相关测试一并删除。

**决策点 D1 —— 已决策（2026-09-13）：整块删除。** 产品负责人确认不保留 Optional Career Exploration；`api/f2_major.py`、`data/f2/*.json`、`f2/*` 路由、`f2-major.{js,css}`、相关测试与异步任务框架全部下线。详见 §10。

---

## 6. 单位/职位检索：立即下线

事实：**没有任何获得终端展示授权的 Organization/Job Provider**；索引恒空（生产实测 `index` 七个计数全 0，`configured:false`）。已于 2026-09-13 上线的只是框架。

裁决：

| 立即（Phase 1） | 从首页、主导航、任何用户入口移除 | 当前主导航本就没有它，需确保不被加回；`f5-apply.html` 内的状态区可保留但不再扩写 |
| 短期 | API 用 feature flag 封存（默认关闭） | 保留 7 张表与 provider 契约，不动数据 |
| 30 天内若仍无授权/Provider/SLA/预算/更新策略 | 删除 UI、routes、provider、表、测试、docs | 对应 5 项业务决策（见 §8） |

**禁止**因为「代码已经写了」而保留产品功能。

---

## 7. 目标信息架构（≤4 个一级工作区）

| # | 一级工作区 | 承载原功能 | 用户看到的动作 |
| --- | --- | --- | --- |
| 1 | **Career Evidence** | F1 简历解析/诊断/Evidence 化 + rewrite +（可选）Career Exploration | 「上传简历 → 确认我的事实」 |
| 2 | **Target Job** | F2 降级 + F5 投递 → Target Job Workspace（含 Cover Letter、Application、Outcome） | 「分析这个岗位，能不能投」 |
| 3 | **Interview Practice** | F3（按 Gap 定向）+ Question Bank（内部数据源） | 「按缺口练面试」 |
| 4 | **Action Loop** | F4 重构为 Gap & Action Plan + Retest | 「补齐证据，然后复测」 |

配套：

- `Ask My Career Evidence`：替代原 KB 问答，只允许基于 Career Evidence / Target Job / Interview History 回答。
- Radar 与 `states.html` 不进导航。
- 所有 Empty / Loading / Error / Fallback / Disabled 状态必须存在；禁用功能不得以「Coming Soon」长期占位。

### 领域模型（Phase 2 目标）

```
CareerProfile        TargetJob                InterviewSession        Action
├── Evidence         ├── JobRequirement       ├── TargetJob           ├── Gap
├── Experience       ├── EvidenceMatch        ├── Gap                 ├── Task
├── Skill            ├── Gap                  ├── Question            ├── Artifact
├── Achievement      ├── Decision             ├── Answer              └── Outcome
├── Story            └── Application          ├── Evaluation
└── Preference                                └── NewEvidence
```

`CareerEvidence` 必备字段（DoD #7）：

`id / type / claim / source_type / source_id / source_quote / confidence / user_confirmed / created_at / updated_at`

来源白名单：`resume | interview | user_input | application_outcome`。
**AI 新发现必须 `pending → 用户确认 → confirmed`，禁止直接写入 confirmed。**

---

## 8. 需要产品负责人决策的点（阻塞后续 Phase）

| ID | 决策 | 影响 |
| --- | --- | --- |
| **D1** | 专业→职业匹配：保留为 Optional Career Exploration，还是整块删除？ | ✅ **已决策：整块删除**（2026-09-13 已执行，见 §10.1） |
| **D2** | 账号：是否接受「email + password，手机号移除」？ | ✅ **已决策：不去手机号**，注册保持手机号 + 邮箱（见 §10.2） |
| **D7** | 进入即强制注册/登录（弹窗门禁）如何落地？ | ✅ **已要求，待 Phase 6 实现**（见 §10.3） |
| **D3** | 单位/职位检索：30 天期限从哪天起算？期间是否有任何数据授权在谈？ | 决定是封存还是直接删除 |
| **D4** | `applications` 现有生产数据是否允许迁移到新 7 态模型？ | 决定 migration 写法 |
| **D5** | 组织级问题：`workflows/`（1519 行 DuMate 文档）是否还有跨团队用途？ | 决定删除还是搬到 `docs/dumate/` |
| **D6** | `deliverables/`(53 文件) 与 `handoffs/`(6 文件) 属交付存档，是否随 Phase 7 归档出仓库？ | 影响仓库体积 |

---

## 9. 与 DoD 的当前位置对照（Phase 0 起点 → Phase 1 完成）

> 「现状」列为 Phase 0 审计快照；「差距」列已按 D1 落地结果更新。

| DoD | 现状 | 差距 |
| --- | --- | --- |
| 1 一级导航 ≤4 | 7 → **5** | −1（Phase 6 再做 IA 重构） |
| 2 无用户可见 F1-F5 | 5 个导航项直接用代号 → **4 个** | 仍需全部改名（Phase 6） |
| 3 单位/职位检索不暴露 | ✅ 首页/导航/用户入口均无入口（导航实测 5 项无此项）；API 保留为显式降级 | 剩余：表与 provider 存废取决于 D3 |
| 4 C7 预测删除 | ✅ **已彻底删除**（rescore / wf05 响应 / schema / scoring.md / radar.js / f4-report.html） | ✅ **已达成**（Phase 1） |
| 5 KB 非独立产品 | ✅ 导航/页面/API 均删除；题库下沉为内部数据源 | ✅ **已达成**（接线留 Phase 3） |
| 6 Major Match 不共用 F2 概念 | 两套并存 → **单一 Target Job Analysis** | ✅ **已达成**（D1） |
| 7 Career Evidence 为 source of truth | ✅ Phase 2 建实体；**Phase 3 已接到 HTTP 且只读已确认证据**（`usable_evidence()`） | ✅ **已达成**（Phase 3） |
| 8 Target Job 输出 APPLY/STRETCH/PASS | ✅ Phase 3：`blocking` 驱动，三个分支均有测试（`test_the_rule_reaches_all_three_verdicts`） | ✅ **已达成**（Phase 3，后端） |
| 9 每个 Decision ≥3 条 evidence | ✅ Phase 3：四类可核对依据（要求判定 / 匹配概览 / 缺口 / 证据盘点），不足即拒判 | ✅ **已达成**（Phase 3） |
| 10 Cover Letter 用 Target Job + Evidence | 仍只读 F1 诊断 | ⏳ **未做**。DoD 表把它标为 Phase 4，但 `phase3-report §9` 对 Phase 4 的定义是 Action Loop，两者口径冲突（见 §13.4）。待裁决：Phase 4b 或并入 Phase 6 |
| 11 Interview 按 Gap 定向 | ✅ Phase 3：`targetJobId` → 缺口按 P0→P1→P2 排序出题，返回 `questionPlan` | ✅ **已达成**（Phase 3，后端） |
| 12 Interview 新事实需用户确认 | ✅ **Phase 4 端到端打通**：D9=A 落地，`wf04/end` 一次性抽取；模型路径与降级路径都由 `candidate_evidence()` 收口，只产 pending（9 项测试锁死） | ✅ **已达成**（Phase 4） |
| 13 Service 不反向依赖 API | 3 处倒置 → **2 处**（`task_service → api.f2_major` 随 D1 消失）；Phase 3 / Phase 4 新增代码均无新倒置（静态校验：domain 层 0 处越层 import） | Phase 5 |
| 14 .env 无重复/废弃 | 4 个重复变量 + 2 个无消费者 | Phase 7 |
| 15 前端只有一套 canonical | public / docs / ui 三份 | Phase 6（D1 已保证三份同步删除、public==docs 逐字节一致） |
| 16-18 Coverage 85/90/75 | Python 79%（Phase 0 基线）；JS 未测 | Phase 15（须在 CI 的 Python 3.11 上重测） |
| 19 CI 全绿 | ✅ pytest **457** passed + node 36/36 | 已达成 |
| 20 High/Critical 依赖漏洞 = 0 | ✅ pip-audit 无发现 | 已达成 |
| 21 关键 AI 输出有 fallback | 大部分有（模型失败回退规则）；Phase 3 的规则路径本身即降级实现；**Phase 4 的面试抽取失败不抛错、降级兜底并透出 `degraded`** | 待逐项核查 |
| 22 删除链路自动化测试 | ✅ **`tests/test_phase1_deletions.py` 24 项**；Phase 3 加目标岗位删除级联；**Phase 4 修掉一处真实的孤儿行泄漏**（删岗位未清派生行动，见 `phase4-report §7` 缺陷 1） | ✅ **已达成** |
| 23 README 与实际 IA 一致 | 已修正项目状态、页面数、F4 口径与已删变量 | 命名体系仍用 F1–F5（Phase 6/7 统一） |
| 24 无 dead routes | ✅ **0 个**；Phase 4 新增 3 条重写（共 **44** 条）后仍为 0，并新增**正向**检查（新接口必须在生产入口有重写） | ✅ **已达成** |
| 25 无明显 dead code | 已清除：专业匹配+任务框架、C7、KB 页、语音链路、陈旧测试产物 | 剩余：`ui/prototype` 陈旧分叉、4 个推送脚本、5 个未调用 prompt（Phase 6/7） |

---

## 10. 决策落地记录

### 10.1 D1 · 专业→职业匹配整块删除（已完成）

产品负责人 2026-09-13 裁决：**整块删除**，不做 Optional Career Exploration。删除范围与验收见 `CHANGELOG.md` 同日条目与 `tests/test_phase1_deletions.py`（11 项断言固化：路由 404、文件不存在、`vercel.json` 无残留、`tasks` 表不再创建、镜像仍一致）。

删除后主产品只剩**一套**匹配概念：Target Job Analysis（`wf03` 血脉，`services/match_service.py`）。DoD #6 达成。

**刻意未删**：`js/job-upload.js`（`/api/wf03` JD 解析→确认→匹配的 UI）以及 `data-bridge.js` 的 `submitJD`/`matchJD`。它们属于要保留的 Target Job Analysis。注意 `job-upload.js` 当前**没有任何页面挂载**（实测：全部页面的 `<script>` 标签均未引用），需要在 Phase 3 的目标岗位工作区里重新挂载，而不是删除。

**遗留**：`public/README.md`、`public/redesign-v2-visual.md`、`public/p0-02-automation-alternatives.md` 与 `docs/design/*`、`docs/f2-iteration-1-plan-*.md`、`docs/test-report.md` 等历史文档仍提到 F2 页面。这些是**带日期的历史记录**，不在 Phase 1 改写；Phase 7 统一处理（同时解决 `public/*.md` 对外暴露问题）。

### 10.2 D2 · 账号手机号（已决策，与审计建议相反）

产品负责人裁决：**不去掉手机号**。注册流程保持「手机号 + 邮箱」双字段，`users` 表不做迁移。审计中「简化账号」的建议作废。

### 10.3 D7 · 进入即强制注册/登录（新增要求，待实现）

产品负责人要求：用户点击进入产品时，**强制注册/登录**，以弹窗形式呈现。

当前状态：`account.js` 已有侧边栏登录/注册入口与 `zyLoginBtn`，但**不拦截**首屏浏览（游客可完成 F1 诊断）。本要求属于「门禁」，需在 Phase 6（前端重构）与账号流程一起实现，未在 D1 中改动。

实现时必须同时满足（不得因加门禁而回退既有安全性质）：

- 保留 HttpOnly Session、密码哈希、授权校验、归属隔离、删除链路、限流
- 弹窗必须是可键盘操作的原生对话框（可访问性），有明确 Empty / Error / Disabled 状态
- 门禁不得让任何页面在未登录时出现空白或不可用；未登录时应展示注册/登录弹窗而不是报错
- DoD #18「首次用户到第一个 Target Job Decision ≤3 分钟」是这条门禁的直接约束：注册弹窗必须极短，不得插入多余步骤

### 10.4 决策状态（截至 2026-09-14）

| ID | 状态 | 裁决与影响 |
| --- | --- | --- |
| D1 专业→职业匹配 | ✅ 已决策 | 整块删除，已执行（`fc016c5`） |
| D2 账号手机号 | ✅ 已决策 | **不去掉**，注册保持手机号 + 邮箱，`users` 表不动 |
| D3 单位/职位检索 | ⏸ **暂缓删除，设期限** | 见 §10.5 |
| D4 `applications` 迁移 | ✅ 已决策 | 允许迁移生产数据，已执行（`23f75cf`） |
| D5 `workflows/` 去留 | ✅ 已决策 | **保留原地**，Phase 7 统一归档（见 §10.6） |
| D6 `deliverables/` 归档 | ✅ 已决策 | 同上 |
| D7 进入即强制注册/登录 | ⏳ 待实现 | Phase 6 前端重构时落地（见 §10.3） |
| D8 诊断 → 证据的转换策略 | ✅ 已决策 | **方案 A**，见 §10.7 |

### 10.5 D3 · 单位/职位检索：暂缓删除并设 30 天期限

产品负责人授权后按推荐方案推进：**不在今天删除，但立即进入「封存 + 倒计时」状态。**

理由不是"舍不得代码"，而是原始指令明确给了 30 天窗口，且框架本身现在是**诚实的空状态**
（无入口、API 报 `unconfigured`、索引全 0），不构成虚假宣传。删除时点由期限决定，不由手感决定。

| 项 | 值 |
| --- | --- |
| 封存起始 | 2026-09-13（Phase 1 移出全部用户入口之日） |
| **到期日** | **2026-10-13** |
| 期满条件 | 需同时具备：数据授权、Provider、数据 SLA、数据预算、更新策略 |

**到期若五项仍未具备，则整块删除**：`organization` search UI、`/api/f5/organizations/*` 路由、
`services/organization_service.py`、`tools/providers/organization.py`、7 张索引表、
对应 tests 与 docs。

**当前必须守住的口径**：任何材料都不得声称已有单位库或实时职位覆盖。索引恒空是设计状态，不是缺陷。

### 10.6 D5/D6 · 仓库体积口径

`workflows/`（1519 行、0 引用）与 `deliverables/`（历史证据材料）**保留原地**，Phase 7 统一归档。
本阶段不删，避免在核心闭环尚未打通时扩大改动面。

### 10.7 D8 · 诊断 → 证据的转换策略：方案 A（已采纳）

**诊断只产出候选证据（`status='pending'`），由用户确认后才进入可信事实。**

实现上必须带**实质内容过滤**，否则会把版块标题写成职业事实：

| 来源 | 是否可以成为证据 | 说明 |
| --- | --- | --- |
| JD 匹配命中的**整句**（`covered` / `weak` 的 `evidence`） | ✅ 可以 | 是完整陈述句，天然是职业事实 |
| 诊断 `source_spans` 中的**实质陈述**（如「编写接口文档并推动联调，与前端约定统一的错误码规范」） | ✅ 可以 | 需通过实质过滤 |
| 诊断 `source_spans` 中的**版块标题 / 短片段**（如「实习经历」「技能」） | ❌ 不可以 | 实测合成样本里 `structure` 子项的 span 就是「实习经历」 |

**为什么不是方案 B**：B 让诊断直接落 `confirmed`，等于把"模型抽取"当成"用户陈述"，
与 §3.2 的不变量直接冲突。而 A 与 DoD #18「≤3 分钟到第一个 Decision」不冲突 ——
确认可以批量化（一次列出全部候选，用户勾掉不对的）。

---

---

---

## 11. Phase 1 完成记录（2026-09-13）

Phase 1（Product Deletion）已全部执行完毕，分两个提交：

| 提交 | 内容 | 规模 |
| --- | --- | --- |
| `fc016c5` | D1：专业→职业匹配整块删除（含只服务它的异步任务子系统） | 74 文件，+1158 / −13688 |
| `4367ec5` | C7 预测 / 独立知识库 / 整条语音链路 / 4 条死路由 | 73 文件，+646 / −4447 |

**Phase 1 的 7 项删除目标全部达成**：Organization Search（无入口）、Job Search（无入口）、
C7 Predictions（彻底删除）、KB Navigation（删除）、Major Match 一级入口（删除）、
Voice remnants（删除）、retired routes（删除 + `/assets/*` 修正）。

**门禁**：pytest 全绿、Node 36/36、`vercel.json` dead routes = 0、public↔docs web 资产逐字节一致、
敏感扫描无发现、`git diff --check` 干净、`tests/test_phase1_deletions.py` 24 项契约全过。

**Phase 1 结束时仍无界面的能力**（重要口径，不得宣传）：

- **目标岗位分析**（`/api/wf03/jd` + `/api/wf03/match`）—— 后端与合同完好，但承载它的
  `js/job-upload.js` 当前**没有任何页面挂载**。Phase 1 删掉了旧的专业匹配页，而目标岗位
  工作区要到 Phase 3 才建。**在此之前不得声称「可以匹配 JD」。**

**Phase 2 入口条件已满足**：D4 已决策（允许迁移 `applications` 生产数据到新 7 态模型），
migration 可以落笔。仍需 D5（`workflows/` 去留）、D6（`deliverables/` 归档）决定仓库体积口径，
D3 阻塞 F5 阶段 2。

---

## 12. Phase 3 完成记录（2026-09-14）

Phase 3（Core Flow）后端闭环打通，一个提交 **`a0c055f`**：18 文件，**+2430 / −106**。

**新增能力**：`/api/profile`（含证据 confirm/reject/edit/delete）、`/api/target-jobs`
（CRUD + analyse + decision）、`POST /api/wf04/start` 支持 `targetJobId` 按缺口定向出题。
详见 `docs/phase3-report.md` 与 `CHANGELOG.md` 同日条目。

**门禁**：pytest 423 passed（54.74s）、Node 36/36、schema OK、敏感扫描 246 文件无发现、
`git diff --check` 干净、public↔docs web 资产逐字节一致、双方言 DDL 各 29 表、
vercel 死路由 = 0、真实 HTTP 冒烟 **37/37**。

**DoD 变化**：#7（Evidence 为 source of truth）、#8（APPLY/STRETCH/PASS）、
#9（≥3 条依据）、#11（Interview 按 Gap 定向）四项达成；#12 部分达成。

**Phase 3 结束时仍不可用的东西**（口径）：

- **闭环在界面上不可见** —— 11 条新路由没有任何页面消费，`js/job-upload.js` 仍无宿主。
  对外不得出现"上传简历 + 贴 JD 就能拿到投递建议"这类描述（Phase 6 才成立）。
- 规则降级路径（未配置模型时）产出 **0 条**候选证据（引文是定长窗口，被完整性过滤挡掉）。
  这是刻意选择，但意味着无模型环境下用户建不了证据档案。

### 12.1 D9 · 面试新事实由谁抽取：方案 A（已采纳，2026-09-16）

| 方案 | 做法 | 代价 |
| --- | --- | --- |
| **A ✅ 已采纳** | 模型在评估轮顺带抽取候选事实（claim + 引文），走 `candidate_evidence()` 落 pending | 多一次模型调用；依赖提示词质量 |
| B | 不自动抽取，只给"把某轮回答存为候选证据"的按钮 | 零模型成本；用户需自己判断哪轮值得存 |

域层已强制 `candidate_evidence()` 只产 pending 且有测试，**两种方案都不会破坏 DoD #12**；
差别只在体验与成本。

**产品负责人 2026-09-16 裁决：取方案 A。**

**实现时机的偏离（同一方案内，需明示）**：抽取挂在 `POST /api/wf04/end`（结束面试时**一次性**抽取
全部轮次），而不是逐轮抽取。理由是逐轮抽取的代价与收益不成比例：

- 成本是轮数 × 模型调用，而候选证据最终要被用户**批量确认**，逐轮落库只会让确认列表变长；
- 同一段经历会在多轮里反复出现，逐轮抽取必然产生重复候选，还得再去重；
- 结束时才有完整对话，抽取质量更高（能看到全局，而不是单轮片段）。

`extract_candidates()` 是独立函数，若将来要改逐轮，只需在 `answer_interview` 里加一行调用，
域层与过滤链不需要任何改动。

### 12.2 其余决策点状态

| ID | 状态 |
| --- | --- |
| D3 单位/职位检索 | ⏸ 封存中，**期限 2026-10-13**（见 §10.5） |
| D5 `workflows/` | ✅ 保留原地，Phase 7 归档 |
| D6 `deliverables/` | ✅ 保留原地，Phase 7 归档 |
| D7 进入即强制注册弹窗 | ⏳ Phase 6 实现 |
| D8 诊断 → 证据 | ✅ 方案 A，已在 Phase 3 落地 |
| **D9 面试新事实抽取** | ✅ **方案 A**（2026-09-16 裁决），Phase 4 落地（见 §12.1） |

---

## 13. Phase 4 完成记录（2026-09-16）

Phase 4（Action Loop：Gap Action Plan + Application 状态回流）后端闭环打通，
一个提交 **`<待回填>`**：17 文件，**+2310 / −15**。

**新增能力**：`/api/actions`（清单 / 批量或单条开单 / start / complete / outcome / drop / 删除）、
`/api/wf07/applications/<id>/outcome` 与 `/outcomes`（一次结果同时推进 7 态状态机并反向写
**待确认**证据）、`POST /api/wf04/end` 接入 **D9=A 一次性抽取**。
详见 `docs/phase4-report.md` 与 `CHANGELOG.md` 同日条目。

**门禁**：pytest **457** passed（138.59s）、Node 36/36、schema 32 项 OK、敏感扫描 249 文件无发现、
`git diff --check` 干净、双方言 DDL 各 29 表、vercel 死路由 = 0（44 条重写）、
真实 HTTP 冒烟 **57/57**（真进程 + 真端口）。

**DoD 变化**：#12（Interview 新事实需用户确认）由"部分达成"变为**达成**；
#19（CI 全绿）、#22（删除链路）、#24（无 dead routes）随本阶段数字更新。
**#10（Cover Letter）仍未做**，见 §13.4。

### 13.1 三条不变的领域不变量

| 不变量 | 本阶段的落地 |
| --- | --- |
| 事实必须可回指来源 | 面试候选的引文必须是回答的**逐字子串**（模型改写的整条丢弃）；结果回流证据的引文是用户写的备注 |
| AI 不能写入已确认事实 | D9=A 与结果回流两条新写入路径都只产 `pending`，域层收口 |
| 关键判定可解释 | 开单不改变 Decision；缺口是否解决只由**重新分析**决定 |

### 13.2 "开单 / 完成 / 放弃"都不等于"缺口解决了"

这是本阶段最容易写错、也最容易骗人的一处，已写成三条独立测试：

- **开单** → 缺口 `open → doing`，仍在"未解决"集合内，**Decision 不变**；
- **完成**（行动 `done`）→ 只记"我做了这件事"，缺口状态不动；
- **放弃**（行动 `dropped`）→ 不关闭缺口，仅允许重新开单。
  缺口只有在**重新分析**发现被覆盖时才变 `cleared`。

否则"打了个勾"就等于"能力补齐了"，而那是假的。

### 13.3 结果回流的三本账

**结果始终落库 / 状态推进可能被拒（如实报 `statusApplied=false`）/ 证据只能 pending** ——
三者互不连坐。已投递后补记"被拒"是事实，倒流补记"进入面试"也是事实，但状态机不允许倒流时
**保留原状态并如实回报**，而不是丢掉结果或静默改写历史。

### 13.4 口径冲突（需裁决）

**DoD #10（Cover Letter 用 Target Job + Evidence）在两个文档里归属不同**：

- `§9 DoD 表`：标为 **Phase 4**；
- `phase3-report §9`：Phase 4 = **Action Loop（Gap Action Plan + Application 状态回流）**。

本阶段按后者执行，**#10 未做**（求职信仍只读 F1 诊断）。两个口径需二选一：
**A** 承认 Phase 4 = Action Loop，#10 另立 Phase 4b 或并入 Phase 6；
**B** Phase 4 不关闭，同一阶段内把 #10 做完再结。

**Phase 4 结束时仍不可用的东西**（口径）：8 条新路由没有任何页面消费，
因此对外不得出现"面试结束后自动生成行动计划""记一次投递结果就能更新档案"这类描述（Phase 6 才成立）。
