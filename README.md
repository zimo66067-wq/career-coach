# career-coach · AI求职面试教练

> **项目状态：F1–F4 全接口已统一实现并回归通过（pytest 482 通过，Node 契约 42/42），六工作流自动化彩排 10/10 通过。**
>
> 正在按「证据驱动的 AI 求职教练」做收敛式重构（**Phase 6a 已完成**）：删除了专业→职业匹配、C7 预测区间、
> 独立面经知识库页、整条语音链路与 4 条死路由；修掉最后 2 处依赖倒置并加静态分层门禁；
> 删掉第三棵前端树 `ui/`，前端收敛为 `public/`（canonical）+ `docs/`（发布镜像）。
> **详细删除清单见 `CHANGELOG.md`，分阶段报告见 `docs/phase1-report.md` ~ `docs/phase6a-report.md`。**
>
> - ✅ 数据合同冻结（4 Schema + scoring.md）
> - ✅ 工具链已实现并测试通过
> - ✅ 提示词 7/7 已完成
> - ✅ 公开静态入口默认空态，未提交材料不展示合成诊断结果
> - ✅ 公开页面：首页 + 5 个功能页（F1 简历诊断 / F3 模拟面试 / F4 能力报告 / F5 投递 / 状态样例）
> - ✅ WF-01~06 后端接口统一实现（同意门/诊断/匹配/面试/能力报告/删除）
> - ✅ 10 次自动化彩排无阻断（deliverables/wf-evidence-*/rehearsal-10x.json）
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
| F4 | 当前能力快照（C0 + 六维）+ 七天行动计划 | AbilityProfile |

> 产品基线：**模型做语义，规则做分数，验证器做事实。** 所有关键节点均有降级路径。
> 口径注意：C0 与六维分是**当前证据快照**，不代表真实就业概率；F4 不再输出任何预测区间
> （原「七天竞争力情景推演」基于固定 0.30/0.70 演示假设，已于 2026-09-13 删除）。

## 目录导航

```
career-coach/
├── public/          # 前端唯一 canonical（Vercel 生产静态根）
├── docs/            # 设计/技术汇总、测试报告 + 发布镜像（Pages 源）
├── contracts/       # 4 个 JSON Schema + scoring.md 评分公式（冻结层，禁止擅改）
├── workflows/       # WF-01~06 工作流定义（DuMate 负责实现）
├── prompts/         # resume / match / interview / plan 提示词模块
├── tools/           # WorkBuddy 交付的 8 个 Python 工具
├── tests/           # fixtures-synthetic 合成样本 + pytest 契约/故障注入测试
├── tasks/           # 任务看板规则
├── handoffs/        # HANDOFF-001~003 交接文件
└── deliverables/    # 最终提交包（DuMate 阶段产出）
```

## 快速开始

**看公开入口**：Vercel 生产静态根是 `public/`（`vercel.json` 把 `/`、`/index.html` 与 `css`、`js`、`pages`、`assets` 四类路径重写到 `public/`）；GitHub Pages 从 `docs/` 发布同一前端。本地直接双击打开 `public/index.html` 即可。功能页默认均为等待用户材料的空态，普通 `?state=...` 参数不会展示诊断结果。

> **同步约定**：`public/` 是唯一 canonical。两棵树下所有**非 `.md`** 文件必须集合相同且逐字节相同 ——
> 由 `tests/test_publish_mirror.js` 门禁守住，用 `python scripts/sync_mirror.py` 修复漂移。
> （2026-09-17 已删除第三棵树 `ui/prototype`：它是陈旧分叉 + `assets` 重复副本，未部署且含 7 处坏引用。）

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
# 只需列**跨源**的前端。Vercel 自己托管的页面是同源，origin_allowed() 直接放行
# （api/http_layer.py 里 `normalized == request.host_url` 那一条），不必登记。
# 因此这里只有 GitHub Pages 的源；不要在名单里写已经下线的 Vercel 域名 —— 它会被
# 当成"这个源能用"的证据留下来，而真正要问的是它还在不在。
DUMATE_ALLOWED_ORIGINS=https://zimo66067-wq.github.io
APP_ENV=production
DATABASE_URL=...              # 生产必需：Neon Postgres 连接串（账号/历史持久化）
SESSION_TTL_DAYS=30           # 可选：登录会话有效期（1-90 天）
# 可选：QIANFAN_API_KEY / QIANFAN_BASE_URL（千帆 V2 备用推理）
# 可选：ADMIN_PASSWORD（/api/admin/* 管理员接口口令）
# 可选：RESUME_DB_PATH（SQLite 会话存储路径，仅本地/测试；生产配置 DATABASE_URL）
# 可选：DEV_DEMO（仅管理员演示数据注入，生产保持空）
```

> **上线自检**：`python scripts/api-prod-probe.py` 一次跑出两件事 —— 线上静态资源是不是就是
> 本地 HEAD，以及业务接口是不是真的通。它填的是别处判据的观察面空洞：
> `scripts/vercel-dead-routes.py` 只比**配置**（配置全对、线上函数没起来时它照样绿），
> `scripts/p0-05-link-check.py` 只判链接**可达**，`scripts/phase4-http-smoke.py` 起的是**本地**端口。
> 2026-09-20 实测就是这三者全绿、而 `/api/*` 每个路径都返回同一个 404 的状态。
> 修完部署后用它复跑：`--origin` 可以指向任意环境。

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
| Frontend Agent (WorkBuddy) | public/ + prompts/ | 前端发布树（唯一 canonical）与提示词 |
| QA/Tool Agent (WorkBuddy) | tools/ + tests/ | 校验器、复算器、契约测试 |
| Workflow Agent (DuMate) | workflows/ + deliverables/ | 六个工作流与提交包 |
| Integration Agent | 合并 + 版本冻结 | 单一负责人 |

规则：两个 Agent 不得同时修改同一文件；交接必须先 commit 再写 HANDOFF；审查 Agent 只输出 review 报告。
