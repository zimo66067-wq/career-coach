# 上线剩余步骤清单

这份文档回答一个问题：**离"真实用户能走通一个完整流程"还差什么。**
它是这件事的唯一台账 —— 状态只在**实测过**之后才改；没实测就老实写「未验证」。

标注：**【你】** = 只有账号持有人能做的（控制台、凭据、真人、业务决策）；**【我】** = 仓库内可代做的。
完成一条就把它的状态改成 ✅（附实测证据），不要凭印象勾。

> **当前状态（2026-09-21）**：**线上主渠道已经通了** —— 生产 `/api/health` = 200，
> 其余接口都由应用应答，静态资源与 HEAD 逐字节相同。§一记录的是那个阻断的根因与修法
> （留着是因为下一次同类症状会以同样的样子出现）；**现在需要你做的都在 §一末与 §二、§三**。
>
> §一末那条"GitHub Pages 调不到 API"已于同日**在代码侧修掉**（放行名单改成并集），
> 剩一步：这次改动推上主干、部署完成后再跑一次探针确认第 3 节三行都 `OK`。

---

## 一、原阻断项（2026-09-21 已解除）与根因记录

判据不是"首页能不能打开"，而是 **`/api/*` 有没有被应用接住**。
一条命令给出现状（它自己按前端字面量找探测源，不写死域名）：

```bash
.venv-audit/Scripts/python.exe scripts/api-prod-probe.py
```

2026-09-20 实测：线上静态资源 = HEAD（3 个新鲜度探针全 OK），
但 `/api/*` 的**每一个**路径都返回同一个 404，且不带应用无条件设置的 `Cache-Control: no-store`。

### 根因（2026-09-21 由**本地复现**定案，不是推断）

线上返回的是 **Werkzeug 默认 404**（207 B、md5 `e46c4e5e1fbc`）。
在本地，**只 import `api/app_instance.py`**（当时叫 `api/app.py`）时，
`/api/health` 返回的正是 **404 / 207 B / md5 `e46c4e5e1fbc` / 无 `no-store`** —— 与线上逐字节相同；
而 **import `api/index.py`** 时同一路径返回 **200 / 591 B / 带 `no-store`**。

⇒ **Vercel 的 Flask 预设按文件名挑入口**（文档给的候选名：`app.py` / `index.py` / `server.py` /
`main.py` / `wsgi.py` / `asgi.py`，位置是仓库根，以及 `src/`、`app/`；实测 `api/` 也会被搜到），
而 `app.py` 排第一顺位。仓库里当时恰好有一个 `api/app.py`（现已改名）—— 那是 Phase 7c 为消除循环 import 把
app 对象下沉成的**叶子模块**（只 `Flask(__name__)`，不注册任何路由）。预设 import 的就是它。

一个**看起来像反证、其实不是**的点：`api.app_instance.app is api.index.app` 为真。
平台只 import 入口那一个模块，**是不是同一个对象无所谓**，"import 它的时候有没有顺带把路由注册上去"才决定线上行为。

### 修法（都在仓库里，不需要改预设）

1. **把原来是 `api/app.py` 的叶子模块改名 `api/app_instance.py`**（旧路径已修，勿再引用）—— 把错的候选名从名单里拿掉。改名后 `api/` 下
   与入口有关的候选只剩 `index.py`（正确的那个），**解析顺序不再是变量**。
2. **根目录 `app.py`** —— 把**同一个** app 对象绑定在根目录的候选名上。文档说根目录优先，
   所以这是"第一顺位"的那条路径；即使顺序与文档不符，第 1 条也已经兜住了。
3. **新增 `scripts/entrypoint-resolution-check.py`** —— 逐个候选名在**全新子进程**里 import，
   要求每个都解析出"规则数 > 1 且 `/api/health` = 200"。**这是唯一能在本地抓住这类 bug 的判据**：
   `tests/` 全都显式 `from api.index import app`，走的直连路径，从来看不见"按文件名会解析到谁"。

### 一次失败的尝试（别再走一遍）

先试的是 `pyproject.toml` + `[tool.vercel] entrypoint = "api.index:app"`（这是官方文档给的
另一个显式声明方式）。**结果构建直接失败**（部署 `dpl_5C4T1VTqfAibMjrHDXetHndVJcnd`）：
**`pyproject.toml` 一存在，平台就改用它作为依赖来源**，以本仓库为 Python 项目去安装；
而本仓库是 flat layout、有多个顶层包（`api`/`domain`/`providers`/`repositories`/`services` …），
setuptools 自动发现报 `Multiple top-level packages discovered`。本地可复现：

```bash
.venv-audit/Scripts/python.exe -m pip install --dry-run --no-deps .
```

所以 `pyproject.toml` **已被删除**，依赖仍走 `requirements.txt`；入口用"文件名"这条路径声明。

| # | 事项 | 谁 | 怎么做 / 判据 |
|---|---|---|---|
| 1 | 核对 Vercel 项目构建设置 | **【你】** | Settings → Build and Deployment：**Root Directory 留空**（= 仓库根 ✅ 已确认）、**Framework Preset 保持 `Flask`**、**Output Directory 留 `N/A`**（Flask 预设自己管静态根 —— 线上 `/capability_matrix.md` 正是从 `public/` 取的，说明它对）。**⚠️ 不要改成 `Other`**：那会切回"`api/` 下每个 `.py` 各自是函数"的约定，而本目录有 25 个 `.py`，其中 23 个不导出任何 handler。 |
| 2 | 补齐生产环境变量 | **【你】** | Settings → Environment Variables（Production）：`ZHIPU_API_KEY`、`DUMATE_MODEL`、`DUMATE_CONSENT_SECRET`、`DATABASE_URL`、`APP_ENV=production`。缺 `DUMATE_CONSENT_SECRET` 会让同意令牌直接失败。`DUMATE_ALLOWED_ORIGINS` 属**追加**项（2026-09-21 起语义是并集，见 §一末）：**不设也照样能用 GitHub Pages 渠道**，只有要额外放行别的跨源前端时才需要填。 |
| 3 | ~~入口修复进主干后点 Redeploy~~ | — | ✅ **已完成**（2026-09-21）：修复（`ec1ce27`）推上主干后 Vercel 自己建了生产部署，**状态 success**，不用手点。 |
| 4 | ~~复跑探针确认阻断解除~~ | **【我】** | ✅ **已完成**：`scripts/api-prod-probe.py` **退出码 0** —— 静态 = HEAD、`/api/health` = **200**、其余接口都是应用在应答（415 / 428 / 404 带 `no-store`）。 |
| 5 | ~~取 Functions 列表与 Build Logs~~ | — | ✅ **不需要了**（定案靠本地隔离 import 对照，没用到平台日志）。保留此行的理由：万一以后又出现同类症状，这是最后一条后备取证手段。 |
| 6 | 端到端冒烟（F1→F5 真流程） | **【我】** | 仓库里已有 `scripts/run-wf-e2e.py`、`scripts/phase4-http-smoke.py`、`scripts/run-rehearsal.py`。⚠️ 注意 `phase4-http-smoke.py` 起的是**本地**端口、清掉了 `ZHIPU_API_KEY`，所以它验的是"路由与状态机"，**不是**"真模型能跑"（那要 P0-01/P0-03）。 |

### 另一条渠道：GitHub Pages 前端调不到 API（已修复，代码侧，2026-09-21）

生产域名**既是页面也是 API**，从它打开是**同源**、CORS 不参与 —— 所以主渠道一直可用。
但仓库里还有一个**跨源**前端（GitHub Pages）：`https://zimo66067-wq.github.io/career-coach/`
**实测在线**（200，`js/pages-api-config.js` 就在那儿），而那个文件存在的唯一理由
就是给非 Vercel 宿主的页面找 API 地址。2026-09-21 实测它是坏的：

```
预检 OPTIONS /api/wf01/consent  Origin=https://zimo66067-wq.github.io  code=204  ACAO=(无)
POST   /api/wf03/jd             Origin=https://zimo66067-wq.github.io  code=403  「请求来源未获授权」
```

⇒ 从 GitHub Pages 打开页面时，**浏览器会拦掉所有接口调用**，写操作还会被应用直接 403。

**原因（是一个语义错，不是漏配）**：`api/http_layer.py` 的 `configured_origins()` 原来写的是
"平台变量覆盖默认值"。默认值本身是对的（不设置时就是那个 Pages 源），但只要**设置了**这个变量
（哪怕是为了别的源），默认值就被整体换掉 —— 于是"**忘了把第一方源也列进去**"成了比
"根本没设置"更坏的配置。三处都看不见：仓库里（默认值是对的）、本地/CI（同源不经过 CORS）、
门禁（没有判据探线上配置）。

**修法（已在仓库里改掉，不用你动控制台）**：放行名单改成 **并集** ——
`builtin_origins()`（= `PUBLIC_PAGES_ORIGIN`，**永远放行**）∪ `env_origins()`
（平台变量 `DUMATE_ALLOWED_ORIGINS` 里**追加**的源）。于是"平台侧的省略"不再能关掉第一方渠道；
真要禁掉它只能改代码，那会是一次 review 里看得见的 diff（**这是决定，不是遗漏**）。
`DUMATE_ALLOWED_ORIGINS` 仍然有用，但语义变成"追加"，**不设也照样能用 Pages 渠道**。

**验收判据（已升级为硬门）**：`scripts/api-prod-probe.py` 第 3 节现在探三件事 ——
第一方源预检必须拿到 ACAO、写操作不得是 403、**敌对源（保留 TLD `*.invalid`）必须拿不到 ACAO**。
第三条是反向控制：没有它，"把名单写成全放行"也会是绿的。

**已做的本地验证**（不必等部署）：`work/verify-cors-fix.py` 起两个本地 app 用同一个探针探 ——
真实现退出 0；把 `origin_allowed` 换成无条件放行后退出 1，且失败项正是反向控制那条。
单元层面 `tests/test_api_boundary.py::test_cors_builtin_pages_origin_survives_env_override`
即是那个语义的反向控制（改回"替换"语义立刻变红）。

**部署后确认（已做完，2026-09-21 12:0x）**：这两笔改动推上主干（`404e656..0242a89`）后，
GitHub Deployments API 显示 **`0242a89` 的 Production 部署 = success**（`github-pages` 同 SHA 也 success），
随后 `python scripts/api-prod-probe.py` **退出码 0**，第 3 节三行全是 `OK`：

```
预检 OPTIONS /api/wf01/consent  Origin=https://zimo66067-wq.github.io  code=204  ACAO=它自己
写操作 POST /api/wf03/jd        Origin=https://zimo66067-wq.github.io  code=428（不是 403）
反向控制 同一路径                Origin=https://probe-hostile-origin.invalid  code=204  ACAO=(无)
```

⇒ **GitHub Pages 那条渠道现在真的能调 API 了**，而且没有变成"全放行"。日志留档：
`work/probe-after-cors-fix.log`。**这一步不需要你做什么**（原来挂着的"要不要支持这个渠道"
已由你在 2026-09-21 决定为"支持"，修法落到了代码里，不用动控制台）。

**一个已知的非阻断现象**：`career-coach-<hash>-zimo66067.vercel.app` 这类**部署 URL** 会 302 到 Vercel 登录
（Deployment Protection），但**生产别名**是公开可达的。所以"部署 URL 打不开"不等于线上不可用；
反过来也别把"别名能打开"当成"部署没问题"。

**另一个已经踩过的坑**：本机 `git status` 会假报 `[ahead N]`。
原因是 `.git/refs/remotes/origin/` 这个目录不存在，git 写松散 ref 失败但静默返回 0。
**判定"推没推上去"只认远端**：`git ls-remote origin refs/heads/main`。
不要因为它假报 ahead 就重推或 force。

---

## 二、上线前必须完成的验证与交付

| # | 事项 | 谁 | 说明 |
|---|---|---|---|
| 7 | P0-01 真实模型复测 | **【你】** 给凭据 / **【我】** 跑 | 需要真实模型 key；无 key 时该项只能停在"未验证"。 |
| 8 | P0-03 端到端真实数据闭环 | **【我】** | 走 `scripts/p0-03-real-model-test.py`，依赖第 7 项。 |
| 9 | G8 真实用户验证（≥5 名真实参与者） | **【你】** | 模板已就绪；这件事**没有人能替你**，且必须真人才算数。 |
| 10 | G9 提交包冻结 | **【我】** 起草 / **【你】** 定稿 | 走 `scripts/p0-07-freeze.py`：方案 PDF（≤20 页 / ≤50MB）、演示 MP4（≤4 分 30 秒 / ≤500MB）、200 字简介、分享 URL、skill 导出、freeze-checklist、commit 记录。 |
| 11 | 仓库可见性口径 | **【你】** 决策 | 提交清单里写的是"私有仓库"，而当前仓库是公开的。要么改口径，要么改设置 —— 需要你定。 |

---

## 三、业务决策（只有你能定，且定了才能对外说）

| # | 事项 | 谁 | 说明 |
|---|---|---|---|
| 12 | F5 五项业务决策 | **【你】** | 数据授权 / 预算 / 责任人等，逐项见 `docs/product-scope.md` 与 F5 计划文档。 |
| 13 | D3（单位 / 职位检索） | **【你】** | 期限 2026-10-13。**决策之前不得对外宣称有单位库或实时职位覆盖。** |

---

## 四、这一轮已经在仓库内落地的（可复跑，不是声明）

| 产物 | 它填的观察面空洞 |
|---|---|
| `scripts/api-prod-probe.py` | 只有它同时看「线上静态是否 = HEAD」与「接口是否真的被应用接住」。原有的 `scripts/vercel-dead-routes.py` 只看配置、`scripts/p0-05-link-check.py` 只判链接可达、`scripts/phase4-http-smoke.py` 打的是本地端口 —— 三者可以全绿而线上一个流程都走不通。探测源从 `public/js/pages-api-config.js` 的字面量推导，避免此处再抄一份会漂移的域名。 |
| `scripts/vercel-dead-routes.py`（新增方向 B） | 原来只判「重写 → 处理分支」。新增「本地路由 → 重写覆盖」：`api/index.py` 里新增一条 `/api/xxx` 却忘了在 `vercel.json` 加 `source` 时，本地全绿、线上静态 404。判据自带反向控制探针（抽掉一条重写必须变红），防止它"绿着失效"。 |
| `docs/release-checklist.md`（本文） | 把"还差什么"从散落的对话与报告里收成一份带责任人的台账，并登记进 `contracts/living-docs.json` 的观察面。 |
| `scripts/entrypoint-resolution-check.py` | **唯一能看见"平台会解析到哪个入口"的判据**。它对每个候选入口名在**全新子进程**里 import，要求都能得到"带路由的 app"。缺了它，`tests/`（全都显式 import `api.index`）与 CI 可以全绿，而线上跑的是另一个模块。自带反向控制：同一段测量代码必须能把裸 app 判成无路由、把带路由 app 判成有路由，否则报红。 |
| `api/app_instance.py`（原来的 `api/app.py` 已修，此为其新名） | 把"错的候选名"从 Vercel 的入口名单里彻底拿掉。名字从此是**部署契约的一部分**，模块注释里写明了原因与实测指纹。 |
| 根目录 `app.py` | 把**同一个** app 对象绑定在根目录的候选名上（文档说根目录优先）。它与 `api/index.py` 两个候选指向同一个带路由的 app —— 于是**解析顺序无论怎么变，结果都一样**。 |
| `pyproject.toml`（**已删除，勿再加**） | 曾用它声明 `[tool.vercel] entrypoint`，会让平台改以本仓库为 Python 项目安装依赖 ⇒ flat layout 下 setuptools 报错 ⇒ **构建失败**。见上文"一次失败的尝试"。 |
