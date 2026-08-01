# tasks/ · 任务看板规则

1. **一个阶段一个写入负责人。** 任何时刻每个文件只有一个 Agent 有权写入。
2. 文件所有权见根 README「双 Agent 分工」表。
3. 切换负责人前必须：通过验收 → 独立 commit → 写 HANDOFF（含 input/output commit、验收结果、未解决问题、回滚点、下一项唯一任务）。
4. 新负责人先拉取并核对 HANDOFF 的 input_commit 与实际 HEAD 一致，再开工。
5. 任务粒度：一个 commit 只做一件事；main 只接收通过验收门的版本，失败回滚到上个验收 commit，不在 main 热修。
6. 本目录可放 `TASK-编号-短名.md` 任务卡片（目标/负责人/验收标准/状态）。
