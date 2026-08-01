# WF-04 · 面试状态机（占位，DuMate 实现）

- **输入**：ResumeProfile + JobProfile（targets 取自 JD 关键要求）
- **输出**：InterviewTurn 序列（≤5 轮）+ 规则分 I + 表现报告
- **状态机**：`SETUP → ASK → ANSWER → ASSESS → FOLLOW_UP_OR_NEXT → COMPLETE → REPORT`
- **主路径**：`prompts/interview/interviewer.md` 驱动提问/追问；每轮输出过 validate_schema（answer_quote 必须是 answer 子串，否则该轮作废重评）
- **备用A**：低延迟模型不可用 → 固定题库顺序提问，追问降级为「请补充结果数据」类模板
- **备用B**（语音增强链）：按键说话 → 百度 ASR → asr_confidence<0.75 触发用户确认 → 确认后回到主路径
- **退出标准**：≤5 主问题、每题≤1 追问；追问必须引用上一轮回答短句或指出 STAR 缺失项；20 条敏感问题全部阻断；首响应 P95 ≤ 8s
- **禁止**：视频表情识别/数字人/全双工实时语音/多面试官群聊（非目标）
