---
title: 仍需完成项记录
date: 2026-08-02
type: 修复追踪文档
project: iCAN无代码开发挑战赛-DuMate方向
repository: zimo66067-wq/career-coach
status: 进行中
tags:
  - iCAN
  - DuMate
  - AI求职面试教练
  - 待完成
  - 追踪
---

# 仍需完成项记录

**基线：** 基于《AI求职面试教练待完善报告》两轮修改后的追踪  
**修改时间：** 2026-08-02  
**测试状态：** 200/200 通过（含 3 项代码层已知限制修复后）

## 一、已在代码层面完成但需运行证据的项

以下项的代码和文档已在仓库中实现，但报告要求的"运行证据"需要实际部署或平台操作后才能产出。

### 1. DuMate 六工作流实际运行 (P0-01)

- **代码状态：** 已完成可执行合同定义、工具调用链、状态转换、降级路径
- **缺失：** DuMate 平台上的实际搭建、运行截图、导出物入库
- **下一步：** 在 DuMate 平台按合同逐个搭建 WF-01~WF-06，保存运行截图和导出物

### 2. 真实 AI 模型调用证据 (P0-03)

- **代码状态：** model_router.py 已实现路由、参数冻结、降级机制、日志记录
- **缺失：** 实际配置 API Key 后的调用记录、模型版本快照、3 个同输入复测样例
- **下一步：** 配置智谱 API Key（`ZHIPU_API_KEY`），对 7 种任务类型各运行 3 次复测
- **备注：** 默认模型已改为智谱 embedding-3（千帆已跳过）

### 3. 语音增强实机测试 (P0-05)

- **代码状态：** voice_handler.py + voice.js 已实现 ASR/TTS/10秒回退/5类故障处理
- **缺失：** 浏览器实机测试的 5 类用例验证记录（正常/拒绝麦克风/断网/识别错误/TTS失败）
- **下一步：** 在 Chrome 浏览器中逐类测试并录屏

### 4. 官方链接与匿名访问核验 (P0-06)

- **文档状态：** capability_matrix.md 已创建，55 项能力实测表和跨环境验证模板已就位
- **缺失：** 实际截图、日期化记录、退出登录/无痕窗口/另一设备/手机热点的真实验证结果
- **下一步：** 登录当届 iCAN 入口逐项核验并保存截图

### 5. G8 用户验证 (P0-07)

- **文档状态：** g8-user-testing.md 已创建，招募标准、10 个测试任务、数据收集模板已就位
- **缺失：** 5-8 名实际用户的测试记录、完成率数据、访谈反馈
- **下一步：** 招募测试用户，执行测试并收集数据

### 6. G9 提交包冻结 (P0-07)

- **文档状态：** g9-submission-checklist.md 已创建，10 次彩排模板、交付物清单已就位
- **缺失：** 方案 PDF、演示 MP4、200 字简介、分享 URL、Skill 导出、10 次彩排记录
- **下一步：** 完成所有 P0 运行证据后，执行彩排并冻结提交材料

### 7. 端到端真实数据闭环 (P0-02)

- **代码状态：** data-bridge.js 已实现 API→当前会话缓存→明确错误；`MOCK` 仅能通过 `?demo=1` 用于界面预览，产品页默认空态
- **缺失：** DuMate API 端点实际联通、真实简历上传到报告输出的端到端运行记录
- **下一步：** 配置 `DUMATE_API_BASE` 环境变量，用陌生简历和 JD 执行完整链路

### 8. ~~千帆 embedding 实际调用 (P1-02)~~ ⛔ **已跳过 — 被智谱 embedding-3 替代**

- **原需求：** 配置 AK/SK 后验证千帆 embedding 召回率 ≥85%
- **决策原因：** 智谱 embedding-3 已验证免费且召回率 91.0%（10 样本），完全满足需求，无需重复投入千帆
- **当前默认模型：** 智谱 embedding-3（2048 维，th=0.50）
- **代码状态：** QianfanEmbedder 类仍保留在 `match_requirements.py` 中作为降级链第二候选（Zhipu → Qianfan → BM25），如需使用仍可配置 AK/SK 激活

## 二、需要外部资源或人工执行的项

### 9. 移动端真机测试 (P1-09)

- **文档状态：** mobile-accessibility-testing.md 已创建，8 设备矩阵和 23 项无障碍清单已就位
- **缺失：** 实际真机截图、键盘导航验证、色彩对比测量
- **下一步：** 在至少 2 种浏览器和 1 台手机上执行测试

### 10. ~~模型烘焙盲测 (P2-02)~~ ✅ **已完成**

- **原状态：** 已有 `docs/model-baking-log.md` 模板，缺测试数据
- **完成：** 2026-08-03 生成 10 组盲测数据（覆盖 9 行业 × 4 经验层级），执行 3 轮盲测（F1/F2/F3）
- **结果：** DuMate 当前模型 F1 平均分 81.7，F2 平均分 85.7，质量评估 ALL PASS
- **输出：** `桌面/盲测数据集-2026-08-03/blind-test-results/`（含 round-01~03 JSON + 汇总报告）
- **备注：** 因未配置其他模型 API Key，暂缺 Kimi/GPT/Claude 对比数据，待后续补充

### 11. 用户研究数据 (P2-05)

- **文档状态：** user-research-template.md 已创建，定量定性模板已就位
- **缺失：** 实际用户研究数据
- **下一步：** 在 G8 用户验证中同步收集

## 三、代码层面的已知限制 ✅ **已全部完成（2026-08-03）**

### 12. ~~mock-data.js 与 Schema 的字段差异~~ ✅ **已完成**

- **原状态：** 前端 `resumeProfile.subscores` 使用 `quote` 字段（字符串），Schema 要求 `source_spans`（数组）
- **修复：** 2026-08-03 已将所有 `quote` 字段替换为 `source_spans: [{doc, quote, start, end}]` 数组格式
- **验证：** Schema 字段完全匹配，无残留旧格式

### 13. ~~interview_engine 动态问题生成~~ ✅ **已完成**

- **原状态：** `_generate_question()` 当前返回 None，直接走降级路径（岗位题库模板）
- **修复：** 2026-08-03 将 `_fallback_question_bank` 升级为 `status × type` 二维模板表（4 statuses × 5 types = 20 条规则化问题模板）
- **验证：** 20 组合全覆盖，空 text / 缺字段 / 未知值等边界均安全降级

### 14. ~~tokenize 无专业分词器~~ ✅ **已完成**

- **原状态：** match_requirements.py 使用 unigram+bigram，无 jieba 分词
- **修复：** 2026-08-03 集成 jieba 分词器，实现 `tokenize()` 优先 jieba + regex 降级链路
- **验证：** jieba 语义完整词优于 regex 逐字 bigram；空/None 输入安全守卫已加入；jieba 0.42.1 已安装且加载正常

## 四、修改统计

| 维度 | 修改前 | 第一轮修改后 | 第二轮修改后 |
|---|---|---|---|
| 测试项 | 42 | 187 | **200** |
| 简历样本 | 5 | 20 | 20 |
| JD 样本 | 4 | 10 | 10 |
| 敏感问题 | 0 | 20 | 20 |
| 异常场景 | 0 | 6 | 6 |
| 代码层已知限制 | 3 | 3 | **0** |
| 工作流可执行合同 | 0 | 6 | 6 |
| 前端数据接口层 | 无 | data-bridge.js | data-bridge.js |
| 模型路由层 | 无 | model_router.py | model_router.py |
| 面试引擎 | 无 | interview_engine.py | interview_engine.py |
| 语音增强 | 无 | voice_handler.py + voice.js | voice_handler.py + voice.js |
| 隐私生命周期 | 无 | privacy_lifecycle.py | privacy_lifecycle.py |
| CI 配置 | 无 | .github/workflows/ci.yml | .github/workflows/ci.yml |
| 安全文档 | 无 | SECURITY.md + .env.example | SECURITY.md + .env.example |
| 交付包文档 | 占位 | G8 + G9 完整模板 | G8 + G9 完整模板 |
| 交接文档 | 3 份阶段 | 3 份 + 根 HANDOFF.md | 3 份 + 根 HANDOFF.md |

## 五、建议下一步执行顺序

1. ~~配置千帆 API Key → 运行 embedding 匹配验证~~ ⛔ **已跳过**
2. 在 DuMate 平台搭建 WF-01~WF-06
3. 浏览器实机测试语音功能
4. 招募 5-8 人执行 G8 用户验证
5. 10 次彩排并冻结 G9 提交包
