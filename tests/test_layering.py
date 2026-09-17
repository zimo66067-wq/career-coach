# -*- coding: utf-8 -*-
"""test_layering.py · 分层静态门禁（Phase 5）

盯的是 DoD #13「Service 不反向依赖 API」，以及 `docs/dependency-map.md §3` 里
Phase 0 就点出、拖到 Phase 5 才修的那些结构问题。规则是**硬性**的：

| # | 规则 | 违例的含义 |
| --- | --- | --- |
| 1 | `services/` 不得 import `api.*` | 编排层反向依赖 HTTP 入口，服务没法脱离 web 层被复用/测试 |
| 2 | `domain/` 不得 import `flask` / `api` / `services` / `repositories` / `tools.database` | 域规则被 I/O 或上层污染，就不能"无库、无网"地测 |
| 3 | `repositories/` 不得 import `flask` / `api` / `services` | 数据层反向依赖编排层 |
| 4 | `domain/` 与 `services/` 不得**传递依赖** Flask | 直接 import 是明面的，传递依赖才是阴的 |
| 5 | `build_model_router` 全仓库**只有一处定义、且无人再绑定它** | 见下面的"打桩点收敛" |

## 四个实现上的坑（都踩过，写在代码里免得下次重踩）

1. **BOM**：仓库里若干文件带 UTF-8 BOM（`services/apply_service.py`、`tools/api_errors.py`、
   `tools/trace.py`、`tools/providers/model.py` …）。`ast.parse` 直接读会
   `SyntaxError: invalid non-printable character U+FEFF` —— 必须 `encoding="utf-8-sig"`。
   **一个静态检查如果自己崩了，门禁就等于没有。**
2. **函数体内的 import 也要算**：那两处倒置正是写在函数里（注释还理直气壮地写着
   "runtime lookup keeps monkeypatch compat"）。只扫模块顶层会全绿漏过。
3. **传递依赖只按模块级 import 计算**：`tools/trace.py` 的 `trace_id()` 在函数内
   `import flask`（Phase 5 改的），这不影响"本模块能否在没有 Flask 的环境里被导入"，
   正是**允许**的形态。规则要能区分这两件事，否则要么误报要么漏报。
4. **外部依赖不能被"解析不到"吞掉**：第一版只返回"能解析成仓库内模块"的 import，
   于是 `from flask import request` 直接被丢掉，规则 1/3 里的 `flask` **永远不可能命中**
   —— 判据恒真、门禁恒绿。所以 `_module_imports` 同时返回**原始名**与**解析名**，
   禁配列表对两者都匹配；判据自检（最后一个测试）专门盯这件事。

## 打桩点收敛（规则 5 的由来）

模型工厂 `build_model_router` 过去有多处绑定：`api/index.py` 一处，两个服务各在函数内
`from api.index import ...` 一处。测试要打桩就得知道"哪条路走哪个绑定"，打错了
**不报错、只是不生效** —— 静默失效是测试里最贵的一类 bug。

Phase 5 把归属地收敛到 `tools/providers/model.py`，其余模块一律
`from tools.providers import model as model_provider` 后做**属性查找**
（`model_provider.build_model_router()`）。于是：

* 全仓库只有一个打桩点：`tools.providers.model.build_model_router`；
* 打错地方会 `AttributeError`（`monkeypatch.setattr` 默认 `raising=True`），**立刻响**。
"""
import ast
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAYERS = ("api", "domain", "services", "repositories", "tools")

#: 允许 import flask 的层 —— 只有 HTTP 入口。
FLASK_ALLOWED_LAYERS = {"api"}

FORBIDDEN = {
    "domain": {"flask", "api", "services", "repositories", "tools.database"},
    "services": {"flask", "api"},
    "repositories": {"flask", "api", "services"},
}


def _module_files():
    """{模块名: 文件路径}，模块名用点号（`tools.providers.model`）。"""
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

    只查模块级 —— 函数内的延迟导入（`tools/trace.py::trace_id()` 就是）不算：
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


def test_importing_tools_trace_does_not_pull_flask():
    """实测证据：`import tools.trace` 不再把 Flask 拖进依赖图（Phase 5 的改动点）。

    服务层要引用 `new_trace_id`，如果这个模块在导入期就 `import flask`，
    那么"服务不依赖 web 层"就只是纸面上的。
    """
    import subprocess
    import sys

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "tools")])
    probe = (
        "import sys; import tools.trace; "
        "print('flask' in sys.modules, callable(tools.trace.new_trace_id))"
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
    assert definitions[0].startswith("tools.providers.model:"), definitions


def test_nobody_rebinds_the_model_router_factory():
    """除归属地外，任何模块都不得 `from ...providers.model import build_model_router`。

    重新绑定 = 又造出一个"打了桩却不生效"的假打桩点。
    正确取法：`from tools.providers import model as model_provider` 后属性查找。
    """
    offenders = []
    for name, path in _module_files().items():
        if name == "tools.providers.model":
            continue
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("providers.model"):
                for alias in node.names:
                    if alias.name == "build_model_router":
                        offenders.append("%s:%d" % (name.replace(".", "/"), node.lineno))
    assert offenders == [], "又出现工厂的模块级绑定：%s" % offenders


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
from tools.providers import model as model_provider


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

    # 传递污染：clean 模块 → tools.trace（模块级 import flask）
    tainted_sample = {
        "services.sample": _module_imports(
            _parse_source("from tools import trace\n"), "services", {"tools.trace": None, "services.sample": None}
        ),
        "tools.trace": _module_imports(
            _parse_source("from flask import request\n"), "tools", {"tools.trace": None}
        ),
    }
    assert flask_tainted(tainted_sample) == {"tools.trace", "services.sample"}
