#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生产 API 探针 —— 一次跑出「线上跑的是哪个提交」+「业务接口通不通」。

为什么需要这个脚本（它填的是判据的观察面空洞）：

* `scripts/vercel-dead-routes.py` 只做**静态比对**：把 `vercel.json` 的每条
  重写对着本地路由表核一遍。配置全对、线上函数没起来时，它照样全绿。
* `scripts/p0-05-link-check.py` 只判链接**可达**，不判接口**可用**。
* `scripts/phase4-http-smoke.py` 起的是**本地**端口，不是生产域名。

三者可以同时全绿，而真实用户点进去一个流程都走不通。2026-09-20~21 就是这个状态：
线上静态资源是最新的、CI 全绿，但 `/api/*` 的**每一个**路径都返回同一个
**Werkzeug 默认 404**（207 B、不带应用无条件设置的 `Cache-Control: no-store`）。

真因（2026-09-21 由本地隔离 import 复现定案）：平台的 **Flask 预设按文件名挑入口**
（`app.py` / `index.py` / `server.py` / `main.py` / `wsgi.py` / `asgi.py`），
而仓库里有一个**只建 Flask 对象、不注册路由**的叶子模块名叫 `app.py` ——
平台 import 的就是它，于是任何路径都是默认 404。
修法见 `docs/release-checklist.md`；本地判据是 `scripts/entrypoint-resolution-check.py`。

三个判据（都是"线上 ≠ 本地"才能看见的）：

1. **探测源来自前端字面量**：`public/js/pages-api-config.js` 里写死的那个 Vercel 源
   就是非 Vercel 宿主（GitHub Pages）唯一会去调的地址。**不在这里再抄一份域名** ——
   写死第二份就等于给下一个人埋一个会漂移的事实；前端改了域名，探针自动跟着改。
2. **静态新鲜度**：取最近一次改动 `public/` 的提交里**真的变过**的文件，比线上字节与
   `git cat-file -s HEAD:<path>`（**不是** `wc -c` —— 工作树含 CRLF，会虚高）。
   线上等于 HEAD 才能说"线上是当前版本"，否则连版本都不对，谈接口没意义。
3. **响应是谁产生的**：本应用装好 HTTP 层之后会对**每一个**响应都加
   `Cache-Control: no-store`（`api/http_layer.py` 的 `after_request`）。
   于是**"带不带 no-store"直接区分了"是谁在回答"**：
   · 带上 → 路由已注册、HTTP 层已挂载，是**本应用**在回答；
   · 不带 → 是平台或一个**没注册路由的裸 app** 在回答。
   （这条判据的来历见 `docs/release-checklist.md`：坏的那一刻，线上每个响应都缺它。）
   对照组 `/__probe_definitely_missing__` 用来给"平台/裸 app 的 404 长什么样"定标 ——
   注意应用是 catch-all 时**它也会带 no-store**，那是正常形态，见下。

4. **跨源渠道能不能用**：生产域名既是前端也是 API，从它打开页面是**同源**；
   但仓库里还有一个跨源前端（GitHub Pages）。那个源能不能调到 API，只取决于平台上的
   `DUMATE_ALLOWED_ORIGINS` —— **仓库里看不出来**，只有探线上才知道。
   这一条刻意记为**警告**而不是硬门（同源是主渠道且可用，不让次要渠道淹没主结论），
   但它是**真缺口**，不是"已决定不做"。

判据的严格程度分两档（刻意不同）：

* `/api/health` 是**硬门**：必须 200。它是唯一"不带参数就该成功"的接口。
* 其余业务接口只要求**不是那个静态 404** —— 本应用回 400/401/415/422 都是**通了**
  （缺 body、缺 token 本来就该这样）。把"非 200 即失败"当判据会在 API 修好的那一刻
  变成假阳性，然后下一个人会把整条判据删掉。

用法：

    python scripts/api-prod-probe.py                          # 探前端字面量指向的源
    python scripts/api-prod-probe.py --origin https://x       # 探别处（对比用）
    python scripts/api-prod-probe.py --skip-freshness         # 只探接口

出口码：0 = 全通过；1 = 有阻断；2 = 探不了（没有可用源 / 网络不可用，不作产品结论）。
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

#: 前端写死 Vercel 源的地方。刻意不写死域名本身，只写死"去哪读"。
LITERAL_SOURCES = ("public/js/pages-api-config.js", "public/js/account.js")

_LITERAL_RE = re.compile(r"https://[A-Za-z0-9.-]+\.vercel\.app")

#: GitHub Pages 那个**跨源**前端的地址。同样不写死值，只写死"去哪读"：
#: 它是 `api/constants.py` 里 `PUBLIC_PAGES_ORIGIN` 的字面量，也是 `DUMATE_ALLOWED_ORIGINS`
#: 未设置时 `api/http_layer.py` 用的默认值。
PAGES_ORIGIN_SOURCE = "api/constants.py"
_PAGES_ORIGIN_RE = re.compile(r'PUBLIC_PAGES_ORIGIN\s*=\s*"(https://[^"]+)"')

#: 业务接口探针。第一条是硬门（必须 200）；其余只要求"是应用回的"。
API_PROBES = (
    ("GET", "/api/health", True),
    ("POST", "/api/wf01/consent", False),
    ("POST", "/api/wf03/jd", False),
    ("GET", "/api/profile", False),
    # 一条"任何架构下都该由应用回答"的路径。它 404 是正常的（没有这条路由），
    # 但**必须带 no-store** —— 不带就说明回答者不是本应用。它与硬门的区别：
    # 硬门查"路由通不通"，它查"回答者是谁"。
    ("GET", "/api/handlers/health", False),
)

#: 对照组：这个路径**一定**不存在。用它给"静态 404 长什么样"定标。
CONTROL_PATH = "/__probe_definitely_missing__"

#: 跨源判据的反向控制：`.invalid` 是 RFC 2606 保留 TLD，永远不可能是本站前端。
#: 它必须**拿不到** `Access-Control-Allow-Origin` —— 否则"放行名单"已变成全放行，
#: 第 3 节里那两个 OK 就都是假的。
HOSTILE_ORIGIN = "https://probe-hostile-origin.invalid"

REPO_ROOT = Path(__file__).resolve().parents[1]


def _opener():
    """显式关掉代理：环境里的出口代理对部分域名会返 502，把结论污染成"线上坏了"。"""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _fetch(opener, url, method="GET", timeout=30, extra_headers=None):
    """返回 (状态码, 响应体, 响应头小写 dict)；网络层失败返回 (None, 异常串, {})。"""
    request = urllib.request.Request(url, method=method, headers=extra_headers or {})
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read()
            headers = {k.lower(): v for k, v in response.headers.items()}
            return response.status, body, headers
    except urllib.error.HTTPError as exc:
        body = exc.read()
        headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
        return exc.code, body, headers
    except Exception as exc:  # noqa: BLE001 - 网络层什么都可能抛，统一降级
        return None, "%s: %s" % (type(exc).__name__, exc), {}


def _git(*args):
    """跑一条 git 命令，成功返回 stdout（strip），失败返回 None。"""
    try:
        done = subprocess.run(
            ["git", "-C", str(REPO_ROOT)] + list(args),
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def frontend_literal_origins():
    """扫发布树，返回 (前端写死的 https 源列表, [问题...])。"""
    found = []
    problems = []
    for rel in LITERAL_SOURCES:
        path = REPO_ROOT / rel
        if not path.exists():
            problems.append("%s 不存在" % rel)
            continue
        text = path.read_text(encoding="utf-8")
        hits = sorted({match.group(0) for match in _LITERAL_RE.finditer(text)})
        if not hits:
            problems.append("%s 里找不到 https://*.vercel.app" % rel)
        found.extend(hits)
    return sorted(set(found)), problems


def freshness_probes(limit=3):
    """挑「最近一次改动过 public/ 的提交」里变过的文件当版本探针。

    刻意不写死文件名：这份清单会随仓库演化，写死就等于给下一个人埋一个假陈述。
    也刻意不只看 `HEAD~1`：回填提交（只改文档）不碰 `public/`，那样会直接跳过整个检查
    —— 2026-09-20 实测就踩了这个（`HEAD~1..HEAD` 是空的，探针静默跳过）。
    """
    last = _git("log", "-1", "--format=%H", "--", "public")
    if not last:
        return []
    changed = _git("diff", "--name-only", "%s~1" % last, last, "--", "public")
    if not changed:
        return []
    picks = [line for line in changed.splitlines() if line.endswith(".md")][:limit]
    if not picks:
        picks = [line for line in changed.splitlines()][:limit]
    out = []
    for path in picks:
        size = _git("cat-file", "-s", "HEAD:%s" % path)
        if size:
            # 线上按「输出根」取：public/a/b.md → /a/b.md
            out.append((path, "/" + path[len("public/"):] if path.startswith("public/") else "/" + path,
                        int(size)))
    return out


def check_freshness(opener, origin, probes, failures):
    print("== 1. 静态新鲜度（线上是否 = HEAD）==")
    if not probes:
        print("  跳过：git 里没找到最近一次改 public/ 时变过的文件")
        return
    for path, url_path, blob_size in probes:
        status, body, _ = _fetch(opener, origin + url_path)
        if status is None:
            print("  %-40s 取不到（%s）" % (url_path, body))
            failures.append("新鲜度探针取不到：%s" % url_path)
            continue
        live = len(body)
        mark = "OK " if live == blob_size else "!! "
        print("  %s%-40s 线上=%-7d HEAD=%-7d" % (mark, url_path, live, blob_size))
        if live != blob_size:
            failures.append(
                "线上 %s 与 HEAD 不一致（线上 %d B / HEAD %d B）—— 线上不是当前提交，"
                "先让 Vercel 部署到 HEAD 再谈接口。" % (url_path, live, blob_size))
    print()


def check_api(opener, origin, failures):
    print("== 2. 业务接口 ==")
    control_status, control_body, control_headers = _fetch(opener, origin + CONTROL_PATH)
    if control_status is None:
        print("  网络不可用：%s" % control_body)
        return False
    control_digest = hashlib.md5(control_body).hexdigest()
    control_no_store = "no-store" in control_headers.get("cache-control", "")
    print("  对照（应 404）%-34s code=%s md5=%s no-store=%s"
          % (CONTROL_PATH, control_status, control_digest[:12], control_no_store))
    # 对照组带不带 no-store，决定"谁是回答者"这条判据怎么用 —— 两种都是可能出现的情形，
    # 不把任何一种当成异常：
    #   · 带 → 应用是 catch-all（框架预设的正常形态：任意路径都送进 Flask）。
    #         此时"与对照逐字节相同"只说明"两个都进了应用"，不再能说明"没被路由接住"。
    #   · 不带 → 平台自己回了对照路径。此时"与对照逐字节相同 + 缺 no-store"就是
    #         "这个接口没被应用接住"的实证。
    if control_no_store:
        print("        应用是 catch-all（正常形态）⇒ 逐字节比对不作判据，改用 no-store 判回答者。")
    else:
        print("        平台自己回了对照路径 ⇒ 逐字节比对 + 缺 no-store 可判『没被应用接住』。")
    print()

    unrouted = []
    for method, path, hard_gate in API_PROBES:
        status, body, headers = _fetch(opener, origin + path, method=method)
        if status is None:
            print("  %-4s %-28s 取不到（%s）" % (method, path, body))
            failures.append("%s %s 取不到：%s" % (method, path, body))
            continue
        digest = hashlib.md5(body).hexdigest()
        no_store = "no-store" in headers.get("cache-control", "")
        flags = []
        # 谁在回答：应用只要装载了 HTTP 层，就必然给每个响应加 no-store。
        served_by_app = no_store or status == 200
        if not served_by_app:
            flags.append("响应缺 no-store（回答者不是本应用）")
        # 只有在"平台回了对照路径"这一种情形下，逐字节相同才是有效证据。
        if not control_no_store and digest == control_digest:
            flags.append("与对照 404 逐字节相同（未被路由接住）")
        if hard_gate and status != 200:
            flags.append("硬门未过（要求 200）")
            # 硬门必须**真的**记进 failures。只打个 `!! ` 是不够的 ——
            # 那样 `/api/health` 回 500 时，全部 flags 里没有一条"不算失败"，
            # 行标是 `!! `，但退出码仍是 0：一个"看得见红、判成绿"的洞。
            failures.append("硬门 %s %s 返回 %s（要求 200）" % (method, path, status))
        if not served_by_app:
            unrouted.append(path)
        elif not hard_gate:
            flags.append("已由应用应答（非 200 不算失败）")
        mark = "OK " if not flags or all("不算失败" in f for f in flags) else "!! "
        print("  %s%-4s %-28s code=%-4s md5=%s  %s"
              % (mark, method, path, status, digest[:12], "；".join(flags)))

    print()
    if unrouted:
        failures.append(
            "%d 个路径的回答者不是应用（响应缺 no-store）⇒ 线上被服务的是一个"
            "**没有注册路由、也没挂载 HTTP 层**的 app。本项目实测过这种病：平台的 Flask 预设"
            "**按文件名挑入口**（`app.py`/`index.py`/`server.py`/`main.py`/`wsgi.py`/`asgi.py`），"
            "而仓库里有个只建对象、不注册路由的叶子模块恰好叫 `app.py`。"
            "本地判据 `scripts/entrypoint-resolution-check.py` 逐个候选入口复算这件事，"
            "先跑它；修法见 `docs/release-checklist.md`。" % len(unrouted))
    return True


def pages_origin():
    """返回仓库里声明的那个**跨源**前端地址（GitHub Pages），读不到返回 None。"""
    path = REPO_ROOT / PAGES_ORIGIN_SOURCE
    if not path.exists():
        return None
    match = _PAGES_ORIGIN_RE.search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def check_cross_origin(opener, origin, origin_reported, failures):
    """跨源渠道能不能用 —— 这条与"同一个源"是两件事，必须分开看。

    生产域名既是前端也是 API，所以从它打开页面是**同源**，CORS 不参与。
    但仓库里还有一个跨源前端（GitHub Pages，`public/js/pages-api-config.js` 就是为它写的；
    2026-09-21 实测该前端在线、且真的在调本 API）。从那个源打开页面时：
      · 预检应答若无 `Access-Control-Allow-Origin` ⇒ 浏览器会拦掉**所有**接口调用；
      · `api/http_layer.py:reject_cross_site_writes()` 还会让**写操作回 403**
        （"请求来源未获授权"）。

    **2026-09-21 起它是硬门，不再是警告。** 上一轮它是警告，因为当时的修法落在**平台配置**里
    （要不要支持这条渠道由人决定）；现在第一方源是 `api/http_layer.py:builtin_origins()`
    的并集里的一支，**放行与否由代码保证、与平台变量无关** —— 它和 `/api/health` = 200
    一样是个不变量。它还红，只说明这次修复没上线。

    **三件事都要探，缺一条判据就不可信**：
      1. 第一方源的预检必须拿到 ACAO（且就等于它自己，防"回一个 `*`"）；
      2. 从第一方源发起的写操作**不得**是 403（预检与写路径用同一套判断，两者必须一致）；
      3. **反向控制**：一个保留 TLD 的敌对源（`HOSTILE_ORIGIN`）**必须没有** ACAO。
         没有第 3 条，把并集写成"无条件放行"也是绿的 —— 那是最危险的一种绿。
    """
    print("== 3. 跨源渠道（GitHub Pages 前端能不能调到 API）==")
    if not origin_reported:
        print("  跳过：读不到 %s 里的 PUBLIC_PAGES_ORIGIN" % PAGES_ORIGIN_SOURCE)
        print()
        return

    def preflight(probe_origin):
        return _fetch(
            opener, origin + "/api/wf01/consent", method="OPTIONS",
            extra_headers={
                "Origin": probe_origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            })

    status, _, headers = preflight(origin_reported)
    if status is None:
        print("  取不到（%s）" % headers)
        failures.append("跨源预检取不到：%s" % headers)
        print()
        return
    allow = headers.get("access-control-allow-origin", "")
    print("  预检 OPTIONS /api/wf01/consent  Origin=%-38s code=%s  ACAO=%s"
          % (origin_reported, status, allow or "(无)"))
    if allow.rstrip("/") == origin_reported.rstrip("/"):
        print("  OK 第一方源被放行 —— `builtin_origins()` 保证它不受平台变量影响。")
    else:
        print("  !! 第一方源**未**被放行 —— 从 GitHub Pages 打开时浏览器会拦掉所有接口调用，")
        print("     写操作还会被应用以 403「请求来源未获授权」直接拒掉。")
        print("     2026-09-21 之前的成因是平台变量整体替换了默认值；`api/http_layer.py` 已改成")
        print("     并集，所以现在还红只剩一种解释：**这次修复没上线**（或 ACAO 回的不是它本身）。")
        failures.append(
            "第一方源 %s 未被放行（预检 ACAO=%s）—— 跨源渠道不可用；"
            "并集语义见 api/http_layer.py，修法见 docs/release-checklist.md"
            % (origin_reported, allow or "无"))

    # 写路径：预检说放行、写操作却回 403，就是"两套判断不一致"，比单纯拒绝更难发现。
    write_status, _, _ = _fetch(
        opener, origin + "/api/wf03/jd", method="POST",
        extra_headers={"Origin": origin_reported})
    print("  写操作 POST /api/wf03/jd       Origin=%s  code=%s"
          % (origin_reported, write_status))
    if write_status is None:
        failures.append("跨源写操作取不到（网络层失败）")
    elif write_status == 403:
        print("  !! 写操作被 403 拒掉 —— 与上面预检的结论不一致（同一个 `origin_allowed()`）。")
        failures.append("第一方源 %s 的写操作返回 403" % origin_reported)
    else:
        print("  OK 写操作没被 CSRF 拦掉（%s 属「缺 body / 缺同意令牌」那一类正常应答）。"
              % write_status)

    # 反向控制。没有它，上面两个 OK 分不清"名单判得对"与"名单是空的/全放行"。
    hostile_status, _, hostile_headers = preflight(HOSTILE_ORIGIN)
    hostile_allow = hostile_headers.get("access-control-allow-origin", "")
    print("  反向控制 OPTIONS 同一路径        Origin=%-38s code=%s  ACAO=%s"
          % (HOSTILE_ORIGIN, hostile_status, hostile_allow or "(无)"))
    if hostile_allow:
        print("  !! 敌对源也拿到了 ACAO ⇒ 放行名单变成了「全放行」（并集被写成了无条件 true）。")
        failures.append(
            "反向控制失败：敌对源 %s 也拿到了 ACAO —— 说明放行判断已失效，"
            "上面两个 OK 不可信" % HOSTILE_ORIGIN)
    else:
        print("  OK 敌对源仍被拒 ⇒ 上面的 OK 判的是「哪些源被放行」，不是「全都放行」。")
    print()


def main():
    parser = argparse.ArgumentParser(description="生产 API 探针")
    parser.add_argument("--origin", default=None, help="要探测的源；默认取前端字面量")
    parser.add_argument("--skip-freshness", action="store_true", help="只探接口，不探版本")
    args = parser.parse_args()

    literal, literal_problems = frontend_literal_origins()
    for problem in literal_problems:
        print("提示：%s" % problem)

    if args.origin:
        origin = args.origin.rstrip("/")
        source = "--origin 指定"
        if literal and origin not in literal:
            print("提示：%s 不在前端字面量 %s 里 —— 你探的不是前端真的会去调的地址。"
                  % (origin, "、".join(literal)))
    elif literal:
        origin = literal[0]
        source = "前端字面量（%s）" % "、".join(LITERAL_SOURCES)
    else:
        print("探不了：前端字面量里没有可用的 https 源，也没有给 --origin。")
        return 2

    head = _git("rev-parse", "--short", "HEAD") or "?"
    print("目标源：%s" % origin)
    print("来源：%s" % source)
    print("本地 HEAD：%s" % head)
    print()

    opener = _opener()
    failures = []

    if not args.skip_freshness:
        check_freshness(opener, origin, freshness_probes(), failures)

    reachable = check_api(opener, origin, failures)
    if not reachable:
        print("网络不可用，本次不给出产品结论。")
        return 2

    pages = pages_origin()
    check_cross_origin(opener, origin, pages, failures)

    print("== 结论 ==")
    if failures:
        for item in failures:
            print("  阻断：%s" % item)
        return 1
    print("  线上静态 = HEAD；业务接口都已被应用接住（/api/health = 200）；")
    print("  第一方跨源前端 %s 已放行，且敌对源 %s 仍被拒。" % (pages, HOSTILE_ORIGIN))
    return 0


if __name__ == "__main__":
    sys.exit(main())
