# HANDOFF.md · 交接入口（薄指针）

> **本文件不保存状态，只保存"去哪里找状态"。**
>
> Phase 7a（2026-09-17）把它从一份"当前阶段事实声明"退役成指针。原因不是它写错了，而是
> **它是一份没有责任人的第二真相源**：它维护着当前阶段、当前 commit hash、里程碑表、
> 未完成项清单、回滚点表和测试数字。这些副本最后一次同步是 2026-08-01（`672102b`），
> 而仓库此后又走了 Phase 1 ~ 6b-3 十几个阶段 —— 于是「当前 commit」是旧的、
> 「下一步唯一任务」是早已完成的、测试数字是 304 而现实是 482。
>
> 所以现在：**任何随时间变化的事实都不写在这里。**

---

## 各问题的唯一去处

| 想知道 | 去看 |
| --- | --- |
| 产品做什么、不做什么；每个决策点的裁决与理由 | `docs/product-scope.md` |
| 当前架构：技术栈、页面清单、API 路由、分层 | `docs/architecture.md` |
| 模块依赖边、依赖违规、死资产清单、目标依赖结构 | `docs/dependency-map.md` |
| 领域模型与不变量 | `docs/domain-model.md` |
| 按时间累积的变更史 | `CHANGELOG.md` |
| 每个阶段做了什么、怎么验证的、留下什么 | `docs/phase1-report.md` ~ `docs/phase6b3-report.md` |
| 收敛式重构的整体安排 | `docs/remediation-and-completion-plan-2026-09-08.md` |
| 隐私与数据最小化的设计基线 | `SECURITY.md`、`docs/design/privacy.md` |
| 能力矩阵与实测记录 | `docs/capability_matrix.md` |
| 验收清单 / 彩排清单 | `tests/acceptance/acceptance-checklist.md`、`tests/rehearsal/demo-checklist.md` |
| 交付存档（阶段产物与证据材料） | `handoffs/`、`deliverables/` |
| DuMate 侧的工作流定义 | `workflows/` |
| 仓库总览与上手 | `README.md`、`docs/README.md` |

## 代码在哪里

| 层 | 路径 |
| --- | --- |
| HTTP 入口（单函数分发） | `api/index.py` |
| 编排与事务边界 | `services/` |
| 领域规则（纯逻辑，不碰 DB 与框架） | `domain/` |
| 领域层的层内工具（机制件，无仓库内依赖 —— 这条是硬约束，见 `tests/test_layering.py` 规则 6） | `domain/internal/` |
| 表级读写（唯一拼 SQL 的地方） | `repositories/` |
| 外部服务适配（模型路由 / OCR / 单位数据） | `providers/` |
| 前端 canonical（Vercel 静态根） | `public/` |
| 前端发布镜像（GitHub Pages） | `docs/` |

> `public/` 与 `docs/` 中的所有非 `.md` 文件由 `tests/test_publish_mirror.js` 强制
> **逐字节相同**。改完 `public/` 用 `scripts/sync_mirror.py` 同步镜像，再用 `--check` 复核。

## 门禁怎么跑

每条判据的脚本都在 `scripts/` 下，自带用法说明与判据自检，**退出码 0 = 通过**：

    pytest tests/ -q                                 # 单元 + 契约 + 分层 + 迁移
    node --test tests/*.js                           # 前端契约（含镜像与门禁判据）
    python scripts/sensitive-scan.py                 # 敏感信息扫描
    python scripts/vercel-dead-routes.py             # 重写源 ⊆ 处理分支（实证发请求）
    python scripts/frontend-api-literal-check.py     # 前端字面量 ⊆ 重写源
    python scripts/live-doc-path-check.py            # 活文档里的页面 / 脚本路径真实存在
    python scripts/env-example-check.py              # .env.example 与代码读取点双向一致
    python scripts/sync_mirror.py --check            # 发布镜像不变量

三个 JSON Schema 的 fixture 校验用 `python domain/validate_schema.py`；
真实 HTTP 冒烟用 `python scripts/phase4-http-smoke.py`。完整的门禁顺序与"每步在防什么"
见 `docs/phase6b3-report.md`（Phase 7a 新增的两步见 `docs/phase7a-report.md`，
Phase 7d 把观察面扩到 5 层与新增第 15 步见 `docs/phase7d-report.md`）。

## 仓库约定（不随时间变化的那部分）

- `.env` 绝不入库；密钥只放部署密钥库。**变量清单以 `.env.example` 为唯一来源**，
  模板与代码的双向一致由判据强制。
- 判据必须**能变红**才算判据：新增判据要做一次变异注入，确认对应用例真的报错。
- 判据的**观察面要等于它要判的语义**。太宽（把注释当成实现）和太窄（同义措辞不认）
  都会失效 —— 两种失效本项目都实际踩过，各记在 `docs/phase6b3-report.md` 与
  `docs/phase7a-report.md`。
- 改完 `public/` 同步 `docs/`；改完活文档跑路径门禁；改完前端调用跑端点门禁；
  改完环境变量跑 env 门禁。
