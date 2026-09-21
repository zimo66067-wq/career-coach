# 上线剩余步骤清单

这份文档回答一个问题：**离"真实用户能走通一个完整流程"还差什么。**
它是这件事的唯一台账 —— 状态只在**实测过**之后才改；没实测就老实写「未验证」。

标注：**【你】** = 只有账号持有人能做的（控制台、凭据、真人、业务决策）；**【我】** = 仓库内可代做的。
完成一条就把它的状态改成 ✅（附实测证据），不要凭印象勾。

---

## 一、阻断项：现在的真实状态是"用户点进去走不通"

判据不是"首页能不能打开"，而是 **`/api/*` 有没有被应用接住**。
一条命令给出现状（它自己按前端字面量找探测源，不写死域名）：

```bash
.venv-audit/Scripts/python.exe scripts/api-prod-probe.py
```

2026-09-20 实测：线上静态资源 = HEAD（3 个新鲜度探针全 OK），
但 `/api/*` 的**每一个**路径都返回同一个 404，且不带应用无条件设置的 `Cache-Control: no-store`。

**2026-09-21 定案**（同一条里原先写的"没有构建出任何 Serverless Function"**是错的**，已改）：
线上返回的是 **Werkzeug 的默认 404**（207 B）；而同一个 app 在**本地**对同一路径返回
105 B、带 `Cache-Control: no-store`、且 `/api?_route=health` 是 **200**。
⇒ **线上被服务的是另一个 app 对象** —— 既不是"路由写错了"，也不是"没构建函数"。

根因：**Vercel 的 Flask 预设按文件名挑入口**，候选名第一顺位就是 `app.py`，
而本仓库有一个 `api/app.py` —— 那是 Phase 7c 为消除循环 import 把 app 对象下沉成的
**叶子模块**（只 `Flask(__name__)`，不注册任何路由）。预设只 import 了这个叶子模块，
于是**任何路径**都是默认 404。静态资源与输出根不受影响 ⇒ CI 全绿、首页 200、
只有接口全 404，仓库内所有判据都看不见。

修法**在仓库里**（不需要改预设）：`pyproject.toml` 的 `[tool.vercel] entrypoint = "api.index:app"`
显式声明入口，外加根目录 `app.py` 把同一个对象再绑定一次以覆盖"按文件名解析"那条路径。

| # | 事项 | 谁 | 怎么做 / 判据 |
|---|---|---|---|
| 1 | 核对 Vercel 项目构建设置 | **【你】** | Settings → Build and Deployment：**Root Directory 留空**（= 仓库根 ✅ 已确认）、**Framework Preset 保持 `Flask`**、**Output Directory 留 `N/A`**（Flask 预设自己管静态根 —— 线上 `/capability_matrix.md` 正是从 `public/` 取的，说明它对）。**⚠️ 不要改成 `Other`**：那会切回"`api/` 下每个 `.py` 各自是函数"的约定，而本目录有 25 个 `.py`，其中 23 个不导出任何 handler。 |
| 2 | 补齐生产环境变量 | **【你】** | Settings → Environment Variables（Production）：`ZHIPU_API_KEY`、`DUMATE_MODEL`、`DUMATE_CONSENT_SECRET`、`DATABASE_URL`、`APP_ENV=production`、`DUMATE_ALLOWED_ORIGINS`。缺 `DUMATE_CONSENT_SECRET` 会让同意令牌直接失败。 |
| 3 | **入口修复进主干后点 Redeploy** | **【你】** | 顺序不能反：Redeploy 重建的是 GitHub 上**当前那个提交**，修复没推上去就白点。 |
| 4 | 复跑探针确认阻断解除 | **【我】** | 期望 `OK GET /api/health code=200`，其余接口"已由应用应答"。**这套修法唯一的判据在线上 —— 仓库内全绿不能说明什么。** |
| 5 | （**仅当**第 4 项仍 404 才需要）取 **Functions 列表** 与 **Build Logs** | **【你】** | Deployments → 最新 Production：Functions 里有没有 `api/index.py`、日志里 resolved entrypoint 是哪个文件。有这两样我能直接定案；第 4 项 OK 就跳过。 |
| 6 | 端到端冒烟（F1→F5 真流程） | **【我】** | 仓库里已有 `scripts/run-wf-e2e.py`、`scripts/phase4-http-smoke.py`、`scripts/run-rehearsal.py`；接口通了以后对着生产域名跑一遍。 |

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
| `pyproject.toml` + 根目录 `app.py` | 显式声明 WSGI 入口（`[tool.vercel] entrypoint = "api.index:app"`），并在根目录把**同一个对象**再绑定一次，覆盖平台"按文件名解析入口"那条路径 —— 不让目录里一个同名叶子模块决定线上跑哪个 app。配套在 `vercel.json` 写死 `installCommand`（`pyproject.toml` 可能改变依赖来源）。**刻意不写 `buildCommand`**：它会覆盖框架自身的构建。 |
