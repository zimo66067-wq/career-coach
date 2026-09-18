# phase7d-report.md · Phase 7d「`tools/` 归并」

- 日期：2026-09-17
- 基线：`51212cb`（Phase 7c 的最后一笔：“docs: backfill the phase 7c commit refs into the changelog”）
- 门禁：`work/gate7d.sh` **16 步（0~15）全部 PASS，退出码 0**；变异注入 **17/17 全部被抓到**
- 范围：Phase 7 的**第四个子阶段，也是最后一个**。把 `tools/` 整层并入
  `domain/` + `providers/`（另加 `repositories/` 1 个、`services/` 1 个），并重写全仓引用。
- 口径：**纯结构重构，对外行为零变化**。见 §3 的"每一处改动都可归因"证明。
- 上一阶段：`docs/phase7c-report.md`（拆 `api/index.py`）
- 复算脚本：`work/verify7d-moves.py`、`work/mutate7d.py`、`work/recon7d.py`、`work/rewrite7d-imports.py`、`work/rewrite7d-rest.py`

---

## 1. 一句话

**`tools/` 整层（23 个模块 / 6440 行 + 一份 requirements）消失，22 个模块 `git mv` 走了、
1 个被拆分；全仓 249 处引用被改写；`import tools` 现在会抛 `ModuleNotFoundError`。**

这一轮的风险**不在业务逻辑**（逻辑一行没改写，可证），而在三件事：

| 风险 | 为什么它躲得过既有判据 | 现在谁看着 |
| --- | --- | --- |
| 某个模块**少 import 一个名字** | 只在**没被用例覆盖的那条分支**上 `NameError`，pytest 会绿 | 门禁第 14 步，**观察面从 `api/` 扩到 5 个生产层 + `scripts/`** |
| 某个模块**又长出 `tools/` 引用**（结构悄悄回潮） | 目录复活不会让任何用例变红；字符串形态的引用连 import 判据也看不见 | `tests/test_phase7d_contract.py` + 门禁第 15 步 |
| **`__file__` 推仓库根推错层** | 既不是 import、也不是字符串形态的 `tools`，所有自动化都归不到它 | 同上，`test_repo_root_derivations_match_the_real_depth` |

---

## 2. 归并成了什么

### 2.1 结构

```
domain/            18 模块  领域规则 + 原 tools/ 的引擎、评分、脱敏、提取、知识库
├── internal/       7 模块  领域层的**层内工具**：机制，不是规则（§2.3）
providers/          5 模块  外部服务适配：模型路由 / OCR / 单位数据
repositories/       9 模块  表级读写（+ database.py）
services/          10 模块  编排与事务边界（+ account_service.py）
```

`tools/` 目录**已删**，且不是"删了文件留个空目录"——空目录会让 `tools` 变成一个可 import 的
**命名空间包**，`import tools` 悄悄成功。判据把这两条一起判（`test_tools_layer_is_gone`）。

### 2.2 映射表（23 条，就是"归并没有漏"的判据，不是文档）

| 目标层 | 条目 | 模块 |
| --- | --- | --- |
| `domain/` | 10 | interview_engine / match_requirements / privacy_lifecycle / upload_security / validate_schema / deidentify / knowledge / optimizer / redflag / rescore |
| `domain/internal/` | 6 | api_errors / contracts / extract_text / log_sanitize / radar_adapter / trace |
| `providers/` | 5 | `__init__` / model / organization / model_router / ocr_provider |
| `repositories/` | 1 | database |
| `services/` | 1 | **account → account_service**（唯一改了文件名的，理由见下） |
| 删除 | 1 | `tools/requirements.txt`（逐行是根 `requirements.txt` 的子集，可复算） |

**为什么只有 `account.py` 改名为 `account_service.py`**：`services/` 里的兄弟都叫
`*_service.py`（`apply_service` / `diagnosis_service` / `interview_service` / `match_service` /
`organization_service` / `target_goal_service` …）。它是 **1 个模块对 1 个层的整体搬家**，
不带改名的话这个层里会多出一个不遵循同层命名的孤儿。改名成本是 1 个 import 点。

**为什么 `database.py` 落 `repositories/` 而不是 `domain/`**：`dependency-map.md` §5 自己写的
"`repositories/` ← `database.py` 拆出的表级读写"。它是**唯一**拼 SQL 的地方，且 `domain/`
有一条禁配表（不得碰 DB）。

### 2.3 `domain/internal/` 是这一轮的**设计决定**，不是收纳筐

`dependency-map.md` §5 第 4 条的原话是「`tools/` 逐步并入 `domain/` + `providers/`，
**或降级为 `domain` 的内部工具**」。"内部工具"在这一轮被读成一个**具体的包**，成员是 6 个
"是机制、不是领域规则"的模块：

| 模块 | 为什么是"层内工具"而不是"领域规则" |
| --- | --- |
| `api_errors` | `ApiError` 携带的是 **HTTP 状态码**；领域规则抛的是 `domain/errors.py` 的 `DomainError`。把两者混进 `domain/` 会让"领域层不认识 HTTP"这条线消失 |
| `contracts` | 读 `contracts/*.json` 并做业务规则校验的**校验器**，是所有域对象共用的机制 |
| `log_sanitize` | 日志脱敏管道，与任何一条业务规则无关 |
| `extract_text` | PDF/DOCX/TXT → 纯文本，纯 IO 机制 |
| `radar_adapter` | `AbilityProfile` → ECharts option，**渲染适配**，不是能力口径本身 |
| `trace` | trace id 的生成与形态（纯的那一半，见 §4.3） |

这个包**有一条硬约束**：成员必须是**叶子**（仓库内零依赖）。原因不是审美 ——
它是**规则 6**的承重墙：

> **规则 6（7d 新增）**：`providers → domain` 是唯一允许的反向边，且**只允许指向叶子模块**。

为什么需要这条边：`providers/model.py` 要抛 `ApiError`（HTTP 状态的载体），
而 `ApiError` 按上面的理由是 `domain/internal/` 的成员。`providers` 又不能"什么都不许碰
`domain`"——那会把 `ApiError` 逼回 `api/` 或复制一份。把它限定在**叶子**上，
反向边就没有传递性：`providers` 拿到的是一个不会再引入 `domain` 其他部分的机制件。
判据同时要求**那条边真的存在且目标真是叶子**（否则"providers 压根不碰 domain"时也是绿的，
那就是空判）。

`test_domain_internal_is_the_leaf_package_rule6_relies_on` 把成员集合**冻结**在表里
（不含 `__init__`）：只判个数（`len == 6`）挡不住"换掉一个"——数量没变，规则 6 的承重墙却塌了一角。

### 2.4 实测规模（`work/verify7d-moves.py` 可复算）

| 量 | 值 |
| --- | --- |
| 归并前 `tools/` | **23 个模块 / 6440 行**（recon 实测）+ `requirements.txt` |
| 归并后各层 | `domain` 18 / `domain/internal` 7 / `providers` 5 / `repositories` 9 / `services` 10 |
| 映射条目 | **23**（22 个 `git mv` + 1 个拆分） |
| 全仓引用改写 | **249 处**（点号 import 208 + 扁平 import 41） |
| 被改写的文件 | **141 个**（`.py` / `.yml` / `.md` / `.js` / `.html`） |
| 字符串常量残留白名单 | **5 个文件**（每条都有理由，见 §4.5） |

---

## 3. 证明"只改了引用，没改逻辑"

### 3.1 第一层证据：22 个模块走的是 `git mv`

`work/migrate7d-move.sh` 里每一条都是 `git mv`，**没有一条是"复制 + 删除"**。
搬家那一刻 `git diff --cached --numstat -M` 里 23 条全是 `0 0`（逐字节相同）。

### 3.2 第二层证据：**改完 import 之后仍然可复算**的那一条

第一层证据有个时效问题：紧接着要重写 import，所以**现在**再去看 `--numstat`，
那些 `R 0 0` 已经变成 `R 1 1`、`R 4 4`——"逐字节相同"在改完之后就不再可复现了。

所以 `work/verify7d-moves.py` 证的是更强、且**任何时候**都能复算的一件事：

> 对每个被搬走的模块，把它相对 HEAD 的每一处改动**做一次引用归一化**之后，
> 旧行与新行必须**逐字相同**；不相同的地方必须落在**声明过的白名单**里。

归一化 = 把任何形态的旧层引用与新层引用换成同一个占位符
（`tools/providers/model.py` / `tools.model_router` / `providers.model_router` / `model_router`
归一到 `«REF»` / `«MOD»`），于是"这处改动是不是只在换引用"变成一次字符串相等判断。

实测（`work/verify7d-moves.py` 输出）：

```
被搬走的 23 个模块合计改动：-29 / +59 行
OK 23 个模块的改动全部可归因：7 个逐字节相同（R 100%）/ 12 个只改引用 / 4 个已声明
```

* **7 个逐字节相同**：`upload_security` / `optimizer` / `api_errors` / `providers/__init__` /
  `organization` / `ocr_provider` / `database`
* **12 个只改引用**：改动量全部落在 import / `sys.path.insert` / `parents[N]` / 命令串上
* **4 个已声明**（下面逐条列出，这也是本脚本的白名单，写不出理由就加不进来）：

| 文件 | 声明内容 |
| --- | --- |
| `domain/internal/contracts.py` | `parents[1] → parents[2]` + 3 行注释（§4.1 的真实缺陷） |
| `domain/interview_engine.py` | `sys.path` 兜底改挂仓库根 + 注释改写 |
| `domain/privacy_lifecycle.py` | 同上；另有一处句末补了句号 |
| `domain/internal/trace.py` | **不是纯搬家，是一次拆分**（§4.3） |

### 3.3 `trace` 是唯一一条 git 自己都不认作 rename 的

`git diff --cached -M --summary` 把它记成 **`A domain/internal/trace.py` + `D tools/trace.py`**：
拆走 web 那一半之后，两边的相似度掉到 git 的阈值以下。所以"它确实来自 `tools/trace.py`"
不能靠 R 记录证，改用**符号存活**证：`TRACE_ID_PATTERN` 与 `def new_trace_id` 在
HEAD 版里存在、在新文件里也存在；而被拆出去的那半必须能在 `api/trace.py` 里找到
`def trace_id` 与 `from flask import request`。两条都由脚本实查。

行数：旧 `tools/trace.py` 31 行 → 新 `domain/internal/trace.py` 22 行 + `api/trace.py` 32 行
（两半各自带了新的 docstring，说明"为什么只剩这一半"）。

---

## 4. 本轮踩到的真缺陷（都是判据当场报出来的）

### 4.1 `__file__` 深度漂移 → 13 个测试模块**在收集期**炸

`tools/contracts.py` 用 `Path(__file__).resolve().parents[1]` 拿仓库根。搬到
`domain/internal/` 之后**深了一层**，`parents[1]` 于是变成 `domain/` —— 它去
`domain/contracts/resume-profile.schema.json` 找 schema，13 个测试模块在收集期
`FileNotFoundError`。

这一类失效的可怕之处：**改路径 / 改 import 的任何自动化都看不见它**（它既不是 import，
也不是字符串形态的 `tools`），而且**不报"我搬过家"，只报下游找不到文件**。

修法两条：
1. 改对深度（`parents[2]`），同类还有 `domain/interview_engine.py` 与
   `domain/privacy_lifecycle.py` 的 `sys.path.insert(0, dirname(__file__))` → `dirname(dirname(__file__))`。
2. 把它变成**静态判据**：`test_repo_root_derivations_match_the_real_depth` —— 全仓每个
   `...resolve().parents[N]` 的 `N` 必须等于该文件在仓库里的深度，**并附正面证据**
   （"确实扫到了 `parents[N]`"），否则正则是死的、永远绿。

> **这条判据的观察面是刻意窄的**：它只覆盖 `parents[N]` 这一种写法（意图无歧义 ——
> `parents[N]` 只能用来指某个祖先）。`dirname^k(abspath(__file__))` 与
> `join(dirname(__file__), "..")` 两种写法**判不了**：前者要 `k = 深度 + 1`，
> 而后者既可以表示"仓库根"（`k=1` + 一个 `".."`）也可以表示"我自己那一层"
> （`dirname(__file__), "fixtures-synthetic"`）——**同一个形状，两种意图**。
> 能覆盖它们的正则一定会在 `tests/test_bm25_baseline.py` 那类"相对自己那一层"的用法上误报，
> 而误报会让判据被绕过。所以这三种写法里的后两种，安全网是**行为侧**：
> 它们一旦指错，第 1 步 pytest 会以收集期错误的形式炸（这次就是这么发现的）。

### 4.2 mock 目标串是**裸模块名** → 只在使用它的那一行炸

`tests/test_model_router_providers.py` 里 8 处 `patch("model_router.urlopen")`。
`model_router` 原来是仓库根的**裸模块**（靠 `sys.path` 挂着），搬到 `providers/` 之后裸名不可解析。

它同时躲过了这一轮的三道判据：

* 不是 `import` → AST 的"没人在 import 已删层"判据看不见；
* 不含 `tools` 字样 → 残留扫描看不见；
* 只在 `patch(...)` **执行到那一行**才炸 → 收集期看不见；而且报错是
  `ModuleNotFoundError: No module named 'model_router'`，**读起来像环境问题，不像搬家问题**。

修法：8 处改成全限定 `"providers.model_router.urlopen"`，并新增判据
`test_mock_targets_resolve_to_real_modules` —— 它**不需要维护任何"已迁移模块名"清单**，
直接把每个 `patch("X.y")` / `monkeypatch.setattr("X.y")` 的首段 `X` 拿去 `find_spec`，
解析不了就红。**判据与运行时用的是同一个判定标准**（运行时也是拿这个名字去 import），
所以这里不存在假阳性。

### 4.3 `domain` 里的函数级 `import flask` → `trace` 被迫拆成两半

`tools/trace.py` 住在无禁配表的 `tools/` 里，所以它把两件事塞进同一个文件：
纯函数 `new_trace_id()` 和需要 Flask 请求上下文的 `trace_id()`（`from flask import request`
写在**函数体内**，Phase 5 为了避开循环导入才这么放的）。

并进 `domain/` 之后，`tests/test_layering.py` **规则 2**（domain 不得 import flask，
**函数体内的也算**）立刻把它报了出来。这不是判据太严 —— 它正好说出了实话：
`trace_id()` 是 web 层的东西。

证法不是"读代码觉得合理"，而是**消费者清点**：`trace_id()` 的 4 个消费者
（`api/handlers/wf01|02|03.py`、`api/http_layer.py`）**全在 `api/`**；
`new_trace_id()` 的消费者是服务层。于是 split 是唯一正确的切法：
纯的那半留 `domain/internal/trace.py`，web 那半去新文件 `api/trace.py`
（它自己 `from flask import request`，不再延迟导入）。

### 4.4 **扩面当场抓到一条与 7d 无关的老 bug**（本轮最值钱的一条）

门禁第 14 步的观察面从 `api/` 扩到 5 个生产层 + `scripts/`（96 个模块）后，第一次跑就报：

```
FAIL services/diagnosis_service.py:113  normalize_score 里用到 're'，但模块级没有这个绑定（少 import 或拼错）
```

`normalize_score()` 专门留了一条 `re.fullmatch` 分支，用来接住 **provider 把分数写成
数字字符串**这种输出（LLM 很常见：`"85"` 而不是 `85`），但那个模块**从来没有 import 过 `re`**。
也就是说：只要模型返回 `"85"`，`diagnose_resume()` 就是 `NameError`。

它此前不可见，**纯粹因为观察面只有 `api/`**。修法是补 `import re`，并在
`tests/test_phase5.py` 加回归用例（把字符串、带空格、小数、非数字、越界、NaN 六种输入各钉一次）。

> **这一条比"我们修好了一个 bug"更重要**：它说明**判据的覆盖面决定了它能看见什么**，
> 而不是它写得多仔细。第 14 步的实现（`symtable` + 作用域规则）一个字没改，
> 只是把 `--roots` 从 1 个值变成 6 个值，就从"绿"变成"红"。
> 反过来看，7c 把观察面定成 `api/` 在当时是**对的**（那时新失效模式只在 api/），
> 7d 没跟着搬家去扩它就会漏 —— **观察面是要跟着风险一起搬的**。

### 4.5 判据自己的三个洞（全是假阳性/空判方向）

1. **`ROOT.rglob("tools")` 把 `.venv-audit` 里第三方的 `tools/` 当成了回潮**：
   site-packages 里有 5 个（playwright / pyparsing / zhipuai）。假阳性比漏判更糟 ——
   它训练人去看白名单而不是看代码。修法：抽一个 `_walk()`，剪掉 `SKIP_DIRS` 与点开头的目录，
   **所有判据共用**；"每个判据各写一遍过滤"迟早有一个忘了。
2. **残留扫描扫纯注释，会把白名单撑成护身符**：第一版是逐字节扫 `tools[._/]`，
   于是名单从 5 条涨到 8 条，多出来的 3 条全是 7d 自己写的**纯 `#` 注释**。
   边界改成"**AST 里的字符串常量**"（即"能被执行到、或被复制去跑"的文字）：
   代码里的路径串 / mock 目标串 / **docstring** 在面内，纯注释不在面内。
   docstring 必须留在面内 —— 这次真的扫出一条约 `pip install -r tools/requirements.txt`
   （写在 `validate_schema.py` 里，会被用户原样复制去跑），是这一轮最有价值的一条修复。
3. **活文档判据（第 10 步）扩第三种形态时，第一版假阳性率 41%**：给
   `scripts/live-doc-path-check.py` 加"仓库内路径"正则后，一次实测报 **68 处**，
   逐条看下来只有 **40 处是真的**。28 处假阳性里两类：
   `work/verify7d-moves.py` 这类**仓库外**路径（`work/` 是门禁脚本住的那层，不在仓库里，
   7 处）、`/blind-test-results/blind-test-report.md` 这类**部署站点的 URL 路径**
   （仓库里根本没有这个目录）。修法与判据语义见 §7。

   这一条和上面两条**方向相反**：前两条是"判据比语义宽"（把注释当实现、把第三方当回潮），
   这一条是"判据的**面**比它要判的那件事宽"。三次都指向同一句话 ——
   判据的观察面必须与它要判的那个语义重合，**宽和窄同样会失效**。

---

## 5. 判据自检与变异测试

### 5.1 判据自检（正面证据，防止"恒绿"）

| 判据 | 探针 | 关键探针 |
| --- | --- | --- |
| `scripts/api-import-check.py` | **13** | 内建名 / 真闭包 / 推导式 / 海象 / `try/except as` / `with as` / `global` 各一条不误报；**3 条反向探针必须报错**（真漏 import、拼错局部变量、**只在某条分支上用的漏 import**）；星号导入必须判出身失效 |
| `scripts/live-doc-path-check.py` | **16** | 三种形态各配正反：死链必须报、带历史标记必须放过；四条**边界**探针（「快照」不得豁免、「删除」不得豁免、父标题标记要遗传、**兄弟节点不得越界**、**H1 不得参与**）；两条**假阳性**探针（仓库外路径、部署 URL 路径都不得进观察面）；一条**已消失的层仍必须被抓** |
| `tests/test_phase7d_contract.py` | **13 个 test** | 每条主判据都配反面：`test_the_mapping_checker_can_fail`（改坏一条映射必须报）；残留白名单要求"每条都要写理由"且"名单里的文件必须**真的**还有残留"（否则名单在腐烂）；`parents[N]` 判据要求"确实扫到了 `parents[N]`"；mock 目标判据要求"确实扫到了 `providers.` 开头的目标"；`test_live_doc_judge_covers_the_path_form` **把判据脚本加载起来跑**（不是 grep 源码） |
| `tests/test_layering.py` | **10 个 test** | 规则 6 配 `test_the_providers_rule_can_fail`：同一个反向边，目标换成**非**叶子必须报，换成叶子必须放过 |

### 5.2 变异注入（`work/mutate7d.py`，**17/17 全部被抓到**，另含 1 条收尾路径复核）

| 注入的违规 | 应变红的判据 | 结果 |
| --- | --- | --- |
| `domain/redflag.py` 挪走（模拟漏搬一条映射） | 映射表逐条命中 | ✅ |
| 建一个空 `tools/` 目录（命名空间包形态） | `test_tools_layer_is_gone` | ✅ |
| 在**仓库深处**建 `domain/tools/` | `test_no_temporary_tools_directory_resurrected` | ✅ |
| 同一个空目录 → 门禁**第 15 步的 shell 分支** | 第 15 步（与契约测试机制不同） | ✅ |
| 死代码里 `from tools.trace import trace_id` | AST import 判据（零容忍、无白名单） | ✅ |
| 加一个带 `tools/` 路径的字符串常量 | 残留白名单必须拒绝新成员 | ✅ |
| `domain/internal/log_sanitize.py` 变成非叶子 | 规则 6 的承重墙 | ✅ |
| `providers/model.py` 长出一条指向**非叶子**的反向边 | 规则 6 本身 | ✅ |
| `parents[2] → parents[1]`（7d 的实际 bug） | `__file__` 深度判据 | ✅ |
| `parents[2] → parents[3]`（过头也是错） | 同上（判据两个方向都判） | ✅ |
| `patch` 目标改回裸名（7d 的实际 bug） | mock 目标可解析 | ✅ |
| `repositories/database.py` 加一个解析不到的名字 | 第 14 步（扩面后） | ✅ |
| **同一处注入，判据只扫 `api/` 时不该报** | **反向控制**：证明"扩面"不是装饰 | ✅ |
| 让 `check_source` 恒返回空（摘掉判据的牙） | 该脚本自带自检 | ✅ |
| 注入行尾空白 | 门禁第 6 步（跨轮次复用，它最容易退化成空判） | ✅ |
| **`contracts/README.md` 追加一条指向已消失层的死链** | **第 10 步**（7d 之前它没有任何判据） | ✅ |
| **同一处追加……但换成仓库外路径与部署 URL** | **反向控制**：第 10 步必须仍然绿（假阳性不进观察面） | ✅ |
| （收尾）路径状态复核 | `tools/` / `domain/tools/` / `redflag*.py` 的存在性必须回到原样 | ✅ |

**表里有两条"期望不要红"的注入（第 13、17 行）。** 没有它们，"扩面"这件事就只有正面证据
（面更宽了、能报出来了），而没有反面证据（旧的窄面**确实**看不见 / 新面**不会**乱报）——
后者才是"扩展真的扩展了观察面、且没有把假阳性一起扩进来"的证明。

### 5.3 脚本自身的五个坑（写在这里，因为下一个搬家的阶段一定会踩）

1. **按单文件加 pathspec 跑 `git diff`，git 拿不到"旧侧"，重命名就配不上**：
   实测 `interview_engine.py` 于是报 `0 旧 / 1176 新` —— "逻辑没改"这句话当场失去依据。
   必须**一次跑全仓 diff**，再按 `+++ b/` 与 `rename to` 两个键索引。
2. **相似度 100% 的纯 rename 不输出 `---` / `+++`**：只有 `rename to` 一行。
   只认 `+++` 的话，7 个逐字节相同的模块会被报成"不在 diff 里"。
3. **`git diff --summary` 把一次重命名打成一行** `rename a => b (95%)`，
   而 `--name-status` 是 `R095\t<旧>\t<新>` —— 后者不会被措辞变化绊倒。
4. **pytest 的退出码在这个环境里不可信 —— 而这条教训门禁里早就写着，变异脚本第一次写的时候
   没沿用，于是自己踩了一遍。** 项目根有 safe-delete 垫片（`sitecustomize.py`），
   pytest 退出时 atexit 的临时目录清理被它拦下抛 `SystemExit(1)`，真实退出码被顶掉，
   `subprocess` 读回来是 0。修法：`is_red()` 对 pytest 命令只看 `\d+ (failed|error)`，
   与 `gate7d.sh` 第 1 步同口径。

   普适版本值得单独记：**"跑完看退出码"在这个仓库里是一个已知空判**，
   任何新写的判据/脚本都必须走摘要行。把教训只写在门禁里不够 —— 它必须写在
   **每一个读退出码的地方**。
5. **文本变异脚本"改第一处"是静默空操作，比不变异更糟。** `mutate7d.py` 首次真跑报的
   3 条 MISS，**判据一条都没坏**：`domain/internal/contracts.py` 里第一处 `parents[2]`
   在**注释**里（"所以 parents[1] → parents[2]"），
   `tests/test_model_router_providers.py` 里第一处 `"providers.model_router.urlopen"`
   在 **docstring** 里 —— 变异改的是注释，真实代码一字未动，判据当然红不了，
   而报表把这笔账记成了"判据没抓到"，下一步就是去修一条好判据。
   修法两条，和 `work/rewrite7d-imports.py`（"每处声明期望替换次数，对不上就拒绝写盘"）
   是同一条纪律：① `inject_replace` **要求锚点唯一**，出现多次直接拒绝施加（记 MUTATE-FAIL）；
   ② 需要"整批改错"的场景另立 `REPLACE_ALL`，语义写在名字里。

   **教训的形态**：变异测试的失败信息会**指向判据**，但根因可能在变异脚本自己。
   首次真跑报 MISS 时，先去读那 8 行日志，而不是先改判据。

---

## 6. 门禁结果

门禁的**判据步骤**从 14 步增至 **15 步**（新增第 15 步「`tools/` 零残留」），
另加第 0 步前置（git 可用性断言）。全绿：

| # | 步骤 | 结果 | 与 7c 对比 |
| --- | --- | --- | --- |
| 1 | `pytest tests/ -q` | **511 passed** | 495 → 511（+16：`test_phase7d_contract.py` 13 + `test_layering.py` 规则 6 两条 + `test_phase5.py` 一条回归） |
| 2 | `node --test tests/*.js` | **85 passed / 0 failed** | 不变 |
| 3 | schema 校验 | **32 OK / 0 FAIL**（入口换成 `domain/validate_schema.py`） | 不变 |
| 4 | 敏感扫描 | **279 文件**，passed | 277 → 279 |
| 5 | vercel 死路由 | 44 条重写 / 38 条 API 重写，**dead = 0** | 不变（零行为变化） |
| 6 | `git diff --check HEAD` | clean | 不变 |
| 7 | 双方言 DDL | 15 passed | 不变 |
| 8 | 真实 HTTP 冒烟 | **70 / 70** | 不变（零行为变化） |
| 9 | 发布镜像不变量 | 30 个非 md 文件逐字节相同 | 不变 |
| 10 | 活文档路径（**观察面 8 份文档 / 3 种形态**） | **436 处引用：310 处存在、126 处处于历史语境、0 处死链** | 5 份 / 121 处 → 8 份 / 436 处（§7） |
| 11 | 前端写死的 API 路径 | 15 个 js、22 个路径全部命中重写源 | 不变 |
| 12 | `.env.example` 双向一致 | 29 个变量 | 不变 |
| 13 | 公开范围 | 16 份 md 与清单一致 | 不变 |
| 14 | 名字解析（**观察面 1 层 → 6 个 root**） | **96 个模块、0 处解析失败** | 24 个模块 → 96 个模块（§4.4） |
| 15 | `tools/` 零残留（**新增**） | shell + 契约两路都过，契约 13 项 | — |

**口径**：第 8 项冒烟 70/70 与第 5 项 dead=0 是**零行为变化**的正面证据；
第 1 项的 511 是全量（含 DDL 与 node 契约之外的所有 pytest）。

---

## 7. 顺带修掉的、与"搬家"无关但与"引用"有关的三处

搬家必然会暴露所有**写死了老路径的散文**。这一轮扫出来的活文档（非历史记录）：

| 位置 | 原文 | 现状 |
| --- | --- | --- |
| `HANDOFF.md` 的"代码在哪里"表 | `引擎 / 脱敏 / 评分 / provider │ tools/、tools/providers/` | 拆成 `domain/` + `domain/internal/` + `providers/` 三行（`domain/internal` 那行注明它是硬约束） |
| `HANDOFF.md` 门禁一节 | `python tools/validate_schema.py` | `python domain/validate_schema.py` |
| `contracts/README.md` | 校验入口 `tools/validate_schema.py` | `domain/validate_schema.py`（并去掉一处过期的"同步 fixtures 与 tools"） |
| `contracts/scoring.md` §7 | 分数输出必须过 `tools/redflag.py` | `domain/redflag.py` |

**没动的是历史记录**：`CHANGELOG.md` 里 20 处、`deliverables/wf-evidence-20260803/*`
（那一批冻结的提交证据）——它们描述的是**当时**的事实，改掉就是伪造历史。
`tools/` 的历史由 7d 这一条新 CHANGELOG 条目承接。

### 7.1 缺口 → 判据：`path` 是第三种形态，`docs/` 的引述不再被误判

**缺口**：门禁第 10 步的"活文档"原先只有 5 份（`docs/` 四份 + `public/README.md`），
`HANDOFF.md` 由 node 契约 `test_phase7a_contract.js` 7a-2 覆盖，
**`contracts/*.md` 两边都不在** —— 上表那两处 `tools/…` 是**没有任何判据在看着**的
情况下人工扫出来的。而且 `PAGE_RE`/`JS_DIR_RE` 的抽取面只认 `pages/*.html` 与 `js/*.js`，
`tools/validate_schema.py` 这种写法**根本抽不出来**。

**修法**（`scripts/live-doc-path-check.py`）：

1. `LIVING_DOCS` 补上 `HANDOFF.md`、`contracts/README.md`、`contracts/scoring.md`（5 → 8 份）。
2. 新增第三种形态 `path`：`<层>/…/<文件>.py|md|json`，存在性对照**全仓相对路径**的集合
   （不是基名 —— 这一类的失效恰恰是"文件还在，但不在那个目录里了"）。

**但第一版报了 68 处，只有 40 处是真的**（见 §4.5 第 3 条）。于是加了**两条收窄**，
两条都是"判据的面必须与语义重合"这一条：

* **收窄 1：第一段必须是仓库顶层目录名，外加一个「已消失的层」清单。**
  `work/…`（仓库外）与 `blind-test-results/…`（部署 URL）因此不进面。
  但"仓库顶层"若只按 `os.listdir` 算，`tools/` 恰好会被排除 —— 而"指向已消失的层"正是
  最该抓的形态。所以 `GONE_LAYERS = {"tools": "<理由>"}` 显式留名，**每项必须写理由**。
* **收窄 2：词表加「基线」与「旧路径」，并把章节标题改成沿父子链遗传（不含 H1）。**
  这三份审计文档（`architecture.md` / `dependency-map.md` / `product-scope.md`）的正文是
  **某个 commit 上的现状快照**，头部有逐阶段账本。正文里的 `tools/redflag.py` 是
  "当时那个文件的**引述**"，不是"现在去打开这个文件" —— §11.3 那张覆盖率基线表里的
  `tools/redflag.py 19%` 是 2026-09-13 的实测值，把路径改写成 `domain/redflag.py`
  等于**伪造测量结果**。所以：
  - `基线`（时间点）/ `旧路径`（作者显式标注）**认**；
  - `快照`（范围说明）**不认** —— 6b-2b 那条教训（把 §2 标题写成"（快照：8 个 HTML）"
    会让整节落进豁免区）不能回退；
  - 父标题上的声明管到子标题（`## 3.（Phase 0 基线）` 覆盖 `### 3.1`），
    但**兄弟节点不得越界**、**H1 不得参与**（`architecture.md` 的 H1 里就写着"审计"，
    让 H1 生效等于整份文件一次豁免）。

**因此"改对"与"标注"分开**：§1 技术栈 / §5 / §6 / §7 / §8 这些是**现况断言** → 逐条改成
归并后的真实路径（并顺手把已经漂移的 `tools/contracts.py:25` 这类**行号**换成符号引用
`domain/internal/contracts.py::RESUME_PROFILE_VALIDATOR`，因为行号会自己漂移 ——
Phase 7c §21.5 已记过这一条）；§11 这类**基线测量** → 一个字不改，靠标题里的「基线」声明豁免。

判据本身也被判：`tests/test_phase7d_contract.py::test_live_doc_judge_covers_the_path_form`
**把脚本加载起来跑**（不是 grep 源码 —— 改个正则名字就骗过去了），
逐条钉住上面每一条收窄与每一个边界；`work/mutate7d.py` 另有两条注入
（正控 + 假阳性反控）证明它在门禁里真的会红、且不会乱红。

---

## 8. 遗留与口径

### 8.1 Phase 7 四个子阶段全部完成

| 段 | 内容 | 规模（实测） | 状态 |
| --- | --- | --- | --- |
| 7a | 门禁扩面与文档真相 | — | ✅ |
| 7b | wf03 去留 + 公开范围 | — | ✅ |
| 7c | `api/index.py` 拆分 | 1621 行 → 24 模块 | ✅ |
| **7d** | **`tools/` → `domain/` + `providers/` 归并** | **23 模块 / 6440 行 → 22 搬家 + 1 拆分** | ✅ |

`dependency-map.md` §5 第 4 条（`tools/` 保留期不超过两个 Phase）**已到期并已执行**。

### 8.2 本轮明确不动的

- **`api/index.py` 的 `REPOSITORY_ROOT` + `sys.path` 插入留在原地。** 线上入口就是本文件，
  `domain/` / `providers/` / `repositories/` / `services/` 能被 import 全靠它。
- **`domain/knowledge.py` 保留**（CHANGELOG 里那条"独立知识库产品下线"的结论不变：
  路由删了，题库作为 Interview Engine 的内部数据源留着）。
- **`tools/requirements.txt` 删了，但根 `requirements.txt` 一行没动。** 删除成立的前提
  （"逐行是根清单的子集"）现在是一条判据：`test_deleted_requirements_were_a_subset_of_the_root_ones`
  把那份清单的**原文**钉在测试里，缺依赖就红。
- **`deliverables/` 与 `CHANGELOG.md` 里的 `tools/` 一字未改**（历史记录，见 §7）。

### 8.3 下一步（不属于 Phase 7）

1. ~~`contracts/*.md` 纳入某个路径判据~~ → **本轮已补**（§7.1：第三种形态 `path` + 8 份活文档
   + 两条收窄 + 契约测试 + 两条变异注入）。
2. **`api/trace.py` 的归属**：它是"web 层的 trace 解析"，现在住在 `api/` 顶层。
   若之后 `api/` 再分层，它应当和 `http_layer.py` 一类同住。
3. `D3`（单位 / 职位检索）期限 **2026-10-13** 不变。
4. **判据自身的已知限制（留给下一个读到它的人）**：历史语境的豁免是**行级**的，
   所以"同一行里既有历史标记、又有一个**现况**引用"时，那个现况引用不会被判 ——
   实测残留一处：`product-scope.md` §2 表格里 `tools/knowledge.py 保留为内部题库`
   （该行末尾有「已删除」，指的是页面/API，不是这个模块）。它处在一张已被
   「已过时（Phase 6b-2）」声明过的表里，所以不是漂移；
   但**下次给这类行补现况引用时要另起一行**。

### 8.4 可复用的五条

1. **观察面要跟着风险一起搬。** 7c 把"名字解析"的观察面定成 `api/` 是对的（那时新失效模式只在
   api/）；7d 的风险换了层，判据本身一个字没改、只把 `--roots` 从 1 个值变成 6 个值，
   就从绿变红，并**当场抓到一条两年前的漏 import**（§4.4）。
   **判据的覆盖面决定了它能看见什么，而不是它写得多仔细。**
2. **"搬完就没证据了"的那一刻，要换一种可复算的口径。** `git mv` 的 `R 0 0` 在改完 import 后
   不再可复现；把口径换成"**每处改动归一化后旧新逐字相同**"，就得到一个（a）更强、
   （b）任何时候都能重跑、（c）白名单必须写理由的判据。
3. **会"只在使用它的那一行"炸的东西，要有一条静态判据。** mock 目标串（§4.2）和
   `parents[N]`（§4.1）属于同一族：**既不是 import，也没有 `tools` 字样**，
   报错还长得像环境问题。它们的共同特征是"**判据的按语义找得到它**"——
   `patch("X.y")` 的 `X` 必须能被 import，这是运行时的硬要求，不是我们的发明。
4. **假阳性和漏判都是失效，但假阳性更毒。** 它训练人去看白名单而不是看代码
   （§4.5 第 1 条）。**当一条判据的观察面比它的语义宽、必然误报时，正确的修法是收窄观察面
   并把边界写清楚，不是加白名单。**
5. **扩面之后，"改对"和"标注"必须分开做，判据不该替人做这个决定。**
   同样是 `tools/…`，在 §1 技术栈里是**现况断言**（要把路径改对），在 §11.3 覆盖率表里是
   **引述**（改一个字就是伪造测量）。判据分不出来 —— 它只能要求**文档自己声明**
   （标题里写「基线」），然后按声明放行。代价是多了一个词表，换来的是：
   历史记录不必被改写，现况断言不必被豁免。
