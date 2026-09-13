# phase1-report.md · Phase 1（Product Deletion）完整报告

- 执行日期：2026-09-13
- 起点 commit：`44986ac1159a0db53c8740f437a87ef675855a20`（Phase 0 只读审计后）
- Phase 1 删除目标（7 项）**全部达成**：Organization Search、Job Search、C7 Predictions、
  KB Navigation、Major Match 一级入口、Voice remnants、retired routes
- 配套：`docs/product-scope.md`（§10 决策、§11 Phase 1 记录）、`docs/architecture.md`、
  `docs/dependency-map.md`、`CHANGELOG.md`、`tests/test_phase1_deletions.py`（24 项契约）

分成两个提交执行：`fc016c5`（D1，专业→职业匹配）与本次（C7 / KB / 语音 / 死路由）。

---

## 1. 修改摘要

把产品从「功能堆叠型职业平台」收敛为「证据驱动的 AI 求职教练」的第一步：**删除低价值能力，
而不是把它们藏起来**。Phase 1 结束时，主产品只剩一套匹配概念、一套面试链路、一套证据评分口径。

### 1.1 D1 · 专业→职业匹配整块删除（提交 `fc016c5`）

**关键判断**：`/api/f2/*` 与 `/api/wf03/*` 是**两套独立实现**（前者专业 Mode A/B + `LEVEL_SCORE`，
后者 JD 四态 + BM25）。核心闭环（e2e、`interview_service`、`data-bridge.matchJD`）走的是 `wf03`，
所以删除 `f2` 不伤核心 —— 这是删除前必须先验证的第一件事。

**连带结论**：`/api/tasks` 整个异步任务子系统在删除前硬编码
`if task_type != "f2_match": raise unsupported_task_type`，没有第二种任务类型，因此它不是通用框架，
而是该功能的配套，一并删除。

**删除清单**：`api/f2_major.py`(703) / `services/task_service.py`(153) / `tools/tasks.py`(138) /
`data/f2/*`(175 KB) / 2 个构建脚本 / 三树各一份 `pages/f2-match.html` + `css/f2-major.css` +
`js/f2-major.js` / 4 个测试文件；`/api/f2/*`、`/api/tasks*`、`/api/f2_major` 全部 404；
`tasks` 表从双方言 DDL 移除并在 `init_db()` 幂等 drop。

### 1.2 C7 预测区间彻底删除

| 层 | 改动 |
| --- | --- |
| 算法 | `tools/rescore.py` 不再计算 `C7_low`/`C7_high`（固定 0.30/0.70 演示假设），只输出 R/M/I/C0 |
| 服务 | `services/interview_service.build_ability_profile` 移除 `scenario_day7` |
| API | `wf05/ability` 响应移除 `C7_low`/`C7_high` |
| 合同 | `contracts/ability-profile.schema.json` 移除 `scenario_day7`（含 `required`）；`contracts/scoring.md` §4 重写为「C0 是当前证据快照」 |
| 前端 | `radar.js` 三条曲线 → 一条「当前证据快照」；`f4-report.html` 删除区间带与情景假设块；`index.html` / `mock-data.js` 同步 |
| 口径 | 所有出现处显式标注 **C0 不代表真实就业概率**，F4 不再输出任何预测区间 |

保留 `C0` 与六维分作为**当前证据快照**。Radar 从一级功能降为**可选可视化组件**。

### 1.3 独立知识库产品下线

删除导航项、`pages/kb.html`、`js/kb.js`（三树）、`/api/knowledge/search`、`/api/knowledge/questions`
与两条 `vercel.json` 重写。
**`tools/knowledge.py` 保留**，按裁决下沉为 Interview Engine 的内部 Question Bank 数据源
（模块级测试保留；接线留 Phase 3）。「Ask My Career Evidence」留 Phase 3/4。

### 1.4 整条语音链路删除（已死功能，占着代码/配置/脚本/文档/测试）

| 资产 | 处置 |
| --- | --- |
| `public/js/voice.js`（三树，318 行/份） | 删除（实测**无任何页面 `<script>` 引用**） |
| `tools/voice_handler.py`(398)、`tools/providers/asr.py`(113) | 删除（生产代码 0 引用，仅被 2 个测试 import） |
| `/api/wf04/asr`（路由 + 重写 + OPTIONS 项） | 删除 |
| `scripts/p0-04-voice-validation.py`、两份 `voice-test-checklist.md` | 删除 |
| `tests/test_new_tools.py`、`tests/test_voice_browser.py` | 删除 |
| `ASR_API_URL` / `TTS_API_URL` / `BAIDU_SPEECH_TOKEN` | 从 `.env.example` 删除 |

`/api/wf04/stream`（SSE 文字面试）与 `asr_confidence` 参数**保留** —— 后者是面试状态机的
「低置信度不推进」保护，与语音链路无关。

### 1.5 死路由修复（`/assets/*`）

`vercel.json` 把 `/assets/:path*` 重写到 `/ui/assets/:path*`，但 **`ui/` 根本不在部署内**
（`/css/*`、`/js/*`、`/pages/*` 都显式重写到 `public/`）。后果有两个，都在线上：

1. **全部页面的 favicon 404**
2. `radar.js` 的「本地 ECharts 兜底」永远不生效（三级降级实际只剩两级）

改为 `/public/assets/:path*`，并把 `assets/`（favicon.svg / logo.svg / vendor/echarts.min.js）
补进 `public/` 与 `docs/` 两棵发布树，同时加入 publish mirror 一致性测试，防止再漂移。

### 1.6 顺手修掉的两个缺陷

1. **自引入的重复路由**：删知识库路由时，一次 Edit 把 `if route == "wf04/asr":` 的**条件行**
   改写成了 `if route == "wf04/start":`，导致 ASR 的处理体挂在 `wf04/start` 下，与真实处理器
   形成重复路由（先匹配者赢）。发现方式：`grep -c 'route == "wf04/start"'` 得到 2。已连带删除
   该 ASR 处理体。
2. **`transfer_owner_data()` 仍更新被 drop 的 `tasks` 表**（D1 中修复）—— 不改这里，老库登录会
   因表不存在直接报错。

## 2. 删除内容汇总

**文件（两轮合计 32 个删除）**

| 类别 | 对象 |
| --- | --- |
| 后端模块 | `api/f2_major.py`、`services/task_service.py`、`tools/tasks.py`、`tools/voice_handler.py`、`tools/providers/asr.py` |
| 数据 | `data/f2/majors_2025.json`、`data/f2/profiles_top30.json` |
| 脚本 | `scripts/build_majors_data.py`、`scripts/validate_f2_data.py`、`scripts/p0-04-voice-validation.py` |
| 前端（三树） | `f2-match.html`、`f2-major.css`、`f2-major.js`、`kb.html`、`kb.js`、`voice.js` |
| 文档 | `public|docs/voice-test-checklist.md` |
| 测试 | `test_f2_routes.py`、`test_f2_search_ui.js`、`test_tasks.py`、`test_tasks_contract.js`、`test_new_tools.py`、`test_voice_browser.py`、`e2e_closed_loop_results.json`（陈旧产物） |

**接口下线**：`/api/f2/{health,majors/tree,majors/search,majors/<code>,match,intent}`、
`/api/f2_major`、`/api/tasks`、`/api/tasks/<id>`、`/api/tasks/<id>/next`、`/api/knowledge/search`、
`/api/knowledge/questions`、`/api/wf04/asr` —— 全部 404（GET 与 OPTIONS 双验证）。

**数据库**：`tasks` 表（DDL ×2 + 幂等 drop + 批量表操作列表）。

**配置**：`vercel.json` 重写 48 → 36 条；`.env.example` 删除 3 个语音变量。

**前端连带面**：导航项（F2、面经知识库）、首页 F2 功能卡与一键体验按钮、F4 行程节点（改为
不可点击的状态指示）、历史记录 F2 事件映射、`quick-demo.js` 的 F2 分支、`data-bridge.js` 的
`matchMajor` + 任务方法、`sync_sidebar.py` 页面清单。

## 3. 受影响文件

```
提交 fc016c5（D1）      74 files changed, 1158 insertions(+), 13688 deletions(-)
本次提交（Phase 1 其余） 73 files changed,   646 insertions(+),  4447 deletions(-)
```

- 新增：`tests/test_phase1_deletions.py`（24 项删除契约）、`public|docs/assets/*`（3 个文件 ×2 树）
- 关键修改：`api/index.py`、`tools/rescore.py`、`tools/radar_adapter.py`、`services/interview_service.py`、
  `services/__init__.py`、`tools/database.py`、`vercel.json`、`.env.example`、
  三树 `index.html` / `radar.js` / `mock-data.js` / `quick-demo.js` / `data-bridge.js` / `account.js` / 各页 HTML
- 测试：9 个文件改 + 6 个文件删 + 1 个新增
- 文档：`CHANGELOG.md`、`README.md`、三树 `README.md`、`docs/{architecture,dependency-map,product-scope,phase1-report}.md`、两份 F2 历史规划文档加作废横幅

## 4. 测试结果

```
Python   pytest -q                                    331 passed in 108.06s
Node     node --test tests/*.js                       36 passed / 0 failed
Schema   ability-01 vs ability-profile.schema.json    OK
Secret   tracked+untracked 扫描（226 文件）            无发现
Whitespace git diff --check                            通过
Mirror   public vs docs（43 个共有文件）               仅 2 个 markdown 文档不同（Phase 6/7）
Dead     vercel 静态重写目标 + _route 处理器            0 个死路由
```

**测试数变化是预期的，不是回归**：

| 阶段 | pytest | Node |
| --- | --- | --- |
| Phase 0 基线 | 436 | 52 |
| D1 之后 | 423 | 38 |
| Phase 1 完成 | **331** | **36** |

减少来自删除整套测试文件（`test_f2_routes` 335 行、`test_tasks` 167 行、`test_voice_browser` 300 行等），
同时把删除本身固化成 24 项契约（`tests/test_phase1_deletions.py`，从 11 项扩到 24 项）：
下线端点 GET/OPTIONS 双 404、能力表无 `f2_major`、被删文件确实不存在、无残留 import、
`vercel.json` 无 f2/tasks/knowledge/asr 重写、`tasks` 表不再创建且不在 `transfer_owner_data`、
C7 在 rescore/schema/scoring 三处都不再定义为公式、radar option 只有一条曲线、
`/assets/:path*` 指向 public 树、**正向对照 `/api/wf03/match` 仍可用**、镜像仍逐字节一致、
导航恰好 5 项且不含已下线能力。

## 5. 性能结果

本次为纯删除，未引入新的计算路径，理论上只减不增。本地进程内 test client 实测（n=25，规则型，无外部模型）：

| 接口 | median | p95 | max |
| --- | --- | --- | --- |
| `POST /api/wf03/jd` | 39.4 ms | 45.5 ms | 52.5 ms |
| `POST /api/wf03/match` | 49.6 ms | 60.7 ms | 1101.2 ms |
| `GET /api/health` | 0.7 ms | 1.1 ms | 1.6 ms |

门禁「规则型 P95 < 800ms」**通过**。`wf03/match` 的 1101 ms max 是首次调用触发 jieba 前缀词典
构建的一次性预热（日志 `Loading model cost 1.040 seconds`），预热后 p95 = 60.7 ms，非稳态成本。
未做真实网络与外部模型路径基准（不属本次范围）。

## 6. 剩余风险

| # | 风险 | 影响 | 处置 |
| --- | --- | --- | --- |
| 1 | **目标岗位分析没有界面** | `js/job-upload.js` 实测无任何页面加载它；旧专业匹配页已删，主产品没有可用的匹配入口 | Phase 3 在目标岗位工作区重新挂载。**在此之前不得宣传「可以匹配 JD」** |
| 2 | **测试总数下降 105（pytest）/16（Node）** | 覆盖率口径需要重测，不能沿用 Phase 0 的 79%/0% | Phase 15 在 CI 的 Python 3.11 上重测 |
| 3 | **F4 行程节点与历史记录仍显示内部代号「F2」** | 节点已改为不可点击（不 404）；`matchJD` 仍把结果记为历史事件类型 `F2`，页面映射已移除，这类历史项变为不可点击 | Phase 6 统一改名 |
| 4 | **`public/*.md` 对外可读 + 两套文档树漂移** | `capability_matrix.md` / `index.md` 在 public 与 docs 内容不同；20+ 内部文档公网可读 | Phase 6/7（`public/*.md` 暴露 + 镜像收敛为单一 canonical） |
| 5 | **`ui/prototype` 是陈旧分叉，自身有 7 处坏引用** | 该树未部署；坏引用**在 Phase 1 之前就存在**，非本次引入 | Phase 6/7 删除死树 |
| 6 | **`pip_audit -r` 在本机失败** | `no such option: --keyring-provider`（pip-audit 2.10.1 给临时 venv 装的 pip 过旧） | 环境问题；本机改用当前环境审计，唯一发现 `setuptools` 且不在任何 requirements 中。依赖清单本次未改动 |
| 7 | **D3 未决** | 单位/职位索引恒空，F5 阶段 2 无法推进 | 需产品负责人给出 5 项决策 |
| 8 | **D5 / D6 未决** | `workflows/`(1519 行) 与 `deliverables/`(53 文件) 的仓库体积口径未定 | 影响 Phase 7 收尾 |

## 7. DoD 推进

**本次达成 5 项、累计达成 8 项**：

| DoD | 状态 |
| --- | --- |
| #3 单位/职位检索不暴露 | ✅ 首页/导航/用户入口均无入口（导航实测 5 项无此项） |
| #4 C7 预测删除 | ✅ 彻底删除，`C0` 保留且标注不代表就业概率 |
| #5 KB 非独立产品 | ✅ 导航/页面/API 删除，题库下沉为内部数据源 |
| #6 Major Match 不共用 F2 概念 | ✅ 只剩一套 Target Job Analysis |
| #22 删除链路自动化测试 | ✅ 24 项契约 |
| #24 无 dead routes | ✅ 0 个 |
| #13 Service 不反向依赖 API | ⬆️ 3 处 → **2 处** |
| #1 / #2 导航收敛 | ⬆️ 7 → **5** 项；用户可见代号 5 → **4**（改名留 Phase 6） |

## 8. 下一阶段入口条件

**Phase 2（Domain Consolidation）已解除阻塞**：D4 已决策 —— **允许迁移 `applications` 现有生产数据到
新的 7 态模型**（`considering / preparing / applied / interview / offer / rejected / withdrawn`），
migration 可以落笔。

Phase 2 要建立：`CareerProfile` / `CareerEvidence` / `TargetJob` / `EvidenceMatch` / `Gap` /
`Action` / `ApplicationOutcome`，并编写 migration。

`CareerEvidence` 必备字段：`id / type / claim / source_type / source_id / source_quote / confidence /
user_confirmed / created_at / updated_at`；来源白名单 `resume | interview | user_input |
application_outcome`；**AI 新发现必须 `pending → 用户确认 → confirmed`，禁止直接写入 confirmed**。

仍需 D5（`workflows/` 去留）与 D6（`deliverables/` 归档）以确定仓库体积口径；D3 阻塞 F5 阶段 2
（不阻塞 Phase 2）。
