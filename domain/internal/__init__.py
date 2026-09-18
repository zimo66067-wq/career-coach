# -*- coding: utf-8 -*-
"""domain.internal · 领域层的层内工具（Phase 7d 由 `tools/` 归并而来）

本子包的存在理由直接写在 `docs/dependency-map.md` §5 第 4 条：

> `tools/` 逐步并入 `domain/` + `providers/`，**或降级为 `domain` 的内部工具**

`domain/` 顶层（见 `domain/__init__.py` 的分层契约）只放"什么算合法"的规则；
下面这些**不是规则**，是各层共用的机制。放顶层会把那份契约说成假话，所以落在这一层：

- ``api_errors``      ApiError：带 HTTP 状态码的错误载体。与 ``domain.errors.DomainError``
                      **刻意分开**，理由见 `domain/errors.py` 的 docstring。
- ``contracts``       跨模块常量 + 两份 JSON Schema 校验器
- ``trace``           trace-id 生成（模块级不 import flask，见 `tests/test_layering.py` 坑 3）
- ``log_sanitize``    日志落盘前的脱敏管道
- ``extract_text``    PDF / DOCX / TXT 纯文本提取
- ``radar_adapter``   AbilityProfile → ECharts option

**分层性质**：这六个模块**零仓库内 import** —— 它们是依赖图里的**叶子**。
叶子不可能造出环，因此任何层都可以依赖它们。`providers/model.py` 取 `ApiError`
正是靠这条：`tests/test_layering.py` 的
``test_providers_may_only_reach_domain_through_leaves`` 把它变成判据，
而不是一句约定。
"""
