# workflows/ · 工作流总览（WF-01 ~ WF-06）

> 六个工作流由 **DuMate（百度搭子）实现**，本目录当前为占位定义：只冻结输入/输出合同、调用的工具与提示词、退出标准。详细搭建指引见 `handoffs/003-tools-to-dumate.md`。

| WF | 名称 | 输入 | 输出合同 | 调用工具/提示词 | 退出标准 |
|---|---|---|---|---|---|
| WF-01 | 材料接收与解析 | 原始文件/粘贴文本 | 纯文本 + pii_removed | extract_text.py → deidentify.py | 非空文本且 pii_removed=true |
| WF-02 | 简历诊断 | 简历纯文本 | ResumeProfile | prompts/resume/diagnose.md → validate_schema.py → redflag.py | 校验通过 + 规则算 R |
| WF-03 | JD 解析与匹配 | JD 纯文本 | JobProfile + 四态 | prompts/match/jd-extract.md → match_requirements.py | 硬性召回≥85% + 规则算 M |
| WF-04 | 面试状态机 | ResumeProfile+JobProfile | InterviewTurn 序列 | prompts/interview/interviewer.md | ≤5 主问题、每题≤1 追问、answer_quote 子串校验通过 |
| WF-05 | 能力聚合与计划 | R/M/I + 证据 | AbilityProfile | rescore.py 复算 → radar_adapter.py | C0 复算容差 ±0.5；plan 过校验 |
| WF-06 | 异常与删除 | 任意异常/删除请求 | 降级态 / DELETED | log_sanitize.py | 10s 内降级；删除后不再调模型 |

主状态机：`CONSENT → RESUME_READY → JD_READY → INTERVIEWING → REPORT_READY`（删除后 `DELETED`）。
