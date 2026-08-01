# contracts/ · 数据合同（冻结层）

四个 JSON Schema（Draft 2020-12）+ scoring.md 评分公式，是全项目的**唯一事实合同**。

## 合同关系

```
原始材料 ──WF-01──▶ 纯文本+pii_removed
   │
   ├─WF-02▶ ResumeProfile ─┐ (resume-profile.schema.json)
   │                       │
   ├─WF-03▶ JobProfile ────┤ (job-profile.schema.json + 四态匹配)
   │                       ├─WF-05▶ AbilityProfile (ability-profile.schema.json)
   └─WF-04▶ InterviewTurn ─┘ (interview-turn.schema.json)
                        计分只按 scoring.md：R / M / I / C0 / C7
```

## 版本约定

- 当前版本：**v1.0 冻结**（commit B）。
- 任何变更必须：① 更新版本号与 CHANGELOG；② 同步 fixtures 与 tools；③ 通过全部契约测试；④ 在新 HANDOFF 中声明。
- 校验入口：`tools/validate_schema.py`（Schema 层 + 业务规则层双重校验）。
- 业务规则（Schema 无法表达的部分）：score∈[0,100]、plan 恰好 7 条且 day 1-7 不重复、每条 30-45 分钟并含 artifact、answer_quote 必须是 answer 子串、dimensions 六维 key 不重复、JobProfile.user_confirmed=true 才允许计分。
