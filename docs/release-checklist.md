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

2026-09-20 实测的结论：线上静态资源 = HEAD（3 个新鲜度探针全 OK），
但 `/api/*` 的**每一个**路径 —— 包括「只要函数构建了就必然存在的 `/api/handlers/health`」——
返回的都是**同一份静态 404**，且不带应用无条件设置的 `Cache-Control: no-store`。
⇒ **那次部署没有构建出任何 Serverless Function，线上只有静态文件。**
`vercel.json` 里那批 `/api/xxx → /api?_route=xxx` 重写因此全部落空，
而静态资源照样最新、CI 照样全绿、首页照样 200 —— 所以只有"按接口逐个打"才看得见。

| # | 事项 | 谁 | 怎么做 / 判据 |
|---|---|---|---|
| 1 | 核对 Vercel 项目构建设置 | **【你】** | Project → Settings → Build and Deployment：**Root Directory 必须是仓库根**（留空或 `/`），**Output Directory = `public`**，**Framework Preset = Other**，Build/Install Command 留默认。改完 Redeploy。这是"函数没被构建"的第一嫌疑。 |
| 2 | 取回该次 Production 部署的 **Functions 列表** 与 **Build Logs** | **【你】** | Deployments → 点最新 Production → 看有没有 Function 条目（应有 `api/index.py`）。把截图或日志贴给我，我按它定案是"没构建"还是"入口挂错"。 |
| 3 | 补齐生产环境变量 | **【你】** | Settings → Environment Variables（Production）：`ZHIPU_API_KEY`、`DUMATE_MODEL`、`DUMATE_CONSENT_SECRET`、`DATABASE_URL`、`APP_ENV=production`、`DUMATE_ALLOWED_ORIGINS`。缺 `DUMATE_CONSENT_SECRET` 会让同意令牌直接失败。 |
| 4 | 复跑探针确认阻断解除 | **【我】** | 期望 `OK GET /api/health code=200`，其余接口"已由应用应答"。 |
| 5 | 端到端冒烟（F1→F5 真流程） | **【我】** | 仓库里已有 `scripts/run-wf-e2e.py`、`scripts/phase4-http-smoke.py`、`scripts/run-rehearsal.py`；接口通了以后对着生产域名跑一遍。 |

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
| 6 | P0-01 真实模型复测 | **【你】** 给凭据 / **【我】** 跑 | 需要真实模型 key；无 key 时该项只能停在"未验证"。 |
| 7 | P0-03 端到端真实数据闭环 | **【我】** | 走 `scripts/p0-03-real-model-test.py`，依赖第 6 项。 |
| 8 | G8 真实用户验证（≥5 名真实参与者） | **【你】** | 模板已就绪；这件事**没有人能替你**，且必须真人才算数。 |
| 9 | G9 提交包冻结 | **【我】** 起草 / **【你】** 定稿 | 走 `scripts/p0-07-freeze.py`：方案 PDF（≤20 页 / ≤50MB）、演示 MP4（≤4 分 30 秒 / ≤500MB）、200 字简介、分享 URL、skill 导出、freeze-checklist、commit 记录。 |
| 10 | 仓库可见性口径 | **【你】** 决策 | 提交清单里写的是"私有仓库"，而当前仓库是公开的。要么改口径，要么改设置 —— 需要你定。 |

---

## 三、业务决策（只有你能定，且定了才能对外说）

| # | 事项 | 谁 | 说明 |
|---|---|---|---|
| 11 | F5 五项业务决策 | **【你】** | 数据授权 / 预算 / 责任人等，逐项见 `docs/product-scope.md` 与 F5 计划文档。 |
| 12 | D3（单位 / 职位检索） | **【你】** | 期限 2026-10-13。**决策之前不得对外宣称有单位库或实时职位覆盖。** |

---

## 四、这一轮已经在仓库内落地的（可复跑，不是声明）

| 产物 | 它填的观察面空洞 |
|---|---|
| `scripts/api-prod-probe.py` | 只有它同时看「线上静态是否 = HEAD」与「接口是否真的被应用接住」。原有的 `scripts/vercel-dead-routes.py` 只看配置、`scripts/p0-05-link-check.py` 只判链接可达、`scripts/phase4-http-smoke.py` 打的是本地端口 —— 三者可以全绿而线上一个流程都走不通。探测源从 `public/js/pages-api-config.js` 的字面量推导，避免此处再抄一份会漂移的域名。 |
| `scripts/vercel-dead-routes.py`（新增方向 B） | 原来只判「重写 → 处理分支」。新增「本地路由 → 重写覆盖」：`api/index.py` 里新增一条 `/api/xxx` 却忘了在 `vercel.json` 加 `source` 时，本地全绿、线上静态 404。判据自带反向控制探针（抽掉一条重写必须变红），防止它"绿着失效"。 |
| `docs/release-checklist.md`（本文） | 把"还差什么"从散落的对话与报告里收成一份带责任人的台账，并登记进 `contracts/living-docs.json` 的观察面。 |
