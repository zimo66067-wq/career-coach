# -*- coding: utf-8 -*-
"""把「响应长什么样」集中到一处（Phase 7c 从 `api/index.py` 逐字拆出）。

这里放的是**每一层都会碰到**的横切代码：CORS 头、跨站写保护、六个错误处理器、
以及 `api_response` / `require_json_object` 两个统一出口。它们的共同点是"决定这次请求
最终回什么形状的 JSON"，跟具体是哪条路由无关。

## 为什么是 `register_http_layer(app)` 而不是模块级装饰器

原来写的是模块级 `@app.after_request` / `@app.errorhandler(...)`，意味着**import 这个
模块就等于改全局 app**（模块级副作用）。拆出来后改成显式注册函数，好处有两个：

1. 依赖方向看得见 —— 这个模块不再"偷偷"持有 app，而是被入口递进来；
2. 注册什么、按什么顺序，一处读完。

`app.after_request(fn)` / `app.register_error_handler(cls, fn)` 与对应的装饰器语义等价
（装饰器本身就是调用它们并返回原函数），所以这是纯搬运。

## 观察面

`register_http_layer` 的**注册项集合**是可数的：1 个 after_request、1 个 before_request、
6 个 errorhandler。少注册一个不会有任何测试直接报错（表现是某个分支回落默认 HTML 错误页），
所以 `tests/test_phase7c_contract.py` 把这个集合钉住了。

## 为什么第一方前端**不听**平台变量（2026-09-21）

`configured_origins()` 原来写的是"平台变量覆盖默认值"：

    os.environ.get("DUMATE_ALLOWED_ORIGINS", PUBLIC_PAGES_ORIGIN)

默认值本身是对的（不设置时就是仓库自带那个 Pages 源）。坏的是这个**替换**语义 ——
平台只要设置了这个变量（哪怕是为了别的源），第一方源就被整体换掉，于是
"**忘了把第一方源也列进去**"变成一条比"根本没设置"更坏的配置。而它三处都看不见：

* 仓库里看不见（默认值是好的，diff 里也没有它）；
* 本地 / CI 看不见（同源路径根本不经过 CORS，测试也不会去读线上配置）；
* 门禁看不见（没有判据探线上）。

2026-09-21 实测正是这个状态：`https://zimo66067-wq.github.io/career-coach/` 这个前端
**真实在线**、且它调的就是本 API（`public/js/pages-api-config.js` 就是为它写的），
但预检无 `Access-Control-Allow-Origin`、写操作回 403「请求来源未获授权」。

现在改成**并集**：`第一方源 ∪ 平台变量里额外声明的源`。变量名保留（它已经出现在
Vercel 控制台、`README.md`、`.env.example` 里，改名只增加迁移负担），语义是**追加**。
这样"省略"不再是可能的破坏动作 —— 真要禁掉第一方源，只能改本文件的代码，
而那会是一次 code review 里看得见的 diff（这是**决定**，不是遗漏）。

判据两边都有：`tests/test_api_boundary.py` 的
`test_cors_builtin_pages_origin_survives_env_override`（把语义改回替换即变红），
以及 `scripts/api-prod-probe.py` 第 3 节（探线上，**带敌对源的反向控制**）。
"""
import os
import re

from flask import jsonify, request
from werkzeug.exceptions import HTTPException

from domain.errors import DomainError
from services.target_job_service import TargetJobError
from domain.internal.api_errors import ApiError
from api.trace import trace_id

from api.app_instance import app
from api.constants import PUBLIC_PAGES_ORIGIN


def builtin_origins():
    """仓库自带的第一方前端的源 —— **永远**在放行名单里，不受平台变量影响。

    它不是"默认值"，是并集的一支。理由见模块文档「为什么第一方前端不听平台变量」。
    """
    return {PUBLIC_PAGES_ORIGIN.rstrip("/")}


def env_origins():
    """平台变量 `DUMATE_ALLOWED_ORIGINS` 里额外声明的跨源前端（可为空、可多个）。"""
    values = os.environ.get("DUMATE_ALLOWED_ORIGINS", "")
    return {origin.strip().rstrip("/") for origin in values.split(",") if origin.strip()}


def configured_origins():
    """放行名单 = 第一方源 ∪ 平台变量里额外声明的源。

    **刻意是并集，不是"变量覆盖默认值"** —— 后者正是 2026-09-21 那条渠道静默失效的机制
    （见模块文档）。改成并集后，平台侧的**省略**不再能关掉第一方渠道。
    """
    return builtin_origins() | env_origins()


def origin_allowed(origin):
    if not origin:
        return False
    normalized = origin.rstrip("/")
    if normalized == request.host_url.rstrip("/"):
        return True
    if normalized in configured_origins():
        return True
    if os.environ.get("APP_ENV", "production").lower() != "production":
        return bool(re.fullmatch(r"http://(?:localhost|127\.0\.0\.1)(?::\d+)?", normalized))
    return False


def apply_cors(response):
    origin = request.headers.get("Origin", "")
    if origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin.rstrip("/")
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, X-Trace-Id, X-Consent-Token, X-Guest-Token, Authorization"
        )
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Max-Age"] = "600"
        existing_vary = response.headers.get("Vary", "")
        response.headers["Vary"] = ", ".join(filter(None, [existing_vary, "Origin"]))
    response.headers["Cache-Control"] = "no-store"
    return response


def reject_cross_site_writes():
    """Reject browser state changes from an untrusted Origin.

    Header-authenticated guest requests need the same protection as cookie
    sessions: a leaked consent/guest token must not make a hostile browser
    origin acceptable. Non-browser clients that omit Origin remain supported.
    """
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    origin = request.headers.get("Origin", "").strip()
    if origin and not origin_allowed(origin):
        raise ApiError("csrf_rejected", "请求来源未获授权。", 403)
    return None


def handle_api_error(error):
    payload = {"error": error.code, "message": error.message, "trace_id": trace_id()}
    retry_after = getattr(error, "retry_after", None)
    if retry_after:
        payload["retry_after_seconds"] = int(retry_after)
    response = jsonify(payload)
    response.status_code = error.status
    if retry_after:
        response.headers["Retry-After"] = str(int(retry_after))
    return response


def handle_domain_error(error):
    """领域规则被违反 → 422，并把领域层的机器可读 code 原样带出。

    领域错误是"这个请求不合法"，不是"服务坏了"，所以不能落到 500 处理器；
    集中在 App 层翻译一次，路由里就不必逐个 try/except。
    """
    return jsonify({
        "error": error.code,
        "message": str(error),
        "trace_id": trace_id(),
    }), 422


def handle_target_job_error(error):
    return jsonify({
        "error": error.code,
        "message": error.message,
        "trace_id": trace_id(),
    }), error.status


def handle_content_too_large(_error):
    return jsonify({
        "error": "payload_too_large",
        "message": "文件或文本超过服务允许的大小，请精简后重试。",
        "trace_id": trace_id(),
    }), 413


def handle_http_error(error):
    """Keep ordinary routing and method errors out of the 500 handler."""
    if error.code == 404:
        return jsonify({
            "error": "not_found",
            "message": "接口不存在。",
            "trace_id": trace_id(),
        }), 404
    if error.code == 405:
        return jsonify({
            "error": "method_not_allowed",
            "message": "请求方法不被允许。",
            "trace_id": trace_id(),
        }), 405
    return jsonify({
        "error": "http_error",
        "message": "请求无法处理。",
        "trace_id": trace_id(),
    }), error.code or 500


def handle_unexpected_error(error):
    # Do not return provider details, local paths, or user material to browsers.
    app.logger.exception("Unhandled API error: %s", type(error).__name__)
    return jsonify({
        "error": "internal_error",
        "message": "诊断服务暂时不可用，请稍后重试。",
        "trace_id": trace_id(),
    }), 500


def api_response(payload, status=200):
    payload.setdefault("trace_id", trace_id())
    return jsonify(payload), status


def require_json_object(label="请求"):
    """Return a JSON object and reject malformed or array-shaped bodies."""
    if not request.is_json:
        raise ApiError("invalid_content_type", f"{label}必须使用 JSON 格式。", 415)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("invalid_request", f"{label}格式无效。", 422)
    return body


def register_http_layer(target):
    """把上面这些挂到 app 上。**只在这里挂**，顺序即注册顺序。"""
    target.after_request(apply_cors)
    target.before_request(reject_cross_site_writes)
    target.register_error_handler(ApiError, handle_api_error)
    target.register_error_handler(DomainError, handle_domain_error)
    target.register_error_handler(TargetJobError, handle_target_job_error)
    target.register_error_handler(413, handle_content_too_large)
    target.register_error_handler(HTTPException, handle_http_error)
    target.register_error_handler(Exception, handle_unexpected_error)
    return target
