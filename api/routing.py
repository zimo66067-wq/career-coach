# -*- coding: utf-8 -*-
"""路由名解析与 CORS 预检应答（Phase 7c 从 `api/index.py` 逐字拆出）。

## `request_route()`：两条入口共用一个名字空间

线上入口是 vercel 重写 `/api/wf03/jd` → `/api?_route=wf03/jd`，本地测试走直连
`/api/wf03/jd`。`request_route()` 把两者收敛成同一个字符串（`wf03/jd`），
所以 `route_api()` 的分派表**只需要认识一种写法**。

这条不变量是 `scripts/vercel-dead-routes.py` 的存在理由：它逐条重写按方法探一遍，
确认"本地绿 == 线上可达"。改这里要同步看一眼那个脚本。

## `handle_options()`：预检只对真实存在的路由点头

CORS 预检不该成为"接口存在性"的旁路 —— 未登记的路由照样 404，否则扫描器可以用
OPTIONS 把一个不存在的端点探测成"存在"。所以这里维护的是**显式清单**，
外加 6 个参数化前缀。清单必须与 `api/handlers/*` 里的分支集合保持一致：
少一条，浏览器就会在预检阶段被拦下（真实请求根本没发出，日志里什么也看不到）。

`str.startswith` 接受元组，所以 6 个前缀写成一行 —— 与原实现（6 个 `or`）等价。
"""
from flask import request

from tools.api_errors import ApiError

#: 精确匹配的预检白名单。
OPTIONS_ROUTES = frozenset({
    "wf01/consent", "wf01/upload", "wf02/diagnose",
    "wf03/upload", "wf03/jd", "wf03/match",
    "wf04/start", "wf04/answer", "wf04/end",
    "wf05/ability", "wf06/delete", "health",
    "admin/resumes", "admin/export",
    "auth/register", "auth/login", "auth/logout", "auth/me",
    "history",
    "wf04/stream",
    "wf02/optimize", "wf02/apply-rewrite",
    "wf07/cover-letter", "wf07/applications",
    "f5/organizations/status", "f5/organizations/suggest",
    "f5/organizations/discover", "f5/organizations/detail",
    "f5/organizations/jobs",
    "profile", "profile/evidence/candidates", "target-jobs", "actions",
})

#: 带参数的预检前缀（`<id>` 这类）。
OPTIONS_PREFIXES = (
    "history/", "f5/", "profile/evidence/", "target-jobs/", "actions/",
    "wf07/applications/",
)


def request_route():
    """Resolve Vercel rewrite routes while retaining direct local test routes."""
    rewritten = request.args.get("_route")
    if rewritten:
        return rewritten.strip("/")
    if request.path.startswith("/api/"):
        return request.path[len("/api/"):]
    return ""


def handle_options(route):
    """预检：登记过的回 204，其余照旧 404。"""
    if route in OPTIONS_ROUTES or route.startswith(OPTIONS_PREFIXES):
        return ("", 204)
    raise ApiError("not_found", "接口不存在。", 404)
