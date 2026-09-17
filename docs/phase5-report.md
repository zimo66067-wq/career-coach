# phase5-report.md · Phase 5（依赖倒置）

- 日期：2026-09-17
- 提交：**`a3541cc`**（18 文件，+725 / −48）
- 阶段目标：**DoD #13「Service 不反向依赖 API」** —— 修掉 `docs/dependency-map.md §3.1`
  从 Phase 0 就点出、被 Phase 2 明确推到本阶段的那两处倒置，并**加静态门禁防回潮**。
- 依据：`dependency-map.md`「Phase 5 验收」4 条硬性约束里，本期落 1、2（并复核 3）。
- 结论：**两处倒置已修，模型工厂收敛为单一归属地，分层静态校验进 pytest 门禁**
  （8 项，含判据自检）。**第 4 条（`tools/` 归并进 `domain/` + `providers/`）仍未做** ——
  它是跨阶段的重构，见 §7。

> **顺带挖出的第二层问题**：修倒置时发现 `services/diagnosis_service.py` 除了
> `from api.index import ...` 这处明面倒置，还通过 `tools.trace.trace_id()` **间接依赖
> Flask 请求上下文** —— 于是它的单测必须 `with app.test_request_context("/")` 才能跑
> （`test_phase5.py` 里那个 workaround）。只改 import 那一行，这个依赖仍然在（见 §3）。

---

## 1. 修改摘要

```
18 files changed, 725 insertions(+), 48 deletions(-)    ← 含新建的 tests/test_layering.py（327 行）
```

这次改动**总量很小、位置很集中**，这是依赖倒置修复的正常形态：真正的成本不在写代码，
在于"把打桩点从多处收敛到一处"所牵动的测试改动（本阶段改了 6 个测试文件 + 1 个脚本）。

| 改造 | 要点 |
| --- | --- |
| `services/diagnosis_service.py` | 工厂改从 `tools.providers.model` 取；`diagnose_resume(resume_text, trace=None)` 新增可选 trace（由调用方注入）；兜底 trace 换成纯函数 `new_trace_id()` |
| `services/interview_service.py` | `build_interview_router()` 同上（去掉函数内的 api 导入） |
| `services/apply_service.py` | 同一收敛原则：不再 `from ... import build_model_router`，改属性查找 |
| `api/index.py` | 去掉工厂的模块级绑定，改 `model_provider.build_model_router()`；`wf02/diagnose` 把 `trace_id()` 注入服务 |
| `tools/trace.py` | flask 改为**函数内**延迟导入；拆出纯函数 `new_trace_id()` |
| 6 个测试文件 + `scripts/run-rehearsal.py` | 打桩点统一改到 `tools.providers.model`（详见 §5） |

| 新建 | 行数 | 作用 |
| --- | --- | --- |
| `tests/test_layering.py` | 327 行 | **8 项**分层门禁：跨层 import / 传递 Flask 依赖 / 工厂单一归属地 / **判据自检** |

---

## 2. 两处倒置的修法

### 2.1 原来为什么那么写

```python
def diagnose_resume(resume_text):
    try:
        from api.index import build_model_router  # runtime lookup keeps monkeypatch compat
        router = build_model_router()
```

注释说的是实话，但它把两件事捆在一起了：

1. **导入位置在函数里** —— 因为 `api/index.py` 会 import `services`，服务在模块级
   import `api.index` 就是循环导入。函数内导入绕开了循环，代价是分层方向被彻底反转。
2. **从 `api.index` 取** —— 因为项目里模型工厂有**两个绑定**（`tools/providers/model.py`
   的真身 + `api/index.py` 的名字），从 api 那侧取能让既有测试继续打桩。

也就是说：**为了迁就测试的写法，服务层反向依赖了 HTTP 入口。**

### 2.2 修法：归属地收敛 + 属性查找

```python
# services/diagnosis_service.py
from tools.providers import model as model_provider   # 模块级，指向底层 provider
...
        router = model_provider.build_model_router()  # 属性查找，而不是把函数名绑进来
```

三件事一次到位：

- **依赖方向正过来了**：`services → tools.providers.model`（底层 provider），api 层不再被服务引用；
- **循环导入天然消失**：`tools.providers.model` 是叶子模块，模块级 import 不需要再躲进函数里；
- **打桩点唯一**：全仓库只有 `tools.providers.model.build_model_router` 一个可打桩的名字，
  任何地方按属性查找调用它。

`tools/trace.py` 同理（见 §3）。`services/interview_service.py` 的 `build_interview_router()`
保留"工厂失败返回 None → 题库降级"的语义不变。

---

## 3. 第二层问题：trace 的传递 Flask 依赖

`tools/trace.py` 原来是：

```python
from flask import request          # 模块级
def trace_id():
    candidate = request.headers.get("X-Trace-Id", "")
```

服务层 `from tools.trace import trace_id` 后用它兜底 —— 于是：

- 服务**间接**依赖 web 层（`services → tools.trace → flask`，静态看是"合规"的，
  因为中间隔着一个 tools 模块）；
- 更要命的是**行为上**：`trace_id()` 要请求上下文，**脱离了 web 层的服务调用会直接抛
  RuntimeError**。`test_phase5.py` 里那句 `with api_module.app.test_request_context("/")`
  就是这个依赖的化石证据。

### 修法：把"读请求头"这件事还给 web 层

```python
# tools/trace.py
def new_trace_id():                 # 纯函数
    return "api_" + uuid.uuid4().hex[:16]

def trace_id():                     # web 层专用
    from flask import request       # 函数内导入：import 本模块不再拖 Flask
    ...
```

```python
# api/index.py（wf02/diagnose）
profile, score_r, model_trace_id, ... = diagnose_resume(resume_text, trace=trace_id())
```

于是服务只接受"一个字符串 trace"，不再关心它从哪来；web 层负责解析 `X-Trace-Id`。
**测试的写法则变成了正面证据**：`test_services_diagnose_matches_previous_rule_fallback`
现在**不加任何请求上下文**直接调服务（原来那个 `test_request_context` 已经删掉）。

另有实测断言 `test_importing_tools_trace_does_not_pull_flask`：起一个子进程
`import tools.trace`，断言 `"flask" in sys.modules` 为 **False**。
纸面分层不算数，得有一行能跑的证明。

---

## 4. 静态门禁怎么写：四个坑

`tests/test_layering.py` 用 AST 扫全仓库，规则见文件头。写这个检查本身踩了四个坑，
每一个都会让门禁**看起来在工作、其实没有**：

| # | 坑 | 后果 | 修法 |
| --- | --- | --- | --- |
| 1 | 仓库里若干文件带 **UTF-8 BOM**（`apply_service.py` / `api_errors.py` / `trace.py` / `providers/model.py` …） | `ast.parse` 直接 `SyntaxError`，**检查自己崩了** | 一律 `encoding="utf-8-sig"` |
| 2 | 只扫模块顶层的 import | 那两处倒置写在**函数体内**，全绿漏过 | `ast.walk(tree)` 扫全树，同时记录"是否模块级" |
| 3 | 传递依赖不区分层级 | `tools/trace` 里那个函数内 `import flask` 会被误报，逼人加白名单绕过 | 传递闭包**只按模块级 import** 计算；"服务层一行都不许碰 flask"另由禁配列表保证 |
| 4 | 只返回"能解析成仓库内模块"的 import | `from flask import request` 直接被丢掉 → `flask` **永远不可能命中**，规则恒真 | 同时返回**原始名**与**解析名**，禁配列表对两者都匹配 |

第 4 个坑最值得记：**第一版门禁跑出"全绿"，而它根本不可能变红。**
所以文件最后一项测试是**判据自检** `test_the_gate_itself_can_fail`：喂一份故意越层的假源码
（`from api.index import ...` + 函数体内 `from flask import request`），断言
`forbidden_violations()` 真的报出这两条（连行号一起），并断言干净样本报空
（防误报）；再喂一份假的依赖图，断言传递污染算得出来。

> 这与 Phase 4b 的死路由判据是同一类教训：**门禁的可信度来自"证明它会红"，不是来自它一直是绿的。**

---

## 5. 打桩点收敛：一个打错就静默失效的地方

`build_model_router` 过去有三个绑定：`api/index.py` 一处、两个服务各一处（函数内）。
测试要打桩就得知道"哪条路走哪个绑定"：打了 `api.index` 只影响 api 层调用点，
服务那条路照旧走真工厂。

**而打错地方的后果是"不报错、只是不生效"** —— 测试仍然绿（因为无密钥时降级路径也能跑），
却什么也没验证。这是测试里最贵的一类 bug。

收敛后：

- 唯一打桩点：`monkeypatch.setattr(model_provider, "build_model_router", lambda: stub)`；
- 打错地方（比如还去 `monkeypatch.setattr(api_module, "build_model_router", ...)`）
  会直接 **AttributeError** —— `monkeypatch.setattr` 默认 `raising=True`，立刻响；
- 门禁规则 5 额外钉住"没人再重新绑定这个工厂"，防止有人顺手 `from ... import` 又造出一个假绑定。

---

## 6. 测试结果

```
pytest                     481 passed（Phase 4b 为 473，+8 项分层门禁）
node --test tests/*.js     36 passed / 0 failed
schema 校验                32 个 fixture 全部 OK
敏感扫描                   253 文件，passed
vercel 死路由              44 条重写 / 38 条 API 路由，broken = 0
git diff --check           干净
双方言 DDL                 15 passed，各 29 张表（本阶段无 schema 变更）
真实 HTTP 冒烟             70/70（本阶段未改路由与冒烟脚本）
**分层静态校验**            8 项（**本阶段起进 pytest 门禁**，此前是手工 grep 一次）
```

新增测试 **8 项**（`tests/test_layering.py`）：

| 组 | 项数 | 关键断言 |
| --- | --- | --- |
| 跨层 import（规则 1-3） | 1 | 禁配表对**原始名与解析名**都匹配，函数体内的 import 也要报出来 |
| 传递 Flask 依赖（规则 4） | 3 | domain/services 无传递 Flask；非 api 层不得在**导入期**依赖 flask；`import tools.trace` 实测不拉 Flask |
| 历史倒置钉住 | 1 | 用 AST 判据点名两处（不是搜字符串 —— 注释里也会出现 `from api.index import ...`） |
| 工厂单一归属地（规则 5） | 2 | 全仓库只有一处定义；无人重新绑定该工厂 |
| **判据自检** | 1 | 越层假样本必须报错（含行号）、干净样本必须为空、传递污染算得出来 |

---

## 7. 剩余与口径

1. **`dependency-map.md`「Phase 5 验收」第 4 条未做**：`tools/` 归并进 `domain/` + `providers/`。
   这是跨阶段的目录重构（涉及 20+ 个模块与全部 import），不属于"修倒置"的最小闭环；
   原文也写明"保留期不超过两个 Phase"，所以它**必须**在 Phase 7 前排期，不能被静默忘掉。
2. **`api/index.py` 仍是单文件 3000+ 行**（`dependency-map.md §4.1`）。本阶段只动了
   3 个调用点，没有拆文件 —— 拆路由属于独立作业，硬塞进 Phase 5 会让"倒置已修"这个结论
   变得不可验证。
3. **口径**：本阶段是**结构与测试**改动，对外能力零变化。发布说明里不得出现
   "服务层性能提升""新增能力"这类描述；唯一对外可见的差异是**错误响应里的
   `model_trace_id` 来源更明确了**（web 层解析后注入，行为与之前一致）。
4. **多语言/多 owner 场景未受影响**：`trace` 是请求级值，注入后不落库、不跨请求。

---

## 8. 下一步

- **Phase 6（前端工作面）**：F5 接 `targetJobId`（Phase 4b 留的口径），并把
  `evidence` / `gaps` / `notice` 呈现给用户；同时消费 Phase 4 的 8 条行动/结果路由。
- **Phase 7（目录与文档收尾）**：`tools/` 归并、`HANDOFF.md` 决定废弃或重写。
- **D3（单位/职位检索）** 仍封存，期限 **2026-10-13**。
