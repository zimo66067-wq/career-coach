# -*- coding: utf-8 -*-
"""test_layering.py · 分层静态门禁（Phase 5）

盯的是 DoD #13「Service 不反向依赖 API」，以及 `docs/dependency-map.md §3` 里
Phase 0 就点出、拖到 Phase 5 才修的那些结构问题。规则是**硬性**的：

| # | 规则 | 违例的含义 |
| --- | --- | --- |
| 1 | `services/` 不得 import `api.*` | 编排层反向依赖 HTTP 入口，服务没法脱离 web 层被复用/测试 |
| 2 | `domain/` 不得 import `flask` / `api` / `services` / `repositories` | 域规则被 I/O 或上层污染，就不能"无库、无网"地测 |
| 3 | `repositories/` 不得 import `flask` / `api` / `services` | 数据层反向依赖编排层 |
| 4 | `domain/` 与 `services/` 不得**传递依赖** Flask | 直接 import 是明面的，传递依赖才是阴的 |
| 5 | `build_model_router` 全仓库**只有一处定义、且无人再绑定它** | 见下面的"打桩点收敛" |
| 6 | `providers/` 依赖 `domain/` 时，被依赖者必须是**叶子** | 见下面的"规则 6：唯一那条反向边" |

## Phase 7d 带来的两处变化

1. **`LAYERS` 里的 `tools` 换成 `providers`。** `tools/` 已整层并入 `domain/` + `providers/`
   （+ `repositories/` 1 个、`services/` 1 个），见 `docs/phase7d-report.md`。
2. **规则 2 里原来的 `"tools.database"` 这一项删掉了 —— 它变成了冗余。**
   那一项存在的理由是"`database.py` 住在 `tools/`，而 domain 不许用它"。
   7d 把 `database.py` 放回它该在的层（`repositories/database.py`），
   于是泛化的 `"repositories"` 已经覆盖它。**留着一条被充分条件覆盖的规则，
   只会让人以为它还在单独起作用。**

## 规则 6：唯一那条反向边

`docs/dependency-map.md §2.1` 记的实测合法方向是 `services → tools → (providers | database)`，
`tools` 的语义位置即今天的 `domain`，所以方向是 `domain → providers`。
但 `providers/model.py` 要抛 `ApiError`，而 `ApiError` 住在 `domain/internal/` ——
这条边是 `providers → domain`，**反向**。

允许它的依据不是"人情的例外"，而是一条可判的性质：**`domain/internal/api_errors.py`
零仓库内 import，是依赖图里的叶子。** 叶子造不出环，也不会把上层语义拖下来，
任何层依赖它都不构成倒置。判据是 `test_providers_may_only_reach_domain_through_leaves`，
它同时断言那条边**真的存在**（否则规则退化成空判）。

## 四个实现上的坑（都踩过，写在代码里免得下次重踩）

1. **BOM**：仓库里若干文件带 UTF-8 BOM（`services/apply_service.py`、`domain/internal/api_errors.py`、
   `domain/internal/trace.py`、`providers/model.py` …）。`ast.parse` 直接读会
   `SyntaxError: invalid non-printable character U+FEFF` —— 必须 `encoding="utf-8-sig"`。
   **一个静态检查如果自己崩了，门禁就等于没有。**
2. **函数体内的 import 也要算**：那两处倒置正是写在函数里（注释还理直气壮地写着
   "runtime lookup keeps monkeypatch compat"）。只扫模块顶层会全绿漏过。
3. **传递依赖（规则 4）只按模块级 import 计算**：函数体内的延迟导入不影响"本模块能否在
   没有 Flask 的环境里被导入"，所以规则 4 不数它。规则 2 是另一回事 —— 它连函数体内的
   import 也算（坑 2），因为"domain 不许碰 flask"是一条**无条件**的分层约束。

   **7d 实测：这两条一度看起来互相矛盾。** 当时 `domain/internal/trace.py` 的 `trace_id()`
   在函数内 `import flask`（Phase 5 改的）：并进 `domain/` 后规则 2 报它、规则 4 不报它。
   结论**不是**放宽规则 2 —— 而是 `trace_id()` 本来就不该住在 domain 层（它读
   `request.headers`，是 HTTP 的东西）。它已拆到 `api/trace.py`，而它的四个消费者
   （`api/handlers/wf01|02|03` + `api/http_layer`）本来全在 `api/`。
   规则要能区分这两件事，否则要么误报要么漏报。
4. **外部依赖不能被"解析不到"吞掉**：第一版只返回"能解析成仓库内模块"的 import，
   于是 `from flask import request` 直接被丢掉，规则 1/3 里的 `flask` **永远不可能命中**
   —— 判据恒真、门禁恒绿。所以 `_module_imports` 同时返回**原始名**与**解析名**，
   禁配列表对两者都匹配；判据自检（最后一个测试）专门盯这件事。

## 打桩点收敛（规则 5 的由来）

模型工厂 `build_model_router` 过去有多处绑定：`api/index.py` 一处，两个服务各在函数内
`from api.index import ...` 一处。测试要打桩就得知道"哪条路走哪个绑定"，打错了
**不报错、只是不生效** —— 静默失效是测试里最贵的一类 bug。

Phase 5 把归属地收敛到 `providers/model.py`，其余模块一律
`from providers import model as model_provider` 后做**属性查找**
（`model_provider.build_model_router()`）。于是：

* 全仓库只有一个打桩点：`providers.model.build_model_router`；
* 打错地方会 `AttributeError`（`monkeypatch.setattr` 默认 `raising=True`），**立刻响**。
"""
import ast
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAYERS = ("api", "domain", "services", "repositories", "providers")

#: 允许 import flask 的层 —— 只有 HTTP 入口。
FLASK_ALLOWED_LAYERS = {"api"}

FORBIDDEN = {
    # 7d 前这里还有一项 "tools.database"：当时 database.py 住在 tools/，而 domain 不许碰它。
    # database.py 归位到 repositories/ 之后，"repositories" 已经覆盖这条边，故删冗余项。
    "domain": {"flask", "api", "services", "repositories"},
    "services": {"flask", "api"},
    "repositories": {"flask", "api", "services"},
}


def _module_files():
    """{模块名: 文件路径}，模块名用点号（`providers.model`）。"""
    files = {}
    for layer in LAYERS:
        for path in (ROOT / layer).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            dotted = path.relative_to(ROOT).with_suffix("").as_posix().replace("/", ".")
            files[dotted] = path
    return files


def _parse(path):
    # BOM 见模块 docstring 坑 1：必须 utf-8-sig，否则带 BOM 的文件直接 SyntaxError
    return ast.parse(path.read_text(encoding="utf-8-sig"))


def _resolve(dotted, known):
    """把 import 的名字收敛到仓库内的模块名（最长前缀匹配）；外部依赖返回 None。"""
    parts = dotted.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in known:
            return candidate
        parts.pop()
    return None


def _module_imports(tree, package, known):
    """返回 [(原始名, 解析名或 None, 行号, 是否模块级)]。

    原始名与解析名都要留着：禁配列表里的 `flask` 是外部依赖，解析不出来（坑 4）。
    """
    found = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = ("." * node.level) + (node.module or "")
            names = [base] + ["%s.%s" % (base, alias.name) for alias in node.names]
        for raw in names:
            normalized = package + raw if raw.startswith(".") else raw
            found.append((normalized, _resolve(normalized, known), node.lineno, node in tree.body))
    return found


def _graph():
    known = _module_files()
    edges = {}
    for name, path in known.items():
        package = name.rsplit(".", 1)[0] if "." in name else name
        edges[name] = _module_imports(_parse(path), package, known)
    return known, edges


def _layer_of(module):
    return module.split(".")[0]


def forbidden_violations(edges):
    """规则 1-3 的判据（纯函数：便于用假数据自检，见最后一个测试）。"""
    problems = []
    for name, items in sorted(edges.items()):
        banned = FORBIDDEN.get(_layer_of(name))
        if not banned:
            continue
        for raw, resolved, line, _top in items:
            for candidate in [c for c in (raw, resolved) if c]:
                if candidate in banned or any(candidate.startswith(b + ".") for b in banned):
                    problems.append("%s.py:%d → %s" % (name.replace(".", "/"), line, candidate))
                    break
    return problems


def _flask_direct(edges):
    """模块级 import 了 flask 的模块（函数内 import 不算，见坑 3）。"""
    return {name for name, items in edges.items()
            if any(raw == "flask" and top for raw, _res, _line, top in items)}


def flask_tainted(edges):
    """传递闭包：模块级依赖链上出现 flask。"""
    tainted = set(_flask_direct(edges))
    changed = True
    while changed:
        changed = False
        for name, items in edges.items():
            if name in tainted:
                continue
            if any(resolved in tainted and top for _raw, resolved, _line, top in items):
                tainted.add(name)
                changed = True
    return tainted


def leaf_modules(edges):
    """没有任何**仓库内**出边的模块（依赖图里的汇点）。

    只按 `resolved`（解析得到的仓库内模块名）判定：`json` / `flask` 这类外部依赖
    解析出来是 `None`，不算出边 —— 否则 `domain/internal/contracts.py`（import jsonschema）
    会因为一条外部依赖而不再算叶子，规则 6 立刻误报。
    """
    return {name for name, items in edges.items()
            if not any(resolved for _raw, resolved, _line, _top in items)}


def reverse_layer_violations(edges, known):
    """规则 6 的判据：`providers/` 依赖 `domain/` 时，被依赖者必须是叶子。

    合法方向是 `domain → providers`（§2.1），所以 `providers → domain` 是反向边。
    唯一被允许的形态是依赖 domain 的**叶子**模块 —— 叶子是汇点，不构成倒置。

    `known` 必须传进来：`from domain.internal.api_errors import ApiError` 的原始名会带
    属性尾巴（`domain.internal.api_errors.ApiError`），**不收剑到模块就没法判叶子**
    （叶子集合里放的是模块名）—— 第一版漏了这一步，于是唯一那条合法的边被误判成违例。
    """
    leaves = leaf_modules(edges)
    problems = []
    for name, items in sorted(edges.items()):
        if _layer_of(name) != "providers":
            continue
        for raw, resolved, line, _top in items:
            for candidate in (resolved, raw):
                if not candidate:
                    continue
                owner = _resolve(candidate, known) or candidate
                if owner.split(".")[0] == "domain" and owner not in leaves:
                    problems.append("%s.py:%d → %s（domain 的非叶子模块）"
                                    % (name.replace(".", "/"), line, owner))
                    break
    return problems


# ------------------------------------------------------------------ #
# 规则 1-3：跨层 import
# ------------------------------------------------------------------ #

def test_no_direct_forbidden_imports():
    """含函数体内的 import（坑 2）。"""
    _known, edges = _graph()
    problems = forbidden_violations(edges)
    assert problems == [], "分层违例：\n  " + "\n  ".join(problems)


# ------------------------------------------------------------------ #
# 规则 4：传递依赖 Flask
# ------------------------------------------------------------------ #

def test_domain_and_services_do_not_transitively_depend_on_flask():
    """domain 要能"无库无网"跑，services 要能脱离 web 层跑。"""
    _known, edges = _graph()
    tainted = flask_tainted(edges)
    offenders = sorted(name for name in tainted if _layer_of(name) in ("domain", "services"))
    assert offenders == [], "间接依赖 Flask：%s" % offenders


def test_only_the_api_layer_depends_on_flask_at_import_time():
    """反向确认：除 `api/` 外，没有任何模块在**模块级** import flask。

    只查模块级 —— 函数内的延迟导入（`domain/internal/trace.py::trace_id()` 就是）不算：
    它不影响"这个模块能不能在没有 Flask 的环境里被导入"。而"服务层一行都不许碰 flask"
    （含函数内）由规则 1/2 的禁配列表保证，两个规则各管一段，别混在一起。
    """
    _known, edges = _graph()
    offenders = []
    for name, items in sorted(edges.items()):
        if _layer_of(name) in FLASK_ALLOWED_LAYERS:
            continue
        for raw, _res, line, top in items:
            if raw == "flask" and top:
                offenders.append("%s.py:%d" % (name.replace(".", "/"), line))
    assert offenders == [], "非 HTTP 层在导入期依赖 flask：%s" % offenders


def test_importing_domain_internal_trace_does_not_pull_flask():
    """实测证据：`import domain.internal.trace` 不再把 Flask 拖进依赖图（Phase 5 的改动点）。

    服务层要引用 `new_trace_id`，如果这个模块在导入期就 `import flask`，
    那么"服务不依赖 web 层"就只是纸面上的。
    """
    import subprocess
    import sys

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "tools")])
    probe = (
        "import sys; import domain.internal.trace; "
        "print('flask' in sys.modules, callable(domain.internal.trace.new_trace_id))"
    )
    completed = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                              text=True, env=env, cwd=str(ROOT), timeout=120)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "False True", completed.stdout


def test_the_two_historical_inversions_are_gone():
    """点名钉住 DoD #13 原文提到的那两处（`dependency-map.md §3.1`）。

    用 AST 判据而不是搜字符串：说明这段历史的**注释**里也会出现
    `from api.index import ...`，搜字符串会把注释当成违例。
    """
    _known, edges = _graph()
    for module in ("services.diagnosis_service", "services.interview_service"):
        offenders = [raw for raw, resolved, _line, _top in edges[module]
                     if (resolved or raw).split(".")[0] == "api"]
        assert offenders == [], "%s 仍依赖 API 层：%s" % (module, offenders)


# ------------------------------------------------------------------ #
# 规则 5：模型工厂只有一处
# ------------------------------------------------------------------ #

def test_model_router_has_exactly_one_definition():
    definitions = []
    for name, path in _module_files().items():
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.FunctionDef) and node.name == "build_model_router":
                definitions.append("%s:%d" % (name, node.lineno))
    assert len(definitions) == 1, "工厂被定义了多次：%s" % definitions
    assert definitions[0].startswith("providers.model:"), definitions


def test_nobody_rebinds_the_model_router_factory():
    """除归属地外，任何模块都不得 `from ...providers.model import build_model_router`。

    重新绑定 = 又造出一个"打了桩却不生效"的假打桩点。
    正确取法：`from providers import model as model_provider` 后属性查找。
    """
    offenders = []
    for name, path in _module_files().items():
        if name == "providers.model":
            continue
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("providers.model"):
                for alias in node.names:
                    if alias.name == "build_model_router":
                        offenders.append("%s:%d" % (name.replace(".", "/"), node.lineno))
    assert offenders == [], "又出现工厂的模块级绑定：%s" % offenders


# ------------------------------------------------------------------ #
# 规则 6：providers 只能经由叶子碰 domain（Phase 7d 新增）
# ------------------------------------------------------------------ #

def test_providers_may_only_reach_domain_through_leaves():
    """由来见模块 docstring「规则 6」。"""
    known, edges = _graph()
    assert reverse_layer_violations(edges, known) == []

    # 正面证据：那条唯一的边**真的存在**、且目标确实是叶子。缺了这一段，
    # 规则在"providers 压根不碰 domain"时也是绿的 —— 那就是空判（7c 的老教训）。
    leaves = leaf_modules(edges)
    reached = {resolved for name, items in edges.items() if _layer_of(name) == "providers"
               for _raw, resolved, _line, _top in items
               if resolved and resolved.split(".")[0] == "domain"}
    assert reached == {"domain.internal.api_errors"}, reached
    assert reached <= leaves, "被 providers 依赖的 domain 模块不是叶子：%s" % (reached - leaves)


def test_the_providers_rule_can_fail():
    """判据自检：同一条边，目标换成 domain 的**非**叶子模块时必须报出来。"""
    non_leaf = {
        "providers.sample": _module_imports(
            _parse_source("from domain import target_job\n"), "providers",
            {"providers.sample": None, "domain.target_job": None}),
        "domain.target_job": _module_imports(
            _parse_source("from repositories import database\n"), "domain",
            {"domain.target_job": None, "repositories.database": None}),
    }
    problems = reverse_layer_violations(non_leaf, set(non_leaf))
    assert any("domain.target_job" in p for p in problems), problems

    # 目标换成叶子 → 必须放过（否则规则会把唯一被允许的形态也判红）
    leaf = {
        "providers.sample": _module_imports(
            _parse_source("from domain.internal.api_errors import ApiError\n"), "providers",
            {"providers.sample": None, "domain.internal.api_errors": None}),
        "domain.internal.api_errors": _module_imports(
            _parse_source("class ApiError(Exception):\n    pass\n"), "domain.internal",
            {"domain.internal.api_errors": None}),
    }
    assert reverse_layer_violations(leaf, set(leaf)) == []


# ------------------------------------------------------------------ #
# 判据自检
# ------------------------------------------------------------------ #

BAD_SERVICE = """# -*- coding: utf-8 -*-
from api.index import build_model_router


def leak():
    from flask import request

    return build_model_router, request
"""

CLEAN_SERVICE = """# -*- coding: utf-8 -*-
from providers import model as model_provider


def fine():
    return model_provider.build_model_router()
"""


def _fake_graph(source, module="services.sample"):
    path = pathlib.Path(module.replace(".", "/") + ".py")
    known = {module: path}
    return {module: _module_imports(_parse_source(source), "services", known)}


def _parse_source(source):
    import tempfile
    handle = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8")
    handle.write(source)
    handle.close()
    return _parse(pathlib.Path(handle.name))


def test_the_gate_itself_can_fail():
    """判据自检：喂**故意越层**的源码，规则必须报出来。

    静态门禁最危险的失败模式是"判据写错了，于是一直绿着"（Phase 4b 的死路由就是）。
    这里跑的是**真实判据函数**，不是就地重写一遍规则：

    * 越层样本 → `forbidden_violations` 必须报 `api.index` **和** `flask`（函数内那个）；
    * 干净样本 → 必须为空（否则规则会误报，等于逼人绕过门禁）；
    * 传递依赖 → 干净样本引用一个"自己 import 了 flask 的模块"时，必须被算成污染。
    """
    bad = _fake_graph(BAD_SERVICE)
    problems = forbidden_violations(bad)
    assert any("api.index" in item for item in problems), problems
    assert any("flask" in item for item in problems), problems
    assert "services/sample.py:6" in "\n".join(problems), problems  # 函数体内那处也要钉住
    assert forbidden_violations(_fake_graph(CLEAN_SERVICE)) == []

    # 传递污染：clean 模块 → domain.internal.trace（模块级 import flask）
    tainted_sample = {
        "services.sample": _module_imports(
            _parse_source("from domain.internal import trace\n"), "services",
            {"domain.internal.trace": None, "services.sample": None}
        ),
        "domain.internal.trace": _module_imports(
            _parse_source("from flask import request\n"), "domain.internal", {"domain.internal.trace": None}
        ),
    }
    assert flask_tainted(tainted_sample) == {"domain.internal.trace", "services.sample"}
