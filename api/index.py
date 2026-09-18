"""Vercel API entry point for the unified career-coach workflows (WF-01~06).

The service processes uploaded material only in the current request and stores
only de-identified, anonymized session data in a lightweight SQLite store
(/tmp by default; ephemeral on Vercel).  Real resumes, JD texts and model
outputs are never logged verbatim.

---
Phase 7c：本文件只剩「入口」这一件事 —— 建 app、装中间件、把路由名分派给
`api/handlers/*`、挂本地测试路由表，以及**再导出**既有消费者一直从 `api.index` 取的符号。
50 个路由分支（38 条 `if route == ...` + 12 条 `route.startswith(...)`）已经搬走，
这里不再有业务分支。拆分前本文件 1621 行。
（**故意不写"现在多少行"**：写 101 实测 105，改这个数字的动作又把行数改成 106 —— 会自我漂移的
数字不属于 docstring；快照记在 `docs/phase7c-report.md`，`work/verify-numbers.py` 可复算。）

三个必须留在这里的东西（不是懒得搬，是搬了会坏）：

1. **`REPOSITORY_ROOT` 与 `sys.path` 插入** —— 线上入口就是本文件，`tools/` / `services/`
   能被 import 全靠这三行。移到别处等于赌"Vercel 一定先 import 了包"。
2. **`app` 对象** —— `vercel.json` 的 `functions` 指向 `api/index.py`，文件名与
   `app` 这个变量名都是部署契约的一部分（`scripts/vercel-dead-routes.py` 也是
   `from api.index import app`）。
3. **本地测试路由表** —— 49 条规则共用一次 `add_url_rule`，是本地 `test_client()` 与线上
   `?_route=` 重写的对照面。
"""
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from flask import request  # noqa: E402

from api.app import app  # noqa: E402
from api.dispatch import dispatch  # noqa: E402
from api.http_layer import register_http_layer  # noqa: E402
from api.routing import handle_options, request_route  # noqa: E402
from api.startup import bootstrap  # noqa: E402

# 兼容再导出：tests/ 与 scripts/ 一直从 `api.index` 取这些符号。
# 这条清单**不是**"顺手留着"，它有判据 —— tests/test_phase7c_contract.py 会把
# tests/ 与 scripts/ 里 `api_module.X` / `from api.index import X` 全部抽出来，
# 断言它们在这里都能取到；反向也断言（入口不许 import 既不用、也没人取的符号）。
from services.diagnosis_service import build_rule_based_resume_profile  # noqa: E402,F401
from services.match_service import build_job_profile, match_job_profile  # noqa: E402,F401
from tools.api_errors import ApiError  # noqa: E402,F401
from tools.database import load_session  # noqa: E402,F401

# 冷启动引导：显式调用，不再靠"import 本模块就顺带跑一次"的隐式副作用。
# 迁移幂等；失败不抛、由 /api/health 照实上报（见 api/startup.py）。
bootstrap()

# 中间件的注册点只有这一处：CORS、跨站写保护、六个错误处理器。
register_http_layer(app)


def route_api(**_ignored):
    """单函数分发：OPTIONS 先答，其余交给 `api/dispatch.py` 的有序表。

    Flask 会把 49 条本地路由规则都绑到这个 view_func 上，所以它必须接受
    `**_ignored`（Flask 传进来的路径参数）。
    """
    route = request_route()
    if request.method == "OPTIONS":
        return handle_options(route)
    return dispatch(route)


# Local test routes plus the single Vercel function route used by vercel.json.
for _rule in (
    "/api", "/api/wf01/consent", "/api/wf01/upload", "/api/wf02/diagnose",
    "/api/wf03/upload", "/api/wf03/jd", "/api/wf03/match",
    "/api/wf04/start", "/api/wf04/answer", "/api/wf04/end",
    "/api/wf05/ability", "/api/wf06/delete", "/api/health",
    "/api/admin/resumes", "/api/admin/export",
    "/api/auth/register", "/api/auth/login", "/api/auth/logout", "/api/auth/me",
    "/api/history", "/api/history/<id>",
    "/api/wf04/stream",
    "/api/wf02/optimize", "/api/wf02/apply-rewrite",
    "/api/wf07/cover-letter", "/api/wf07/applications",
    "/api/f5/organizations/status", "/api/f5/organizations/suggest",
    "/api/f5/organizations/discover", "/api/f5/organizations/detail",
    "/api/f5/organizations/jobs",
    # Phase 3 · 核心闭环：职业证据档案 + 目标岗位分析
    "/api/profile",
    "/api/profile/evidence/candidates",
    "/api/profile/evidence/<id>",
    "/api/profile/evidence/<id>/confirm",
    "/api/profile/evidence/<id>/reject",
    "/api/profile/evidence/<id>/edit",
    "/api/target-jobs",
    "/api/target-jobs/<id>",
    "/api/target-jobs/<id>/analyse",
    "/api/target-jobs/<id>/decision",
    # Phase 4 · 行动闭环：缺口 → 可执行行动
    "/api/actions",
    "/api/actions/<id>",
    "/api/actions/<id>/start",
    "/api/actions/<id>/complete",
    "/api/actions/<id>/outcome",
    "/api/actions/<id>/drop",
    # Phase 4 · 投递结果回流
    "/api/wf07/applications/<id>/outcome",
    "/api/wf07/applications/<id>/outcomes",
):
    app.add_url_rule(_rule, endpoint="route_" + _rule.replace("/", "_") or "root", view_func=route_api,
                     methods=["GET", "POST", "DELETE", "OPTIONS"])
