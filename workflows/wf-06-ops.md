# WF-06 · 异常处理与数据删除

> DuMate 对话任务工作流 | 状态：任意 -> 降级态 / DELETED | 覆盖：全部 WF 的异常与安全

## 1. 触发条件

任意工作流（WF-01~05）发生异常、依赖故障、用户请求删除数据或用户主动退出。

## 2. 状态转换

```
任意状态 -> ERROR_DETECTED -> DEGRADING -> DEGRADED (继续服务)
                                   -> FATAL_ERROR (不可恢复)
任意状态 -> DELETE_REQUESTED -> DELETING -> DELETED (终态)
```

| 状态 | 含义 | 用户可见 |
|------|------|----------|
| ERROR_DETECTED | 检测到异常 | 对应功能的降级横幅 |
| DEGRADING | 正在切换降级路径 | "正在切换备用方案..." |
| DEGRADED | 已降级，继续服务 | 降级横幅 + "部分功能受限" |
| FATAL_ERROR | 不可恢复 | "服务暂时不可用，请稍后重试" |
| DELETE_REQUESTED | 用户请求删除 | "确认删除所有数据？" |
| DELETING | 正在删除 | "正在清除数据..." |
| DELETED | 删除完成（终态） | "数据已清除，不再调用任何模型" |

## 3. 降级映射表

| 故障类型 | 检测方式 | 降级路径 | 降级时间 | 用户可见 |
|----------|----------|----------|----------|----------|
| 模型超时/断网 | DuMate 计时 / 网络异常 | 重试一次后切降级横幅，保留已确认数据 | <=10s | "网络波动，已切换简化模式" |
| 语音 ASR 故障 | ASR 返回错误或超时 | 回退文字主链路 | <=10s | "语音不可用，请文字回答" |
| 图表渲染失败 | radar_adapter.py 异常 / ECharts 加载失败 | 六维表格降级 | <=10s | 表格替代雷达图 |
| PDF 解析失败 | extract_text.py exit 2 | 引导粘贴文本 | 即时 | "请另存为 TXT 或直接粘贴" |
| Schema 校验失败 | validate_schema.py exit 1 | 降低 temperature 重试一次；仍失败切简化模式 | <=5s | "诊断格式异常，已切换简化诊断" |
| 事实锁阻断 | redflag.py exit 1 | 切简化模式并标注阻断 | 即时 | "检测结果存在可疑数据，已切换简化模式" |
| 千帆 embedding 不可用 | match_requirements.py exit 4 | 切 BM25 并标注"简化匹配" | <=5s | "已切换简化匹配模式" |
| 模型返回非 JSON | JSON 解析失败 | 尝试提取 JSON 片段；仍失败走降级 | <=5s | "处理异常，正在重试" |

## 4. 工具调用链

### 4.1 异常捕获与降级

```
步骤1: 捕获异常
  - DuMate 对话任务捕获工具调用的退出码和异常
  - 记录 trace_id + 输入摘要哈希（非原文）+ 模型/规则版本
  - 不记录原始文件内容、音频或完整简历

步骤2: 判断降级路径
  - 按降级映射表选择对应路径
  - 10秒内切换到降级路径

步骤3: 执行降级
  - 保留用户已确认的数据（不回退已通过的 WF 结果）
  - 只回退当前未完成的节点
  - 展示降级横幅，告知用户当前状态

步骤4: 日志记录
  - 日志落盘前必须过 log_sanitize.py
  python tools/log_sanitize.py --input /tmp/app.log --output /tmp/app.clean.log
  - 或管道方式: cat /tmp/app.log | python tools/log_sanitize.py > /tmp/app.clean.log
```

### 4.2 数据删除流程

```
步骤5: 用户请求删除
  - 用户明确表达"删除数据""清除记录"等意图
  - 确认弹窗："确认删除所有数据？此操作不可恢复。"

步骤6: 用户确认删除
  - 状态 -> DELETING

步骤7: 清除数据
  - 清除会话状态和缓存残留
  - 删除 /tmp/ 下的中间文件（resume_raw.txt, resume_clean.txt, resume_profile.json 等）
  - 不再调用任何模型

步骤8: 记录删除
  - 只记录 trace_id（不含内容）
  - 状态 -> DELETED（终态）
```

## 5. DuMate 对话任务编排

```
[任意 WF 执行中]
  │
  ├─ 异常发生 -> ERROR_DETECTED
  │   ├─ 记录 trace_id + 输入哈希 + 版本
  │   ├─ 查降级映射表 -> 选择降级路径
  │   ├─ DEGRADING: 10秒内切换
  │   │   ├─ 保留已确认数据
  │   │   ├─ 只回退当前节点
  │   │   └─ 展示降级横幅
  │   ├─ DEGRADED: 继续服务
  │   └─ 日志 -> log_sanitize.py -> 落盘
  │
  └─ 用户请求删除
      ├─ 确认弹窗 -> DELETE_REQUESTED
      ├─ 用户确认 -> DELETING
      │   ├─ 清除会话/缓存
      │   ├─ 删除 /tmp/ 中间文件
      │   ├─ 不再调模型
      │   └─ 记录 trace_id（不含内容）
      └─ DELETED（终态）
```

## 6. 变量绑定

| 变量名 | 来源 | 用途 |
|--------|------|------|
| `trace_id` | WF-01 传递 | 异常追踪 |
| `error_type` | 异常捕获 | 选择降级路径 |
| `error_context` | 异常捕获 | 日志记录（脱敏后） |
| `degraded_wf` | 降级映射 | 标记哪个 WF 被降级 |
| `confirmed_data` | 已通过的 WF 结果 | 保留不回退 |
| `model_version` | DuMate 记录 | 日志 |
| `rule_version` | scoring.md 版本 | 日志 |

## 7. 退出标准（验收门）

| 验收项 | 标准 | 验证方式 |
|--------|------|----------|
| 降级时效 | 故障 10秒内切降级路径 | 模拟故障计时 |
| 降级可用 | 降级后仍可继续服务 | 验证降级路径输出 |
| 数据保留 | 不回退用户已确认数据 | 检查已通过 WF 结果未被清除 |
| 删除完整性 | 删除后不再调模型 | 检查 DELETED 状态后无模型调用 |
| 删除残留 | 删除后无缓存/会话残留 | 检查 /tmp/ 文件已清除 |
| 日志安全 | 日志扫描无 PII（姓名/电话/邮箱/身份证/音频/完整简历） | log_sanitize.py 扫描 |
| 日志脱敏 | 手机号/邮箱/JWT/AK-SK 全部脱除 | log_sanitize.py 测试 |
| 降级界面 | 降级态参照 ui/prototype/pages/states.html | 检查界面状态 |

## 8. 验收命令

```bash
# 日志脱敏测试
echo "姓名：张三 电话：13800138000 邮箱：test@example.com Bearer eyJabc.def.ghi api_key=sk-1234567890" \
  | python tools/log_sanitize.py

# 故障注入测试（验证各类异常被正确拒绝/降级）
python -m pytest tests/test_fault_injection.py -v

# 现有全部测试
python -m pytest tests/ -v
```

## 9. 禁止事项

- 禁止失败时回退用户已确认的数据（只回退当前未完成节点）
- 禁止删除后继续调用任何模型
- 禁止日志中包含 PII（姓名/电话/邮箱/身份证/音频/完整简历）
- 禁止日志未经 log_sanitize.py 直接落盘
- 禁止降级超过 10 秒
- 禁止人工放行被 redflag 阻断的结果
- 禁止降级时不告知用户（必须展示降级横幅）

## 可执行合同（P0-01 更新）

### 输入合同
- 输入格式: 异常信号（工具退出码 / 网络异常 / 超时）或用户删除请求（自然语言意图）
- 必填字段: `trace_id`（全链路追踪）、`error_type`（异常分类）或 `delete_intent`（删除意图）
- 校验: 异常退出码匹配降级映射表；删除意图需用户二次确认

### 输出合同
- 输出格式: 状态标记（`DEGRADED` / `FATAL_ERROR` / `DELETED`）+ 脱敏日志
- 必填字段: 降级态含 `degraded=true` + 降级原因；删除态含 `DELETED` 终态标记；日志经 `log_sanitize.py` 处理
- 校验: `log_sanitize.py` 扫描日志无 PII 残留；DELETED 状态后无模型调用记录

### 工具调用链
1. 捕获异常（工具退出码 / 网络异常 / 超时），记录 `trace_id` + 输入摘要哈希
2. 查降级映射表，选择对应降级路径
3. 10s 内执行降级（保留已确认数据，只回退当前节点，展示降级横幅）
4. `python tools/log_sanitize.py --input /tmp/app.log --output /tmp/app.clean.log`
5. （删除路径）用户确认 -> 清除会话状态与 `/tmp/` 中间文件 -> 记录 `trace_id`（不含内容）-> DELETED

### 状态转换
- 初始态: 任意运行态
- 成功态: DEGRADED（降级后继续服务）
- 降级态: DEGRADED（此 WF 本身即降级处理）
- 错误态: FATAL_ERROR（不可恢复）
- 删除态: DELETED（终态，不再调用任何模型）

### 降级路径
| 主路径失败原因 | 降级方案 | 标记 |
|---|---|---|
| 模型超时/断网 | 重试一次后切降级横幅，保留已确认数据 | degraded=true |
| 语音 ASR 故障 | 10s 内回退文字主链路 | degraded=true |
| 图表渲染失败 | 10s 内降级为六维表格 | degraded=true |
| PDF 解析失败 | 引导粘贴文本 | degraded=true |
| Schema 校验失败 | 降低 temperature 重试；仍失败切简化模式 | degraded=true |
| 事实锁阻断 | 切简化模式并标注阻断 | degraded=true |
| 千帆 embedding 不可用 | 切 BM25 并标注"简化匹配" | degraded=true |
| 模型返回非 JSON | 尝试提取 JSON 片段；仍失败走降级 | degraded=true |

### 模型路由
- 任务类型: 无模型调用（纯运维操作）
- 参数: N/A
- 降级: N/A（此 WF 本身即降级与删除处理，不涉及模型调用）

### 验收命令
```bash
# 日志脱敏测试
echo "姓名：张三 电话：13800138000 邮箱：test@example.com Bearer eyJabc.def.ghi api_key=sk-1234567890" \
  | python tools/log_sanitize.py
# 故障注入测试
python -m pytest tests/test_fault_injection.py -v
# 全部测试
python -m pytest tests/ -v
```

### 禁止事项
- [X] 禁止模型自报总分
- [X] 禁止跳过 deidentify（日志落盘前必须过 log_sanitize.py）
- [X] 禁止失败时回退用户已确认的数据
- [X] 禁止删除后继续调用任何模型
- [X] 禁止日志中包含 PII
- [X] 禁止降级超过 10s
- [X] 禁止人工放行被 redflag 阻断的结果
- [X] 禁止降级时不告知用户
- [X] 禁止 DELETED 状态下调用模型
