# Changelog

格式遵循 Keep a Changelog；每次冻结记一条。commit hash 在实际提交后回填。

## [Unreleased]

### Changed - 2026-09-17 依赖倒置：模型工厂收敛 + 分层门禁（Phase 5）

DoD #13「Service 不反向依赖 API」。两处倒置（`diagnosis_service` / `interview_service` 里
**写在函数体内**的 `from api.index import build_model_router`）从 Phase 0 就点出，
一直拖到现在才修 —— 修完还发现它们有第二层依赖。

- **工厂收敛为单一归属地**：`build_model_router` 只保留 `tools/providers/model.py` 一处定义，
  其余模块（api 层 + 三个服务）一律 `from tools.providers import model as model_provider`
  后**属性查找**。此前多处绑定导致"打桩打错地方不报错、只是不生效"；
  收敛后打错会 `AttributeError`（`monkeypatch.setattr` 默认 `raising=True`）
- **移除传递 Flask 依赖**：`tools.trace.trace_id()` 要 Flask 请求上下文，诊断服务用它兜底，
  于是**服务的单测必须 `with app.test_request_context()` 才能跑**。改为：
  `tools/trace.py` 拆出纯函数 `new_trace_id()`、flask 改函数内延迟导入；
  web 层解析 `X-Trace-Id` 后用 `diagnose_resume(resume_text, trace=...)` **注入**服务
- `services/diagnosis_service.diagnose_resume()` 新增可选 `trace` 入参（缺省用纯函数生成）
- `services/interview_service.build_interview_router()` / `services/apply_service` 同步收敛
- **新增门禁** `tests/test_layering.py`（**8 项**，进 pytest）：跨层 import（含函数体内的）、
  domain/services 的**传递 Flask 依赖**（只按模块级 import 计算）、`build_model_router`
  单一归属地且无人重新绑定、**判据自检**（喂故意越层的假源码证明它会红）
- 6 个测试文件 + `scripts/run-rehearsal.py` 的打桩点统一改到 `tools.providers.model`

提交：**`<待回填>`**（<待回填> 文件，<待回填>）。

### Changed - 2026-09-17 Phase 5 门禁口径

- pytest **473 → 481**（+8 项分层门禁）；node 36/36 不变
- **分层静态校验从"手工 grep 一次"升级为 pytest 门禁**（此前报告里的
  "domain 层 0 处越层 import"是跑一次命令得出的，不可回归；现在是 8 项常驻用例）
- 真实 HTTP 冒烟仍 **70/70**（本阶段未改路由与冒烟脚本）
- vercel 重写仍 **44** 条 / 死路由 0；双方言 DDL 仍各 **29** 张表；敏感扫描无发现

### Added - 2026-09-17 求职信接目标岗位与已确认证据（Phase 4b · DoD #10）

DoD #10 不是"再写一版提示词"，而是**换掉事实底座**：旧路径读的是 F1 诊断里模型抽的 span 引文 ——
那些**不是已确认事实**，只是"模型觉得相关"的简历片段。求职信是发给雇主的对外材料，
底座错了，写得再漂亮也是替用户编经历。

- `POST /api/wf07/cover-letter` 增可选 `targetJobId`。**不传则旧行为完全不变**
  （只读 F1 诊断，新增 `grounding: "diagnosis"` 供前端区分两条路）；传则走接地路径
- `services/apply_service.py`：`_letter_context()` 一次取齐事实底座 ——
  岗位（`get_target_job(id, owner_key)`，**第一步就做归属校验**）、要求（按 `priority_for()`
  排 P0→P1→P2、截断 5 条）、缺口（只留 `OPEN_GAP_STATUSES`）、证据
  （`career_evidence_service.usable_evidence()`，Phase 3 定下的**下游唯一入口** = 只含 confirmed、截断 3 条）
- **三条不可让步的规则**：①**没有已确认证据就不请模型写**（`build_model_router()` 只在证据非空时调用，
  否则只给带明确占位的框架）；②**未覆盖的要求是"禁止声称"名单**，只进元数据不进正文；
  ③**正文每段经历都要能回指一条已确认证据**（复用四字片段校验，过不了退规则模板）
- 接地路径返回新增字段：`grounding` / `evidence` / `requirements` / `gaps` / `notice`
  （后三个是给 Phase 6 界面用的：告诉用户正文引了哪几条证据、哪几条要求没声称）
- `prompts/apply/cover-letter.md`：写明 A（接地）/ B（旧）两种输入结构与接地路径的三条硬约束
- `tests/test_cover_letter_grounding.py`（**16 项**）：只引用已确认证据（6）/ 要求与缺口（2）/
  模型三道门（3）/ 归属隔离与旧路径兼容（5）
- `scripts/phase4-http-smoke.py` 追加 **13 项**真端口检查（接地路径 / 未确认证据不进正文 /
  会话与岗位两道归属各测一次 / 旧路径仍要 F1 诊断）
- `scripts/vercel-dead-routes.py`（新建）：把"死路由"判据从**静态比对前缀**换成**实证逐方法探测**
  —— 旧判据对参数化重写（`$1`）永远判"接上了"，实际漏掉"只有特定方法才进分支"这类问题

提交：**`5cba7b4`**（10 文件，+1112 / −12）。

### Changed - 2026-09-17 Phase 4b 门禁口径

- pytest **457 → 473**（+16，本阶段新增用例）；node 36/36 不变
- 真实 HTTP 冒烟 **57 → 70** 项
- vercel 重写仍 **44** 条（本阶段未新增路由），死路由 0
- **死路由判据换了**：从"用 `_route` 值比对分派表的前缀族"改成**实证逐方法探测**
  （`scripts/vercel-dead-routes.py`）。旧判据把参数化重写（`history/$1`）一律判为"接上了"，
  实际它只有 DELETE 才进分支 —— 静态前缀比对永远发现不了这类问题
- 双方言 DDL 仍各 **29** 张表，无漂移（本阶段无 schema 变更）
- 补记：敏感扫描 **249 → 252** 文件（本阶段新增测试文件与检查脚本）

### Added - 2026-09-16 行动闭环：Gap Action Plan + 投递结果回流（Phase 4）

Phase 3 只回答"我差什么"和"能不能投"，用户拿到结论之后**无事可做**。Phase 4 补的是闭环的
另一半：把缺口翻成今天就能做的一件事，让做完之后发生的事回流成新证据。

- `services/action_plan_service.py`：缺口 → 可执行行动。四条硬约束 ——
  **开单需要可验证成果物**（域层 `open_from_gap()` 拒绝没有 `expected_artifact` 的缺口，
  服务层不绕过，缺成果物的缺口如实报进 `skipped` 并给原因）；**幂等**（`todo`/`doing` 期间不重复开单）；
  **开单即让缺口进 `doing` 但仍属未解决**（`OPEN_GAP_STATUSES`，所以开单不会让 Decision 变乐观）；
  **完成 ≠ 缺口解决**（行动 `done` 只记"我做了这件事"，缺口是否补齐只由**重新分析**决定）
- `services/apply_service.record_outcome_feedback()`：三本账分开算 —— 结果始终落库 /
  状态推进可能被拒并如实回报 `statusApplied=false`（倒流补记不改写历史）/ 证据只能 `pending`
  （`source_type=application_outcome`，"被拒""拿 offer"都只是推断）
- **D9 方案 A 落地**：`POST /api/wf04/end` 增可选 `targetJobId`，结束后**一次性**抽取面试新事实
  （`prompts/interview/evidence.md`，逐字引文铁律）。模型路径与降级路径都由
  `domain.interview.candidate_evidence()` 收口，**只产 pending**；引文必须是回答的**逐字子串**，
  模型改写原文整条丢弃；模型说"这轮没有事实"时**不允许**用 `answer_quote` 兜底补一条
- 8 条路由：`/api/actions`（清单 / 批量或单条开单 / start / complete / outcome / drop / 删除）、
  `/api/wf07/applications/<id>/outcome` 与 `/outcomes`；`vercel.json` 增 3 条重写（共 **44** 条）
- `repositories.action.list_with_gap_context()`：一次 LEFT JOIN 取缺口上下文，P0 优先排序
- `tools/model_router.py` 注册 `interview_evidence` 任务（temperature 0.1 / timeout 30s / 降级空数组）
- `tests/test_action_loop.py`（**34 项**）：9 项面试抽取 + 13 项行动计划 + 7 项结果回流 + 3 项契约
- `/api/health` 的能力表增 `actions`

提交：**`e4b7da3`**（17 文件，+2314 / −15；含测试、冒烟脚本与文档）。

### Fixed - 2026-09-16 删除目标岗位时遗留孤儿行动（Phase 4 自查）

`delete_target_job` 的契约明确写着"从它派生出来的个人数据必须一并消失，不能留下可以反推出
岗位与要求的孤儿行"，但原实现删了 requirements / matches / gaps / decisions，**唯独没删 actions**。
而行动的 `task` / `artifact` 文案正是缺口 `action` / `expected_artifact` 的复制，也就是**被改写过的
JD 要求**；`list_with_gap_context` 的 `LEFT JOIN` 让整行照常出现在清单里 ——
**LEFT JOIN 的容错把数据泄漏伪装成了健壮性**。

修法：新增 `repositories.action.delete_for_target()`，在删 `gaps` **之前**调用
（行动靠 `gap_id` 认路，顺序反了就再也认不出来），并补测试
`test_deleting_a_target_job_also_removes_its_actions`。
这是"测试通过、门禁全绿"却真实存在的漏洞，只有照删除契约逐条核对派生数据才发现。

### Changed - 2026-09-16 Phase 4 门禁口径

- pytest **423 → 457**（+34，本阶段新增用例）；node 36/36 不变
- vercel 重写 **41 → 44** 条，死路由仍为 0，并新增**正向**检查：
  新接口必须在生产入口有重写（只在本地注册 = 线上 404）
- 真实 HTTP 冒烟 **37 → 57** 项（`scripts/phase4-http-smoke.py`，真进程 + 真端口）
- 新增 `scripts/sensitive-scan.py`：与 CI 步骤 6 同口径的敏感信息扫描（本地门禁跑，避免本地过、CI 挂）
- 双方言 DDL 仍各 **29** 张表，无漂移；`actions` / `application_outcomes` 双方言均在

### Added - 2026-09-14 核心闭环：职业证据档案 + 目标岗位分析（Phase 3）

把 domain / repositories 两层接到 HTTP 上，打通
**Resume → Evidence → Target Job → Match → APPLY/STRETCH/PASS → Interview**。

- `services/career_evidence_service.py`：模型产出 → **候选证据（pending）** → 用户确认。
  HTTP 层不提供任何直接写 `confirmed` 的入参。三道内容过滤：子项白名单
  （`structure` / `ats_readability` 不产证据）、`is_substantive_claim`（挡版块标题）、
  `is_complete_span`（挡词中间截断的定长窗口）
- `services/target_job_service.py`：JD → 要求 → 匹配 → 缺口 → 决策。含 JD 解析过滤
  （丢掉标题行与版块名，并把标题回收成岗位名）与 `blocking` 判定
- `repositories/career_profile.py`：CareerProfile 幂等持久化
- 11 条路由：`/api/profile`、`/api/profile/evidence/*`（confirm/reject/edit/delete）、
  `/api/target-jobs`（CRUD + analyse + decision）；`vercel.json` 增 5 条重写（共 41 条）
- `POST /api/wf04/start` 新增可选 `targetJobId`：出题顺序直接来自该岗位的未解决缺口，
  并返回 `questionPlan` 证明 P0 排在 P1 之前
- `domain.target_job.GAP_TYPES` 增 `unverifiable`
- `/api/health` 的能力表增 `profile`、`target_jobs`

### Fixed - 2026-09-14 Phase 3 自查发现的三个缺陷

- **无缺口时凑不满 3 条依据**：只有 1 条要求的 JD 在"没有缺口"（= APPLY）时只剩 2 条依据，
  于是返回 `insufficient_grounds` 422 —— 把"JD 要求少"误判成"证据不足"。补一条**匹配概览**
  依据（`岗位共 N 条要求：已覆盖 X、弱命中 Y、缺失 Z、无法判定 W`）
- **`unknown` 不产缺口 → 完全没核实也输出 APPLY**：匹配 `unknown` 表示"材料完全对不上，
  无法判定"。原实现把它排除在缺口之外，于是一条关键硬性要求既不产生缺口也不阻断，
  最终输出 APPLY（"关键要求均有已确认证据支撑"）—— 而事实是什么都没核实。
  改为产出 `unverifiable` 缺口（非 blocking → STRETCH）
- **三份真实 JD 全部输出 PASS**：初版规则是"存在未解决的 P0 缺口即 PASS"，但**弱命中也是
  P0 缺口**，于是"材料能对上但强度不足"被判成"不可短期解决"。引入 `blocking`
  （该缺口是否不可短期解决）并**存进 `gaps.blocking`**，使判定可只从库里复现：
  学历门槛高于现有 / 要求证书而材料无相关字样 → PASS；弱命中或材料对不上 → STRETCH

### Added - 2026-09-14 迁移 `2026-09-14-phase3-gap-blocking`

`gaps` 增加 `blocking`（补列，非破坏）。老行默认 0（不阻断）——
无法从旧数据反推当时是否真的不可短期解决，重新分析会刷新。

- 回归门禁：pytest 423 passed (54.74s)、Node 36/36；schema / 敏感扫描 / `git diff --check` /
  public↔docs 镜像 / 双方言 DDL 同步 / vercel 死路由全部通过；真实 HTTP 冒烟 37/37

### Added - 2026-09-14 领域收敛：Career Evidence / TargetJob / Action / Application（Phase 2）

新增纯域层与数据层两包，把"什么算合法"从 `api/index.py` 与 `services/*.py` 里
抽出来。分层方向定为 Routes → Services → **Domain** → Repositories / Providers；
`domain/` 不 import Flask / `tools.database` / `services`，因此可以在无数据库、
无网络的条件下测试。

- `domain/evidence.py`：CareerEvidence。三条硬规则 —— 引文必填且必须是来源原文的
  逐字子串（与 F1 的 source_span 事实锁同口径）；模型产出（resume / interview /
  application_outcome）**不得**直接写成 confirmed，只有 `user_input` 可以；已确认
  证据的正文被修改会退回 pending，除非声明 `confirmed_by_user=True`
- `domain/career_profile.py`：CareerProfile 的六个分支是**同一批证据的视图**，
  不是第二套事实；`usable_evidence()` 是唯一对外入口
- `domain/target_job.py`：JobRequirement / EvidenceMatch / Gap / Decision。
  APPLY / STRETCH / PASS 写成可读谓词而非权重求和，且 `decide()` 会独立重算
  `expected_decision()`，结论不一致直接拒绝（不允许手写判定）；每条 Decision 至少
  3 条不重复依据
- `domain/interview.py`：出题优先级 P0 Gap > P1 Gap > 关键证据验证 > 行为问题 >
  通用题库；评估分数强制标注为**训练指标**，不得暗示招聘成功率；面试新经历走
  `candidate_evidence()` 必然是 pending
- `domain/action.py`：Gap → Action → Artifact → Outcome。没有 `expected_artifact`
  的动作不算闭环；只有 `done` 且带 artifact 才允许记录结果
- `domain/application.py`：7 态状态机（considering/preparing/applied/interview/
  offer/rejected/withdrawn），终态不可迁出；**新建默认 preparing 而非 applied**
  （原实现默认 applied 等于凭空断言已投递）；结果可反向写入待确认证据
- `repositories/`：唯一拼 SQL 的层。每条语句走 `database.render()` 以兼容双方言；
  所有查询带 `owner_key` 条件，归属隔离在数据层兜底
- 双方言 DDL 新增 9 张表 + `schema_migrations`；库内共 30 张

### Added - 2026-09-14 版本化迁移（D4：已授权迁移生产数据）

- `applications` 补 `target_job_id`（ALTER TABLE，非破坏）
- 历史 `status` 规范到 7 态；未知值兜底为最保守的 `applied` 并记入 `unknown_values`，
  不猜测
- 为历史 owner_key 补建 CareerProfile，**但不生成任何证据**
- **刻意不从既有 `diagnoses` 反向生成证据**：诊断的 `source_spans` 多是"实习经历"
  这类小节标题，变成职业事实会污染唯一可信源
- `/api/health` 新增 `migrations` 字段（`ok / applied / expected / error`），
  报告前先补跑未应用的迁移，避免"换了数据库却继续报 ok"

### Fixed - 2026-09-14 Phase 2 自查发现的四个缺陷

- **Decision 规则误判**：初版额外做了一层「P0 且 req_type == hard」过滤，但
  `priority_for` 已把 hard 唯一映射成 P0，且缺口记录不保存 req_type，导致"P0 硬性
  缺口"被判成 STRETCH。修正为只看优先级，并加测试锁住「P0 ⟺ hard」
- **迁移无法人工重跑**：`apply_all(force=True)` 会重复插入 `schema_migrations`
  版本行并撞主键。`_mark()` 改为幂等
- **`init_db()` 每次调用重放整套 DDL**：`repositories.base.cursor()` 每次都走
  `connection()` → `init_db()`，而 DDL 从不缓存；Phase 2 新增的 `applied_versions()`
  被 `/api/health` 调用，于是每个健康检查请求都在重放 29 张表 + 约 30 个索引
  （实测冷跑 75ms）。`init_db()` 改为按连接目标在进程内缓存一次，
  单次 `connection()` 从 ~82ms 降到 7.35ms
- **邮箱脱敏正则二次复杂度（先于 Phase 2 存在，但属生产缺陷）**：
  `[A-Za-z0-9._%+-]+@` 在"不含 @"的长文本上对每个起点都要吃到结尾再回溯找 `@`。
  接口明确接受 20 万字符简历、脱敏又是 WF-01 必经环节，实测 `deidentify(200_000)`
  需 **114.7 秒**，`test_text_maximum_length_accepted` 单用例 75.6 秒、占全量门禁的
  64%。加前瞻 `(?<![A-Za-z0-9._%+-])` + RFC 长度上限后降到 **10.3ms**，该用例
  **0.12 秒**，全量门禁 **234 秒 → 52.13 秒**；`tools/log_sanitize.py` 同一写法同步修正。
  语义不变（`a@b.co` 仍脱敏、`a @ b` 不误伤），有测试覆盖

- 回归门禁：pytest 392 passed (52.13s)、Node 36/36；schema / 敏感扫描 / `git diff --check` / 镜像一致

- 回归门禁：pytest 待记、Node 36/36；schema / 敏感扫描 / `git diff --check` / 镜像一致

### Removed - 2026-09-13 Phase 1 其余项（C7 预测 / 知识库 / 语音 / 死路由）
- **C7 预测区间彻底删除**：`tools/rescore.py` 不再输出 `C7_low`/`C7_high`（固定 0.30/0.70 演示假设），`services/interview_service.build_ability_profile` 与 `api/index.py` 的 `wf05/ability` 响应不再返回；`contracts/ability-profile.schema.json` 移除 `scenario_day7`（含 required）；`contracts/scoring.md` §4 改写为「C0 是当前证据快照，不是就业概率，也不是预测」。保留 `C0` 与六维分，并新增「不代表真实就业概率」的显式标注
- **前端同步**：`radar.js` 只画一条「当前证据快照」曲线（原三条：C0 + 七天推演 low/high）；`f4-report.html` 移除区间带与情景假设块，标题去掉「七天竞争力情景推演」；`index.html` 与 `mock-data.js` 同步；三份镜像一致
- **独立知识库产品下线**：导航与 `pages/kb.html` + `js/kb.js`（三树各一份）删除，`/api/knowledge/search`、`/api/knowledge/questions` 及两条 `vercel.json` 重写移除。`tools/knowledge.py` **保留**，作为 Interview Engine 的内部 Question Bank 数据源（待 Phase 3 接线）
- **整条语音链路删除**：`public/js/voice.js`（三树）、`tools/voice_handler.py`(398)、`tools/providers/asr.py`(113)、`scripts/p0-04-voice-validation.py`、`public|docs/voice-test-checklist.md`、`tests/test_new_tools.py`、`tests/test_voice_browser.py`；`/api/wf04/asr` 路由 + 重写 + OPTIONS 项移除；`.env.example` 删除 `ASR_API_URL`/`TTS_API_URL`/`BAIDU_SPEECH_TOKEN` 三个变量
- **死路由修复**：`/assets/:path*` 原重写到未部署的 `/ui/assets/:path*`，导致**所有页面的 favicon 线上 404**、`radar.js` 的本地 ECharts 兜底永不生效；现改为 `/public/assets/:path*` 并把 `assets/`（favicon / logo / vendor/echarts.min.js）纳入 public 与 docs 两棵发布树，同时加入 publish mirror 一致性测试
- 导航从 7 项收敛到 **5 项**（首页 / F1 / F3 / F4 / F5）；首页、各页导航、`scripts/sync_sidebar.py`、`test_publish_mirror.js` 同步
- 顺手修掉一个自引入缺陷：删知识库路由时误把 `/api/wf04/asr` 处理器改名为 `wf04/start`，造成与真实 `wf04/start` **重复路由**；已连带删除该 ASR 处理器，`wf04/start` 恢复唯一
- 删除陈旧生成物 `tests/e2e_closed_loop_results.json`（含过期 C7 文案，测试每次运行会重新生成）
- 回归门禁：**pytest 全绿**、**Node 36/36**；`vercel.json` 静态重写目标全部存在、`_route` 全部有处理器（**dead routes = 0**）；无残留 voice/asr/知识库代码引用

### Removed - 2026-09-13 专业→职业匹配整块下线（D1）
- 删除 `api/f2_major.py`（703 行）：专业目录检索、意向推荐、模式 A/B 匹配、`LEVEL_SCORE` 专业契合度，以及 `/api/f2/*` 全部端点（`health`/`majors/tree`/`majors/search`/`majors/<code>`/`match`/`intent`），现在统一返回 404
- 删除数据与脚本：`data/f2/majors_2025.json`、`data/f2/profiles_top30.json`（合计 175 KB）、`scripts/build_majors_data.py`、`scripts/validate_f2_data.py`
- 删除仅为该功能存在的异步分片任务子系统：`services/task_service.py`、`tools/tasks.py`、`/api/tasks` 系列端点在移除前只支持 `task_type="f2_match"`，无其它调用方
- 删除前端三套副本中的 `pages/f2-match.html`、`css/f2-major.css`、`js/f2-major.js`（public / docs / ui/prototype），以及 `data-bridge.js` 的 `matchMajor`、`createTask`/`getTask`/`advanceTask`/`pollTask`、`ENDPOINTS.tasks`/`ENDPOINTS.majorMatch`
- 导航与入口：首页与各页移除 F2 导航项、F2 一键体验按钮与 F2 功能卡；`quick-demo.js` 只保留 F1 一键体验并移除 `DEMO_JD`；`account.js` 历史记录不再把 F2 事件链到已删除页面；`scripts/sync_sidebar.py` 的页面清单同步移除
- F4 报告的 F2 行程节点改为不可点击的状态指示，避免跳转到已删除页面；节点文案沿用原文，留待导航重构阶段统一改名
- 数据库：`tasks` 表从双方言 DDL 移除，并在 `init_db()` 中对其执行幂等 `DROP TABLE IF EXISTS`（老库不留孤儿表）；`transfer_owner_data()` 不再尝试更新该表
- 保留但不再有页面挂载：`js/job-upload.js`（`/api/wf03` JD 解析→确认→匹配 UI）与 `job-upload.js` 相关测试。目标岗位分析的后端、数据桥与合同未做任何改动
- 回归门禁：**pytest 423/423**、**Node 38/38**；`schema validation` 通过；敏感信息扫描对 tracked+untracked 内容无发现；`pip_audit` 两份 requirements 未新增发现；`git diff --check` 通过；public/docs 镜像逐字节一致
- 新增回归门禁 `tests/test_phase1_deletions.py`（11 项）：下线端点在 GET 与 OPTIONS 下均 404、能力表不再含 `f2_major`、删除文件确实不存在、`api/index.py` 无残留 import、`vercel.json` 无 f2/tasks 重写、`tasks` 表不再创建且不再出现在 `transfer_owner_data`、`/api/wf03/match` 正向对照仍可用、publish 两树仍逐字节一致、publish 树不再出现已删页面引用

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
