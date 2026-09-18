# -*- coding: utf-8 -*-
"""`UNHANDLED` 哨兵 —— 单独一个模块，唯一理由是**打断 import 环**。

拆分的直接后果是分派表和 handler 互相需要：

    api/dispatch.py  ──imports──►  api/handlers/*.py     （要调用它们）
    api/handlers/*.py ──imports──►  api/dispatch.py      （要拿 UNHANDLED）

放在同一个模块里就是一个真环：`api.dispatch` 执行到 import handler 时，handler 又回头
要 `api.dispatch` 里那个**还没执行到**的赋值，Python 直接 `ImportError`。
（这正是 `dependency-map.md §3.5` 说 `api/index.py ↔ services/*` 当年靠"函数内延迟
import 侥幸避开"的那种形态 —— 只是当时没人真的踩到。）

两种修法里选了后者：

* ❌ handler 里写 `from api.dispatch import UNHANDLED` 放进函数内 —— 环还在，只是被推迟；
* ✅ 把哨兵下沉到一个**叶子模块**，双方都依赖叶子，方向重新变成单向。

## 为什么哨兵不能用 `None`

每个 handler 的契约是「接住 → 返回响应；没接住 → 返回 `UNHANDLED`」。若用 `None`，
一个合法的 `return None`（Flask 眼里是"空 body 200"）就会被分派表当成"没接住"，
请求被**静默地**交给后面的 handler。哨兵让这两种情况不可能混淆：
判据是 `result is UNHANDLED`，身份比较，任何别的对象都不等。
"""
UNHANDLED = object()
