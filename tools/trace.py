# -*- coding: utf-8 -*-
"""Shared trace-id helper (phase 5: extracted from api/index.py).

两个函数分得很清楚，**服务层只能用 `new_trace_id()`**：

* `new_trace_id()` —— 纯函数，不碰请求上下文；
* `trace_id()`      —— **Web 层专用**：优先透传请求头 `X-Trace-Id`。

flask 在 `trace_id()` **函数内**才导入（Phase 5）：这样 `import tools.trace`
本身不带 web 依赖，服务层引用 `new_trace_id` 不会把 Flask 拖进依赖图。
"""
import re
import uuid

TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,96}$")


def new_trace_id():
    """生成一个新的 trace id（纯函数，可在没有 web 层时调用）。"""
    return "api_" + uuid.uuid4().hex[:16]


def trace_id():
    """Web 层用：透传合法的 `X-Trace-Id`，否则新生成一个。"""
    from flask import request

    candidate = request.headers.get("X-Trace-Id", "")
    if TRACE_ID_PATTERN.fullmatch(candidate):
        return candidate
    return new_trace_id()

