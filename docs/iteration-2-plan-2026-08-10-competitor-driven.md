# 职业教练 · 第二轮竞品驱动迭代计划（2026-08-10）

> 状态：**待用户确认，本计划尚未执行任何代码改动**
> 证据来源：`docs/competitor-analysis-2026-08-10.md` + 本仓库代码核查（2026-08-10）
> 范围：账号持久化专项 + 竞品弱项补强，分阶段落地

## 一、从 2.1-2.4 提炼：我们弱于竞品的模块清单

### 1.1 前端设计（2.1）

| 弱项模块 | 竞品最佳实践 | 影响 |
|---|---|---|
| 首用引导：无 Quick Demo 一键试玩 | DeepInterview：一键填充样例 CV+JD，零上传体验 | 新用户首用门槛高 |
| 流式渲染：无 SSE 流式回答 | FaceTomato：SSE 流式 + Markdown 渲染 + 快照恢复 | 面试/诊断等待体验差 |
| 语音交互：无语音输入/实时对话 | FaceTomato（语音输入）、zzzlip（多模态 ASR）、DeepInterview（voice-first） | 模拟面试真实感不足 |
| 国际化：仅中文 | DeepInterview：i18n 语言包 | 暂不影响国内定位，P2 可选 |
| 工程化：原生 HTML/JS 零构建 | Next.js/React + Tailwind | 原型期合理，产品期需组件化 |

持平项（不弱）：视觉体系（设计令牌 v2）、响应式适配、ECharts 三级降级 + F4 雷达图。

### 1.2 产品服务页面（2.2）

| 弱项模块 | 竞品最佳实践 | 影响 |
|---|---|---|
| 账号体系：localStorage 原型，无真实后端 | zzzlip Spring Security、DeepInterview Supabase auth | 多用户隔离与长期保存缺失（用户已实际踩坑） |
| 历史记录：本地假数据，无任务中心 | zzzlip 任务中心（全量状态/进度） | 历史不可信、无进度反馈 |
| 转化路径：诊断→报告单向，无投递闭环 | careerbot / AutoApply：起草申请→人工闸门提交 | 商业闭环缺失（P2） |
| 内容生态：无面经题库/内容站/社区 | FaceTomato 题库、prisma-ai 面经站、ig-club 社区 | 留存与引流缺失（P1） |
| 首用门槛：空态严格但无演示入口 | DeepInterview Quick Demo | 见 1.1 |

持平项（不弱）：四功能入口 + 侧边栏原型、空态/状态规范。

### 1.3 后端运行逻辑（2.3）

| 弱项模块 | 竞品最佳实践 | 影响 |
|---|---|---|
| 架构分层：Flask 单文件（约 55KB） | zzzlip 模块化单体 + 架构门禁 | 扩展与维护受限（P2） |
| 异步长任务：无任务中心/SSE/MQ/幂等 | zzzlip RabbitMQ + 任务中心 + SSE + Idempotency-Key | 长任务体验与可靠性（P0-4） |
| 存储：SQLite 文本 + Vercel /tmp 易失 | zzzlip MinIO、FaceTomato 服务端解析 | **账号数据无法长期保存（本轮核心）** |
| 安全：缺限流/审计/CSRF，原型明文密码 | zzzlip CSRF/限流/审计、DeepInterview RLS | 账号系统上线前必须补齐 |
| 可观测性：有 trace_id，缺审计日志面板 | zzzlip 审计日志 | 故障定位弱（P1） |
| 可测试性：缺 mock-first 离线开发 | DeepInterview provider adapter + mock | 无 Key 无法全量 CI（P2） |

强项（不弱）：PII 脱敏 + 同意门 + 生命周期删除；BM25 四态 + embedding 证据验证器（precision 97% / recall 84%）；pytest 覆盖 wf01-wf06 + 真机复测。

### 1.4 技术栈选型（2.4）

| 弱项 | 竞品主流 | 影响 |
|---|---|---|
| 模型层无 provider adapter / mock-first | DeepInterview provider matrix | 模型切换与离线开发困难（P2） |
| 存储单机 SQLite | Postgres/MySQL + Redis + 对象存储 | 多用户后必须升级（本轮） |
| 无消息/异步组件 | RabbitMQ / SSE | 长任务必须引入（P0-4） |
| 检索生态单薄（无面经库） | FAISS/LightRAG + 题库 | 有 embedding 地基，缺内容（P1） |

合理项（不弱）：Flask 轻量适配 Vercel、原生前端零构建（原型期）、SQLite 单机演示够用。

### 1.5 与 G1-G10 的对应关系

| 不足编号 | 内容 | 本轮归属 |
|---|---|---|
| G1 | 无公网演示 | 阶段 1 |
| G2 | 无语音/实时面试 | 阶段 4 |
| G3 | 文档解析未闭环 | 阶段 2（需修正，见 3.3） |
| G4 | 无真实用户体系 | **阶段 0（本轮核心）** |
| G5 | 长任务无异步架构 | 阶段 3 |
| G6 | 内容生态单薄 | 阶段 4 |
| G7 | 无流式/断点恢复 | 阶段 4 |
| G8 | 观测不足 | 阶段 4（随账号审计一并落地） |
| G9 | 单体无分层 | 阶段 5 |
| G10 | 模型策略单一 | 阶段 5 |

## 二、账号持久化与历史可见性专项方案（用户点名，最高优先级）

### 2.1 问题根因（代码级证据）

1. **登出即删号**：`ui/prototype/js/account.js` 只维护单条 `zy_account`（localStorage）。注册是直接覆盖该键；登出执行 `save(KEY_ACCOUNT, null)`，把唯一账号记录整个删除。登录逻辑只与当前单条记录比对 → 登出后再登录必然提示"没有注册过"。
2. **无用户表**：原型没有 `users` 列表，多账号互斥覆盖，本质上只支持"一个浏览器一个临时账号"。
3. **localStorage 按源隔离**：换端口、换域名（GitHub Pages / Vercel）、清缓存、换浏览器即全部丢失；无法跨设备。
4. **生产部署风险**：现有后端 SQLite 默认落在 Vercel `/tmp`，冷启动即清空（`.env.example` 与 `docs/account-system-plan-2026-08-06.md` 已注明）。即使把账号落到现有 SQLite，上线后仍会丢。
5. **密码明文**：`account.js` 将 `pwd` 原样写入 localStorage，违反安全规范。
6. **演示数据暴露**：`history()` 首次访问自动注入 s1-s6 六条种子记录，另有"添加演示记录"按钮 → 所有游客和注册用户都能看到开发演示数据；历史无用户归属。
7. **生产页面未接入**：账号侧边栏仅存在于 `ui/prototype`；`docs/` 与 `public/` 两套生产静态镜像均无 `account.js`。

### 2.2 解决方案总纲

**结论：需要引入外部持久化数据库 + 后端认证/历史 API + 前端真实接口替换 localStorage 原型。** 三者缺一不可：

| 层 | 现状 | 目标 |
|---|---|---|
| 存储 | localStorage / SQLite /tmp（易失） | 外部托管数据库（生产），本地 SQLite（开发） |
| 后端 | 无认证、无历史接口 | `/api/auth/*` + `/api/history/*`，user_id 归属校验 |
| 前端 | account.js 假数据原型 | 真 API 客户端；游客零历史；仅本人可见；演示数据仅 admin |

#### 数据库选型决策矩阵

| 方案 | 优点 | 缺点 | 适配度 |
|---|---|---|---|
| **A. Neon Postgres（推荐）** | Vercel 原生集成、免费 0.5GB、标准 SQL、长期扩展性好 | 需 Vercel 项目授权/连接串；与现有 SQLite 代码需适配层 | ★★★★★ |
| B. Supabase | 免费额度大、自带 Auth/RLS，可省自建登录 | 引入外部平台依赖；国内访问需评估 | ★★★★ |
| C. Turso/libSQL | SQLite 协议兼容，迁移成本最低 | 免费层限制；生态相对小众 | ★★★ |

**建议**：生产用方案 A（Neon），本地开发继续 SQLite；`tools/database.py` 增加一层 store 适配（`db_connect()` 按 `DATABASE_URL` 环境变量选择 SQLite/Postgres），现有表 SQL 保持兼容。若用户希望最快上线且不愿申请 Neon，方案 B（Supabase 自带 Auth）是第二选择。

#### 数据模型（Postgres/SQLite 双兼容）

```sql
CREATE TABLE users (
  id            BIGSERIAL PRIMARY KEY,
  phone         TEXT UNIQUE NOT NULL,
  email         TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,          -- werkzeug/scrypt，绝不存明文
  display_name  TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'user',   -- user | admin
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at TIMESTAMPTZ
);

CREATE TABLE sessions (
  id         TEXT PRIMARY KEY,          -- 服务端会话令牌（哈希存储）
  user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE history_events (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_id TEXT NOT NULL,             -- 关联现有 wf01-06 会话数据
  event_type TEXT NOT NULL,             -- F1 / F2 / F3 / F4
  title      TEXT NOT NULL,
  status     TEXT NOT NULL,             -- done / partial / failed
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_history_user ON history_events(user_id, created_at DESC);
```

说明：现有 `resumes / matches / interview_sessions / abilities / diagnoses` 不动，通过 `session_id + history_events.user_id` 完成归属映射，避免大改现有数据流。

#### API 设计

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/register` | 手机号/邮箱/密码/账户名 → 哈希入库 → 自动登录 |
| POST | `/api/auth/login` | 手机号或邮箱 + 密码 → 签发会话 |
| POST | `/api/auth/logout` | 注销会话 |
| GET | `/api/auth/me` | 当前登录态 + 脱敏信息 + role |
| GET | `/api/history` | 分页拉取**本人**历史（type 过滤） |
| POST | `/api/history` | 检测完成后自动落库（服务端同时校验 session 存在） |
| DELETE | `/api/history/:id` | 删除单条历史，级联删除会话数据（复用 `delete_session_data`） |

#### 会话与安全

- 密码哈希：`werkzeug.security.generate_password_hash`（Flask 自带依赖，不新增包；生产可调高 method）。
- 会话：GitHub Pages 跨域承载前端 → Cookie `HttpOnly + Secure + SameSite=None` + CORS `Allow-Credentials`；前端保留 Authorization Bearer 回退（浏览器拦截第三方 Cookie 时）。同域部署时自动降级 `SameSite=Lax`。
- 越权防护：所有 history 接口强制校验 `user_id` 归属；查询他人或游客会话一律 403/404。
- 限流：注册/登录按 IP + 账号维度 5 次/分钟；手机号/邮箱唯一约束兜底。
- 密码字段：注册表单文案明确"设置平台登录密码，勿使用邮箱本身的密码"（沿用 08-06 规划中的安全纠正）。

### 2.3 侧边栏可见性规则（明确需求 → 行为矩阵）

| 状态 | 历史区 | 用户卡 | 演示数据 |
|---|---|---|---|
| 未登录游客 | **不渲染任何记录**，显示"登录后可长期保存"空态 | 游客 + 登录/注册按钮 | 无 |
| 已登录普通用户 | 仅本人 `history_events` | 姓名 + 脱敏手机号/邮箱 + 退出 | 无 |
| 管理员/开发者（role=admin） | 本人记录 + 演示记录 | admin 标识 | 仅 `DEV_DEMO=1` 时注入 |

实现要点：

1. 删除 `account.js` 中 `seed` 数组、`extraTitles`、`addMockRecord` 逻辑；演示数据改为后端按 `role=admin + DEV_DEMO` 环境变量注入。
2. 每次页面加载先 `GET /api/auth/me` + `GET /api/history`；未登录时历史区渲染空态，不做任何本地兜底假数据。
3. 检测完成后：登录用户 `POST /api/history` 落库；游客不落库，提示"注册后历史可长期保存"。
4. 回看安全：`?session=` 回看必须校验归属；游客/他人会话不返回数据。
5. 生产镜像同步：以 `ui/prototype` 为源，将 account.js/sidebar.css 单向同步到 `docs/` 与 `public/`，纳入收尾检查。

### 2.4 前端改造点

- `account.js` 重写为 API 客户端：fetch + credentials/token，移除 localStorage 账号逻辑；保留侧边栏折叠、移动端抽屉、回看条 UI。
- `data-bridge.js` 统一携带会话；`pages-api-config.js` 增加同域/跨域 API Base 配置。
- 所有页面（index、F1-F4、states）统一挂载侧边栏组件；API 不可用时历史区静默降级，不阻塞主流程。
- 表单校验沿用原型（手机号 11 位、邮箱格式、密码 ≥8 位含字母数字、账户名 2-16 字符），错误内联展示。

### 2.5 测试与验收（账号专项）

- pytest：注册唯一性（手机号/邮箱重复 409）、登录成败、登出、me、历史 CRUD、越权 403、密码哈希非明文、限流。
- Playwright：游客零历史 → 注册自动登录 → 检测落库 → 登出 → **再登录历史仍在** → 第二个账号看不到第一个账号数据 → 删除历史后会话数据级联删除。
- 真机多浏览器验证 + 手机端抽屉；部署后公网实测"注册 → 隔天登录 → 历史仍在"。

## 三、完整迭代计划（分阶段）

### 阶段 0：账号系统 + 持久化 + 历史归属（本轮核心，3-5 人日）

- 交付物：users/sessions/history_events 表；auth/history API；account.js 真接口改造；侧边栏可见性规则；Neon（或确认 Supabase）接入；docs/public 同步。
- 里程碑：M0.1 后端 API 全绿 → M0.2 前端接入 → M0.3 多用户隔离验收 → M0.4 部署验证。
- 依赖：需用户确认数据库选型与连接权限。

### 阶段 1：公网部署 + Quick Demo（P0-1，0.5-1 人日）

- 保持现有架构：GitHub Pages 静态界面 + Vercel API；跨域会话已通过 `SameSite=None; Secure` Cookie + CORS Credentials 解决（详见阶段 0 执行记录）。
- DeepInterview 式 Quick Demo：一键填充样例 CV+JD，30 秒内体验 F1/F2（mock 数据与入口已有基础）。
- 验收：外部人员无账号、无文件也可完整走通一次诊断与匹配。

### 阶段 2：文档解析闭环补强（P0-2 修正，1-2 人日）

- **事实修正**：核查代码后确认，后端 `read_uploaded_document` 已支持 PDF/DOCX/TXT 服务端解析，前端 `data-bridge.uploadResume` 已通过 FormData 上传 `/api/wf01/upload`。竞品报告中 G3"解析未闭环"应修正为：**扫描件 OCR 兜底缺失 + 上传失败降级路径未验证**。
- 新增：扫描件 OCR（接入免费 OCR 服务或明确提示粘贴文字）；上传进度/失败错误态完善；对 docs/public 两套镜像实测上传链路。

### 阶段 3：任务化 + SSE 进度（P0-4，2-3 人日）

- 任务表 `tasks(id, user_id, kind, status, progress, result_ref)` + 轮询或 SSE；先覆盖 F3 面试与 F2 匹配长任务。
- 幂等键：客户端生成 `Idempotency-Key`，服务端去重。
- 约束说明：Vercel 函数单次上限 60s，长任务需异步 Worker（外部队列）或拆分为多轮轮询任务；SSE 用于前端进度展示，后端仍按轮询推进。

### 阶段 4：内容生态与体验（P1，约 10-14 人日）

- 面经题库 + RAG 检索（复用 embedding 验证器）；语音输入（ASR→文本，百度/DashScope 已集成过）；前端 SSE 流式渲染 + 会话快照恢复；简历生成/优化器。
- 可选：prisma-ai 式内容站引流、ig-club 式社区。

### 阶段 5：工程化（P2，约 13-17 人日）

- 后端分层重构（domain/application/interface，保留 Vercel 单函数出口）；provider adapter + mock-first；投递闭环（求职信/申请跟踪/人工闸门）。

### 依赖与风险

| 风险 | 缓解 |
|---|---|
| 外部数据库需要密钥/项目权限 | 用户确认选型后提供；密钥只入 Vercel 环境变量，不进仓库 |
| GitHub Pages 跨域 Cookie 限制 | 已用 SameSite=None;Secure + CORS Credentials 解决；浏览器拦截第三方 Cookie 时前端回退 Authorization Bearer |
| Vercel 函数 60s 限制 | 阶段 3 任务化按轮询/拆分子任务设计 |
| 国内访问外部数据库延迟 | Neon/Supabase 选亚太区；本地开发用 SQLite |

## 四、等待用户确认的事项

1. 数据库选型：A Neon Postgres（推荐）/ B Supabase / C Turso，并确认能否提供 Vercel 项目权限或连接串。
2. 部署形态：是否接受"Vercel 同域为主、GitHub Pages 保留镜像"。
3. Quick Demo（阶段 1）是否与账号系统（阶段 0）同批执行。
4. 管理员演示数据开关：`role=admin + DEV_DEMO` 方案是否认可。
5. 确认后执行顺序：阶段 0 → 1 → 2 → 3；阶段 4/5 另行排期。

---

# 五、执行记录（阶段 0 · 2026-08-10 追加）

> 用户已确认：数据库选 A（Neon）、Quick Demo 延后、DEV_DEMO 方案认可、GitHub Pages 与 Vercel 双部署同步。

## 5.1 已完成（代码已落地，本地测试全绿）

| 模块 | 改动 |
|---|---|
| tools/database.py | SQLite/PostgreSQL 双方言适配（DATABASE_URL 优先）；新增 users / sessions / history_events 表及持久化函数 |
| tools/account.py | 注册/登录/登出/会话/历史服务；werkzeug 密码哈希（不存明文）；按 IP 限流；role=admin + DEV_DEMO=1 时注入演示数据（不落库） |
| api/index.py | `/api/auth/register|login|logout|me`、`/api/history` GET/POST/DELETE；HttpOnly 会话 Cookie（生产 SameSite=None;Secure）；CORS 支持 DELETE/Authorization/Credentials |
| vercel.json | 新增 auth/history 路由重写 |
| requirements.txt | 新增 psycopg（Neon Postgres 驱动） |
| .env.example | 新增 DATABASE_URL / SESSION_TTL_DAYS / DEV_DEMO 说明 |
| 前端 | account.js 重写为真 API 客户端；游客零历史、仅本人历史；docs/public/ui 三树同步；6 个页面注入侧边栏；data-bridge 在 F1-F4 完成后自动落库 |
| 测试 | 新增 tests/test_account.py（6 项）；全量 pytest 228 passed / 4 skipped；node 镜像契约 7 passed |

## 5.2 待完成（依赖外部）

1. Vercel 环境变量配置 DATABASE_URL（Neon）→ 生产持久化（否则 Vercel 上仍回退 SQLite /tmp，账号会随冷启动丢失）。
2. 代码提交推送 main 后，验证 GitHub Pages 与 Vercel 双部署状态。
3. 阶段 1 Quick Demo（用户确认延后）。

## 5.3 Neon 接入与双部署操作步骤（用户操作）

### 方式 A（推荐）：Vercel 市场集成 Neon Postgres

1. 打开 Vercel → 项目 career-coach → **Settings → Integrations → Marketplace → Neon Postgres** → Add/Install。
2. 安装时选择本项目，区域选 **Singapore 或 Tokyo**（降低国内访问延迟）。
3. 授权创建 Neon 项目；集成完成后自动写入环境变量 `DATABASE_URL`（Production/Preview 均可用）。
4. 到 **Project → Settings → Environment Variables** 确认 `DATABASE_URL` 已存在后 Redeploy。

### 方式 B：手动创建连接串

1. 注册/登录 [neon.tech](https://neon.tech) → **New Project** → 区域选 Singapore/Tokyo。
2. 项目页 → **Connect** → 选 **Pooled connection**（serverless 必须用 pooler 地址）→ Copy。
3. 连接串格式：`postgresql://user:password@ep-xxx-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`
4. Vercel → **Project → Settings → Environment Variables** → 新增 `DATABASE_URL`（勾选 Production）→ Redeploy。

### 所需权限

- Vercel 项目 **Owner/Admin**（安装集成或设置环境变量）。
- Neon 项目 **Owner**（查看连接串；集成方式下 Vercel 代管）。
- 密钥只配置在 Vercel 环境变量，**严禁写入 GitHub 仓库**。

### 双部署同步

- GitHub Pages：仓库 **Settings → Pages → Source = Deploy from a branch → main → /docs**；推送 main 后自动更新静态界面。
- Vercel：项目连接 GitHub 仓库 main 分支；推送 main 后自动构建部署 API。
- 我将在你确认 DATABASE_URL 配置完成后提交推送 main，并逐一验证两个线上地址与账号持久化（注册→登出→再登录→历史仍在）。

## 标签

`#迭代计划` `#账号系统` `#数据库` `#竞品驱动` `#历史记录` `#用户体系` `#技术选型`
