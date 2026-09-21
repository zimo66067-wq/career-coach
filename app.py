# -*- coding: utf-8 -*-
"""Vercel 入口：把一个**带路由**的 Flask app 绑定在根目录的候选名上。

## 为什么要有这个文件

Vercel 的 Flask 预设**按文件名**找"里面有 `Flask` 实例 `app` 的模块"，候选名是
`app.py` / `index.py` / `server.py` / `main.py` / `wsgi.py` / `asgi.py`，位置是
仓库根（以及 `src/`、`app/`）。**根目录优先**。

2026-09-21 之前根目录没有这个文件，于是平台解析到了 `api/app.py` —— 那只是为了消除循环
import 而把 app 对象下沉成的**叶子模块**（`Flask(__name__)`，不注册任何路由）。线上被服务的
就是它：任何路径都返回 Werkzeug 默认 404（207 B、无 `Cache-Control: no-store`），而同一个
app 在本地对 `/api/health` 返回 200。详见 `api/app_instance.py` 的模块注释。

## 为什么不用 `[tool.vercel] entrypoint`

那是 Vercel 文档给的另一个显式声明方式（`pyproject.toml` 里
`[tool.vercel] entrypoint = "模块:变量"`），但 **`pyproject.toml` 一旦存在，平台就改用它作为
依赖来源**，会以本仓库为 Python 项目去安装 —— 本仓库是 flat layout、有多个顶层包
（`api`/`domain`/`providers`/`repositories`/`services` …），setuptools 自动发现直接报
"Multiple top-level packages discovered"，**构建失败**（2026-09-21 实测，部署
`dpl_5C4T1VTqfAibMjrHDXetHndVJcnd` 就是这么挂的）。

所以入口用"文件名"这条路径声明，`pyproject.toml` 保持不存在，依赖仍走 `requirements.txt`。

## 它不制造第二个 app

`from api.index import app` 拿到的是**同一个对象**（`api.app_instance.app is api.index.app`）。
这里只是换个位置再导出一次名字。

**真正的保证不靠"根目录优先"这条顺序**：`api/` 下唯一的入口候选 `index.py` 也指向同一个
带路由的 app，所以解析顺序无论怎么变，结果都一样 —— 这条性质由
`scripts/entrypoint-resolution-check.py` 逐个候选复算，不是靠注释承诺。
"""
from api.index import app  # noqa: F401
