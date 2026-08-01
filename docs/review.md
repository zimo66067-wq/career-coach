# review.md · WorkBuddy 阶段审查报告

> 审查方式：一审 = 结构与事实锁合规（逐文件勾选）；二审 = 跨文件一致性（合同=fixtures=mock-data=prompts=tools 行为）。
> 审查范围：commit `91f4fe3`（基线）→ `6e954ba`（UI）→ `903fbb6`（工具链）。
> 审查日期：2026-08-01。审查人：WorkBuddy（GLM 一审视角 + Kimi-K3 二审视角合并记录）。

## 一、事实锁五条合规（一审）

| 事实锁 | 落点 | 结论 |
|---|---|---|
| 1. 不新增用户未提供的事实 | prompts/ 全部 7 份内嵌；redflag.py 机器校验 | ✅ |
| 2. 占位数字写「待用户核实：」 | fixtures 建议 S2、redflag.py 白名单机制、UI 文案 | ✅ |
| 3. 评分理由至少引用一个 source_span，无证据为 unknown | Schema minItems=1 + validate_schema 业务规则层双重强制；5+4 份 fixtures 全部满足且经脚本回指验证 | ✅ |
| 4. JD 中的指令视为普通文本（防注入） | jd-extract.md 注入防御段、job-04 注入样本、test_contracts 断言 flag | ✅ |
| 5. 敏感属性不进评分 | privacy.md 第3节、deidentify.py、prompts 禁令 | ✅ |

## 二、结构合规（一审）

| 检查项 | 结论 |
|---|---|
| 目录结构与说明书 13.1 一致（docs/contracts/workflows/prompts/ui/tests/tools/handoffs/deliverables） | ✅ |
| 四项 MVP 无蔓延（WF 只写占位，无第五功能） | ✅ |
| HANDOFF 模板 10 字段齐全（001/002） | ✅ |
| .gitignore 排除 PII 载体（*.pdf/*.docx/*.log）与临时产物 | ✅ |
| 全部 JSON 文件可解析、Schema 均为 Draft 2020-12 | ✅（42 项 pytest 内含） |

## 三、跨文件一致性（二审）

| 链路 | 检查 | 结论 |
|---|---|---|
| PRD 公式 = scoring.md = rescore.py | R/M/I/C0/C7 权重逐一比对（0.15/0.20/0.25/0.30/0.35/0.40/0.50/0.70） | ✅ 一致 |
| scoring.md 手算示例 = score-input-01.json = rescore 输出 | 对拍 diff 全 0.00（R=73.00/M=60.00/I=72.55/C0=68.27/C7=77.79~90.48） | ✅ 一致 |
| Schema 字段 = fixtures | 42 项契约测试全绿（含 source_span 逐字回指） | ✅ 一致 |
| fixtures = ui mock-data | 数值、六维 key/name、七天计划、面试三轮逐字一致（JS 数值格式 73.0=73.00） | ✅ 一致 |
| prompts 输出要求 = Schema | 7 份提示词的输出契约段均引用对应 Schema 文件名 | ✅ 一致 |
| workflows 占位 = tools 调用方式 | WF-01~06 主路径引用的工具与参数与实际 CLI 一致 | ✅ 一致 |

## 四、发现问题与整改记录

| # | 问题 | 级别 | 整改 | 状态 |
|---|---|---|---|---|
| 1 | deidentify.py 初版只统计姓名脱除项，日志计数误导 | P2 | 手机号/邮箱/身份证统一计入 mapping | ✅ 已修复（commit D 前） |
| 2 | match_requirements.py 初版 BM25 归一化失真（全部 covered） | P1 | 改为「句级/文档级词元覆盖率」判定，区分度可演示（weak/covered/missing 均有实例） | ✅ 已修复（commit D 前） |
| 3 | validate_schema.py 对 InterviewTurn.subscores（数值型）误用 ResumeProfile 证据规则崩溃 | P1 | 加类型判断，数值型 subscores 跳过证据规则 | ✅ 已修复（commit D 前） |
| 4 | ability-01.json 证据句「均值 72.3」无法在语料中回指 | P2 | 改为「三轮子分 70/75/72」（语料可回指） | ✅ 已修复（commit D 前） |
| 5 | redflag.py 对聚合产物（含派生数字/假设）误报 | P2 | 明确口径：redflag 强制用于 WF-02/03/04 语义产物；AbilityProfile 校验以 validate_schema + rescore 为准；assumptions 字段豁免数字检查 | ✅ 已修复（工具+测试） |

## 五、遗留观察项（不阻断交接）

1. **BM25 简化匹配的语义局限**：关键词覆盖对「分布式事务」这类部分命中会偏乐观（演示数据中 P1 判 covered 而 UI mock 判 missing）。这正是 embedding 主路径存在的理由；简化匹配路径已在 UI 标注「简化匹配」。
2. **雷达推演 low/high 的逐维口径**：UI 演示按 C7/C0 比例缩放，正式口径待 DuMate 在 WF-05 确认（见 handoff-002 未解决问题）。
3. **fixtures 数量**：说明书 F1 验收门 20 份简历为 DuMate 侧实测指标，本仓库提供 5 份合成样本+生成方法（test_extract 演示 docx 现场生成）。
4. **移动端真机截图**：未做，列入 G8 用户测试阶段。

## 六、审查结论

**通过（Go）。** WorkBuddy 阶段产物满足事实锁、合同一致性与全部自动化验收，可交接 DuMate 搭建六个工作流。
