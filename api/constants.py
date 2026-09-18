# -*- coding: utf-8 -*-
"""API 层的纯常量（Phase 7c 从 `api/index.py` 逐字拆出）。

放这里的唯一理由：这些值原先散落在入口文件顶部，而**所有**层都要用（中间件、校验、
同意签名、限流）。拆出来之后 `api/` 内部的依赖方向是单向的 —— 大家都依赖本模块，
本模块只依赖标准库。

## 一条实测发现（拆分时才看清楚的）

原 `api/index.py` 顶部先写了

    from tools.contracts import MAX_TEXT_CHARS, MIN_TEXT_CHARS

然后在 10 行之后**又赋值了一遍**：

    MAX_TEXT_CHARS = 200_000
    MIN_TEXT_CHARS = 20

也就是说那次 import 拿到的名字**立刻被同名常量覆盖**，是个哑绑定（两者的值恰好一致：
`tools/contracts.py:14-15` 也是 20 / 200_000）。拆到这里时只保留**生效的那一份**，
值一字不改；那个 import 不再需要，因为 API 层用的一直是这里的常量。

## `TRACE_ID_PATTERN` 是死的（记录，不在本轮删）

`api/index.py` 里定义了它但**没有任何引用**；真正在用的同名模式在 `tools/trace.py:15`。
7c 的 DoD 是"拆分"，不是"删代码"，所以这里照搬保留，并把证据记在
`docs/phase7c-report.md`，留给后续阶段决定 —— 混进这一轮会让"对外行为零变化"这句话变浑。
"""
import re

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
MIN_TEXT_CHARS = 20
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
PUBLIC_PAGES_ORIGIN = "https://zimo66067-wq.github.io"
TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,96}$")
CONSENT_TOKEN_SALT = "career-coach-consent-v1"
GUEST_TOKEN_SALT = "career-coach-guest-v1"
DEFAULT_CONSENT_MAX_AGE_SECONDS = 1800
DEFAULT_GUEST_MAX_AGE_SECONDS = 365 * 86400
