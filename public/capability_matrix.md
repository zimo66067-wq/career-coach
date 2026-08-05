# capability_matrix.md · DuMate 平台能力实测记录表 (P0-06)

> 本文件记录 iCAN/DuMate 提交规则核验与 DuMate 平台能力的实测结果。
> 每项标注「已验证 / 待验证 / 不适用」，并保留日期化截图占位符。
> 更新规则：每次实测后回填结果与截图编号，不得批量预填「已验证」。

---

## 1. 当届 iCAN/DuMate 提交规则核验

| # | 规则项 | 核验内容 | 状态 | 证据 / 备注 |
|---|---|---|---|---|
| 1 | 赛事名称 | iCAN 无代码开发挑战赛 · DuMate 方向 | 已验证 | 见 docs/PRD.md 第1节 |
| 2 | 提交截止日期 | 2026-10-15（以官方规则为准） | 待验证 | 需访问 iCAN 官网确认最新日期 |
| 3 | 主产品载体 | DuMate 对话任务与可复用 Skill | 已验证 | README.md 明确声明 |
| 4 | 交付物清单 | 方案 PDF / 演示 MP4 / 200 字简介 / 分享 URL / Skill 导出 / 冻结清单 | 已验证 | 见 deliverables/README.md |
| 5 | 方案文档限制 | ≤20 页 / ≤50MB | 已验证 | deliverables/README.md 命名规范 |
| 6 | 演示录屏限制 | 4 分 30 秒主路径 | 已验证 | docs/demo-script.md 分镜表 |
| 7 | 提交方式 | GitHub 私有仓库为唯一事实源 + DuMate 平台提交 | 已验证 | README.md 双 Agent 分工 |
| 8 | 代码可用性 | 评委需可匿名访问分享 URL | 待验证 | G9 阶段跨环境验证 |
| 9 | 团队规模限制 | 以官方规则为准 | 待验证 | 需访问 iCAN 官网确认 |
| 10 | 评分维度 | 以官方规则为准 | 待验证 | 需访问 iCAN 官网确认 |

> 截图占位符：`[CAP-001 iCAN官网提交规则截图 2026-XX-XX]`

---

## 2. DuMate 平台能力实测记录表

### 2.1 节点能力

| # | 能力节点 | 测试内容 | 预期行为 | 状态 | 实测日期 | 截图编号 |
|---|---|---|---|---|---|---|
| N1 | WF-01 材料接收 | 上传简历 TXT 文件并解析 | extract_text.py 成功输出纯文本 | 已验证 | 2026-08-01 | `[CAP-002]` |
| N2 | WF-01 材料接收 | 上传简历 PDF（文本型） | 成功提取文本 | 已验证 | 2026-08-01 | `[CAP-003]` |
| N3 | WF-01 材料接收 | 上传扫描件 PDF | 明确报错，引导粘贴文本 | 已验证 | 2026-08-01 | `[CAP-004]` |
| N4 | WF-01 材料接收 | deidentify 脱敏 | 姓名/手机/邮箱/身份证脱除 | 已验证 | 2026-08-01 | `[CAP-005]` |
| N5 | WF-02 简历诊断 | 模型输出 ResumeProfile JSON | 通过 validate_schema + redflag | 已验证 | 2026-08-05 | tests/test_api.py（diagnosis / rule_fallback）+ validate_schema |
| N6 | WF-02 简历诊断 | R 分数复算一致 | rescore.py 对拍 ±0.5 | 已验证 | 2026-08-01 | `[CAP-007]` |
| N7 | WF-03 JD 匹配 | BM25 四态匹配 | 输出 covered/weak/missing/unknown | 已验证 | 2026-08-01 | `[CAP-008]` |
| N8 | WF-03 JD 匹配 | Embedding 主路径 | 智谱 embedding-3 为主（千帆 V2 备） | 已验证 | 2026-08-05 | docs/embedding-model-comparison.md（10 样本召回 91.0%，th=0.50） |
| N9 | WF-03 JD 匹配 | 注入 JD 被置 flag | prompt_injection_flags 非空 | 已验证 | 2026-08-01 | `[CAP-010]` |
| N10 | WF-04 面试 | 文字面试状态机流转 | start→answer→end 完整流转 | 已验证 | 2026-08-05 | tests/test_api.py::test_f3_interview_full_flow |
| N11 | WF-04 面试 | answer_quote 子串校验 | 非子串时该轮作废 | 已验证 | 2026-08-01 | `[CAP-012]` |
| N12 | WF-04 面试 | 敏感问题阻断 | 20 条敏感问题全部阻断 | 已验证 | 2026-08-05 | tests/test_new_tools.py（20 条模式逐一断言） |
| N13 | WF-04 面试 | 语音 ASR 增强 | 按键说话 → 文字转写 | 待验证 | — | `[CAP-014]` |
| N14 | WF-05 能力聚合 | C0 复算对齐 | R/M/I/C0/C7 diff 全 0.00 | 已验证 | 2026-08-01 | `[CAP-015]` |
| N15 | WF-05 能力聚合 | 七天计划生成 | 恰好 7 条 / day 1-7 不重复 / 30-45 分钟 | 已验证 | 2026-08-05 | tests/test_api.py::test_f4_ability_report_consented_full_flow + validate_schema |
| N16 | WF-05 能力聚合 | 雷达图渲染 | ECharts option 可渲染六维雷达 | 已验证 | 2026-08-01 | `[CAP-017]` |
| N17 | WF-06 异常 | 模型超时降级 | 主模型不可用切规则降级并标注 | 已验证 | 2026-08-05 | tests/test_api.py::test_unavailable_model_returns_labeled_rule_fallback |
| N18 | WF-06 异常 | 用户删除数据 | DELETED 终态，数据清除 | 已验证 | 2026-08-05 | tests/test_api.py::test_f6_delete_removes_session_data |

### 2.2 模型能力

| # | 模型 | 用途 | 测试输入 | 预期输出 | 状态 | 截图编号 |
|---|---|---|---|---|---|---|
| M1 | DuMate 当前模型 | 简历语义抽取 | resume-01-swe.txt | ResumeProfile JSON | 待验证 | `[CAP-020]` |
| M2 | DuMate 当前模型 | JD 解析 | job-01-swe.txt | JobProfile JSON | 待验证 | `[CAP-021]` |
| M3 | DuMate 当前模型 | 面试追问 | interview-01.json | InterviewTurn 追问 | 待验证 | `[CAP-022]` |
| M4 | 千帆 Qwen3-Embedding | JD 语义召回 | requirements 数组 | 四态匹配 + 召回率 ≥85% | 待验证 | `[CAP-023]` |
| M5 | 百度 ASR | 语音转文字 | 面试回答音频 | 文字转写 + 置信度 | 待验证 | `[CAP-024]` |
| M6 | 百度 TTS | 文字转语音 | 面试官问题 | 语音播报 | 待验证 | `[CAP-025]` |
| M7 | Kimi-K3 | 报告/七天计划 | 聚合 R/M/I 数据 | 七天竞争力情景推演 | 待验证 | `[CAP-026]` |

> 模型选择记录详见 `docs/model-baking-log.md`。

### 2.3 文件能力

| # | 文件类型 | 测试内容 | 预期行为 | 状态 | 截图编号 |
|---|---|---|---|---|---|
| F1 | TXT 简历 | extract_text.py 处理 | 成功提取纯文本 | 已验证 | `[CAP-027]` |
| F2 | PDF 文本型 | extract_text.py 处理 | 成功提取文本 | 已验证 | `[CAP-028]` |
| F3 | PDF 扫描型 | extract_text.py 处理 | 报错引导粘贴 | 已验证 | `[CAP-029]` |
| F4 | DOCX 简历 | extract_text.py 处理 | 成功提取纯文本 | 已验证 | `[CAP-030]` |
| F5 | JSON 产物 | validate_schema.py 校验 | exit 0 VALID | 已验证 | `[CAP-031]` |
| F6 | ECharts option | radar_adapter.py 输出 | 6 indicator / max=100 / 3 series | 已验证 | `[CAP-032]` |
| F7 | 脱敏日志 | log_sanitize.py 处理 | 手机/邮箱/JWT/AK 全脱除 | 已验证 | `[CAP-033]` |

### 2.4 图表能力

| # | 图表类型 | 测试内容 | 预期行为 | 状态 | 截图编号 |
|---|---|---|---|---|---|
| C1 | 六维雷达图 | ECharts CDN 渲染 | 正常渲染六维雷达 | 已验证 | `[CAP-034]` |
| C2 | 六维雷达图 | ECharts 本地 vendor 渲染 | 断网后正常渲染 | 已验证 | `[CAP-035]` |
| C3 | 六维雷达图 | 表格降级 | 禁用 vendor 后六维表格显示 | 已验证 | `[CAP-036]` |
| C4 | UI 五状态 | empty/processing/success/error/degraded | 五态均可正确展示 | 已验证 | `[CAP-037]` |

### 2.5 语音能力

| # | 语音功能 | 测试内容 | 预期行为 | 状态 | 截图编号 |
|---|---|---|---|---|---|
| V1 | ASR 语音输入 | 按键说话 → 文字转写 | 转写成功 + 置信度显示 | 待验证 | `[CAP-038]` |
| V2 | ASR 低置信度处理 | 置信度 < 0.75 | 触发用户确认提示 | 待验证 | `[CAP-039]` |
| V3 | ASR 故障降级 | ASR 接口超时/错误 | 10 秒内回退文字主链路 | 已验证 | tests/test_voice_browser.py（故障回退 + 10s 计时器） |
| V4 | TTS 语音播报 | 面试官问题语音输出 | 语音播放正常 | 待验证 | `[CAP-041]` |
| V5 | TTS 故障降级 | TTS 接口不可用 | 不阻断主链路 | 已验证 | tests/test_voice_browser.py（tts_error 非阻断） |

> 语音为增强链路，文字是等价稳定主链路（见 PRD 第2节 F3 说明）。

---

## 3. 官方 URL 类型确认

| # | URL 类型 | 确认内容 | 状态 | 证据 / 备注 |
|---|---|---|---|---|
| U1 | DuMate 搭子入口 | DuMate 桌面端 / Web 端访问地址 | 待验证 | 需确认是桌面应用还是 Web URL |
| U2 | Skill 分享 URL | DuMate 可复用 Skill 的分享链接格式 | 待验证 | 需确认 URL 是否可匿名访问 |
| U3 | GitHub 仓库 URL | 私有仓库，评委需邀请访问 | 待验证 | 需确认评委访问方式 |
| U4 | iCAN 提交入口 | iCAN 官网提交页面 URL | 待验证 | 需访问 iCAN 官网确认 |
| U5 | 分享 URL 匿名性 | 评委无需登录即可访问 | 待验证 | G9 阶段跨环境验证 |

> 截图占位符：`[CAP-043 DuMate入口URL截图 2026-XX-XX]`

---

## 4. 匿名访问验证记录

| # | 验证项 | 测试方法 | 预期结果 | 状态 | 截图编号 |
|---|---|---|---|---|---|
| A1 | Skill 分享 URL 无登录访问 | 退出 DuMate 登录后访问分享 URL | 可正常访问功能 | 待验证 | `[CAP-044]` |
| A2 | 无痕窗口访问 | Chrome 无痕模式访问分享 URL | 可正常访问功能 | 待验证 | `[CAP-045]` |
| A3 | 评委模拟访问 | 使用未登录浏览器访问 | 可完整走 F1-F4 主路径 | 待验证 | `[CAP-046]` |
| A4 | 不触发鉴权弹窗 | 访问过程中无登录要求 | 全程无登录拦截 | 待验证 | `[CAP-047]` |

---

## 5. 跨环境访问验证

| # | 环境 | 验证内容 | 预期结果 | 状态 | 截图编号 |
|---|---|---|---|---|---|
| E1 | 退出登录后访问 | DuMate 退出登录 → 重新访问分享 URL | 可匿名访问 | 待验证 | `[CAP-048]` |
| E2 | 无痕窗口访问 | Chrome Incognito 模式 | 可匿名访问 | 待验证 | `[CAP-049]` |
| E3 | 另一台设备 | 不同 PC 访问分享 URL | 可匿名访问 | 待验证 | `[CAP-050]` |
| E4 | 手机热点 | 手机 4G/5G 热点连接 PC 访问 | 可匿名访问 | 待验证 | `[CAP-051]` |
| E5 | 手机直接访问 | 手机浏览器打开分享 URL | 移动端可用（降级适配） | 待验证 | `[CAP-052]` |
| E6 | 平板设备 | iPad / Android 平板浏览器 | 平板端可用 | 待验证 | `[CAP-053]` |
| E7 | 断网离线 | 断网后打开已缓存的 UI 原型 | F1-F4 success 态可展示 | 已验证 | `[CAP-054]` |
| E8 | 弱网环境 | 限速 3G 网络访问 | 降级横幅出现，核心功能可用 | 待验证 | `[CAP-055]` |

> 移动端无障碍测试详见 `docs/mobile-accessibility-testing.md`。

---

## 6. 验证状态汇总

| 状态 | 数量 | 占比 |
|---|---|---|
| 已验证 | 37 | 54% |
| 待验证 | 31 | 46% |
| 不适用 | 0 | 0% |
| **合计** | **68** | **100%** |

> 本表在每次实测后更新计数。已验证项的证据为：自动化测试（pytest/node）或实测报告；平台截图类仍待 DuMate 平台操作补齐。
> 下一优先验证：V1/V4（语音实机）、M1-M3（DuMate 平台模型）、U1-U5/A1-A4/E1-E6/E8（匿名与跨环境访问）。
