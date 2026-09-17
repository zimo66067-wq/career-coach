# dependency-map.md · career-coach 模块依赖地图

- 生成日期：2026-09-13
- 范围：Phase 0 只读审计产物，**未修改任何业务代码**
- 基线 commit：`44986ac1159a0db53c8740f437a87ef675855a20`（`main`）
- 配套文档：`docs/architecture.md`、`docs/product-scope.md`

依赖关系均为静态扫描实测（`grep`/AST 级 import 统计），不是凭印象描述。

> **Phase 1 更新（2026-09-13）**：本文件列出的全部 Phase 1 删除项已执行完毕，以下条目
> **只描述删除前的状态**：
>
> - §1 的 `api/f2_major.py`(703)、§3.1 的 `services.task_service ──► api.f2_major` **违规已消失**
>   （dependency inversion 3 → 2）、§3.2 的 `tools.tasks`、§3.3 页面专属脚本里的 `f2-major`、
>   §4.1「既是路由又是业务又是服务器」、§4.2 的**两套匹配逻辑并存**（已只剩一套）、
>   §5 的 `/api/f2_major` 退休垫片
> - §3.2 / §4.3 的 `tools.voice_handler ──► tools.providers.asr` 整条链已删除
> - §4.3 / §7 所列的 `public/js/voice.js`、`tools/voice_handler.py`、`tools/providers/asr.py`、
>   `/api/wf04/asr`、3 个 ASR/TTS env 全部删除
> - §1 的 `kb.html` / `kb.js` / `/api/knowledge/*` 已删除（`tools/knowledge.py` 保留为内部题库）
> - C7 预测链（`rescore` → `scoring.md` §4 → schema `scenario_day7` → `radar.js` / `f4-report.html`）
>   已整体删除
>
> **现状**：主产品只剩 `wf03` / `services/match_service.py` 一套 Target Job Analysis；
> `vercel.json` 静态重写目标全部存在、`_route` 全部有处理器（**dead routes = 0**）；
> 一级导航 7 → 5。新增回归门禁 `tests/test_phase1_deletions.py`（11 项）。
> 仍有效的结论：§6 的 `ui/prototype` 陈旧分叉、§7 的 `tasks/` 目录与 4 个一次性推送脚本。
>
> **Phase 2 更新（2026-09-14）**：领域层与数据层建成，本文档以下结论随之改变 ——
>
> - **§3 依赖倒置从 2 处减少的路径没有走通，但新增代码不再制造新倒置**：
>   `services/diagnosis_service.py:324` 与 `services/interview_service.py:50` 仍
>   `from api.index import build_model_router`。新的 `domain/` 与 `repositories/`
>   两包经静态扫描确认**不 import flask / api / services**，分层方向在新增代码上成立；
>   既有两处的修复属于 Phase 5（`build_model_router` 应从 `tools/providers/model.py`
>   经 provider registry 注入）。
> - **§7 "无 migration 机制"已解决**：新增 `repositories/migrations.py`，版本化、幂等、
>   `/api/health` 可观测。
> - **表数量 20 → 30**，双方言 DDL 同步。
> - **§4.1 "api/index.py 既是路由又是业务"仍然有效**：拆 `api/index.py` 属于 Phase 5。
>
> 新增参考：`docs/domain-model.md`。

> **Phase 5 更新（2026-09-17）**：§3.1 / §3.2 的倒置**已修**，验证方式从"手工 grep 一次"
> 升级为**门禁**：
>
> - **§3.1 两处 Service → API 倒置已消失**：`diagnosis_service` / `interview_service`
>   改为依赖 `tools.providers.model`（叶子模块，模块级 import 不再有循环导入问题）。
>   同时发现并修掉了它们的**第二层依赖**：`tools.trace.trace_id()` 要 Flask 请求上下文，
>   服务用它兜底 → 服务单测必须 `with app.test_request_context()`。现在 trace 由 web 层
>   解析后**注入**服务，`tools/trace.py` 的 flask 改为函数内延迟导入。
> - **§3.2 收敛完成**：`build_model_router` 全仓库**只有一处定义**（`tools/providers/model.py`），
>   其余模块一律 `from tools.providers import model as model_provider` 后属性查找。
>   打桩点因此唯一，打错会 AttributeError（此前打错是**静默失效**）。
> - **新增门禁** `tests/test_layering.py`（8 项，进 pytest）：跨层 import（含函数体内）、
>   传递 Flask 依赖（只算模块级）、工厂单一归属地、**判据自检**（喂假源码证明它会红）。
> - **仍未做**：本文件「Phase 5 验收」第 4 条——`tools/` 归并进 `domain/` + `providers/`；
>   以及 §4.1 的 `api/index.py` 拆文件。两者都是跨阶段重构，已记入 `phase5-report.md §7`。
>
> 细节见 `docs/phase5-report.md`。

---

## 1. 实际目录与规模

| 层 | 路径 | 文件 | 行数 | 说明 |
| --- | --- | --- | --- | --- |
| API 入口 | `api/index.py` | 1 | 1282 | 唯一入口，含 40 条路由 + 中间件 + 业务编排 |
| API 模块 | `api/f2_major.py` | 1 | 703 | **既是 Flask 应用又是业务模块**（见 §4.2） |
| Service | `services/*.py` | 7 | 1593 | apply / diagnosis / interview / match / organization / task |
| Domain-ish | `tools/*.py` | 23 | 6805 | 引擎、评分、脱敏、提取、知识库等，**无 domain/ 层** |
| Provider | `tools/providers/*.py` | 3 | 199 | model / asr / organization |
| 数据 | `tools/database.py` | 1 | 1579 | 20 张表的建表 + 全部 CRUD |
| 契约 | `contracts/*.json` | 4 | 267 | 4 个 JSON Schema（2 个被运行时代码加载） |
| 提示词 | `prompts/**/*.md` | 9 | 280 | 9 个声明，**4 个被实际调用** |
| 前端 canonical | `public/**` | 47 | — | Vercel 静态根（实测生效） |
| 前端镜像 | `docs/**` | 66 | — | 混合：Web 镜像 + 19 个项目文档 |
| 前端旧原型 | `ui/prototype/**` | 27 | — | **未部署**（见 §4.4） |
| 测试 | `tests/**` | 139 | — | 37 个 pytest 文件 + 12 个 node 契约文件 |

后端 Python 合计 **10383 行**（`api` + `services` + `tools`）。

---

## 2. 实测依赖边

### 2.1 合法方向：`api → services → tools → (providers | database)`

```
api/index.py
├── services.diagnosis_service   ──► tools.{api_errors, contracts, deidentify, redflag, rescore, trace, validate_schema}
│                                    └── ✗ tools? no … ✗ api.index            (§3.1 违规)
├── services.match_service       ──► tools.{api_errors, contracts, deidentify, redflag, match_requirements}
├── services.interview_service   ──► tools.{api_errors, contracts, database, interview_engine, rescore}
│                                    └── services.match_service (同层)
│                                    └── ✗ api.index                          (§3.1 违规)
├── services.apply_service       ──► tools.{api_errors, database, providers.model}   ✅ 方向正确
├── services.organization_service──► tools.{api_errors, database, providers.organization}
├── services.task_service        ──► tools.{api_errors, contracts}
│                                    └── ✗ api.f2_major                        (§3.1 违规)
└── tools.*（大量直接使用）
```

### 2.2 `tools/` 内部

```
tools.interview_engine ──► tools.deidentify, tools.rescore        (函数内延迟 import)
tools.model_router     ──► prompts/*.md (文件读取), ZHIPU_*, QIANFAN_*
tools.match_requirements──► tools.model_router (Embedding)
tools.tasks            ──► tools.database
tools.voice_handler    ──► tools.providers.asr        ← 无生产消费者，见 §4.3
tools.radar_adapter    ──► （被 services.interview_service 引用）
```

`tools/` **不反向依赖 `services/`**，这一点是干净的。

### 2.3 前端

```
public/pages/*.html
   ├── ../js/app.js (全局壳/导航)
   ├── ../js/data-bridge.js  ← 唯一 API 客户端，ENDPOINTS 映射 15 个端点
   ├── ../js/account.js      ← /api/auth/*, /api/history/*
   ├── ../js/pages-api-config.js（1 个常量，16 行）
   └── 页面专属: resume-upload / optimizer / f2-major / f3-interview / radar / f5-apply / kb
```

`public/js/voice.js` **没有任何页面 `<script>` 引用**，见 §4.3。

---

## 3. 依赖违规清单

### 3.1 Service → API 倒置（3 处，必须修）

| 位置 | 代码 | 问题 |
| --- | --- | --- |
| `services/diagnosis_service.py:324` | `from api.index import build_model_router` | Service 反向依赖 API 入口 |
| `services/interview_service.py:50` | `from api.index import build_model_router` | 同上 |
| `services/task_service.py:14,108` | `from api import f2_major` | Service 依赖另一个 API 模块 |

注释写着 "runtime lookup keeps monkeypatch compat"——即为了测试打桩而牺牲了分层。正确做法是把 `build_model_router` 收敛到 `tools/providers/model.py`（该文件**已经存在**同名函数），Service 只依赖它。

### 3.2 同一能力有两套 router 构造函数

| 位置 | 方向 |
| --- | --- |
| `tools/providers/model.py::build_model_router` | ✅ 正确层 |
| `api/index.py::build_model_router` | ❌ API 层重复实现 |

`services/apply_service.py` 用的是正确那个，`diagnosis_service` / `interview_service` 用的是倒置那个 → **同一仓库两种取 router 的方式**。

### 3.3 API 模块兼任服务器（结构缺陷）

`api/f2_major.py` 同时包含：
- Flask `app = Flask(__name__)` + `serve_index` / `serve_static` + `app.add_url_rule`（模块级副作用）
- 业务逻辑：`search_majors`、`mode_a_result`、`mode_b_result`、`classify_requirement`、`judge_requirement`

它是**唯一一个既是路由又是业务又是服务器**的文件，且被 `services/task_service.py` 以业务身份 import。

### 3.4 重复实现：两套「JD 要求提取 + 匹配权重」

| | `services/match_service.py` + `tools/match_requirements.py` | `api/f2_major.py` |
| --- | --- | --- |
| 要求分类 | `job_requirement_type()` / `strip_requirement_prefix()` | `classify_requirement()` + `extract_requirements()` |
| 权重常量 | 自己的 `MATCH_WEIGHTS`（20 行） | 自己的 `MATCH_WEIGHTS`（27 行，`hard .50 / responsibility .25 / bonus .15 / term .10`） |
| 分词 | `tools/match_requirements.py` 内 | `tokenize()` 自实现 |
| 概念 | JD 四态（covered/weak/missing/unknown） | 专业画像 Mode A/B + `LEVEL_SCORE` |

两套逻辑都在生产被调用（`/api/wf03/match` 与 `/api/f2/match`），**这就是产品层 F2 概念冲突的代码根因**。

### 3.5 循环引用风险

当前无硬循环（`tools` 不回指 `services`），但 `api/index.py ↔ services/*` 已是双向：`api → services` 是正常调用，`services → api` 是倒置。一旦有人在 `api/index.py` 顶层 import 那些 service 函数就会形成真循环——现状靠「函数内延迟 import」侥幸避开。

---

## 4. 无效 / 退休 / 重复资产

### 4.1 死路由

| 路由 | 证据 | 结论 |
| --- | --- | --- |
| `/api/wf04/asr` | `public/`、`ui/` 全树 **0 处引用**；前端 `voice.js` 用的是浏览器 Web Speech API，不走后端 | 死路由 |
| `/api/f2_major` | 重写到 `retired/f2-major`，恒 404 | 退休垫片，可删 |

### 4.2 未被调用的提示词（5/9）

声明于 `tools/model_router.py:33-41`，但全仓无调用点：

- `resume_report` → `prompts/resume/report-deep.md`
- `jd_extract` → `prompts/match/jd-extract.md`
- `jd_match_explain` → `prompts/match/explain.md`
- `interview_review` → `prompts/interview/review.md`
- `seven_day_plan` → `prompts/plan/seven-day.md`

实际调用：`resume_diagnosis`、`resume_rewrite`、`interview_question`、`cover_letter`。

### 4.3 旧语音能力残留（整条链路已断，代码仍在）

| 资产 | 状态 |
| --- | --- |
| `public/js/voice.js`（318 行） | **无页面引用** → 死前端代码 |
| `tools/voice_handler.py`（398 行） | **生产 0 引用**，仅被 2 个测试 import |
| `tools/providers/asr.py`（113 行） | 仅服务死路由 `/api/wf04/asr` |
| `/api/wf04/asr` | 死路由 |
| `ASR_API_URL` / `TTS_API_URL` / `BAIDU_SPEECH_TOKEN` | voice_handler / asr.py 专用 |
| `scripts/p0-04-voice-validation.py`（216 行） | 语音验证脚本 |
| `public/voice-test-checklist.md`（251 行） | 且**对公网可见**（见 §4.5） |
| `tests/test_voice_browser.py`、`test_new_tools.py` 语音部分 | 为死代码保活的测试 |

即：产品早已不走语音，但语音的代码、配置、脚本、文档、测试全部留着。

### 4.4 三份前端副本，只有一份 canonical

| 树 | 文件 | 状态 |
| --- | --- | --- |
| `public/` | 47 | **canonical**，Vercel 实测静态根 |
| `docs/` | 66 | GitHub Pages 镜像（45 个与 public 逐字节相同）+ 19 个只存在于 docs 的项目文档；**2 个漂移**：`capability_matrix.md`、`index.md` |
| `ui/prototype/` | 27 | **未部署**。`/ui/prototype/index.html` 实测 404 |

`ui/prototype/` 是 `public/` 的陈旧分叉，逐文件行数已不同（如 `data-bridge.js` 829 vs 889、`main.css` 447 vs 621、`f2-major.js` 611 vs 719）。

### 4.5 生产静态暴露面（实测）

Vercel 静态根是 `public/`，**其中所有文件都对公网可读**。实测 200 的内部文档包括：

```
/capability_matrix.md            /observability.md
/dumate-workflow-sop.md          /defense-evidence-index.md
/README.md                       /blind-test-results/blind-test-report.md
/voice-test-checklist.md         /remaining-items.md（列已知缺口）
```

同时 `/assets/favicon.svg`、`/assets/logo.svg`、`/assets/vendor/echarts.min.js` **实测 404**：`vercel.json` 把 `/assets/:path*` 重写到 `/ui/assets/:path*`，但 `ui/` 不在部署静态根内 → **所有页面的 favicon 在线上是坏的，雷达图的本地 ECharts 兜底也永远 404**（只剩 CDN 路径可用）。

### 4.6 一次性运维脚本（约 1079 行）

`scripts/push-via-api.py`(366) / `push-via-api-v2.py`(276) / `push-head-via-api.py`(202) / `push-head-api.sh`(239) —— 手工走 GitHub REST 推提交的历史工具，现已被「Git Credential Manager + `git push`」取代。

### 4.7 其他孤儿

- `workflows/`（7 文件 ~1519 行）：**全仓代码 0 引用**，是 DuMate 的工作流文档。
- `tasks/`：仅一个 README.md。
- `scripts/_wf04_inline.py`：下划线前缀，无调用方。
- `.env.example` 中 `LOG_LEVEL`、`ENV`：**无任何消费者**。

---

## 5. 目标依赖结构（Phase 5 落地）

```
api/
├── app.py                  # 只做 Flask app 装配、CORS/consent/rate-limit 中间件
├── routes/
│   ├── resume.py           # wf01 upload / wf02 diagnose / rewrite
│   ├── target_jobs.py      # wf03 jd / match → Target Job Analysis
│   ├── interviews.py       # wf04 start/answer/end/stream
│   ├── applications.py     # wf07 cover-letter / applications
│   ├── profile.py          # evidence profile + ability/action plan
│   └── auth.py             # auth / history
services/                   # 编排 + 事务边界，不再被 api 反向依赖
domain/                     # CareerEvidence / TargetJob / Gap / Decision / Action 规则
repositories/               # database.py 拆出的表级读写
providers/                  # model / asr(待删) / organization(封存) 统一注册
```

硬性约束（Phase 5 验收）：

1. `services/`、`domain/`、`repositories/`、`providers/` **不得** import `api.*`。
2. `build_model_router` 只保留 `providers/model.py` 一处。
3. `api/` 下任何模块不得有 `app = Flask(...)` / `app.add_url_rule` 之外的模块级副作用。
4. `tools/` 逐步并入 `domain/` + `providers/`，或降级为 `domain` 的内部工具；保留期不超过两个 Phase。
