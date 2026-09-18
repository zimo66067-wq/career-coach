# -*- coding: utf-8 -*-
"""domain.errors · 领域层错误类型

与 ``domain.internal.api_errors.ApiError`` 分开：ApiError 关心 HTTP 状态码，DomainError 只关心
"违反了哪条业务规则"。Service 层负责把 DomainError 翻译成 ApiError（Phase 3 接线）。
"""


class DomainError(ValueError):
    """违反领域不变量。``code`` 是稳定的机器可读标识，``message`` 面向用户/日志。"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)

    def __str__(self):
        return "[%s] %s" % (self.code, self.message)
