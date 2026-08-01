# WF-01 · 材料接收与解析

> DuMate 对话任务工作流 | 状态：CONSENT -> RESUME_READY | 优先级：G2 前置

## 1. 触发条件

用户在 DuMate 对话中上传 PDF/DOCX/TXT 文件，或粘贴文本，并明确表达"诊断简历""分析简历"等意图。

## 2. 状态转换

```
INIT -> CONSENT -> EXTRACTING -> DEIDENTIFYING -> RESUME_READY
                                                -> PARSE_FAILED (降级)
```

| 状态 | 含义 | 用户可见 |
|------|------|----------|
| INIT | 等待用户上传或粘贴 | "请上传简历文件（PDF/DOCX/TXT）或直接粘贴文本" |
| CONSENT | 等待用户同意处理 | "我将对你的简历进行去标识化处理，仅用于本次诊断，不保存原始文件。是否同意？" |
| EXTRACTING | 正在提取文本 | "正在提取简历内容..." |
| DEIDENTIFYING | 正在去标识化 | "正在去除敏感信息..." |
| RESUME_READY | 文本就绪，可进入 WF-02 | 展示脱敏后文本前100字，询问确认 |
| PARSE_FAILED | 提取失败 | "无法解析该文件，请另存为 TXT 后重试，或直接粘贴简历文本" |

## 3. 工具调用链

### 3.1 主路径

```
步骤1: python tools/extract_text.py --input <用户文件> --output /tmp/resume_raw.txt
步骤2: python tools/deidentify.py --input /tmp/resume_raw.txt --output /tmp/resume_clean.txt
步骤3: 校验 /tmp/resume_clean.txt 尾部含 "pii_removed:true"
步骤4: 用 grep/正则扫描 /tmp/resume_clean.txt，确认无手机号/邮箱/身份证残留
```

### 3.2 粘贴文本路径

用户直接粘贴文本时跳过步骤1，将文本写入 /tmp/resume_raw.txt 后直接执行步骤2。

### 3.3 备用路径

| 故障 | 检测方式 | 降级动作 |
|------|----------|----------|
| PDF 提取为空（扫描件） | extract_text.py 退出码 2 | 提示用户"该 PDF 可能是扫描件，请另存为 TXT 后重试，或直接粘贴文本" |
| DOCX 解析失败 | extract_text.py 已内建 zipfile 降级；仍失败时异常 | 同上引导粘贴 |
| 去标识化后残留 PII | deidentify.py 退出码 3 | 阻断流程，提示"敏感信息处理异常，请删除姓名/电话后重试" |
| 文件格式不支持 | extract_text.py 退出码 2 | 提示"仅支持 PDF/DOCX/TXT 格式" |

## 4. DuMate 对话任务编排

```
[用户上传文件或粘贴文本]
  │
  ├─ DuMate 检测到文件/文本 -> 进入 CONSENT 状态
  │
  ├─ 用户同意 -> 进入 EXTRACTING
  │   ├─ 调用 extract_text.py（文件模式）
  │   └─ 或写入粘贴文本（粘贴模式）
  │
  ├─ 提取成功 -> 进入 DEIDENTIFYING
  │   └─ 调用 deidentify.py
  │       ├─ 成功（exit 0）-> 扫描残留 -> 无残留 -> RESUME_READY
  │       └─ 失败（exit 3）-> PARSE_FAILED，阻断
  │
  └─ 提取失败（exit 2）-> PARSE_FAILED，引导粘贴
```

## 5. 变量绑定

| 变量名 | 来源 | 用途 |
|--------|------|------|
| `resume_file_path` | 用户上传 | 传给 extract_text.py --input |
| `resume_raw_text` | extract_text.py --output | 传给 deidentify.py --input |
| `resume_clean_text` | deidentify.py --output | 传给 WF-02 作为模型输入 |
| `source_type` | 文件扩展名 | 写入 ResumeProfile.source_type（pdf/docx/paste）|
| `trace_id` | DuMate 生成 UUID | 全链路追踪 |

## 6. 退出标准

- `/tmp/resume_clean.txt` 非空
- 文件尾部含 `pii_removed:true`
- 手机号正则 `1[3-9]\d{9}` 扫描无命中
- 邮箱正则扫描无命中
- 身份证正则 `\d{17}[\dXx]` 扫描无命中

## 7. 验收命令

```bash
# 用合成样本端到端测试
python tools/extract_text.py --input tests/fixtures-synthetic/resumes/resume-01-swe.txt --output /tmp/wf01_raw.txt
python tools/deidentify.py --input /tmp/wf01_raw.txt --output /tmp/wf01_clean.txt
grep -c "pii_removed:true" /tmp/wf01_clean.txt  # 应为 1
grep -cE "1[3-9][0-9]{9}" /tmp/wf01_clean.txt   # 应为 0

# DOCX 路径测试
python tools/extract_text.py --input tests/fixtures-synthetic/resumes/resume-01-swe.docx --output /tmp/wf01_docx.txt  # 若有 docx fixture

# 现有测试
python -m pytest tests/test_extract.py tests/test_deidentify.py -v
```

## 8. 禁止事项

- 禁止将未脱敏文本送入模型
- 禁止保存原始文件副本到仓库
- 禁止将 PII 映射表（--map 输出）入库
- 日志落盘前必须过 log_sanitize.py
- 禁止跳过用户同意（CONSENT）直接处理
