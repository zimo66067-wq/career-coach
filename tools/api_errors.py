# -*- coding: utf-8 -*-
"""Shared API error type (phase 5: extracted from api/index.py)."""


class ApiError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
