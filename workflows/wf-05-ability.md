# WF-05 · 能力聚合与七天计划（F4）

> DuMate 对话任务工作流 | 状态：INTERVIEW_DONE -> REPORT_READY | 功能：F4 六维雷达与七天提升计划

## 1. 触发条件

WF-04 完成（INTERVIEW_DONE），R、M、I 三个分数及其证据全部就绪。若 F3 未完成（用户中途退出），不生成综合竞争力分 C0，只显示 F1 和 F2 阶段结果。

## 2. 状态转换

```
INTERVIEW_DONE -> AGGREGATING -> RESCORING -> DIMENSION_MAPPING -> PLAN_GENERATING -> VALIDATING -> REPORT_READY
                                                                                              -> PLAN_FAILED (降级)
                                                                                              -> RESCORE_MISMATCH (排查)
```

| 状态 | 含义 | 用户可见 |
|------|------|----------|
| AGGREGATING | 收集 R/M/I 及证据 | "正在聚合诊断数据..." |
| RESCORING | 规则引擎复算 C0 | "正在计算综合基线..." |
| DIMENSION_MAPPING | 六维能力映射 | "正在生成能力雷达..." |
| PLAN_GENERATING | 模型生成七天计划 | "正在生成七天提升计划..." |
| VALIDATING | 校验计划 + 雷达 | "正在校验结果..." |
| REPORT_READY | 报告就绪 | 展示雷达图、基线C0、情景区间、七天计划 |
| PLAN_FAILED | 计划校验失败 | 降级为模板计划，标注"模板计划" |
| RESCORE_MISMATCH | 复算不一致 | 阻断，提示排查语义层 |

## 3. 工具调用链

### 3.1 聚合与复算

```
步骤1: 收集输入
  R = WF-02 的 resume_score + ResumeProfile.subscores
  M = WF-03 的 match_score + match_result.json（四态明细）
  I = WF-04 的 interview_score + 所有 InterviewTurn.rubric_partial

步骤2: 构造 score-input JSON
  {
    "R": { 五个子分 },
    "M": { requirements: [{type, status}, ...] },
    "I": { 五个子分 }
  }

步骤3: python tools/rescore.py \
    --input /tmp/score-input.json \
    --expect C0=<预期值>
  - 复算 R/M/I/C0/C7_low/C7_high
  - 对拍容差 ±0.5
  - exit 0 = PASS，继续
  - exit 1 = 超差，进入 RESCORE_MISMATCH
  - exit 3 = 证据不足（全 unknown），不生成 C0
```

### 3.2 六维映射

```
步骤4: 将 R/M/I 子分映射为六维能力
  | 维度 | 数据来源 | 计算方式 |
  |------|----------|----------|
  | 岗位契合 | F2 (M) | M 各类别加权后的总分 |
  | 成果证据 | F1 (R) | R.achievement_evidence 子分 |
  | 专业表达 | F1+F3 | (R.clarity + I.clarity) / 2 |
  | 结构化回答 | F3 (I) | I.structure 子分 |
  | 岗位深度 | F2+F3 | (M.responsibility 得分 + I.relevance) / 2 |
  | 追问适应 | F3 (I) | I.followup_adaptation 子分 |

  每个维度的 sources 必须指向实际存在的对象ID（sections.id / requirements.id / turn）

步骤5: 构造 AbilityProfile JSON
  {
    "resume_score": R,
    "match_score": M,
    "interview_score": I,
    "dimensions": [6个维度对象],
    "baseline": C0,
    "scenario_day7": {
      "low": C7_low,
      "high": C7_high,
      "assumptions": [
        "0.30 为 MVP 演示假设，不是统计学习参数",
        "0.70 为 MVP 演示假设，不是统计学习参数",
        "若完成任务且质量达到要求",
        "第七天复测才是真实变化"
      ]
    },
    "plan": [待步骤6生成]
  }
```

### 3.3 七天计划生成

```
步骤6: 装配提示词
  系统提示 = prompts/plan/seven-day.md 中的 "## 系统提示" 部分
  用户输入:
    缺口清单: {gaps_json}        # P0/P1/P2 分级（来自 WF-03 缺口清单 + WF-04 missing_elements 汇总）
    STAR 缺失汇总: {missing_json}  # 来自 WF-04 所有轮次的 missing_elements
    unknown 待确认项: {unknowns_json}  # 来自 WF-03 四态中的 unknown 条目

步骤7: 调用模型生成 plan JSON 数组（7条）
  - 每条含 day/minutes/action/artifact/mapped_gap
  - day 1-7 不重复
  - minutes 30-45
  - artifact 必填
  - mapped_gap 指向 requirements.id 或 sections.id

步骤8: 将 plan 写入 AbilityProfile.plan

步骤9: python tools/validate_schema.py \
    --schema contracts/ability-profile.schema.json \
    --instance /tmp/ability_profile.json
  - exit 0 = VALID
  - exit 1 = INVALID（plan 条数/时长/artifact 缺失等）

步骤10: python tools/redflag.py \
    --output /tmp/ability_profile.json \
    --against <resume_profile.json> <job_profile.json> <interview_turn_1.json> ... <interview_turn_N.json> contracts/scoring.md
  - --against 必须包含全部上游合同 JSON + scoring.md
  - 派生数字（如 M 子类别得分、I 子分均值）需能在上游合同或 scoring.md 中回指
  - exit 0 = 通过
  - exit 1 = 阻断
```

### 3.4 雷达图生成

```
步骤11: python tools/radar_adapter.py \
    --input /tmp/ability_profile.json \
    --output /tmp/radar_option.json
  - 输出 ECharts option（6 indicator, max=100, 3 series）
  - series: C0基线 + 七天推演low + 七天推演high
  - 直接被 ui/prototype/js/radar.js 消费
```

### 3.5 备用路径

| 故障 | 检测方式 | 降级动作 |
|------|----------|----------|
| 复算超差（>0.5） | rescore.py exit 1 | 阻断，排查语义层（检查模型输出子分是否合理） |
| 全 unknown | rescore.py exit 3 | 不生成 C0，只显示 F1/F2 阶段结果，缺失维度显式展示 |
| 计划校验失败（第一次） | validate_schema exit 1 | 降低 temperature 重试一次 |
| 计划校验失败（第二次） | 仍 exit 1 | 使用模板计划（七天计划模板，标注"模板计划"） |
| 事实锁阻断 | redflag.py exit 1 | 阻断，检查幻觉数字来源 |
| 雷达图渲染失败 | radar_adapter.py 异常或前端渲染失败 | 10秒内降级为六维表格展示 |
| 模型超时（>30s） | DuMate 计时 | 提示"报告生成中"，不展示未校验结果 |

## 4. DuMate 对话任务编排

```
[WF-04 完成，R/M/I 及证据就绪]
  │
  ├─ AGGREGATING: 收集 R/M/I + 子分 + 证据
  │
  ├─ RESCORING: rescore.py 复算
  │   ├─ PASS -> 继续
  │   ├─ 超差 -> 阻断，排查
  │   └─ 证据不足 -> 不生成 C0，只显示 F1/F2
  │
  ├─ DIMENSION_MAPPING: 六维能力映射
  │   ├─ 每个维度 score 0-100 整数
  │   └─ sources 指向真实对象ID
  │
  ├─ PLAN_GENERATING: 装配 seven-day.md -> 模型生成计划
  │   ├─ VALIDATING: validate_schema + redflag
  │   │   ├─ 通过 -> 继续
  │   │   ├─ 失败(1次) -> 重试
  │   │   └─ 失败(2次) -> 模板计划
  │   └─ 雷达图: radar_adapter.py -> ECharts option
  │       └─ 失败 -> 表格降级
  │
  └─ REPORT_READY 后展示:
      - 六维雷达图（C0基线 + 七天推演 low/high）
      - 综合基线 C0 = 0.25R + 0.35M + 0.40I
      - 七天情景区间 C7_low ~ C7_high（标注"非录用概率、非真实预测"）
      - 七天行动计划（每天 action + artifact + mapped_gap）
      - 情景假设列表（0.30/0.70 演示假设声明）
```

## 5. 变量绑定

| 变量名 | 来源 | 用途 |
|--------|------|------|
| `R_score` | WF-02 规则引擎 | AbilityProfile.resume_score |
| `M_score` | WF-03 规则引擎 | AbilityProfile.match_score |
| `I_score` | WF-04 规则引擎 | AbilityProfile.interview_score |
| `R_subscores` | ResumeProfile.subscores | 六维映射 |
| `M_categories` | match_result.json | 六维映射 |
| `I_subscores` | InterviewTurn.rubric_partial 均值 | 六维映射 |
| `C0` | rescore.py 复算 | AbilityProfile.baseline |
| `C7_low/C7_high` | rescore.py 复算 | AbilityProfile.scenario_day7 |
| `gaps_json` | WF-03 缺口清单 + WF-04 missing_elements | 七天计划输入 |
| `ability_profile_json` | 聚合构造 | 校验 + 雷达图 |
| `radar_option_json` | radar_adapter.py 输出 | 前端 ECharts |
| `trace_id` | WF-01 传递 | 全链路追踪 |

## 6. 退出标准（验收门）

| 验收项 | 标准 | 验证方式 |
|--------|------|----------|
| 复算对齐 | rescore.py 对拍 diff <=0.5 | rescore.py --expect |
| 六维可追溯 | 六个维度 100% 可追溯到 F1-F3 分项 | 检查 dimensions[].sources |
| plan 完整性 | 恰好7条，day 1-7不重复，30-45分钟，含artifact | validate_schema 业务规则 |
| 情景声明 | 标注"非录用概率、非真实预测" | 检查 assumptions |
| 假设标注 | 0.30/0.70 标注为"MVP演示假设" | 检查 assumptions |
| 确定性 | 同一输入同一规则版本得到相同基线和区间 | 两次复算比对 |
| 雷达图 | 6 indicator, max=100, 3 series | radar_adapter.py 输出 |
| 报告时延 | P95 <= 30s | DuMate 计时 |
| 图表降级 | 雷达失败时10秒内显示等价表格 | 模拟故障 |
| 事实锁 | redflag 无阻断 | exit 0 |

## 7. 验收命令

```bash
# 分数复算对拍
python tools/rescore.py \
  --input tests/fixtures-synthetic/abilities/score-input-01.json \
  --expect C0=68.27

# AbilityProfile Schema 校验
python tools/validate_schema.py \
  --schema contracts/ability-profile.schema.json \
  --instance tests/fixtures-synthetic/abilities/ability-01.json

# 雷达图生成
python tools/radar_adapter.py \
  --input tests/fixtures-synthetic/abilities/ability-01.json \
  --output /tmp/wf05_radar.json

# 事实锁校验（--against 必须包含全部上游合同 + scoring.md）
python tools/redflag.py \
  --output tests/fixtures-synthetic/abilities/ability-01.json \
  --against tests/fixtures-synthetic/resumes/resume-01-swe.expected.json \
            tests/fixtures-synthetic/jobs/job-01-swe.expected.json \
            tests/fixtures-synthetic/interviews/interview-01.json \
            contracts/scoring.md

# 现有测试
python -m pytest tests/test_rescore.py tests/test_fault_injection.py -v
```

## 8. 禁止事项

- 禁止使用"预测"一词（统一口径"七天竞争力情景推演"）
- 禁止编造未在输入中的能力证据
- 禁止模型自报 C0 或 C7
- 禁止 plan 不是恰好7条
- 禁止 day 重复或 minutes 越界
- 禁止 artifact 为空
- 禁止不标注 0.30/0.70 演示假设
- 禁止不标注"非录用概率、非真实预测"
- 禁止雷达图失败时不降级表格
- 日志落盘前必须过 log_sanitize.py

## 可执行合同（P0-01 更新）

### 输入合同
- 输入格式: JSON（`score-input.json`，含 R/M/I 子分与匹配明细）+ 全部上游合同 JSON
- 必填字段: `R`（五个子分）、`M`（requirements 四态明细）、`I`（五个子分）；上游 JSON: ResumeProfile + JobProfile + InterviewTurn 序列 + `contracts/scoring.md`
- 校验: `rescore.py --input <score-input.json> --expect C0=<预期值>`（对拍容差 ±0.5）

### 输出合同
- 输出格式: JSON（符合 `contracts/ability-profile.schema.json`）+ ECharts option JSON
- 必填字段: `resume_score`/`match_score`/`interview_score`/`dimensions[]`（6 维，每维含 score + sources）/`baseline`(C0)/`scenario_day7`/`plan[]`（恰好 7 条）
- 校验: `validate_schema.py --schema contracts/ability-profile.schema.json` + `redflag.py --against <全部上游合同 JSON + scoring.md>`

### 工具调用链
1. 收集 R/M/I 子分及证据，构造 `score-input.json`
2. `python tools/rescore.py --input /tmp/score-input.json --expect C0=<预期值>`
3. 六维能力映射（R/M/I 子分 -> 6 个维度，sources 指向真实对象 ID）
4. 装配 `prompts/plan/seven-day.md` + 缺口清单 + STAR 缺失 + unknown 待确认项
5. 调用模型（`seven_day_plan` 路由），生成 plan JSON 数组（7 条）
6. `python tools/validate_schema.py --schema contracts/ability-profile.schema.json --instance /tmp/ability_profile.json`
7. `python tools/redflag.py --output /tmp/ability_profile.json --against <全部上游合同 + scoring.md>`
8. `python tools/radar_adapter.py --input /tmp/ability_profile.json --output /tmp/radar_option.json`

### 状态转换
- 初始态: INTERVIEW_DONE
- 成功态: REPORT_READY
- 降级态: PLAN_FAILED（计划校验失败 -> 模板计划）、全 unknown（不生成 C0，只显示 F1/F2）
- 错误态: RESCORE_MISMATCH（复算超差 -> 阻断排查）、TIMEOUT（>30s）
- 删除态: DELETED

### 降级路径
| 主路径失败原因 | 降级方案 | 标记 |
|---|---|---|
| 复算超差（>0.5） | 阻断，排查语义层 | degraded=false（硬阻断） |
| 全 unknown（证据不足） | 不生成 C0，只显示 F1/F2 阶段结果 | degraded=true |
| 计划校验失败（第一次） | 降低 temperature 重试一次 | degraded=false（重试中） |
| 计划校验失败（第二次） | 使用模板计划（7 天模板，标注"模板计划"） | degraded=true |
| 事实锁阻断 | 阻断，检查幻觉数字来源 | degraded=false（硬阻断） |
| 雷达图渲染失败 | 10s 内降级为六维表格展示 | degraded=true |
| 模型超时（>30s） | 提示报告生成中，不展示未校验结果 | degraded=false（待重试） |

### 模型路由
- 任务类型: `seven_day_plan`（七天计划生成）
- 参数: temperature=0.2, max_tokens=2048, timeout=20s
- 降级: `DEGRADED_OUTPUTS["seven_day_plan"]`（7 条占位计划，title/artifact 均为 TBD，标注 `degraded=true`）

### 验收命令
```bash
python tools/rescore.py \
  --input tests/fixtures-synthetic/abilities/score-input-01.json --expect C0=68.27
python tools/validate_schema.py \
  --schema contracts/ability-profile.schema.json \
  --instance tests/fixtures-synthetic/abilities/ability-01.json
python tools/radar_adapter.py \
  --input tests/fixtures-synthetic/abilities/ability-01.json --output /tmp/wf05_radar.json
python tools/redflag.py \
  --output tests/fixtures-synthetic/abilities/ability-01.json \
  --against tests/fixtures-synthetic/resumes/resume-01-swe.expected.json \
            tests/fixtures-synthetic/jobs/job-01-swe.expected.json \
            tests/fixtures-synthetic/interviews/interview-01.json \
            contracts/scoring.md
python -m pytest tests/test_rescore.py tests/test_fault_injection.py -v
```

### 禁止事项
- [X] 禁止模型自报总分
- [X] 禁止跳过 deidentify（WF-01 前置保证）
- [X] 禁止使用"预测"一词（统一口径"七天竞争力情景推演"）
- [X] 禁止模型自报 C0 或 C7
- [X] 禁止 plan 不是恰好 7 条
- [X] 禁止不标注 0.30/0.70 演示假设
- [X] 禁止不标注"非录用概率、非真实预测"
- [X] 禁止雷达图失败时不降级表格
- [X] 禁止 DELETED 状态下调用模型
