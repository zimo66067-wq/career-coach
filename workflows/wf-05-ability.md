# WF-05 · 能力聚合与七天计划（占位，DuMate 实现）

- **输入**：R、M、I 及其证据（各合同中的 source_span / 四态明细）
- **输出**：AbilityProfile（contracts/ability-profile.schema.json）
- **主路径**：`rescore.py` 复算对齐 scoring.md（容差 ±0.5）→ 六维映射 → `prompts/plan/seven-day.md` 生成七天计划 → `validate_schema.py` → `radar_adapter.py` 输出 ECharts option
- **备用A**：计划校验失败（非 7 条/时长越界/缺 artifact）→ 重试一次；仍失败 → 使用模板计划并标注「模板计划」
- **备用B**：雷达图渲染失败 → 六维表格降级（ui/prototype/js/radar.js 已内建）
- **退出标准**：plan 恰好 7 条、day 1-7 不重复、每条 30-45 分钟且含 artifact；assumptions 如实列出 0.30/0.70 演示假设
- **禁止**：称「预测」（统一口径「七天竞争力情景推演」）；编造未在输入中的能力证据
