# -*- coding: utf-8 -*-
"""api-import-check.py · 「名字解析」门禁（Phase 7c 建，7d 把观察面扩到 5 层）

## 为什么需要它

把一个 1621 行的入口拆成二十来个模块，最容易犯、也最难发现的错**不是逻辑写错，
而是少 import 一个名字**：

* 语法检查会过 —— `python -m compileall` 只看语法；
* pytest 会绿 —— 只要那条分支**没有用例覆盖**，`NameError` 就永远不会被触发；
* code review 也容易漏 —— 它藏在某个 `if route == "..."` 的深处。

而 7c 恰好把 871 行路由分支搬了家，其中相当一部分分支没有直接用例（`wf05/ability`、
`admin/export`、`target-jobs/<id>/decision` …）。所以这一步判的不是「逻辑对不对」，
而是「每个名字都解析得到吗」。

## 判据：用解释器自己的作用域规则，而不是搜字符串

`compile()` 只查语法、不查名字；`ast` 要自己重实现一遍作用域规则（很容易写错，
而**判据写错 = 门禁恒绿**）。所以这里直接问 `symtable` —— 它就是 CPython 编译期用的
符号表，`is_global()` / `is_local()` / `is_free()` 是权威答案。

对 `api/**/*.py` 的每个作用域（模块 / 每个函数 / 每个推导式），一个名字**解析不到**的
定义是：

    sym.is_global() and not sym.is_assigned() and name not in 模块级绑定 and name not in 内建

`sym.is_global()` 且在本作用域没被赋值 ⇒ Python 会去模块作用域找；模块作用域也没有
⇒ 运行期 `NameError`。这就是「少 import 或拼错」。

反向也成立：真闭包（内层读外层局部）在 symtable 里是 `is_free()` 而**不是**同级的
`is_global()`，所以不会被误报（自检探针 4 钉住这件事）。

## 观察面（这一步看什么、不看什么）

看：

  A. `--roots` 指定的各层下的 `**/*.py`（跳过 `__pycache__`）；默认 `api`，
     Phase 7d 起门禁传 `api,domain,providers,repositories,services,scripts`
     （5 个生产层 + 重写脚本本身）；
  B. 每个作用域里 **Name 在作用域链上能否解析**。

不看：

  C. 属性是否存在（`x.foo` 里的 `foo`）、调用参数个数、类型正确性；
  D. 各层的**形状**（层间依赖、谁不许 import 谁 —— 那是 `tests/test_layering.py` 的事）；
  E. 循环 import —— 那是运行期的事，由 pytest 覆盖。

⇒ 它只能证明「观察面里没有解析不到的名字」，**不能**证明「这些模块是对的」。
   后者归 pytest（全量）+ 死路由实证（38 条重写逐方法探）+ HTTP 冒烟（70 条）管。

### 为什么 7d 把观察面从 `api/` 扩到 5 层 + `scripts/`

原来 `from tools import …` 那一层的模块，被分到 `domain` / `providers` / `repositories` /
`services` 四个包下（208 处点号 import + 41 处扁平 import 被改写）。重写脚本的失效模式
恰好就是这一格的失效模式：
**漏改一处 ⇒ 那个名字解析不到 ⇒ 只在没被覆盖的分支上 `NameError`**。
7d 实测撞到的是它的近亲 —— `domain/internal/contracts.py` 用 `parents[1]` 推仓库根，
搬家后深了一层，于是 13 个测试模块在**收集期**就 FileNotFoundError（这次运气好，看得见）。

扩面本身立刻抓到一条**跟 7d 无关的老 bug**：`services/diagnosis_service.py::normalize_score`
用 `re.fullmatch` 接住"分数是数字字符串"的分支，而模块从未 `import re` ——
只要 provider 把 `"85"` 当分数返回，这条分支就是 `NameError`。
它此前不可见，纯粹因为观察面只有 `api/`。**这说明"观察面 = 语义"不是口号：
判据的覆盖面决定了它能看见什么，而不是它写得多仔细。**

`scripts/` 也纳入观察面：7d 的改写有一大块落在 `scripts/`（`sys.path` 插入、扁平 import），
只扫生产层会把"改写脚本自己坏了"漏掉。

## 两类失败必须分清楚

| 码 | 含义 | 该怎么办 |
| --- | --- | --- |
| 1 | 有解析不到的名字 | 补 import，或修拼写 |
| 2 | 观察面为空 / 判据自检失败 / 出现 `import *` | **先修判据**，不要改代码去迎合它 |

`import *` 单列为失败而不是放过：星号导入会把模块作用域填成"什么都有"，
symtable 也就答不出"这个名字到底存不存在"—— 判据会静默失效。把它判红，
是为了**不允许出现让判据失效的写法**。

用法（仓库根目录）：

    .venv-audit/Scripts/python.exe scripts/api-import-check.py [--verbose] [--selfcheck]
    .venv-audit/Scripts/python.exe scripts/api-import-check.py --roots api,domain,providers,repositories,services
"""
import argparse
import ast
import builtins
import pathlib
import symtable
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
#: `--roots` 的默认值。7d 起门禁显式传 5 层，这里保留 `api` 是为了让单独手跑时的
#: 默认行为跟 7c 一致（不因为门禁扩面而改变手工调用的语义）。
DEFAULT_ROOTS = "api"

#: 解释器注入的名字（不是内建函数，但模块里可以直接用）。
INTERPRETER_NAMES = {
    "__file__", "__name__", "__doc__", "__package__", "__spec__",
    "__loader__", "__builtins__", "__debug__", "__path__",
    "__annotations__", "__class__", "__dict__",
}

BUILTIN_NAMES = set(dir(builtins)) | INTERPRETER_NAMES


def module_bound(table):
    """模块级绑定：import / def / class / 赋值 / for / with / except as / del。"""
    bound = set()
    for sym in table.get_symbols():
        if sym.is_assigned() or sym.is_imported() or sym.is_namespace() or sym.is_parameter():
            bound.add(sym.get_name())
    return bound


def _walk_tables(table, path=()):
    yield path, table
    for child in table.get_children():
        yield from _walk_tables(child, path + (child.get_name() or "<comprehension>",))


def _load_lines(tree):
    """{名字: [出现行号…]} —— `symtable.Symbol` 不提供行号，从 AST 补。

    符号表是权威的「有没有绑定」，但要说清「在哪一行」，得回到 AST 找那几次 Load。
    """
    lines = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            lines.setdefault(node.id, []).append(node.lineno)
    for name in lines:
        lines[name].sort()
    return lines


def _line_for(lines, name, anchor):
    """取「作用域起点之后」的第一次 Load；找不到就退回第一次 Load。"""
    candidates = lines.get(name) or [anchor]
    for line in candidates:
        if line >= anchor:
            return line
    return candidates[0]


def check_source(source, filename, extra_module_bound=()):
    """返回 [(行号, 作用域, 名字, 说明)]，空列表 = 全部可解析。"""
    tree = ast.parse(source, filename)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    return [(node.lineno, "<module>", "*",
                             "星号导入让判据失效（模块作用域变成「什么都有」），请改成显式 import")]

    table = symtable.symtable(source, filename, "exec")
    known = module_bound(table) | set(extra_module_bound) | BUILTIN_NAMES
    lines = _load_lines(tree)

    problems = []
    for path, scope in _walk_tables(table):
        anchor = scope.get_lineno() or 1
        for sym in scope.get_symbols():
            name = sym.get_name()
            if not sym.is_global() or sym.is_assigned():
                continue
            if name in known:
                continue
            where = ".".join(path) or "<module>"
            problems.append((_line_for(lines, name, anchor), where, name,
                             "%s 里用到 %r，但模块级没有这个绑定（少 import 或拼错）" % (where, name)))
    return sorted(problems)


def target_files(roots):
    """观察面 = 各 root 下的全部 `*.py`（跳过 `__pycache__`）。

    故意**不**在 root 不存在时静默跳过：那会让「观察面为空」变成空判。
    这里返回空列表，由 `run()` 用退出码 2 报出来。
    """
    files = []
    for root in roots:
        base = ROOT / root
        if not base.is_dir():
            continue
        files.extend(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(set(files))


def run(roots, verbose=False):
    files = target_files(roots)
    if not files:
        print("观察面为空：%s 下没有 .py 文件 —— 判据在空跑，必须响。" % ",".join(roots))
        return 2

    total_problems = 0
    for path in files:
        source = path.read_text(encoding="utf-8-sig")
        problems = check_source(source, str(path))
        rel = path.relative_to(ROOT).as_posix()
        if problems:
            total_problems += len(problems)
            for line, where, name, message in problems:
                print("FAIL %s:%d %s" % (rel, line, message))
        elif verbose:
            print("OK   %s" % rel)

    print("已解析 %d 个模块（观察面 %s）、%d 处解析失败"
          % (len(files), ",".join(roots), total_problems))
    return 1 if total_problems else 0


# ------------------------------------------------------------------ #
# 判据自检
# ------------------------------------------------------------------ #
#: (说明, 源码, 期望解析不到的名字集合)
PROBES = (
    ("内建名可直接用",
     "print(len(open))\n", set()),
    ("模块级 import + 函数内引用 → 干净",
     "import os\n\n\ndef f():\n    return os.sep\n", set()),
    ("from ... import 的名字 → 干净",
     "from flask import request\n\n\ndef f():\n    return request.method\n", set()),
    ("真闭包（内层读外层局部）→ 不得误报",
     "def outer():\n    value = 1\n\n    def inner():\n        return value\n\n    return inner\n", set()),
    ("推导式目标 → 干净",
     "def f(items):\n    return [x for x in items if x]\n", set()),
    ("海象运算符 → 干净",
     "def f(payload):\n    if (size := len(payload)) > 0:\n        return size\n", set()),
    ("try/except as 绑定 → 干净",
     "def f():\n    try:\n        pass\n    except ValueError as err:\n        return err.args\n", set()),
    ("global 声明 + 模块级绑定 → 干净",
     "COUNT = 0\n\n\ndef bump():\n    global COUNT\n    COUNT += 1\n", set()),
    ("with ... as 绑定 → 干净",
     "def f(handle):\n    with open(handle) as stream:\n        return stream.read()\n", set()),
    ("**真正的漏 import 必须报出来**",
     "import json\n\n\ndef f():\n    return jsn.dumps({})\n", {"jsn"}),
    ("拼错局部变量必须报出来",
     "def f(payload):\n    body = payload.get('x')\n    return bodi\n", {"bodi"}),
    ("**只在某条分支上用的漏 import 也必须报出来**（切分场景的主失效模式）",
     "import json\n\n\ndef f(route):\n    if route == 'a':\n        return json.dumps({})\n"
     "    if route == 'b':\n        return uuid.uuid4().hex\n    return None\n", {"uuid"}),
    ("星号导入 → 判据失效，必须红",
     "from os import *\n\n\ndef f():\n    return getcwd()\n", {"*"}),
)


def selfcheck():
    failures = []
    for label, source, expected in PROBES:
        try:
            found = {name for _line, _where, name, _msg in check_source(source, "<probe>")}
        except Exception as exc:  # noqa: BLE001 - 自检就是要把崩溃暴露出来
            failures.append("%s → 判据崩了：%s: %s" % (label, type(exc).__name__, exc))
            continue
        if found != expected:
            failures.append("%s → 期望解析不到 %s，实际 %s" % (label, sorted(expected), sorted(found)))
    if failures:
        print("判据自检失败（%d/%d）：" % (len(failures), len(PROBES)))
        for item in failures:
            print("  - " + item)
        return 2
    print("判据自检通过：%d 项（含 3 项「必须报错」的反向探针）" % len(PROBES))
    return 0


def main():
    parser = argparse.ArgumentParser(description="模块「名字解析」门禁（默认观察面 api/）")
    parser.add_argument("--verbose", action="store_true", help="逐文件打印 OK 行")
    parser.add_argument("--selfcheck", action="store_true", help="只跑判据自检")
    parser.add_argument("--roots", default=DEFAULT_ROOTS,
                        help="逗号分隔的观察面（默认 %s）。Phase 7d 起门禁传 " % DEFAULT_ROOTS +
                             "api,domain,providers,repositories,services,scripts —— "
                             "归并后的模块换了 import 写法，"
                             "「少 import 一个名字」这个失效模式跟着搬家了。")
    args = parser.parse_args()
    roots = [r.strip() for r in args.roots.split(",") if r.strip()]

    if args.selfcheck:
        return selfcheck()

    code = selfcheck()
    if code:
        return code
    return run(roots, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
