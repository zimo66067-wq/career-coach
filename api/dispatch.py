# -*- coding: utf-8 -*-
"""单函数分派表（Phase 7c：从 `api/index.py` 里那个 917 行的 `route_api()` 拆出）。

`api/index.py` 原本是一个 917 行的 `route_api()`（原文件 664–1580 行），里面 38 个
`if route == ...` 与 12 个 `route.startswith(...)` 顺次排开。
拆开之后，分派 = **一张有序表 + 一个哨兵 + 一个兜底 404**。

## 为什么用哨兵，不用 None

每个 handler 的契约是：

    接住 → 返回响应（Flask 能直接吃的东西）；没接住 → 返回 UNHANDLED

`None` 不行：它在 Flask 眼里是"视图没返回东西"，将来一旦有人真的 `return None` 表示
空响应，就会与"没接住"撞车 —— 表现是请求被**静默地**交给后面的 handler，
而这条路径没有任何测试会红。哨兵让这两种情况不可能混淆。

## 顺序为什么不重要（但仍然确定）

每个 handler 认领的是**一个互不相交的路由前缀族**：`wf01/`、`profile/`、`target-jobs/`……
没有任何一条路由名同属两族，所以顺序在语义上无关。表按产品分类法排（WF-01→WF-07，
再接 Phase 3 的档案 / Phase 4 的行动闭环，最后是运维与健康检查），是为了**读起来像产品**，
不是为了分派正确。

"互不相交"是**判据**而不是声明：`tests/test_phase7c_contract.py` 用 AST 把每个 handler
里的路由字面量抽出来、算族名，断言族名不重复。有人把 `wf02/x` 写进 `wf04.py` 会立刻红。

## 哨兵在哪

`UNHANDLED` 住在 `api/sentinel.py`（叶子模块），不住在这里 —— 因为 handler 也要 import 它，
放在本模块会形成 `dispatch ⇄ handlers` 的**真 import 环**。理由与两种修法的取舍写在
`sentinel.py` 的 docstring 里。

## 观察面

看：每个 `api/handlers/*.py` 的 `route ==` / `route.startswith()` 字面量族。
不看：handler 内部的语义、`vercel.json` 的重写、OPTIONS 白名单。
⇒ 「重写到得了分派」由 `scripts/vercel-dead-routes.py` 实证（38 条重写逐方法探），
   「族不重叠」由本节说的那条判据管，两件事各归各。
"""
from tools.api_errors import ApiError

from api.sentinel import UNHANDLED

from api.handlers.account import handle_account
from api.handlers.actions import handle_actions
from api.handlers.admin import handle_admin
from api.handlers.health import handle_health
from api.handlers.organizations import handle_organizations
from api.handlers.profile import handle_profile
from api.handlers.target_jobs import handle_target_jobs
from api.handlers.wf01 import handle_wf01
from api.handlers.wf02 import handle_wf02
from api.handlers.wf03 import handle_wf03
from api.handlers.wf04 import handle_wf04
from api.handlers.wf05 import handle_wf05
from api.handlers.wf06 import handle_wf06
from api.handlers.wf07 import handle_wf07

#: "本族没接住"的哨兵。定义在 `api/sentinel.py`（叶子模块），上面的 import 只是取用 ——
#: 直接定义在本模块会与 handler 互相 import 成环。语义见 `sentinel.py`。
#: 判据是身份比较（`result is UNHANDLED`），所以任何"值相等"的东西都不算。

#: 有序分派表。族内顺序 = 原 `route_api()` 里的相对顺序（未打乱，便于逐行对照）。
HANDLERS = (
    handle_wf01,        # wf01/consent, wf01/upload
    handle_wf02,        # wf02/diagnose, wf02/optimize, wf02/apply-rewrite
    handle_wf03,        # wf03/upload, wf03/jd, wf03/match
    handle_wf04,        # wf04/stream, wf04/start, wf04/answer, wf04/end
    handle_wf05,        # wf05/ability
    handle_wf06,        # wf06/delete
    handle_wf07,        # wf07/cover-letter, wf07/applications[/<id>/…]
    handle_profile,     # profile, profile/evidence/…
    handle_target_jobs, # target-jobs, target-jobs/<id>[/…]
    handle_actions,     # actions, actions/<id>[/…]
    handle_organizations,  # f5/organizations/…
    handle_account,     # auth/{register,login,logout,me}, history[/<id>]
    handle_admin,       # admin/resumes, admin/export
    handle_health,      # health
)


def dispatch(route):
    """把路由名交给第一个认领它的 handler；没人认领 → 与原来一样 404。

    注意：返回 `None` 会被当作**已接住**（因为判据是 `is UNHANDLED`），这是有意的 ——
    `None` 在 Flask 里是合法响应（空 body、200），把它当成"没接住"会改变行为。
    """
    for handler in HANDLERS:
        result = handler(route)
        if result is not UNHANDLED:
            return result
    raise ApiError("not_found", "接口不存在。", 404)
