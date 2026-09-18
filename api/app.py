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
"""
from flask import Flask

from api.constants import MAX_FILE_BYTES

app = Flask(__name__)

# Multipart overhead is allowed here; the file itself is checked separately.
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_BYTES + 1024 * 1024
