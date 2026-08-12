# career-coach · AI求职面试教练

> **项目状态：F1-F4 全接口已统一实现并回归通过（pytest 220 通过 / 4 跳过，Node 契约 7/7），六工作流自动化彩排 10/10 通过，G9 可自动材料已生成。**
>
> - ✅ 数据合同冻结（4 Schema + scoring.md）
> - ✅ 工具链已实现并测试通过
> - ✅ 提示词 7/7 已完成
> - ✅ 公开静态入口默认空态，未提交材料不展示合成诊断结果
> - ✅ 静态原型 6 页面完整
> - ✅ WF-01~06 后端接口统一实现（同意门/诊断/匹配/面试/能力报告/删除）
> - ✅ 10 次自动化彩排无阻断（deliverables/wf-evidence-*/rehearsal-10x.json）
> - ✅ 语音链路验证通过（18/18 PASS）
> - ✅ 官方链接核验完成（6/9 可达）
> - ⬜ P0-01 真实模型复测（待 API key）
> - ⬜ P0-03 端到端真实数据闭环（依赖 P0-01）
> - ⬜ G8 用户验证（模板就绪，待执行）
> - ⬜ G9 提交包冻结（可自动材料已生成，待平台/彩排/演示材料补齐后正式冻结）

iCAN 无代码开发挑战赛（DuMate 方向）参赛项目。
本仓库是**唯一事实源**：DuMate（百度搭子）做主产品，WorkBuddy 做分工开发，双方通过 git commit + HANDOFF 异步接力。

## MVP 四项（严格冻结）

| 编号 | 功能 | 产出合同 |
|---|---|---|
| F1 | 简历 AI 诊断打分 + 逐条修改建议 | ResumeProfile |
| F2 | 简历-JD 匹配度 + 关键词缺口 | JobProfile + 四态匹配 |
| F3 | 文字 AI 模拟面试（会追问，结束出表现报告） | InterviewTurn 序列 |
| F4 | 能力雷达图 + 七天竞争力情景推演 | AbilityProfile |

> 产品基线：**模型做语义，规则做分数，验证器做事实。** 所有关键节点均有降级路径。
> 口径注意：F4 的七天结果统一称「七天竞争力情景推演」，不得称「预测」。

## 目录导航

```
career-coach/
├── docs/            # 设计/技术汇总、测试报告、发布镜像（Pages 源）
├── contracts/       # 4 个 JSON Schema + scoring.md 评分公式（冻结层，禁止擅改）
├── workflows/       # WF-01~06 工作流定义（DuMate 负责实现）
├── prompts/         # resume / match / interview / plan 提示词模块
├── ui/              # prototype/ 静态高保真原型 + assets/
├── tools/           # WorkBuddy 交付的 8 个 Python 工具
├── tests/           # fixtures-synthetic 合成样本 + pytest 契约/故障注入测试
├── tasks/           # 任务看板规则
├── handoffs/        # HANDOFF-001~003 交接文件
└── deliverables/    # 最终提交包（DuMate 阶段产出）
```

## 快速开始

**看公开入口**：GitHub Pages 从 `docs/` 发布；本地可双击打开 `ui/prototype/index.html`。功能页默认均为等待用户材料的空态，普通 `?state=...` 参数不会展示诊断结果。

**内部 QA 演示**：仅限显式使用 `?demo=1&state=empty|processing|success|error|degraded`；该入口不在公开导航中，合成数据不得作为用户诊断结果使用。

> 上线边界：当前仓库仍处于真实上传、AI 调用及 DuMate 工作流集成阶段。公开静态页只提供前端入口；没有经过用户提交、服务端处理和证据校验的材料，页面不得展示评分、建议或匹配结论。

要让公开页完成真实上传与诊断，部署方必须在加载 `data-bridge.js` 前配置 `window.DUMATE_API_BASE`，并提供可从 Pages 域名访问的 `POST /api/wf01/upload` 与 `POST /api/wf02/diagnose` 服务。未接入时页面会明确显示失败状态，不会使用旧缓存或合成诊断代替用户结果。

### 生产 API 部署（Vercel）

仓库已包含 `api/index.py` 和 `vercel.json`，用于在 Vercel 部署真实上传与诊断服务。Vercel 项目需配置以下环境变量，所有密钥只能保存在 Vercel，不能写入 GitHub Pages 或仓库：

```text
ZHIPU_API_KEY=...
DUMATE_MODEL=glm-4.7-flash
# 可选：ZHIPU_FALLBACK_MODEL=...（备用智谱 Chat 模型）
DUMATE_CONSENT_SECRET=...          # 同意令牌签名密钥（生产必需）
DUMATE_ALLOWED_ORIGINS=https://zimo66067-wq.github.io,https://career-coach-o7eu.vercel.app
APP_ENV=production
DATABASE_URL=...              # 生产必需：Neon Postgres 连接串（账号/历史持久化）
SESSION_TTL_DAYS=30           # 可选：登录会话有效期（1-90 天）
# 可选：QIANFAN_API_KEY / QIANFAN_BASE_URL（千帆 V2 备用推理）
# 可选：ASR_API_URL / TTS_API_URL / BAIDU_SPEECH_TOKEN（百度语音备用通道）
# 可选：ADMIN_PASSWORD（/api/admin/* 管理员接口口令）
# 可选：RESUME_DB_PATH（SQLite 会话存储路径，仅本地/测试；生产配置 DATABASE_URL）
# 可选：DEV_DEMO（仅管理员演示数据注入，生产保持空）
```

API 已实现 WF-01~WF-06 全链路：

```text
POST /api/wf01/consent     签发短时效同意令牌（材料接口前置门）
POST /api/wf01/upload      简历上传（PDF/DOCX/TXT）→ 去标识化 → 持久化
POST /api/wf02/diagnose    简历诊断（主模型→备用→规则降级）→ R 分
POST /api/wf03/upload       JD 文件上传解析
POST /api/wf03/jd          JD 解析（JSON 或文件）→ JobProfile
POST /api/wf03/match       四态匹配（user_confirmed=true 必须）→ M 分
POST /api/wf04/start       面试开始（出题）
POST /api/wf04/answer      提交回答（STAR 缺口/追问/子串校验）
POST /api/wf04/end         面试结束（报告 + I 分）
POST /api/wf05/ability     能力报告（六维雷达 + C0 + 七天计划）
POST /api/wf06/delete      删除会话数据（DELETED 终态）
GET  /api/health           健康检查
GET  /api/admin/resumes    管理员：简历/诊断列表（X-Admin-Password）
GET  /api/admin/export     管理员：全量导出备份
POST /api/auth/register    注册（手机号+邮箱+密码+账户名）→ HttpOnly 会话 Cookie
POST /api/auth/login       登录（手机号或邮箱+密码）
POST /api/auth/logout      登出
GET  /api/auth/me          当前登录用户
GET  /api/history          当前用户历史记录（未登录为空）
POST /api/history          写入一条检测记录
DELETE /api/history/<id>   删除本人一条记录
```

F1/F2 采用规则评分与 BM25 兜底，不依赖 Embedding 密钥也可完整演示；配置智谱/千帆密钥后升级为语义路径。

Vercel 现已通过 `vercel.json` 重写同时托管静态前端（`/`→`/public/index.html`、`/pages/*`、`/js/*`）与 API；GitHub Pages 仍从 `docs/` 发布同一前端。部署完成后，将 Vercel 的 HTTPS 生产地址写入 `docs/js/pages-api-config.js` 的 `window.DUMATE_API_BASE`，并确保该脚本在 `data-bridge.js` 之前加载。API 会仅对 `DUMATE_ALLOWED_ORIGINS` 白名单来源返回 CORS 响应；文件原件只写入请求临时目录并在响应前删除。

**跑测试**（Windows）：

```bat
cd /d <本仓库目录>
set PY=C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe
%PY% -m pip install -r tools\requirements.txt
%PY% -m pytest tests\ -v
```

## 双 Agent 分工与文件所有权

| 角色 | 拥有目录 | 说明 |
|---|---|---|
| Product Agent | docs/ + contracts/ | 已冻结，改动须走变更流程 |
| Frontend Agent (WorkBuddy) | ui/ + prompts/ | 静态原型与提示词 |
| QA/Tool Agent (WorkBuddy) | tools/ + tests/ | 校验器、复算器、契约测试 |
| Workflow Agent (DuMate) | workflows/ + deliverables/ | 六个工作流与提交包 |
| Integration Agent | 合并 + 版本冻结 | 单一负责人 |

规则：两个 Agent 不得同时修改同一文件；交接必须先 commit 再写 HANDOFF；审查 Agent 只输出 review 报告。
