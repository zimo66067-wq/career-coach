# acceptance-checklist.md · 验收门逐条核对表（WorkBuddy 相关项）

| # | 验收门（来源） | 自动化/人工 | 对应测试或步骤 | 结果 |
|---|---|---|---|---|
| 1 | 四个 Schema 可校验且 fixtures 全部通过 | 自动 | `pytest tests/test_contracts.py` | ✅ |
| 2 | source_span 100% 可回指原文 | 自动 | `test_contracts.py::test_source_spans_point_into_source` | ✅ |
| 3 | 建议 100% 带证据（≥1 source_span） | 自动 | validate_schema 业务规则 | ✅ |
| 4 | R/M/I/C0/C7 复算与 scoring.md 手算一致（±0.5） | 自动 | `pytest tests/test_rescore.py` + `tools/rescore.py --input score-input-01.json` | ✅ |
| 5 | unknown 不进分母；全 unknown → insufficient_evidence | 自动 | `test_rescore.py` 两个边界用例 | ✅ |
| 6 | 脱敏后无手机号/邮箱/身份证残留 | 自动 | `pytest tests/test_deidentify.py` | ✅ |
| 7 | docx/pdf 提取可用；扫描件明确报错 | 自动 | `pytest tests/test_extract.py` | ✅ |
| 8 | BM25 硬性要求识别（J1/J2 不 missing）；四态互斥 | 自动 | `pytest tests/test_match.py` | ✅ |
| 9 | 故障注入全部拒绝：score=120 / plan=6条 / day重复 / minutes=60 / 缺 artifact / answer_quote 非子串 / 缺必填 | 自动 | `pytest tests/test_fault_injection.py` | ✅ |
| 10 | 注入 JD 被置 flag；幻觉数字被 redflag 阻断；占位数字放行 | 自动 | `test_fault_injection.py` 后四例 | ✅ |
| 11 | 五页面五状态可开（人工走查） | 人工 | `ui/prototype/pages/states.html` 矩阵逐个点开 | ✅ |
| 12 | 雷达三级降级（人工断网验证） | 人工 | 断网开 F4 页 → 应走 vendor；再禁 vendor → 表格 | ✅ |
| 13 | 日志脱敏（token/手机号） | 自动+人工 | `type sample.log \| python tools/log_sanitize.py` | ✅ |

> DuMate 侧验收门（F1 20 份简历≥19 抽取成功、F2 硬性召回≥85%、F3 敏感问题 20 条全阻断、性能门实测）不在本表范围，见 handoffs/003。
