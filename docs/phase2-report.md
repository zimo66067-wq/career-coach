# phase2-report.md · Phase 2（Domain Consolidation）

- 日期：2026-09-14
- 阶段目标：建立 `CareerProfile / CareerEvidence / TargetJob / EvidenceMatch / Gap / Action / ApplicationOutcome` 领域模型，并把 `applications` 的历史数据迁移到新模型
- 授权：D4 已由产品负责人决策 —— **允许迁移生产数据**
- 结论：**Phase 2 完成**，domain 与 repositories 两层就位、迁移可跑、门禁通过。**尚未接入 HTTP 路由**（Phase 3）

---

## 1. 修改摘要

新增两个包，共 17 个文件：

```
domain/                        纯领域规则，零 I/O 依赖
├── errors.py                  DomainError（带机器可读 code）
├── evidence.py                CareerEvidence + 三条不变量
├── career_profile.py          CareerProfile（六分支是证据的视图）
├── target_job.py              JobRequirement / EvidenceMatch / Gap / Decision
├── interview.py               InterviewSession 子实体 + 出题优先级
├── action.py                  Gap → Action → Artifact → Outcome
└── application.py             申请 7 态状态机 + 结果回写

repositories/                  唯一拼 SQL 的层
├── base.py                    connection/render/insert/update + 归属隔离约定
├── career_evidence.py
├── target_job.py
├── action.py
├── application.py
└── migrations.py              版本化、幂等迁移
```

**分层方向**（写入 `domain/__init__.py` 与 `repositories/base.py` 的模块注释）：

```
Routes  →  Services  →  Domain  →  Repositories / Providers
```

静态扫描确认：`domain/` 与 `repositories/` **不 import flask / api / services**。
因此域规则可以在没有数据库、没有网络的条件下测试 —— `tests/test_domain_model.py`
46 项，0.7 秒跑完。

### 领域模型要解决的具体问题

| 之前 | 现在 |
| --- | --- |
| "职业事实"没有任何实体，简历分数 / 匹配证据 / 面试引用块各说各话 | `career_evidence` 是唯一可信来源，改写 / 匹配 / 面试 / 求职信都必须读 `usable_evidence()` |
| 模型产出可以直接当成事实 | 三个模型来源（resume / interview / application_outcome）**禁止**直接写入 confirmed |
| 匹配结论是 0-100 分，不可解释 | `decide()` 只输出 APPLY / STRETCH / PASS，且必须 ≥3 条不重复依据，并独立重算校验 |
| 新建申请默认 `applied`（凭空断言已投递） | 默认 `preparing`，投出去由用户显式确认 |
| 无迁移机制 | `repositories/migrations.py`，`/api/health` 可观测 |

---

## 2. 删除内容

Phase 2 以新增为主，**只删除了两处恒真式**：

- `domain/target_job.py`：删除 `_has_unresolved()` 的 `requirement_types` 过滤参数与
  `_requirement_type_of()` 辅助函数（见 §5 缺陷 1）
- `data-bridge.js` 未动；前端本阶段无改动

---

## 3. 受影响文件

| 文件 | 变化 |
| --- | --- |
| `tools/database.py` | 双方言 DDL 各 +9 表；`applications` +`target_job_id`；新增公共门面 `connection/render/insert_id/utc_iso/has_column/table_names/db_path`（此前这些是 `_` 私有名，仓储层不该依赖私有名） |
| `api/index.py` | 冷启动执行迁移；`/api/health` 新增 `migrations` 字段 |
| `CHANGELOG.md` | Phase 2 条目 |
| `docs/domain-model.md` | 新增（领域模型参考） |
| `docs/architecture.md`、`docs/dependency-map.md` | 追加 Phase 2 更新块，标注哪些审计结论已失效 |
| `tests/test_domain_model.py` | 新增 46 项 |
| `tests/test_migrations.py` | 新增 12 项 |

---

## 4. 迁移设计（D4）

两条版本：

| 版本 | 内容 |
| --- | --- |
| `2026-09-13-phase2-application-status` | `applications` 补 `target_job_id`（ALTER TABLE）；历史 `status` 规范到 7 态 |
| `2026-09-13-phase2-career-profiles` | 为历史 owner_key 补建 CareerProfile |

设计要点：

1. **建表是加法，改数据才需要迁移。** 9 张新表由 `CREATE TABLE IF NOT EXISTS` 建；
   迁移只负责"列补齐 + 状态规范化 + 档案回填"。
2. **不猜测脏数据。** 未知历史状态值兜底为最保守的 `applied`，并把原值记入
   `unknown_values` 上报。实测本仓库 API 从未写过 `status`（默认 `'applied'`），
   所以真实生产库大概率 `statuses_normalized == 0`。
3. **刻意不从 `diagnoses` 反向生成证据。** 诊断的 `source_spans` 引文多为
   "实习经历"这类小节标题，把它变成"职业事实"会直接污染唯一可信源。证据必须由
   用户确认后进入，迁移不代替用户做这件事。有专门测试锁住这条。
4. **`/api/health` 先补跑再上报**，避免"换了数据库却继续报 ok"。

---

## 5. 测试结果

```
pytest                     392 passed (52.13s)
node --test tests/*.js     36 passed / 0 failed
schema 校验                resume + job + ability 全部 OK
敏感扫描（tracked+untracked）242 文件  无发现
git diff --check           干净
public↔docs web 资产       26 个同名文件，0 处内容差异
双方言 DDL                 各 29 张表（+schema_migrations = 30），无漂移
迁移 CLI                   可直接 `python -m repositories.migrations` 运行，二次运行无操作
真实 HTTP 冒烟             21/21（含 health.migrations、4 条已下线路由 404、10 张表存在）
```

新增 **61 项**（domain 46 + migration 13 + deidentify 复杂度回归 2）。迁移测试不是拿新库
跑一遍：它用手写的旧 DDL 建一个**真的没有 `target_job_id` 列、status 为 `submitted` /
`interviewing` / `saved` / `weird_value` 的库**，再断言迁移结果。

Phase 1 结束时全量为 `331 passed (108s)`；本轮 `392 passed (52s)` —— 用例数增加而总耗时
减半，原因是修掉了缺陷 4。

### 测试自查发现并修复的四个真实缺陷

**缺陷 1 · Decision 规则误判（严重）**

初版 `expected_decision()` 额外做了一层「P0 且 `req_type == hard`」的过滤。但有两点
使它必然出错：`priority_for()` 已经把 `hard` **唯一**映射成 P0；而 `gaps` 表里
**没有 `req_type` 列**，缺口记录也不保存它。结果是传 `requirements=None` 时，
`gap.get("req_type")` 为 `None`，**"P0 硬性缺口"被误判成 STRETCH**。

修正后只看优先级（P0 → PASS，P1 → STRETCH，否则 APPLY），并删除那层无用过滤；
新增测试 `test_only_hard_requirements_can_produce_a_p0_gap` 锁住「P0 ⟺ hard」这个
映射，防止再次引入同类错误。

**缺陷 2 · 迁移无法人工重跑**

`apply_all(force=True)` 会重跑迁移函数，但 `_mark()` 无条件 INSERT 版本行，
第二次就撞 `schema_migrations` 主键并抛 `IntegrityError`。而 `force=True` 恰恰是
人工排障路径。修正为幂等（已记录则跳过），并加断言检查重跑后版本行仍只有 2 条。

**另外两处按域测试暴露的口径修正**：

- `Action` 状态机原本不允许 `todo → done`，导致"当天做掉一件小事"这个主场景
  无法标记完成（`open_from_gap()` 建出来就是 `todo`）。改为允许，保留
  `done → doing` 返工与 `dropped` 终态。
- `interview.candidate_evidence()` 的引文事实锁需要一个 `answer_text` 参数才能生效
  （签名里本就有），测试初期漏传，暴露了"不传就退化为无校验"的风险，已在测试中
  显式覆盖 `quote_not_verbatim`。

### 缺陷 3 · `init_db()` 每次调用都重放整套 DDL（性能，Phase 2 自引入）

根因：`repositories.base.cursor()` 每次都走 `database.connection()`，而
`connection()` 里是 `init_db() + _get_conn()` —— **`init_db()` 无条件重放整套
DDL**（29 张表 + 约 30 个索引，实测冷跑 **75ms**）。

Phase 2 之前没有仓储层，所以没人高频调 `connection()`；本阶段新增的
`applied_versions()` 被 `/api/health` 调用，于是**每个健康检查请求都在重放建表脚本**。

修法：`init_db()` 按连接目标（SQLite 取解析后的路径，PG 取 `"postgres"`）在进程内
缓存一次；DDL 全是 `CREATE ... IF NOT EXISTS`，重放只是白跑、从不是正确性要求。
提供 `reset_init_cache()` 给测试用。实测单次 `connection()` 从 ~82ms 降到 **7.35ms**，
并新增回归测试 `test_schema_ddl_is_not_replayed_for_an_initialised_database`
（用计数版 `_get_conn` 断言已初始化的库不再触碰 DDL，且清缓存后必须真的重跑一次）。

> 说明：这一条起初被我误判为全量门禁变慢（108s → 234s）的原因。逐用例计时后证实
> 主因是缺陷 4（单用例 139.8s），本条只是"本来可以更早便宜"的正确性改进。两条都修了。

### 缺陷 4 · 邮箱脱敏正则是二次复杂度（**先于 Phase 2 存在**，但属生产缺陷）

`tools/deidentify.py` 与 `tools/log_sanitize.py` 的 `RE_EMAIL` 原本是
`[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`。在"**没有 `@`** 的长文本"上，
引擎对每个起点都要把字符类吃到结尾、再逐字回溯去找 `@` —— 呈二次复杂度。

影响是实际的：接口**明确接受 20 万字符简历**（`test_text_maximum_length_accepted`
断言 200_000 字必须被接受），而脱敏是 WF-01 的必经环节。实测：

| | 修复前 | 修复后 |
| --- | --- | --- |
| `deidentify(20_000)` | 1,213.6 ms | **0.9 ms** |
| `deidentify(200_000)` | **114,678.4 ms** | **10.3 ms** |
| `log_sanitize.sanitize(200_000)` | ~5,700 ms（外推） | **25.1 ms** |
| `test_text_maximum_length_accepted` | **75.6 s** | **0.12 s** |
| 全量门禁 | **234 s** | **52.13 s** |

修法：加 `(?<![A-Za-z0-9._%+-])` 前瞻，使匹配只能从"局部段之外"开始（同一段
`aaa...` 里只有局部段起点会被尝试，其余位置 O(1) 否决），并按 RFC 上限给局部段
（≤64）与域名段（≤255）加长度边界。语义不变：`a@b.co`、`zhang.san+job@sub.example.co.uk`、
`前缀xxxxfoo@bar.com` 仍被脱敏，`a @ b`、纯中文长文本不误伤 —— 有测试覆盖。
两个模块的写法保持一致并在注释里注明原因。

**这条说明：Phase 0 审计里"规则型 API p95 < 800ms"（Phase 16 验收项）在修复前是
不可能达标的，而当时没有任何测试能发现它 —— 因为唯一覆盖长文本的用例只是"能通过"，
从不计时。**

修法：`init_db()` 按连接目标（SQLite 取解析后的路径，PG 取 `"postgres"`）在进程内
缓存一次；DDL 全是 `CREATE ... IF NOT EXISTS`，重放只是白跑、从不是正确性要求。
提供 `reset_init_cache()` 给测试用。实测单次 `connection()` 从 ~82ms 降到 **7.35ms**，
并新增回归测试 `test_schema_ddl_is_not_replayed_for_an_initialised_database`
（用计数版 `_get_conn` 断言已初始化的库不再触碰 DDL，且清缓存后必须真的重跑一次）。

---

## 6. 性能结果

Phase 2 **没有新增任何 HTTP 路由**，因此对外延迟不变（Phase 1 基线：规则型接口
p95 45.5 / 60.7 / 1.1 ms）。新增的成本在冷启动：

- `ensure_applied()` 按数据库路径缓存，进程内只跑一次；`/api/health` 上的调用是
  一次 set 查找。
- 迁移本身是 1 次 `PRAGMA` 级列检查 + 1 次全表 `SELECT id, status`（表很小）+ 1 次
  owner_key 去重查询。空库实测可忽略。
- `init_db()` 现在按连接目标在进程内缓存（见 §5 缺陷 3），单次 `connection()`
  从 ~82ms 降到 **7.35ms**。

### 门禁耗时本身的一个真实缺陷（详见 §5 缺陷 4）

第一次跑全量门禁用了 234 秒（Phase 1 是 108 秒），`--durations` 显示
**单个用例 `test_api_boundary.py::test_text_maximum_length_accepted` 占 139.8 秒**，
即整套的 64%。定位到 `tools/deidentify.py` 的邮箱正则是二次复杂度：20 万字符要
114.7 秒。这不是 Phase 2 引入的（Phase 1 的 108 秒里也含这条用例，只是当时机器负载
不同），但它是一条**真实的生产缺陷**：接口明确接受 20 万字符简历，脱敏又是 WF-01
必经环节，一次合法上传即可占满请求线程。

修复后：`deidentify(200_000)` **114,678ms → 10.3ms**，该用例 **75.6s → 0.12s**，
全量门禁 **234s → 52.13s**。

---

## 7. 剩余风险

| # | 风险 | 说明 | 计划 |
| --- | --- | --- | --- |
| 1 | **domain 尚未接线** | 没有 CareerProfile / TargetJob / Decision 的 HTTP 路由；`js/job-upload.js` 仍无宿主页面 | Phase 3 |
| 2 | `api/index.py` 在 import 期跑迁移 | 若未来把 `app` 拆成工厂函数，迁移调用点要跟着搬 | Phase 5 拆 `api/index.py` 时一并处理 |
| 3 | 既有 2 处依赖倒置未修 | `diagnosis_service.py:324`、`interview_service.py:50` 仍 `from api.index import build_model_router` | Phase 5 |
| 4 | PostgreSQL 分支未经真实连接验证 | 双方言 DDL 已做静态一致性核对，但本机只有 SQLite。生产用 `DATABASE_URL`（Postgres）时需真机验证一次 | 上线前 |
| 5 | Coverage 未达标 | Phase 0 基线 Python 79%、JS 0%（契约型）。本轮新增的 domain/repositories 覆盖良好，但全局仍未到 85/90/75 | Phase 15 |
| 6 | `ui/prototype` 陈旧分叉仍在 | 含 7 处坏引用（Phase 1 之前就坏），未部署 | Phase 6/7 |
| 7 | 其余长文本正则未经同口径审查 | 本轮只修了 `RE_EMAIL`（唯一实测二次的）。`log_sanitize` 的 JWT/AK-SK 规则、`interview_engine` 的敏感词表未做 20 万字符压力测试 | Phase 16 性能验收时统一做 |

---

## 8. 口径（不得对外声称的事）

Phase 2 交付的是**模型与迁移**，不是可用功能。因此：

> **当前不得对外声称已具备 "Career Evidence Profile" 或 "APPLY / STRETCH / PASS
> 决策" 能力。** 这些是 Phase 3 的交付物 —— 领域规则已就位、数据表已就位、
> 迁移已可跑，但用户在界面上还看不到任何入口。

同时 `js/job-upload.js`（JD 解析→确认→匹配 UI）**仍无页面挂载**，Phase 1 报告中
的这条口径继续有效。

---

## 9. 下一步（Phase 3 前置条件）

Phase 3（Core Flow：Resume → Evidence → Target Job → Match → Decision → Interview）
可以直接开始，但需要在设计上先定一件事：

**D8（建议新增决策点）· 简历诊断 → 证据的转换策略。**

诊断结果转成 `career_evidence` 有两条路：

- **A（推荐）**：诊断只产出**候选证据**（`source_type='resume'`，
  `status='pending'`），用户在 Career Profile 页逐条确认。符合"AI 不能写入已确认
  事实"的不变量，但用户在拿到第一个 Decision 之前多一步确认。
- **B**：诊断直接落成 confirmed（仅限有 `source_span` 逐字引文支撑的条目）。快，
  但把"模型抽取"当成了"用户陈述"，与 §3.2 的不变量直接冲突。

我倾向 **A**，并且这与 DoD #18「首次用户到第一个 Target Job Decision ≤3 分钟」并不
冲突 —— 确认可以批量化（"这 6 条里哪几条不对？"）。但这条影响主路径步骤数，属于
产品决策，不替你定。

另外 D5（`workflows/` 去留）、D6（`deliverables/` 归档）仍悬空，不阻塞 Phase 3。
D3（单位/职位数据授权）仍阻塞 F5 阶段 2。
