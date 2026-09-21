"""Vercel 入口的**文件名兜底**（真入口是 `api/index.py`）。

背景（2026-09-21 实测，详见 `pyproject.toml` 的注释）：
Vercel 的 Flask 预设找入口有**两条**路径 —— 显式声明的 `tool.vercel.entrypoint`
（`pyproject.toml` 里已声明为 `api.index:app`），以及**按文件名**解析的候选列表
（`app.py` / `index.py` / `server.py` / `main.py` / `wsgi.py` / `asgi.py`，
根目录优先）。而 `api/` 目录下恰好有一个 `api/app.py` —— 那只是"存放 app 对象的
叶子模块"，零路由零中间件；线上当时就是在服务它（任何路径都返回 Werkzeug 默认
404，且没有应用必设的 `Cache-Control: no-store`）。

这个文件把**同一个** `app` 对象在根目录再绑定一次：根目录优先于子目录、
`app.py` 又是候选名第一顺位。于是无论 Vercel 走哪条解析路径，落到线上的都是
`api/index.py` 那个装好 50 条路由与 HTTP 层的 app。

它不是第二个 app —— `api.app.app is api.index.app` 本来就是同一个对象，
这里只是换个位置再导出同一个名字。判据（`scripts/api-prod-probe.py`）认的是
线上响应，不认这个文件在不在。
"""
from api.index import app  # noqa: F401
