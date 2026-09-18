# -*- coding: utf-8 -*-
"""Shared trace-id helper (phase 5: extracted from api/index.py).

Phase 7d 之后本模块只剩**纯**的那一半：

* `new_trace_id()` —— 纯函数，不碰请求上下文（服务层唯一该用的入口）；
* `TRACE_ID_PATTERN` —— trace id 的合法形态，`api/trace.py` 的 `trace_id()` 共用同一口径。

Web 层那一半（`trace_id()`，要先有 Flask 请求上下文才能透传 `X-Trace-Id`）
已拆到 `api/trace.py`。**触发这次拆分的是一条判据，不是审美**：并进 `domain/` 后，
`tests/test_layering.py` 规则 2「domain 不得 import flask」立刻把那个函数内的
延迟 `import flask` 报了出来（规则 2 连函数体内的 import 也算，见该文件"坑 2"）。
"""
import re
import uuid

TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,96}$")


def new_trace_id():
    """生成一个新的 trace id（纯函数，可在没有 web 层时调用）。"""
    return "api_" + uuid.uuid4().hex[:16]
