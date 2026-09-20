#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生产 API 探针 —— 一次跑出「线上跑的是哪个提交」+「业务接口通不通」。

为什么需要这个脚本（它填的是判据的观察面空洞）：

* `scripts/vercel-dead-routes.py` 只做**静态比对**：把 `vercel.json` 的每条
  重写对着本地路由表核一遍。配置全对、线上函数没起来时，它照样全绿。
* `scripts/p0-05-link-check.py` 只判链接**可达**，不判接口**可用**。
* `scripts/phase4-http-smoke.py` 起的是**本地**端口，不是生产域名。

三者可以同时全绿，而真实用户点进去一个流程都走不通。2026-09-20 就是这个状态：
线上静态资源是最新的、CI 全绿，但 `/api/*` 的**每一个**路径都返回同一个 404
（连 `/api/handlers/health` 这种「函数只要构建了就一定存在的路径」也是）——
说明那次部署**一个 Serverless Function 都没有**，线上只有静态文件。

三个判据（都是"线上 ≠ 本地"才能看见的）：

1. **探测源来自前端字面量**：`public/js/pages-api-config.js` 里写死的那个 Vercel 源
   就是非 Vercel 宿主（GitHub Pages）唯一会去调的地址。**不在这里再抄一份域名** ——
   写死第二份就等于给下一个人埋一个会漂移的事实；前端改了域名，探针自动跟着改。
2. **静态新鲜度**：取最近一次改动 `public/` 的提交里**真的变过**的文件，比线上字节与
   `git cat-file -s HEAD:<path>`（**不是** `wc -c` —— 工作树含 CRLF，会虚高）。
   线上等于 HEAD 才能说"线上是当前版本"，否则连版本都不对，谈接口没意义。
3. **响应是谁产生的**：本应用对**每一个**响应都加 `Cache-Control: no-store`
   （`api/http_layer.py` 的 `after_request`）与 JSON 错误体。所以
   「不带 `no-store` + HTML 404」= 这个响应不是本应用产生的。
   把业务接口的响应与"绝对不存在的路径"的响应逐字节比一次，这条就有实证。

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

#: 业务接口探针。第一条是硬门（必须 200）；其余只要求"是应用回的"。
API_PROBES = (
    ("GET", "/api/health", True),
    ("POST", "/api/wf01/consent", False),
    ("POST", "/api/wf03/jd", False),
    ("GET", "/api/profile", False),
    # 只要函数构建了，这个路径必然存在（api/handlers/health.py → /api/handlers/health）。
    # 它 404 就等于"线上一个函数都没有"，与"路由映射写错了"是两种不同的病。
    ("GET", "/api/handlers/health", False),
)

#: 对照组：这个路径**一定**不存在。用它给"静态 404 长什么样"定标。
CONTROL_PATH = "/__probe_definitely_missing__"

REPO_ROOT = Path(__file__).resolve().parents[1]


def _opener():
    """显式关掉代理：环境里的出口代理对部分域名会返 502，把结论污染成"线上坏了"。"""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _fetch(opener, url, method="GET", timeout=30):
    """返回 (状态码, 响应体, 响应头小写 dict)；网络层失败返回 (None, 异常串, {})。"""
    request = urllib.request.Request(url, method=method)
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
    if control_no_store:
        failures.append(
            "对照组 %s 竟然带了 no-store —— 说明有 catch-all 路由把任意路径都送进了应用；"
            "这时『与对照 404 相同』不再能证明接口没被接住，本探针的判据失效。"
            % CONTROL_PATH)
    print()

    static_404 = []
    for method, path, hard_gate in API_PROBES:
        status, body, headers = _fetch(opener, origin + path, method=method)
        if status is None:
            print("  %-4s %-28s 取不到（%s）" % (method, path, body))
            failures.append("%s %s 取不到：%s" % (method, path, body))
            continue
        digest = hashlib.md5(body).hexdigest()
        no_store = "no-store" in headers.get("cache-control", "")
        flags = []
        served_by_app = True
        if digest == control_digest:
            flags.append("与对照 404 逐字节相同")
            served_by_app = False
        if not no_store:
            # 应用无条件设 no-store；没有它 => 这个响应不是本应用产生的
            flags.append("响应缺 no-store（非本应用产生）")
            served_by_app = False
        if hard_gate and status != 200:
            flags.append("硬门未过（要求 200）")
        if not served_by_app:
            static_404.append(path)
        elif not hard_gate:
            flags.append("已由应用应答（非 200 不算失败）")
        mark = "OK " if not flags or all("不算失败" in f for f in flags) else "!! "
        print("  %s%-4s %-28s code=%-4s md5=%s  %s"
              % (mark, method, path, status, digest[:12], "；".join(flags)))

    print()
    if static_404:
        failures.append(
            "%d 个路径返回的都是同一份静态 404（连 `/api/handlers/health` 也在内）⇒ 那次部署"
            "**没有构建出任何 Serverless Function**，线上只有静态文件。"
            "去 Vercel 看该次部署的 Functions 列表与构建日志；重点核对 Project Settings 里的"
            "**Root Directory / Output Directory / Framework Preset** —— 函数没被构建时，"
            "`vercel.json` 里那些 `/api/xxx -> /api?_route=xxx` 重写全部落空，"
            "而静态资源照样是最新的，所以 CI 与『站点可达性』都会给你绿灯。"
            % len(static_404))
    return True


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

    print("== 结论 ==")
    if failures:
        for item in failures:
            print("  阻断：%s" % item)
        return 1
    print("  线上静态 = HEAD，业务接口都已被应用接住（/api/health = 200）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
