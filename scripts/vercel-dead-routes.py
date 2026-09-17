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

用法（仓库根目录）：
    .venv-audit/Scripts/python.exe scripts/vercel-dead-routes.py
退出码：有死路由 = 1。
"""
import json
import os
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


def main():
    config, rewrites = rewritten_routes()
    client = app.test_client()
    dead = []
    for source, route in rewrites:
        seen = probe(client, route)
        if all(is_fallthrough(entry) for entry in seen):
            dead.append((source, route))

    print("重写总数 %d / API 重写 %d / 死路由 %d" % (len(config["rewrites"]), len(rewrites), len(dead)))
    for source, route in dead:
        print("  DEAD %s -> _route=%s" % (source, route))
    if not dead:
        print("  所有 API 重写都能落到处理分支（参数化路由按方法逐个探过）")
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())
