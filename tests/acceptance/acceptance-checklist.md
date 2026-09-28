# acceptance-checklist.md · 验收门逐条核对表（WorkBuddy 相关项）

## 当前核心版正式用例（2026-09-28）

所有输入均为合成样本，真实参与者数量为 0；测试通过不代表五名真人体验合格。

| 用例 | 操作 | 必须满足的结果 | 实现与证据 |
|---|---|---|---|
| CORE-01 简历与模型真实性 | 同意后诊断简历、请求单条改写 | 有结构化评分与建议；线上必须为真实主/备模型，规则降级不可冒充；改写须待确认 | `scripts/core-release-acceptance.py` TC01 |
| CORE-02 证据到岗位行动 | 从已保存简历提取证据、确认、建岗位、仅用会话分析、生成行动两次 | 证据先 pending；结论为 APPLY/STRETCH/PASS；行动有成果物；重复操作不重复开单 | 同脚本 TC02；本地全流程测试 |
| CORE-03 定向面试 | 按目标岗位开场、连续回答三次、结束提取 | 题目不重复；后续问题包含回答原文片段；新证据仍需确认；此检查不等于人工语义质量评分 | 同脚本 TC03 |
| CORE-04 投递闭环 | 根据已确认证据生成求职信、登记申请、登记面试结果 | 有证据依据、待确认；状态合法推进；不向真实单位发送材料 | 同脚本 TC04 |
| CORE-05 权限与删除 | 无授权访问、另一个合成身份读取/删除、清理本次创建数据 | 无授权 428、跨身份 404、会话删除后不能读取；长期档案保留范围须明确 | 同脚本 TC05；`tests/test_core_release_security.py` |

执行线上用例：`python scripts/core-release-acceptance.py --base-url https://career-coach-omega-three.vercel.app --repeat 3 --out <OUTPUT_JSON>`。输出选用本次新文件，不能覆盖历史证据。只处理本轮新建的随机会话；失败停止依赖链、仍清理测试记录；不写入密钥或原始响应。脚本每轮还可能留下空档案与限流元数据，不应声称完成账号注销。

本地五类验收：`python -m pytest tests/test_core_release.py -v`。包含完整流程、降级反向控制、并发限流、日志防泄漏、隔离 SQLite 备份恢复；真实模型质量和生产 Postgres 恢复必须另外实测。当前结果与失败证据统一登记在 `docs/release-checklist.md`。

## 旧版 WorkBuddy 验收记录（历史，不作为当前上线通过证明）

| # | 验收门（来源） | 自动化/人工 | 对应测试或步骤 | 结果 |
|---|---|---|---|---|
| 1 | 四个 Schema 可校验且 fixtures 全部通过 | 自动 | `pytest tests/test_contracts.py` | ✅ |
| 2 | source_span 100% 可回指原文 | 自动 | `test_contracts.py::test_source_spans_point_into_source` | ✅ |
| 3 | 建议 100% 带证据（≥1 source_span） | 自动 | validate_schema 业务规则 | ✅ |
| 4 | R/M/I/C0/C7 复算与 scoring.md 手算一致（±0.5） | 自动 | `pytest tests/test_rescore.py` + `domain/rescore.py --input score-input-01.json` | ✅ |
| 5 | unknown 不进分母；全 unknown → insufficient_evidence | 自动 | `test_rescore.py` 两个边界用例 | ✅ |
| 6 | 脱敏后无手机号/邮箱/身份证残留 | 自动 | `pytest tests/test_deidentify.py` | ✅ |
| 7 | docx/pdf 提取可用；扫描件明确报错 | 自动 | `pytest tests/test_extract.py` | ✅ |
| 8 | BM25 硬性要求识别（J1/J2 不 missing）；四态互斥 | 自动 | `pytest tests/test_match.py` | ✅ |
| 9 | 故障注入全部拒绝：score=120 / plan=6条 / day重复 / minutes=60 / 缺 artifact / answer_quote 非子串 / 缺必填 | 自动 | `pytest tests/test_fault_injection.py` | ✅ |
| 10 | 注入 JD 被置 flag；幻觉数字被 redflag 阻断；占位数字放行 | 自动 | `test_fault_injection.py` 后四例 | ✅ |
| 11 | 五页面五状态可开（人工走查） | 人工 | `ui/prototype/pages/states.html` 矩阵逐个点开 | ✅ |
| 12 | 雷达三级降级（人工断网验证） | 人工 | 断网开 F4 页 → 应走 vendor；再禁 vendor → 表格 | ✅ |
| 13 | 日志脱敏（token/手机号） | 自动+人工 | `type sample.log \| python domain/internal/log_sanitize.py` | ✅ |

> DuMate 侧验收门（F1 20 份简历≥19 抽取成功、F2 硬性召回≥85%、F3 敏感问题 20 条全阻断、性能门实测）不在本表范围，见 handoffs/003。
