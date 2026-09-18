# phase7c-report.md · Phase 7c「拆 `api/index.py`」

- 日期：2026-09-17
- 范围：Phase 7 的**第三个子阶段**。**不含** `tools/` → `domain/` + `providers/` 归并（7d）。
- 口径：**纯结构重构，对外行为零变化**。逻辑一行没改写 —— 见 §3 的逐字证明。
- 上一阶段：`docs/phase7b-report.md`（wf03 路由去留 + 公开文档范围）
- 复算脚本：`work/verify-verbatim.py`、`work/verify-numbers.py`、`work/mutate7c.py`

---

## 1. 一句话

**1621 行的入口拆成 24 个模块，入口只剩 108 行；被搬走的 831 行是非空行级逐一相等的。**

这一轮的风险**不在业务逻辑**（那是逐行搬的，可证），而在四件事：

| 风险 | 为什么它躲得过既有判据 | 现在谁看着 |
| --- | --- | --- |
| 某个模块**少 import 一个名字** | 只在**没被用例覆盖的那条分支**上 `NameError`，pytest 会绿 | 门禁第 14 步 `scripts/api-import-check.py` |
| 模块回头 `import api.index`，把单向依赖变回环 | 平时不报，一旦真的写出来**连收集都过不去** | `tests/test_phase7c_contract.py` 7c-2 |
| handler 认领的路由族**重叠** | 分派仍能跑对，只是"顺序无关"从事实退化成赌注 | 同上 7c-3 |
| 入口的**再导出面**与消费者需求漂移 | 少一个 → import 炸（吵）；多一个 → **无人察觉的垃圾**（静默） | 同上 7c-5 |

---

## 2. 拆成了什么

### 2.1 结构

```
api/
├── index.py          108 行  ← Vercel 单函数入口（文件名与 app 变量名是部署契约）
├── app.py             25 行  Flask 实例（叶子）
├── constants.py       40 行  纯常量（叶子）
├── sentinel.py        26 行  UNHANDLED 哨兵（叶子，唯一理由是打断 import 环）
├── startup.py         78 行  bootstrap() + migration_status()
├── http_layer.py     186 行  CORS / 跨站写保护 / 6 个错误处理器
├── security.py       272 行  会话、同意签名、配额
├── validation.py     126 行  上传与文本校验
├── routing.py         65 行  request_route() + OPTIONS 白名单
├── dispatch.py        93 行  有序分派表 + 兜底 404
└── handlers/        14 个模块，1484 行  逐字搬过来的路由分支
```

### 2.2 实测规模（`work/verify-numbers.py` 可复算）

| 量 | 值 | 怎么算的 |
| --- | --- | --- |
| 拆分前 `api/index.py` | **1621 行** | `git show 131f83d:api/index.py` |
| 其中 `route_api()` | **917 行**（原文件 664–1580） | AST `FunctionDef.end_lineno - lineno + 1` |
| 其中被搬走的分支区间 | **891 行**（688–1578），非空 **831** 行（去重 598） | 非空行计数器 |
| 分支条件的构成 | **38 个 `if route ==`** + **12 个 `route.startswith(`** = 50 | AST `Compare` / `Call` 计数 |
| 拆分后 `api/` | **24 个模块**（含 14 个 handler） | `api/**/*.py` |
| 入口 + `api/` 膨胀比 | **1.457**（2362 / 1621） | 新壳是 docstring + import 头 + `def` + `return UNHANDLED` |
| 入口本地规则表 | **49 条** = 34 非参数化（`/api` + 33）+ 15 参数化 | 正则 + AST |
| `OPTIONS_ROUTES` / `OPTIONS_PREFIXES` | **33** / **6** | `api/routing.py` |

**关于"现在多少行"**：入口的行数在 `api/index.py` 的 docstring 里**故意不写**。第一稿写的是
101，实测 105；而"把这个数字改对"这个动作本身又把行数改成了 106 —— **会自我漂移的数字不属于
docstring**。行数快照记在这里，由脚本复算。同类修正共 4 处，见 §5.1。

---

## 3. 逐字迁移怎么证明

「逻辑一行没改写」不是一句话，是一件可核验的事：把原文件的分支区间（688–1578）与 14 个
handler 的**函数体**各自取"非空行 → 计数器"，两边必须**逐行相等含重数**。

```
原分支区间非空行数：831（去重 598）
handler 函数体非空行数：831（去重 598）
逐字迁移成立：两边逐行相等含重数（831 行全部对上）
```

* 少一行 → 搬丢了一段逻辑；
* 多一行 → 有人顺手改了内容。

**比对方本身也验了**：`work/verify-verbatim.py` 用的基线副本
（`C:/cc-tmp/index-orig.py`）与 `git show 131f83d:api/index.py` **逐字节相同** ——
否则"逐字"比的是一个来历不明的文件。外壳（docstring / import 头 / `def` / 末尾
`return UNHANDLED`）不参与比较，那些是新写的。

---

## 4. 本轮踩到的两个「判据不会红」（都在门禁自己身上）

### 4.1 第 6 步 `git diff --check HEAD` 是**空判**（7b 就已经是）

门禁脚本第 12 行把 PATH 收窄成 `/usr/bin:/bin:/c/Windows/...`，而 PortableGit 的 `git.exe`
在 `mingw64/bin` —— **不在 `/usr/bin` 里**。于是当调用者的 PATH 里没有 git 时，这一格执行的是

```
git: command not found    (exit 127)
```

而原来那行是 `git diff --check HEAD && echo "clean"` —— `&&` 短路，**日志里那一格什么都不打印**，
读起来和 `clean` 一模一样。

实测对照：

| 日志 | 第 6 步那一格 | 真相 |
| --- | --- | --- |
| `gate6b2b.log` / `gate6b3.log` / `gate7a.log` | `clean` | 那一格真的跑了 |
| **`gate7b.log`** / 首次 `gate7c.log` | （空） | **没跑** —— 应视为**未验证** |

修法两处：git 走绝对路径 + 开跑前先断言它真能执行（`=== 0. 前置 ===`）。
`git diff --check` 这一步本身在 6b-1 已经被修过一次（当时的问题是"不查已暂存"），
**这是同一个步骤的第二个洞** —— 两次都不是"判据写错了"，而是"判据在某种环境下没被执行，
而没被执行看起来和通过一样"。

### 4.2 门禁**恒以 0 退出**，所以"看退出码"本身也是空判

本脚本原来结尾只有 `echo "=== GATE DONE ==="`，从不 `exit 1`。后果实测到了：
本轮第一次后台跑门禁，外层 wrapper 报 `GATE_EXIT=127`，而**门禁其实一步都没跑**
（`bash: command not found`）—— 那个 127 是 wrapper 的，不是门禁的。

修法：每步的结论都记进 `VERDICTS`，末尾汇总；任一步没通过则 `exit 1`，并打印
`GATE FAIL：未通过的步号 = ...`。于是"看退出码"重新变成一个**有含义**的动作。

> **可复用的一条**：判据的失效有两种，**"判错"与"没被执行"**。本项目此前防的一直是第一种
> （观察面比语义宽 / 窄），7c 这一轮撞到的是第二种 —— 它对全绿外观的贡献是**完全一样**的。

---

## 5. 判据自检与变异测试

### 5.1 数字写错了四处（判据抓出正文错误，这是第三次）

新模块的 docstring 与契约测试里引用了若干规模数字。第一稿**四处是错的**：

| 位置 | 第一稿 | 实测 |
| --- | --- | --- |
| `api/index.py` / `tests/test_phase7c_contract.py` | 入口「101 行」 | **105 行**（改这个数字的动作又把它变成 106） |
| `api/index.py` / `api/dispatch.py` | 「39 条 `if route ==`」 | **38 条** |
| `api/index.py` | 「50 条 `add_url_rule` / 50 条本地路由规则」 | **49 条** |
| `tests/test_phase7c_contract.py` | 「参数化那 13 条」 | **15 条** |

另有 `api/dispatch.py` 的「919 行 `route_api()`」→ 实测 **917 行**；
`tests/test_migrations.py` 的一句注释断言「`api.index` 仍然再导出 `migration_status`」——
**它已经不导出了**（7c 的再导出判据要求这个面双向干净，没人取的符号被删掉了，注释没跟着改）。

修法不只是改数字：新增 `work/verify-numbers.py`，把每条断言与它的**算法**钉在一起
（含"基线副本必须与 `git show` 逐字节相同"这一条前置断言），改代码而没改散文就会在那里红。
**行数这类会自我漂移的量改成判"膨胀比落在 1.3~1.6"这个不变量**，只记快照、不判等值。

### 5.2 判据自检探针

| 判据 | 探针数 | 关键探针 |
| --- | --- | --- |
| `scripts/api-import-check.py` | **13** | 内建名不误报；真闭包不误报（内层读外层局部）；推导式目标、海象、`try/except as`、`with as`、`global` 声明各一条不误报；**3 条反向探针必须报错**（真漏 import / 拼错局部变量 / **只在某条分支上用的漏 import**）；星号导入必须判据失效并响 |
| `tests/test_phase7c_contract.py` | 12 个 test | 每条主判据都配一条反向探针：入口抽不到字面量要红、抽取器一个都没抽到要红、喂同族字面量要判出碰撞、少一条白名单要判出不相等 |

第 14 步用的是 `symtable`（**解释器自己的作用域规则**），不是 `compile()`（只查语法，不查名字）
也不是自己拿 `ast` 重写一遍作用域规则（那就是在重实现，容易错）。副作用：`symtable.Symbol`
**没有行号**，所以行号要从 AST 的 `Name`/`Load` 节点另算一份 —— 这一条写在脚本里。

### 5.3 变异注入（`work/mutate7c.py`，**14/14 全部被抓到**）

| 注入的违规 | 应变红的判据 | 结果 |
| --- | --- | --- |
| 删掉 `wf04.py` 的 `import json`（只在 SSE 分支里用） | 第 14 步名字解析 | ✅ |
| 让 `api-import-check.py` 恒不报（摘掉探针的牙） | 该脚本自带自检 | ✅ |
| 入口重新长出一条 `if route ==` | 7c-1 | ✅ |
| 本地规则表把 `wf05/ability` 拼错 | 7c-1 规则表一致性 | ✅ |
| **真写** `import api.index`（真环） | 连收集都过不去（`error during collection`） | ✅ |
| 死代码里的 `import api.index`（AST 看得见、运行期不执行） | 7c-2 | ✅ |
| `sentinel.py` import 仓库内模块（不再是叶子） | 7c-2 | ✅ |
| `wf05.py` 把本族路由写成 `wf06` 的（两族重叠） | 7c-3 | ✅ |
| 白名单删掉 `wf06/delete` | 7c-4 | ✅ |
| 再导出一个没人取的 `migration_status` | 7c-5 | ✅ |
| 少注册 `HTTPException` 处理器 | 7c-6 | ✅ |
| 分派表里拿掉 `health` | 7c-7 | ✅ |
| 兜底 404 文案改了 | 7c-7 | ✅ |
| **注入行尾空白**（第 6 步的正控） | 第 6 步 | ✅ |

**两条"成环"的注入是分开的**，因为它们证的不是同一件事：真写 `import api.index` 时跑的是
**一段真环**，pytest 连收集都过不去、根本走不到判据那一步；所以"AST 判据是活的"要用一条
**AST 看得见、运行期不执行**的 import 来验。真环的报错实测为：

```
api\handlers\health.py:16: in <module>
    import api.index
api\index.py:36: in <module>
    from api.dispatch import dispatch
E   ImportError: cannot import name 'dispatch' from partially initialized module
    'api.dispatch' (most likely due to a circular import)
```

这正是 `api/sentinel.py` 的 docstring 所声称的形态 —— **`dependency-map.md §3.5` 当年
`api/index.py ↔ services/*` 靠"函数内延迟 import 侥幸避开"的那种环，7c 把它在 `api/` 内部
真踩了一次，并因此把哨兵下沉到叶子模块**。

---

## 6. 门禁结果

门禁的**判据步骤**从 **13 步增至 14 步**（新增第 14 步 `api/` 层名字解析），
另加一个**第 0 步**前置：git 可用性断言（§4.1 的防线之一，它本身不是判据，是"判据能不能跑"的
自检）。全绿：

| # | 步骤 | 结果 | 与 7b 对比 |
| --- | --- | --- | --- |
| 1 | `pytest tests/ -q` | **495 passed** | 482 → 495（+13：`test_phase7c_contract.py` 12 + 1 守卫） |
| 2 | `node --test tests/*.js` | **85 passed / 0 failed** | 不变 |
| 3 | schema 校验 | 32 OK / 0 FAIL | 不变 |
| 4 | 敏感扫描 | **277 文件**，passed | 252 → 277（+25：23 个新 `api/` 模块 + 1 个门禁脚本 + 本报告；新契约测试在 `tests/`，该目录本就在扫描口径之外） |
| 5 | vercel 死路由 | 44 条重写 / 38 条 API 重写，**dead = 0** | 不变（重写源与处理分支都没动） |
| 6 | `git diff --check HEAD` | clean（**已修，见 §4.1**） | 7b 那一格是空的 |
| 7 | 双方言 DDL | 15 passed | 不变 |
| 8 | 真实 HTTP 冒烟 | 70 / 70 | 不变（零行为变化） |
| 9 | 发布镜像不变量 | 30 个非 md 文件逐字节相同 | 不变 |
| 10 | 活文档路径 | 5 份活文档 / 121 处引用全部可解析 | 不变 |
| 11 | 前端写死的 API 路径 | 15 个 js、22 个路径全部命中重写源 | 不变 |
| 12 | `.env.example` 双向一致 | 29 个变量 | 不变 |
| 13 | 公开范围 | 16 份 md 与清单一致 | 不变 |
| 14 | `api/` 名字解析（**新增**） | **24 个模块、0 处解析失败**，判据自检 13 项通过 | — |

**口径**：第 8 项冒烟 70/70 与第 5 项 dead=0 是**零行为变化**的正面证据 —— 若拆分改坏了任何
一条路由的接法，这两项会先在数量上露出来。

---

## 7. 遗留与口径

### 7.1 Phase 7 只剩一段

| 段 | 内容 | 规模（实测） | 状态 |
| --- | --- | --- | --- |
| 7a | 门禁扩面与文档真相 | — | ✅ |
| 7b | wf03 去留 + 公开范围 | — | ✅ |
| **7c** | `api/index.py` 拆分 | 1621 行 → 24 模块 | ✅ |
| **7d** | `tools/` → `domain/` + `providers/` 归并 | `tools/` **6252 行** / 20+ 模块，全部 import 需重写 | 未开始 |

`dependency-map.md`「Phase 5 验收」第 4 条写明 `tools/` 的"保留期不超过两个 Phase"，
**现已到期**，7d 不构成"可再推一轮"的选项。

### 7.2 本轮明确不动的（这些都是判据的输入，不是遗漏）

- **`api/index.py` 不改名、`app` 变量名不动。** `vercel.json` 的 `functions` 指向
  `api/index.py`，且 `scripts/vercel-dead-routes.py` 是 `from api.index import app` ——
  文件名与变量名都是**部署契约**，不是实现细节。文件只剩 108 行也没合并进别的模块。
- **`REPOSITORY_ROOT` 与 `sys.path` 插入留在入口。** 线上入口就是本文件，`tools/` / `services/`
  能被 import 全靠这三行；移走等于赌"Vercel 一定先 import 了包"。
- **`TRACE_ID_PATTERN` 是死常量，保留不删。** `api/index.py` 里定义了它但没有任何引用，
  真正在用的同名模式在 `tools/trace.py:15`。7c 的 DoD 是"拆分"不是"删代码" ——
  混进来会让"对外行为零变化"这句话变浑。已记录，留给后续阶段决定。
- **`api/constants.py` 里那个"哑绑定"只保留生效的那一份。** 原入口先
  `from tools.contracts import MAX_TEXT_CHARS, MIN_TEXT_CHARS`，10 行后又赋值一遍同名常量
  （两者值恰好一致：20 / 200_000），那次 import 是**哑绑定**。拆分时只搬生效的那份，值一字不改。
- **`tests/` 与 `scripts/` 的 7 个文件是被迫改的，不是顺手改的。** 打桩点必须跟着实现搬：
  `extract_txt` / `ocr_pdf` / `consent_serializer` 已不在 `api.index` 里，仍打在那里就是**空判**。
  为此在 `tests/test_api_boundary.py` 新增一条守卫用例 —— 打桩目标不存在时要**响亮地失败**，
  而不是静默不生效。

### 7.3 可复用的三条

1. **判据的失效有"判错"和"没被执行"两种，后者长得和前者通过时一模一样。** 7c 撞到两次，
   都在门禁自己身上（`git` 不在 PATH 里 → 那格静默；门禁恒退出 0 → 退出码无意义）。
   **凡"某个检查在环境不满足时什么都不打印"，它就已经不是检查了。**
2. **"会被自己改动的动作改变"的数字，不要写进被改的那个文件。** 入口行数写 101 → 实测 105 →
   改成 106。修法是把这类量从 docstring 里拿掉，改成判**不变量**（膨胀比落在区间内）+ 记快照。
3. **真环与判据要用两条不同的注入分别证。** "真写一个 reverse import"证的是**环是真的**
   （连收集都过不去），"死代码里的 reverse import"证的是**判据是活的**。用一条注入同时想证两件事，
   会得到一个"红了但没报出预期特征串"的假 MISS。

### 7.4 下一步

Phase 7d —— `tools/`（6252 行 / 20+ 模块）归并进 `domain/` + `providers/`，全部 import 重写。
`D3`（单位 / 职位检索）期限 **2026-10-13** 不变。
