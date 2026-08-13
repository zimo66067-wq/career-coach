---
title: 职业教练 · 阶段 1-5 全链路迭代规划
date: 2026-08-12
type: 规划
project: career-coach（职业教练）
repository: zimo66067-wq/career-coach
status: 已确认执行
milestone: 竞品驱动迭代 · 阶段1-5
tags:
  - 职业教练
  - 迭代规划
  - 竞品驱动
  - QuickDemo
  - OCR
  - 任务中心
  - SSE
  - RAG
  - 工程化
---

# 职业教练 · 阶段 1-5 全链路迭代规划（2026-08-12）

## 0. 项目背景

职业教练（career-coach）是一个面向求职者的 AI 教练产品，核心闭环为：**简历诊断（F1）→ 专业导向岗位匹配（F2）→ 模拟面试（F3）→ 能力报告（F4）**。产品定位与 FaceTomato / DeepInterview 等头部开源项目一致；差异化亮点为 845 个本科专业目录底座（教育部口径）+ 双分制匹配（专业-岗位适配分 M + 简历-JD 匹配分）。

竞品分析（2026-08-10）结论：最大短板不在功能而在交付形态（无公网演示、文档解析未闭环、无用户体系）与工程化（异步任务、分层、provider 适配）。第一轮竞品驱动迭代（阶段 0）已完成：真实账号体系 + Neon Postgres 持久化 + 历史归属隔离 + Vercel/GitHub Pages 双部署上线（325 pytest / 14 Node 契约全绿，E2E 验收已通过）。

本规划承接阶段 0，定义阶段 1-5 的功能需求、技术实现路径、具体步骤与验收标准，并约定两次测试验收报告的产出节点。

## 1. 当前系统架构（基线）

| 层 | 现状 |
|---|---|
| 部署 | GitHub Pages 静态（docs/public 镜像）+ Vercel Serverless API（Flask 单入口）+ Neon Postgres（生产持久化） |
| 后端 | `api/index.py`（约 72KB 单函数路由，WF-01~06 + auth/history + health）+ `api/f2_major.py`（专业目录与双分制匹配） |
| 领域工具 | `tools/`：database（SQLite/Postgres 双方言）、account、model_router（主模型→备用→规则降级）、extract_text（PDF/DOCX/TXT）、voice_handler（ASR/TTS）、match_requirements（BM25/embedding 四态）、deidentify、rescore、radar_adapter 等 |
| 前端 | `ui/prototype` 原生 HTML/CSS/JS 零构建；`js/data-bridge.js` 统一 API 层；`?demo=1` 演示模式已有雏形；`docs/` 与 `public/` 双镜像 |
| 数据 | resumes / diagnoses / matches / interview_sessions / abilities / users / sessions / history_events |
| 模型 | 智谱路由 + BM25/embedding 检索；无 key 时规则降级 |
| 测试 | pytest 325 项 + Node 契约 14 项；`tests/conftest.py` 自动隔离 SQLite |

### 约束（影响技术选型）

1. **Vercel 函数 60 秒上限**：长任务必须"客户端驱动的分片轮询"而非常驻后台 worker。
2. **Vercel 包体积约 50MB 上限**：OCR 采用 REST API 调用（百度 OCR 免费额度），不引入本地 OCR 引擎。
3. **外部密钥不确定**：OCR / ASR / embedding 均采用 provider 抽象 + mock-first，无 key 时全链路可降级运行。
4. **跨域会话**：GitHub Pages 承载前端，Vercel 承载 API；Cookie `SameSite=None; Secure` + CORS Credentials，前端保留 Bearer 回退。

## 2. 阶段 1：Quick Demo 一键体验（P0-1）

### 2.1 功能需求

- 首页与 F1/F2 页面提供"一键体验"入口：游客无需注册、无需上传文件，一键填充样例简历与 JD，30 秒内走通 F1 诊断 + F2 匹配。
- 所有演示结果必须带"演示数据"标注，禁止伪装成真实用户结果。
- 移动端可操作。

### 2.2 技术实现路径

- 复用现有 `?demo=1` + `window.MOCK` 演示机制（`data-bridge.js` 已有 demoData 通道），新增 `ui/prototype/js/quick-demo.js` 编排：填充简历/JD 文本 → 调用 data-bridge 真实 API（无 key 时后端规则降级）→ 失败时自动退回纯演示数据。
- 后端零新增接口；只需验证无 `ZHIPU_API_KEY` 时 wf02/wf03 的规则降级路径在演示流量下可用。

### 2.3 具体步骤

1. 新增 `ui/prototype/js/quick-demo.js`：`startQuickDemo(target)` 支持 F1/F2 两个入口，注入样例文本并自动执行。
2. 修改 `index.html`、`pages/f1-resume.html`、`pages/f2-match.html`：加入"一键体验"按钮 + 演示标签样式。
3. 新增 `tests/test_quick_demo.js`：断言按钮存在、`?demo=1` 标注、脚本引用齐全。
4. 同步 docs/public 镜像并跑契约测试。

### 2.4 验收标准

- [x] 未登录游客点击一键体验后，无需上传即可看到 F1 诊断与 F2 匹配结果
- [x] 演示结果带明确标注
- [x] Node 契约测试全绿

## 3. 阶段 2：文档解析闭环补强（OCR 兜底 + 上传降级）

### 3.1 功能需求

- 扫描件/图片型 PDF 检测并给出可操作引导（粘贴文本或开启 OCR）。
- 图片型 PDF 在配置 OCR key 后自动提取文本；未配置时明确提示，不静默返回空文本。
- 上传进度条与失败错误态完善（前端 XHR onprogress + 错误码映射）。
- docs/public 双镜像上传链路实测。

### 3.2 技术实现路径

- 新增 `tools/ocr_provider.py`：
  - `detect_scanned_pdf(path)`：用 pypdfium2 渲染首页并判断是否有文本层，返回扫描件置信度。
  - `ocr_image(image_bytes, provider="baidu")`：REST 调用百度 OCR（`OCR_API_KEY`/`OCR_SECRET_KEY`），无 key 返回 `unsupported`。
- `api/index.py` wf01/upload 与 wf03/upload：PDF 文本为空时先 `detect_scanned_pdf`；扫描件且未配置 OCR → 返回 `scanned_pdf` 错误码 + 引导文案；配置 OCR → 逐页 OCR 后返回文本。
- 前端 `resume-upload.js` / `job-upload.js`：上传进度条、`scanned_pdf` 错误态提示面板、网络/超时错误态。
- 测试：`tests/test_ocr_provider.py`（mock 百度响应）、`test_upload_errors.py` 扩展扫描件分支。

### 3.3 具体步骤

1. 后端实现 ocr_provider + 上传路由改造。
2. 前端实现进度条与错误态。
3. 新增 pytest + Node 测试并全量回归。
4. 同步 docs/public 镜像。

### 3.4 验收标准

- [x] 扫描件 PDF 上传返回 `scanned_pdf` 明确错误，不产生空文本静默成功
- [x] 配置 OCR key（mock 验证）后图片型 PDF 可提取文本
- [x] 前端上传进度与失败错误态可用
- [x] 相关 pytest/Node 全绿

## 4. 阶段 3：任务中心 + 轮询进度 + 幂等

### 4.1 功能需求

- 新增 tasks 表与任务状态机（pending → running → done / failed）。
- `POST /api/tasks`（携带 `Idempotency-Key` 创建任务）、`GET /api/tasks/:id`（查进度）、`POST /api/tasks/:id/next`（客户端驱动分片推进）。
- F2 匹配、F3 面试等长任务接入任务化流程，前端显示进度条。
- 同 `Idempotency-Key` 重复提交返回同一任务；越权访问 403/404。

### 4.2 技术实现路径（Vercel 60s 务实方案）

- 任务不在函数内常驻执行：每次 `next` 调用处理一个分片（如 JD 硬性要求分批匹配），更新 progress 后返回；前端轮询 `GET` 并在 running 时继续调 `next`，直至 done。
- `tools/database.py` 增加 tasks 表（SQLite/Postgres 双方言 + 索引）；`tools/tasks.py` 服务层（创建/幂等/推进/完成/失败）。
- `api/index.py` 新增 tasks 路由；`vercel.json` 增加重写。
- `data-bridge.js` 新增任务化封装（createTask/advanceTask/pollTask），F2 匹配流程接入。

### 4.3 具体步骤

1. database + tasks 服务层。
2. API 路由 + vercel.json。
3. data-bridge 任务化封装 + F2 前端进度条。
4. `tests/test_tasks.py`（幂等/推进/完成/越权）+ Node 契约测试 + 全量回归。
5. 同步 docs/public 镜像。

### 4.4 验收标准

- [x] 同 Idempotency-Key 重复提交返回同一任务（不重复执行）
- [x] 任务可查询进度、分片推进、最终 done 并落库
- [x] 游客/他人访问任务 403/404
- [x] 前端进度条随分片更新

## 5. 阶段 4：内容生态与体验

### 5.1 功能需求

- **面经题库 + RAG 检索**：内置 20+ 条种子面经（按 F3 场景分类），支持 BM25 检索（embedding 可选），前端知识库入口。
- **语音输入增强**：Web Speech 优先，百度/DashScope ASR 可配置；无 key 时 10 秒文字回退（现有 voice.js 契约不变）。
- **SSE 流式渲染 + 会话快照恢复**：F3 面试回答流式输出；刷新/断线后可从快照恢复会话。
- **简历优化器**：基于 F1 诊断 suggestions 生成可复写段落（模型或规则降级）。

### 5.2 技术实现路径

- `tools/knowledge.py`：面经数据加载 + BM25 检索（复用 jieba/BM25 实现），embedding 配置存在时升级为向量召回。
- `tools/providers/asr.py`：ASR provider 抽象（baidu/dashscope/mock）；`voice_handler.py` 改为经抽象调用。
- `api/index.py`：`/api/knowledge/search`、`/api/knowledge/questions`、`/api/wf04/stream`（SSE）、`/api/wf02/optimize`。
- 前端：知识库页 `pages/kb.html`（检索框 + 分类列表）；`voice.js` 适配 ASR provider；`f3-interview.html` 流式渲染 + sessionStorage 快照恢复；`f1-resume.html` 增加"应用建议改写"按钮。

### 5.3 具体步骤

1. 面经种子数据 + knowledge 检索服务 + API。
2. ASR provider 抽象与 mock。
3. SSE 流式接口 + 前端渲染 + 快照恢复。
4. 简历优化器 API + 前端接入。
5. 新增 pytest（knowledge/tasks/stream/optimize）+ Node 契约 + 全量回归 + 镜像同步。

### 5.4 验收标准

- [x] 面经可按关键词/分类检索，无 embedding key 时 BM25 可用
- [x] 语音无 key 降级不阻断面试主流程
- [x] SSE 流式渲染逐字显示；刷新后可从快照恢复会话
- [x] 优化器输出带"待确认"标记，用户确认后才落库

## 6. 阶段 5：工程化

### 6.1 功能需求

- **后端分层重构**：路由薄化，业务编排收敛到 services 层，保持 Vercel 单函数出口。
- **provider adapter + mock-first**：统一模型/检索/OCR/ASR provider 接口，无 key 时 MockProvider 全量可测。
- **投递闭环**：求职信生成（`/api/wf07/cover-letter`）+ 申请跟踪（`/api/wf07/applications` CRUD）+ 人工闸门（生成内容需用户确认后才保存）。

### 6.2 技术实现路径

- 新增 `services/`：diagnosis_service、match_service、interview_service、task_service、apply_service；`api/index.py` 仅保留参数校验与路由转发。
- 新增 `tools/providers/`：base.py（接口契约）、zhipu.py、mock.py、baidu_ocr.py、asr.py；`model_router.py` 改由 `MODEL_PROVIDER` 环境变量选择，默认 mock。
- 前端新增 `pages/f5-apply.html`：求职信生成预览 → 人工确认 → 存入申请跟踪表。

### 6.3 具体步骤

1. services 层抽取（机械搬迁 + 路由改造，先保证 325 项回归不变）。
2. providers 抽象 + model_router 改造 + mock 适配器。
3. 投递闭环 API + 前端页面。
4. 新增 pytest（provider mock/投递闭环）+ Node 契约 + 全量回归 + 镜像同步。

### 6.4 验收标准

- [x] 全量回归不低于现有基线（325+ 且只增不减）
- [x] 无任何 key 时 `pytest` 与 Node 契约全绿（mock-first 生效）
- [x] 求职信生成→人工确认→申请跟踪落库全链路可用
- [ ] Vercel 生产健康检查通过（收尾推送后验证，见交付说明）

## 7. 里程碑、交付物与依赖

| 里程碑 | 内容 | 交付物 | 依赖 |
|---|---|---|---|
| M1 | 阶段 1-2 完成 | Quick Demo + OCR/上传降级 + **第一次测试验收报告** | 无（OCR key 可选） |
| M2 | 阶段 3 完成 | 任务中心 + 幂等 + 前端进度 （pytest 338 / Node 31 全绿） ✅ | M1 |
| M3 | 阶段 4 完成 | 面经 RAG + ASR 抽象 + SSE + 优化器 （pytest 349 / Node 37 全绿） | M2 |
| M4 | 阶段 5 完成 | services 分层 + provider adapter + 投递闭环 （pytest 358 / Node 41 全绿） + **第二次全量测试验收报告** | M3 |

依赖关系：阶段间顺序执行（1→2→3→4→5）；阶段 4 的 ASR/embedding 真实服务依赖外部密钥，未提供时以 mock 交付并标注。

## 8. 两次测试验收报告约定

1. **第一次验收（M1，阶段 1-2 后）**：Quick Demo 演示链路、扫描件错误路径、上传进度/错误态；含 pytest/Node 新增用例结果与公网部署验证。
2. **第二次验收（M4，阶段 3-5 后）**：任务中心、SSE、知识库、优化器、投递闭环 + 全量回归（325 基线之上） + Vercel/GitHub Pages 线上验证。
3. 两份报告均按 AGENTS.md 双格式交付：Obsidian Markdown（`C:\Users\Administrator\Documents\Obsidian Vault\职业教练\YYYY-MM-DD_主题_类型.md`）+ 桌面 `.docx` 备份，核心正文一致。

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 外部密钥缺失（OCR/ASR/embedding） | provider 抽象 + mock-first；无 key 全链路降级可用，交付时明示"待配 key 激活真实服务" |
| Vercel 60s 函数上限 | 阶段 3 采用客户端驱动分片轮询，不做常驻 worker |
| Vercel 包体积限制 | OCR 用 REST API，不引入本地 OCR 引擎 |
| 沙箱无外网、提权被审批策略拦截 | 本地开发与测试在沙箱完成；推送/重部署命令输出给用户终端执行（或经 GitHub/Vercel MCP 验证云端状态） |
| 重构回归风险 | 阶段 5 分层先机械搬迁保行为不变，325 项基线全绿后再叠加新功能 |

## 标签

`#迭代规划` `#阶段1-5` `#QuickDemo` `#OCR` `#任务中心` `#SSE` `#RAG` `#工程化` `#竞品驱动`
