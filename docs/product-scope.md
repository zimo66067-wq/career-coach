# product-scope.md · career-coach 收敛式重构产品范围

- 生成日期：2026-09-13
- 范围：Phase 0 只读审计产物，**未修改任何业务代码**
- 基线 commit：`44986ac1159a0db53c8740f437a87ef675855a20`（`main`）
- 配套文档：`docs/architecture.md`、`docs/dependency-map.md`
- 目标形态：**「证据驱动的 AI 求职教练」**，闭环
  `Career Evidence → Target Job → Gap Analysis → Interview Practice → Action → Outcome → Career Evidence 更新`

---

## 1. 用户可见信息架构（快照：7 项导航、5 项带代号）

> **已过时（Phase 6b-2，2026-09-17）**：本节是审计当时的信息架构快照，当时 5 项直接以内部代号命名。归属该节的三条结论**已全部落地**：一级导航**收敛到 4 个**工作区（简历证据 / 目标岗位 / 模拟面试 / 行动闭环），**用户可见面（含 URL）不再出现 F 代号**，首页由品牌区进入。下面的实测表与行数不再代表现状，保留作为审计记录。

`public/index.html` 与所有页面的侧边栏导航**审计时**实测为 **7 项，其中 5 项直接用内部代号命名**；D1 已移除 F2 一项，现为 **6 项、4 项带代号**（完整 IA 重构见 Phase 6）：

```
首页 | F1 简历诊断 | F3 模拟面试 | F4 能力报告 | F5 投递 | 面经知识库
```

| 代号 | 页面 | 行数 | 用户看到的名称 | D1 后 |
| --- | --- | --- | --- | --- |
| — | `public/index.html` | 127 | 首页 | 保留（Phase 6b-2 起由品牌区进入，不再占一级导航位） |
| F1 | ~~`public/pages/f1-resume.html`~~ → `public/pages/resume-evidence.html` | 235 | 简历证据 | 保留（Phase 6b-2 改名） |
| ~~F2~~ | ~~`public/pages/f2-match.html`~~ | 214 | ~~F2 岗位匹配~~ | **已删除** |
| F3 | ~~`public/pages/f3-interview.html`~~ → `public/pages/interview-practice.html` | 296 | 模拟面试 | 保留（Phase 6b-2 改名） |
| F4 | ~~`public/pages/f4-report.html`~~ → `public/pages/action-loop.html` | 483 | 行动闭环（能力报告 + 缺口行动清单） | 保留（Phase 6b-2 改名；一级导航第 4 项，行程节点改为不可点击） |
| F5 | ~~`public/pages/f5-apply.html`~~ → `public/pages/job-apply.html` | 138 | 投递与求职信 | 保留（Phase 6b-2 改名；二级页，不再是导航项） |
| KB | ~~`public/pages/kb.html`~~ | 105 | ~~面经知识库~~ | **已删除（Phase 6a 入口下线，题库下沉为面试引擎内部数据源）** |
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
| **D7** | 进入即强制注册/登录（弹窗门禁）如何落地？ | ✅ **已实现（Phase 6b-3）**，见 §10.3 / §18 |
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
| 10 Cover Letter 用 Target Job + Evidence | ✅ **Phase 4b 达成（后端）**：`wf07/cover-letter` 带 `targetJobId` 即走接地路径 —— 事实底座 = 岗位要求（P0→P1→P2，≤5 条）+ `usable_evidence()`（只含 confirmed，≤3 条），缺口只进元数据不进正文，无已确认证据时**不请模型**（15 项测试 + 冒烟锁定） | 前端 F5 页面尚未传 `targetJobId`（Phase 6 接线），详见 `phase4b-report.md §7` |
| 11 Interview 按 Gap 定向 | ✅ Phase 3：`targetJobId` → 缺口按 P0→P1→P2 排序出题，返回 `questionPlan` | ✅ **已达成**（Phase 3，后端） |
| 12 Interview 新事实需用户确认 | ✅ **Phase 4 端到端打通**：D9=A 落地，`wf04/end` 一次性抽取；模型路径与降级路径都由 `candidate_evidence()` 收口，只产 pending（9 项测试锁死） | ✅ **已达成**（Phase 4） |
| 13 Service 不反向依赖 API | ✅ **Phase 5 达成**：两处倒置已修（`diagnosis_service` / `interview_service` 不再 import api，模型工厂收敛为 `tools.providers.model` 唯一归属地）；新增静态门禁 `tests/test_layering.py`（8 项，进 pytest，含判据自检） | ✅ **已达成**（Phase 5）。`tools/` 归并进 domain+providers 属 Phase 7 |
| 14 .env 无重复/废弃 | ✅ **Phase 7a 达成**：模板重写为 **29 个变量、无重复、每行合法**（旧版有一行未注释的 `====` 分隔符，`DUMATE_CONSENT_SECRET` / `_MAX_AGE_SECONDS` 各出现 3 次），删掉 0 消费者的 `LOG_LEVEL` / `ENV`，**并补上 13 个代码在读但模板漏掉的变量**（含服务端游客会话密钥 `DUMATE_GUEST_SECRET`）。新增判据 `scripts/env-example-check.py` 双向强制（模板 ⊆ 代码、代码 ⊆ 模板，例外须写理由） | ✅ **已达成**（Phase 7a，见 §19） |
| 15 前端只有一套 canonical | ✅ **Phase 6a 达成**：`ui/prototype`（陈旧分叉）+ `ui/assets`（与 `public/assets` 逐字节重复）**整树已删**；`public/` 定为唯一 canonical，`docs/` 为发布镜像，非 `.md` 文件由 `tests/test_publish_mirror.js` 强制集合相同 + 逐字节相同（含判据自检） | ✅ **已达成**（Phase 6a）。`.md` 的公开范围属产品/隐私决策，未擅自增删 |
| 16-18 Coverage 85/90/75 | Python 79%（Phase 0 基线）；JS 未测 | Phase 15（须在 CI 的 Python 3.11 上重测） |
| 19 CI 全绿 | ✅ pytest **457** passed + node 36/36 | 已达成 |
| 20 High/Critical 依赖漏洞 = 0 | ✅ pip-audit 无发现 | 已达成 |
| 21 关键 AI 输出有 fallback | 大部分有（模型失败回退规则）；Phase 3 的规则路径本身即降级实现；**Phase 4 的面试抽取失败不抛错、降级兜底并透出 `degraded`** | 待逐项核查 |
| 22 删除链路自动化测试 | ✅ **`tests/test_phase1_deletions.py` 24 项**；Phase 3 加目标岗位删除级联；**Phase 4 修掉一处真实的孤儿行泄漏**（删岗位未清派生行动，见 `phase4-report §7` 缺陷 1） | ✅ **已达成** |
| 23 README 与实际 IA 一致 | 已修正项目状态、页面数、F4 口径与已删变量 | 命名体系仍用 F1–F5（Phase 6/7 统一） |
| 24 无 dead routes | ✅ **0 个**；Phase 4 新增 3 条重写（共 **44** 条）后仍为 0，并新增**正向**检查（新接口必须在生产入口有重写） | ✅ **已达成** |
| 25 无明显 dead code | 已清除：专业匹配+任务框架、C7、KB 页、语音链路、陈旧测试产物；**Phase 6a 再清：`ui/` 整树（24 文件）、`scripts/capture_ui.py`（已坏）** | 剩余：4 个推送脚本、5 个未调用 prompt（Phase 7）。`ui/prototype` 一项已结清 |

---

## 10. 决策落地记录

### 10.1 D1 · 专业→职业匹配整块删除（已完成）

产品负责人 2026-09-13 裁决：**整块删除**，不做 Optional Career Exploration。删除范围与验收见 `CHANGELOG.md` 同日条目与 `tests/test_phase1_deletions.py`（11 项断言固化：路由 404、文件不存在、`vercel.json` 无残留、`tasks` 表不再创建、镜像仍一致）。

删除后主产品只剩**一套**匹配概念：Target Job Analysis（`wf03` 血脉，`services/match_service.py`）。DoD #6 达成。

**~~刻意未删~~ → 已于 Phase 6b-1（2026-09-17）退役**：`js/job-upload.js` 与 `data-bridge.js` 的
`submitJD`/`matchJD`/`uploadJD*`。当时的理由是"它们属于要保留的 Target Job Analysis，只是缺宿主页面"。
**该理由在 Phase 6b-1 的侦察中被实测推翻**：`job-upload.js` 的通路是
`uploadJD → submitJD → matchJD`，即 `/api/wf03/{upload,jd,match}`，产出的是 `jobProfile` 与
`matchResult`（匹配分数 + gaps）——**产不出 Decision，也产不出落库的 Gap 与 Action**。
换句话说，即使给它建了宿主页面，它也交不出 §7 要求的 Target Job Workspace
（"分析这个岗位，能不能投" → APPLY/STRETCH/PASS + 依据），因为它的契约里没有这两个概念。
且它跨 6 个状态依赖 **29 个 DOM id**（含已删的 `f2-match.html` 布局），复用它等于把已删页面的
布局契约重新引回 canonical 树。

**因此 6b-1 的处置是：新建控制器而非重新挂载**——

- 已删除 `public/js/job-upload.js` + `docs/js/job-upload.js` + `tests/test_job_upload.js`
  （实测：全部页面的 `<script>` 均未引用它；`submitJD`/`matchJD` 在全前端**只有它一个调用方**，
  所以它一走，`/api/wf03/*` 的前端消费方归零）。
- 新建 `pages/target-job.html` + `js/target-job.js`，走 `/api/target-jobs` 与 `/api/actions`。
- 退役 `data-bridge.js` 的 `uploadJD` / `uploadJDWithProgress` / `submitJD` / `matchJD` 及其端点映射；
  新增目标岗位 5 个方法 + 行动闭环 9 个方法 + 证据档案 1 个方法，以及"当前目标岗位"这一跨页概念
  （`setCurrentTargetJob` / `getCurrentTargetJob`），供 F5 投递与 F3 出题共用同一岗位口径。
- 清理随之失效的 `.job-upload-layout` CSS（实测：两棵发布树中**无任何 HTML 引用它**）。

**仍然刻意未动**：后端 `/api/wf03/upload|jd|match` 三条路由本身（`api/index.py` 仍服务、
`tests/test_api.py` 与 `scripts/run-rehearsal.py` 仍覆盖）。前端消费方虽已归零，
但路由的去留属独立决议 —— 见 Phase 7 待办，不在 6b-1 内顺手删。

**遗留**：`public/README.md`、`public/redesign-v2-visual.md`、`public/p0-02-automation-alternatives.md` 与 `docs/design/*`、`docs/f2-iteration-1-plan-*.md`、`docs/test-report.md` 等历史文档仍提到 F2 页面。这些是**带日期的历史记录**，不在 Phase 1 改写；Phase 7 统一处理（同时解决 `public/*.md` 对外暴露问题）。

### 10.2 D2 · 账号手机号（已决策，与审计建议相反）

产品负责人裁决：**不去掉手机号**。注册流程保持「手机号 + 邮箱」双字段，`users` 表不做迁移。审计中「简化账号」的建议作废。

### 10.3 D7 · 进入即强制注册/登录（已实现，Phase 6b-3）

产品负责人要求：用户点击进入产品时，**强制注册/登录**，以弹窗形式呈现。

**当前状态：已实现（Phase 6b-3，2026-09-17）**。落地为 `public/js/auth-gate.js` 政策层 +
`public/js/account.js` 机制层的组合，加上原生 `<dialog>` 弹窗。四条要求逐条对应：

| 要求 | 落地方式 |
| --- | --- |
| 不回退既有安全性质 | 服务端安全实现（HttpOnly Session / 密码哈希 / 授权校验 / 归属隔离 / 删除链路 / 限流）**一行未改**，门禁只加在它前面 |
| 原生可键盘操作对话框 + 三态 | 原生 `<dialog>`（`showModal()` 自带焦点陷阱与 `::backdrop`）；三态 `empty` / `error` / `disabled` 显式存在且可断言 |
| 未登录不得出现空白或不可用页面 | 门禁只把交互挡在弹窗后，**页面本身始终可见**；未登录时展示注册/登录弹窗而不是报错 |
| DoD #18（≤3 分钟到首个 Decision） | 注册弹窗**只有四项**（手机号、邮箱、密码、账户名），不插入任何多余步骤 |

细则（分层、三条不可回退口径、豁免名单、判据缺陷）见 **§18**。

### 10.4 决策状态（截至 2026-09-14）

| ID | 状态 | 裁决与影响 |
| --- | --- | --- |
| D1 专业→职业匹配 | ✅ 已决策 | 整块删除，已执行（`fc016c5`） |
| D2 账号手机号 | ✅ 已决策 | **不去掉**，注册保持手机号 + 邮箱，`users` 表不动 |
| D3 单位/职位检索 | ⏸ **暂缓删除，设期限** | 见 §10.5 |
| D4 `applications` 迁移 | ✅ 已决策 | 允许迁移生产数据，已执行（`23f75cf`） |
| D5 `workflows/` 去留 | ✅ 已决策 | **保留原地**，Phase 7 统一归档（见 §10.6） |
| D6 `deliverables/` 归档 | ✅ 已决策 | 同上 |
| D7 进入即强制注册/登录 | ✅ 已实现 | Phase 6b-3 落地：政策层 + 原生 dialog 门禁（见 §10.3 / §18） |
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
一个提交 **`e4b7da3`**：17 文件，**+2314 / −15**。

**新增能力**：`/api/actions`（清单 / 批量或单条开单 / start / complete / outcome / drop / 删除）、
`/api/wf07/applications/<id>/outcome` 与 `/outcomes`（一次结果同时推进 7 态状态机并反向写
**待确认**证据）、`POST /api/wf04/end` 接入 **D9=A 一次性抽取**。
详见 `docs/phase4-report.md` 与 `CHANGELOG.md` 同日条目。

**门禁**：pytest **457** passed（138.59s）、Node 36/36、schema 32 项 OK、敏感扫描 249 文件无发现、
`git diff --check` 干净、双方言 DDL 各 29 表、vercel 死路由 = 0（44 条重写）、
真实 HTTP 冒烟 **57/57**（真进程 + 真端口）。

**DoD 变化**：#12（Interview 新事实需用户确认）由"部分达成"变为**达成**；
#19（CI 全绿）、#22（删除链路）、#24（无 dead routes）随本阶段数字更新。
**#10（Cover Letter）裁决为方案 A 并已由 Phase 4b 落地**，见 §13.4 与 §13.5。

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

### 13.4 口径冲突（已裁决）

**DoD #10（Cover Letter 用 Target Job + Evidence）在两个文档里归属不同**：

- `§9 DoD 表`：标为 **Phase 4**；
- `phase3-report §9`：Phase 4 = **Action Loop（Gap Action Plan + Application 状态回流）**。

**裁决：方案 A（2026-09-16）** —— 承认 Phase 4 = Action Loop，**#10 另立 Phase 4b** 单独结项。
Phase 4b 已于 2026-09-17 完成（见 §13.5），两个文档的口径自此一致。

**Phase 4 结束时仍不可用的东西**（口径）：8 条新路由没有任何页面消费，
因此对外不得出现"面试结束后自动生成行动计划""记一次投递结果就能更新档案"这类描述（Phase 6 才成立）。

### 13.5 Phase 4b 完成记录（2026-09-17 · DoD #10）

提交 **`5cba7b4`**（10 文件，+1112 / −12）；门禁 pytest **473** passed、真实 HTTP 冒烟 **70/70**、
vercel 死路由 **0**（44 条重写 / 38 条 API 路由）、双方言 DDL 各 29 张表。

**目标**：把求职信的事实底座从"F1 诊断里模型抽的 span 引文"换成
**目标岗位要求 + 已确认职业证据**。前者只是"模型觉得相关"，后者才是用户确认过的事实 ——
求职信是发给雇主的对外材料，底座错了，写得再漂亮也是替用户编经历。

**接口**：`POST /api/wf07/cover-letter` 新增可选 `targetJobId`。
不带 → 旧行为**完全不变**（新增 `grounding: "diagnosis"` 供前端区分）；
带 → 接地路径，返回 `grounding` / `evidence` / `requirements` / `gaps` / `notice`。

**三条不可让步的规则**（详见 `phase4b-report.md §2`）：

1. **没有已确认证据就不请模型写** —— 空地会让模型替用户编经历；只给带明确占位的框架。
   写成正面测试：替身路由的调用次数必须是 **0**。
2. **未覆盖的要求是"禁止声称"名单** —— 它只进元数据让界面提示，不进正文。
3. **正文每段经历都要能回指一条已确认证据** —— 模型输出过不了四字片段校验就退规则模板。

**口径**：这是**后端能力**。前端 F5 页面尚未传 `targetJobId`，用户在页面上生成的求职信
仍走旧路径；"求职信会自动引用你的目标岗位与已确认经历"在 Phase 6 接线前**不得对外说**。

---

## 14. Phase 5 完成记录（2026-09-17 · 依赖倒置）

提交 **`a3541cc`**（18 文件，+725 / −48）；门禁 pytest **481**、真实 HTTP 冒烟 **70/70**、
vercel 死路由 **0**（44 条重写 / 38 条 API 路由）、双方言 DDL 各 29 张表。

**目标**：DoD #13「Service 不反向依赖 API」—— 修掉 `dependency-map.md §3.1` 从 Phase 0
就点出、被 Phase 2 推到本阶段的两处倒置，并加静态门禁防回潮。

**修了什么**

1. **两处明面倒置**：`diagnosis_service` / `interview_service` 里的
   `from api.index import build_model_router`（都写在函数体内，注释理由是"monkeypatch compat"）
   → 改依赖 `tools.providers.model`（叶子模块，模块级 import 不再触发循环导入）。
2. **一处分层之外的真问题**：`tools.trace.trace_id()` 要 Flask 请求上下文，而诊断服务用它
   兜底 → **服务的单测必须 `with app.test_request_context()` 才能跑**。
   修法：`tools/trace.py` 拆出纯函数 `new_trace_id()`、flask 改函数内延迟导入；
   web 层解析 `X-Trace-Id` 后**注入**服务（`diagnose_resume(resume_text, trace=...)`）。
   `test_phase5.py` 里那个 `test_request_context` workaround 已删除 —— 去掉它本身就是验收。
3. **工厂收敛为单一归属地**：`build_model_router` 全仓库只有一处定义，
   其余模块一律 `from tools.providers import model as model_provider` 后属性查找。
   此前"打错桩不报错、只是不生效"，现在打错直接 AttributeError。

**门禁**：新增 `tests/test_layering.py`（**8 项，进 pytest**）：跨层 import（含函数体内）、
传递 Flask 依赖（只按模块级 import 计算）、工厂单一归属地与"无人重新绑定"、
以及**判据自检**（喂故意越层的假源码，证明检查会红）。
细节与四个实现坑见 `docs/phase5-report.md §4`。

**仍未做（已排期）**：`dependency-map.md`「Phase 5 验收」第 4 条（`tools/` 归并进
`domain/` + `providers/`）与 §4.1 的 `api/index.py` 拆文件 —— 两者都是跨阶段重构，
属 Phase 7；不塞进本期，是为了让"倒置已修"这个结论保持可验证。

**口径**：本阶段是结构与测试改动，**对外能力零变化**。发布说明不得出现"性能提升/新增能力"。

---

## 15. Phase 6a 完成记录（2026-09-17 · 前端 canonical 唯一化与死树清理）

提交 **`a1586a5`**（46 文件，+749 / −4511）；门禁 pytest **482**、node **42/42**、
真实 HTTP 冒烟 **70/70**、vercel 死路由 **0**、双方言 DDL 各 **29** 张表、
发布镜像 27 个非 md 文件逐字节一致。

**为什么先做这一段（裁决）**：`product-scope.md §7` 与多条 Phase 报告把 Phase 6 写成"前端工作面"，
但它实际包含四件规模不同的事：① canonical 唯一化 ② IA 收敛到 4 个一级工作区 + 去 F 代号
③ 闭环接线（目标岗位工作区挂 `job-upload.js`、F5 接 `targetJobId`、Action Loop 消费 8 条路由）
④ D7 登录门禁。一次做完必然注水，且 ①②是 ③④ 的前置（改名不能跨着一棵待删的树做）。
**故拆为 6a（本轮，结构）与 6b（IA 收敛 + 闭环接线 + D7）**。

**修了什么**

1. **删掉第三棵前端树 `ui/`（24 文件）**：`ui/prototype/` 是 `public/` 的陈旧分叉 —— 21 个文件名
   全部已存在于 `public/`（12 个逐字节相同、9 个不同且其中 8 个更小，如 `css/main.css` 20336 vs 32008；
   `pages/f3-interview.html` 反而更大，但 prototype 侧**缺** `pages-api-config.js`、`job-upload.js`、
   `resume-upload.js`）、含 **7 处坏引用**（6 处指向不存在的 JS + `radar.js` 里在 prototype 下失效的
   ECharts 相对路径）、**未部署**（`vercel.json` 无 `ui/` 重写）、**无任何运行期引用**；
   `ui/assets/` 与 `public/assets/` **逐字节完全相同**（3 文件，含 1MB echarts）。
   没有一件是 prototype 独有的。
2. **不变量从"约定"升级为"门禁"**：`public/` 定为唯一 canonical，`docs/` 定为发布镜像；
   新增 `scripts/sync_mirror.py`（规则化 + `--check`）与重写的 `tests/test_publish_mirror.js`
   （**规则驱动、双向、含判据自检**）。原测试是**硬编码 26 项清单**，漏掉了
   `blind-test-results/blind-test-summary.json` —— 恰好当时两边相同，那处漂移永远不会被发现。
3. **两棵发布树的自述文件是死树自述**：`public/README.md` 与 `docs/README.md` 逐字节相同，
   且整篇在描述 `ui/prototype`（还列出 Phase 1 已删的 `pages/kb.html`、C7 区间带、七天计划）。
   两棵都重写为发布树说明。
4. **顺带修掉的真实缺陷**：`scripts/sync_sidebar.py` 的来源声明写着 `ui/prototype`（删树后成假话）、
   `PAGES` 漏了 `pages/f5-apply.html`（6 页都有侧栏，脚本只管 5 页）；`pages/f4-report.html`
   在同一个 `<head>` 里**重复引入 `sidebar.css`**；`public/capability_matrix.md` 比 `docs/` 那份旧
   （08-05 vs 08-06，且后者带 `deliverables/p0-03-evidence/` 实跑证据）；两份 `index.md` 都还索引着
   已不存在的 `voice-test-checklist.md`。删 `scripts/capture_ui.py`（目标树被删且本就指向已删的 `f2-match.html`）；
   修 `scripts/capture_mobile_ui.py` 的同类坏条目。

**未做（有意）**

- `scripts/p0-06-user-mission.py` / `p0-07-freeze.py` 里的 `ui/prototype` 引用**不改**：它们是
  2026-08-03 G9 证据链的**时点归档脚本**，引用是历史事实。但**不得重跑**（会产出错误证据）。
- `.md` 的公开范围（`docs/` 45 份内部文档、`public/` 16 份）**未擅自增删** —— 这属产品/隐私决策。
- IA 收敛（去 F 代号、导航 ≤4）与闭环接线未动，按上面的裁决留给 6b。

**口径**：本阶段是结构与清理改动，**用户可见行为零变化**。唯一对外可见差异是
`public/capability_matrix.md` 与 `README.md` 的内容修正。

**下一步**：Phase 6b-1（见 §16）。

---

## 16. Phase 6b-1 完成记录（2026-09-17 · 目标岗位工作区 + 退役 wf03 前端路径）

提交 **`d9b662c`**（27 文件，+2345 / −1654）；门禁 pytest **482**、node **40/40**、
真实 HTTP 冒烟 **70/70**、vercel 死路由 **0**、双方言 DDL **15**、
发布镜像 **28** 个非 md 文件逐字节一致。

**为什么 6b 还要再拆（裁决）**：§15 把 6b 定为五件事，侦察后发现两条硬顺序约束：

1. **一级工作区 ≤4 是产品门禁**：`tests/test_phase1_deletions.py` 把导航标签写死为
   `["首页","F1 简历诊断","F3 模拟面试","F4 能力报告","F5 投递"]`，并注明"不得超过 DoD 的 4 项上限 + 首页"。
   于是本轮**不能**顺手往导航塞第 6 项。
2. **IA 收敛要等四个工作区都真的存在**：§7 的 Action Loop = "F4 重构为 Gap & Action Plan + Retest"，
   `f4-report.html` 要**先**长出行动清单，才能改名叫「行动闭环」。

**故 6b-1 = 把事情做出来，6b-2 = 把界面收敛。** 本轮结束时导航**一个字符都没改** ——
这是遵守约束 1 的结果，不是遗漏。目标岗位页从 ① 首页功能卡 ② F5 投递页引导链接进入，
二者都进了新判据（防"无人挂载"）。

**做成了什么**

1. **目标岗位工作区上线**：`pages/target-job.html` + `js/target-job.js`，
   建岗 → 拆要求 → 对照简历 → **APPLY/STRETCH/PASS** + 可逐条回查依据 + 缺口清单。
   `/api/target-jobs`（5 条）与 `/api/actions`（8 条）从**零前端消费**变为有消费方 ——
   `docs/phase3-report.md` 遗留项 #1「闭环在界面上不可见」就此关闭。
2. **引入「当前目标岗位」跨页口径**（缓存 `currentTargetJobId`）：此前"我分析的是哪个岗位"
   在前端根本不存在，F3 只能靠 `matchResult.gaps` 出题；现在 F5 与 F3 共读同一岗位。
3. **DoD #11 真正接通**：`startInterview()` 现在把 `targetJobId` 递给 `/api/wf04/start`。
   后端本就支持（`api/index.py:1437` 起按该岗位未解决缺口 P0→P1→P2 排序出题并回传 `questionPlan`），
   缺的只是前端把它传过去。
4. **拒绝给结论的行为被原样呈现**：后端在可核对事实 < 3 条时返回 `insufficient_grounds(422)`，
   页面显示该消息而不给分数；`insufficient_evidence` / `match_notice` 显式展示；
   缺口为空时页面明确写"不等于能力已达标"。

**决策反转：`job-upload.js` 退役而非重新挂载**

§5 原写"刻意未删……需要在目标岗位工作区里重新挂载，而不是删除"。**该理由被侦察推翻**：
它的通路 `uploadJD → submitJD → matchJD`（`/api/wf03/{upload,jd,match}`）只产出 `jobProfile`
与匹配分数，**产不出 Decision，也产不出落库的 Gap 与 Action**。它的契约里没有这两个概念，
所以即使建了宿主页面也交不出 §7 要求的 Target Job Workspace。且它跨 6 个状态依赖 **29 个 DOM id**
（多个来自已删的 `f2-match.html`），复用它等于把已删页面的布局契约引回 canonical 树。

四条证据：①无人挂载（全部页面 `<script>` 均未引用）②`submitJD`/`matchJD` 在全前端只有它一个调用方
③契约已不成立 ④自身依赖已删页面的 DOM。处置见 §5 的修订段与 `CHANGELOG.md` 同日条目。
**后端 `/api/wf03/*` 三条路由刻意保留**（`tests/test_api.py`、`scripts/run-rehearsal.py` 仍覆盖），
去留记入 Phase 7。

**顺带修掉的三处判据失效**（都是"判据自己不可靠"这一类）

| 判据 | 失效方式 | 修法 |
| --- | --- | --- |
| `git diff --check`（门禁第 6 步） | 只查未暂存差异，而本流程先 `git add -A` 再跑门禁 → **恒为 0**。实测注入行尾空白后仍 exit 0（`git diff --check HEAD` 正确 exit 2） | 改为 `git diff --check HEAD` |
| 新契约判据的 wf03 扫描 | 用全文正则，被自己写的说明性**注释**命中（误报） | 只解析 `ENDPOINTS` 映射的**值**，并断言取值数 ≥10 防假通过 |
| `patch6b.py` 幂等性 | 判据写成"`new` 在且 `old` 不在"，对追加型补丁（`new = old + 新增行`）永远不成立 → 第二次运行把页面清单插了两遍 | 改为"`new` 已在即跳过" |

第一条与 §15 修掉的 `cmd | tail -5; echo $?` 属同一类：**判据的观察面与实际改动面不重合**。

**事故记录**：本轮中途发现 `public/`、`docs/`、`tests/` 三棵树被**外部进程**从工作区清空
（`git status` 显示为第二列 ` D`，即工作区删除、索引未动 —— 与 6a 那次 `scripts/` 事件同签名）。
已用 `git checkout -- public docs tests` 从索引完整还原，并逐文件用 `git hash-object` 与
`git rev-parse HEAD:<path>` 比对确认逐字节一致。代价：未暂存的编辑会丢（本轮丢了 5 个文件的编辑）。
对策：全部前端改动收进幂等可重跑的 `work/patch6b.py`；每完成一个可验证小段就 `git add -A`
（索引在本环境中未被清空，暂存即持久化）。

**口径**：本阶段是**能力新增**（此前界面上不存在目标岗位分析与行动闭环），
不是"性能提升"或"体验优化"。发布说明应写"新增目标岗位工作区"，
**不得**宣传为"能自动替你投递"。

**下一步**：Phase 6b-2（**已完成，见 §17**）—— 原文：IA 收敛到 4 个一级工作区【简历证据 / 目标岗位 / 模拟面试 / 行动闭环】
+ 全量去 F 代号 + Action Loop 落位到 `f4-report.html` 消费 `/api/actions` + F5 接当前目标岗位口径
+ F3 渲染 `questionPlan`）；6b-3（D7 进入即强制注册/登录）；D3 期限 **2026-10-13**。


## 17. Phase 6b-2 完成记录（2026-09-17 · 信息架构收敛与去 F 代号）

提交 **`72cd3d8`**（17 文件，+1319 / −20，6b-2a 能力落位）+
**`a8ec061`**（46 文件，+674 / −690，6b-2b 界面收敛）；门禁 pytest **482**、node **54/54**、
schema **32/32 VALID**、真实 HTTP 冒烟 **70/70**、vercel 死路由 **0**、双方言 DDL **15**、
发布镜像 **29** 个非 md 文件逐字节一致、活文档 **44 处页面引用**全部可解析。

**为什么 6b-2 还要再拆两刀**：§16 把 6b 切成"6b-1 做出来 / 6b-2 收敛"，而 6b-2 自己仍受
同一条约束支配 —— `f4-report.html` 要**先**长出行动清单，才能改名叫「行动闭环」。
故 **6b-2a = 能力落位（导航一个字符不改）**，**6b-2b = 界面收敛**。

**做成了什么**

1. **Action Loop 第一次到用户面前**：`/api/actions` 的 8 条路由此前**零前端消费**
   （`phase6a-report.md §8` 记为待办）。新增 `js/action-loop.js`，面板挂在
   `f4-report.html` 且位于**所有 state view 之外** —— empty / error 态下行动清单依然可用。
   落位在既有页而不是新建页：§7 写的是"F4 **重构为** Gap & Action Plan + Retest"，
   雷达图 / C0 快照 / 缺口清单同屏，复测前后才能对照；新建页会把导航顶到 5 项，
   与 ≤4 的产品门禁直接冲突。
2. **DoD #10 结清**：`generateCoverLetter()` 新增 `targetJobId`，未显式传参时回退
   「当前目标岗位」；投递页显式呈现"这封信引用了哪些依据"（证据 / 岗位要求底座 / 未覆盖缺口），
   **零证据时明说没有引用任何个人经历**，不留白。
3. **DoD #11 结清**：模拟面试显示 `questionPlan`（题型 + 优先级），题型标签覆盖
   `domain/interview.py::QUESTION_PRIORITY` 的全部 5 个取值（跨语言比对，防后端加题型后前端静默漏显示）。
4. **IA 收敛到 4 个一级工作区**：导航 5 → 4，去掉「首页」项，改由品牌区
   `职跃AI` 回首页；投递页退出导航、降为目标岗位的二级页，并由目标岗位页的出口区链入
   —— **少一个格子，但没少一条回家的路**（有判据断言品牌链接存在）。
5. **去 F 代号的范围包含 URL**：文件名也是用户可见面，故 4 个页面 + 2 个脚本在两棵树上
   同时改名（改后逐字节一致）：`f1-resume→resume-evidence`、`f3-interview→interview-practice`、
   `f4-report→action-loop`、`f5-apply→job-apply`。

**顺带清掉的一段死代码**：`f4-report.html` 内联着「F1–F3 完成进度追踪器」，引用 6 个
**早已不存在**的 DOM id，每次加载必抛 `TypeError`，而**没有任何测试会失败** ——
因为没有判据在看"页面声明的 id"与"脚本引用的 id"是否对得上。删掉它，并新增
通用判据：页面的内联脚本不得 `getElementById` 一个该页没有声明的 id。

**三处判据缺陷**（仍是"判据的观察面与实际面不重合"这一类）

| 判据 | 失效方式 | 修法 |
| --- | --- | --- |
| 路径扫描（6b-2a 新增） | 只覆盖**发布树**且**排除 `.md`**，于是活文档里指向旧名的行不在观察面内 | 新增门禁第 10 步 `scripts/live-doc-path-check.py` 专查活文档 |
| 该门禁的"历史语境"判定（第一版） | 用**上下 ±10 行**窗口：§2 现况表格里任何一行都能被 8 行之外的注记开脱。变异测试实测：塞 `action-loop-NOPE.html` 仍**通过** | 收紧到**同一行或本节标题**，同一注入 exit 1 |
| 同上，连锁 | 为说明"这节是快照"而把 §2 标题改成「用户页面（**审计时的** 8 个 HTML）」，这一步本身让整节重新落进遮蔽区 | 标题改为不带历史措辞的「用户页面（快照：8 个 HTML）」，历史结论交给注记段落与**每一行自己的标记** |

第三条是这一轮最有价值的发现：**为了让文档说实话而加的那句话，可能反过来削弱判据。**
同类错误的三个变体已可并排：6a 的 `cmd | tail -5; echo $?`（取错退出码）、
6b-1 的 `git diff --check`（不查已暂存）、6b-2 的 ±10 行窗口（窗口比语义宽）。

**口径**：6b-2a 是**能力新增**，6b-2b 是**信息架构收敛**（不产生新能力）。
发布说明应写"新增行动闭环、投递与面试接入当前目标岗位"，不得宣传为"能自动替你投递"，
也不得轻描淡写为"只是改了个名字"—— 对用户而言，导航与 URL 是他每天直接看到的那一层。

**下一步**：Phase 6b-3（D7 进入即强制注册/登录，`§10.3`）—— **已完成，见 §18**；
Phase 7a（门禁扩面与文档真相）—— **已完成，见 §19**；
Phase 7b（`/api/wf03/*` 后端路由去留、`public/*.md` 公开范围）、
7c（`api/index.py` 拆分，实测 1621 行）、7d（`tools/` → `domain/` + `providers/` 归并）；
D3 期限 **2026-10-13**。

---

## 18. Phase 6b-3 完成记录（2026-09-17 · D7 进入即强制注册/登录）

`§10.3` 的四条要求到此落地。**口径**：这是**门禁**，不是账号体系重构 —— 服务端安全实现
（HttpOnly Session、密码哈希、授权校验、归属隔离、删除链路、限流）**一行未改**，
只在其前面加了一层"进来先登录"的政策。

### 18.1 分层：政策与机制分开

| 文件 | 角色 | 判据如何观察它 |
| --- | --- | --- |
| `js/account.js` | **机制**：弹窗、表单、`/api/auth/*` 调用 | 保留原职，只加了 busy 态与事件广播 |
| `js/auth-gate.js`（新增） | **政策**：谁被拦、何时拦、能否关掉 | `decide()` / `plan()` 是纯函数，脱离 DOM 即可断言 |

分层的收益是**可判据化**：政策不碰 DOM，于是"断网时会不会放行""本地标记能不能绕过"这类
问题可以在 VM 里跑出来，不需要浏览器 —— 而这恰恰是 D7 最该被锁死的两个性质。

### 18.2 三条不可回退的口径

1. **登录态只认服务端。** 政策层不读 `localStorage` / `sessionStorage` / `document.cookie`，
   只经 `ZY_ACCOUNT.refreshAuth()` 取 `GET /api/auth/me` 的答复。前端一句 `loggedIn = true`
   不该能开门。判据用**存取陷阱**（键名故意起得像真的）证明政策层**一次都没碰过**本地存储，
   而不是仅读源码断言"没写 localStorage"。
2. **"不知道"不等于"是游客"，一律拦下。** 拿不到服务端答复（断网 / 5xx）判为 `unavailable`
   → 强制弹窗 + 「重新连接」出口。把两者混为一谈，等于给服务器故障开了一道后门。
3. **强制态关不掉，三层兜底。** ①政策层隐藏关闭按钮；②`account.js` 在
   `forced && !currentUser` 时拒绝 `closeAuth()`；③CSS
   `[data-forced="true"] .zy-modal-close { display: none }` 作为 JS 未跑到的兜底。
   `Esc` 亦被原生 `cancel` 事件拦下（`preventDefault()`）。

### 18.3 可访问性与"不出现空白页"

弹窗改用**原生 `<dialog>`**：`showModal()` 自带焦点陷阱与 `::backdrop`，关闭按钮、
状态区、重试按钮都在页面上真实存在。三态显式且可断言：`empty`（默认）/ `error`（拿不到
登录态）/ `disabled`（提交中或该页门禁关闭），状态区为 `role="status" aria-live="polite"`。
门禁只把交互挡在弹窗后面，**页面本身始终可见**，不清空、不报错。

**DoD #18 的约束怎么落的**：注册弹窗**只有四项**（手机号、邮箱、密码、账户名），
不插入任何多余步骤，弹窗内即可完成注册与登录切换。

### 18.4 豁免名单刻意只有一项

`pages/states.html`（内部 QA 状态墙 —— 不进导航、不含任何用户数据，且它的用途就是预览
包含 empty 在内的六种界面状态，加门禁会让自己不可用）。有判据把它**锁成恰好一项**：
扩容必须是有意为之，不能顺手放一个产品页出去。

### 18.5 修掉的一个接口隐患（本轮唯一的**产品侧**缺陷）

`check()` 过去返回 `plan()` 的结果，而 `plan()` 与 `decide()` **同用一个 `gate` 键、
语义还相反**：豁免页 `plan().gate === 'exempt'` 是**真值**，而 `decide().gate === false`
意思是"别拦"。同一个键承载两种语义，`if (plan.gate) …` 这种写法会在豁免页上给出完全
相反的行为。现在 `check()` 返回**决策本体**（`gate` 布尔 + `reason`）并附带计划的呈现
字段，两层键名错开为 `gate`（布尔）/ `mode`（字符串）。

### 18.6 四处判据缺陷（同一族：判据的观察面与实际面不重合）

首轮门禁 **15 项里红了 5 项，其中 4 项是判据自己的缺陷**：

| 判据 | 失效方式 | 修法 |
| --- | --- | --- |
| "不得使用本地存储" | `includes('localStorage')` 扫**全文**，命中的是文件头那句"本文件不读 localStorage" —— 判据在逼人删掉最该留下的安全说明 | 新增字符串感知的 `codeOnly()` 只剥注释、保留字符串与代码；并加探针证明它剥得掉注释又不会漏掉真的调用 |
| `/api/auth/me` 断言 | 写在 `auth-gate.js` 上，而该文件里**没有**这个字面量（真正的调用在 `account.js` 的 `api('/auth/me')`）—— 它是靠注释里的 "GET /api/auth/me" **凑巧通过**的 | 断言挪到 `account.js`，并要求命中**引号内的字面量** |
| `deepEqual` 比 VM 对象 | `vm` 里造出的对象与宿主字面量的 `Object.prototype` 不是同一份，`deepStrictEqual` 报"结构相同但引用不等" —— **判据的锅，不是产品的锅** | 加 `flat()` 复制进宿主对象再比；并加探针断言 vm 对象确实与宿主不同原型（否则 `flat()` 就是在给一个不存在的问题打补丁） |
| `check()` 的返回契约 | 测试以为返回决策（`gate` 布尔），实际返回计划（`gate` 字符串）；且脚本加载时 `init()` **自己已经问过服务端一次**，"调用次数 = 1"的期望没把这条基线算进去 | 修产品（见 §18.5 与 `mode` 键名错开）；修测试：把基线写成**显式断言**，并让 `apply()` 的用例先清掉 init 的异步落地 |

**这是同类错误的第四个变体**，可与前三个并排记忆：6a 的 `cmd | tail -5; echo $?`（取错
退出码）、6b-1 的 `git diff --check`（不查已暂存）、6b-2 的 ±10 行窗口（窗口比语义宽）、
6b-3 的扫全文（把注释当实现）。四次的共同点是**判据的观察面比它要判的那个语义宽**。

### 18.7 判据可证伪性的证明

全绿本身不构成证据（本项目已四次栽在"判据不可能变红"上），所以本轮做了**变异测试**：
对 6 个关键判据各注入一次违规，逐个确认对应用例真的变红，再回放快照恢复。

| 注入的违规 | 应变红的用例 |
| --- | --- |
| 政策层真读一次 `localStorage` | 第 5 项（不得以本地存储判定登录态） |
| 把 `unavailable` 判为放行（断网即放行） | 第 8 项（decide 四象限） |
| `check()` 退回返回计划（`gate` 键又变字符串） | 第 14 项（豁免页） |
| 去掉 CSS 强制态兜底 | 第 7 项（三层兜底） |
| 豁免名单悄悄扩容一项 | 第 4 项（名单恰好一项） |
| 产品页不再挂政策层 | 第 1 项（装配顺序） |

6/6 全部被抓到，恢复后回到全绿。脚本：`work/mutate6b3.sh`。

**本轮另一次事故（工具侧）**：变异脚本第一版用 `git checkout -- public/index.html`
恢复被改的页面 —— 那条命令回到的是 **HEAD**（6b-2 状态），把本轮**尚未提交**的改动
一起冲掉了（受损范围经核对只有这一个文件）。修法是让变异脚本对每个被改文件都**快照到
工作副本**再回放：变异脚本面对的永远是未提交的工作区，**git 在这里不是安全网**。
文件已从镜像树逐字节还原（`docs/index.html` 未被触及）。

### 18.8 遗留

- ~~`docs/architecture.md` 提到前端消费端点的来源里有 `js/kb.js`~~ —— **已修（Phase 7a，2026-09-17）**。
  该文件早已不存在，而当时那条引用写成**裸脚本名**（不带 `js/` 前缀），所以带前缀的路径扫描看不见它。
  Phase 7a 把活文档门禁的观察面从 `pages/*.html` 扩到 `js/*.js` **并覆盖反引号里的裸脚本名**，
  同时把「前端实际消费 N 个端点」这句手抄计数换成三段可判据的不变量（见 `architecture.md §3`）。
  **可复用的教训**：判据的观察面要覆盖作者**真实会写**的写法，而不是我们自己偏爱的那一种 ——
  否则"扩面"只是换了个地方继续漏。
- 门禁从 10 步不变（新增的 15 项判据并入既有第 2 步 `node --test`）。

**下一步**：Phase 7a（门禁扩面与文档真相）—— **已完成，见 §19**；Phase 7b/7c/7d 见 §19.5；
D3 期限 **2026-10-13**。

---

## 19. Phase 7a 完成记录（2026-09-17 · 门禁扩面与文档真相）

Phase 7 的第一个子阶段。**没有新能力，对外行为零变化** —— 改的全部是"判据的观察面"与
"文档说的实话"。完整报告见 `docs/phase7a-report.md`。

**口径一句话**：这是同一件事的四次重复 —— **把一条已存在的约定变成判据，并让判据的观察面
对准作者真实会写的写法**。四次里三次抓到的是同一类失败：约定一直在，判据没在看。

### 19.1 活文档路径门禁 → 脚本层（观察面扩三种形态）

Phase 6b-3 记下的那处**裸脚本名**陈旧引用（`kb.js`，本轮已修，见 §18.8），
**扩成 `pages|js` 也抓不到** —— 带目录前缀的规则看不见不带前缀的写法。所以扩面收三种形态：
页面 `pages/*.html`、带目录的脚本 `js/*.js`、**反引号内的裸脚本名**（形如 `radar.js`
这种不写 `js/` 的写法）。

扩面后抓到 **11 处**，其中**只有 1 处是真漂移**（`architecture.md` 把 `kb.js` 列为端点来源，该文件早已删除），
其余 10 处都是"历史语境但标记写法不在判据词表里"。

### 19.2 判据太窄 —— 6b-3 那条教训的镜像

- 6b-3：判据观察面比语义**宽**（`includes('localStorage')` 扫全文，命中文件头那句安全说明）；
- 7a：判据观察面比语义**窄** —— `"已删除" in "已整条删除"` 为 **False**，于是一条
  **完全正确的**历史注记被判成漂移。

窄的那一侧更阴：**判据红了会引导人去改正确的东西。** 修法是加同义容忍正则
（`已(?:于<状语>)?(?:整条|整块|全部|整体)?(?:删除|删掉|移除|退役|下线|废弃|作废)`），
边界由两个**相反方向**的探针钉住：认「已整条删除」，不认裸「删除」（那是动作条目）。
刻意不放「快照」——6b-2b 实测过它会让整节落进豁免区。

### 19.3 端点计数退役 → 三段不变量

`architecture.md §3` 的「前端实际消费 15 个端点」实测已烂：15 个名字里 5 个退役、
Phase 3/4 的 3 组新端点一个没列、来源里还写着已删除的 `kb.js`；同节路由表还留着 7 条
Phase 1 已删的路由，两个数字也从未实测过（写 40/48，实测 49/44）。

处置：**删掉这句话**，换成可判据的不变量 —— **前端字面量 ⊆ vercel 重写源 ⊆ `route_api()` 处理分支**。
第一段由新增的 `scripts/frontend-api-literal-check.py` 判（实测 22 个写死的路径，全部命中），
后两段沿用 `scripts/vercel-dead-routes.py`。文档只描述分组与含义，**条数交给脚本打印**。

### 19.4 `.env.example` 双向一致（本轮最实质的一处发现）

旧模板有三类毛病：一行**未注释**的 `====` 分隔符、一整块重复（两个变量各 3 次）、
以及**漏掉 13 个代码里真的在读取的变量** —— 含服务端游客会话密钥 `DUMATE_GUEST_SECRET`
（代码里有回退，**所以漏配不会被任何测试发现**）。

第 3 类最危险：**模板短了不会红。** 重写为 29 个变量、无重复、每行合法，新增
`scripts/env-example-check.py` 双向判，并给白名单加"必须写理由 + 名单里的键必须仍被读取"
两条自检（防止名单腐烂成护身符）。

### 19.5 `HANDOFF.md` 退役为薄指针（含勘误）

`HANDOFF.md` 作为"第二真相源"已腐烂 6 周（停在 2026-08-01）。**决策：不重写，退役成指针** ——
理由不是"它写错了"，而是**它没有触发条件**：没有判据、没有流程在它过期时报错。
新增判据：不得出现 40 位 commit hash 与测试计数；它指到的每个仓库内路径必须真实存在。

**勘误**：`api/index.py`「3000+ 行」这个数字在 5 份 phase report 里传播，
实测 **1621 行**，且从未为真（Phase 0 基线 1282 行）。不改写历史报告，改在此记一条，
并作为 7c 的输入 —— 拆分规模比文档暗示的小一半。

### 19.6 遗留（Phase 7 还剩三段）

| 段 | 内容 |
| --- | --- |
| **7b** | `/api/wf03/*` 后端路由去留（前端消费方已于 6b-1 归零）；`public/*.md` 15 份对公网可读的公开范围 |
| **7c** | `api/index.py` 拆分（实测 1621 行） |
| **7d** | `tools/` → `domain/` + `providers/` 归并（`dependency-map.md`「保留期不超过两个 Phase」已到期） |

**下一步**：Phase 7b。`D3`（单位/职位检索）期限 **2026-10-13** 不变。
