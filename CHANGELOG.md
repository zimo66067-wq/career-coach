# Changelog

格式遵循 Keep a Changelog；每次冻结记一条。commit hash 在实际提交后回填。

## [Unreleased]

### Added - 2026-09-12 F5 单位/职位索引基础框架（阶段 1）
- 新增双方言索引表：`organizations`、`organization_aliases`、`organization_profiles`、`source_snapshots`、`job_postings`、`job_posting_versions`、`job_embeddings`；单位与职位均以 `(source_provider, source_key)` / `(source_provider, external_job_id)` 幂等 upsert，职位内容哈希变化才追加版本
- 新增 provider 契约 `tools/providers/organization.py`：默认 `UnconfiguredOrganizationProvider`，结果必须携带 `source_provider`、`source_url`、`source_updated_at`、`verified_at`、`verification_state`，缺项在写入与返回两处一律剔除；通过 `ORG_DATA_PROVIDER` 选择已注册且已授权的 provider
- 新增 `services/organization_service.py`：未配置数据源时返回显式 `status="unconfigured"` 状态与提示，`discover` 返回 422 `discovery_unavailable`，`suggest` 强制 64 字与 1–20 条边界；即使索引内存在人为写入的行，未配置时也不对外返回
- 新增 API `/api/f5/organizations/{status|suggest|discover|detail|jobs}`，并登记本地路由与 `vercel.json` 重写
- F5 页面新增「单位与职位检索：尚未接入授权数据源」状态区与「未经平台核验」手动输入提示；**不提供**任何单位搜索框，也不生成单位事实
- 新增回归测试 `tests/test_organization_index.py`（16 项）与 F5 页面契约断言（public/docs 镜像 + 五项决策 + 无搜索框）
- 规划文档 `docs/f5-organization-job-search-plan-2026-09-11.md` 标记阶段 0/1 已交付，并明确阶段 2–4 未开始

### Changed - 2026-09-11 自适应面试、专业容错检索与 F5 边界透明化
- F3 第二个及后续主问题强制携带最近回答上下文，并在模型与规则降级路径中引用脱敏后的回答原句；新增重复题、高相似题、敏感字段回流和模型输出类型防护
- F2 专业搜索从字面包含升级为代码规范化、名称编辑距离、专业类、岗位意向与专业画像联合排序；返回匹配原因并处理请求乱序、空结果和错误状态
- F5 页面明确当前仅支持手填公司/职位后的求职信与申请跟踪，不提供或核验单位/职位搜索；新增单位实体与职位时效双索引扩展规划
- 回归门禁：pytest 420/420、Node 51/51；requirements 与 tools/requirements 依赖审计均未发现已知漏洞；git diff --check 通过

### Security - 2026-09-11 F3 发布阻断项清零（fail closed）
- 新增 `_check_unsafe_generated_question()`，与 HR 敏感词闸门分离：拦截提示注入（忽略/绕过/覆盖规则与系统提示）、凭据索取（系统提示词、API key、.env、环境变量、令牌、密钥、验证码）与 PII 索取（身份证、手机号、银行卡等）；在拼接回答 anchor 前后各检查一次，降级题再检查一次，最终回落硬编码安全题
- `_safe_answer_anchor()` 拒绝危险注入短句，并强制 anchor 必须是原始回答的逐字子串；若最终题目不再包含 anchor，`basis` 置空，保证 basis ⊆ question 不变量
- 送模型上下文闭环：`job_title` 先脱敏再截断 120 字；`target_gap` 按 id≤64/type≤32/text≤160/status≤16 硬截断；`router.call()` 的 context 只保留 `turn_id` 与布尔标记，不再回传原始 gap 与 recent_turns，杜绝未脱敏 PII 与超长输入外发
- 中文姓名去标识化补全：新增「姓名：」「我叫/我是/本人叫/名字是」自述规则与“整行仅姓名”兜底规则（含称谓词与常见非姓名词保护），不再把邻近词一并吞掉
- 低 ASR 置信度不再推进状态机：主回答与待回答追问两条路径均不记录 turn、不生成追问、不递增主问题计数，SSE 返回 `nextQuestion=null` 与 `needs_confirmation=true`
- F3 输入边界：`answer_text` 上限 4000 字（422 `answer_too_long`）、`matchGaps` 限 20 条且逐项校验为对象（422 `invalid_match_gaps`）、`asr_confidence` 非数字返回 422；`/wf04/answer` 与 `/wf04/stream` 共用同一编排；页面 textarea 同步 `maxlength=4000`
- 新增回归测试：恶意 router 输出、恶意 answer anchor、恶意 gap 文本、10k 字 title/gap 的 payload 有界与脱敏断言、低置信度状态机不推进

### Fixed - 2026-09-11 F2 兼容与 UI 闭环
- `total` 改为截断前候选数（`search_majors_with_total()`），`limit=1&q=计算机` 返回 `items=1` 且 `total>1`
- 第二个“意向输入”框补齐与主搜索同级的防护：requestVersion/AbortController 防乱序、加载/空结果/4xx-5xx/`query_too_long`/网络失败状态，修复长输入 422 后对不存在 `items` 调用 `.map()` 与旧结果残留
- 主搜索区分业务错误与网络错误：只展示 `query_too_long` 等安全可预期文案，5xx/网络统一通用提示
- 两个搜索框加 `maxlength="64"`；失焦后使在途请求失效，慢响应不再把下拉框重新弹出
- 两字查询只接受名称前缀命中：「数学」仍能召回「数学与应用数学」，但「计科」不再跨词命中「材料设计科学与工程」(080415)；补充简称 `电科 → 080702`、`数媒 → 080906 / 130508`
- 保持 `public/` 与 `docs/` 的 F2/F3/F5 页面与脚本哈希一致

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
