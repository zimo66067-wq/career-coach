# architecture.md · 架构（v1.0 冻结）

## 1. 四层架构

```
┌────────────────────────────────────────────────────┐
│ 交互层   DuMate 对话任务 + ui/prototype 静态原型     │
├────────────────────────────────────────────────────┤
│ 编排层   WF-01~06 状态机（DuMate 实现）              │
├────────────────────────────────────────────────────┤
│ AI 层    语义抽取/解释/追问（模型，只做语义）          │
├────────────────────────────────────────────────────┤
│ 可信层   contracts 校验 + rescore 复算 + redflag    │
│          事实锁 + deidentify 去标识化（规则做分数、   │
│          验证器做事实）                              │
└────────────────────────────────────────────────────┘
```

核心原则：**模型做语义，规则做分数，验证器做事实。**

## 2. 数据流（WF × contracts × tools）

```
简历/JD 原文
  │ WF-01  extract_text.py → deidentify.py        (纯文本, pii_removed=true)
  ├─ WF-02 prompts/resume/diagnose.md → ResumeProfile
  │         └─ validate_schema.py + redflag.py 通过后才展示，规则算 R
  ├─ WF-03 prompts/match/jd-extract.md → JobProfile(含 prompt_injection_flags)
  │         └─ match_requirements.py (embedding 主 / bm25 备) → 四态，规则算 M
  ├─ WF-04 prompts/interview/interviewer.md → InterviewTurn×N
  │         └─ answer_quote 子串校验，规则算 I
  └─ WF-05 聚合 R/M/I → rescore.py 复算对齐 scoring.md
            → AbilityProfile → radar_adapter.py → ECharts/表格
    WF-06  异常 10s 内降级（states.html 五态）；删除按 docs/privacy.md
```

## 3. 双 Agent 协作（GitHub 异步接力）

- 唯一事实源：本仓库 main 分支；交接 = commit + HANDOFF（handoffs/001-003）。
- 两个 Agent 不得同时修改同一文件；审查 Agent 只输出 review 报告。
- 分支命名 `feature/TASK-编号-短名`；main 只接收通过验收门的版本；失败回滚到上个验收 commit，不在 main 热修。

## 4. 模型与工具分工

| 任务 | 主选 | 备用 |
|---|---|---|
| 产品合同/提示词初稿 | DuMate 当前实测模型 | — |
| 前端原型 | WorkBuddy + Kimi-K3 | Kimi-K2.7-Code |
| 工具/测试 | WorkBuddy + Kimi-K2.7-Code | Kimi-K3（疑难跨文件） |
| JD 语义召回 | 千帆 Qwen3-Embedding-4B | bge-large-zh → TF-IDF/BM25 |
| 面试即时追问 | 低延迟非思考模型 | 固定题库 |
| 报告/F4/七天计划 | Kimi-K3 | GLM 系列 |
| 评分/雷达 | 确定性规则 + ECharts | SVG/表格 |
| 中文安全审查 | GLM 系列一审 | Kimi-K3 二审 |

## 5. 关键设计决策（ADR 摘要）

- **ADR-1 分数只由规则引擎计算**：模型输出子分数，R/M/I/C0 由 scoring.md 公式复算，杜绝模型自报总分。
- **ADR-2 四态互斥 + unknown 剔分母**：避免「不知道」被当「不满足」，保证 M 的可解释性。
- **ADR-3 事实锁机器校验**：redflag.py 对输出做输入闭集检查，幻觉即阻断发布。
- **ADR-4 原型零依赖**：静态 HTML/CSS/JS + ECharts 三级降级，现场无网可演示。
- **ADR-5 语音仅增强**：文字链路是等价稳定主链路，语音失败不阻断提交。
