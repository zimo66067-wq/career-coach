# defense-evidence-index.md · 答辩证据索引 (P2-06)

> 本文件列出评委可能提出的 20+ 问题，每题映射到具体证据文件，按五大类别组织。
> 答辩前每位成员必须熟悉本索引，确保每个问题都能在 30 秒内定位到对应证据。

---

## 一、产品设计类

| # | 评委可能提问 | 映射证据 | 证据路径 | 要点 |
|---|---|---|---|---|
| Q1 | 你们的产品解决了什么核心问题？ | PRD 第1节 + README.md | `docs/PRD.md` 第1节 / `README.md` | 北极星指标：完成一轮「诊断→匹配→面试→报告→七天计划」的用户比例 |
| Q2 | MVP 范围是怎么确定的？为什么只做四项？ | PRD 第2节 | `docs/PRD.md` 第2节 | F1-F4 严格冻结，明确「不做」清单防止范围蔓延 |
| Q3 | 你们的评分体系是怎么设计的？为什么用规则而不是模型打分？ | scoring.md + architecture.md ADR-1 | `contracts/scoring.md` / `docs/architecture.md` ADR-1 | 原则：模型做语义，规则做分数。R/M/I/C0/C7 公式冻结，rescore.py 复算对齐 |
| Q4 | 四态匹配（covered/weak/missing/unknown）的 unknown 为什么不计入分母？ | scoring.md 第2节 + architecture.md ADR-2 | `contracts/scoring.md` 第2节 / `docs/architecture.md` ADR-2 | 避免「不知道」被当「不满足」，保证 M 的可解释性 |
| Q5 | 七天竞争力推演的 0.30/0.70 参数是怎么来的？ | scoring.md 第4节 | `contracts/scoring.md` 第4节 | MVP 演示假设，不是统计学习参数；对外口径统一为「情景推演」 |
| Q6 | 简历诊断的修改建议如何保证能对应到原文？ | PRD 事实锁第3条 + test_contracts.py | `docs/PRD.md` 事实锁第3条 / `tests/test_contracts.py` | 每条评分理由至少引用一个 source_span，Schema minItems=1 强制 |

## 二、AI 能力类

| # | 评委可能提问 | 映射证据 | 证据路径 | 要点 |
|---|---|---|---|---|
| Q7 | 你们用了哪些模型？为什么选这些？ | architecture.md 第4节 + model-baking-log.md | `docs/architecture.md` 第4节 / `docs/model-baking-log.md` | 按任务选模型：Kimi-K3 语义/计划、千帆 embedding 召回、规则算分 |
| Q8 | 如何防止模型编造内容（幻觉）？ | PRD 事实锁第1条 + redflag.py + test_fault_injection.py | `docs/PRD.md` 事实锁第1条 / `tools/redflag.py` / `tests/test_fault_injection.py` | redflag.py 对输出做输入闭集检查，语料外数字阻断发布 |
| Q9 | JD 里如果藏了恶意指令（提示词注入），怎么处理？ | PRD 事实锁第4条 + job-04-injection + test_contracts 断言 | `docs/PRD.md` 事实锁第4条 / `tests/fixtures-synthetic/jobs/job-04-injection.txt` | JD 中的指令视为普通文本，写入 prompt_injection_flags |
| Q10 | 模型超时或断网了怎么办？ | PRD 第8节 + WF-06 降级映射表 + architecture.md ADR-5 | `docs/PRD.md` 第8节 / `workflows/wf-06-ops.md` 第3节 / `docs/architecture.md` ADR-5 | 重试一次 → 10 秒内切降级路径，保留已确认数据 |
| Q11 | 面试追问是怎么实现的？怎么保证追问引用了用户的回答？ | WF-04 + InterviewTurn schema + test_contracts answer_quote 校验 | `workflows/wf-04-interview.md` / `contracts/interview-turn.schema.json` / `tests/test_contracts.py` | answer_quote 必须是 answer 子串，否则该轮作废 |
| Q12 | 雷达图是怎么算出来的？和模型有关系吗？ | scoring.md 第4节 + rescore.py + radar_adapter.py | `contracts/scoring.md` 第4节 / `tools/rescore.py` / `tools/radar_adapter.py` | C0=0.25R+0.35M+0.40I 规则复算，模型不参与总分计算 |

## 三、隐私安全类

| # | 评委可能提问 | 映射证据 | 证据路径 | 要点 |
|---|---|---|---|---|
| Q13 | 用户的简历数据存在哪里？会被保存吗？ | privacy.md 第2节 + SECURITY.md 第3节 | `docs/privacy.md` 第2节 / `SECURITY.md` 第3节 | 数据最小化：仓库只存合成样本，用户数据仅会话期间在 /tmp/ 临时存在 |
| Q14 | 你们怎么处理姓名、手机号等 PII？ | privacy.md 第1节 + deidentify.py + test_deidentify.py | `docs/privacy.md` 第1节 / `tools/deidentify.py` / `tests/test_deidentify.py` | deidentify.py 强制脱除 4 类 PII，pii_removed=true 才进评分 |
| Q15 | 用户想删除数据，你们怎么处理？ | privacy.md 第5节 + WF-06 第4.2节 | `docs/privacy.md` 第5节 / `workflows/wf-06-ops.md` 第4.2节 | DELETED 终态，不再调模型，清除 /tmp/ 与会话缓存 |
| Q16 | 日志里会不会泄露用户信息？ | privacy.md 第4节 + log_sanitize.py + observability.md 第5节 | `docs/privacy.md` 第4节 / `tools/log_sanitize.py` / `docs/observability.md` 第5节 | 日志落盘前必须过 log_sanitize.py，禁止记录清单覆盖 12 类敏感内容 |
| Q17 | 性别、年龄这些敏感属性会影响评分吗？ | PRD 事实锁第5条 + privacy.md 第3节 | `docs/PRD.md` 事实锁第5条 / `docs/privacy.md` 第3节 | 敏感属性不进评分，prompts 各模块已内嵌禁令 |
| Q18 | 你们的 CI 怎么防止密钥泄露？ | SECURITY.md 第5节 + ci.yml 敏感信息扫描 | `SECURITY.md` 第5节 / `.github/workflows/ci.yml` 步骤6 | grep 扫描 5 类密钥模式 + .env 入库检查 + 白名单机制 |

## 四、测试验证类

| # | 评委可能提问 | 映射证据 | 证据路径 | 要点 |
|---|---|---|---|---|
| Q19 | 你们有多少自动化测试？通过率如何？ | handoffs/003 第4节 + acceptance-checklist.md | `handoffs/003-tools-to-dumate.md` 第4节 / `tests/acceptance/acceptance-checklist.md` | 42 项 pytest 全绿（契约/复算/脱敏/提取/匹配/故障注入），13 项验收全勾选 |
| Q20 | 故障注入测试覆盖了哪些场景？ | test_fault_injection.py + acceptance-checklist.md 第9-10项 | `tests/test_fault_injection.py` / `tests/acceptance/acceptance-checklist.md` | 7 类故障注入：score=120 / plan=6条 / day重复 / minutes=60 / 缺 artifact / answer_quote 非子串 / 缺必填 + 注入 JD + 语料外数字 |
| Q21 | 你们的评分公式怎么保证正确？ | scoring.md 手算示例 + rescore.py 对拍 + test_rescore.py | `contracts/scoring.md` 第6节 / `tools/rescore.py` / `tests/test_rescore.py` | 手算 R=73.00/M=60.00/I=72.55/C0=68.27/C7=77.79~90.48，rescore 对拍 diff 全 0.00 |
| Q22 | 降级路径真的能在 10 秒内切换吗？ | WF-06 降级映射表 + g9-submission-checklist.md 故障注入 | `workflows/wf-06-ops.md` 第3节 / `deliverables/g9-submission-checklist.md` 第5节 | 8 类故障映射降级路径，G9 阶段实测降级耗时记录 |
| Q23 | 你们做过用户测试吗？结果如何？ | g8-user-testing.md | `deliverables/g8-user-testing.md` | 5-8 人测试，四功能各 2-3 个任务，定量+定性数据收集模板 |
| Q24 | 移动端能正常用吗？ | mobile-accessibility-testing.md + capability_matrix.md 跨环境 | `docs/mobile-accessibility-testing.md` / `docs/capability_matrix.md` 第5节 | 手机/平板/桌面三端测试 + 无障碍清单 + 降级方案 |

## 五、演示准备类

| # | 评委可能提问 | 映射证据 | 证据路径 | 要点 |
|---|---|---|---|---|
| Q25 | 现场没有网络能演示吗？ | demo-checklist.md + architecture.md ADR-4 | `tests/rehearsal/demo-checklist.md` / `docs/architecture.md` ADR-4 | UI 原型零依赖，ECharts 本地化，断网可展示 success 态 |
| Q26 | 演示过程中如果出了故障怎么办？ | demo-checklist.md 故障预案 + WF-06 | `tests/rehearsal/demo-checklist.md` 故障预案演练 / `workflows/wf-06-ops.md` | 3 类故障预案：拔网线→vendor 降级、被问准不准→现场跑 rescore.py、被问会不会编内容→现场跑 redflag |
| Q27 | 你们的演示流程是什么？ | demo-script.md + demo-checklist.md 现场走查 | `docs/demo-script.md` / `tests/rehearsal/demo-checklist.md` | 7 分镜：开场→F1证据→F2四态→F3追问→F4报告→降级→收尾 |
| Q28 | 彩排了多少次？最后一次有阻断吗？ | g9-submission-checklist.md 10次彩排记录 | `deliverables/g9-submission-checklist.md` 第2节 | 10 次彩排，最后 3 次无阻断才准予提交 |
| Q29 | 评委可以自己试用吗？分享 URL 怎么访问？ | capability_matrix.md 匿名访问 + g9-submission-checklist.md 跨环境 | `docs/capability_matrix.md` 第4-5节 / `deliverables/g9-submission-checklist.md` 第4节 | 匿名访问验证：退出登录/无痕/另一设备/手机热点，8 项跨环境验证 |
| Q30 | 你们的代码和 Skill 可以复用吗？ | README.md + deliverables/README.md + skill/ 目录 | `README.md` / `deliverables/README.md` / `deliverables/skill/` | DuMate 可复用对话 Skill 导出，GitHub 仓库为唯一事实源 |

---

## 答辩准备清单

- [ ] 每位成员通读本索引，确保 30 秒内定位到对应证据文件
- [ ] 打印本索引作为答辩速查卡（A4 双面）
- [ ] 准备以下文件可直接展示：
  - `tests/fixtures-synthetic/` 合成样本（可现场跑工具）
  - `ui/prototype/index.html` 零依赖原型（可断网演示）
  - `tools/rescore.py` + `score-input-01.json`（可现场对拍）
  - `tools/redflag.py`（可现场跑注入用例）
  - `tests/test_fault_injection.py`（可现场跑故障注入）
- [ ] 准备答辩 PPT / PDF 方案文档（≤20 页）
- [ ] 准备演示 MP4（4 分 30 秒主路径 + 降级演示）
- [ ] 确认分享 URL 匿名可访问（跨环境验证全通过）
