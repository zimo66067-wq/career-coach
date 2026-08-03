# observability.md · 可观测性规范 (P2-03)

> 本文件定义 career-coach 项目的 trace_id 规范、节点耗时记录、错误分类体系、匿名摘要导出格式与禁止记录清单。
> 所有日志落盘前必须经过 `tools/log_sanitize.py` 脱敏处理。

---

## 1. trace_id 规范

### 1.1 格式定义

```
trace_id = cc-{YYYYMMDD}-{HHmmss}-{6位随机hex}
```

示例：`cc-20260801-183751-a3f9c2`

### 1.2 生成规则

- 在 WF-01（材料接收）入口生成，贯穿整个会话生命周期。
- 一用户一次完整会话（F1 → F2 → F3 → F4）共享同一 trace_id。
- 删除操作沿用同一 trace_id，后缀 `-del`。
- 降级操作沿用同一 trace_id，后缀 `-deg`。

### 1.3 传递规范

- trace_id 作为 DuMate 对话任务的全局变量传递。
- 每次工具调用（tools/*.py）的日志输出必须包含 trace_id。
- 日志格式：`[{timestamp}] [{trace_id}] [{wf_node}] [{level}] {message}`

### 1.4 trace_id 用途

- 异常追踪：通过 trace_id 关联一次会话中的所有操作。
- 性能分析：按 trace_id 聚合各节点耗时。
- 删除验证：通过 trace_id 确认删除后无模型调用。
- 日志脱敏后导出：按 trace_id 导出匿名摘要（见第 4 节）。

---

## 2. 节点耗时记录规范

### 2.1 记录格式

每个工作流节点执行时记录以下信息：

| 字段 | 类型 | 说明 | 示例 |
|---|---|---|---|
| trace_id | string | 会话追踪 ID | cc-20260801-183751-a3f9c2 |
| wf_node | string | 工作流节点标识 | WF-02-resume-diagnosis |
| node_step | string | 节点内步骤 | extract / deidentify / model_call / validate / rescore |
| start_time | ISO8601 | 步骤开始时间 | 2026-08-01T18:37:51+08:00 |
| end_time | ISO8601 | 步骤结束时间 | 2026-08-01T18:38:15+08:00 |
| duration_ms | integer | 耗时（毫秒） | 24000 |
| status | enum | success / degraded / error | success |
| model_used | string | 实际使用的模型（如涉及） | kimi-k3 |
| model_version | string | 模型版本 | 2026-07-31 |
| input_hash | string | 输入摘要 SHA256（非原文） | a1b2c3d4... |
| output_hash | string | 输出摘要 SHA256（非原文） | e5f6g7h8... |
| error_type | string | 错误类型（如 error） | model_timeout |
| fallback_triggered | boolean | 是否触发降级 | false |

### 2.2 关键节点耗时门限

| 节点 | 步骤 | 门限 (P95) | 备注 |
|---|---|---|---|
| WF-01 | extract_text | ≤5s | PDF/DOCX 解析 |
| WF-01 | deidentify | ≤2s | 去标识化 |
| WF-02 | model_call (诊断) | ≤30s | 模型推理 |
| WF-02 | validate_schema | ≤2s | Schema 校验 |
| WF-02 | redflag | ≤2s | 事实锁校验 |
| WF-02 | rescore (R) | ≤2s | 规则复算 |
| WF-03 | model_call (JD解析) | ≤15s | 模型推理 |
| WF-03 | match_requirements | ≤8s | 四态匹配 |
| WF-03 | rescore (M) | ≤2s | 规则复算 |
| WF-04 | model_call (首响应) | ≤8s | 首响应延迟 |
| WF-04 | validate_schema (每轮) | ≤2s | InterviewTurn 校验 |
| WF-05 | rescore (C0/C7) | ≤2s | 综合复算 |
| WF-05 | seven_day_plan | ≤20s | 七天计划生成 |
| WF-05 | radar_adapter | ≤2s | 雷达图 option |
| WF-06 | 降级切换 | ≤10s | 故障到降级完成 |

### 2.3 耗时记录输出

- 耗时记录写入 `/tmp/trace_{trace_id}.jsonl`（JSON Lines 格式）。
- 每行一条记录，按步骤顺序追加。
- 会话结束后可按 trace_id 查询完整耗时链路。
- 日志落盘前过 `tools/log_sanitize.py`。

---

## 3. 错误分类体系

### 3.1 错误等级

| 等级 | 定义 | 影响 | 处理方式 | 是否阻断 |
|---|---|---|---|---|
| E1-FATAL | 不可恢复的系统错误 | 整个会话不可用 | 显示「服务暂时不可用」+ 记录 trace_id | 是 |
| E2-BLOCK | 事实锁/Schema 校验阻断 | 当前节点不可用 | 切简化模式或阻断发布 | 是（当前节点） |
| E3-DEGRADE | 依赖故障可降级 | 当前功能降级 | 10 秒内切降级路径 | 否（降级继续） |
| E4-RETRY | 临时性错误可重试 | 延迟增加 | 重试一次后继续 | 否 |
| E5-WARN | 非阻断性警告 | 不影响功能 | 记录日志，继续执行 | 否 |

### 3.2 错误类型清单

| error_type | 等级 | 触发条件 | 降级路径 | 用户可见 |
|---|---|---|---|---|
| model_timeout | E3 | 模型响应超过门限 | 切 FALLBACK_MODEL | 「网络波动，已切换简化模式」 |
| model_error | E3 | 模型返回错误 | 重试一次 → 切降级 | 「处理异常，正在重试」 |
| model_non_json | E3 | 模型返回非 JSON | 提取 JSON 片段 → 降级 | 「格式异常，已切换简化模式」 |
| schema_validation_failed | E2 | validate_schema exit 1 | 降低 temperature 重试 → 简化模式 | 「诊断格式异常，已切换简化诊断」 |
| redflag_blocked | E2 | redflag.py exit 1 | 切简化模式并标注阻断 | 「检测结果存在可疑数据，已切换简化模式」 |
| embedding_unavailable | E3 | match_requirements exit 4 | 切 BM25 简化匹配 | 「已切换简化匹配模式」 |
| asr_failed | E3 | ASR 接口错误/超时 | 回退文字主链路 | 「语音不可用，请文字回答」 |
| tts_failed | E3 | TTS 接口错误/超时 | 降级文字提示 | 「语音播报不可用」 |
| echarts_failed | E3 | ECharts 加载失败 | 本地 vendor → 表格 | 表格替代雷达图 |
| pdf_parse_failed | E4 | extract_text exit 2 | 引导粘贴文本 | 「请另存为 TXT 或直接粘贴」 |
| network_error | E3 | 网络断开 | 保留已确认数据，提示重连 | 「网络已断开，数据已保存」 |
| delete_in_progress | E5 | 删除中触发新操作 | 拒绝新操作 | 「正在删除数据，请稍候」 |
| fatal_error | E1 | 不可恢复异常 | 记录 trace_id 并停止 | 「服务暂时不可用，请稍后重试」 |

### 3.3 错误处理原则

- 错误记录必须包含 trace_id + error_type + 发生节点 + 输入摘要哈希（非原文）。
- E2-BLOCK 类错误不得人工放行（redflag 阻断不可手动跳过）。
- E3-DEGRADE 类错误必须在 10 秒内切换降级路径。
- 降级后保留用户已确认的数据，不回退已通过的 WF 结果。
- 同一错误重试不超过一次；重试仍失败则走降级路径。

---

## 4. 匿名摘要导出格式

### 4.1 导出目的

用于答辩展示、性能分析、验收数据汇总，不含任何 PII。

### 4.2 导出格式

```json
{
  "export_date": "2026-08-01",
  "export_version": "1.0",
  "total_sessions": 10,
  "sessions": [
    {
      "trace_id": "cc-20260801-183751-a3f9c2",
      "date": "2026-08-01",
      "duration_total_ms": 180000,
      "wf_nodes": [
        {
          "node": "WF-02-resume-diagnosis",
          "duration_ms": 24000,
          "status": "success",
          "model_used": "kimi-k3",
          "fallback": false
        },
        {
          "node": "WF-03-jd-match",
          "duration_ms": 18000,
          "status": "degraded",
          "model_used": "bm25",
          "fallback": true,
          "fallback_reason": "embedding_unavailable"
        }
      ],
      "errors": [
        {
          "node": "WF-03-jd-match",
          "error_type": "embedding_unavailable",
          "level": "E3-DEGRADE",
          "recovered": true
        }
      ],
      "scores": {
        "R": 73.00,
        "M": 60.00,
        "I": 72.55,
        "C0": 68.27,
        "C7_low": 77.79,
        "C7_high": 90.48
      }
    }
  ],
  "statistics": {
    "avg_f1_duration_ms": 28000,
    "avg_f2_duration_ms": 20000,
    "avg_f3_first_response_ms": 6000,
    "avg_report_duration_ms": 25000,
    "degradation_rate": 0.1,
    "schema_pass_rate": 1.0,
    "redflag_block_rate": 0.0
  }
}
```

### 4.3 导出规则

- 导出文件不含姓名、电话、邮箱、身份证号、音频、完整简历。
- 分数保留两位小数（四舍五入）。
- 模型标识使用通用名称（kimi-k3 / bm25），不含 API Key 或密钥。
- 输入/输出只记录 SHA256 哈希前 8 位，不记录原文。
- 导出文件可保存到 `deliverables/` 目录用于答辩展示。

---

## 5. 禁止记录的内容清单

### 5.1 绝对禁止记录

| 禁止内容 | 原因 | 检查方式 |
|---|---|---|
| 用户真实姓名 | PII | log_sanitize.py 脱除为 [REDACTED_NAME] |
| 用户手机号 | PII | log_sanitize.py 脱除为 [REDACTED_PHONE] |
| 用户邮箱 | PII | log_sanitize.py 脱除为 [REDACTED_EMAIL] |
| 身份证号 | PII | log_sanitize.py 脱除为 [REDACTED_ID] |
| 简历原文（全文或片段） | 用户数据 | 只记录输入摘要哈希 |
| JD 原文（全文或片段） | 用户数据 | 只记录输入摘要哈希 |
| 面试回答原文 | 用户数据 | 只记录 answer_quote 子串校验结果 |
| 音频文件/音频数据 | 用户数据 | 不落盘，流式处理 |
| API Key / Secret Key | 密钥 | log_sanitize.py 脱除 token/AK-SK 模式 |
| Bearer Token | 密钥 | log_sanitize.py 脱除 |
| access_token | 密钥 | log_sanitize.py 脱除 |
| PII 映射表（deidentify --map） | PII | 默认不落盘 |

### 5.2 允许记录的内容

| 允许内容 | 格式 | 备注 |
|---|---|---|
| trace_id | 字符串 | 会话追踪 |
| 时间戳 | ISO8601 | 节点耗时分析 |
| 工作流节点标识 | 字符串 | 流程追踪 |
| 步骤名称 | 字符串 | 步骤级追踪 |
| 耗时（毫秒） | 整数 | 性能分析 |
| 状态（success/degraded/error） | 枚举 | 状态追踪 |
| 模型标识 | 字符串 | 模型选择记录 |
| 模型版本 | 字符串 | 版本追踪 |
| 输入摘要哈希（SHA256 前 8 位） | 字符串 | 非原文 |
| 输出摘要哈希（SHA256 前 8 位） | 字符串 | 非原文 |
| 错误类型 | 字符串 | 错误分类 |
| 降级触发标志 | 布尔 | 降级分析 |
| 分数（R/M/I/C0/C7） | 数值 | 验收数据 |
| 规则版本（scoring.md 版本） | 字符串 | 版本追踪 |

### 5.3 日志质量门

- 日志扫描不含姓名、电话、邮箱、身份证号、音频或完整简历。
- 日志扫描不含 API Key、Secret Key、Bearer Token、access_token。
- 日志落盘前必须经过 `tools/log_sanitize.py` 管道处理。
- 违反质量门的日志不得落盘，必须修复后重新输出。

### 5.4 日志保留与清理

- 脱敏后日志保留 7 天，到期自动清理。
- 匿名摘要导出文件可长期保留（用于答辩与验收）。
- 删除操作后，对应 trace_id 的日志同步清除。
