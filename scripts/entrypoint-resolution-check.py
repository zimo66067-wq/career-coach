# -*- coding: utf-8 -*-
"""入口解析判据：**每一个候选入口名**都必须解析到"带路由的 app"。

## 它补的是哪个洞（2026-09-21 实测踩到）

`tests/` 与其它脚本都是显式 `from api.index import app`，走的是**直连路径**。
而 Vercel 的 Flask 预设是**按文件名找入口**的：候选名
`app.py` / `index.py` / `server.py` / `main.py` / `wsgi.py` / `asgi.py`，
位置是仓库根（以及 `src/`、`app/`），并且实测 `api/` 也会被搜索。

于是出现了一种三套测试全绿、本地全绿、CI 全绿、首页 200，而**线上每个接口都 404** 的状态：
平台 import 的是 `api/app.py` —— 一个只 `Flask(__name__)`、**不注册任何路由**的叶子模块。
所有测试都只 import `api.index`，**没有任何判据看过"按文件名会被解析到哪个模块"**。

## 判据怎么算

对每个"存在的候选入口文件"：

1. **在全新子进程里** import 它（不能在本进程 —— 一旦 `api.index` 被 import 过，
   路由就注册到同一个 app 对象上了，之后再看这个对象就永远是"有路由"，判据会绿着失效）；
2. 读 `len(app.url_map.iter_rules())` 与 `app.test_client().get("/api/health").status_code`；
3. 要求：**规则数 > 1**（>1 就是除 static 之外真有路由）且 `/api/health` 回 200。

只要有一个候选名解析出"无路由的 app"，就红 —— 因为**解析顺序是平台侧的实现细节，本地观测不到**，
任何一个错的候选都是潜伏故障。

## 反向控制（防"绿着失效"）

判据自身会在一份**临时构造的**包里跑同一段测量代码，要求它把一个裸 app 判成无路由、
把一个带路由的 app 判成有路由。若这段测量本身失去分辨力，判据报红而不是报绿。

用法（仓库根目录）：
    .venv-audit/Scripts/python.exe scripts/entrypoint-resolution-check.py
退出码：有候选解析出无路由的 app，或自检失败 = 1。
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Vercel Flask 预设的候选入口名（官方文档 "Deploy a Flask app on Vercel"）。
CANDIDATE_NAMES = ("app.py", "index.py", "server.py", "main.py", "wsgi.py", "asgi.py")

# 搜索位置。官方文档写的是"仓库根，以及 src/ 与 app/ 里的同名文件"；
# `api/` 是文档没写、但 2026-09-21 实测被搜索过的位置（线上被服务的正是 api/ 下的叶子模块）。
# 把它纳入观察面：**宁可多算一个位置，也不要漏掉一个真实会被解析的地方**。
SEARCH_DIRS = ("", "src", "app", "api")

# 子进程里跑的测量代码。`{}` 处填模块名。
PROBE_CODE = (
    "import json,sys;"
    "import importlib;"
    "m=importlib.import_module({module!r});"
    "a=getattr(m,'app',None);"
    "print(json.dumps({{"
    "'rules': len(list(a.url_map.iter_rules())) if a is not None else -1,"
    "'health': a.test_client().get('/api/health').status_code if a is not None else -1,"
    "'is_flask': a is not None}}))"
)


def _measure(module_path, cwd):
    """在**全新子进程**里把模块 import 进来，回报它的路由数与 /api/health 状态码。

    必须是子进程：本进程一旦 import 过 `api.index`，路由就已经注册在同一批 app 对象上，
    再测量任何入口都会得到"有路由"，判据永远抓不到问题。
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(cwd) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-c", PROBE_CODE.format(module=module_path)],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()
        return {"error": tail[-1] if tail else "子进程退出码 %d" % proc.returncode}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": "无法解析子进程输出: %r" % proc.stdout[-200:]}


def candidates():
    """列出"真实存在"的候选入口：返回 (相对路径, 可 import 的模块名)。"""
    found = []
    for directory in SEARCH_DIRS:
        for name in CANDIDATE_NAMES:
            path = Path(directory) / name if directory else Path(name)
            if not (ROOT / path).is_file():
                continue
            module = name[:-3] if not directory else "%s.%s" % (directory, name[:-3])
            found.append((str(path).replace(os.sep, "/"), module))
    return found


def self_check():
    """反向控制：在临时包里验证"这段测量代码"确实能把裸 app 与带路由 app 分开。

    探针失去分辨力时判据会**报红**，而不是因为"没抓到问题"而报绿。
    """
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        pkg = base / "probe_pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "bare.py").write_text(
            "from flask import Flask\napp = Flask(__name__)\n", encoding="utf-8")
        (pkg / "routed.py").write_text(
            "from flask import Flask\napp = Flask(__name__)\n"
            "@app.route('/api/health')\ndef health():\n    return {'ok': True}\n",
            encoding="utf-8")
        bare = _measure("probe_pkg.bare", base)
        routed = _measure("probe_pkg.routed", base)

    problems = []
    if bare.get("rules") != 1:
        problems.append("裸 app 应被测出 1 条规则（只有 static），实测 %r" % bare)
    if routed.get("rules", 0) < 2:
        problems.append("带路由的 app 应被测出 >=2 条规则，实测 %r" % routed)
    if bare.get("health") == 200:
        problems.append("裸 app 的 /api/health 不应是 200，实测 %r" % bare)
    if routed.get("health") != 200:
        problems.append("带路由 app 的 /api/health 应为 200，实测 %r" % routed)
    return problems


def main():
    print("候选入口搜索位置: 仓库根 + " + ", ".join(
        d + "/" for d in SEARCH_DIRS if d))
    print("候选文件名: " + ", ".join(CANDIDATE_NAMES))
    print()

    found = candidates()
    if not found:
        print("!! 一个候选入口文件都不存在 —— 线上会解析不到 Flask app。")
        return 1

    bad = []
    for path, module in found:
        result = _measure(module, ROOT)
        if "error" in result:
            print("  ERROR  %-16s %s" % (path, result["error"]))
            bad.append((path, result["error"]))
            continue
        rules = result["rules"]
        health = result["health"]
        verdict = "有路由" if rules > 1 else "**无路由**"
        line = "  %-16s 规则数=%-4s /api/health=%-4s -> %s" % (path, rules, health, verdict)
        if rules <= 1 or health != 200:
            print(line + "   ← 这个候选名一旦被平台解析到，线上就是「每个接口都 404」")
            bad.append((path, "规则数=%s /api/health=%s" % (rules, health)))
        else:
            print(line)

    print()
    print("自检（反向控制）:")
    problems = self_check()
    if problems:
        for item in problems:
            print("  SELF-CHECK FAIL  " + item)
    else:
        print("  OK  同一段测量代码能把裸 app（1 条规则/非 200）与带路由 app（>=2 条/200）分开")

    print()
    if bad or problems:
        print("裁决: 失败 —— 候选入口 %d 个中 %d 个解析出不可用的 app；自检问题 %d 项"
              % (len(found), len(bad), len(problems)))
        return 1
    print("裁决: 成立 —— %d 个候选入口全部解析出带路由的 app，"
          "解析顺序无论如何都不会改变线上行为" % len(found))
    return 0


if __name__ == "__main__":
    sys.exit(main())
