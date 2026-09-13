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
| 7 | 面试语音（`/api/wf04/asr`、`tools/voice_handler.py`、`tools/providers/asr.py`、`public/js/voice.js`） | 链路已断，前端 0 引用 | **删除**（见 §4） |
| 8 | 能力报告 + 雷达图（`wf05/ability`、`radar_adapter`、`public/js/radar.js`） | 雷达图无决策价值 | **重构为 Gap & Action Plan**；Radar 降级为可选可视化 |
| 9 | 七天竞争力情景推演 C7_low / C7_high（0.3 / 0.7 假设） | 预测型，无真实依据 | **删除**（见 §3） |
| 10 | 面经知识库（`knowledge/search`、`knowledge/questions`、`public/pages/kb.html`、`tools/knowledge.py` 333 行、24 条问答） | 通用百科，与个人证据无关 | **拆解**：导航与独立页删除；题库数据下沉为 Interview Engine 内部数据源；问答升级为 Ask My Career Evidence |
| 11 | 求职信（`wf07/cover-letter`、`apply_service.generate_cover_letter`） | Outcome ✅ | **保留并重构**：输入必须含 TargetJob requirements + EvidenceMatch + Career Evidence，且每项事实可映射 Evidence ID |
| 12 | 申请记录（`wf07/applications`、`applications` 表） | Outcome Feedback ✅ | **保留并重构**：并入 Target Job Workspace；状态扩展为 7 态；Outcome 反写 Career Profile |
| 13 | 单位/职位检索（`/api/f5/organizations/*`、7 张新表、`organization_service`、`providers/organization.py`） | 无授权数据源，索引恒空 | **下线**（见 §6） |
| 14 | 账号系统（`auth/register|login|logout|me`、`history`） | 支撑隔离与留存 | **保留**（D2 已决策：**不去手机号**，注册仍要求手机号 + 邮箱）；另新增「进入即强制注册/登录弹窗」要求，见 §10 |
| 15 | 异步任务（`tasks` 路由 + `task_service` + `tools/tasks.py`） | 仅服务 F2 大文件匹配 | **已随 #5 一并删除**（该子系统在删除前只支持 `task_type="f2_match"`，无其它调用方） |
| 16 | 管理接口（`admin/resumes`、`admin/export`） | 运维需要 | **保留**（非用户功能） |
| 17 | 状态样例页 `states.html` | 设计走查用 | **保留为非导航页** |
| 18 | 观察性文档 `public/observability.md` 等 20+ md 在 web 根 | 无用户价值且对外暴露 | **移出 public 根** |

---

## 3. F4 的预测属性：必须删除

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

## 4. 旧语音能力：整条链路已断，代码全留

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

## 5. F2 概念冲突的处置

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

## 9. 与 DoD 的当前位置对照（Phase 0 起点 + D1 后）

> 「现状」列为 Phase 0 审计快照；「差距」列已按 D1 落地结果更新。

| DoD | 现状 | 差距 |
| --- | --- | --- |
| 1 一级导航 ≤4 | 7 → **6** | −2 |
| 2 无用户可见 F1-F5 | 5 个导航项直接用代号 → **4 个** | 仍需全部改名（Phase 6） |
| 3 单位/职位检索不暴露 | 已不在一级导航；API 在线 | 需 feature flag |
| 4 C7 预测删除 | `C7_low/C7_high` 在 API 与页面 | 未删 |
| 5 KB 非独立产品 | KB 是独立一级页 | 未拆 |
| 6 Major Match 不共用 F2 概念 | 两套并存 → **单一 Target Job Analysis** | ✅ **已达成**（D1） |
| 7 Career Evidence 为 source of truth | **不存在** CareerProfile/CareerEvidence 实体 | Phase 2 新建 |
| 8 Target Job 输出 APPLY/STRETCH/PASS | 只有 0-100 分 | Phase 3 |
| 9 每个 Decision ≥3 条 evidence | 不存在 | Phase 3 |
| 10 Cover Letter 用 Target Job + Evidence | 只读 F1 诊断 | Phase 4 |
| 11 Interview 按 Gap 定向 | 按 gap 弱相关，未接 Evidence | Phase 3 |
| 12 Interview 新事实需用户确认 | 无候选证据流 | Phase 2/3 |
| 13 Service 不反向依赖 API | 3 处倒置 → **2 处**（`task_service → api.f2_major` 随 D1 消失） | Phase 5 |
| 14 .env 无重复/废弃 | 4 个重复变量 + 2 个无消费者 | Phase 7 |
| 15 前端只有一套 canonical | public / docs / ui 三份 | Phase 6（D1 已保证三份同步删除、public==docs 逐字节一致） |
| 16-18 Coverage 85/90/75 | Python 79%；JS 未测 | Phase 15 |
| 19 CI 全绿 | ✅ pytest 全绿 + node 38/38 | 已达成 |
| 20 High/Critical 依赖漏洞 = 0 | ✅ pip-audit 无发现 | 已达成 |
| 21 关键 AI 输出有 fallback | 大部分有（模型失败回退规则） | 待逐项核查 |
| 22 删除链路自动化测试 | 部分 → **`tests/test_phase1_deletions.py` 11 项** | ✅ **已达成**（D1） |
| 23 README 与实际 IA 一致 | ❌ README 仍写 F1-F5 + 过期测试数字 | Phase 7 |
| 24 无 dead routes | 2 个 → **0 个**（`/api/f2/*`、`/api/tasks*` 已下线） | ✅ **已达成**（D1） |
| 25 无明显 dead code | 语音链路 + ui/prototype + 4 个推送脚本 + 5 个未用 prompt（→ 专业匹配与任务框架已清除） | Phase 1/7 继续 |

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

### 10.4 D3–D6 状态

| ID | 状态 |
| --- | --- |
| D3 单位/职位 30 天期限起算 | **仍未决策**，阻塞 F5 阶段 2 |
| D4 `applications` 生产数据迁移 | **仍未决策**，阻塞 Phase 2 migration |
| D5 `workflows/` 去留 | **仍未决策** |
| D6 `deliverables/` 归档 | **仍未决策** |

**D3 仍是 F5 阶段 2 的唯一阻塞项**：没有数据授权、Provider、SLA、预算、纠错责任人五项决策，索引就只能保持为空，任何材料都不得声称已有单位库或实时职位覆盖。

---
