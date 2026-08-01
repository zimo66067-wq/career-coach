# HANDOFF-001 · 产品基线 → 构建

- **input_commit**: `0eb43c2`（chore: init repo skeleton）
- **output_commit**: `91f4fe3`（feat(baseline): freeze PRD + contracts + fixtures + workflows 占位）
- **handoff_commit**: 本文件紧随 output_commit 提交

## 任务目标

冻结产品基线（替代原 DuMate 第1阶段）：PRD、四个 JSON Schema、评分公式、合成测试样本、WF 占位定义，为前端与工具链开发提供合同输入。

## 已完成

- docs/PRD.md（MVP F1-F4 冻结、事实锁五条、性能门、验收门、降级总表）
- docs/architecture.md（四层架构、数据流、ADR-1~5）
- docs/privacy.md（去标识化清单、入库规则、删除流程）
- contracts/：resume-profile / job-profile / interview-turn / ability-profile 四个 Schema（Draft 2020-12）+ scoring.md（R/M/I/C0/C7 公式 + 手算示例）+ README
- tests/fixtures-synthetic/：简历×5（含假 PII）、JD×4（job-04 含注入文本）、面试×1、能力×1、对拍输入×1；全部 source_span 偏移经脚本校验
- workflows/：WF-01~06 占位（输入/输出合同、主路径/备用A/备用B、退出标准）

## 变更文件

contracts/（6）、docs/（3）、tests/fixtures-synthetic/（23）、workflows/（7）

## 验收命令与结果

| 验收项 | 结果 |
|---|---|
| 5+4 份 expected.json 的 source_span 与原文逐字一致（脚本校验） | ✅ 通过（resume-01 spans OK / job-04 injection span OK，全量生成时逐条断言） |
| scoring.md 手算示例 R=73.00/M=60.00/I=72.55/C0=68.27/C7=77.79~90.48 | ✅ 已核算并写入第6节 |
| fixtures 无真实 PII | ✅ 全部为合成数据，README 已声明 |
| Schema 均含 `$schema: draft 2020-12` 声明 | ✅ |

（自动化契约测试 pytest 在阶段3 工具链交付后执行，结果回填至 handoffs/003。）

## 未解决问题

- jsonschema/pytest 等依赖未装（阶段3 一并解决并跑契约测试）。
- ability-01.json 的六维分数为演示用映射值，正式映射规则需 DuMate 在 WF-05 实测确认。

## 已知风险

- fixtures 的 txt 一经修改，source_span 偏移即失效 → 修改后必须重新校准（fixtures README 已写明）。
- job-04 注入样本仅覆盖一类注入话术，正式测试应扩充注入语料。

## 回滚点

- 回滚到 `0eb43c2` = 仅骨架。

## 下一位Agent唯一任务

**前端 Agent（WorkBuddy/Kimi-K3）**：按 contracts 与 fixtures 开发 ui/prototype 五页面×五状态静态原型 + prompts/ 七份提示词 + docs/demo-script.md。只拥有 ui/ 与 prompts/、docs/demo-script.md，不得改 contracts/ 与 fixtures。

## 禁止改动

contracts/（含 scoring.md）、tests/fixtures-synthetic/ 在本 HANDOFF 之后视为冻结；如必须改，新开 HANDOFF 并同步 CHANGELOG。
