#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生产 API 探针 —— 一次跑出「线上跑的是哪个提交」+「业务接口通不通」。

为什么需要这个脚本（它填的是判据的观察面空洞）：

* `scripts/vercel-dead-routes.py` 只做**静态比对**：把 `vercel.json` 的每条
  重写对着本地路由表核一遍。配置全对、线上函数没起来时，它照样全绿。
* `scripts/p0-05-link-check.py` 只判链接**可达**，不判接口**可用**。
* `scripts/phase4-http-smoke.py` 起的是**本地**端口，不是生产域名。

三者可以同时全绿，而真实用户点进去一个流程都走不通。2026-09-20 就是这个状态：
线上静态资源是最新的、CI 全绿，但 `/api/*` 的**每一个**路径都返回同一个 404。

两个判据（都是"线上 ≠ 本地"才能看见的）：

1. **静态新鲜度**：取 HEAD 相对上一提交**真的变过**的静态文件，比线上字节与
   `git cat-file -s HEAD:<path>`（**不是** `wc -c` —— 工作树含 CRLF，会虚高）。
   线上等于 HEAD 才能说"线上是当前版本"，否则连版本都不对，谈接口没意义。
2. **同一性 + 响应来源**：业务接口的 404 与"绝对不存在的路径"的 404
   **逐字节相同** ⇒ 这些接口没有被任何路由接住。
   再叠一层：应用自己会给响应加 `Cache-Control: no-store`（`api/http_layer.py`），
   响应里没有这个头 ⇒ 这个 404 **不是本应用产生的**。

用法：

    python scripts/api-prod-probe.py                      # 探默认生产域名
    python scripts/api-prod-probe.py --origin https://x   # 探别处（修完复跑用）
    python scripts/api-prod-probe.py --skip-freshness     # 只探接口

出口码：0 = 全通过；1 = 有阻断；2 = 网络不可用（不作产品结论）。
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_ORIGIN = "https://career-coach-omega-three.vercel.app"

#: 业务接口探针。第一条是硬门：`/api/health` 都必须 200。
API_PROBES = (
    ("GET", "/api/health"),
    ("POST", "/api/wf01/consent"),
    ("POST", "/api/wf03/jd"),
    ("GET", "/api/profile"),
)

#: 对照组：这个路径**一定**不存在。用它给"404 长什么样"定标。
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
        print("  跳过：git 里没找到 HEAD~1..HEAD 变过的 public/ 文件")
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
    print("  对照（应 404）%-34s code=%s md5=%s" % (CONTROL_PATH, control_status, control_digest[:12]))
    print()

    same_as_control = []
    for method, path in API_PROBES:
        status, body, headers = _fetch(opener, origin + path, method=method)
        if status is None:
            print("  %-4s %-30s 取不到（%s）" % (method, path, body))
            failures.append("%s %s 取不到：%s" % (method, path, body))
            continue
        digest = hashlib.md5(body).hexdigest()
        no_store = "no-store" in headers.get("cache-control", "")
        flags = []
        if digest == control_digest:
            flags.append("与对照 404 逐字节相同")
            same_as_control.append(path)
        if not no_store:
            # 应用自己会设 no-store；没有它 => 这个响应不是本应用产生的
            flags.append("响应缺 no-store（非本应用产生）")
        if status != 200:
            flags.append("非 200")
        mark = "OK " if not flags else "!! "
        print("  %s%-4s %-30s code=%-4s md5=%s  %s"
              % (mark, method, path, status, digest[:12], "；".join(flags)))

    print()
    if same_as_control:
        failures.append(
            "%d 个业务接口返回的 404 与不存在的路径**逐字节相同** → 这些接口没有被任何路由接住，"
            "线上 Python 侧没有在服务这套 app（去 Vercel 看该次部署的 Functions 列表与构建日志）。"
            % len(same_as_control))
    health_status, _, _ = _fetch(opener, origin + "/api/health")
    if health_status != 200:
        failures.append("/api/health 未返回 200（当前 %s）—— 这是硬门。" % health_status)
    return True


def main():
    parser = argparse.ArgumentParser(description="生产 API 探针")
    parser.add_argument("--origin", default=DEFAULT_ORIGIN, help="要探测的源，默认生产域名")
    parser.add_argument("--skip-freshness", action="store_true", help="只探接口，不探版本")
    args = parser.parse_args()
    origin = args.origin.rstrip("/")

    head = _git("rev-parse", "--short", "HEAD") or "?"
    print("目标源：%s" % origin)
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
    print("  线上静态 = HEAD，业务接口全部 200。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
