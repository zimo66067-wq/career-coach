# WF-04 · 面试状态机（F3 文字先行）

> DuMate 对话任务工作流 | 状态：JD_READY -> INTERVIEWING -> INTERVIEW_DONE | 功能：F3 AI模拟面试

## 1. 触发条件

WF-03 完成（JD_READY），ResumeProfile 和 JobProfile 均就绪，用户选择"开始模拟面试"。

## 2. 状态机

```
SETUP -> ASK -> ANSWER -> ASSESS -> FOLLOW_UP_OR_NEXT -> ... -> COMPLETE -> REPORT
                                                                    -> INTERVIEW_DONE
```

| 状态 | 含义 | 触发条件 | 用户可见 |
|------|------|----------|----------|
| SETUP | 初始化面试 | 用户选择"开始面试" | "面试即将开始，共5个主问题，每题最多1次追问。请用文字回答。" |
| ASK | 面试官提问 | 进入新主问题或追问 | 展示问题文本 |
| ANSWER | 等待用户回答 | 面试官提问后 | 等待用户输入 |
| ASSESS | 评估本轮回答 | 用户提交回答 | "正在评估你的回答..." |
| FOLLOW_UP_OR_NEXT | 决定追问或下一题 | 评估完成 | 展示反馈+追问 或 "进入下一题" |
| COMPLETE | 面试结束 | 5个主问题完成 | "面试结束，正在生成报告..." |
| REPORT | 生成复盘报告 | COMPLETE 后 | 展示 I 分、逐轮反馈、改进建议 |

### 追问决策规则

| 优先级 | 触发条件 | 追问内容 |
|--------|----------|----------|
| 1 | 回答与问题无关（relevance <30） | "请回到具体场景，谈谈你本人做了什么" |
| 2 | 缺少本人行动（missing action） | "你本人具体做了什么？用什么工具或方法？" |
| 3 | 缺少结果（missing result） | "结果如何？有没有可量化的指标？" |
| 4 | 涉及简历或JD缺口 | "你在简历中提到XX，能展开说说是怎么做的吗？" |
| 5 | 回答充分（missing_elements 为空） | 不追问，进入下一题 |

## 3. 工具调用链

### 3.1 每轮主路径

```
步骤1: 装配提示词
  系统提示 = prompts/interview/interviewer.md 中的 "## 系统提示" 部分
  上下文输入:
    ResumeProfile: {resume_profile_json}
    JobProfile: {job_profile_json}
    历史轮次: {previous_turns_json}
    本轮: question=..., answer={user_answer}

步骤2: 调用 DuMate 当前模型（优先低延迟模型），获取 InterviewTurn JSON
  - 包含 turn/question/targets/answer_text/answer_quote/missing_elements/
    follow_up/rubric_partial/asr_confidence(null)/safety_flags

步骤3: 写入 /tmp/interview_turn_{N}.json

步骤4: python tools/validate_schema.py \
    --schema contracts/interview-turn.schema.json \
    --instance /tmp/interview_turn_{N}.json
  - 业务规则校验：answer_quote 必须是 answer 的子串，否则该轮作废重评
  - exit 0 = VALID，继续
  - exit 1 = INVALID，重试一次（降低 temperature）

步骤5: python tools/redflag.py \
    --output /tmp/interview_turn_{N}.json \
    --against <resume_clean.txt> <jd_text.txt>
  - 检查模型输出中是否有语料外数字
  - exit 0 = 通过
  - exit 1 = block_release，该轮重评

步骤6: 检查 safety_flags
  - 非空表示检测到敏感信息，展示警告但不阻断
  - 敏感问题清单（婚育/年龄/籍贯/薪资底线/性别相关等）全部阻断提问
```

### 3.2 面试结束路径

```
步骤7: 5个主问题完成后，进入 COMPLETE 状态

步骤8: 规则引擎按 scoring.md 公式计算 I 分
  I = 结构性*25% + 岗位相关性*25% + 具体性*20% + 追问适应性*15% + 表达清晰度*15%
  从每轮 InterviewTurn.rubric_partial 读取五维子分
  所有轮次的子分取平均值，加权计算 I

步骤9: 装配复盘报告
  系统提示 = prompts/interview/review.md 中的 "## 系统提示" 部分
  用户输入:
    InterviewTurn 序列: {turns_json}
    I 分与子分: {score_I_json}
  调用模型生成 Markdown 复盘报告
```

### 3.3 语音增强链（F3 文字版稳定后接入）

```
按键说话 -> 百度 ASR -> 转写文本
  ├─ asr_confidence >= 0.75 -> 文本直接进入 ANSWER 状态
  └─ asr_confidence < 0.75 -> 展示转写文本，请求用户确认/编辑
      └─ 用户确认后 -> 确认文本进入 ANSWER 状态
```

### 3.4 备用路径

| 故障 | 检测方式 | 降级动作 |
|------|----------|----------|
| Schema 校验失败 | validate_schema.py exit 1 | 降低 temperature 重试一次；仍失败则该轮用模板评估 |
| answer_quote 非子串 | validate_schema 业务规则 | 该轮作废，重新评估 |
| 事实锁阻断 | redflag.py exit 1 | 该轮重评；仍阻断则用模板评估 |
| 模型超时（>8s 首响应） | DuMate 计时 | 切固定题库顺序提问，追问降级为模板"请补充结果数据" |
| 语音 ASR 故障 | ASR 返回错误或超时 | 10秒内回退文字输入，展示"语音不可用，请文字回答" |
| ASR 置信度低 | asr_confidence < 0.75 | 100%触发用户确认或文字编辑 |
| 敏感问题 | safety_flags 非空或敏感词检测 | 阻断提问，礼貌转向岗位相关话题 |

## 4. DuMate 对话任务编排

```
[WF-03 完成，ResumeProfile + JobProfile 就绪]
  │
  ├─ 用户选择"开始模拟面试" -> SETUP
  │   ├─ 从 JobProfile 中选取 importance 最高的 5 个要求作为 targets
  │   ├─ 题目类型轮换：成果证据/协作冲突/学习适配/岗位深度/情景压力
  │   └─ 进入第1轮 ASK
  │
  ├─ 每轮循环（最多5主问题 + 最多5追问 = 最多10轮）:
  │   ├─ ASK: 面试官提问（绑定 targets）
  │   ├─ ANSWER: 等待用户回答（文字或语音转写）
  │   ├─ ASSESS: 装配 interviewer.md -> 模型输出 InterviewTurn JSON
  │   │   ├─ validate_schema（answer_quote 子串校验）
  │   │   ├─ redflag 事实锁
  │   │   └─ safety_flags 检查
  │   ├─ FOLLOW_UP_OR_NEXT:
  │   │   ├─ missing_elements 非空且追问次数 <1 -> 追问（回到 ASK）
  │   │   └─ missing_elements 为空 或 已追问1次 -> 下一主问题
  │   └─ 5主问题完成 -> COMPLETE
  │
  ├─ COMPLETE: 规则引擎计算 I 分
  │   ├─ 五维子分 = 所有轮次 rubric_partial 的平均值
  │   └─ I = 加权计算
  │
  └─ REPORT: 装配 review.md -> 生成复盘报告
      ├─ 总体表现（I 分五维子分强弱分布）
      ├─ 逐轮复盘（题目/亮点/缺口/追问应对）
      ├─ 高频问题预备（3个）
      └─ 与七天计划的衔接
```

## 5. 变量绑定

| 变量名 | 来源 | 用途 |
|--------|------|------|
| `resume_profile_json` | WF-02 | 提示词上下文 |
| `job_profile_json` | WF-03 | targets 选取 |
| `previous_turns_json` | 累积的 InterviewTurn 列表 | 每轮上下文 |
| `current_question` | 模型生成或固定题库 | 展示给用户 |
| `user_answer` | 用户输入或 ASR 转写 | 评估输入 |
| `interview_turns[]` | 每轮 InterviewTurn JSON | 累积序列 |
| `I_score` | 规则引擎计算 | 写入 AbilityProfile.interview_score |
| `asr_confidence` | 百度 ASR（语音模式） | 置信度检查 |
| `trace_id` | WF-01 传递 | 全链路追踪 |

## 6. 退出标准（验收门）

| 验收项 | 标准 | 验证方式 |
|--------|------|----------|
| 轮数控制 | <=5 主问题，每题 <=1 追问 | 检查 turn 序列 |
| 问题绑定 | 首问均绑定已确认 JD 要求 | 检查 targets 字段 |
| 追问质量 | 追问引用上一轮回答短句或指出 STAR 缺失 | 检查 answer_quote + follow_up |
| answer_quote | 必须是 answer 的子串 | validate_schema 业务规则 |
| 敏感问题阻断 | 20条敏感问题测试全部阻断 | 敏感问题测试集 |
| ASR 降级 | asr_confidence <0.75 时 100%触发确认 | 语音测试 |
| 首响应时延 | P95 <= 8s | DuMate 计时 |
| 报告时延 | 最终报告 P95 <= 30s | DuMate 计时 |
| 会话完成率 | 10次五轮会话 >=9 次正常完成 | 批量测试 |
| I 分规则 | I 由规则引擎计算，非模型自报 | 检查模型输出不含 I 字段 |

## 7. 验收命令

```bash
# InterviewTurn Schema 校验
python tools/validate_schema.py \
  --schema contracts/interview-turn.schema.json \
  --instance tests/fixtures-synthetic/interviews/interview-01.json

# answer_quote 子串校验（故障注入测试）
python -m pytest tests/test_fault_injection.py::test_answer_quote_not_substring_rejected -v

# 敏感问题阻断测试
python -m pytest tests/test_fault_injection.py -v

# 现有契约测试
python -m pytest tests/test_contracts.py::test_interview_turns_valid -v
```

## 8. 禁止事项

- 禁止超过 5 个主问题
- 禁止每题超过 1 次追问
- 禁止重复问题
- 禁止一次问多个问题
- 禁止询问婚育、籍贯、疾病、宗教、家庭资产等敏感内容
- 禁止视频表情识别、数字人、全双工实时语音、多面试官群聊
- 禁止模型自报总分 I
- 禁止 answer_quote 非子串时通过校验
- 日志落盘前必须过 log_sanitize.py

## 可执行合同（P0-01 更新）

### 输入合同
- 输入格式: `resume_profile_json`（WF-02）+ `job_profile_json`（WF-03）+ 用户文字回答（每轮）
- 必填字段: `resume_profile_json` 已校验、`job_profile_json` 已校验且 `user_confirmed=true`、`user_answer` 非空
- 校验: WF-02/WF-03 退出标准全部满足

### 输出合同
- 输出格式: InterviewTurn JSON 序列（符合 `contracts/interview-turn.schema.json`）+ 复盘报告 Markdown
- 必填字段: 每轮含 `turn`/`question`/`targets`/`answer_text`/`answer_quote`/`missing_elements`/`follow_up`/`rubric_partial`/`safety_flags`；`answer_quote` 必须是 `answer_text` 的子串
- 校验: `validate_schema.py --schema contracts/interview-turn.schema.json` + `redflag.py --against <resume_clean.txt> <jd_text.txt>`

### 工具调用链
1. 从 JobProfile 选取 importance 最高的 5 个要求作为 targets
2. 装配 `prompts/interview/interviewer.md` + ResumeProfile + JobProfile + 历史轮次 + 本轮问答
3. 调用模型（`interview_question` 路由），获取 InterviewTurn JSON
4. `python tools/validate_schema.py --schema contracts/interview-turn.schema.json --instance /tmp/interview_turn_{N}.json`
5. `python tools/redflag.py --output /tmp/interview_turn_{N}.json --against <resume_clean.txt> <jd_text.txt>`
6. 检查 `safety_flags`（非空展示警告，敏感问题阻断提问）
7. 循环步骤 2-6（最多 5 主问题 + 最多 5 追问 = 最多 10 轮）
8. 5 主问题完成后规则引擎计算 I 分（`I = 结构*25% + 相关*25% + 具体*20% + 追问*15% + 表达*15%`）
9. 装配 `prompts/interview/review.md` 生成复盘报告

### 状态转换
- 初始态: SETUP
- 成功态: INTERVIEW_DONE
- 降级态: 模板评估（Schema/redflag 连续失败 -> 模板 rubric）、固定题库（超时 -> 顺序提问）
- 错误态: 该轮作废重评（answer_quote 非子串）、敏感问题阻断
- 删除态: DELETED

### 降级路径
| 主路径失败原因 | 降级方案 | 标记 |
|---|---|---|
| Schema 校验失败 | 降低 temperature 重试一次；仍失败用模板评估 | degraded=true |
| answer_quote 非子串 | 该轮作废，重新评估 | degraded=false（重试中） |
| 事实锁阻断 | 该轮重评；仍阻断用模板评估 | degraded=true |
| 模型超时（>8s 首响应） | 切固定题库顺序提问，追问降级为模板 | degraded=true |
| 语音 ASR 故障 | 10s 内回退文字输入 | degraded=true |
| ASR 置信度低（<0.75） | 100% 触发用户确认或文字编辑 | degraded=false（交互确认） |
| 敏感问题 | 阻断提问，转向岗位相关话题 | degraded=false（安全阻断） |

### 模型路由
- 任务类型: `interview_question`（每轮评估）+ `interview_review`（复盘报告）
- 参数: temperature=0.4, max_tokens=1024, timeout=15s（每轮）；temperature=0.3, max_tokens=4096, timeout=30s（复盘）
- 降级: `DEGRADED_OUTPUTS["interview_question"]`（题库 fallback，generic_behavioral）；`DEGRADED_OUTPUTS["interview_review"]`（骨架报告）

### 验收命令
```bash
python tools/validate_schema.py \
  --schema contracts/interview-turn.schema.json \
  --instance tests/fixtures-synthetic/interviews/interview-01.json
python -m pytest tests/test_fault_injection.py::test_answer_quote_not_substring_rejected -v
python -m pytest tests/test_fault_injection.py -v
python -m pytest tests/test_contracts.py::test_interview_turns_valid -v
```

### 禁止事项
- [X] 禁止模型自报总分
- [X] 禁止跳过 deidentify（WF-01 前置保证）
- [X] 禁止超过 5 个主问题
- [X] 禁止每题超过 1 次追问
- [X] 禁止询问婚育/籍贯/疾病/宗教/家庭资产等敏感内容
- [X] 禁止 answer_quote 非子串时通过校验
- [X] 禁止 DELETED 状态下调用模型
