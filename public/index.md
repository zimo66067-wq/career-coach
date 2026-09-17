# 职跃AI · 公开文档索引

本索引列出**发布树 `public/` 下对公网可读的全部文档**（不含本索引自身）。

公开范围由 `contracts/publish-scope.json` 逐份记录，并有判据 `scripts/publish-scope-check.py`
守着：新增 / 删除 / 改名一份 md 而不同步改清单，门禁会红。

| 文件 | 类型 | 说明 |
|---|---|---|
| README.md | 发布树自述 | 页面清单、公开运行规则、发布结构与同步约定 |
| blind-test-results/blind-test-report.md | 盲测证据 | 模型盲测报告（P2-02） |
| capability_matrix.md | 赛事能力证据 | DuMate 平台能力实测表（P0-06），N1–N18 映射 WF-01–WF-06 |
| defense-evidence-index.md | 赛事能力证据 | 答辩证据索引（P2-06）与对应文件位置 |
| dumate-workflow-sop.md | 平台搭建手册 | DuMate 六工作流搭建 SOP（P0-01） |
| embedding-model-comparison.md | 技术选型证据 | embedding 模型对比（千帆 / 智谱 / Jina） |
| mobile-accessibility-testing.md | 测试方法与模板 | 移动端与无障碍测试计划（P1-09） |
| model-baking-log.md | 技术选型证据 | 模型选择与盲测记录（P2-02） |
| observability.md | 工程规范 | 可观测性规范（P2-03），含禁止记录清单 |
| p0-02-automation-alternatives.md | 过程追踪 | P0-02 自动化替代方案评估 |
| qianfan-embedding-test-report.md | 技术选型证据 | 千帆 Embedding API 连通性测试（2026-08-02） |
| redesign-v2-visual.md | 交付与改版记录 | 前端视觉改版（v2）交付记录 |
| remaining-items.md | 过程追踪 | 仍需完成项记录（2026-08-02，带逐项状态） |
| remaining-items-2026-08-02-fixed.md | 过程追踪 | 待完善与修复报告（2026-08-02，G0–G9 符合性） |
| user-research-template.md | 测试方法与模板 | G8 用户验证数据收集模板 |

> **新增文档时要做两件事**：按 `主题_类型.md` 命名，并且**同步更新
> `contracts/publish-scope.json`**（写明用途分类与理由）。只做前一件，门禁会红 ——
> 因为往 `public/` 里放文件就是把它发布出去，这一步必须是有意的。
