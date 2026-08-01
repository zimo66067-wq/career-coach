# fixtures-synthetic · 合成测试样本

> **本目录全部为人造合成数据，不含任何真实个人信息。** 姓名（张三/李四/王五/赵六/孙七）、电话、邮箱、身份证号均为虚构，仅用于去标识化与契约测试。

## 命名规范

- `resumes/resume-XX-<画像>.txt` + 同名 `.expected.json`（期望 ResumeProfile）
- `jobs/job-XX-<画像>.txt` + 同名 `.expected.json`（期望 JobProfile）
- `interviews/interview-XX.json`（InterviewTurn 序列）
- `abilities/ability-XX.json`（期望 AbilityProfile）/ `score-input-XX.json`（rescore 对拍输入）

## 清单

| 文件 | 用途 |
|---|---|
| resume-01-swe ~ resume-05-fresh（5 份） | 后端/前端/数据/产品/应届五画像；均含假 PII，供 deidentify 测试 |
| job-01-swe ~ job-03-data（3 份） | 正常 JD，requirements 四类齐全 |
| job-04-injection | **故意嵌入提示词注入文本**，供 prompt_injection_flags 与 redflag 测试 |
| interview-01 | 3 轮面试，answer_quote 逐字摘自 answer；turn_2 缺 metric、turn_3 缺 result |
| ability-01 | 与 contracts/scoring.md 手算示例一致（R=73/M=60/I=72.55/C0=68.27/C7=77.79~90.48） |
| score-input-01 | rescore.py 对拍输入（含 expected 基准值） |

## 规则

1. 禁止放入真实简历/JD/面试记录（见 docs/privacy.md）。
2. 修改样本必须同步修改对应 expected.json，并跑通 `pytest tests/`。
3. source_span 的 start/end 为 UTF-8 字符偏移，修改 txt 后需重新校准。
