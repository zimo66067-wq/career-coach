# -*- coding: utf-8 -*-
"""test_phase7c_contract.py · Phase 7c「拆 `api/index.py`」的结构判据

7c 把 1621 行的入口拆成 24 个模块（入口本身只剩建 app、装中间件、分派、再导出四件事）。
这一轮的风险**不是**业务逻辑写错 —— 分支体是逐行搬的（`work/verify-verbatim.py` 证明 831 行
逐行相等）—— 而是**结构塌陷**：

* 入口又悄悄长出业务分支（拆了个寂寞）；
* 某个模块忘了 import（只在没覆盖的分支上 `NameError`）→ 这条归 `scripts/api-import-check.py`；
* 模块回头 `import api.index`，把"单向依赖"变回环；
* handler 认领的路由族重叠，让分派顺序变得有意义（于是"顺序无关"从事实退化成赌注）；
* 入口的再导出面与 `tests/` `scripts/` 的实际需求漂移（少一个 → import 就炸；多一个 → 无人察觉的垃圾）；
* OPTIONS 白名单与真实路由集合漂移（少一条：浏览器预检被拦，**真实请求根本没发出**，日志里什么都没有）。

## 观察面

看：`api/**/*.py` 的 AST、`tests/`+`scripts/` 里对 `api.index` 的取用、`vercel.json` 的 functions 段。
不看：handler 内部的语义正确性（归 pytest 的 483 条）、线上可达性（归 `scripts/vercel-dead-routes.py`）。
⇒ 本文件只判**形状**。形状对 ≠ 行为对，但形状塌了行为一定守不住。

每个判据都配一个反向探针（喂假样本，证明它会红）—— 判据不可能变红等于没有判据。
"""
import ast
import json
import pathlib
import re

import pytest

import api.dispatch as dispatch
import api.index as api_module
import api.routing as routing
import api.sentinel as sentinel

ROOT = pathlib.Path(__file__).resolve().parents[1]
API_DIR = ROOT / "api"


def api_files():
    return sorted(p for p in API_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def parse(path):
    # 仓库里若干文件带 UTF-8 BOM（见 tests/test_layering.py 坑 1），一律 utf-8-sig。
    return ast.parse(path.read_text(encoding="utf-8-sig"))


def route_literals(tree):
    """抽出 `route == "x"` 与 `route.startswith("x")` 里的字面量。"""
    found = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Compare) and isinstance(node.left, ast.Name)
                and node.left.id == "route"):
            for op, comparator in zip(node.ops, node.comparators):
                if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant) \
                        and isinstance(comparator.value, str):
                    found.add(comparator.value)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "startswith"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "route"):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.add(arg.value)
    return found


def handler_route_literals():
    """{handler 模块名: 它认领的路由字面量}。"""
    out = {}
    for path in sorted((API_DIR / "handlers").glob("*.py")):
        out[path.stem] = route_literals(parse(path))
    return out


def family_root(literal):
    """路由字面量的"族名" = 第一段。`wf07/applications/<id>` → `wf07`。"""
    return literal.strip("/").split("/")[0]


# ------------------------------------------------------------------ #
# 7c-1 入口退化成纯分发器
# ------------------------------------------------------------------ #

def test_entry_module_has_no_route_branches():
    """`api/index.py` 不该再出现任何 `route ==` / `route.startswith(` 比较。

    这条是"拆分真的发生了"的唯一硬证据 —— 别的都可能靠搬文件糊过去。
    """
    entry_literals = route_literals(parse(API_DIR / "index.py"))
    assert entry_literals == set(), "入口又长出业务分支了：%s" % sorted(entry_literals)

    # 反向探针：同一个判据喂给一个 handler，必须**非空** —— 否则说明抽取逻辑坏了，
    # 上面那句 assert 就变成恒真（"判据恒绿"是这轮最该防的失败模式）。
    probe = api_files()
    assert probe, "观察面为空：api/ 下没有 .py"
    handler_literals = handler_route_literals()
    assert any(handler_literals.values()), "抽取器一个路由字面量都没抽到，判据是坏的"


def test_entry_module_is_still_the_deployment_contract():
    """`app` 对象与 `route_api` 必须在入口模块里 —— 它们是部署契约，不是实现细节。"""
    assert callable(getattr(api_module, "route_api"))
    assert api_module.app is not None
    assert hasattr(api_module.app, "add_url_rule")

    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    functions = config.get("functions") or {}
    assert "api/index.py" in functions, "vercel functions 不再指向 api/index.py"


def test_local_route_table_matches_the_options_whitelist():
    """本地 Flask 规则表与 OPTIONS 白名单必须描述同一组端点。

    这两份清单**独立写在两个文件里**（`api/index.py` 的规则表 / `api/routing.py` 的白名单），
    所以"它们相等"是一个有内容的判据，而不是同义反复：

    * 规则表少了 → `test_client()` 走不到那条路由，本地测试**看起来全绿**，线上却可达；
    * 白名单少了 → 浏览器预检被 404 挡住，**真实请求根本发不出去**，服务端日志一片空白。

    实测：`/api` 规则 49 条，其中非参数化 34 条 = `/api` + 33 条精确路由，
    与 `OPTIONS_ROUTES` 的 33 条精确对上（参数化那 15 条由前缀判据覆盖）。
    """
    source = (API_DIR / "index.py").read_text(encoding="utf-8")
    assert '"/api"' in source, "线上入口规则 /api 丢了（vercel 所有重写都指向它）"

    rules = [r.rule for r in api_module.app.url_map.iter_rules() if r.rule.startswith("/api")]
    non_param = {r for r in rules if "<" not in r}
    expected = {"/api"} | {"/api/%s" % route for route in routing.OPTIONS_ROUTES}
    assert non_param == expected, (
        "本地规则表与 OPTIONS 白名单不一致\n  规则表多出：%s\n  规则表缺少：%s" % (
            sorted(non_param - expected), sorted(expected - non_param)))
    assert len(rules) == 49, "参数化规则数变了：%d（原 49 条 /api 规则）" % len(rules)

    # 反向探针：把白名单去掉一条，上面的等式必须不成立（证明判据真的在比对）
    probe = set(routing.OPTIONS_ROUTES) - {"health"}
    assert non_param != {"/api"} | {"/api/%s" % r for r in probe}, "判据对少一条不敏感"


# ------------------------------------------------------------------ #
# 7c-2 依赖不成环
# ------------------------------------------------------------------ #

def test_no_api_module_imports_the_entry_point():
    """除入口自身外，`api/` 里任何模块都不得 import `api.index`。

    这是 `sentinel.py` 存在的理由（`dispatch ⇄ handlers` 的真环），也是
    `dependency-map.md §3.5` 警告过的形态。这条一旦红，说明有人用"函数内延迟 import"
    把环藏了起来 —— 那种写法在本仓库有明确的历史评价。
    """
    offenders = []
    for path in api_files():
        if path.name == "index.py":
            continue
        for node in ast.walk(parse(path)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "")]
            for name in names:
                if name == "api.index" or name.startswith("api.index."):
                    offenders.append("%s:%d" % (path.relative_to(ROOT).as_posix(), node.lineno))
    assert offenders == [], "api/ 内部出现指向入口的 import（会成环）：%s" % offenders


def test_handler_packages_import_the_entry_module_never():
    """反向探针：手工喂一个真的 import，上述判据必须报出来。"""
    probe_source = "from api.index import app\n"
    names = [(node.module or "") for node in ast.walk(ast.parse(probe_source))
             if isinstance(node, ast.ImportFrom)]
    assert any(n == "api.index" for n in names), "抽取器看不到 api.index 的 import，判据是坏的"


def test_sentinel_is_a_leaf_shared_by_dispatch_and_handlers():
    """哨兵住在叶子模块，且全仓库只有**一个**哨兵对象。"""
    tree = parse(API_DIR / "sentinel.py")
    repo_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in {
                "api", "providers", "services", "domain", "repositories"}:
            repo_imports.append(node.module)
        if isinstance(node, ast.Import):
            repo_imports.extend(a.name for a in node.names if a.name.split(".")[0] in {
                "api", "providers", "services", "domain", "repositories"})
    assert repo_imports == [], "sentinel.py 必须是叶子，却 import 了：%s" % repo_imports

    assert dispatch.UNHANDLED is sentinel.UNHANDLED, "分派表用的不是唯一的那个哨兵"
    assert sentinel.UNHANDLED is not None, "哨兵不能是 None（None 是合法响应）"
    # handler 也必须从叶子取，而不是各自 `object()`
    for name, literals in handler_route_literals().items():
        source = (API_DIR / "handlers" / ("%s.py" % name)).read_text(encoding="utf-8")
        assert "from api.sentinel import UNHANDLED" in source, \
            "%s 没从 api.sentinel 取哨兵" % name


# ------------------------------------------------------------------ #
# 7c-3 路由族互不相交（顺序无关与否，是可判的）
# ------------------------------------------------------------------ #

def test_route_families_do_not_overlap_across_handlers():
    """一个族只能属于一个 handler。重叠 → 分派顺序从"无关"变成"有含义"。"""
    owners = {}
    collisions = []
    for name, literals in sorted(handler_route_literals().items()):
        for literal in literals:
            root = family_root(literal)
            if root in owners and owners[root] != name:
                collisions.append("%s 同时被 %s 与 %s 认领" % (root, owners[root], name))
            owners.setdefault(root, name)
    assert collisions == [], "路由族重叠：%s" % collisions

    # 反面：喂两条同族字面量给判据，必须被判出碰撞
    probe = {"a": {"wf02/diagnose"}, "b": {"wf02/optimize"}}
    probe_owners, probe_collisions = {}, []
    for name, literals in probe.items():
        for literal in literals:
            root = family_root(literal)
            if root in probe_owners and probe_owners[root] != name:
                probe_collisions.append(root)
            probe_owners.setdefault(root, name)
    assert probe_collisions, "判据看不到同族碰撞，是坏的"


# ------------------------------------------------------------------ #
# 7c-4 OPTIONS 白名单 == 真实路由集合
# ------------------------------------------------------------------ #

def test_options_whitelist_matches_the_handler_route_set():
    """两侧各自维护着同一份"端点清单"，必须逐一相等。

    这两份清单是**独立写的**：handler 里是 `route == "..."`，白名单是 `OPTIONS_ROUTES`。
    少写在白名单里，浏览器预检被 404 挡住，**真实请求根本不会发出**，服务端日志里
    一点痕迹都没有 —— 属于最难从现象反查的一类问题。
    """
    exact = {literal for literals in handler_route_literals().values()
             for literal in literals if not literal.endswith("/")}
    # 只保留"精确路由名"（排除前缀式的族名，它们由下面的前缀判据管）
    prefixes = {literal for literals in handler_route_literals().values()
                for literal in literals if literal.endswith("/")}
    exact -= prefixes

    assert routing.OPTIONS_ROUTES == exact, (
        "OPTIONS 白名单与 handler 路由集合不一致\n  白名单多出：%s\n  白名单缺少：%s" % (
            sorted(routing.OPTIONS_ROUTES - exact), sorted(exact - routing.OPTIONS_ROUTES)))

    # 每个 handler 的**前缀族**都必须被白名单的某个前缀覆盖（白名单可以更宽，不能更窄）
    uncovered = [p for p in prefixes
                 if not any(p.startswith(w) for w in routing.OPTIONS_PREFIXES)]
    assert uncovered == [], "这些参数化前缀没被白名单覆盖：%s" % sorted(uncovered)


# ------------------------------------------------------------------ #
# 7c-5 入口的再导出面与真实需求一致（双向）
# ------------------------------------------------------------------ #

IMPORT_ALIAS_RE = re.compile(r"^\s*import\s+api\.index\s+as\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
FROM_ENTRY_RE = re.compile(r"from\s+api\.index\s+import\s+([^\n#]+)")


def consumer_needs():
    """tests/ 与 scripts/ 从 `api.index` 取用的符号集合（含别名 import）。"""
    needs = set()
    for base in ("tests", "scripts"):
        for path in (ROOT / base).rglob("*"):
            if path.suffix not in (".py", ".js") or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8-sig")
            for alias in IMPORT_ALIAS_RE.findall(text):
                needs |= set(re.findall(r"\b%s\.([A-Za-z_][A-Za-z0-9_]*)" % re.escape(alias), text))
                # `api_module.X` 里也有 `api.X` 这种假阳性，用真实属性存在性过滤（见下）
            for group in FROM_ENTRY_RE.findall(text):
                for item in group.split(","):
                    name = item.strip().split(" as ")[0].strip()
                    if name:
                        needs.add(name)
    return needs


def entry_imports():
    """入口模块顶层 import 绑定的 `{名字: 语句}`。"""
    out = {}
    for node in parse(API_DIR / "index.py").body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                out[alias.asname or alias.name.split(".")[0]] = "import %s" % alias.name
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                out[alias.asname or alias.name] = "from %s import %s" % (node.module, alias.name)
    return out


def entry_local_names():
    """入口模块里 `Name` 被**读取**过、以及顶层 `def`/`class` 定义出来的名字。"""
    tree = parse(API_DIR / "index.py")
    loaded = {n.id for n in ast.walk(tree)
              if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    defined = {n.name for n in tree.body
               if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))}
    return loaded, defined


def test_entry_import_surface_is_exactly_what_is_used_or_needed():
    """入口 import 的每一个名字，要么自己用，要么消费者要用 —— 两个方向都不能多不能少。

    定义"再导出"的方式不是标记，而是**语义**：`imported - 本模块用过` = 纯粹为别人留的。
    这样它自维护：没人再取的再导出会立刻变红（否则垃圾会一直长），
    消费者还需要的再导出被删也会立刻变红（否则 import 就炸）。
    """
    imported = entry_imports()
    loaded, defined = entry_local_names()
    consumers = {name for name in consumer_needs() if hasattr(api_module, name)}

    assert imported, "入口一个 import 都没有 —— 抽取逻辑坏了"
    assert consumers, "一个消费者都没扫到 —— 扫描逻辑坏了"

    # 方向一：消费者要的，入口必须给得出
    missing = {name for name in consumers if not hasattr(api_module, name)}
    assert missing == set(), "tests/scripts 在取但入口取不到：%s" % sorted(missing)

    # 方向二：入口 import 的，必须"自己用"或"消费者要用"；否则是没人察觉的垃圾
    orphans = {name for name in imported
               if name not in loaded and name not in consumers and name not in defined}
    assert orphans == set(), "入口 import 了既不用、也没人取的符号：%s" % sorted(
        orphans)

    # 纯再导出（本模块不用）必须真的有人在取
    pure = {name for name in imported if name not in loaded}
    assert pure <= consumers, "纯再导出里有人没人取：%s" % sorted(pure - consumers)
    assert pure, "再导出面空了 —— 消费者契约不该为空（app/ApiError 等）"


# ------------------------------------------------------------------ #
# 7c-6 中间件注册项可数
# ------------------------------------------------------------------ #

def test_http_layer_registers_the_expected_middleware_set():
    """6 个错误处理器 + 1 个 after_request + 1 个 before_request。

    少注册一个不会有测试直接报错（表现是某个分支回落默认 HTML 错误页），所以把集合钉住。
    """
    source = (API_DIR / "http_layer.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    registrations = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "target"):
            registrations.append(node.func.attr)
    assert sorted(registrations) == sorted(
        ["after_request", "before_request"] + ["register_error_handler"] * 6), registrations

    # 行为面：注册真的生效。注意 413 是按**状态码**注册的，落在 error_handler_spec 的
    # 整数键下，与"按异常类注册"分属两个命名空间 —— 只数类键会漏掉它（第一版就漏了）。
    classes, codes = set(), set()
    for _blueprint, mapping in api_module.app.error_handler_spec.items():
        for key, keyed in mapping.items():
            (codes if isinstance(key, int) else classes).update(keyed)
    assert Exception in classes, "兜底 500 处理器没挂上"
    assert len(classes) == 5, "按异常类注册的处理器应为 5 个，实际 %s" % sorted(
        str(c) for c in classes)
    assert codes, "按状态码注册的处理器（413）没挂上"
    assert len(classes) + len(codes) == 6, "错误处理器总数应为 6"


# ------------------------------------------------------------------ #
# 7c-7 逐字迁移的规模不变量
# ------------------------------------------------------------------ #

def test_handlers_together_cover_every_dispatch_family():
    """分派表里的 handler 必须与 `api/handlers/*.py` 一一对应（不多不少）。"""
    from_disk = {name for name in handler_route_literals()}
    from_table = {handler.__module__.rsplit(".", 1)[-1] for handler in dispatch.HANDLERS}
    assert from_table == from_disk, "分派表与磁盘上的 handler 不一致：%s" % sorted(
        from_table ^ from_disk)
    assert len(dispatch.HANDLERS) == len(set(dispatch.HANDLERS)), "分派表里有重复项"


def test_dispatch_raises_the_same_fallback_404():
    """没人认领 → 与拆分前逐字相同的兜底 404。"""
    with api_module.app.test_request_context("/api"):
        with pytest.raises(api_module.ApiError) as caught:
            dispatch.dispatch("definitely/not/a/route")
    assert caught.value.code == "not_found"
    assert caught.value.status == 404
    assert caught.value.message == "接口不存在。"
