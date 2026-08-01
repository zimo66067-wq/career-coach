# WF-02 · 简历诊断（占位，DuMate 实现）

- **输入**：WF-01 输出的简历纯文本
- **输出**：ResumeProfile（contracts/resume-profile.schema.json）+ 规则分 R
- **主路径**：`prompts/resume/diagnose.md` + 简历文本 → 模型输出 JSON → `validate_schema.py` → `redflag.py` → 规则按 scoring.md 算 R
- **备用A**：模型输出校验失败 → 重试一次（temperature 调低）；仍失败 → 降级为「结构检查清单」（规则静态分析）并标注「简化诊断」
- **备用B**：模型超时（>45s）→ 提示处理中并允许用户稍后查看，不得展示未校验结果
- **退出标准**：JSON 过校验；每条建议 ≥1 个 source_span；redflag 无标红；P95 ≤ 45s
- **禁止**：模型自报总分；无证据打分（必须 unknown）
