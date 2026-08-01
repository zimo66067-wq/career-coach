# HANDOFF.md · 当前阶段交接文件 (P1-08)

> 本文件是 career-coach 仓库的根级 HANDOFF，描述当前阶段状态、已完成里程碑、未完成项与下一步。
> 每次阶段切换或重要变更后更新。

---

## 1. 当前阶段事实声明

- **当前阶段**：G7（审查与交接完成）→ G8（校内验证准备中）。
- **当前 commit hash**：`672102bfbaba7a72d00c8ec8c771e5bc3ec060de`。
- **分支**：main。
- **最后更新日期**：2026-08-01。
- **最后操作**：创建 P1-06~P2-06 审计报告整改文件（.env.example、SECURITY.md、ci.yml、capability_matrix.md、deliverables README/G8/G9、docs/mobile-accessibility-testing.md、model-baking-log.md、observability.md、defense-evidence-index.md）。

## 2. 已完成里程碑列表

| 里程碑 | commit | 日期 | 说明 |
|---|---|---|---|
| 基线冻结（commit B） | `91f4fe3` | 2026-07-31 | docs/PRD、architecture、privacy；contracts 四 Schema + scoring.md；fixtures 23 份；workflows 占位 |
| 前端原型与提示词（commit C） | `6e954ba` | 2026-07-31 | ui/prototype 六页五状态；prompts/ 七份；demo-script |
| 工具链与测试（commit D） | `903fbb6` | 2026-07-31 | tools/ 八工具；tests/ 42 项 pytest 全绿；验收/彩排清单 |
| 审查报告（commit E） | `3431620` | 2026-08-01 | docs/review.md 一审二审通过，结论 Go |
| 工作流搭建（commit F） | `654e475` | 2026-08-01 | WF-01~06 六条工作流定义并接通 F1-F4 |
| 验收清单勾选（commit G） | `672102b` | 2026-08-01 | gitignore 预览截图 + .dumate，验收清单 13 项全部勾选 |
| 审计报告整改（本批） | 待提交 | 2026-08-01 | 12 个审计文件创建（.env.example、SECURITY.md、ci.yml 等） |

## 3. 未完成项清单

| # | 任务 | 优先级 | 说明 | 阻塞项 |
|---|---|---|---|---|
| 1 | 千帆 embedding 接通实测 | P0 | 需配 QIANFAN_API_KEY 并测硬性召回率 ≥85% | 需获取千帆凭证 |
| 2 | F1 简历诊断模型实测（20 份） | P0 | 需 DuMate 侧跑 20 份简历，≥19 份抽取成功 | 需 DuMate 平台运行 |
| 3 | F3 面试状态机实测 | P0 | 文字面试完整流转、追问引用上轮原句 | 需 DuMate 平台运行 |
| 4 | F3 敏感问题阻断实测（20 条） | P0 | 20 条敏感问题全部阻断 | 需 DuMate 平台运行 |
| 5 | F4 七天计划生成实测 | P0 | 恰好 7 条 / day 1-7 不重复 / 30-45 分钟 / 含 artifact | 需 DuMate 平台运行 |
| 6 | 语音 ASR/TTS 链路实测 | P1 | 按键说话 → 文字转写 + TTS 播报 | 需配置 ASR/TTS 接口 |
| 7 | G8 校内用户测试 | P0 | 招募 5-8 人，完成四功能测试 | 需主功能实测通过 |
| 8 | G9 彩排（10 次） | P0 | 10 次完整彩排无阻断 | 需 G8 通过 |
| 9 | 移动端真机测试 | P1 | 手机/平板截图与无障碍测试 | 需主功能实测通过 |
| 10 | 跨环境匿名访问验证 | P0 | 退出登录/无痕/另一设备/手机热点 | 需 Skill 分享 URL |
| 11 | CI 流水线首次运行 | P1 | 推送到 GitHub 后验证 ci.yml 全步骤通过 | 需推送到远程仓库 |
| 12 | 方案 PDF / 演示 MP4 产出 | P0 | G9 最终交付物 | 需所有实测与彩排完成 |

## 4. 当前 commit hash

```
672102bfbaba7a72d00c8ec8c771e5bc3ec060de
```

> 本批整改文件提交后将更新此 hash。

## 5. 回滚点

| 回滚点 | commit hash | 含义 |
|---|---|---|
| 回滚到验收清单勾选 | `672102b` | 全部 WorkBuddy 产物 + 工作流 + 验收清单（不含本批整改） |
| 回滚到工作流搭建 | `654e475` | 基线 + UI + 工具链 + 审查 + 工作流（不含验收清单与整改） |
| 回滚到审查报告 | `3431620` | 基线 + UI + 工具链 + 审查（不含工作流） |
| 回滚到工具链 | `903fbb6` | 基线 + UI + 工具链（不含审查） |
| 回滚到 UI 原型 | `6e954ba` | 基线 + UI（无工具链） |
| 回滚到基线 | `91f4fe3` | 仅基线合同（无 UI/工具链/工作流） |

## 6. 下一唯一任务

**接通千帆 embedding 主路径并实测硬性召回率 ≥85%。**

操作步骤：
1. 在 `.env` 中填入 QIANFAN_API_KEY 和 QIANFAN_SECRET_KEY（从千帆控制台获取）。
2. 运行 `python tools/match_requirements.py --backend embedding --jd tests/fixtures-synthetic/jobs/job-01-swe.txt --resume tests/fixtures-synthetic/resumes/resume-01-swe.txt`。
3. 确认输出四态匹配结果，检查硬性要求召回率是否 ≥85%。
4. 失败时降级为 BM25（exit 4），确认界面标注「简化匹配」。
5. 成功后在 `docs/capability_matrix.md` 回填 N8 状态为「已验证」。

> 完成此任务后，进入 DuMate 平台搭建并实测 F1-F4 主功能。

## 7. 证据索引

| 证据 | 文件路径 | 说明 |
|---|---|---|
| 产品需求文档 | `docs/PRD.md` | v1.0 冻结，四功能范围与验收门 |
| 架构文档 | `docs/architecture.md` | 四层架构 + ADR 决策 |
| 隐私策略 | `docs/privacy.md` | 去标识化 + 数据最小化 + 删除流程 |
| 审查报告 | `docs/review.md` | 一审二审通过，Go |
| 评分公式 | `contracts/scoring.md` | R/M/I/C0/C7 公式（冻结） |
| 工具链验收 | `handoffs/003-tools-to-dumate.md` | 42 项 pytest 全绿 + 工具命令实测 |
| 验收清单 | `tests/acceptance/acceptance-checklist.md` | 13 项全勾选 |
| 彩排清单 | `tests/rehearsal/demo-checklist.md` | 会前检查 + 现场走查 + 故障预案 |
| 安全策略 | `SECURITY.md` | 漏洞报告 + 密钥轮换 + 数据边界 + PII + 依赖扫描 |
| 环境变量模板 | `.env.example` | 所有变量名与获取方式 |
| CI 流水线 | `.github/workflows/ci.yml` | pytest + schema + 敏感信息扫描 |
| 能力矩阵 | `docs/capability_matrix.md` | DuMate 平台能力实测记录 |
| G8 测试计划 | `deliverables/g8-user-testing.md` | 校内验证 5-8 人测试 |
| G9 提交清单 | `deliverables/g9-submission-checklist.md` | 10 次彩排 + 冻结清单 |
| 移动端测试 | `docs/mobile-accessibility-testing.md` | 移动端 + 无障碍测试 |
| 模型选择记录 | `docs/model-baking-log.md` | 盲测输入 + 对比维度 |
| 可观测性 | `docs/observability.md` | trace_id + 错误分类 + 禁止记录清单 |
| 答辩证据索引 | `docs/defense-evidence-index.md` | 20+ 评委问题 → 证据映射 |
