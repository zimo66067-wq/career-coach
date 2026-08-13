# -*- coding: utf-8 -*-
"""Shared trace-id helper (phase 5: extracted from api/index.py)."""
import re
import uuid

from flask import request

TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,96}$")


def trace_id():
    candidate = request.headers.get("X-Trace-Id", "")
    if TRACE_ID_PATTERN.fullmatch(candidate):
        return candidate
    return "api_" + uuid.uuid4().hex[:16]
