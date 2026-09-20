# -*- coding: utf-8 -*-
"""vercel-dead-routes.py · vercel 重写是否有"死路由"（改写指向了没人处理的分支）

为什么需要它：生产入口是 `/api?_route=<route>` 这一层重写（`vercel.json`）。
本地 `test_client()` 走的是 `/api/<route>` 直连路径（`request_route()` 会自己剥前缀），
所以**本地全绿 ≠ 线上可达** —— 少一条重写，或重写指到一个分派表里没有的分支，
线上就是 404，而本地测试一点异常都看不出来。

判据（实证，不靠静态表比对）：
    对每条 API 重写发一次请求，看它是否落到 `route_api()` 的兜底 `not_found`。
    · 兜底 404 的 message 是固定的 "接口不存在。" —— 用它区分"路由没接上"与
      "路由接上了、只是这个 id/session 不存在"（后者也是 404，但是**正确**的 404）。
    · **必须逐个方法试**（GET / POST / DELETE / PUT / PATCH）：有些路由只在特定方法下
      进入分支（`/api/history/<id>` 只有 DELETE，用 GET 探会得到兜底 404，
      看起来像死路由，其实不是）。只要**存在一个方法**没落到兜底，就算接上了。
    · 带参数的重写（`$1`）拿不到真实参数值，同样只要求"不是全方法兜底 404"。

上面的判据只管**方向 A：重写 → 处理分支**。还有**方向 B：本地路由 → 重写覆盖**，
它原来没人看，而恰恰是"只坏在生产"的那种病：

    线上入口是**枚举式**的 —— `api/index.py` 里新增一条 `/api/xxx`，必须同时在
    `vercel.json` 里加一条 `source`，否则线上直接静态 404，而本地 `test_client()` 全绿
    （本地走 `/api/xxx` 直连，根本不经过重写）。所以逐条核：每个本地路由要么**本身就是
    某条重写的 destination**（函数自己的路径，如 `/api`），要么被某条 `source` 匹配上
    （含 `(.*)` / `:param` 形态）。这条不联网、不依赖部署状态。

两条判据合起来才闭合：A 抓"重写指向了空分支"，B 抓"分支没有重写指过来"。

用法（仓库根目录）：
    .venv-audit/Scripts/python.exe scripts/vercel-dead-routes.py
退出码：有死路由 或 有未被覆盖的本地路由 = 1。
"""
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 导入 app 前先隔离数据文件，避免碰真实库。
_BOOTSTRAP_TMP = tempfile.mkdtemp(prefix="vercel-dead-routes-")
os.environ.setdefault("RESUME_DB_PATH", os.path.join(_BOOTSTRAP_TMP, "dead-routes.db"))
os.environ.setdefault("DUMATE_CONSENT_SECRET", "vercel-dead-routes-secret")
os.environ.pop("DATABASE_URL", None)

from api.index import app  # noqa: E402

FALLTHROUGH_MESSAGE = "接口不存在。"
PROBE_METHODS = ("get", "post", "delete", "put", "patch")


def rewritten_routes():
    config = json.loads(open(os.path.join(ROOT, "vercel.json"), encoding="utf-8").read())
    items = []
    for rule in config["rewrites"]:
        destination = rule["destination"]
        if not rule["source"].startswith("/api/") or "?_route=" not in destination:
            continue
        items.append((rule["source"], destination.split("?_route=", 1)[1]))
    return config, items


def probe(client, route):
    """逐个方法探一次，返回 [(method, status, message), ...]。"""
    seen = []
    for method in PROBE_METHODS:
        response = getattr(client, method)("/api?_route=" + route, json={})
        body = response.get_json(silent=True) or {}
        seen.append((method.upper(), response.status_code, body.get("message")))
    return seen


def is_fallthrough(entry):
    return entry[1] == 404 and entry[2] == FALLTHROUGH_MESSAGE


def source_matcher(source):
    """把一条 rewrite 的 `source` 编译成能匹配具体路径的正则。

    只支持 `vercel.json` 里真实用到的两种形态：
    `(.*)`（正则捕获组）与 `:name` / `:name*`（路径参数）。
    刻意不做通用的 vercel 路由语法模拟 —— 那会变成又一份需要维护的规格。
    """
    pattern = re.escape(source)
    pattern = pattern.replace(r"\(\.\*\)", ".*")
    pattern = re.sub(r":[A-Za-z_]\w*\*", ".*", pattern)
    pattern = re.sub(r":[A-Za-z_]\w*", "[^/]*", pattern)
    return re.compile("^" + pattern + "$")


def local_rules():
    """本地路由表 = `api/index.py` 里 `add_url_rule` 注册的那一批（endpoint 前缀 route_）。"""
    return sorted(
        str(rule) for rule in app.url_map.iter_rules() if rule.endpoint.startswith("route_")
    )


def uncovered_local_rules(config):
    """本地路由里，既不是某条重写的 destination、也没被任何 source 覆盖的那些。"""
    sources = [rule["source"] for rule in config["rewrites"]]
    matchers = [source_matcher(source) for source in sources]
    destinations = {
        rule["destination"].split("?", 1)[0] for rule in config["rewrites"]
    }
    missing = []
    for rule in local_rules():
        if rule in destinations:
            continue
        # /api/target-jobs/<id>/analyse → /api/target-jobs/sample/analyse
        concrete = re.sub(r"<[^>]+>", "sample", rule)
        if not any(matcher.match(concrete) for matcher in matchers):
            missing.append((rule, concrete))
    return missing


def self_test(config):
    """反向控制探针：抽掉一条精确重写，方向 B 必须立刻报出对应的那条路由。

    没有这一步，方向 B 可能因为匹配正则写得太松（例如把所有 source 都编译成 `^.*$`）
    而**永远绿** —— 那种"绿着失效"比红更贵。返回问题串，通过则返回 None。
    """
    exact = [
        rule["source"] for rule in config["rewrites"]
        if rule["source"].startswith("/api/") and "(" not in rule["source"] and ":" not in rule["source"]
    ]
    if not exact:
        return "vercel.json 里找不到「精确路径」形态的 API 重写，方向 B 无法自检（结构变了？）"
    victim = exact[0]
    weakened = {"rewrites": [rule for rule in config["rewrites"] if rule["source"] != victim]}
    missing = {rule for rule, _ in uncovered_local_rules(weakened)}
    if victim not in missing:
        return ("抽掉重写 %s 以后方向 B 仍然全绿 —— 匹配逻辑失效，这条判据不可信" % victim)
    return None


def main():
    config, rewrites = rewritten_routes()
    client = app.test_client()
    dead = []
    for source, route in rewrites:
        seen = probe(client, route)
        if all(is_fallthrough(entry) for entry in seen):
            dead.append((source, route))

    uncovered = uncovered_local_rules(config)
    probe_problem = self_test(config)

    print("重写总数 %d / API 重写 %d / 死路由 %d"
          % (len(config["rewrites"]), len(rewrites), len(dead)))
    for source, route in dead:
        print("  DEAD %s -> _route=%s" % (source, route))
    if not dead:
        print("  [A] 所有 API 重写都能落到处理分支（参数化路由按方法逐个探过）")

    print("本地路由 %d / 未被重写覆盖 %d" % (len(local_rules()), len(uncovered)))
    for rule, concrete in uncovered:
        print("  UNCOVERED %s（线上会拿它当静态路径，必然 404）" % rule)
    if not uncovered:
        print("  [B] 每个本地路由要么是重写目标本身、要么被某条 source 覆盖")

    if probe_problem:
        print("  自检失败：%s" % probe_problem)
    else:
        print("  自检通过：抽掉一条重写后方向 B 会红（判据不是空判）")

    return 1 if (dead or uncovered or probe_problem) else 0


if __name__ == "__main__":
    sys.exit(main())
