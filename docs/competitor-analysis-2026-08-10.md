# 竞品对比分析报告 · 职业教练（职跃AI）vs GitHub 同类开源项目

> 日期：2026-08-10 ｜ 用途：产品迭代决策依据 ｜ 证据等级：A=完整 README/仓库页深读；B=搜索快照与仓库摘要；C=推断

## 一、方法与样本

检索范围：GitHub 全站关键词（AI resume analyzer / AI mock interview / AI career coach / resume matcher / AI 面试 / job application agent），筛选与"简历诊断-岗位匹配-模拟面试-能力报告"场景相近的开源项目。

样本：**20 个项目**（3 个 A 级深读，17 个 B 级快照），覆盖三类范式：全栈 Web 平台、本地/CLI Agent、匹配引擎。

| # | 项目 | 技术栈（证据） | 核心功能 | 等级 |
|---|---|---|---|---|
| 1 | [DeepInterview](https://github.com/ngoanpv/DeepInterview) | Next.js + Python(LiveKit/LangGraph) + LightRAG + Docker（A） | 语音优先多语言模拟面试：prep/live/post 三阶段、评分报告、学习教练、社区题库包 | A |
| 2 | [FaceTomato](https://github.com/Infinityay/FaceTomato) | React18+TS + FastAPI + LangChain + SQLite（A） | 中文技术岗：简历解析/PDF-DOCX-PNG、JD匹配、简历优化、面经题库RAG、SSE模拟面试、复盘、语音输入 | A |
| 3 | [langgraph-AI-interview-agent](https://github.com/zzzlip/langgraph-AI-interview-agent) | Spring Boot3 + Python LangGraph Worker + MySQL/Redis/RabbitMQ/MinIO（A） | 多用户认证、异步任务中心、SSE、简历评估/优化、算法测试、模拟面试、多模态ASR、审计 | A |
| 4 | [JobVector](https://github.com/ivruhs/JobVector) | MERN 全栈（B） | 简历↔JD 语义匹配、求职 co-pilot | B |
| 5 | [AI-Resume-Intelligence-Platform](https://github.com/Sasanksurya/AI-Resume-Intelligence-Platform) | FastAPI + Next.js + LangChain + FAISS + Gemini（B） | 4-Agent 流水线：简历分析/JD匹配/ATS评分/职业洞察 | B |
| 6 | [ats-resume-analyzer](https://github.com/Anshum77/ats-resume-analyzer) | Python + TF-IDF/cosine + Docker（B） | 可解释匹配、规则技能抽取、简历分类 | B |
| 7 | [AI-Career-Mentor](https://github.com/Prasannaganesann/AI-Career-Mentor) | Python（B） | 简历分析、ATS、JD匹配、面试准备、职业路线图 | B |
| 8 | [AI-Carrier-Coach](https://github.com/x0lg0n/AI-Carrier-Coach) | Next.js15 + React19 + Prisma + Gemini（B） | 简历构建、求职信、面试准备、行业洞察 | B |
| 9 | [Beacon-AI](https://github.com/Tejas-h-blitz/Beacon-AI) | Next.js + LangChain + Neon + Prisma（B） | 简历/求职信/技能差距分析/模拟面试 | B |
| 10 | [careerbot](https://github.com/thoughtfulllc/careerbot) | AI Agent（B） | 研究公司、匹配岗位、起草申请答案、Answer Bank | B |
| 11 | [lapel](https://github.com/ciwaskiw/lapel) | 本地 CLI + MCP（B） | living profile、岗位管线、永不伪造经历 | B |
| 12 | [AutoApply](https://github.com/Liam-Frost/AutoApply) | 本地 Agent（B） | 岗位发现/评分/材料生成/表单填写，人工闸门提交 | B |
| 13 | [career-ops](https://github.com/santifer/career-ops) | CLI-agnostic（B） | A-F 岗位评分、ATS PDF、投递跟踪、本地运行 | B |
| 14 | [prisma-ai](https://github.com/weicanie/prisma-ai) | AI co-pilot（B） | 项目优化/简历定制/岗位匹配/面试准备 + 面经站 pinkprisma.com | B |
| 15 | [ig-club](https://github.com/Starryzl/ig-club) | DDD 微服务（B） | 刷题、模拟面试、简历分析、社区 | B |
| 16 | [ai-interview-coach](https://github.com/Subakkumar/ai-interview-coach) | Python（B） | 自适应追问 + 雷达图性能报告 | B |
| 17 | [Ai-mock-Interview](https://github.com/modamaan/Ai-mock-Interview) | Next.js + Tailwind + PostgreSQL + Drizzle + Gemini（B） | 模拟面试平台 | B |
| 18 | [job-matcher](https://github.com/mrdmunk/job-matcher) | 本地 embeddings + SQLite（B） | 简历/岗位 embedding + cosine，本地优先 | B |
| 19 | [resume-matcher-bert](https://github.com/Om-Shandilya/resume-matcher-bert) | MiniLM + FAISS（B） | 领域适配 BERT 语义匹配 | B |
| 20 | [Interviewer](https://github.com/IliaLarchenko/Interviewer) | 本地 STT/LLM/TTS（B） | 本地运行 AI 面试官 | B |

## 二、四维度对比

### 2.1 前端设计（UI / 交互 / 响应式）

| 维度 | 我们（职跃AI） | 竞品最佳实践 |
|---|---|---|
| 视觉体系 | 设计令牌 v2（温润近白+电光蓝）、克制留白、状态规范 | DeepInterview：产品级向导（Setup→Live→Report→Coach）；FaceTomato：番茄品牌意象+对话流式渲染 |
| 交互流程 | F1-F4 分页 + 四步向导（选专业→画像→上传→报告） | DeepInterview：一键 Quick Demo 填充样例 CV+JD，零上传体验 |
| 流式体验 | 无 SSE 流式 | FaceTomato：SSE 流式回答 + Markdown 渲染 + 本地快照恢复 |
| 响应式 | 移动端单栏堆叠（实测文档） | 竞品普遍 Tailwind 响应式；我们已具备 |
| 图表 | ECharts 三级降级 + 雷达图 | ai-interview-coach：雷达图报告（我们 F4 已有） |
| i18n | 仅中文 | DeepInterview：i18n 语言包（EN+VI，可插拔） |

### 2.2 产品服务页面设计（信息架构 / 引导 / 转化）

| 维度 | 我们 | 竞品最佳实践 |
|---|---|---|
| 首页导航 | 四功能入口 + 侧边栏历史 | prisma-ai：内容站（面经）引流产品，内容→工具转化双轮 |
| 空态/引导 | 空态规范严格（默认 empty，不展示结果） | DeepInterview：Quick demo 一键试玩，降低首用门槛 |
| 账号体系 | 侧边栏登录/注册原型（localStorage） | zzzlip：Spring Security 多用户认证 + 用户级 API Key 保存；DeepInterview：hosted-only Supabase auth |
| 历史记录 | 侧边栏历史 + 演示数据 | zzzlip：任务中心（全量任务状态/进度） |
| 转化路径 | 诊断→匹配→面试→报告单向 | careerbot/AutoApply：投递闭环（起草申请→人工闸门提交） |
| 社区/生态 | 无 | ig-club 社区、DeepInterview 题库包共创、FaceTomato 面经库 |

### 2.3 后端运行逻辑（架构 / 数据流 / 性能 / 扩展性）

| 维度 | 我们 | 竞品最佳实践 |
|---|---|---|
| 架构 | Flask 单文件（55KB）+ SQLite + 静态前端 | zzzlip：Spring Boot 模块化单体（domain/application/interface/infrastructure）+ Python Worker，ArchUnit 架构门禁；DeepInterview：prep/live/post 三阶段 + 跨语言契约（TS↔Pydantic） |
| 异步/长任务 | 同步请求，无任务中心 | zzzlip：RabbitMQ + 任务中心 + SSE 进度 + 幂等（Idempotency-Key）；DeepInterview：重模型放前后、轻模型在线 |
| 文件存储 | SQLite 文本存储 | zzzlip：MinIO 对象存储 + 可验证产物；FaceTomato：后端解析 PDF/DOCX/PNG |
| 数据流 | BM25 四态 + embedding 证据验证器（实测 precision 97%/recall 84%） | ats-resume-analyzer：TF-IDF 可解释匹配；job-matcher：本地 embedding→SQLite 隐私优先 |
| 安全 | PII 脱敏、同意门、防注入、生命周期删除 | zzzlip：CSRF/限流/审计/Outbox-Inbox；DeepInterview：共享密钥 + Row Level Security |
| 可测试性 | pytest 覆盖 wf01-wf06 + 真机复测 | DeepInterview：mock-first 适配器，无 Key 跑全 CI；zzzlip：specs + TDD |
| 可观测性 | trace_id + observability 文档 | zzzlip：审计日志；DeepInterview：结构化状态标注 |

### 2.4 技术栈选型差异

| 关注点 | 我们 | 竞品主流 | 差距评估 |
|---|---|---|---|
| 前端 | 原生 HTML/CSS/JS（零构建） | Next.js/React + Tailwind | 原型期合理；产品期需组件化与状态管理 |
| 后端 | Python Flask（Vercel 兼容） | FastAPI / Spring Boot / Node | 轻量够用；缺分层与异步 |
| 模型层 | Zhipu 路由 + BM25/embedding | LangChain/LangGraph + provider 适配层 | 我们缺统一 provider adapter 与 mock-first |
| 存储 | SQLite/JSON | Postgres/MySQL + Redis + 对象存储 | 单机演示够；多用户后需升级 |
| 消息 | 无 | RabbitMQ/SSE | 长任务必须引入 |
| 检索 | embedding 全量召回（自有验证器） | FAISS/LightRAG + 面经库 | 我们有检索地基，缺内容生态 |

## 三、我们项目当前不足（G1-G10）

| 编号 | 不足 | 证据/影响 |
|---|---|---|
| G1 | 无公网可访问演示：功能仅本地 8123 可见 | Vercel 路由已配置但未上线；竞品均有 live demo 或一键部署按钮 |
| G2 | 模拟面试为文本对话，无语音/视频/实时 | DeepInterview voice-first、FaceTomato 语音输入、zzzlip 多模态 ASR |
| G3 | .docx/.pdf 前端降级为粘贴文本，解析链路未闭环 | FaceTomato/DeepInterview（markitdown）/zzzlip 均服务端解析 |
| G4 | 无真实用户体系后端：账号侧边栏是 localStorage 原型 | 无法多用户隔离、长期保存；zzzlip Spring Security 为参照 |
| G5 | 长任务无异步架构：无任务中心、SSE 进度、MQ、幂等 | 面试/匹配耗时长时体验差；zzzlip 任务中心为参照 |
| G6 | 内容生态单薄：无面经题库/RAG 检索、无职业路线图、无简历/求职信生成 | FaceTomato 题库、prisma-ai 面经站、AI-Carrier-Coach 生成器 |
| G7 | 前端流式渲染与断点恢复缺失 | FaceTomato SSE + 快照恢复 |
| G8 | 性能与观测未量化：无压测、无请求级日志面板 | 竞品有审计/可观测设计 |
| G9 | Flask 单文件扩展性受限：无分层、无架构门禁 | zzzlip ArchUnit + 模块化单体 |
| G10 | 模型策略单一：无 provider 适配层、无 mock-first 离线开发 | DeepInterview provider matrix |

## 四、竞品优势亮点（B1-B10）

- **B1** DeepInterview 三阶段流水线（prep/live/post）＋ provider adapter ＋ mock-first：开发不依赖 Key，CI 全绿，工程效率标杆。
- **B2** DeepInterview 一键 Quick Demo ＋ 无登录自托管：把"首次体验成本"降到零。
- **B3** zzzlip 生产级异步架构（MQ/MinIO/SSE/幂等/CSRF/审计）＋ TDD 规格文档：最接近"可商用"的工程范式。
- **B4** FaceTomato 中文场景闭环（简历→JD→优化→题库→面试→复盘→语音）：与我们定位最贴近且功能面更全。
- **B5** prisma-ai 内容站引流模式：面经内容→产品转化的双轮增长。
- **B6** lapel/career-ops/AutoApply 本地优先＋人工闸门＋永不伪造：信任与合规设计（与我们"防伪造红标"一致并可借鉴）。
- **B7** job-matcher/resume-matcher-bert 本地 embedding＋隐私优先：与我们脱敏/本地化路线呼应。
- **B8** ats-resume-analyzer 可解释 TF-IDF＋Docker：与我们 BM25 证据思路同源，验证了可解释方向正确。
- **B9** ig-club 社区＋刷题＋面试闭环：粘性与留存设计。
- **B10** ai-interview-coach 自适应追问＋雷达图：与我们 F3/F4 方向一致，需补"追问自适应"深度。

## 五、不足 → 竞品最佳实践映射

| 我们的不足 | 参考竞品 | 借鉴做法 |
|---|---|---|
| G1 无公网演示 | DeepInterview | Vercel 一键部署 + 公开 demo 链接；本地 8123 仅供开发 |
| G2 无语音面试 | FaceTomato / zzzlip | 先接 ASR 语音输入（DashScope/百度已有集成基础），再演进实时对话 |
| G3 文档解析未闭环 | FaceTomato / DeepInterview | 服务端 markitdown 解析 PDF/DOCX，OCR 兜底扫描件 |
| G4 无用户体系 | zzzlip | Spring Security 式认证可先用 Flask-Login/会话替代；账号原型前端已备 |
| G5 无异步任务 | zzzlip | 引入任务表 + SSE 进度；Vercel 限制下先用轮询/队列服务 |
| G6 内容生态单薄 | FaceTomato / prisma-ai | 面经题库入库（RAG 检索复用 embedding 验证器）；简历/求职信生成器 |
| G7 无流式/断点 | FaceTomato | SSE 流式回答 + 会话快照恢复 |
| G8 观测不足 | zzzlip | 请求日志/审计表 + trace 面板 |
| G9 单体无分层 | zzzlip | 按 domain/application/interface 拆模块，保留 Vercel 单函数出口 |
| G10 模型策略单一 | DeepInterview | provider adapter + mock 适配器 + 本地 Ollama 选项 |

## 六、改进建议优先级

评分口径：RICE 简化（影响×信心 / 成本），P0=下个迭代，P1=下下个，P2=远期。

| 优先级 | 改进项 | 竞品参考 | 理由 | 预估成本 |
|---|---|---|---|---|
| P0-1 | 公网部署 + 一键 Quick Demo | DeepInterview | 当前用户无法访问，阻断一切验证；成本低 | 0.5-1 人日 |
| P0-2 | 服务端 .docx/.pdf 解析 | FaceTomato/DeepInterview | F1/F2 主入口卡点；markitdown 成熟 | 1-2 人日 |
| P0-3 | 最小用户体系后端（注册/登录/历史落库） | zzzlip | 归属感需求已规划，前端就绪 | 2-3 人日 |
| P0-4 | 任务化 + SSE 进度（先匹配/面试） | zzzlip | 长任务体验直接相关 | 2-3 人日 |
| P1-1 | 面经题库 + RAG 检索 | FaceTomato | 复用 embedding 验证器，内容生态起点 | 3-5 人日 |
| P1-2 | 语音输入（ASR→文本） | FaceTomato/zzzlip | 百度语音 SDK 已集成过，扩展即可 | 2-3 人日 |
| P1-3 | 前端流式渲染 + 会话快照 | FaceTomato | 面试体验提升明显 | 2 人日 |
| P1-4 | 简历生成/优化器 | AI-Carrier-Coach/Beacon-AI | 与 F1 诊断互补 | 3-4 人日 |
| P2-1 | 后端分层重构 + 架构门禁 | zzzlip | 用户量上来前不必做 | 5-8 人日 |
| P2-2 | provider adapter + mock-first + 本地模型 | DeepInterview | 工程化长期收益 | 3-5 人日 |
| P2-3 | 投递闭环（求职信/申请跟踪/人工闸门） | careerbot/AutoApply | 需商业模式配合 | 5+ 人日 |

## 七、结论

1. **定位验证**：我们"简历诊断→专业导向匹配→模拟面试→能力报告"的闭环方向与 FaceTomato/DeepInterview 等头部开源项目一致，功能覆盖不落后，专业目录数据底座（845 专业）为差异化亮点，竞品均无此设计。
2. **最大短板不是功能而是交付形态**：G1 无公网演示、G3 文档解析未闭环、G4 无用户体系，三者直接阻碍用户真正使用；应先修这三项。
3. **工程化差距集中在异步与分层**：竞品（zzzlip/DeepInterview）已进入"生产级"阶段，我们仍是原型工程；在用户量增长前，优先补异步任务与可观测性即可，分层重构可延后。
4. **可借鉴的差异化机会**：中文专业目录 + 官方数据审计（教育部/人社部）是国际竞品不具备的护城河；面经题库 RAG 与内容站引流（prisma-ai 模式）是低成本高杠杆的下一步。

## 标签

`#竞品分析` `#产品迭代` `#F2岗位匹配` `#模拟面试` `#技术选型` `#路线图`
