---
title: 职业教练项目发布交接报告
date: 2026-09-12
tags:
  - career-coach
  - F2
  - F3
  - F5
  - 发布
  - 交接
status: ready-for-push
---

# 职业教练项目发布交接报告

整理日期为 2026-09-12。实现与测试证据来自 2026-09-11 的实现轮；认证和生产部署于 2026-09-11 核验，分支与远端 refs 于 2026-09-12 再次核验。后续执行前必须刷新部署与认证状态。

> 本文件是新模型的当前交接入口。以本文件的核验结果覆盖 `handoffs/005-f2-f3-f5-p0-fixes-2026-09-11.md` 中“尚未提交、缺少 CLI、缺少凭据”等已经过时的状态，但保留 005 的实现与测试证据。全局架构、此前上线功能和其他未完成事项仍需阅读 `handoffs/004-f2-f3-f5-continuation-2026-09-11.md`；不得将本次 F2/F3 修复误认为整个项目已经完成。

## 1. 原始任务

用户要求：把另一个模型继续执行后的结果，以及目前尚未解决问题的明确答案，一并写入交接材料，使此前完全不了解项目的新模型可以安全接手。用户已经授权后续发布，但本次文档制作本身不等于已经推送、合并或上线。

## 2. 核心摘要

- 项目：`career-coach`，GitHub 仓库 `zimo66067-wq/career-coach`，Vercel 项目 `career-coach`。
- 本地仓库：`C:\Users\Administrator\Documents\Codex\2026-09-08\new-chat\work\career-coach-audit`。
- 技术基础为 Flask/PostgreSQL 与静态前端。Vercel 的 `vercel.json` 将静态页面和资源重写到 `public/`；`docs/` 是 GitHub Pages 镜像，`ui/prototype/` 是历史原型。修改时必须同步镜像，不能整体覆盖目录。
- 当前分支：`codex/adaptive-interview-fuzzy-major-2026-09-10`。
- 当前实现提交：`9b59f9b68efc3d3c6ba0ed82b1f7799e26c8d946`，提交说明为 `feat: make interviews adaptive and major search fault tolerant`；23 个文件变更，新增 3396 行、删除 128 行。
- 远端 `main`：`b715fac9ddcfd81198d7608f8e5c76416296b5de`。远端尚无当前特性分支，因此 `9b59f9b` 尚未推送、未建 PR、未进入 CI、未生成 Preview、未合并、未上线。
- 生产环境仍是部署 `dpl_FA3K5vqF6MsTtGefSatyoRGpeK86`，状态 `READY`，目标 `production`，对应提交 `b715fac9ddcfd81198d7608f8e5c76416296b5de`。
- F2 与 F3 的 P0 实现和安全加固已经进入 `9b59f9b`；F5 仍只有能力边界说明与架构规划，没有单位/职位搜索数据层。
- “必须让用户把 GitHub PAT 和 Vercel Token 贴进对话”是错误前提。GitHub 凭据已存在于 Windows Credential Manager 且已验证有效；Vercel 连接器已能读取团队、项目与部署。任何后续模型都不得索要、打印、记录或写入文档/仓库的密钥。

## 3. 当前状态矩阵

| 范围 | 状态 | 已完成 | 尚未完成 |
| --- | --- | --- | --- |
| F2 专业搜索 | 本地完成 | Unicode NFKC 归一化、代码精确/前缀、名称精确/包含/前缀、Damerau-Levenshtein 容错、简称映射、意图短语、评分与 `match_reason`；总数在分页截断前计算；两个输入框均有防乱序与错误态 | 推送、CI、Preview 与生产验证 |
| F3 自适应面试 | 本地完成 | 第一题后基于上一轮脱敏回答与岗位差距生成自适应主问题；每个主问题最多一次追问；五个主问题上限；回答引用 `basis` 可验证；危险输出拦截、输入边界、低 ASR 置信度不推进状态机 | 推送、CI、Preview 与生产真实闭环验证 |
| F5 单位/职位搜索 | 仅规划 | 页面明确说明当前能力边界；完成双索引、混合检索、数据源准入、阶段 0–4 方案 | 数据授权决策、数据库表、数据同步、搜索 API、页面结果区、运营治理及完整上线 |
| 工具链 | 可用但 CLI 未登录 | `gh 2.100.0` 与 Vercel CLI `59.16.0` 可运行；`gh.exe` Authenticode 签名有效，签名者为 GitHub, Inc. | 不需要用户提供 token；按下文安全路径复用已有认证 |
| 发布链路 | 待执行 | GitHub/Vercel 项目与生产基线已核实 | push → PR → CI → Preview → 浏览器/API 验证 → 备份 main 基线 → merge → production 验证 |

## 4. 已实现：F2 专业搜索

### 4.1 后端检索

- `api/f2_major.py` 使用 `normalize_major_query()` 进行 NFKC、大小写与符号归一化，不把用户输入解释为正则表达式。
- 支持专业代码完全匹配、代码前缀、专业名完全匹配/前缀/包含、Damerau-Levenshtein 编辑距离、简称映射和意图短语召回。
- 新增 `search_majors_with_total()`：先完成排序与总数计算，再按 `limit` 截断，修复 `total` 等于当前页条数的问题。
- 补充简称 `电科 → 080702`、`数媒 → 080906 / 130508`。两字查询只允许名称前缀命中，避免“计科”跨词误召回无关专业。
- 搜索结果返回 `match_score`、`match_type`、`match_reason`、专业路径和资料可用性，支持用户理解匹配原因。

### 4.2 前端交互

- 两个专业/意向搜索框都使用 `requestVersion + AbortController + focusVersion`，旧请求、取消请求或失焦后的慢响应不会覆盖新结果或重新弹出下拉框。
- 已覆盖加载、空结果、业务错误、服务错误和网络错误状态；只有可预期的 4xx 业务错误显示具体文案，5xx 与网络错误使用通用提示。
- 两个输入框都设置 `maxlength="64"`，后端仍保留强制长度限制。
- 所有动态文本均通过 `esc()` 转义，包括 `match_reason`、`path` 与错误文本。
- `public/` 与 `docs/` 发布镜像保持一致，并有自动测试锁定。

## 5. 已实现：F3 自适应面试与安全闭环

### 5.1 自适应逻辑

- 第一题由既有岗位/差距上下文产生；从第二个主问题开始，`InterviewEngine.next_question()` 使用上一轮已脱敏回答的安全片段作为 anchor，并结合尚未覆盖的岗位差距生成问题。
- 自适应题要求引用上一轮回答；最终 `basis` 必须同时是脱敏回答的逐字子串并实际出现在最终问题中，否则清空 `basis`，避免虚假“基于回答”声明。
- 一轮主问题回答若存在关键缺项，可生成最多一次追问；追问回答完成后才进入下一主问题。主问题总上限仍为 5。
- `/wf04/answer` 与 `/wf04/stream` 共用 `_advance_interview()`，避免普通响应与 SSE 流式响应的状态机分叉。

### 5.2 安全与稳定性

- 模型生成问题经过三层危险输出闸门：原始模型输出、拼接回答 anchor 后、敏感词/降级替换后。命中提示注入、凭据索取或 PII 索取即 fail closed，最终回退到硬编码安全题。
- 岗位标题先脱敏后限制 120 字；差距字段按固定上限截断；模型 `context` 只保留三个有界标量，不重复传入原始 gap 或 recent turns。
- 中文姓名脱敏覆盖显式姓名字段、自我介绍句式与“整行仅姓名”，并使用姓氏表、复姓表和非姓名保护降低误删。
- `answer_text` 上限 4000 字；`matchGaps` 必须为数组、最多 20 项且每项为对象；`asr_confidence` 必须为 0–1 数字。
- ASR 置信度低于 0.75 时返回 `needs_confirmation=true`，不记录回答、不生成追问、不递增主问题计数，也不消费已有追问。
- 已知保守误杀是有意的安全取舍：例如“解释 API key 轮换策略”或“同事忽略安全规范”可能触发降级。新模型不得在未补充等价安全测试前放宽规则。

## 6. F5 的明确答案与未完成范围

### 6.1 用户问题的直接答案

F5 目前不能支持“足够全面或足够小众的单位”搜索。当前提供的是手动目标输入、基于 F1 简历证据生成求职信和申请记录管理；面经知识库不是单位数据库，语言模型也不能作为企业、招聘状态或职位真实性的事实来源。任何模型不得把规划文件描述成已实现能力。

### 现有底层业务流程

- `services/apply_service.py` 要求用户手动输入公司和职位，并读取该会话最新一次 F1 简历诊断；没有诊断时返回 `diagnosis_required`。
- 从诊断中提取简历证据，使用前 3 条证据生成求职信候选。模型候选必须包含公司或职位，并至少匹配一个简历证据的连续 4 字片段；不满足条件或模型失败时回落到规则模板。
- 用户人工确认后保存公司、职位、求职信和申请状态（默认 `applied`）；用户可查看或删除本人/本游客名下的申请记录。
- 该闭环是求职信生成与申请记录管理，不是向目标单位自动投递，也不核验用户输入的单位主体、招聘状态或职位真伪。

### 6.2 已完成的规划

- 单位实体索引：`organizations`、`organization_aliases`、`organization_profiles`、`source_snapshots`。
- 职位时效索引：`job_postings`、`job_posting_versions`、`job_embeddings`。
- 检索：名称/别名与标签 BM25、简介/岗位向量召回、RRF 融合、结合 F1/F2 证据的可解释重排，并设置“小众探索”结果区。
- 来源治理：授权准入、来源快照、时效、缓存、熔断、成本预算、纠错举报与下架审计。
- 实施顺序：阶段 0 能力透明化；阶段 1 内部基础框架；阶段 2 获授权的单位名称检索；阶段 3 实时职位和抽象发现；阶段 4 生产运营与成本治理。

### 6.3 启动 F5 前必须完成的五项业务决策

1. 覆盖地域和单位类型，是否包括港澳台及境外单位。
2. 至少一个允许向终端用户展示并进行必要缓存的单位数据授权方案。
3. 实时职位来源及其展示、摘要、缓存和跳转权利。
4. 月度外部数据预算、目标搜索量和缓存策略。
5. 单位纠错与虚假招聘复核责任人。

在上述决策完成前，可以建设 schema、provider adapter、检索合同和页面骨架，但不得宣称具有全面单位库或实时职位覆盖。

## 7. 验证证据与证据边界

`handoffs/005-f2-f3-f5-p0-fixes-2026-09-11.md` 记录了实现完成时的全量门禁结果：Python `420 passed in 152.24s`，Node `51 passed`，两份 requirements 的依赖审计无已知漏洞，`git diff --check` 通过，四组 `public/`/`docs/` 镜像一致。该结果属于上一实现轮次的记录，本次文档轮没有重复运行全量测试。原报告称新增测试 21 项，但分项 7 + 6 + 5 + 4 合计为 22；新增测试数量存在记录口径冲突，本轮不把该数量当作已核实结果，以实际测试运行和 CI 结果为准。

本次实时核验完成以下只读检查：

- 当前 HEAD、分支、提交统计和远端 refs；创建本文件前工作区干净。
- `gh 2.100.0`、Vercel CLI `59.16.0`；两者 CLI 均显示 logged out。
- `gh.exe` Authenticode 签名状态为 `Valid`，签名者 GitHub, Inc.
- Git credential helper 为 `manager`；只检查字段存在性并通过 GitHub `/user` 验证，凭据有效且对应 `zimo66067-wq`，未输出任何凭据值。
- Vercel 连接器可列出团队 `team_StsTBBpm3KTED16tRWkAiS9t`、项目 `prj_Y0Za3bdEyGFBrwExDSjz953zTECL` 和当前生产部署。
- `.github/workflows/ci.yml` 只在 push 到 `main` 或针对 `main` 的 pull request 时触发；单独推送特性分支不会运行 CI。

## 8. 已消除的“认证阻断”

### 8.1 GitHub

CLI 未登录不等于无法发布。当前 Windows Credential Manager 中已有有效 GitHub 凭据，`git push` 可以直接通过 credential helper 使用。创建 PR 时可由新模型采用以下任一安全路径：

1. 优先直接使用已有凭据完成 `git push`，再通过 GitHub REST 创建/读取 PR 与 Actions 状态；凭据仅在进程内存中使用，不回显、不落入命令历史、不写文件。
2. 若必须使用 `gh`，从 credential helper 读取凭据并通过标准输入交给 `gh auth login --with-token`；不得将 token 放到命令行参数、环境输出、聊天消息、日志或文档中。

禁止要求用户把 PAT 贴进对话。若凭据未来失效，用户应在本机交互式浏览器/凭据管理器中重新登录，然后只告知“登录已完成”。

### 8.2 Vercel

Vercel CLI 当前未登录，但不是发布阻断。项目已绑定 GitHub；推送分支和创建 PR 后应由 Git 集成生成 Preview，连接器可以读取部署、构建日志与生产状态。只有在必须执行 CLI 专属操作且连接器无法完成时，才让用户在本机交互式运行 `vercel login`；不得索要 Vercel Token。

### 8.3 GitHub DNS

本仓库设置了局部配置 `http.curloptResolve=github.com:443:140.82.113.3`，当前 `git ls-remote` 已恢复且 TLS 校验保留。该固定 IP 可能随 GitHub 网络变化而失效；只在当前 DNS 故障期间保留。网络恢复后执行只读验证，再移除该仓库局部覆盖。不要修改系统 hosts，也不要关闭 TLS 校验。

## 9. 新模型接手后的严格执行顺序

1. 阅读本文件、004 全局交接、005 修复报告和 `docs/f5-organization-job-search-plan-2026-09-11.md`；检查 `git status`，确认不存在其他会话并发推送或合并。
2. 确认 HEAD 为 `9b59f9b`。本交接文件是在该提交之后新增，需单独作为文档变更处理；不得篡改或重写 9b59f9b 的实现历史。
3. 记录发布前 `main` 基线 `b715fac9ddcfd81198d7608f8e5c76416296b5de`，作为回滚依据。
4. 通过 credential helper 推送 `codex/adaptive-interview-fuzzy-major-2026-09-10`；禁止输出凭据。
5. 创建指向 `main` 的 PR。CI 只会在 PR 建立后触发，等待 `CI` 成功；失败时只读取必要错误上下文并修复对应问题。
6. 等待同一 commit 的 Vercel Preview 达到 `READY`；确认 deployment metadata 的 commit SHA 等于 `9b59f9b...`。
7. 在 Preview 做完整验证：F2 错字、简称、两字防误召回、`total`、64 字边界和双输入乱序；F3 首题后回答驱动的主问题、最多一次追问、五题结束、低 ASR 确认、4000 字/非法 gap/危险输出；F5 能力边界；同时检查浏览器控制台和相关 API 不出现新增 5xx。
8. 只有 CI、Preview、浏览器、API 与安全探针全部通过后才合并 `main` 并推送。不得把 F5 规划描述为已实现功能。
9. 等待生产 deployment `READY`，核对生产 SHA 为合并提交；打开 `https://career-coach-omega-three.vercel.app/` 及 F2/F3/F5 页面重复关键闭环验证。
10. 最终报告必须包含：特性提交、PR、CI 结果、Preview deployment、合并提交、生产 deployment、线上可见性、失败/降级项和回滚基线。

## 10. 禁止事项与风险提示

- 不得在前端、提交、PR、日志、截图、文档或聊天中暴露 GitHub/Vercel/API 密钥。
- 不得以“push 成功”代替“CI、Preview、合并和生产验证完成”。
- 不得绕过 CI 或在验证失败时直接合并。
- 不得在未授权数据源条件下抓取、缓存或公开展示单位和职位数据。
- 不得删除 F3 的 fail-closed 安全闸门，除非先完成等价风险分析和回归测试。
- 本文件新增后工作区将不再是完全干净状态；新模型必须区分交接文档变更与 `9b59f9b` 已提交的产品代码。

## 11. 行动项

- [ ] 将本交接文档作为独立文档变更纳入后续提交，或在 PR 中清晰说明。
- [ ] 安全推送当前特性分支并创建 PR。
- [ ] 等待 CI 成功并核对测试/扫描结果。
- [ ] 完成 Preview 的 F2/F3/F5 浏览器与 API 全链路验证。
- [ ] 记录 `main` 回滚基线后合并，并完成生产验证。
- [ ] 另行收集 F5 五项业务决策；在决策和数据授权完成前不启动对外单位搜索。
