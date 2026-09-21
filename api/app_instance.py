# -*- coding: utf-8 -*-
"""Flask 应用对象（Phase 7c 从 `api/index.py` 拆出）。

这是 `api/` 内部唯一的**叶子**模块：它只依赖 flask 与 `api.constants`，不依赖任何
兄弟模块，也不依赖仓库下层。这个性质是有用的 ——

* `api/startup.py`（迁移）与 `api/http_layer.py`（错误处理）需要 `app.logger`；
* `api/security.py` 需要 `app.config["TESTING"]`；
* `api/handlers/*` 需要 `app.logger` 记数据库写入失败。

如果这些模块都回头 `from api.index import app`，就形成 `index → handlers → index`
的真循环（`dependency-map.md §3.5` 警告过的那种）。把 app 下沉成一个叶子模块之后，
依赖方向变成单向的 `index → handlers → app`，不需要任何"函数内延迟 import 来侥幸绕开"。

`app.config["MAX_CONTENT_LENGTH"]` 与常量同处一地：它是这个 app 自身的配置，
放在建 app 的地方比放在入口文件里更不容易被漏掉。

## 文件名是部署契约的一部分（2026-09-21 起，原名 `api/app.py`）

这个模块**绝不能**叫 `app.py` / `index.py` / `server.py` / `main.py` / `wsgi.py` / `asgi.py`。
Vercel 的 Flask 预设是**按文件名**找"里面有 `Flask` 实例 `app` 的模块"的，候选名里
`app.py` 排第一 —— 它原名就叫 `app.py`，于是平台 import 了这个**只建对象、不注册路由**的
叶子模块，把"1 条规则（只有 static）"的 app 推上了生产：任何路径都返回 Werkzeug 默认 404。

实测指纹（这次就是靠它定案的）：只 import 本模块时，`/api/health` 返回
**404 / 207 B / md5 `e46c4e5e1fbc` / 无 `Cache-Control: no-store`**，与线上逐字节相同；
而 import `api/index.py` 时同一路径返回 **200 / `no-store`**。两者差的就是"路由注册有没有被执行"。

更阴的是：**`api.app_instance.app is api.index.app` 为真并不构成反证** —— 平台只 import
入口那一个模块，同不同一个对象不重要，"这个模块被 import 时有没有顺带把路由注册上去"才重要。

现名 `app_instance` 不在候选名单里，`api/` 下与入口有关的候选只剩 `index.py`（正确的那个）；
根目录另有一个 `app.py` 指向同一个 app。于是**无论平台按什么顺序解析，落到线上的都是同一个
带路由的 app** —— 这正是 `scripts/entrypoint-resolution-check.py` 每次都会复算的性质。
"""
from flask import Flask

from api.constants import MAX_FILE_BYTES

app = Flask(__name__)

# Multipart overhead is allowed here; the file itself is checked separately.
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_BYTES + 1024 * 1024
