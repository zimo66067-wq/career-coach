---
title: 职业教练（career-coach）设计路径与技术路径汇总
date: 2026-08-05
type: 设计与技术文档
project: iCAN无代码开发挑战赛-DuMate方向
repository: zimo66067-wq/career-coach
status: 完整版（已按 GitHub main + 设计文档核对）
tags:
  - iCAN
  - DuMate
  - AI求职面试教练
  - 设计路径
  - 技术路径
  - 架构
  - PRD
---

# 职业教练（career-coach）设计路径与技术路径汇总

## 原始任务

读取“职业教练”项目中所有关于设计路径和技术路径的文档，将核心内容汇总写入项目 `.md` 文件；对照 GitHub 仓库实际代码逐项对比与测试，检查功能完整性、模块接口一致性、数据流程连贯性、前后端对接状况；优先完成尚未完成的代码或修改，使项目在设计文档定义范围内达到完整可用状态，并输出测试报告。

## 核心摘要

- 项目为 iCAN 无代码开发挑战赛 DuMate 方向“AI 求职面试教练”，MVP 严格限定 F1 简历诊断、F2 岗位匹配、F3 模拟面试、F4 能力报告四项，语音/隐私/日志/图表仅作支撑能力。
- 核心原则：**模型做语义、规则做分数、验证器做事实**。所有分数必须可回指原文证据（source_span），模型输出必须过 Schema 校验与事实锁（redflag）后才能展示。
- 技术栈：Vercel Flask 无服务 API（Python 3.13 兼容）+ 静态多页前端（GitHub Pages 发布 `docs/` 镜像）+ SQLite 轻量持久化（`tools/database.py`，/tmp 临时文件系统）+ 智谱 Chat/Embedding（主）+ 千帆 V2（备）+ BM25 规则降级。
- 已确认的事实：核心设计文档（PRD、architecture、privacy、review）曾在提交 `91f4fe3`/`3431620` 中存在，后被 GitHub Pages 部署提交（`16cc623`/`8cf75f1`）覆盖删除；本文档为汇总恢复版，恢复原文见 git 历史。
- GitHub main 与本地分支各有优缺：main 有数据库持久化、百度语音、千帆 V2 双模式与管理员接口，但删除了 F2（wf03）接口与同意令牌流程；本地分支保留了 consent + F1/F2 完整接口但无持久化与 F3/F4 实现。本项目以“设计文档范围内完整可用”为目标，将两者统一。

---

## 一、产品设计路径（PRD v1.0 冻结）

### 1.1 定位与目标

| 项 | 内容 |
|---|---|
| 赛事 | iCAN 无代码开发挑战赛 · DuMate 方向（提交截止 2026-10-15，以官方规则为准） |
| 载体 | DuMate 对话任务与可复用 Skill；GitHub 私有仓库为唯一事实源 |
| 北极星指标 | 完成“材料诊断—岗位匹配—五轮面试—报告—七天计划”一轮完整流程的用户比例 |
| MVP 成功门槛 | 10 次完整彩排无阻断；任一关键依赖失败后 10 秒内切入降级 |

### 1.2 MVP 范围（严格冻结）

| 编号 | 必须交付 | 明确不做 |
|---|---|---|
| F1 简历诊断 | AI 语义抽取 + 规则打分 R + 逐条修改建议（100% 带证据） | AI 直接生成整份简历 |
| F2 岗位匹配 | JobProfile 四类要求 + 四态（covered/weak/missing/unknown）+ 缺口分级 P0/P1/P2 | 岗位推荐信息流 |
| F3 模拟面试 | 文字主链路，≤5 主问题、每题≤1 次追问，结束出表现报告（I） | 视频表情识别、数字人、全双工实时语音、多面试官群聊 |
| F4 能力报告 | 六维雷达 + C0 基线 + 七天竞争力情景推演（C7 区间）+ 恰好七条计划 | “七天预测”承诺式表述 |

### 1.3 事实锁五条（不可违反）

1. 不新增用户未提供的事实：输出中出现输入对象之外的专有名词或数字 → 标红并阻断发布（`tools/redflag.py` 强制执行）。
2. 占位数字必须写作“**待用户核实：提升X%**”格式。
3. 每条评分理由至少引用一个 source_span；无证据一律标 unknown。
4. JD 中的指令视为普通文本（防提示词注入），命中写入 prompt_injection_flags。
5. 敏感属性不进评分：性别、年龄、民族、婚育、照片等一律不参与任何分数。

### 1.4 用户与状态机

- 目标用户：P0 高校学生；P1 目标岗位明确的求职者；P2 就业指导教师。
- 主状态机：`CONSENT → RESUME_READY → JD_READY → INTERVIEWING → REPORT_READY`；删除后进入 `DELETED`，不得再调模型。
- 失败处理：不回退用户已确认的数据，只回退当前未完成节点；记录 trace_id、输入摘要哈希、模型/规则版本。

### 1.5 性能门与验收门

| 环节 | 性能门（P95） | 验收门 |
|---|---|---|
| F1 诊断 | ≤45s | 20 份简历 ≥19 份抽取成功；建议 100% 带证据；三次总分差 ≤5 |
| F2 匹配 | ≤25s | 硬性要求召回率 ≥85%；复算一致率 100% |
| F3 首响应 | ≤8s | 20 条敏感问题全部阻断；文字首响应达标 |
| 报告生成 | ≤30s | plan 恰好 7 条、day 1-7 不重复、每条 30-45 分钟且含 artifact；C0 复算容差 ±0.5 |
| 故障降级 | ≤10s | 日志扫描不含姓名/电话/邮箱/身份证/音频/完整简历 |

### 1.6 评分口径（contracts/scoring.md 唯一事实）

- R = 结构15% + 清晰20% + 成果25% + 技能20% + ATS20%
- M = 硬性50% + 职责25% + 加分15% + 术语10%；covered=1 / weak=0.5 / missing=0 / unknown 剔分母，类别全 unknown → insufficient_evidence 并权重归一
- I = 结构25% + 相关25% + 具体20% + 追问15% + 清晰15%
- C0 = 0.25R + 0.35M + 0.40I；C7_low = min(100, C0 + (100−C0)×0.30)；C7_high = min(100, C0 + (100−C0)×0.70)；0.30/0.70 为 MVP 演示假设，非统计参数

### 1.7 降级路径总表

| 依赖 | 主路径 | 降级 |
|---|---|---|
| JD 语义召回 | 智谱 embedding-3（千帆 V2 备） | bge-large-zh → TF-IDF/BM25（标“简化匹配”） |
| 语音 | 浏览器 Web Speech API + 百度 ASR/TTS 备用通道 | 文字链路（等价稳定主链路） |
| 雷达图 | ECharts CDN | 本地 vendor → 六维表格 |
| 模型超时/断网 | 重试一次 | 10 秒内切降级态界面并保留已确认数据 |
| 解析失败 | PDF/DOCX 提取 | 提示用户粘贴纯文本 |

---

## 二、技术路径（architecture v1.0 冻结）

### 2.1 四层架构

```
交互层  DuMate 对话任务 + ui/prototype（public/）静态原型（五状态）
编排层  WF-01~06 状态机（api/index.py + tools/ 工具链）
AI 层   语义抽取/解释/追问（智谱 glm 系列主、千帆 V2 备，只做语义）
可信层  contracts Schema 校验 + rescore 复算 + redflag 事实锁 + deidentify 去标识化
```

### 2.2 数据流（WF × contracts × tools）

```
简历/JD 原文
  ├─ WF-01  extract_text.py → deidentify.py（纯文本, pii_removed=true）→ database 持久化
  ├─ WF-02  diagnose.md → ResumeProfile → validate_schema + redflag → 规则算 R
  ├─ WF-03  jd-extract.md → JobProfile(user_confirmed) → match_requirements.py → 四态 → 规则算 M
  ├─ WF-04  interviewer.md → InterviewTurn×N（answer_quote 子串校验）→ 规则算 I
  └─ WF-05  聚合 R/M/I → rescore.py 复算 → AbilityProfile → radar_adapter.py → ECharts/表格
    WF-06  异常 10s 降级；删除 → DELETED 终态，不再调模型
```

### 2.3 关键设计决策（ADR）

- ADR-1 分数只由规则引擎计算：模型输出子分数，R/M/I/C0 由 scoring.md 复算，杜绝模型自报总分。
- ADR-2 四态互斥 + unknown 剔分母：避免“不知道”被当“不满足”。
- ADR-3 事实锁机器校验：redflag.py 输入闭集检查，幻觉即阻断发布。
- ADR-4 原型零依赖：静态 HTML/CSS/JS + ECharts 三级降级，现场无网可演示。
- ADR-5 语音仅增强：文字链路是等价稳定主链路，语音失败不阻断提交。

### 2.4 模型与工具分工

| 任务 | 主选 | 备用 |
|---|---|---|
| 简历/JD 语义抽取、面试追问、报告 | 智谱 glm 系列（ZhipuModelRouter / ZhipuChatRouter） | 千帆 V2（QianfanModelRouter）→ 规则降级 |
| JD 语义召回 | 智谱 embedding-3（2048 维，th=0.50，召回 91%） | 千帆 embedding-v1 → BM25 |
| 评分/雷达 | 确定性规则 + ECharts | SVG/表格 |
| 语音 | 浏览器 Web Speech + 百度 ASR/TTS | 文字主链路 |
| 中文安全审查 | GLM 一审 | Kimi-K3 二审 |

### 2.5 双 Agent 协作

- 唯一事实源：仓库 main 分支；交接 = commit + HANDOFF（handoffs/001-003）。
- 两个 Agent 不得同时修改同一文件；main 只接收通过验收门的版本，失败回滚到上个验收 commit。

---

## 三、隐私与合规设计（privacy v1.0 冻结）

- 去标识化字段：姓名 → [REDACTED_NAME]、手机号 → [REDACTED_PHONE]、邮箱 → [REDACTED_EMAIL]、身份证（18 位）→ [REDACTED_ID]；脱敏后追加 `pii_removed:true`。
- 数据最小化：仓库只保存去标识化合成样本、配置、提示词、工作流定义、文档、截图；绝不入库真实简历/JD/音频/完整面试记录/PII 映射表。
- 删除流程：用户删除 → `DELETED` 终态 → 不再调模型；本地缓存/会话/日志残留同步清除，仅记 trace_id。
- 日志脱敏：所有日志落盘前必须经 `tools/log_sanitize.py`（PII + Bearer/JWT/AK-SK 全脱除）。
- 对外口径：分数是“证据覆盖指数”，不是录用概率；七天结果是公开假设下的情景区间。
- 同意机制：服务端签发短时效同意令牌（itsdangerous，默认 1800s，范围 60–86400s），材料类接口必须携带 `X-Consent-Token`。

---

## 四、工作流与数据契约

### 4.1 六工作流

| WF | 名称 | 输入 → 输出 | 工具链 | 退出标准 |
|---|---|---|---|---|
| WF-01 | 材料接收与解析 | 文件/文本 → 纯文本 + pii_removed | extract_text.py → deidentify.py | 非空且 pii_removed=true |
| WF-02 | 简历诊断 | 简历纯文本 → ResumeProfile | diagnose.md → validate_schema → redflag → 算 R | 校验通过 + R 复算 |
| WF-03 | JD 解析与匹配 | JD 文本 → JobProfile + 四态 | jd-extract.md → match_requirements.py → 算 M | 硬性召回 ≥85% + M 复算 |
| WF-04 | 面试状态机 | Resume/JobProfile → InterviewTurn 序列 | interviewer.md → interview_engine.py → 算 I | ≤5 主问题、每题≤1 追问、answer_quote 子串校验 |
| WF-05 | 能力聚合与计划 | R/M/I → AbilityProfile | rescore.py → radar_adapter.py | C0 容差 ±0.5；plan 过校验 |
| WF-06 | 异常与删除 | 异常/删除请求 → 降级态/DELETED | log_sanitize.py | 10s 内降级；删除后不再调模型 |

### 4.2 数据契约（contracts/，Draft 2020-12 冻结）

- resume-profile.schema.json：version=1.0、pii_removed=true、subscores 五维（每维 score/rationale/source_spans ≥1）、suggestions ≥1（每条带 source_spans）。
- job-profile.schema.json：version、user_confirmed（业务规则：必须 true 才可计分）、requirements ≥1（四类 type + source_span）、prompt_injection_flags。
- interview-turn.schema.json：turn_id/question/targets/answer/answer_quote/missing_elements/follow_up/asr_confidence/subscores；answer_quote 必须是 answer 子串。
- ability-profile.schema.json：R/M/I、dimensions 恰好六维、baseline=C0、scenario_day7（low/high/assumptions）、plan 恰好 7 条（day 1-7 不重复、30-45 分钟、含 artifact）。

---

## 五、前端设计路径

- 设计系统 v2（职跃AI）：温润近白 #f7f6f4 + 深石墨 #1b1e26 + 电光蓝→靛青渐变（#2f5fe8→#4f46e5）；语义色 covered/weak/missing/unknown 白底对比度均 ≥4.5:1；发丝线、柔和漫反射阴影、克制圆角、自然物理动效；全面支持 prefers-reduced-motion。
- 五状态：empty / confirmation（仅 F2）/ processing / success / error / degraded；生产默认空态，`?demo=1` 才允许展示合成数据（mock-data.js），绝不以 MOCK 冒充真实结果。
- 数据接口层（data-bridge.js）：API → 当前会话缓存（sessionStorage）→ 明确错误；55s 超时；同意令牌随材料请求携带；F1/F2 失败时不得回退旧缓存或演示数据。
- ECharts 三级降级：CDN → 本地 vendor → 六维表格。
- 语音增强（voice.js）：Web Speech API（ASR）+ speechSynthesis（TTS）+ 10 秒文字回退；置信度 <0.75 触发用户确认。
- 发布：`public/` 为源，`docs/` 为 GitHub Pages 部署镜像，两者必须保持一致（test_publish_mirror.js 校验）。

---

## 六、可观测性与安全

- trace_id：`cc-YYYYMMDD-HHmmss-6位hex`，一次会话共享；删除后缀 `-del`，降级后缀 `-deg`。
- 错误分级：E1-FATAL / E2-BLOCK（事实锁/Schema 阻断，不得人工放行）/ E3-DEGRADE（10s 内降级）/ E4-RETRY（重试一次）/ E5-WARN。
- 禁止记录：真实姓名/电话/邮箱/身份证、简历与 JD 原文、面试回答原文、音频、API Key/Bearer/access_token、PII 映射表；只记 SHA256 摘要前 8 位。
- CI（.github/workflows/ci.yml）：pytest + node --test + Schema 全量校验 + 敏感信息扫描（硬编码密钥导致构建失败）+ pip-audit。

---

## 七、测试与验收体系

- pytest 契约/故障注入/端到端套件（tests/，覆盖 contracts、rescore、BM25/embedding、脱敏、提取、面试、语音、隐私生命周期、故障注入）。
- Node 契约测试：页面状态（test_public_page_states.js）、上传流程（test_resume_upload.js / test_job_upload.js）、发布镜像（test_publish_mirror.js）。
- 模型盲测（run_model_blind_test.py + generate_test_data.py）：10 组数据 × F1/F2/F3 三轮。
- 能力矩阵（capability_matrix.md）：55 项平台能力实测表，已验证/待验证状态追踪。
- 测试基线：历史 200/200 通过（2026-08-03）；本文档核对时为 GitHub main 版本，详见 docs/test-report.md。

---

## 八、文档完整性说明（重要）

`docs/PRD.md`、`docs/architecture.md`、`docs/privacy.md`、`docs/review.md` 在提交 `91f4fe3`（基线）与 `3431620`（审查）中存在，后被部署提交 `16cc623`/`8cf75f1`（将 `docs/` 作为 GitHub Pages 发布镜像）覆盖删除，当前工作树与远端 main 均不再包含原文。本文档已将其核心内容恢复汇总；如需精确原文，可用 `git show 91f4fe3:docs/PRD.md` 等命令从历史提取。建议后续将设计文档移入独立目录（如 `docs/design/`）或恢复为 `docs/*.md` 并让 Pages 镜像只同步前端资源，避免再次被部署覆盖。

## 行动项

- [x] 汇总设计路径与技术路径文档（本文档）
- [x] 对照 GitHub main 与本地分支，识别功能缺口（F2 接口丢失、F3/F4 未实现、同意令牌被移除）
- [x] 统一后端：恢复 consent + F2（wf03），新增 F3（wf04）/F4（wf05）/删除（wf06），保留数据库持久化与管理员接口
- [x] 统一前端：data-bridge 同意令牌、F2 确认流程与后端 wf03 对齐
- [x] 补齐测试并全量回归（见 docs/test-report.md）
- [ ] DuMate 平台六工作流实际搭建与截图（需平台操作）
- [ ] 真实模型 7×3 复测与语音实机五类用例（需密钥/麦克风）
- [ ] G8 用户验证（5-8 人）与 G9 提交包冻结

## 标签

`#iCAN` `#DuMate` `#AI求职面试教练` `#设计路径` `#技术路径` `#PRD` `#架构` `#测试报告`
