# phase1-report.md · Phase 1（Product Deletion）执行报告

- 执行日期：2026-09-13
- 起点 commit：`44986ac1159a0db53c8740f437a87ef675855a20`（`main`，Phase 0 只读审计后）
- 范围：本次只执行 **D1（专业→职业匹配整块删除）**，未触碰 C7 预测、KB 导航、语音链路
- 配套：`docs/product-scope.md`（§10 决策记录）、`docs/architecture.md`、`docs/dependency-map.md`、`CHANGELOG.md`

---

## 1. 修改摘要

删除「专业→职业匹配」这一整块产品能力，使主产品只剩**一套**匹配概念（Target Job Analysis）。

关键判断与证据：

| 判断 | 证据 |
| --- | --- |
| `/api/f2/*` 与 `/api/wf03/*` 是两套独立实现 | `api/f2_major.py`（专业 Mode A/B + `LEVEL_SCORE`）与 `services/match_service.py`（JD 四态 + BM25），各有自己的 `MATCH_WEIGHTS` |
| 核心闭环走的是 `wf03`，不是 `f2` | `data-bridge.js` 的 `matchJD → /api/wf03/match`；`interview_service.py` 从 `match_service` 取 `MATCH_WEIGHTS`；e2e 主链路用 `wf03` |
| 异步任务子系统只为该功能存在 | `api/index.py` 的 `/api/tasks` 在删除前硬编码 `if task_type != "f2_match": raise unsupported_task_type`，无第二种类型 |
| 语音链路与此无关 | 本次未动，仍待 Phase 1 后续处理 |

## 2. 删除内容

**代码与数据（20 个文件 + 1 个目录）**

| 类别 | 对象 |
| --- | --- |
| 后端 | `api/f2_major.py`(703) / `services/task_service.py`(153) / `tools/tasks.py`(138) |
| 数据 | `data/f2/majors_2025.json`(116 KB) / `data/f2/profiles_top30.json`(59 KB) |
| 脚本 | `scripts/build_majors_data.py`(88) / `scripts/validate_f2_data.py`(122) |
| 前端（三套副本） | `pages/f2-match.html` / `css/f2-major.css` / `js/f2-major.js` × (public, docs, ui/prototype) |
| 测试 | `tests/test_f2_routes.py`(335) / `tests/test_f2_search_ui.js`(310) / `tests/test_tasks.py`(167) / `tests/test_tasks_contract.js`(119) |

**接口下线**：`/api/f2/health`、`/api/f2/majors/{tree,search,<code>}`、`/api/f2/match`、`/api/f2/intent`、`/api/f2_major`、`/api/tasks`、`/api/tasks/<id>`、`/api/tasks/<id>/next` —— 全部 404（GET 与 OPTIONS 均验证）。

**导航与入口**：首页导航项、F2 一键体验按钮、F2 功能卡；各页侧边栏 F2 链接；`scripts/sync_sidebar.py` 页面清单；`data-bridge.js` 的 `matchMajor`、`createTask/getTask/advanceTask/pollTask`、`ENDPOINTS.tasks`、`ENDPOINTS.majorMatch`；`quick-demo.js` 的 F2 分支与 `DEMO_JD`；`account.js` 中 F2 历史事件的目标页。

**数据库**：`tasks` 表从 SQLite 与 PostgreSQL 两份 DDL 移除，并在 `init_db()` 中对其执行幂等 `DROP TABLE IF EXISTS`；`transfer_owner_data()`（登录时迁移归属）不再尝试更新该表 —— **若不改这一处，老库登录会因表不存在而失败**。

**刻意保留**：`js/job-upload.js`（`/api/wf03` JD 解析→确认→匹配 UI）与 `data-bridge.js` 的 `submitJD`/`matchJD`。它们属于要保留的 Target Job Analysis，不是被删对象。

## 3. 受影响文件

```
74 files changed, 1158 insertions(+), 13688 deletions(-)
```

- 删除：20 个文件（上表）
- 新增：`tests/test_phase1_deletions.py`（11 项删除契约）
- 修改（后端）：`api/index.py`、`tools/database.py`、`services/__init__.py`、`vercel.json`（−36 行重写）
- 修改（前端，三树各 6–7 个）：`index.html`、`js/{quick-demo,data-bridge,account}.js`、`pages/{f1,f3,f4,f5,kb,states}.html`
- 修改（测试）：`test_{api_boundary,e2e_full_chain,phase5,phase5_contract,public_page_states,publish_mirror,quick_demo,security_hardening,upload_progress}`
- 文档：`CHANGELOG.md`、`docs/{architecture,dependency-map,product-scope}.md`、三树 `README.md`、两份 F2 历史规划文档加作废横幅

## 4. 测试结果

```
Python   pytest -q                                   423 passed in 93.53s
Node     node --test tests/*.js                       38 passed / 0 failed
Schema   validate_schema (resume + job fixtures)      pass
Secret   tracked+untracked 扫描（231 文件）            无发现
Deps     requirements.txt / tools/requirements.txt    未改动，无新增发现
Whitespace git diff --check                            通过
Mirror   public == docs（10 个改动页/脚本）             逐字节一致
Assets   public/ + docs/ 页面本地 js/css 引用           全部可解析
```

测试数从 436 + 52 变为 423 + 38：删除 4 个测试文件（931 行），新增 11 项删除契约。

`tests/test_phase1_deletions.py` 固化的不变量：

1. 全部下线端点在 GET 与 OPTIONS 下均 404
2. 能力表 `/api/health.workflows` 不再含 `f2_major`
3. 20 个被删文件确实不存在
4. `api/index.py` 不含 `f2_major` / `task_service` / `tools.tasks`
5. `vercel.json` 无 f2 或 tasks 重写
6. `tasks` 表不再出现在 DDL 与 `transfer_owner_data`
7. `init_db()` 后数据库里确实没有 `tasks` 表
8. **正向对照**：`/api/wf03/match` 仍正常返回 `score_M` 与四态要求
9. publish 两树对改动文件仍逐字节一致
10. publish 树不再出现 `f2-match.html` / `f2-major.js` / `matchMajor` / `quickDemoF2`

## 5. 性能结果

本地进程内 test client，n=25（规则型，无外部模型）：

| 接口 | median | p95 | max |
| --- | --- | --- | --- |
| `POST /api/wf03/jd`（JD 解析） | 39.4 ms | 45.5 ms | 52.5 ms |
| `POST /api/wf03/match`（Target Job 匹配） | 49.6 ms | 60.7 ms | 1101.2 ms |
| `GET /api/health` | 0.7 ms | 1.1 ms | 1.6 ms |

门禁「规则型 P95 < 800ms」**通过**。`wf03/match` 那个 1101ms 的 max 是首次调用触发 jieba 前缀词典构建的一次性预热（日志可见 `Loading model cost 1.040 seconds`），预热后 p95 为 60.7ms，非稳态成本。

本次是纯删除，未引入新的计算路径，理论上只减不增；未做真实网络与外部模型路径的基准（那不属本次范围）。

## 6. 剩余风险

| # | 风险 | 影响 | 处置 |
| --- | --- | --- | --- |
| 1 | **目标岗位分析当前没有界面** | `job-upload.js` 实测无任何页面加载它，F2 页删除后主产品没有可用的匹配入口；用户只能走 F1 诊断 | Phase 3（核心闭环）在目标岗位工作区重新挂载；**在此之前不得宣传"可以匹配 JD"** |
| 2 | **F4 行程节点与历史记录仍显示内部代号「F2」** | 行程节点已改为不可点击的状态指示（不 404）；`matchJD` 仍把匹配结果记成历史事件类型 `F2`，但 `account.js` 的页面映射已移除该类型，所以这类历史项**变为不可点击**（不会 404，但少了跳转） | Phase 6 统一 IA 改名：节点与事件类型一起改成「目标岗位匹配」 |
| 3 | **历史文档仍提到 F2 页面** | `public/{mobile-accessibility-testing,redesign-v2-visual}.md`、`docs/{iteration-3-plan,test-report}.md`、`docs/design/*` | 已作废的两份 F2 规划文档已加横幅；其余属带日期的历史记录，Phase 7 统一处理，同时解决 `public/*.md` 对外暴露问题 |
| 4 | **`ui/prototype` 是陈旧分叉且自身有 7 处坏引用** | 该树未部署，`pages-api-config.js`/`resume-upload.js` 本就不存在（**D1 之前就坏**，非本次引入） | Phase 7 删除死树 |
| 5 | **`pip_audit -r` 在本机失败** | 报 `no such option: --keyring-provider`：pip-audit 2.10.1 给临时 venv 装依赖时，用的 pip 过旧 | 非代码问题；依赖清单本次未改动，CI 上仍以 `-r` 为准；本机改用当前环境审计，唯一发现是 `setuptools 65.5.0`，而它**不在**任何 requirements 中（仅是构建工具） |
| 6 | **本地 venv 是 Python 3.10.11，CI 是 3.11** | 覆盖率门禁数字不可跨版本直接比较 | Phase 15 在 CI 版本上重测 |
| 7 | **D3 未决** | 单位/职位索引仍恒为空，F5 阶段 2 无法推进 | 需产品负责人给出 5 项决策（地域范围 / 数据授权 / 职位来源权利 / 预算 / 纠错责任人） |

## 7. DoD 推进

本次达成 3 项、推进 2 项：

- ✅ **#6** Major Match 不再与 JD Match 共用 F2 概念 —— 只剩一套 Target Job Analysis
- ✅ **#22** 删除链路通过自动化测试 —— `tests/test_phase1_deletions.py` 11 项
- ✅ **#24** 无 dead routes —— f2/tasks 路由全部下线
- ⬆️ **#13** Service 不反向依赖 API：3 处 → **2 处**（`task_service → api.f2_major` 随删除消失）
- ⬆️ **#1/#2** 一级导航 7 → **6**；用户可见代号 5 → **4**（完整改名在 Phase 6）

## 8. 下一阶段入口条件

Phase 1 的其余项（C7 预测、KB 一级导航、语音链路、`ui/prototype`、孤儿 env、未用 prompt）**本次未动**，可在无阻塞情况下继续。Phase 2（领域整合）需要先明确 **D4**（`applications` 生产数据是否允许迁移到新 7 态模型），否则 migration 无法落笔。

按工作纪律，请确认本报告后再进入下一阶段。
