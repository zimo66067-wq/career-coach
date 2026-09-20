# Changelog

格式遵循 Keep a Changelog；每次冻结记一条。commit hash 在实际提交后回填。

## [Unreleased]

### Changed - 2026-09-20 观察面扩面与死链归零（Phase 8）

> 提交：`5d6b27d`（判据改造 + 死链归零，32 文件）+ `2e17c02`（报告与决策记录，4 文件）。
> 相对 `58a8383`、**截至 `2e17c02`** 合计 **36 文件 / +1302 −185**。
> （不含本条回填自身的几行 —— 本文件每声明一次总数，那个数就立刻过期，
> 所以这里只声明"截至哪个提交"，不再自称"本阶段总计"。）
> 门禁：`work/gate8.sh` **17 步（0~16）全部 PASS，退出码 0**；变异注入 **15/15 全部被抓到**。

Phase 7 把**结构**拆完了，这一轮补的是**判据的观察面**。Phase 7 结束时判据只看着
**8 份**活文档，而仓库里有 56 份在描述"现在是什么样" —— 也就是说，近一半的引用
（436 / 955）**从来没有被任何东西看过**。扩面当场报出 **162 处死链**，全部修到 0。

- **观察面从判据里挪出来，成了可判对象 `contracts/living-docs.json`**：56 条 `living`
  （逐条写 `why`）、17 条 `historical` 族、**14 对镜像**（逐对登记）、3 条 `excluded_forms`、
  一句 `precedence`。清单缺失或损坏时判据**不降级**（宁可红），因为"悄悄退回写死的 8 份"
  正是那种"看着很宽其实只看了 8 份"的状态
- **判据改读清单**（`scripts/live-doc-path-check.py`，+181 / −17），并补三条**双向**自检：
  A 清单条目必须在实仓落得下（防幽灵条目）、B 实仓含引用的 md 必须全部登记（防漏登记）、
  C 每条 `historical` glob 至少命中 1 个文件（防装饰性规则）。另有探针 17/18/19 钉住
  最容易回退的三处语义：`deliverables/**` 必须能豁免**深层**文件、`living` 优先于 `historical`、
  `docs/index.md` 与 `public/index.md` **必须被判为不一致**（这一对同名但语义不同，
  是"同名 ≠ 镜像"的实物证据）
- **新增门禁第 16 步：观察面清单的独立复算**（`scripts/living-docs-scope-check.py`，197 行，
  **不 import 判据**）。同一份实现自查只能证明"它和自己一致"。它专门覆盖第 10 步**看不见**的
  两种形态：**空判豁免**（某条 glob 命中的文件全部已是 `living`，它一个都没豁免）与
  **观察面被吞成空集**；另带一条反向控制探针（两份同名 index.md 必须内容不同），
  少了它，"镜像逐字节比对"全绿可能只是因为那个比对恒真
- **新增 `tests/test_phase8_contract.py`（8 项）**：用临时清单证明观察面是**数据驱动**的
  （换一份清单，`LIVING_DOCS` 必须跟着换），并钉住"清单缺失/非法/条目缺理由 → 必须返回问题"
  三种不许降级的情形
- **162 处死链**（25 个文件）分两类：**146 处**是 `tools/` 搬家的机械重定向
  （`work/rewrite8-links.py`，每处声明期望替换次数，对不上就拒绝写盘；`EXPECTED` 表可复算，
  含 7 个"期望 0 处"的模块 —— 让"漏掉某个 7d 搬过的模块"这件事可判）；
  **16 处**路径搬家解决不了、按内容改写
- **修掉能力表里的假陈述**：`docs/capability_matrix.md`（及 `public/` 镜像）的语音能力表
  V1~V5 原写「待验证 / **已验证**」，而 `4367ec5` 已把整条语音链删掉 —— V3/V5 的「已验证」
  是**随证据失效的假陈述**（证据文件 `tests/test_voice_browser.py` 已不存在）。状态改为
  **已移除**，并在段首说明为什么。同类处理：`tests/TEST_PLAN.md`（前端契约改到
  `test_upload_progress.js`）、`docs/domain-model.md`（`job-upload.js` 标注已退役）
- **"修链"与"判链"共用同一判定函数**：修链脚本第一版用「文本里出现过旧路径」当条件，
  干跑报 182 处，其中包含 `tools/knowledge.py` —— 那是**账本里的历史引用**，判据刻意豁免它。
  第一版会改掉那句注记（等于篡改记录）。重写版 `import` 判据模块、**只改 `verdict == "offender"`**
  的位置，改完后那一处归零，正好证明豁免生效
- **D5 / D6 收口为「保留原地、不归档」**（原口径「Phase 7 统一归档」作废，Phase 7 全程未执行）。
  理由：D5 的立论依据「`workflows/` 全仓代码 0 引用」只覆盖 import 一个方向，
  漏掉三条真实在用的引用面 —— 答辩证据索引（Q10/Q11/Q15/Q22/Q26 指向 `workflows/wf-06-ops.md`、
  `wf-04-interview.md`）、冻结清单（`scripts/p0-07-freeze.py` 把 `workflows/*.md`、
  `deliverables/**/*` 登记为交付组）、运行期写路径（`run-wf-e2e.py`、`run-rehearsal.py`、
  `p0-05/06/07`、`backup-sessions.py` 默认往 `deliverables/` 下写）。见 `docs/product-scope.md` §10.6。
  `workflows/*.md` 自身也不是"只读说明书"：正文是可执行命令
  （`python domain/validate_schema.py …`），上面那 146 处重定向里有一大块落在它身上
- **判据的接口变了，调用方跟着变**：`test_phase7d_contract.py` 的
  `_load_live_doc_judge()` 从"加载模块"改成"加载模块**并完成清单装载**"，装载报错即失败
  （门禁首轮因此 1 failed / 510 passed，是预期内的接口变更，不是缺口回归）
- **判据的裁决文案里不再写会漂移的数字**：门禁第 14 步原写"观察面 96 个模块"，
  本轮新增一个脚本后实际 97 —— 写死的数字在下一轮就变成假陈述。真实条数由脚本每次实测打印
- **裸 `.py` / `.md` 名刻意不收**（实测 23 处，观察面内仅 1 处）：同一写法混了"现在该存在 /
  计划产出 / 仓库外脚本"三种语义，收了就是制造假阳性，而假阳性会让下一个人把整条判据删掉。
  理由与实测数写进清单的 `excluded_forms` —— **"不收"是一个决定，不是遗漏**
- **`CHANGELOG.md` 与 `deliverables/` 里的历史记录一字未改** —— 改掉就是伪造历史

### Changed - 2026-09-17 归并 `tools/`（Phase 7d）

> 提交：`47b4167`（结构重构 112 文件）+ `e47989a`（文档记录 8 文件）。
> 相对 `51212cb`、**截至 `e47989a`** 合计 **120 文件 / +2003 −431**。
> （不含本条回填自身的几行 —— 本文件每声明一次总数，那个数就立刻过期，
> 所以这里只声明"截至哪个提交"，不再自称"本阶段总计"。）
> 门禁：`work/gate7d.sh` **16 步（0~15）全部 PASS，退出码 0**；变异注入 **17/17 全部被抓到**。

Phase 7 的**最后一个**子阶段。**纯结构重构，对外行为零变化** —— 可证：把每个被搬走的模块
相对 HEAD 的每处改动做一次"引用归一化"，旧行与新行必须逐字相同；实测 **7 个逐字节相同 /
12 个只改引用 / 4 个已声明**（3 处散文 + `trace` 拆分），合计改动仅 `-29 / +59` 行。
脚本 `work/verify7d-moves.py`，任何时候都能重跑。

- **`tools/` 整层消失**：23 个模块 / 6440 行 → **22 个 `git mv` + 1 个拆分**。
  `domain/` 10、`domain/internal/` 6、`providers/` 5、`repositories/` 1（`database.py`）、
  `services/` 1（`account.py` → `account_service.py`，唯一改名的，为了跟同层的 `*_service.py` 命名一致）。
  删除 `tools/requirements.txt`（逐行是根清单的子集）。**空目录都不留** ——
  那会让 `tools` 变成可 import 的命名空间包、`import tools` 静默成功
- **全仓 249 处引用改写**（点号 import 208 + 扁平 import 41）。字符串形态的引用
  （`sys.path.insert(0, "tools")`、`monkeypatch("tools.model_router.urlopen")`、
  `ROOT/"tools"/"database.py"`、CI 里的 `python tools/validate_schema.py`）单独一轮处理，
  **每一处都声明期望的替换次数，对不上就拒绝写盘**
- **新增 `domain/internal/`**：`dependency-map.md` §5 第 4 条的"或降级为 `domain` 的内部工具"
  被读成一个具体的包 —— 放进 6 个"**是机制、不是领域规则**"的模块
  （`api_errors` / `contracts` / `extract_text` / `log_sanitize` / `radar_adapter` / `trace`），
  并附带一条硬约束：**成员必须是叶子**（仓库内零依赖）
- **新增分层规则 6**：`providers → domain` 是唯一允许的反向边，且**只允许指向叶子模块**。
  由 `providers/model.py` 要抛 `ApiError` 逼出来；反向边指向叶子就没有传递性。
  判据同时要求那条边**真的存在且目标真是叶子**（否则"providers 压根不碰 domain"时也是绿的）
- **`tools/trace.py` 拆成两半**：`domain/internal/trace.py`（纯的 `new_trace_id` /
  `TRACE_ID_PATTERN`）+ 新文件 `api/trace.py`（要 Flask 请求上下文的 `trace_id()`）。
  **触发拆分的是判据不是审美**：并进 `domain/` 后，`tests/test_layering.py` 规则 2
  （domain 不得 import flask，**函数体内的也算**）立刻把那个函数内延迟 `import flask` 报了出来。
  拆分依据是消费者清点：`trace_id()` 的 4 个消费者全在 `api/`
- **新增门禁第 15 步「`tools/` 零残留」**：shell 分支（目录不存在 + `import tools` 抛错）
  与契约测试（23 条映射逐条命中、AST 无 `tools.*` import、字符串常量残留白名单、
  `__file__` 深度、mock 目标可解析）**两路**，因为它们会以不同方式失效
- **门禁第 14 步的观察面从 `api/` 扩到 5 个生产层 + `scripts/`**（24 → 96 个模块）。
  **扩面当天就抓到一条与本阶段无关的老 bug**：`services/diagnosis_service.py::normalize_score`
  用 `re.fullmatch` 接住"provider 把分数写成数字字符串"的分支，但该模块从未 `import re` ——
  模型返回 `"85"` 时 `diagnose_resume()` 就是 `NameError`。已补 `import re` +
  `tests/test_phase5.py` 回归用例（6 种输入）
- **修掉三处"藏在引用里"的缺陷**（既不是 import、也不含 `tools` 字样）：
  `domain/internal/contracts.py` 的 `parents[1]` 在深一层后指错目录（**13 个测试模块在收集期
  FileNotFoundError**）；`test_model_router_providers.py` 的 8 处 `patch("model_router.urlopen")`
  裸模块名（只在 `patch` 执行那一行炸，报错像环境问题）；`domain` 里的函数级 `import flask`
- **修掉 4 处写死老路径的活文档**：`HANDOFF.md`（代码分层表 + 门禁命令）、
  `contracts/README.md`、`contracts/scoring.md`。
  **`CHANGELOG.md` 与 `deliverables/` 里的历史记录一字未改** —— 改掉就是伪造历史
- **判据的观察面补一种形态：仓库内路径（`<层>/…/<文件>.py|md|json`）。**
  原先 `scripts/live-doc-path-check.py` 只认 `pages/*.html` 与 `js/*.js`，
  `tools/validate_schema.py` 这种写法**根本抽不出来** —— `contracts/*.md` 里那两处死链
  是**没有任何判据在看着**的情况下人工扫出来的。现在活文档 5 → **8 份**、
  引用 121 → **436 处**（310 存在 / 126 历史语境 / 0 死链）。
  第一版扩面报 68 处、只有 40 处为真，于是加两条收窄（**每一条都在代码里写了理由**）：
  ① 首段必须是仓库顶层目录名 ∪「已消失的层」清单（挡住仓库外的 `work/…` 与部署 URL 路径，
  同时**继续认 `tools`**）；② 词表加「基线」「旧路径」，章节标题沿父子链遗传但不含 H1
  （`architecture.md` 的 H1 里就有"审计"，让 H1 生效等于整份文件一次豁免）。
  「快照」**仍然不豁免** —— 6b-2b 那条教训不回退
- **`docs/` 三份审计文档按"现况断言改对、基线测量不改"分开处理**：§1 技术栈 / §5 / §6 / §7 / §8
  里的路径逐条改成归并后的真实路径（顺手把 `tools/contracts.py:25` 这类**行号**换成符号引用，
  行号会自己漂移）；§11 覆盖率基线**一个字不改**（那是 2026-09-13 的实测值，
  改路径等于伪造测量），靠标题里的「基线」声明豁免
- **新增判据**：`tests/test_phase7d_contract.py`（13 项，含映射表可复算、残留白名单必须写理由、
  `__file__` 深度、mock 目标可解析、以及"改坏一条映射必须报"的自检；
  `test_live_doc_judge_covers_the_path_form` **把活文档判据脚本加载起来跑**而不是 grep 源码）；
  `tests/test_layering.py` 新增规则 6 与 `test_the_providers_rule_can_fail`；
  `scripts/api-import-check.py` 新增 `--roots`；`scripts/live-doc-path-check.py` 新增 `path` 形态
- **变异脚本自己踩到一条门禁早就记过的坑**：pytest 在这个环境里**退出码不可信**
  （atexit 的临时目录清理被 safe-delete 垫片拦下抛 `SystemExit`），首次真跑 17 条里
  3 条 MISS 全由它造成，而测试其实已经红了。改成与 `gate7d.sh` 第 1 步同口径（只认摘要行）
- **规模口径的一处修正**：§21.6 原先估 `tools/` 是"6252 行 / 20+ 模块"，
  实测 **6440 行 / 23 个模块**（多 188 行、多 3 个模块）

### Added - 2026-09-17 拆 `api/index.py`（Phase 7c）

> 提交：`bf738fd`（拆分 32 文件）+ `82688d4`（文档记录 4 文件）。
> 相对 `131f83d`、**截至 `82688d4`** 合计 **36 文件 / +3515 −1580**。
> （不含本条回填自身的几行 —— 本文件每声明一次总数，那个数就立刻过期，
> 所以这里只声明"截至哪个提交"，不再自称"本阶段总计"。）
> 门禁：`work/gate7c.sh` **15 步（0~14）全部 PASS，退出码 0**；变异注入 **14/14 全部被抓到**。

Phase 7 的第三个子阶段。**纯结构重构，对外行为零变化** —— 逻辑一行没改写，
可证：把原文件的分支区间与 14 个 handler 的函数体各自做「非空行计数器」，
两边**逐行相等含重数**（831 行全部对上，去重 598）；比对方（基线副本）也与
`git show 131f83d:api/index.py` **逐字节相同**。

- **1621 行的入口 → 24 个模块，入口只剩 108 行**（`route_api()` 原 917 行 / 664–1580 行，
  内含 38 个 `if route ==` + 12 个 `route.startswith(` = 50 个路由分支条件；
  被搬走的区间 688–1578 共 891 行）。拆法：`api/app.py` / `constants.py` / `sentinel.py` /
  `startup.py` / `http_layer.py` / `security.py` / `validation.py` / `routing.py` /
  `dispatch.py` + `api/handlers/*` 14 模块
- **`api/index.py` 不改名**：`vercel.json` 的 `functions` 指向它、`vercel-dead-routes.py`
  是 `from api.index import app` —— 文件名与 `app` 变量名是**部署契约**。
  `REPOSITORY_ROOT` + `sys.path` 插入也留在入口（线上 `tools/` / `services/` 能被 import 全靠它）
- **哨兵下沉到叶子模块**：`dispatch ⇄ handlers` 是真 import 环，实测真写一次就
  `ImportError: cannot import name 'dispatch' from partially initialized module 'api.dispatch'`
  —— 与 `dependency-map.md §3.5` 警告的形态同源。`UNHANDLED` 因此住进
  `api/sentinel.py`，两个方向都只依赖叶子
- **入口的再导出面变成双向判据**：`imported − 本模块用过` = 纯再导出，必须**真的有人在取**。
  这条把 `migration_status` 正确地挤掉了（消费者已改从 `api.startup` 取），
  并暴露出 `tests/test_migrations.py` 里一句注释在断言"它仍然再导出"——**注释是错的，已修**
- **打桩点跟着实现搬**：`extract_txt` / `ocr_pdf` / `consent_serializer` 已不在 `api.index`，
  仍打在那里就是空判。7 个测试文件被迫改，并新增一条守卫用例：打桩目标不存在时要**响亮地失败**
- **新增门禁第 14 步** `scripts/api-import-check.py`（用 `symtable` 走解释器自己的作用域规则）：
  这是本轮**唯一的新失效模式** —— 某个模块少 import 一个名字，只在没被用例覆盖的那条分支上
  `NameError`，于是 pytest 会绿、评审会漏。前 13 步没有任何一步看得见它。含 13 项自检探针
  （3 项是"必须报错"的反向探针）
- **新增 `tests/test_phase7c_contract.py`（12 项）**，每条主判据配一条反向探针
- **修掉门禁自己的两个洞（都在第 6 步 / 整体退出码上，见 phase7c-report §4）**：
  ① 第 6 步 `git diff --check HEAD` 在 `git` 不在 PATH 时执行的是 `command not found`，
  `&&` 短路后**那格什么都不打印**，读起来和 `clean` 一样 —— `gate7b.log` 就是这样，
  那格应视为**未验证**；② 门禁**恒以 0 退出**，所以"看退出码"本身是空判
  （实测外层 wrapper 报 127 而门禁一步没跑）。现在 git 走绝对路径 + 前置断言，
  且每步结论进汇总、任一步失败即 `exit 1`
- **修掉四处写错的规模数字**：入口「101 行」实测 105（改这个数字的动作又把它变成 106）、
  「39 条 `if route ==`」实测 38、「50 条本地路由规则」实测 49、「参数化 13 条」实测 15；
  另有「919 行 `route_api()`」实测 917。新增 `work/verify-numbers.py` 把每条断言与它的算法钉住
  ——**会自我漂移的量（行数）改为判不变量（膨胀比 1.457，落在 1.3~1.6）**，只记快照
- **门禁判据 13 步 → 14 步**（另加"第 0 步"git 可用性前置断言）；pytest 482 → **495**；
  敏感扫描 252 → **277** 文件
  （+25：23 个新 `api/` 模块 + 1 个门禁脚本 + 本阶段报告；新契约测试在 `tests/`，
  该目录本就在扫描口径之外）
- 变异测试 `work/mutate7c.py` **14/14 全部被抓到**。其中"成环"要两条注入分开证：
  真写 reverse import 证**环是真的**（连收集都过不去），死代码里的 reverse import 证**判据是活的**

### Added - 2026-09-17 wf03 路由去留 + 公开文档范围（Phase 7b）

Phase 7 的第二个子阶段。**没有新能力，对外行为零变化**。两件事都**先问对问题再动手**：
「消费者是谁」与「这个集合现在是什么」。两处此前各被挂起过一次（6a / 6b-1）——
**挂起不是决定，而且挂起没有触发条件**，所以都在本轮第三次出现。

- **`/api/wf03/*` 三条路由保留，它不是死接口。** 上一轮的推理链断在最后一步：
  「前端没人调」被读成了「没人调」。实测消费者全在浏览器之外 —— `wf07` 那套
  DuMate 工作流分类法（`GET /api/health` 的 `workflows` 段报告 `"wf03": "available"`）、
  公开材料 `capability_matrix.md` 的 **N7/N9** 两行（把 WF-03 标为已验证）、
  `scripts/run-rehearsal.py` 的彩排链中段（consent → diagnose → **jd → match** → …）。
  **与 7a 那条教训同形**：判据的观察面（前端）窄于它要判的语义（有没有消费者）——
  7a 表现为判错文案，7b 表现为**差点删掉一份公开能力声明**
- **`public/*.md` 公开范围从"隐式"变成"可判"**：Vercel 静态根是 `public/`，
  所以**把文档放进 `public/` 与把它发布出去是同一个动作**，没有中间态。
  此前没人能回答"当前公开集合是什么"（`public/index.md` 只索引 12 份、
  `dependency-map.md §4.5` 只列 7 份、镜像判据明确排除 `.md`）——
  6a 与 6b-1 写"属产品/隐私决策"**不是推诿，是当时确实没有可判的对象**。
  实测 **16 份**、`sensitive-scan.py` 全部无发现，**一份都没撤**；
  新增 `contracts/publish-scope.json`（逐份记录路径 + 用途分类 + **公开的理由**）
  与 `scripts/publish-scope-check.py`（全向比对：增 / 删都红 + 空判防线 + 8 项自检探针）。
  撤出公网现在是一步的事：删文件 + 改清单
- **修掉「自述文件描述的不是它所在的那棵树」**：`public/index.md` 标题写成
  「docs 文档目录索引」，内容是 `docs/index.md` 的真子集，且漏掉自己树里 4 份 md。
  与 6a 修掉的「死树自述」同类。现名「职跃AI · 公开文档索引」，列全本树 15 份
- 两棵发布树的 `README.md` 恢复一致（6a 刻意对齐过，`.md` 不在镜像不变量内，
  这条一致性此前没有判据）；两份都补上 wf03 的决议结论
- 新增 `tests/test_phase7b_contract.js`（8 项）。**判据抓出了正文的事实错误**：
  第一版断言「WF-03 的证据行指向 `tests/test_api.py`」，而实测那两行的证据列是
  `[CAP-008]`/`[CAP-010]`（`tests/test_api.py` 是 WF-02/WF-04 的写法）——
  我把别处看到的模式顺手填进了证据列，`architecture.md` 里同一句错话也一并改了
- 门禁 12 步 → **13 步**（新增第 13 步公开范围校验）；node 77 → **85**（敏感扫描 249 → 252 文件）

### Added - 2026-09-17 门禁扩面与文档真相（Phase 7a）

Phase 7 的第一个子阶段。**没有新能力，对外行为零变化** —— 改的全部是"判据的观察面"与
"文档说的实话"。同一件事做了四次：**把一条已存在的约定变成判据，并让判据的观察面对准
作者真实会写的写法**。四次里三次抓到的是同一类失败：约定一直在，判据没在看。

- **活文档路径门禁扩到脚本层**（`scripts/live-doc-path-check.py`）。扩成 `pages|js` 还不够：
  6b-3 记的那处陈旧引用写成**裸脚本名**（`` `kb.js` ``，不带 `js/` 前缀），带前缀的扫描
  永远看不见。现在收三种形态：页面、带目录的脚本、**反引号内的裸脚本名**。扩面后抓到 11 处，
  其中 1 处是真漂移
- **修掉一处判据"太窄"的缺陷**（6b-3 教训的镜像）：`"已删除" in "已整条删除"` 为 `False`，
  于是一条**完全正确的**历史注记被判成漂移。窄的那一侧更阴 —— 判据红了会引导人去改正确的东西。
  加同义容忍正则，边界由两个相反方向的探针钉住（认「已整条删除」、不认裸「删除」）；
  刻意不放「快照」（6b-2b 实测过它会让整节落进豁免区）
- **端点计数退役，换成三段不变量**：`architecture.md §3` 的「前端实际消费 15 个端点」实测已烂
  （5 个名字已退役、3 组新端点没列、来源里写着已删除的 `kb.js`），同节路由表还留着 7 条
  Phase 1 已删的路由，两个数字也从未实测过（写 40/48，实测 49/44）。现在只描述分组与含义，
  **条数交给脚本打印**；不变量 = **前端字面量 ⊆ vercel 重写源 ⊆ `route_api()` 处理分支**
- 新增 `scripts/frontend-api-literal-check.py`：扫前端写死的 `/api/...` 与 `api('/...')` 参数
  （整段参数表 —— 只取第一个字面量会漏掉三元表达式里的 `/auth/login`）。实测 22 个路径全部命中。
  **盲区写在文件头**：不看 `ENDPOINTS.x + '/' + id` 这类拼出来的动态段
- **`.env.example` 双向一致**（本轮最实质的一处发现）：旧模板有一行**未注释**的 `====` 分隔符、
  一整块重复（两个变量各 3 次），并**漏掉 13 个代码里真的在读取的变量** —— 含服务端游客会话
  密钥 `DUMATE_GUEST_SECRET`（代码里有回退，**漏配不会被任何测试发现**）。重写为 29 个变量、
  无重复、每行合法；新增 `scripts/env-example-check.py` 双向判，白名单须逐条写理由且
  **名单里的键必须仍被读取**（防止名单腐烂成护身符）
- **`HANDOFF.md` 退役为薄指针**：它作为"第二真相源"已腐烂 6 周（停在 2026-08-01）。
  决策是不重写而是退役 —— 理由不是"它写错了"，而是**它没有触发条件**。新增判据：
  不得出现 40 位 commit hash 与测试计数，且它指到的每个仓库内路径必须真实存在（当前 32 个）
- 新增 `tests/test_phase7a_contract.js`（8 项），每条判据都带正反样本
- **勘误**：`api/index.py`「3000+ 行」在 5 份 phase report 里传播，实测 **1621 行**且从未为真
  （Phase 0 基线 1282 行）。不改写历史报告，改在 `docs/phase7a-report.md` 记一条，
  并作为 7c 的输入 —— 拆分规模比文档暗示的小一半

### Added - 2026-09-17 进入即强制注册/登录门禁（Phase 6b-3 · D7）

产品负责人要求的"点进产品即强制注册/登录"落地为弹窗门禁。这是**门禁**，不是账号体系重构：
服务端安全实现（HttpOnly Session、密码哈希、授权校验、归属隔离、删除链路、限流）一行未改，
门禁只加在它前面。

- 新增 `public/js/auth-gate.js`（**政策层**）：`decide()` / `plan()` 两个纯函数决定"谁被拦、
  何时拦、能否关掉"，脱离 DOM 即可断言；`js/account.js` 保持**机制**角色（弹窗、表单、
  `/api/auth/*` 调用）。分层是为了可判据化 —— 断网会不会放行、本地标记能不能绕过，
  这类问题能在 VM 里跑出来，不需要浏览器
- **登录态只认服务端**：政策层不读 `localStorage` / `sessionStorage` / `document.cookie`，
  只认 `GET /api/auth/me` 的答复。判据用**存取陷阱**证明它一次都没碰过本地存储
- **"不知道"不等于"是游客"，一律拦下**：拿不到服务端答复（断网 / 5xx）判为 `unavailable`
  → 强制弹窗 + 「重新连接」出口。把两者混为一谈等于给服务器故障开后门
- **强制态关不掉，三层兜底**：政策层隐藏关闭按钮 + `account.js` 在 `forced && !currentUser`
  时拒绝 `closeAuth()` + CSS `[data-forced="true"] .zy-modal-close { display: none }`；
  `Esc` 亦被原生 `cancel` 事件拦下
- 弹窗改为**原生 `<dialog>`**：`showModal()` 自带焦点陷阱与 `::backdrop`；三态显式存在
  （`empty` / `error` / `disabled`），状态区为 `role="status" aria-live="polite"`。
  门禁只挡住交互，**页面本身始终可见**，不清空也不报错
- 注册弹窗只有四项（手机号、邮箱、密码、账户名），满足 DoD #18「首次用户到第一个
  Target Job Decision ≤3 分钟」对注册环节的约束
- 豁免名单刻意只有一项：`public/pages/states.html`（内部 QA 状态墙 —— 不进导航、不含用户
  数据，且用途就是预览包含 empty 在内的六种界面状态）。有判据锁成"恰好一项"
- **修正一个接口隐患**：`check()` 过去返回 `plan()` 的结果，而 `plan()` 与 `decide()`
  **同用一个 `gate` 键、语义还相反**（豁免页 `plan().gate === 'exempt'` 是真值，
  `decide().gate === false` 意思是"别拦"）。现在 `check()` 返回**决策本体**，
  两层键名错开为 `gate`（布尔）/ `mode`（字符串）
- 新增 `tests/test_phase6b3_contract.js`（15 项）：含"只有服务端能放行"的行为判据、
  跨 realm 比较与注释剥离两个工具的探针

### Changed - 2026-09-17 一级导航收敛到 4 个工作区（Phase 6b-2b）

`product-scope.md §7` 定下的四个一级工作区（简历证据 / 目标岗位 / 模拟面试 / 行动闭环）
到此才第一次成为**导航的事实**：此前导航是 5 项、且首页占着一格。这次同时把"首页只能靠
导航进入"改成品牌区可点 —— 少一个格子，但没少一条回首页的路（有判据锁死品牌链接）。

- `index.html` 导航由 5 项改为 4 项：`<a class="brand" href="index.html">职跃AI</a>` +
  简历证据 / 目标岗位 / 模拟面试 / 行动闭环；「首页」导航项取消
- 投递页（原 F5）**退出导航**，作为目标岗位的二级页保留：`pages/target-job.html`
  新增出口区链入 `action-loop.html` 与 `job-apply.html`，它不会因为下架而变得不可达
- `pages/states.html` 状态矩阵同步为 3 行（简历证据 / 模拟面试 / 行动闭环）
- `tests/test_phase1_deletions.py` 的导航判据重写：**标签必须逐字等于**这四个工作区，
  并显式禁止「面经知识库 / 岗位匹配 / 知识库 / 首页」回流、禁止标签里出现 `F[1-5]`、
  要求品牌区指向 `index.html` —— 把"≤4 个一级工作区"从口号变成会失败的门禁

### Changed - 2026-09-17 页面与脚本改名为用户语言文件名，全量去除 F 代号（Phase 6b-2b）

DoD #2 要求用户可见面不出现内部代号。**URL 也是用户可见面**，所以这次连文件名一起换，
而不是只在界面上改文案：

| 旧 | 新 |
| --- | --- |
| `pages/f1-resume.html` | `pages/resume-evidence.html` |
| `pages/f3-interview.html` | `pages/interview-practice.html` |
| `pages/f4-report.html` | `pages/action-loop.html` |
| `pages/f5-apply.html` | `pages/job-apply.html` |
| `js/f3-interview.js` | `js/interview-practice.js` |
| `js/f5-apply.js` | `js/job-apply.js` |

- 两棵发布树（`public/` 与 `docs/`）同时改名，改后逐字节一致（镜像不变量未被破坏）
- 页面 `data-page` 取值同步改为 `resume / target / interview / action / apply`
- 新增判据：**发布树里不得再有带 F 代号的路径或可见文本**（`.md` 属历史记录，不在范围内）
- 4 个测试文件里以正则字面量写死的旧文件名（`test_phase4_contract.js`、
  `test_phase5_contract.js`、`test_quick_demo.js` 等）一并更新 —— 字符串替换扫不到
  转义过的正则，这正是改名最容易漏的一类残留

### Removed - 2026-09-17 能力报告页里的死进度追踪器（Phase 6b-2b）

`f4-report.html` 内联着一段「F1–F3 完成进度追踪器」，引用 6 个早已不存在的 DOM id
（`progressSummary` / `progressBarFill` / `connector1` / `connector2` / `progress-step` /
`progress-tracker`），**每次加载必抛 TypeError**，且它自己也带着 F 代号。

- 删掉该内联脚本与配套的 `.progress-tracker` 样式（约 137 行）
- 保留仍在使用中的行程进度指示，节点改名为 resume-evidence / target-job-analysis /
  interview-practice，并把「2/目标岗位分析」由不可点文本改成指向 `target-job.html` 的链接
- 新增通用判据：**页面的内联脚本不得 `getElementById` 一个该页没有声明的 id** ——
  这类死代码不会让测试变红，只会让控制台每次都报错

### Added - 2026-09-17 活文档路径门禁（Phase 6b-2b）

改名之后，`docs/architecture.md §2`、`docs/product-scope.md §1` 的页面表格仍指着旧文件名。
它没被任何判据抓到，因为路径扫描只覆盖发布树且排除 `.md` —— 文档是给人看的，真人会照着
它去找文件，这条路径同样会烂。

- 新增 `scripts/live-doc-path-check.py`：活文档（architecture / dependency-map /
  product-scope / 两棵 README）里的每个 `pages/*.html` 引用，要么指向真实存在的文件，
  要么**同一行或本节标题**带有「已删除 / 已下线 / 已修 / 审计 / 完成记录」之类明确的历史措辞
- 门槛刻意收窄到"同一行或本节标题"：早期版本用了"上下 ±10 行"的窗口，变异测试显示
  §2 现况表格里任何一行都能被 8 行之外的注记开脱 —— 下次再改名就抓不到了
- 门禁自检（引用集合非空 + 正反两个探针），并已变异测试：往 §2 塞 `action-loop-NOPE.html`
  → exit 1；塞带「已删除」标记的死链 → exit 0
- 文档本身按新口径修正：4 个改名页给出「旧名 → 新名」对照，两个已删除页面划掉并注明
  何时删的，两个审计快照表格的标题写明是快照（用词刻意不带历史标记，否则会削弱门禁）

### Added - 2026-09-17 行动闭环落位到能力报告页（Phase 6b-2a）

`product-scope.md §7` 的第 4 个一级工作区 Action Loop 首次到用户面前：
「补齐证据，然后复测」—— 按目标岗位的未解决缺口铺开行动，并让状态流转与结果回流留在界面上。
此前 `/api/actions` 的 8 条路由**零前端消费**（`phase6a-report.md §8` 明确记为待办）。

- 新增 `public/js/action-loop.js`（控制器）：清单、按岗位铺开、`todo→doing→done` 流转、
  结果回流、放弃、删除；五类状态徽标（待办/进行中/已完成/已放弃）+ 缺口优先级徽标
- `public/pages/f4-report.html` 新增「行动闭环 · 缺口 → 行动 → 复测」面板。
  面板位于**所有 state view 之外**，因此在 empty / error 态下依然可用（有判据锁死这一点）
- 幂等铺开的结果**如实分账**：`新建 N 条 / 已有未关闭 M 条 / 跳过 K 条（缺口没有可验证的成果物说明）`
  —— 被跳过的条数不静默丢弃，否则用户会误以为"我的缺口都开好单了"
- 「记录结果」按钮**只在行动已完成且带成果物说明时出现**：域层本就要求 `done + artifact`
  才允许 `outcome`，界面不制造必然 422 的操作
- 新增 `tests/test_phase6b2_contract.js`（7 条门禁）：面板存在且不在 state view 内、
  控制器只调用真实导出的 DataBridge 方法、行动状态取值集合与 `domain/action.py` 的
  `ActionStatus` 一致、限定语不得被删、判据自检

### Added - 2026-09-17 求职信接入目标岗位并显式呈现引用依据（Phase 6b-2a，DoD #10）

`phase4b-report.md §7` 记的"前端 F5 页面尚未传 `targetJobId`"到此结清。

- `data-bridge.js` 的 `generateCoverLetter()` 新增第 4 个参数 `targetJobId`；
  **未显式传参时回退到「当前目标岗位」** —— 保证 F5 与 F3 出题、F4 行动清单认同一个岗位
- `pages/f5-apply.html` 新增依据面板：`引用 N 条已确认证据 / 岗位要求底座（前 5 条）/ 未覆盖的缺口`
  + 后端下发的 `basis`（AI 生成 / 规则模板）与 `grounding`（目标岗位+证据 / 仅岗位要求 / 简历诊断）
- **没有任何已确认证据时明说**"正文没有引用任何个人经历"，而不是留白让人以为写了
- 缺口只作提示、不写进正文，也不被声称具备 —— 该限定写在后端 `notice` 与前端渲染两处

### Added - 2026-09-17 模拟面试显示按缺口定向的出题顺序（Phase 6b-2a，DoD #11）

DoD #11 的后端在 Phase 3 就返回 `questionPlan`，但界面上一直看不见，因此"顺序即优先级"无法验证。

- `pages/f3-interview.html` 新增出题计划面板：逐题显示题型（P0/P1 缺口定向题 / 关键证据验证题 /
  行为问题 / 通用题库）+ 优先级，并注明"来自目标岗位的未解决缺口"
- `js/f3-interview.js` 新增 `renderQuestionPlan()`；题型标签覆盖 `domain/interview.py::QUESTION_PRIORITY`
  的全部 5 个取值（有判据跨语言比对，防后端加题型后前端静默漏显示）
- 开始面试时显式读「当前目标岗位」并递给 `/api/wf04/start`；岗位无缺口时面板自动隐藏，
  不显示空壳

### Added - 2026-09-17 目标岗位工作区（Phase 6b-1）

`product-scope.md §7` 的 Target Job Workspace 首次到用户面前：「分析这个岗位，能不能投」——
建岗 → 拆出可核对要求 → 对照简历 → 给出 APPLY/STRETCH/PASS 判定 + 可逐条回查的依据 + 缺口清单。

- 新增 `public/pages/target-job.html`（宿主页，含 empty/processing/success/error/degraded 五状态）
  与 `public/js/target-job.js`（控制器）
- `data-bridge.js` 新增目标岗位 7 个方法（`listTargetJobs` / `createTargetJob` / `getTargetJob` /
  `analyseTargetJob` / `deleteTargetJob` / `setCurrentTargetJob` / `getCurrentTargetJob`）、
  行动闭环 9 个方法、证据档案 1 个方法（`getProfile`）
- 引入「**当前目标岗位**」这一跨页口径（会话缓存 `currentTargetJobId`）：
  此前「我分析的是哪个岗位」在前端不存在，F5 投递与 F3 出题无从对齐
- `startInterview()` 现在把 `targetJobId` 真的递给 `/api/wf04/start`（后端本就支持，
  `api/index.py:1437` 起按该岗位未解决缺口 P0→P1→P2 出题并回传 `questionPlan`）——DoD #11 接通
- 后端 `/api/target-jobs`（5 条）与 `/api/actions`（8 条）从**零前端消费**变为有消费方
- 新增 `tests/test_phase6b_contract.js`（5 条门禁）：坏引用、退役路径不得复活、接线正确、
  页面可达性、判据自检

**依据不足时不给结论**：后端在可核对事实 < 3 条时返回 `insufficient_grounds(422)`，
页面原样显示该消息而不给分数 —— 这是 DoD #9 要求的行为，不是故障。

### Removed - 2026-09-17 退役 `/api/wf03/*` 的前端路径与孤儿脚本 `js/job-upload.js`（Phase 6b-1）

`product-scope.md §5` 原裁决是"刻意未删 `job-upload.js`，待目标岗位工作区重新挂载"。
**该理由被侦察推翻**：它的通路 `uploadJD → submitJD → matchJD`（`/api/wf03/{upload,jd,match}`）
只产出 `jobProfile` 与匹配分数，**产不出 Decision，也产不出落库的 Gap 与 Action** ——
即使给它建了宿主页面，也交不出 §7 要求的 Target Job Workspace。且它跨 6 个状态依赖
**29 个 DOM id**（含已删 `f2-match.html` 的布局），复用它等于把已删页面的布局契约引回 canonical 树。

- 删除 `public/js/job-upload.js`、`docs/js/job-upload.js`、`tests/test_job_upload.js`
- `data-bridge.js` 退役 `uploadJD` / `uploadJDWithProgress` / `submitJD` / `matchJD` 及其
  `/api/wf03/*` 端点映射（实测：`submitJD`/`matchJD` 在全前端只有它一个调用方）
- 清理随之失效的 `.job-upload-layout` CSS（实测：两棵发布树中无任何 HTML 引用）
- **后端 `/api/wf03/upload|jd|match` 三条路由刻意保留**（`tests/test_api.py`、
  `scripts/run-rehearsal.py` 仍覆盖）；前端消费方归零一事记入 Phase 7 待办
- `tests/test_frontend_chain.js` 链路断言由 `/api/wf03/*` 改为 `/api/target-jobs` + `/api/actions`
- `tests/test_upload_progress.js` 删去 JD 进度上传与 job-upload 两条用例

### Fixed - 2026-09-17 门禁判据三处失效（Phase 6b-1）

- **`git diff --check` 不看已暂存**：本流程先 `git add -A` 再跑门禁，该步恒为 0（空转）。
  实证：注入行尾空白后 `git diff --check` 仍 exit 0，`git diff --check HEAD` 正确 exit 2。
  门禁第 6 步已改为 `git diff --check HEAD` —— 与 6a 修掉的 `cmd | tail -5; echo $?`
  属同一类错误：**判据的观察面与实际改动面不重合**
- **新契约判据误报**：最初用 `/\/api\/wf03/` 扫 `data-bridge.js` 全文，被自己写的
  说明性注释命中。改为只解析 `ENDPOINTS` 映射的**值**，并断言取值数 ≥10 防假通过
- **补丁脚本不幂等**：`patch6b.py` 的幂等判据写成"`new` 在且 `old` 不在"，
  对追加型补丁（`new = old + 新增行`）永远不成立，第二次运行把页面清单插了两遍。
  改为"`new` 已在即跳过"，实测第二次运行 39 项全部 skipped

### Removed - 2026-09-17 删除第三棵前端树 ui/（Phase 6a）

`ui/prototype/` 是 `public/` 的陈旧分叉：21 个文件名全部已存在于 `public/`（12 个逐字节相同，
9 个不同，其中 8 个更小 —— `css/main.css` 20336 vs 32008），
含 **7 处坏引用**（6 处指向不存在的 JS + `radar.js` 在 prototype 下失效的 ECharts 相对路径），
`vercel.json` 无 `ui/` 重写所以**从未部署**，且 `public/`、`docs/` 的 HTML/JS/CSS 中**零运行期引用**。
`ui/assets/` 与 `public/assets/` **逐字节完全相同**。没有一件是 prototype 独有的。

- 删除 `ui/` 整树（24 文件）+ 删除 `scripts/capture_ui.py`（目标树被删，且本就指向已删的 `f2-match.html`）
- `tests/test_phase1_deletions.py`：`RETIRED_TREES` 去掉 `ui/prototype`，另加一项断言
  `ui/` **整目录不得复活**（`public/` 是唯一前端树）
- `scripts/capture_mobile_ui.py`：去掉已删的 `f2-match` 条目，补上缺的 `pages/f5-apply.html`

### Changed - 2026-09-17 前端 canonical 口径：public 为源、docs 为镜像（Phase 6a）

不变量从"约定"升级为门禁：两棵发布树下所有 **非 `.md`** 文件必须**集合相同且逐字节相同**。

- 新增 `scripts/sync_mirror.py`：规则化（不硬编码清单）、幂等、`--check` 只校验并以退出码 1 报漂移；
  不自动删除镜像侧孤儿文件（需人工确认）
- 重写 `tests/test_publish_mirror.js`：**规则驱动 + 双向检查 + 判据自检**。
  原测试是**硬编码 26 项清单**，漏掉了 `blind-test-results/blind-test-summary.json` ——
  恰好当时两边相同，那处漂移永远不会被发现；且清单式规则的失效方式是"静默漏检"
- 已实测门禁会红：注入 `docs/` 侧内容漂移 + 孤儿文件 → `--check` 退出码 1、node 测试 `not ok`
- `scripts/sync_sidebar.py`：来源声明由 `ui/prototype` 改为 `public/`；`PAGES` 补上漏掉的
  `pages/f5-apply.html`（6 页都有侧栏，脚本原来只管 5 页）；`TREES` 改为源在前

### Fixed - 2026-09-17 Phase 6a 顺带修掉的四处真实偏差

- `pages/f4-report.html`（两棵树）在同一个 `<head>` 里**重复引入 `css/sidebar.css`** → 去掉重复项
- `public/capability_matrix.md` 比 `docs/` 那份旧：N8 行 08-05 vs 08-06，后者带
  `tests/embedding_full_recall_zhipu-3.json` + `deliverables/p0-03-evidence/`（2026-08-06 实跑）→ 同步
- `public/README.md` 与 `docs/README.md` **逐字节相同、整篇是 `ui/prototype` 的自述**，
  还列着 Phase 1 已删的 `pages/kb.html`、C7 区间带、七天计划 → 两棵都重写为发布树说明
  （页面清单、公开运行规则、发布结构与同步约定）
- 两份 `index.md` 都还索引着**不存在**的 `voice-test-checklist.md`（Phase 1 删语音链路时遗留）→ 删除该行

提交：**`a1586a5`**（46 文件，+749 / −4511；其中 25 项是删除）。

### Changed - 2026-09-17 Phase 6a 门禁口径

- pytest **481 → 482**（+1 项 `ui/` 整树已删断言）；node **36 → 42**（镜像测试 1→3 项、新增 6a 契约 4 项）
- 八步门禁扩为**九步**：新增第 9 步「发布镜像不变量」（`scripts/sync_mirror.py --check`）。
  该步第一版写成 `cmd | tail -5; echo $?` —— `$?` 取的是 `tail` 的退出码、**永远为 0**，
  一个不可能报错的检查；已改为先接住输出与退出码再打印，并实测三种状态回读正确
- 真实 HTTP 冒烟仍 **70/70**；vercel 重写仍 **44** 条 / 死路由 0；双方言 DDL 仍各 **29** 张表
- 敏感扫描 253 → **236** 文件（删除 `ui/` 24 文件等），无发现

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

提交：**`a3541cc`**（18 文件，+725 / −48）。

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
