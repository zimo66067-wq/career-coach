# Changelog

格式遵循 Keep a Changelog；每次冻结记一条。commit hash 在实际提交后回填。

## [Unreleased]

### Changed - 2026-08-12 合并 main 与阶段0上线
- 合并 main（9bf4912）：Vercel 静态托管（root→public rewrites）、首页登录/注册、F2 JD 上传匹配 UI、低分分析（low_score_analysis / insufficient_evidence）、生产 API 域更新
- 保留阶段0真 API 账号/历史（docs/public 双镜像），游客零历史、仅本人可见；data-bridge F2 恢复真实契约（resumeText → /api/wf03/match），失败不复用旧缓存
- vercel.json 合并 f2/auth/history 与静态重写；CI 节点契约扩展至 test_frontend_chain + test_voice_ui
### Added - 阶段0 账号系统与历史持久化（2026-08-10，commit hash 待回填）
- 数据库双方言适配：tools/database.py 支持 SQLite（本地/测试）与 PostgreSQL（生产，DATABASE_URL），新增 users / sessions / history_events 表
- 账号服务 tools/account.py：注册/登录/登出/会话/历史 CRUD；werkzeug 密码哈希；按 IP 限流；role=admin + DEV_DEMO=1 演示数据注入（不落库）
- API：/api/auth/register|login|logout|me、/api/history GET/POST/DELETE；HttpOnly 会话 Cookie（生产 SameSite=None;Secure）；CORS 支持 DELETE/Authorization/Credentials；vercel.json 新增路由重写
- 前端：account.js 重写为真 API 客户端（游客零历史、仅本人历史）；docs/public/ui 三树同步；6 个页面注入可伸缩侧边栏；data-bridge 在 F1-F4 完成后自动落库
- 配置：requirements.txt 新增 psycopg；.env.example 新增 DATABASE_URL / SESSION_TTL_DAYS / DEV_DEMO
- 测试：tests/test_account.py 六项（注册/登录/登出/隔离/限流/管理员演示）；全量 pytest 228 passed / 4 skipped；node 镜像契约 7 passed
- 文档：docs/iteration-2-plan-2026-08-10-competitor-driven.md（执行记录 + Neon 接入与双部署步骤）

### Added - 遗留项自动解决批次（2026-08-06）
- scripts/backup-sessions.py：会话数据日期化自动备份（缓解 Vercel /tmp 冷启动丢数据）
- scripts/run-rehearsal.py：10 次自动化彩排（FakeRouter 全闭环，证据 JSON）
- scripts/capture_mobile_ui.py：375×812 移动端截图（含降级态，0 JS 错误）
- tests/test_voice_ui.js：F3 语音 UI 契约测试（DOM/接线/10s 回退，docs/public 双镜像），纳入 CI
- deliverables/200字项目简介.md；能力矩阵 9 项回填为已验证；mobile-accessibility MT-3/4/5/8/9/10 回填
- README：WF-01~06 端点与环境变量说明、状态与目录导航更新
- scripts/p0-07-freeze.py：修复 gbk 控制台 emoji 输出崩溃（stdout 强制 UTF-8）

### Added - 全工作流统一补全（2026-08-05）
- 统一后端 api/index.py：恢复 WF-01 同意令牌门；新增 WF-03 上传/解析/匹配、WF-04 面试 start/answer/end、WF-05 能力报告、WF-06 删除接口；保留数据库持久化与管理员接口（admin/resumes、admin/export）
- tools/database.py：新增 matches / interview_sessions / abilities 表与会话级读写/删除，支持 F2-F5 跨请求状态
- tools/interview_engine.py：修复问题未写入会话（_current_question/_current_targets/_current_followup）导致回合记录缺失
- 前端：data-bridge.js 恢复同意令牌携带；F2 确认+匹配流程（job-upload.js）与后端 wf03 对齐；docs/ 发布镜像同步
- CI：恢复全量 pytest 门禁与 Node 契约测试（test_public_page_states / test_resume_upload / test_job_upload / test_publish_mirror）
- 文档：docs/design-and-tech-path.md（设计路径与技术路径汇总，含从 git 历史恢复的 PRD/架构/隐私/审查核心）、docs/test-report.md（完整性测试报告）

### Changed - 前端视觉改版 v2（职跃AI 设计系统，基于 DuMate 最新主链路重放）
- ui/prototype 全站升级「温润近白 + 深石墨 + 电光蓝→靛青」视觉语言：新增 css/tokens.css，重写 main.css / states.css
- 四页新增 AI 可解释性元素：分析阶段步进器、呼吸光、语义流动线、面试官语音波形；F4 C0 数字递增动画
- F3 语音组件（voice.js）配色对齐设计系统，ASR/TTS/文字回退逻辑零改动
- 无障碍：skip-link、:focus-visible、prefers-reduced-motion 全量降级、aria 补全
- docs/ GitHub Pages 部署副本全量同步（补齐 voice.js / data-bridge.js 滞后）
- DOM ID / class / data-* / window.* 契约零破坏；pytest 42 项全过
- docs/redesign-v2-visual.md（修改清单 + 验收记录 + 无障碍/性能检查）

### Frozen - 基线冻结（commit B）
- docs/PRD.md、architecture.md、privacy.md 首版冻结
- contracts/ 四个 JSON Schema + scoring.md（R/M/I/C0/C7 公式与手算示例）冻结
- tests/fixtures-synthetic 合成样本集（简历×5、JD×4、面试×1、能力×2）
- workflows/ WF-01~06 占位定义
- handoffs/001-product-to-build.md

### Added - 前端原型与提示词（commit C）
- ui/prototype 五页面 × 五状态静态原型（ECharts 雷达三级降级）
- prompts/ 七份提示词模块（含事实锁与注入防御）
- docs/demo-script.md
- handoffs/002-frontend-to-pipeline.md

### Added - 工具链与测试（commit D）
- tools/ 八个工具：extract_text / deidentify / validate_schema / rescore / log_sanitize / match_requirements / radar_adapter / redflag
- tests/ pytest 契约测试 + 故障注入 + 验收与彩排清单

### Added - 审查与交接（commit E）
- docs/review.md（一审结构合规 + 二审跨文件一致性）
- handoffs/003-tools-to-dumate.md（交 DuMate 主交接文件）

## [Unreleased] - 2026-08-02

### Added
- P0-01: 六工作流可执行合同章节（WF-01~WF-06）
- P0-02: 前端数据接口层 data-bridge.js（三级降级）
- P0-03: 模型路由层 model_router.py
- P0-04: 文字自适应面试引擎 interview_engine.py
- P0-05: 语音增强 voice_handler.py + voice.js
- P0-06: capability_matrix.md
- P0-07: G8/G9 交付包结构
- P1-01: 扩充至 20 份简历、10 份 JD、20 条敏感问题、6 个异常场景
- P1-02: 千帆 embedding 实现 + BM25 降级标识
- P1-03: F4 逐维趋势算法冻结
- P1-04: privacy_lifecycle.py
- P1-06: CI 配置
- P1-07: .env.example + SECURITY.md
- P1-08: 根 HANDOFF.md
- P1-09: 移动端无障碍测试文档
- P2-01~06: 状态声明、模型记录、观测、版本锁定、用户研究、答辩索引
- 新增 21 项测试（总计 63 项）

### Changed
- README.md: 增加项目状态声明
- tools/match_requirements.py: 千帆 embedding 实现
- tools/requirements.txt: 添加 requests 依赖
- workflows/wf-*.md: 追加可执行合同
- ui/prototype/pages/f3-interview.html: 增加语音组件
- ui/prototype/pages/f1-resume.html: 引入 data-bridge.js, 主链路优先 DataBridge
- ui/prototype/pages/f2-match.html: 引入 data-bridge.js, 主链路优先 DataBridge
- ui/prototype/pages/f4-report.html: 引入 data-bridge.js, 主链路优先 DataBridge
- ui/prototype/index.html: 引入 data-bridge.js
- ui/prototype/pages/f3-interview.html: 主链路优先 DataBridge, MOCK 降级为缓存
