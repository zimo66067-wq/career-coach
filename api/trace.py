# -*- coding: utf-8 -*-
"""api.trace · Web 层专用的 trace id（Phase 7d 从 `domain/internal/trace.py` 拆出）

**为什么必须拆**：`trace_id()` 读 `request.headers`，它本来就属于 HTTP 层。
原来 `tools/trace.py` 把两件事塞在一个文件里 —— 纯函数 `new_trace_id()` 和这个要
Flask 请求上下文的 `trace_id()`。`tools/` 那一层没有任何禁配表，所以"文件里有个函数
import flask"从来没人管过。

7d 把它并入 `domain/` 之后，`tests/test_layering.py` 的规则 2（domain 不得 import flask）
立刻报了出来 —— 这不是误报。

而证据显示**调用方早就按层分开了，只是文件没分开**：

| 符号 | 消费者 | 都在哪一层 |
| --- | --- | --- |
| `trace_id()` | `api/handlers/wf01`、`api/handlers/wf02`、`api/handlers/wf03`、`api/http_layer` | **全部在 `api/`** |
| `new_trace_id()` | `services/diagnosis_service` | 服务层 |

于是拆法是确定的：纯的一半留在 `domain/internal/trace.py`（连同 `TRACE_ID_PATTERN`，
两边共用同一个口径），Web 的一半落在这里 —— `api/` 是唯一被允许 import flask 的层。
"""
from flask import request

from domain.internal.trace import TRACE_ID_PATTERN, new_trace_id


def trace_id():
    """Web 层用：透传合法的 `X-Trace-Id`，否则新生成一个。"""
    candidate = request.headers.get("X-Trace-Id", "")
    if TRACE_ID_PATTERN.fullmatch(candidate):
        return candidate
    return new_trace_id()
