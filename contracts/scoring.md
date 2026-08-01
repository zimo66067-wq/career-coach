# scoring.md · 评分公式（冻结 v1.0）

> **冻结层文件。** 任何公式、权重、阈值变更必须走变更流程：更新版本号 + 测试记录 + HANDOFF。
> 原则：**模型做语义，规则做分数。** 模型负责产出子分数与四态判断，本文件的公式是唯一计分依据，模型不得自行给总分。

## 1. F1 简历诊断分 R（0-100）

```
R = 结构完整度×15% + 表达清晰度×20% + 成果证据×25% + 技能证据×20% + ATS可读性×20%
```

| 子项 | 字段 | 权重 | 数据来源 |
|---|---|---|---|
| 结构完整度 | structure | 15% | ResumeProfile.subscores.structure |
| 表达清晰度 | clarity | 20% | ResumeProfile.subscores.clarity |
| 成果证据 | achievement_evidence | 25% | ResumeProfile.subscores.achievement_evidence |
| 技能证据 | skill_evidence | 20% | ResumeProfile.subscores.skill_evidence |
| ATS可读性 | ats_readability | 20% | ResumeProfile.subscores.ats_readability |

每个子分数 0-100，且**每条评分理由必须至少引用一个 source_span**；无证据的维度记 unknown 并从权重中剔除（剩余权重归一化）。

## 2. F2 岗位匹配分 M（0-100）

```
M = 硬性要求×50% + 职责匹配×25% + 加分项×15% + 术语覆盖×10%
```

四态计分（互斥）：**covered=1，weak=0.5，missing=0，unknown 不计入分母**。
类别得分 = 该类 Σ计分 / 该类有效条数（剔除 unknown）× 100；某类全部 unknown → 该类记 `insufficient_evidence`，其权重在剩余类别间按比例归一。

| 类别 | type | 权重 |
|---|---|---|
| 硬性要求 | hard | 50% |
| 职责匹配 | responsibility | 25% |
| 加分项 | preferred | 15% |
| 术语覆盖 | terminology | 10% |

## 3. F3 面试表现分 I（0-100）

```
I = 结构性×25% + 岗位相关性×25% + 具体性×20% + 追问适应性×15% + 表达清晰度×15%
```

子分数取全部 InterviewTurn 对应子分的均值；某轮 `answer_quote` 缺失或不是回答原文子串 → 该轮作废不计。

## 4. 综合基线 C0 与七天情景推演

```
C0      = 0.25×R + 0.35×M + 0.40×I
可提升空间 = 100 - C0
C7_low  = min(100, C0 + 可提升空间 × 0.30)
C7_high = min(100, C0 + 可提升空间 × 0.70)
```

> 0.30 与 0.70 是 **MVP 演示假设，不是统计学习参数**。对外口径统一为「七天竞争力情景推演」，假设必须写入 `scenario_day7.assumptions[]`。

## 5. 舍入规则

- 中间过程保留全精度，最终输出四舍五入保留 2 位小数（round half up）。
- 复算容忍差：±0.5（rescore.py 默认 tolerance）。

## 6. 手算示例（rescore.py 唯一对拍基准）

输入（与 `tests/fixtures-synthetic/abilities/score-input-01.json` 完全一致）：

**R 子分**：structure=80, clarity=75, achievement_evidence=60, skill_evidence=70, ats_readability=85

```
R = 80×0.15 + 75×0.20 + 60×0.25 + 70×0.20 + 85×0.20
  = 12 + 15 + 15 + 14 + 17 = 73.00
```

**M 四态**（8 条要求）：

| # | type | status | 计分 |
|---|---|---|---|
| 1 | hard | covered | 1 |
| 2 | hard | weak | 0.5 |
| 3 | hard | missing | 0 |
| 4 | hard | unknown | 剔除 |
| 5 | responsibility | covered | 1 |
| 6 | responsibility | covered | 1 |
| 7 | preferred | missing | 0 |
| 8 | terminology | covered | 1 |

```
hard           = (1 + 0.5 + 0) / 3 × 100 = 50.00   （unknown 已剔除，分母=3）
responsibility = (1 + 1) / 2 × 100       = 100.00
preferred      = 0 / 1 × 100             = 0.00
terminology    = 1 / 1 × 100             = 100.00
M = 50×0.50 + 100×0.25 + 0×0.15 + 100×0.10 = 25 + 25 + 0 + 10 = 60.00
```

**I 子分**：structure=70, relevance=80, specificity=65, followup_adaptation=75, clarity=72

```
I = 70×0.25 + 80×0.25 + 65×0.20 + 75×0.15 + 72×0.15
  = 17.5 + 20 + 13 + 11.25 + 10.8 = 72.55
```

**综合**：

```
C0      = 0.25×73.00 + 0.35×60.00 + 0.40×72.55 = 18.25 + 21 + 29.02 = 68.27
可提升空间 = 100 - 68.27 = 31.73
C7_low  = min(100, 68.27 + 31.73×0.30) = 68.27 + 9.519  = 77.79
C7_high = min(100, 68.27 + 31.73×0.70) = 68.27 + 22.211 = 90.48
```

**对拍期望值**：R=73.00，M=60.00，I=72.55，C0=68.27，C7_low=77.79，C7_high=90.48（±0.5）。

## 7. 边界规则

- M 某类全部 unknown → 该类 `insufficient_evidence`，权重归一；全部类别均 unknown → M 整体 `insufficient_evidence`，C0 不计算并报错。
- R/I 输入缺失 → 对应项按 unknown 处理，不得按 0 分硬算。
- 分数输出前必须过 `tools/redflag.py`：输出中出现输入对象之外的专有名词或数字 → 标红并阻断发布。
