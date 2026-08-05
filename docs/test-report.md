---
title: 职业教练（career-coach）完整性测试报告
date: 2026-08-05
type: 测试报告
project: iCAN无代码开发挑战赛-DuMate方向
repository: zimo66067-wq/career-coach
status: 代码层完整可用（外部平台/真实密钥类验收待做）
tags:
  - iCAN
  - DuMate
  - AI求职面试教练
  - 测试报告
  - 完整性
  - 接口一致性
---

# 职业教练（career-coach）完整性测试报告

## 原始任务

读取设计路径与技术路径文档并汇总写入项目 `.md`；对照 GitHub 仓库实际代码逐项对比和测试，重点检查功能完整性、模块接口一致性、数据流程连贯性、前后端对接状况；优先完成未完成或需修改的代码，使项目在设计文档定义范围内完整可用；输出测试报告。

## 核心摘要

- 对照基准：PRD v1.0（F1-F4 四项 MVP、事实锁五条、性能门、验收门）+ workflows WF-01~06 合同 + contracts 四 Schema。
- 测试基线：**pytest 220 通过 / 4 跳过；Node 契约测试 7/7 通过；Schema 全量校验通过**。
- 2026-08-06 自动解决批次：能力矩阵证据回填、10 次自动化彩排、会话备份脚本、G9 可自动材料、语音 UI 契约测试、移动端截图（详见第六节）；Node 契约测试增至 9/9。
- 结论：GitHub main 与本地分支均不完整（main 缺 F2/F3/F4 接口与同意门；本地缺持久化与 F3/F4 实现）。已在 `codex/complete` 分支（基于 main）完成统一补全，四个 MVP 与六个工作流在后端、前端、测试三端闭合。
- 工作区：`C:\Users\Administrator\Documents\职业教练\career-coach-complete`（分支 `codex/complete`，基于 `origin/main` da5e41e）。原本地工作区未改动。

## 测试环境

| 项 | 值 |
|---|---|
| Python | 3.13.12（WorkBuddy venv，已补装 jieba 0.42.1、zhipuai 2.1.5、sniffio） |
| Node | v24.15.0 |
| 数据库 | SQLite（RESUME_DB_PATH 指向测试临时文件） |
| 覆盖 | tests/ 全量（契约/API/故障注入/端到端/语音/隐私）+ 4 个 Node 契约测试 |

## 一、设计文档要求 vs 实际实现对比

| 设计要求（PRD/WF） | GitHub main | 本地分支 | 统一后（codex/complete） |
|---|---|---|---|
| F1 简历诊断（上传→去标识化→诊断→R 分） | ✅（含 SQLite 持久化） | ✅（含同意门） | ✅ 两者合并 |
| F2 岗位匹配（JD 解析→确认→四态匹配→M 分） | ❌ wf03 接口被删 | ✅ | ✅ 恢复 + 持久化 |
| F3 模拟面试（≤5 题、每题≤1 追问、报告 I） | ❌ 无接口 | ❌ 501 桩 | ✅ 新增 wf04 start/answer/end |
| F4 能力报告（六维雷达、C0、七天计划） | ❌ 无接口 | ❌ 501 桩 | ✅ 新增 wf05 ability |
| WF-06 删除（DELETED 终态，不再调模型） | ❌ 无接口 | ❌ 501 桩 | ✅ 新增 wf06 delete + 数据清理 |
| 同意门（CONSENT→短时效令牌） | ❌ 被移除 | ✅ | ✅ 恢复 + 前端携带令牌 |
| 事实锁/Schema/证据回指 | ✅ | ✅ | ✅ 保留 |
| 语音增强（百度 ASR/TTS 备用通道 + 10s 文字回退） | ✅ | ❌ NotImplemented | ✅ 保留 main 实现 |
| 发布镜像 docs/ 与 public/ 一致 | ✅ | ✅ | ✅ test_publish_mirror 通过 |
| CI 严格门禁（pytest 失败即失败 + Node 测试） | ❌ pytest `\|\| true`、无 Node | ✅ | ✅ 恢复 |
| 设计文档存在性（PRD/架构/隐私/审查） | ❌ 被部署提交删除 | ❌ 同 | ✅ 恢复为 design-and-tech-path.md |

## 二、逐项检查结果

### 2.1 功能完整性

- F1：consent → upload（PDF/DOCX/TXT，10MB/20-20万字符）→ diagnose（主模型→备用→规则降级）→ R 复算 → 持久化。✅
- F2：wf03/upload（文件）、wf03/jd（JSON 或文件）、wf03/match（user_confirmed 必须 true）→ 四态 + 缺口 P0/P1/P2 + M 复算。✅
- F3：wf04/start（出题）→ answer（STAR 缺口、追问≤1、answer_quote 子串校验）→ end（报告 + I 分）。✅
- F4：wf05/ability 聚合已存 R/M/I → rescore 复算 C0/C7 → 六维雷达 + 7 天计划（恰好 7 条、30-45 分钟、含 artifact）。✅
- WF-06：wf06/delete 清除简历/诊断/匹配/面试/能力数据并返回 DELETED。✅

### 2.2 模块接口一致性

- 前端 data-bridge.js 端点表与后端路由表逐条对齐（wf01-06 + admin/health）。✅
- 同意令牌：前端 `X-Consent-Token` 头与后端 `require_consent()` 一致；OPTIONS 预检放行该头。✅
- 契约：resume-profile / job-profile / interview-turn / ability-profile 四 Schema 与前后端字段一致（validate_schema 全量通过）。✅
- F2 前端确认流程（job-upload.js）与后端 `user_confirmed=true` 业务规则一致。✅

### 2.3 数据流程连贯性

- 一次会话以 `session_id`（默认取 X-Trace-Id）贯穿 upload → diagnose → match → interview → ability → delete。✅
- 跨请求状态由 SQLite（matches / interview_sessions / abilities 表）承载；测试 `_full_flow` 验证同 session 完整闭环。✅
- 诊断无上传记录时自动补建占位简历行，保证 save_diagnosis 不静默丢失。✅

### 2.4 前端与后端对接

- f1/f2/f3/f4 页面 → data-bridge → 真实 API 路径可用；演示数据仅 `?demo=1`。✅
- docs/（GitHub Pages）与 public/ 镜像一致（job-upload.js、data-bridge.js、f2-match.html 等已同步）。✅
- CI 恢复 Node 契约测试（页面状态、上传流程、F2 流程、发布镜像）。✅

## 三、发现的问题与修复内容

| # | 问题 | 级别 | 修复 |
|---|---|---|---|
| 1 | GitHub main 删除 wf03（F2）接口，前端 jd-upload.js 调用的 `/api/wf03/jd` 不存在，F2 前后端断链 | P0 | 恢复 wf03/upload/jd/match，且 wf03/jd 兼容 JSON 与文件两种输入 |
| 2 | F3/F4（wf04/wf05）在 main 与本地均无接口实现 | P0 | 新增 wf04 start/answer/end、wf05 ability，基于 InterviewEngine + rescore + radar_adapter |
| 3 | main 移除同意令牌门，材料接口无 consent 校验 | P0 | 恢复 issue_consent/require_consent，前端 data-bridge 携带 X-Consent-Token |
| 4 | interview_engine 未把当前问题/追问写入会话，回合记录 question 为空 | P1 | next_question/submit_answer 持久化 `_current_question/_current_targets/_current_followup` |
| 5 | main 的 CI 用 `\|\| true` 吞掉 pytest 失败且删除 Node 契约测试 | P1 | 恢复严格门禁：全量 pytest 失败即失败 + node --test 4 个文件 |
| 6 | main 的 F2 前端只解析不出匹配（无确认态、不调 matchJD） | P1 | 恢复本地分支完整 job-upload.js + f2-match.html（确认→匹配→四态）并同步 docs 镜像 |
| 7 | 核心设计文档（PRD/架构/隐私/审查）被 GitHub Pages 部署提交覆盖删除 | P1 | 从 git 历史恢复核心内容，写入 docs/design-and-tech-path.md |
| 8 | main 缺少 test_job_upload.js / test_publish_mirror.js，发布镜像无自动化保障 | P1 | 恢复两个 Node 测试并纳入 CI |
| 9 | 测试环境缺 jieba / zhipuai / sniffio 导致测试无法收集 | P2 | 安装依赖（环境级，requirements.txt 已声明） |
| 10 | 本地分支 push-head-api.sh 硬编码 GitHub 令牌 | P1 | 确认 main 已改为 `${GITHUB_TOKEN:-}` 环境变量读取；保留该修复 |

## 四、验证通过的模块

- pytest 222 通过（4 跳过为需要外部密钥的 embedding 实测类）：
  - API 契约 20/20（consent/上传/诊断/降级/F2/F3/F4/F6/管理员/CORS）
  - contracts + rescore 对拍、故障注入、脱敏、提取、BM25、面试引擎、语音后端、隐私生命周期、端到端
- Node 契约测试 9/9：public page states、resume upload、job upload（F2）、publish mirror、voice UI
- Schema 校验：resume/ability fixtures VALID；CI 同款全量循环可用
- 真实模型 7×3 复测（2026-08-06，glm-4-flash）：21/21 成功（100%），降级 0
- Embedding 全量召回（2026-08-06，embedding-3）：2000 对样本召回率 91.0%（th=0.50）；集成召回 10 对召回率 83.8%、精确率 96.9%、F1 90.0%（证据验证器生效后，详见第七节）

## 五、遗留项（不在代码层，需外部资源/平台）

1. DuMate 平台六工作流实际搭建与截图（P0-02/P0-05，需平台操作）。
2. 语音实机五类用例（需麦克风/百度语音 token）。
3. G8 用户验证（5-8 人）与 G9 提交包冻结（PDF/MP4/10 次彩排）。
4. Vercel 部署后 `/tmp` 数据会随冷启动清空：生产如需长期留存，应接外部数据库或定期 admin/export。

> 说明：以上 1-3 均为外部资源型，无法在本机完全闭环；其中 G9 的可自动材料（简介/冻结清单/自动化彩排证据）已在第六节完成，PDF 方案与 MP4 演示仍需人工审定后生成。真实模型 7×3 复测与 embedding 全量召回已由用户提供 ZHIPU_API_KEY 在本机完成实测（见第七节）。

## 六、可自动解决部分执行结果（2026-08-06）

| 自动解决项 | 产物/结果 | 证据 |
|---|---|---|
| 能力矩阵证据回填 | N5/N8/N10/N12/N15/N17/N18、V3/V5 共 9 项由“待验证”改“已验证”（附自动化测试或实测报告）；汇总同步为 37/31 | docs/capability_matrix.md（已同步 public/） |
| 10 次自动化彩排 | 10/10 轮完整闭环无阻断（consent→diagnose→jd→match→interview→ability→delete） | deliverables/wf-evidence-20260806/rehearsal-10x.json |
| 会话数据自动备份 | 新增 scripts/backup-sessions.py，导出日期化 JSON，缓解 Vercel /tmp 丢数据 | deliverables/session-backup-20260806.json |
| G9 可自动材料 | 200 字项目简介、g9-submission-checklist.json（p0-07-freeze.py 已修复 gbk 编码并运行） | deliverables/200字项目简介.md、deliverables/wf-evidence-20260806/g9-submission-checklist.json |
| 语音 UI 契约测试 | 新增 tests/test_voice_ui.js（F3 语音 DOM/接线/10s 回退契约，docs 与 public 双镜像），2/2 通过并纳入 CI | node 9/9 通过 |
| 移动端截图 | scripts/capture_mobile_ui.py 生成 375×812 截图 10 张（含降级态，页面 JS 错误 0）；MT-3/4/5/8/9/10 回填为已验证 | deliverables/mobile-screenshots-20260806/ |
| README/文档一致性 | README 状态、目录导航、WF-01~06 端点与环境变量说明更新；docs 索引补新文档 | README.md、docs/index.md |

## 七、真实模型 7×3 复测与 embedding 全量召回（2026-08-06，ZHIPU_API_KEY 实测）

| 测试 | 范围 | 结果 | 证据 |
|---|---|---|---|
| P0-03 真实模型 7×3 复测 | 7 类任务 × 3 次，智谱 glm-4-flash | 21/21 成功（100%），降级 0，失败 0，总耗时 409.5s | deliverables/p0-03-evidence/p0-03-report-20260806_023311.json |
| Embedding 全量召回 | 2000 对句子（20 正样本 × 100 负样本），智谱 embedding-3 | 召回率 91.0%（th=0.50，precision 5.3%，F1 10.0%）；th=0.10~0.50 区间召回率均 ≥90% | deliverables/p0-03-evidence/embedding_full_recall_zhipu-3.json |
| 集成召回率 | 10 组 resume/job 端到端匹配（100 条要求），embedding-3 | 召回率 83.8%（31/37）、精确率 96.9%、F1 90.0%（修复前 100%/37.0%/54.0%） | deliverables/p0-03-evidence/integration_recall_zhipu_embedding_3.json |

发现的问题与修复：

1. 三个脚本在 Windows GBK 控制台下打印 Unicode 符号即崩溃 → 复测/召回运行前置 `PYTHONIOENCODING=utf-8`；`test_integration_recall.py` 已在子进程注入 UTF-8 环境，其他脚本在文档注明运行方式。
2. `test_integration_recall.py` 此前从未跑通，两处缺陷：a) job expected.json 无逐条覆盖真值 → 新建 `tests/fixtures-synthetic/ground-truth-labels.json`（10 对 × 100 条人工真值，covered/weak/missing）；b) 脚本把 JD 原文喂给匹配器 CLI，要求编号为 L 系列与真值 J/R/P/T 错位 → 改为传 job expected.json，编号统一。
3. 【已处理】embedding 匹配过匹配：修复前 100 条要求中 63 条误报（43 covered / 20 weak，精确率 37%），典型例：证据句是 Java 技能却判定「熟悉 HTML/CSS/JavaScript」为 covered。已在 `tools/match_requirements.py` 增加**证据验证器**（embedding 主路径）：
   - 证据句过滤：章节标题/过短句不作为证据；
   - Top-20 证据重排：从模型 Top 语义候选中选第一个有词级事实重叠的句子；
   - 词级验证：jieba 分词后要求与证据至少有一个"具体词"重叠（泛化词如 熟悉/熟练/了解、过泛词如 语言/测试/项目/数据 不计入）。
   修复后集成召回：精确率 37.0% → **96.9%**，F1 54.0% → **90.0%**，召回率 100% → 83.8%（7 个漏报中 4 个为"弱标注"边界、简历确无相关内容，3 个为同义改写型匹配如"输出报告↔周报""BI 工具↔Tableau"——词级验证器的设计边界，不强行放水）。真实模型链路与 2000 对全量召回（91.0%）不受影响。

## 行动项

- [x] 汇总设计路径与技术路径文档（docs/design-and-tech-path.md）
- [x] 统一后端 wf01-06 + 同意门 + 持久化 + 管理员接口
- [x] 统一前端（F2 确认流程、同意令牌、发布镜像）
- [x] 恢复严格 CI 与 Node 契约测试
- [x] 全量回归：pytest 220 通过、Node 7/7、Schema VALID
- [x] 2026-08-06 自动解决批次：矩阵回填、10 次彩排、备份脚本、G9 可自动材料、语音 UI 测试、移动端截图
- [x] 2026-08-06 真实模型 7×3 复测 + embedding 全量召回（智谱实测，证据见第七节）
- [x] 2026-08-06 embedding 过匹配处理：证据验证器 + 全量回归（pytest 222、Node 9/9、7×3、2000 对召回）
- [x] 提交 codex/complete 分支并推送（用户已确认）
- [ ] 平台与真实密钥类验收（见遗留项）

## 标签

`#iCAN` `#DuMate` `#AI求职面试教练` `#测试报告` `#完整性` `#接口一致性` `#pytest` `#GitHub`
