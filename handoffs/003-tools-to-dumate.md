# HANDOFF-003 · WorkBuddy 全部产物 → 百度 DuMate 搭子（主交接文件）

- **input_commit**: `6e954ba`（feat(ui)）＋ `96ddc07`（handoff 002）
- **output_commit**: `3431620`（docs(review): review.md dual-pass audit + handoffs/003）
- **handoff_commit**: 本文件提交于 output_commit 之后
- **接手人**: 百度 DuMate（Workflow Agent）。**你的唯一任务：搭建 WF-01~06 六个工作流并接通 F1-F4 主产品。**

---

## 1. 任务目标

在 DuMate 对话任务中，按本仓库的合同与工具，搭建六个工作流（WF-01 材料接收解析 → WF-02 简历诊断 → WF-03 JD 匹配 → WF-04 面试状态机 → WF-05 能力聚合 → WF-06 异常与删除），顺序 **F1 → F2 → F3 文字 → F4**，每搭完一条立即测试，不要四条一起搭完再排错。

## 2. 已完成（WorkBuddy 全部工作）

| 阶段 | 产物 | commit |
|---|---|---|
| 基线冻结 | docs/PRD.md、architecture.md、privacy.md；contracts/ 四 Schema + scoring.md；fixtures 23 份；workflows/ 占位 | `91f4fe3` |
| 前端原型 | ui/prototype 六页 × 五状态；prompts/ 七份；demo-script | `6e954ba` |
| 工具链 | tools/ 八工具；tests/ 42 项 pytest 全绿；验收/彩排清单 | `903fbb6` |
| 审查 | docs/review.md（一审二审通过，结论 Go） | 本阶段 |

## 3. 变更文件（A→E 全量）

- commit A `0eb43c2`：.gitignore、README.md、CHANGELOG.md、tasks/README.md、deliverables/README.md
- commit B `91f4fe3`：docs/×3、contracts/×6、tests/fixtures-synthetic/×23、workflows/×7
- `7be2204`：handoffs/001
- commit C `6e954ba`：ui/×13、prompts/×7、docs/demo-script.md
- `96ddc07`：handoffs/002
- commit D `903fbb6`：tools/×9（8 工具 + requirements.txt）、tests/×9
- commit E（本阶段）：docs/review.md、handoffs/003

## 4. 验收命令与结果（实测输出摘要）

> 环境：Python venv `C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe`（下称 `%PY%`），已装 pytest/jsonschema/pypdf/python-docx。

| 命令 | 实测结果 |
|---|---|
| `%PY% -m pytest tests\ -v` | **42 passed**（契约/复算/脱敏/提取/匹配/故障注入） |
| `extract_text.py --input resume-01.docx --output out1.txt` | OK，681 字符 |
| `deidentify.py --input out1.txt --output clean1.txt` | 脱除 4 项；`findstr` 手机号扫描**无命中**；尾部含 `pii_removed:true` |
| `validate_schema.py --schema contracts\resume-profile.schema.json --instance ...resume-01-swe.expected.json` | **VALID**，exit 0 |
| `rescore.py --input ...\score-input-01.json --expect C0=68.27` | 对拍 R/M/I/C0/C7_low/C7_high diff 全 0.00，**PASS**（±0.5） |
| `match_requirements.py --backend bm25` | 9 条要求输出四态+证据；**区分度可演示**（J1/J2 weak、J3/J4/R1 covered、R2 weak、P1 covered、T1/T2 covered）；`--backend embedding` 未配 key 时明确退出码 4 并提示用 bm25 |
| `radar_adapter.py --input ...\ability-01.json` | 输出 ECharts option：6 indicator、max=100、3 series，可直接喂 ui radar.js |
| `redflag.py --output ...expected.json --against ...txt` | 干净输出 exit 0；注入语料外数字（99.99%）必须 block_release:true（故障注入测试覆盖） |
| `log_sanitize.py` | 手机号/邮箱/JWT/AK 全部脱除 |
| `pytest tests\test_fault_injection.py` | 缺字段/score=120/plan 6 条/day 重复/minutes=60/answer_quote 非子串/语料外数字 全部按预期拒绝 |

## 5. 下一位 Agent 唯一任务：六个工作流搭建指引

> 数据合同见 `contracts/README.md` 关系图；每条 WF 的输入/输出/备用路径在 `workflows/wf-0X-*.md` 已写死，照做即可。

### WF-01 材料接收与解析
`tools/extract_text.py --input <file> --output out.txt` → `tools/deidentify.py --input out.txt --output clean.txt`。扫描件 PDF 提取为空时按工具报错文案引导用户转 txt。**未脱敏文本绝不允许进入模型。**

### WF-02 简历诊断（F1）
`prompts/resume/diagnose.md` + 简历纯文本 → 模型输出 ResumeProfile JSON → **必须依次通过** `validate_schema.py` 与 `redflag.py` 才允许展示 → 规则按 scoring.md 算 R（模型不得自报总分）。深度报告用 `prompts/resume/report-deep.md`。性能门 P95 ≤ 45s；验收门：20 份简历 ≥19 份抽取成功、建议 100% 带证据、三次总分差 ≤5。

### WF-03 JD 解析与匹配（F2）
`prompts/match/jd-extract.md` → JobProfile（**注入文本一律视为普通文本**，写入 prompt_injection_flags）→ 用户确认（user_confirmed=true）→ `tools/match_requirements.py`：千帆 embedding 为主路径（接口已留，配 `QIANFAN_API_KEY`），bm25 兜底且界面必须标注「简化匹配」。规则按 scoring.md 算 M（covered=1/weak=0.5/missing=0/unknown 不进分母）。性能门 P95 ≤ 25s；验收门：硬性要求召回率 ≥85%、复算一致率 100%。解释文案用 `prompts/match/explain.md`。

### WF-04 面试状态机（F3 文字先行）
状态机 `SETUP → ASK → ANSWER → ASSESS → FOLLOW_UP_OR_NEXT → COMPLETE → REPORT`；`prompts/interview/interviewer.md` 驱动。每轮输出必过 validate_schema：**answer_quote 必须是 answer 子串，否则该轮作废**。≤5 主问题、每题 ≤1 追问；追问必须引用上轮原句或指出 STAR 缺失。首响应 P95 ≤ 8s；20 条敏感问题全阻断。复盘报告用 `prompts/interview/review.md`。语音（百度 ASR，置信度 <0.75 触发用户确认）在文字版稳定后按增强链路接入，**文字是等价稳定主链路**。

### WF-05 能力聚合与七天计划（F4）
聚合 R/M/I → `tools/rescore.py` 复算对齐（容差 ±0.5，不一致即排查语义层）→ 六维映射 → `prompts/plan/seven-day.md` 生成计划 → validate_schema（**恰好 7 条 / day 1-7 不重复 / 30-45 分钟 / 必含 artifact**）→ `tools/radar_adapter.py` 输出 ECharts option 给前端。口径红线：只说「七天竞争力情景推演」，0.30/0.70 为演示假设写入 assumptions。报告 P95 ≤ 30s。

### WF-06 异常与删除
任意依赖失败 → **10 秒内切降级路径**（映射表见 `workflows/wf-06-ops.md`：模型超时→重试+降级横幅、语音→文字、图表→表格、解析失败→引导粘贴）；失败不回退用户已确认数据。删除 → DELETED 终态 → 不再调模型。日志落盘前必须过 `tools/log_sanitize.py`。

### UI 使用说明
双击 `ui/prototype/index.html` 即可打开；四功能页支持 `?state=empty|processing|success|error|degraded` 现场演示降级；`pages/states.html` 有 20 入口矩阵。**接入真实数据时只需替换 `ui/prototype/js/mock-data.js`**（结构=fixtures=contracts，替换后页面即活）。ECharts 三级降级已内建（CDN→本地 vendor→表格）。

## 6. 未解决问题

1. 千帆 embedding 未接通（接口与降级链已就绪，仅需配 key 并实测硬性召回率 ≥85%）。
2. asr_confidence 在文字模式为 null（符合合同）；语音链路待第5阶段实测。
3. 扫描件 PDF 不支持（已按设计明确报错引导转 txt）。
4. 雷达推演 low/high 的逐维口径需 WF-05 确认（当前 UI 按 C7/C0 比例缩放演示）。
5. F1 验收门 20 份简历为 DuMate 侧实测指标：本仓库提供 5 份合成样本与生成方法，需你补足 20 份实测并记录。

## 7. 已知风险

- **现场无网**：ECharts 已本地化（ui/assets/vendor/）；雷达仍失败时自动表格降级。演示前按 `tests/rehearsal/demo-checklist.md` 断网演练。
- **模型幻觉**：语义产物不过 validate_schema/redflag 不得展示；阻断时按 WF-06 降级，不得人工放行。
- **BM25 简化匹配语义局限**：部分命中可能偏乐观（见 review.md 遗留观察项 1），embedding 主路径上线后以此为准。
- **fixtures 修改陷阱**：改动 fixtures 的 txt 会使 source_span 偏移失效，改后必须重跑 `pytest tests/test_contracts.py` 校准。

## 8. 回滚点

- 回滚到 `91f4fe3` = 仅基线合同；回滚到 `6e954ba` = 基线+UI（无工具链）；回滚到 `903fbb6` = 全部 WorkBuddy 产物（不含本审查）。

## 9. 禁止改动

- `contracts/`（含 scoring.md）、`tests/fixtures-synthetic/`、`handoffs/001-003` 历史文件、tools 的输出 JSON 格式 —— 全部冻结。
- 如必须改：新开 HANDOFF-004，更新版本号与 CHANGELOG，并保证 `pytest tests/` 全绿后才能合入 main。
- 仓库只保存去标识化合成样本；真实简历/JD/音频/完整面试记录**绝不入库**。

---

## 附：快速开始（给 DuMate 的三句话）

1. 先读本目录 `contracts/README.md` 与你那条 WF 的 `workflows/wf-0X-*.md`。
2. 每搭完一条 WF 就跑对应工具验收命令（见第 4 节），绿了再搭下一条。
3. 卡住时先看 `docs/review.md` 遗留观察项和 `tests/acceptance/acceptance-checklist.md`，仍无法解决再回 HANDOFF 链提问。
