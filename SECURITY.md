# SECURITY.md · 安全策略 (P1-07)

> 本文件定义 career-coach 项目的安全治理规范，覆盖漏洞报告、密钥轮换、数据边界、PII 处理与依赖安全扫描。
> 所有协作者（WorkBuddy / DuMate / Integration Agent）必须遵守本文件。

## 1. 漏洞报告流程

### 1.1 报告渠道

- **内部渠道**：在 GitHub 仓库创建 `Security Advisory`（Private vulnerability reporting）。
- **紧急渠道**：直接联系 Integration Agent（单一负责人），口头告知后补工单。
- **禁止行为**：不得在公开 Issue、Commit Message、PR 标题中包含漏洞细节。

### 1.2 响应时效

| 严重程度 | 定义 | 首次响应 | 修复时限 |
|---|---|---|---|
| P0 Critical | 密钥泄露 / PII 入库 / 远程代码执行 | 1 小时内 | 24 小时内 |
| P1 High | 鉴权绕过 / 日志含 PII / 降级失效 | 4 小时内 | 72 小时内 |
| P2 Medium | 输入校验不严 / 信息泄露（非 PII） | 1 个工作日 | 1 周内 |
| P3 Low | 文档不一致 / 日志格式问题 | 3 个工作日 | 下次迭代 |

### 1.3 处理流程

1. 收到报告 → 确认严重程度 → 创建私有分支 `security/fix-<编号>`。
2. 在私有分支修复 → 补充测试用例 → 跑全量 `pytest tests/ -v`。
3. 修复经 Integration Agent 审核后合入 main → 发布安全公告。
4. 如涉及密钥泄露 → 立即执行密钥轮换（见第 2 节）。

## 2. 密钥轮换策略

### 2.1 轮换触发条件

- **定期轮换**：每 90 天轮换一次千帆 AK/SK（QIANFAN_API_KEY / QIANFAN_SECRET_KEY）。
- **事件触发轮换**：密钥疑似泄露、人员变动、安全审计要求时立即轮换。
- **CI 检测触发**：CI 敏感信息扫描（ci.yml）检出硬编码密钥时，立即轮换并修复代码。

### 2.2 轮换步骤

1. 在千帆控制台生成新 AK/SK → 更新 `.env` 文件（本地，不入库）。
2. 旧 AK/SK 在千帆控制台禁用（不立即删除，保留 24 小时观察期）。
3. 跑 `pytest tests/ -v` 确认新凭证可用 → 跑 `python tools/match_requirements.py --backend embedding` 验证 embedding 接口。
4. 24 小时观察期无异常后，在千帆控制台彻底删除旧 AK/SK。
5. 在 HANDOFF.md 记录轮换日期与原因。

### 2.3 密钥存储规范

- 密钥仅存在于 `.env` 文件（本地）或环境变量中，绝不硬编码在源码、提示词、工作流定义或文档中。
- `.env` 已在 `.gitignore` 中排除。
- 仓库中仅保留 `.env.example` 作为模板，不含真实值。
- CI 流水线通过 GitHub Secrets 注入密钥，不在 YAML 中明文写入。

## 3. 数据边界说明

### 3.1 数据存储矩阵

| 数据类型 | 存储位置 | 保留时长 | 删除方式 | 入库？ |
|---|---|---|---|---|
| 用户上传简历原文（PDF/DOCX） | DuMate 会话临时变量 + `/tmp/` 中间文件 | 会话期间 | 用户删除或会话结束自动清除 | 否 |
| 简历纯文本（脱敏后） | `/tmp/` 中间文件 | 会话期间 | 同上 | 否 |
| ResumeProfile / JobProfile 等 JSON 产物 | DuMate 会话状态 | 会话期间 | 同上 | 否 |
| 面试记录（InterviewTurn 序列） | DuMate 会话状态 | 会话期间 | 同上 | 否 |
| 去标识化合成样本 | `tests/fixtures-synthetic/` | 永久（冻结层） | 走变更流程 | 是 |
| 提示词 / 合同 / 工作流定义 | Git 仓库 main 分支 | 永久 | 走变更流程 | 是 |
| 运行日志（脱敏后） | `/tmp/app.clean.log` | 7 天 | 自动清理脚本 | 否 |
| 音频文件（ASR 输入） | 不落盘，流式处理 | 不保留 | — | 否 |

### 3.2 数据最小化原则

- 仓库只保存：去标识化合成样本、配置、提示词、工作流定义、文档、截图。
- 绝不入库：真实简历、真实 JD、音频、完整面试记录、PII 映射表。
- `.gitignore` 已默认排除 `*.pdf` / `*.docx` / `*.log`（合成样本白名单除外）。
- 所有中间文件存放在 `/tmp/` 下，会话结束或用户删除时清除。

### 3.3 数据删除流程

1. 用户发起删除 → 状态机进入 `DELETED` 终态。
2. 删除生效后不得再调任何模型处理该用户数据。
3. 清除 `/tmp/` 下所有中间文件（resume_raw.txt、resume_clean.txt、resume_profile.json 等）。
4. 清除 DuMate 会话变量与缓存残留。
5. 日志已脱敏（见第 4 节），无需额外清除。
6. 删除动作仅记录 trace_id（不含内容）。

## 4. PII 处理策略

### 4.1 去标识化字段清单

进入任何模型调用与评分流程前，以下字段必须由 `tools/deidentify.py` 脱除：

| 字段 | 脱除标记 | 检测方式 |
|---|---|---|
| 姓名 | `[REDACTED_NAME]` | 中文姓名模式 + 常见姓氏表 |
| 手机号 | `[REDACTED_PHONE]` | 11 位数字模式 |
| 邮箱 | `[REDACTED_EMAIL]` | RFC 邮箱正则 |
| 身份证号（18 位） | `[REDACTED_ID]` | 18 位数字+校验位模式 |

脱除完成后文本尾部追加 `pii_removed:true` 标记行；ResumeProfile.pii_removed 必须为 true 才允许进入评分。

### 4.2 敏感属性不进评分

性别、年龄、民族、婚育、照片、籍贯等敏感属性一律不参与 R/M/I/C0 任何计算；模型提示词中已内嵌该禁令（prompts/ 各模块「事实锁」段）。

### 4.3 日志脱敏

- 所有工作流日志落盘前必须经 `tools/log_sanitize.py` 管道处理（复用 deidentify 规则 + token/AK-SK 模式）。
- 质量门：日志扫描不含姓名、电话、邮箱、身份证号、音频或完整简历。
- 日志保留 7 天后自动清理。

### 4.4 PII 泄露应急

1. 发现 PII 入库 → 立即执行 `git filter-branch` 或 BFG 清除历史。
2. 轮换所有可能暴露的密钥。
3. 通知 Integration Agent 并记录到 SECURITY.md 附录。
4. 跑全量测试确认清除彻底。

## 5. 依赖安全扫描

### 5.1 扫描工具

| 工具 | 扫描范围 | 频率 | 配置文件 |
|---|---|---|---|
| GitHub Dependabot | `tools/requirements.txt` + GitHub Actions 依赖 | 每周自动检查 | `.github/dependabot.yml`（待配置） |
| `pip-audit` | Python 依赖（requirements.txt） | CI 流水线每次推送 | ci.yml |
| `grep` 敏感信息扫描 | 全仓库源码 | CI 流水线每次推送 | ci.yml |
| `bandit`（可选） | Python 代码静态安全分析 | CI 流水线 | ci.yml |

### 5.2 漏洞处理

- **Critical / High**：48 小时内升级到修复版本或添加补丁；无法升级时评估替代方案。
- **Medium / Low**：下次迭代统一处理。
- 升级后必须跑全量 `pytest tests/ -v` 确认无回归。

### 5.3 敏感信息扫描规则

CI 流水线（ci.yml）中的 `grep` 扫描检查以下模式：

- API Key 模式：`api_key=`, `API_KEY=`, `apikey=` 后跟非占位值
- Secret Key 模式：`secret=`, `SECRET_KEY=` 后跟非占位值
- 密码模式：`password=`, `passwd=` 后跟非占位值
- Token 模式：`Bearer `, `token=` 后跟非占位值
- 千帆 AK/SK：`sk-` 前缀、32 位连续字母数字串（排除 `.env.example` 中的占位符）

白名单文件：`.env.example`、`.gitignore`、`SECURITY.md`、`ci.yml` 自身（仅含模式名不含真实值）。

### 5.4 依赖锁定

- `tools/requirements.txt` 应固定版本号（`==`），避免隐式升级引入风险。
- 新增依赖前评估：是否必要、是否有已知 CVE、是否有更安全的替代。
- 移除未使用的依赖（定期审查）。
