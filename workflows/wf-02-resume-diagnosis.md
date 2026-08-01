# WF-02 · 简历诊断（F1）

> DuMate 对话任务工作流 | 状态：RESUME_READY -> DIAGNOSED | 功能：F1 简历AI诊断

## 1. 触发条件

WF-01 输出 `resume_clean_text`（已脱敏、`pii_removed:true`），状态为 `RESUME_READY`。

## 2. 状态转换

```
RESUME_READY -> DIAGNOSING -> VALIDATING -> SCORING -> DIAGNOSED
                                         -> REDFLAG_BLOCKED (降级)
                                         -> SCHEMA_FAILED (重试/降级)
                                         -> TIMEOUT (降级)
```

| 状态 | 含义 | 用户可见 |
|------|------|----------|
| RESUME_READY | 等待开始诊断 | "简历已就绪，开始诊断..." |
| DIAGNOSING | 模型正在抽取 ResumeProfile | "正在分析简历结构和成果证据..." |
| VALIDATING | 正在校验 JSON + 事实锁 | "正在校验诊断结果..." |
| SCORING | 规则引擎计算 R 分 | "正在计算诊断分数..." |
| DIAGNOSED | 诊断完成 | 展示总分R、五维子分、逐条建议、深度报告入口 |
| SCHEMA_FAILED | 模型输出校验失败 | "诊断结果格式异常，正在重试..." |
| REDFLAG_BLOCKED | 事实锁阻断 | "诊断结果存在可疑数据，已切换为简化诊断" |
| TIMEOUT | 模型超时（>45s） | "处理时间较长，请稍后查看结果" |

## 3. 工具调用链

### 3.1 主路径

```
步骤1: 装配提示词
  系统提示 = prompts/resume/diagnose.md 中的 "## 系统提示" 部分
  用户输入 = resume_clean_text（WF-01 输出）
  将系统提示中的 {deidentified_resume_text} 替换为 resume_clean_text

步骤2: 调用 DuMate 当前模型，获取 ResumeProfile JSON
  - 要求模型只输出 JSON，不输出 markdown 代码块标记
  - 记录 trace_id、模型名、模型版本

步骤3: 将模型输出写入 /tmp/resume_profile.json

步骤4: python tools/validate_schema.py \
    --schema contracts/resume-profile.schema.json \
    --instance /tmp/resume_profile.json
  - 退出码 0 = VALID，继续
  - 退出码 1 = INVALID，进入 SCHEMA_FAILED

步骤5: python tools/redflag.py \
    --output /tmp/resume_profile.json \
    --against <resume_clean_text 文件路径>
  - 退出码 0 = 通过，继续
  - 退出码 1 = block_release:true，进入 REDFLAG_BLOCKED

步骤6: 规则引擎按 scoring.md 公式计算 R 分
  R = 结构完整度*15% + 表达清晰度*20% + 成果证据*25% + 技能证据*20% + ATS可读性*20%
  从 ResumeProfile.subscores 读取五项子分，加权计算
  模型不得自报总分，总分只由规则引擎计算

步骤7: （可选）装配深度报告
  系统提示 = prompts/resume/report-deep.md 中的 "## 系统提示" 部分
  用户输入 = ResumeProfile JSON + resume_clean_text
  调用模型生成 Markdown 深度报告
```

### 3.2 备用路径

| 故障 | 检测方式 | 降级动作 |
|------|----------|----------|
| Schema 校验失败（第一次） | validate_schema.py exit 1 | 降低 temperature 重试一次（步骤2-4） |
| Schema 校验失败（第二次） | 重试后仍 exit 1 | 降级为规则静态结构检查（标注"简化诊断"），输出包含：段落数、技能数、量化成果比例、ATS可读性指标 |
| 事实锁阻断 | redflag.py exit 1 | 降级为"简化诊断"并标注"事实锁阻断"，展示 redflag 报告中的 red 项 |
| 模型超时（>45s） | DuMate 计时 | 提示"处理时间较长"，不展示未校验结果；允许用户稍后查看 |
| 模型返回非 JSON | 解析失败 | 尝试从响应中提取 JSON 片段；仍失败则走 Schema 失败降级 |

## 4. DuMate 对话任务编排

```
[WF-01 完成，resume_clean_text 就绪]
  │
  ├─ 装配 diagnose.md 提示词 + resume_clean_text
  │
  ├─ 调用模型 -> 获取 JSON 输出
  │   ├─ 写入 /tmp/resume_profile.json
  │   │
  │   ├─ validate_schema.py 校验
  │   │   ├─ VALID -> redflag.py 事实锁
  │   │   │   ├─ 通过 -> 规则算 R -> DIAGNOSED
  │   │   │   └─ 阻断 -> 降级"简化诊断" + 标注
  │   │   └─ INVALID -> 重试一次
  │   │       ├─ VALID -> 继续
  │   │       └─ 仍 INVALID -> 降级"简化诊断"
  │   │
  │   └─ 超时 -> 提示稍后查看
  │
  └─ DIAGNOSED 后展示:
      - 总分 R（规则引擎计算）
      - 五维子分（结构/表达/成果/技能/ATS）
      - 逐条建议（每条含原文证据、问题、改写草案、待确认问题）
      - 深度报告入口（report-deep.md 生成）
```

## 5. 变量绑定

| 变量名 | 来源 | 用途 |
|--------|------|------|
| `resume_clean_text` | WF-01 | 模型输入 + redflag --against |
| `resume_profile_json` | 模型输出 | 校验 + 规则算分 + WF-03/WF-05 输入 |
| `R_score` | 规则引擎计算 | 写入 AbilityProfile.resume_score |
| `R_subscores` | ResumeProfile.subscores | 五维子分展示 |
| `suggestions` | ResumeProfile.suggestions | 逐条建议展示 |
| `trace_id` | WF-01 传递 | 全链路追踪 |
| `model_name` | DuMate 记录 | 日志 |
| `model_version` | DuMate 记录 | 日志 |

## 6. 退出标准（验收门）

| 验收项 | 标准 | 验证方式 |
|--------|------|----------|
| JSON 校验 | ResumeProfile 过 validate_schema.py | exit 0 |
| 事实锁 | redflag.py 无阻断 | exit 0，block_release=false |
| 证据覆盖 | 每条建议 >=1 个 source_span | 检查 suggestions[].source_spans |
| 总分规则 | R 由规则引擎计算，非模型自报 | 检查模型输出不含 R 字段 |
| 子分范围 | 五项子分均 0-100 | validate_schema 业务规则 |
| 稳定性 | 同一输入连续三次总分差 <=5 | 三次调用比对 |
| 时延 | P95 <= 45s | DuMate 计时 |
| 抽取成功率 | 20份测试简历 >=19 份完成抽取 | 批量测试 |

## 7. 验收命令

```bash
# Schema 校验（用合成 fixture）
python tools/validate_schema.py \
  --schema contracts/resume-profile.schema.json \
  --instance tests/fixtures-synthetic/resumes/resume-01-swe.expected.json

# 事实锁校验
python tools/redflag.py \
  --output tests/fixtures-synthetic/resumes/resume-01-swe.expected.json \
  --against tests/fixtures-synthetic/resumes/resume-01-swe.txt

# 现有测试
python -m pytest tests/test_contracts.py tests/test_fault_injection.py -v
```

## 8. 禁止事项

- 禁止模型自报总分 R
- 禁止无证据打分（必须标 unknown）
- 禁止跳过 validate_schema 或 redflag 直接展示
- 禁止展示未校验的模型输出
- 禁止编造用户简历中不存在的事实
- 禁止评价与求职无关的个人特征
- 日志落盘前必须过 log_sanitize.py
