# architecture.md · career-coach 当前架构（Phase 0 只读审计）

- 生成日期：2026-09-13
- 基线 commit：`44986ac1159a0db53c8740f437a87ef675855a20`（`main`）
- **本文件只描述现状，不代表目标架构**；目标架构见 `docs/dependency-map.md` §5
- 配套：`docs/product-scope.md`（产品范围与裁决）、`docs/dependency-map.md`（依赖与缺陷清单）
- 历史文档：`docs/design/architecture.md`（62 行，2026-08 的四层架构描述，**已过期**，Phase 7 归并）

> **Phase 1 更新（2026-09-13）**：本次审计列出的全部 Phase 1 删除项已执行完毕，本文件中以下条目
> **只描述删除前的状态，不再代表现状**：
>
> | 审计条目 | 位置 | 现状 |
> | --- | --- | --- |
> | `public/pages/f2-match.html` | §2 | 已删除 |
> | `/api/f2/*`、`/api/f2_major`、`/api/tasks*` | §4 | 已删除（全部 404） |
> | `services/task_service.py`、`api/f2_major.py` | §5、§11 | 已删除 |
> | `tasks` 表 | §7 | 已从双方言 DDL 移除 + `init_db()` 幂等 drop |
> | `C7_low` / `C7_high` / `scenario_day7` | §4（wf05）、§7 | 已删除；只留 `C0` 与六维分作为当前证据快照 |
> | `public/pages/kb.html`、`js/kb.js`、`/api/knowledge/*` | §2、§4 | 已删除；`tools/knowledge.py` 保留为内部题库 |
> | `public/js/voice.js`、`tools/voice_handler.py`、`tools/providers/asr.py`、`/api/wf04/asr`、3 个 env | §4、§6、§12 | 已全部删除 |
> | `README:74` 列出 3 个语音 env | §14 | 已删除（README 同步修正） |
> | `/assets/:path*` → `/ui/assets/:path*` | §4 死路由 | 已修正为 `/public/assets/:path*`，favicon 恢复 |
>
> **Phase 2 更新（2026-09-14）**：领域层与数据层已建立，本文件以下结论随之改变 ——
>
> | 审计条目 | 位置 | 现状 |
> | --- | --- | --- |
> | "不存在 CareerProfile / CareerEvidence 实体" | §5、§7 | 已建立 `domain/`（纯规则）+ `repositories/`（唯一拼 SQL），双方言新增 9 张表 + `schema_migrations` |
> | `diagnosis_service` / `interview_service` 反向 import `api.index` | §3 依赖倒置 | **仍然存在**（2 处）。新的 domain/repositories 层不反向依赖 API，但既有 service 的重构属于 Phase 5，本轮未动 |
> | 表数量 20 张 | §7 | 30 张 |
> | 无 migration 机制 | §7 | 已有 `repositories/migrations.py`（版本化、幂等、`/api/health` 可观测） |
>
> 新增参考：`docs/domain-model.md`（领域模型与不变量）。
>
> **Phase 3 更新（2026-09-14）**：领域层已接到 HTTP 上 ——
>
> | 审计条目 | 位置 | 现状 |
> | --- | --- | --- |
> | "`api/index.py` 既是路由又是业务" | §4.1 | 仍在，但 Phase 3 新增的业务全部落在 `services/`，路由块只做校验与转发；拆分属 Phase 5 |
> | `js/job-upload.js` 无宿主页面 | §2 | ✅ **已解决（Phase 6b-1，2026-09-17）**：该脚本绑定的是 `/api/wf03/{upload,jd,match}`，只产匹配分数、产不出 Decision 与 Gap，无法支撑目标岗位工作区，故**退役**；替代实现是 `pages/target-job.html` + `js/target-job.js`（走 `/api/target-jobs` 与 `/api/actions`）。后端 `wf03` 路由保留，去留见 Phase 7 |
> | 迁移 2 条 | §7 | 3 条（新增 `2026-09-14-phase3-gap-blocking`） |
> | 表数量 30 张 | §7 | 30 张不变（只给 `gaps` 加了 `blocking` 列） |
>
> 新增 **11 条路由**：`/api/profile`、`/api/profile/evidence/*`（confirm/reject/edit/delete）、
> `/api/target-jobs/*`（CRUD + analyse + decision）。`vercel.json` 重写 36 → 41 条，
> 死路由校验仍为 0（静态目标全部存在、每条 `_route` 都有处理器）。
> 新增参考：`docs/phase3-report.md`。
>
> **现状口径**：主产品只剩一套匹配概念（`wf03` / `services/match_service.py`，DoD #6 达成）；
> dependency inversion 已由 3 处降为 **0 处**（Phase 5 修完并加静态门禁 `tests/test_layering.py`）；
> 一级导航 7 → **4** 项（Phase 6b-2 完成：去掉「首页」项，改由品牌区回首页；去代号的范围含 URL）；dead routes = 0。
> 仍有效的审计结论：`/api/admin/*`、`/api/f5/organizations/*` 无用户界面消费。
> **Phase 6a（2026-09-17）**：`ui/prototype` 陈旧分叉已**整树删除**，前端只剩 `public/`（canonical）与 `docs/`（发布镜像），
> 非 `.md` 文件由镜像门禁强制逐字节相同。
> **Phase 6b-3（2026-09-17）**：D7「进入即强制注册/登录」落地为 `js/auth-gate.js` 政策层
> （`decide()` / `plan()` 是纯函数，脱离 DOM 可断言）+ 原生 `<dialog>` 弹窗。登录态**只认服务端**
> `GET /api/auth/me`；拿不到答复（断网 / 5xx）判为**拦下**而非放行；强制态三层兜底关不掉。
> 豁免名单刻意只有 `public/pages/states.html`（内部 QA 状态墙）。服务端安全实现一行未改。
> 参考 `docs/phase6b3-report.md`。

---

## 1. 技术栈

| 层 | 技术 | 证据 |
| --- | --- | --- |
| 后端 | Python 3.11（CI）/ 本地 3.10.11；Flask + Werkzeug | `.github/workflows/ci.yml`、`api/index.py:130` |
| 部署 | Vercel Serverless Function，单一入口 `api/index.py`，`maxDuration: 60` | `vercel.json` |
| 数据 | SQLite（本地/测试）/ PostgreSQL（生产，`DATABASE_URL`）双方言 | `tools/database.py:21-23` |
| 模型 | 智谱 Chat（主）、千帆 V2 Chat（备）、千帆 Embedding | `tools/model_router.py:329/418`、`tools/match_requirements.py` |
| 前端 | 原生 ES5 风格 JS + 手写 CSS，无构建步骤、无框架、无包管理 | `public/js/*.js`、无 `package.json` |
| 静态托管 | Vercel 静态根 = `public/`（实测）；`docs/` 为 GitHub Pages 镜像 | 见 §12 |
| 图表 | ECharts 5.5（CDN + 本地 vendor 双路径） | `public/js/radar.js:3-4` |
| OCR | 可选 OCR provider（扫描件 PDF 兜底） | `tools/ocr_provider.py` |
| 测试 | pytest 9.0.3 + `node --test`；schema 校验 + 敏感扫描 + pip-audit | `ci.yml` |

**不存在**：`package.json`、`package-lock.json`、Dockerfile、`pyproject.toml`、make/CI 之外的构建脚本、`domain/` 层、`repositories/` 层。

---

## 2. 用户页面（快照：8 个 HTML）

> **审计基线与现状的差异（Phase 6b，2026-09-17）**：下表是审计当时的快照，其行数/导航列已不再逐字成立 —— Phase 1 删掉 `f2-match.html` 并从导航移除，Phase 6a 删掉 `ui/` 整树与 `kb.html` 入口，**Phase 6b-2 把一级导航收敛为 4 个工作区（简历证据 / 目标岗位 / 模拟面试 / 行动闭环），首页改由品牌区进入，并给 4 个页面换了不带 F 代号的文件名**。当前页面清单以 `public/README.md` 的表格为准；下表中已改名的行按新路径列出，`f2-match.html` / `kb.html` 两行留作审计记录。

| 页面 | 行数 | 作用 | 是否进导航 |
| --- | --- | --- | --- |
| `public/index.html` | 127 | 落地页 + 快速演示 | ✅ 首页 |
| `public/pages/resume-evidence.html` | 235 | 简历上传 / 粘贴 / 诊断 / 改写 | ✅ 简历证据 |
| ~~`public/pages/f2-match.html`~~ | 214 | ~~专业选择 → 画像 → 匹配 / JD 匹配~~ | **已删除（Phase 1）** |
| `public/pages/interview-practice.html` | 296 | 文字模拟面试（含追问） | ✅ 模拟面试 |
| `public/pages/action-loop.html` | 483 | 能力报告 + 雷达图 + 行动闭环（缺口 → 行动 → 复测） | ✅ 行动闭环 |
| `public/pages/job-apply.html` | 138 | 求职信（接地到当前目标岗位）+ 申请跟踪 + 单位检索边界 | ⛔（二级页，由目标岗位/行动闭环链入） |
| ~~`public/pages/kb.html`~~ | 105 | ~~面经知识库（BM25/向量）~~ | **已删除（Phase 6a 入口下线，题库下沉为面试引擎内部数据源）** |
| `public/pages/states.html` | 116 | 空/加载/错误态样例 | ❌ |

页面脚本装配（实测 `<script>` 标签）：`app.js`（壳/导航）+ `pages-api-config.js`（1 常量）+ `data-bridge.js`（唯一 API 客户端）+ `account.js`（账号机制）+ `auth-gate.js`（D7 门禁政策）+ 页面专属脚本。

`public/js/voice.js`（318 行）**不被任何页面加载**；Phase 6b-2 时该文件已不在 `public/js/` 中（`ls public/js/` 无此项）。

---

## 3. API Route（40 条本地路由，48 条 Vercel 重写）

全部经 `api/index.py::route_api()` 单函数分发；Vercel 用 `? _route=` 重写把路径映射进来。

| 分组 | 路由 | 备注 |
| --- | --- | --- |
| 同意门 | `POST /api/wf01/consent` | 签发短时同意令牌，写操作前置 |
| 简历 | `POST /api/wf01/upload`、`POST /api/wf02/diagnose` | |
| 简历改写 | `POST /api/wf02/optimize`、`POST /api/wf02/apply-rewrite` | |
| JD | `POST /api/wf03/upload`、`/jd`、`/match` | 四态匹配主链路 |
| 面试 | `POST /api/wf04/start`、`/answer`、`/end`、`/stream` | `/stream` 为 SSE |
| 面试语音 | `POST /api/wf04/asr` | **死路由**（前端 0 引用） |
| 能力 | `POST /api/wf05/ability` | 返回含 `C7_low`/`C7_high` |
| 删除 | `POST /api/wf06/delete` | 会话级删除闭环 |
| 投递 | `POST /api/wf07/cover-letter`、`GET/POST/DELETE /api/wf07/applications` | |
| 专业匹配 | `GET /api/f2/health`、`/majors/tree`、`/majors/search`、`/majors/<code>`、`/intent`；`POST /api/f2/match` | **与 wf03 概念冲突** |
| 退休垫片 | `/api/f2_major` → `retired/f2-major` | 恒 404 |
| 单位检索 | `GET /api/f5/organizations/{status,suggest,detail,jobs}`、`POST .../discover` | 索引恒空 |
| 知识库 | `GET /api/knowledge/search`、`/questions` | |
| 账号 | `POST /api/auth/{register,login,logout}`、`GET /api/auth/me` | |
| 历史 | `GET/POST/DELETE /api/history`、`/api/history/<id>` | |
| 任务 | `GET/POST /api/tasks`、`/api/tasks/<id>`、`POST /api/tasks/<id>/next` | 仅服务 F2 大文件匹配 |
| 运维 | `GET /api/health`、`/api/admin/resumes`、`/api/admin/export` | admin 需 `X-Admin-Password` |

**前端实际消费 15 个端点**（`public/js/data-bridge.js:12` 的 `ENDPOINTS` 映射 + `account.js` + `kb.js`）：

```
uploadResume / uploadJD / diagnoseResume / submitJD / matchJD
startInterview / submitAnswer / endInterview / getAbility / deleteData
consent / coverLetter / applications / majorMatch / tasks
```

→ `/api/wf04/asr`、`/api/f2_major`、`/api/admin/*`、`/api/health`、`/api/f2/health`、`/api/f5/organizations/*` 均无用户界面消费。

---

## 4. Service 层（7 个文件 / 1593 行）

| Service | 行数 | 职责 | 对外函数 |
| --- | --- | --- | --- |
| `diagnosis_service.py` | 363 | 简历诊断编排、模型/规则降级 | `diagnose_resume` |
| `match_service.py` | 353 | JD 解析、四态匹配、低分分析 | `build_job_profile`、`validate_job_profile`、`match_job_profile` |
| `interview_service.py` | 358 | 面试会话、SSE 编排、能力报告 | `start_interview`、`answer_interview`、`end_interview`、`build_ability_profile`、`_advance_interview` |
| `apply_service.py` | 152 | 求职信生成、申请 CRUD | `generate_cover_letter`、`create_application`、`list_applications_for`、`delete_application` |
| `organization_service.py` | 204 | F5 索引与 provider 状态 | `provider_status`、`suggest_organizations`、`discover_organizations`、`get_organization`、`list_jobs_for`、`ingest_organizations` |
| `task_service.py` | 153 | 异步任务分片（F2 大文件匹配） | `_f2_match_chunk` 等 |
| `__init__.py` | 10 | 包声明 | — |

**Service 层缺陷**：3 处反向依赖 API（见 `dependency-map.md` §3.1）；`interview_service` 同时承担会话编排与能力报告两个职责。

---

## 5. Domain / Data Model

**当前没有 domain 层。** 领域概念散落在 Service 与 tools 中，以 `dict` 传递，靠 `contracts/*.json` 做形状校验。

### 5.1 现有契约（4 个 JSON Schema）

| Schema | 行数 | 运行时代码加载 | 用途 |
| --- | --- | --- | --- |
| `resume-profile.schema.json` | 77 | ✅ `tools/contracts.py:25` | ResumeProfile |
| `job-profile.schema.json` | 63 | ✅ `tools/contracts.py:30` | JobProfile |
| `interview-turn.schema.json` | 55 | ❌ 仅 CI + 测试 | InterviewTurn |
| `ability-profile.schema.json` | 72 | ❌ 仅 CI + 测试 | AbilityProfile |

`contracts/scoring.md`(116) 是 R/M/I/C0/C7 的唯一执行口径文档，`tools/rescore.py` 是其实现。

### 5.2 领域实体现状

| 目标实体（Phase 2） | 现状 |
| --- | --- |
| `CareerProfile` | **不存在** |
| `CareerEvidence` | **不存在**（简历证据只以 `source_spans` 片段存在于诊断 JSON 内） |
| `TargetJob` | 部分：`job_profile` dict + `matches` 表 |
| `EvidenceMatch` / `Gap` | 部分：`requirements[].status` 四态 + `gaps[]` |
| `Decision`（APPLY/STRETCH/PASS） | **不存在** |
| `InterviewSession` | ✅ `interview_sessions` 表 |
| `Action` / `Task` / `Artifact` / `Outcome` | **不存在**（有 `tasks` 表但是异步作业，不是用户行动） |
| `Application` | ✅ `applications` 表（仅 status 单字段） |

---

## 6. Provider

| Provider | 文件 | 行数 | 选择方式 | 默认 | 消费者 |
| --- | --- | --- | --- | --- | --- |
| 模型（Chat） | `tools/model_router.py` + `tools/providers/model.py` | 512 + 74 | `DUMATE_MODEL` | 智谱 → 千帆 → 规则降级 | diagnosis / interview / optimizer / apply |
| Embedding | `tools/match_requirements.py` | 554 | `QIANFAN_EMBEDDING_AK/SK` | BM25 | F2/F3 匹配 |
| ASR | `tools/providers/asr.py` | 113 | `ASR_PROVIDER` | mock | **仅死路由 + voice_handler** |
| OCR | `tools/ocr_provider.py` | 173 | — | 关闭 | 扫描件 PDF 上传 |
| Organization | `tools/providers/organization.py` | 112 | `ORG_DATA_PROVIDER` | `unconfigured`（永不返回数据） | F5 索引 |

**缺陷**：`build_model_router` 在 `tools/providers/model.py` 与 `api/index.py` 各有一份（见 `dependency-map.md` §3.2）。

---

## 7. Database Table（20 张）

| 分组 | 表 |
| --- | --- |
| 简历与诊断 | `resumes`、`diagnoses`、`resume_rewrites` |
| 匹配 | `matches` |
| 面试 | `interview_sessions`、`abilities` |
| 用户与权限 | `users`、`sessions`、`session_owners` |
| 历史与配额 | `history_events`、`usage_events` |
| 异步任务 | `tasks` |
| 投递 | `applications` |
| **F5 单位/职位（恒空）** | `organizations`、`organization_aliases`、`organization_profiles`、`source_snapshots`、`job_postings`、`job_posting_versions`、`job_embeddings` |

`tools/database.py` 1579 行同时承担：双方言连接、建表 DDL（SQLite 与 PostgreSQL 各一份，**手工保持同步**）、全部 CRUD。

---

## 8. AI 调用路径

```
route_api
 └── services/*  ──► tools/providers/model.build_model_router() 或 api.index.build_model_router()
      └── ModelRouter.call(task_name, user_input, context?)
           ├── 载入 prompts/<task>.md（冻结提示词）
           ├── ZhipuModelRouter._try_call   （ZHIPU_API_KEY）
           ├── QianfanModelRouter._try_call （QIANFAN_API_KEY）
           └── 失败 → status != success → 调用方走规则降级
```

**9 个声明的 task key，仅 4 个被调用**：

| task key | prompt 文件 | 调用点 |
| --- | --- | --- |
| `resume_diagnosis` | `prompts/resume/diagnose.md` | `services/diagnosis_service.py:327` |
| `resume_rewrite` | `prompts/resume/rewrite.md` | `tools/optimizer.py:113` |
| `interview_question` | `prompts/interview/interviewer.md` | `tools/interview_engine.py:247` |
| `cover_letter` | `prompts/apply/cover-letter.md` | `services/apply_service.py:87` |
| `resume_report` | `prompts/resume/report-deep.md` | **无** |
| `jd_extract` | `prompts/match/jd-extract.md` | **无** |
| `jd_match_explain` | `prompts/match/explain.md` | **无** |
| `interview_review` | `prompts/interview/review.md` | **无** |
| `seven_day_plan` | `prompts/plan/seven-day.md` | **无** |

另有非 `ModelRouter` 的模型调用：`tools/match_requirements.py` 的 Embedding（千帆）。

**降级策略现状**：每个 AI 能力都有规则兜底（诊断走规则评分、面试走题库、求职信走模板、匹配走 BM25），即 DoD #21 大体已满足，但缺自动化断言。

---

## 9. 数据流

### 9.1 主链路（现状）

```
① 上传        浏览器 → POST /api/wf01/upload（multipart）
              → extract_text/ocr → deidentify（PII 脱除）→ upload_security 校验
              → INSERT resumes → 返回 session_id + resumeText

② 诊断        浏览器 → POST /api/wf02/diagnose {resumeText, session_id}
              → diagnosis_service → ModelRouter("resume_diagnosis") → 失败则规则评分
              → validate_schema.business_rules → INSERT diagnoses（含 source_spans）
              → 返回 resumeProfile(subscores + suggestions)

③ 匹配        (a) 浏览器 → POST /api/wf03/jd → job_profile
              (b) → POST /api/wf03/match {resumeText, jobProfile}
                  或 POST /api/f2/match {majorCode, resumeText, jdText}
              → INSERT matches → 返回 requirements 四态 + gaps + score_M

④ 面试        → POST /api/wf04/start {jobProfile, resumeProfile, matchGaps}
              → InterviewEngine.start → next_question（模型生成 / 题库降级）
              → POST /api/wf04/stream（SSE）逐字返回题目 + done 事件
              → submit_answer → STAR 缺口 → 追问（≤1/题）→ 下一题（≤5 主问题）
              → POST /api/wf04/end → end_session → report + score_I + turns
              → update_session 持久化

⑤ 能力        → POST /api/wf05/ability {session_id}
              → build_ability_profile 聚合 R/M/I → rescore.compute → C0 + C7_low/high
              → INSERT abilities → 返回 6 维 + radar_option

⑥ 投递        → POST /api/wf07/cover-letter → 读 F1 诊断 → 模型/模板 → pending_confirm
              → POST /api/wf07/applications（人工确认后落库）

⑦ 删除        → POST /api/wf06/delete → 会话级级联删除
```

### 9.2 关键数据边界

- PII 在 `wf01/upload` 阶段脱除；模型输入为脱敏文本；`_deidentify_answer` 对面试回答二次脱敏。
- 所有写请求需 `X-Consent-Token`（`wf01/consent` 签发，`DUMATE_CONSENT_SECRET` HMAC）。
- 会话归属经 `session_owners` 做 owner isolation；跨 owner 访问返回 404。
- 限流按 `owner_key` + 时间桶写入 `usage_events`。

---

## 10. 模块依赖关系

见 `docs/dependency-map.md`（含实测依赖边、3 处依赖倒置、2 套重复匹配实现、目标结构）。

---

## 11. 测试覆盖情况（Phase 0 基线）

### 11.1 规模

| 项 | 数量 |
| --- | --- |
| pytest 文件 | 37 |
| node 契约文件 | 12 |
| 测试 fixture | `tests/fixtures-synthetic/`（resumes / jobs / interviews / abilities / edge-cases / sensitive） |
| 文档型目录混入 | `tests/acceptance/`、`tests/rehearsal/`、`tests/user-research/` 各只有 1 个 .md |

### 11.2 执行基线（2026-09-13 实测）

```
pytest tests/ -q                      436 passed in 167.66s
node --test tests/*.js                 52 passed
pip-audit -r requirements.txt          无已知漏洞
pip-audit -r tools/requirements.txt    无已知漏洞
schema validation（4 类 fixture）      通过
sensitive scan（tracked+untracked）    无命中
git diff --check                       通过
```

### 11.3 覆盖率基线（`--cov=api --cov=services --cov=tools`）

**总体：79%**（5044 statements / 1074 missing）。目标 ≥85%，**缺口 6 个百分点**。

| 模块 | 覆盖 | 目标 | 判定 |
| --- | --- | --- | --- |
| `services/match_service.py` | 93% | 90% | ✅ |
| `tools/interview_engine.py` | 90% | 90% | ✅ |
| `services/task_service.py` | 90% | — | ✅ |
| `api/f2_major.py` | 91% | — | ✅ |
| `tools/model_router.py` | 93% | — | ✅ |
| `tools/knowledge.py` | 96% | — | ✅ |
| `services/apply_service.py` | 89% | 90% | ⚠️ −1 |
| `services/interview_service.py` | 88% | 90% | ⚠️ −2 |
| `api/index.py` | 86% | — | ⚠️ |
| `tools/account.py` | 86% | — | ⚠️ |
| `tools/database.py` | 85% | — | ⚠️ |
| `services/organization_service.py` | 81% | — | ⚠️（待下线） |
| `services/diagnosis_service.py` | 77% | 90% | ❌ −13 |
| `tools/upload_security.py` | 80% | — | ❌ |
| `tools/privacy_lifecycle.py` | 64% | — | ❌ |
| `tools/rescore.py` | 64% | — | ❌ |
| `tools/deidentify.py` | 63% | — | ❌ |
| `tools/log_sanitize.py` | 61% | — | ❌ |
| `tools/extract_text.py` | 59% | — | ❌ |
| `tools/radar_adapter.py` | 59% | — | ❌（待重构） |
| `tools/match_requirements.py` | 58% | — | ❌ |
| `tools/providers/asr.py` | 51% | — | 待删除 |
| `tools/ocr_provider.py` | 42% | — | ❌ |
| `tools/voice_handler.py` | 39% | — | 待删除 |
| `tools/validate_schema.py` | 38% | — | ❌ |
| `tools/redflag.py` | **19%** | — | ❌ 最低 |

**核心模块达标情况**（Career Evidence / Target Job Analysis / Interview / Application）：
`Interview` 与 `Application` 已接近或达标；**`Career Evidence` 与 `Target Job Analysis` 尚不存在实体**，Phase 2/3 新建时须同步达到 90%。

**JS 覆盖率：0%** —— 无 JS 覆盖率工具，12 个 node 测试均为契约型（结构/接线断言），不测执行分支。目标 75% 需引入 `c8`/`nyc`。

### 11.4 覆盖率测量口径说明

- 本地 venv 为 Python **3.10.11**，CI 为 **3.11** → 覆盖率数字可能有轻微偏差，Phase 15 需在 CI 同版本复测。
- `pytest-cov` 为本次基线测量临时安装，**尚未进入 `requirements.txt`**（Phase 15 正式引入）。

---

## 12. 配置与部署结构

### 12.1 `vercel.json`

| 键 | 内容 |
| --- | --- |
| `functions` | `api/index.py` → `maxDuration: 60` |
| `headers` | 全局 CSP（`script-src 'self' 'unsafe-inline' cdn.jsdelivr.net`；`connect-src 'self' + 生产域名`） |
| `rewrites` | **48 条**：40 条 `/api/* → /api?_route=*`，6 条静态（`/`、`/index.html`、`/css/:path*`、`/js/:path*`、`/pages/:path*`、`/assets/:path*`），2 条其他 |

**无 `outputDirectory`、无 `.vercelignore`。**

### 12.2 静态托管真相（实测，与文档描述不一致）

| 事实 | 证据 |
| --- | --- |
| Vercel 静态根是 **`public/`** | `/capability_matrix.md` → 200；`/public/index.html` → 404 |
| `ui/` **不在部署内** | `/ui/assets/favicon.svg` → **404** |
| 因此 `/assets/:path* → /ui/assets/:path*` 重写 **是坏的** | `/assets/favicon.svg`、`/logo.svg`、`/vendor/echarts.min.js` 全部 **404** |
| 后果 1 | 所有 8 个页面的 `<link rel="icon" href=".../assets/favicon.svg">` **线上 404** |
| 后果 2 | radar.js 的「本地 vendor 兜底」**永远 404**，只剩 CDN 路径可用 |
| `public/` 内所有文件公网可读 | `/observability.md`、`/capability_matrix.md`、`/dumate-workflow-sop.md`、`/defense-evidence-index.md`、`/README.md`、`/voice-test-checklist.md`、`/blind-test-results/*` 均 200 |

### 12.3 环境变量（`.env.example`，171 行）

- 声明 **28 行 / 22 个唯一变量**；**4 个变量重复声明**：`DUMATE_CONSENT_SECRET`×3、`DUMATE_CONSENT_MAX_AGE_SECONDS`×3、`ZHIPU_API_KEY`×2、`ZHIPU_BASE_URL`×2。
- 文件第 30 行有一处**未注释的 `====` 分隔线**（会导致该行被当成非法内容）。
- **2 个变量无任何消费者**：`LOG_LEVEL`、`ENV`。
- **3 个语音变量**：`ASR_API_URL`、`TTS_API_URL`、`BAIDU_SPEECH_TOKEN`（随语音链路删除）。
- 头部「环境变量模板 (P1-07)」注释块**出现两次**。
- 完整变量→消费者矩阵与 `ENVIRONMENT.md` 的生成工作属 Phase 14。

### 12.4 GitHub 侧

| 项 | 状态 |
| --- | --- |
| 分支保护 | `main` **未开启**保护（API 返回 `Branch not protected`），账号有 admin 权限 |
| CI | `.github/workflows/ci.yml`：checkout → py3.11 → 装依赖 → pytest → node 20 契约 → schema 校验 → 敏感扫描 → pip-audit。**只在 `push: main` 或 `pull_request → main` 触发** |
| Pages | `pages-build-deployment` 从 `main` 构建 `docs/` |
| 远端残留分支 | `agent/*`×3、`codex/complete`、`codex/complete-blockers-security-2026-09-08`、`eng-hardening-2026-08-03` |

---

## 13. 文档与代码不一致清单

| # | 文档说法 | 代码/线上事实 |
| --- | --- | --- |
| 1 | `README.md:3`「pytest 220 通过 / 4 跳过，Node 契约 7/7」 | 早已更新为 **482 passed / 42 node**（2026-09-17）；本行滞后于 README 本身 |
| 2 | `README.md:26-29` 把 F1–F5 作为产品功能表 | 与「取消用户可见 F1-F5」的目标直接冲突 |
| 3 | `README.md:32`「F4 七天结果称『情景推演』不得称『预测』」 | 预测能力本身仍在（`C7_low/high` + 0.3/0.7 参数） |
| 4 | `README.md:74` 列出 `ASR_API_URL / TTS_API_URL / BAIDU_SPEECH_TOKEN` | 语音链路已死 |
| 5 | `docs/design/architecture.md`（62 行）描述四层架构 | 实际无 domain/repositories 层；3 处依赖倒置**已由 Phase 5 降为 0 处**并加静态门禁 |
| 6 | `vercel.json` 把 `/assets/*` 重写到 `ui/assets/*` | ✅ **已修**：改重写到 `/public/assets/:path*`，`assets/` 已纳入两棵发布树并有镜像门禁 */
| 7 | `scripts/sync_sidebar.py` 说 `ui/prototype` 是 sidebar 的 source of truth | ✅ **已修（Phase 6a）**：改为 `public/` 为唯一源；`ui/` 整树已删；脚本的 `PAGES` 还漏了 `pages/f5-apply.html`，一并补上 |
| 8 | `docs/design/privacy.md` 与 `SECURITY.md` 描述日志脱敏 | 需在 Phase 7 逐条复核（本次未验证） |
| 9 | `contracts/*.schema.json` 共 4 个 | 只有 2 个被运行时加载，另 2 个仅 CI 使用 |
| 10 | `CHANGELOG.md` 多条仍写「commit hash 待回填」 | 历史提交已完成 |
| 11 | `public/README.md` 与 `docs/README.md` 整篇是 `ui/prototype` 的自述 | ✅ **已修（Phase 6a）**：两棵树的自述重写为发布树说明；原文还列着 Phase 1 已删的 `pages/kb.html`、C7 区间带、七天计划 |

---

## 14. Phase 0 结论

审计确认可执行，且**删除面大于新增面**。优先级排序（按用户价值/风险）：

1. **Phase 1（删除）**：语音链路整条（前端 0 引用 + 死路由 + 2 模块 + 3 env + 脚本 + 文档 + 相关测试）、`C7_low/high` 预测、KB 一级导航、F2 一级入口、`/api/f2_major` 退休垫片、`ui/prototype` 死树、4 个一次性推送脚本、5 个未调用 prompt、2 个孤儿 env。
2. **Phase 2–4（领域）**：新建 CareerEvidence / TargetJob / Decision / Action，打通 `Evidence → Target Job → APPLY/STRETCH/PASS → Interview → Action → Outcome`。
3. **Phase 5–6（结构）**：拆 `api/index.py`、修 3 处依赖倒置、统一 provider、前端单一 canonical + 构建脚本、导航收敛到 4 项。
4. **Phase 7–8（清理与验证）**：dead code / env / 镜像 / README 收口，覆盖率补到 85%/90%/75%。

阻塞项：`docs/product-scope.md` §8 的 6 个决策点（D1–D6），其中 **D1（Major Match 去留）** 直接决定 Phase 1 删除范围。
