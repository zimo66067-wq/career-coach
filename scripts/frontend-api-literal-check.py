#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""前端写死的 API 路径必须是一条真实存在的路由（Phase 7a 门禁第 11 步）。

为什么需要它：`docs/architecture.md §3` 长期维护一句手抄的「前端实际消费 15 个端点」+
15 个名字。手抄的清单**只会持续漂移** —— 实测当时那 15 个名字里 `uploadJD` / `submitJD` /
`matchJD` / `majorMatch` / `tasks` 五个早已随对应功能退役，而 `/api/profile`、
`/api/target-jobs`、`/api/actions` 三个新端点又根本没被列进去；`kb.js` 还被写成消费端点的
来源之一（该文件早已删除，且那一行因为**不带 `js/` 前缀**而躲过了所有路径扫描）。

所以 7a 不再更新那个数字，而是把这句话换成可判据的不变量：

    前端字面量  ⊆  vercel 重写源  ⊆  route_api() 处理分支

本脚本判第一段（静态，不起 Flask）；后两段由 `scripts/vercel-dead-routes.py` 判（发真请求探）。

观察面（说清楚，免得下一个人以为它管得比实际宽）：
  * A. `public/js/*.js` 里任何形如 `'/api/...'` 的字符串字面量；
  * B. `public/js/*.js` 里对本地 `api()` 辅助函数的调用 —— 其参数表内所有形如 `'/...'`
       的字面量（`account.js` 用 `api('/auth/me')` 这种相对写法，`/api` 由辅助函数补上）。
       整段参数表都要扫：`api(isRegister ? '/auth/register' : '/auth/login', …)` 里两个
       路径是三元表达式的两个分支，只取"第一个字面量参数"会漏掉一个。
       规则 B 只在**文件里真的定义了 `function api(`** 时启用，避免误伤别的 `api(`。
  * 字面量以 `/` 结尾且后面紧跟 `+` 的，按动态段处理（`'/history/' + id` → `/api/history/:seg`）。

**不在观察面内**：用 `ENDPOINTS.targetJobs + '/' + id` 拼出来的动态段。这类调用没有可静态
校验的字面量 —— 要有意义地判它，得在 VM 里桩掉 `fetch` 真跑一遍，那是集成测试的量级，
不是这一步。本步只对"写死的路径"负责，而写死正是最容易腐烂的那一类。

用法：python scripts/frontend-api-literal-check.py [--root .] [--verbose]
退出码 0 = 通过；1 = 有前端路径没有对应路由 / 判据失效。
"""
from __future__ import print_function

import io
import json
import os
import re
import sys

JS_DIR_REL = os.path.join("public", "js")

API_LITERAL_RE = re.compile(r"""(['"`])(/api/[^'"`\s]*)['"`]""")
API_CALL_RE = re.compile(r"\bapi\s*\(")
REL_LITERAL_RE = re.compile(r"""(['"])(/[^'"\s]*)['"]""")
DEFINES_API_HELPER_RE = re.compile(r"function\s+api\s*\(")


def normalize(path, dynamic=False):
    """把字面量规整成可与 vercel 源比对的形式。返回 None 表示不是 API 路径。"""
    path = re.sub(r"\$\{[^}]*\}", ":seg", path)
    path = re.sub(r"[?#].*$", "", path)
    path = path.rstrip("/")
    if dynamic:
        path += "/:seg"
    if path == "/api":
        return path
    if not path.startswith("/api/"):
        return None
    return path


def is_dynamic(src, end):
    """字面量右引号之后紧跟 `+` 说明还有拼接段。"""
    return bool(re.match(r"\s*\+", src[end:end + 10]))


def balanced_args(src, open_paren):
    """从 '(' 的位置取出配对括号内的原文；配不上就取到结尾（宁可多扫不可漏扫）。"""
    depth = 0
    for i in range(open_paren, len(src)):
        c = src[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return src[open_paren + 1:i]
    return src[open_paren + 1:]


def literals_in(src, name):
    """返回 {规范化后的路径: {来源标记}}。"""
    found = {}

    def add(path, where):
        path = normalize(path, dynamic=where[1])
        if path:
            found.setdefault(path, set()).add(where[0])

    for m in API_LITERAL_RE.finditer(src):
        add(m.group(2), (name, is_dynamic(src, m.end())))

    if DEFINES_API_HELPER_RE.search(src):
        for m in API_CALL_RE.finditer(src):
            args = balanced_args(src, m.end() - 1)
            for lit in REL_LITERAL_RE.finditer(args):
                add("/api" + lit.group(2),
                    (name + "(api())", is_dynamic(args, lit.end())))
    return found


def collect(root):
    d = os.path.join(root, JS_DIR_REL)
    found, files = {}, []
    if not os.path.isdir(d):
        return found, files
    for name in sorted(os.listdir(d)):
        if not name.endswith(".js"):
            continue
        files.append(name)
        src = io.open(os.path.join(d, name), encoding="utf-8", newline="").read()
        for path, where in literals_in(src, name).items():
            found.setdefault(path, set()).update(where)
    return found, files


def sources(root):
    cfg = json.loads(io.open(os.path.join(root, "vercel.json"), encoding="utf-8").read())
    out = []
    for rule in cfg["rewrites"]:
        s = rule["source"]
        if not s.startswith("/api/"):
            continue
        rx = re.escape(s).replace(r"\(\.\*\)", ".*").replace(r":path\*", ".*")
        out.append((s, re.compile("^" + rx + "/?$")))
    return out


def matched_by(path, srcs):
    for s, rx in srcs:
        if rx.match(path):
            return s
    return None


def main():
    root = "."
    argv = sys.argv[1:]
    if "--root" in argv:
        root = argv[argv.index("--root") + 1]
    verbose = "--verbose" in argv

    found, files = collect(root)
    srcs = sources(root)

    # ── 判据自检：探针 + 空判防线 ──
    problems = []
    if not files:
        problems.append("public/js/ 下没找到任何 js，判据空判")
    if len(found) < 8:
        problems.append("前端只解析出 %d 个 /api 路径，判据近乎空判" % len(found))
    if len(srcs) < 20:
        problems.append("vercel 只解析出 %d 条 API 重写源，判据近乎空判" % len(srcs))
    # 探针 1：真实存在的路径必须被判为命中
    if matched_by("/api/wf01/upload", srcs) is None:
        problems.append("探针失效：/api/wf01/upload 没有被任何重写源命中")
    # 探针 2：不存在的路径必须判为未命中
    if matched_by("/api/definitely-not-a-route", srcs) is not None:
        problems.append("探针失效：/api/definitely-not-a-route 竟被命中")
    # 探针 3：参数化源要能覆盖它下面的具体路径
    if matched_by("/api/actions/abc123/start", srcs) is None:
        problems.append("探针失效：/api/actions/<id>/start 没有被参数化源命中")
    # 探针 4：三元表达式里的第二个路径必须被扫到（"只取第一个字面量参数"会漏）
    probe_src = ("function api(p){return p;}\n"
                 "api(isRegister ? '/auth/register' : '/auth/login', { method: 'POST' });")
    probe = literals_in(probe_src, "probe.js")
    if "/api/auth/login" not in probe or "/api/auth/register" not in probe:
        problems.append("探针失效：api() 参数表里的三元分支没被扫到")
    # 探针 5：`/apiary/...` 这种同前缀但不是 API 的串不得被当成路径
    if literals_in("var x = '/apiary/bees';", "probe.js"):
        problems.append("探针失效：/apiary/... 被误判为 API 路径")
    # 探针 6：动态段要按动态段处理（`'/history/' + id`）。
    #         若把它当成无参数的 `/api/history`，参数化源上就永远判不出问题。
    if "/api/history/:seg" not in literals_in(
            "function api(p){return p;}\napi('/history/' + id, {});", "probe.js"):
        problems.append("探针失效：`'/history/' + id` 没有按动态段处理")

    if problems:
        print("FAIL 判据自检未通过：")
        for p in problems:
            print("  " + p)
        return 1

    bad = sorted(p for p in found if matched_by(p, srcs) is None)
    if bad:
        print("FAIL 前端写死了 %d 个没有对应路由的 API 路径：" % len(bad))
        for p in bad:
            print("  %-44s [%s]" % (p, ", ".join(sorted(found[p]))))
        print("  修法：改成 `public/js/data-bridge.js` 的 `ENDPOINTS` 里真实存在的键，"
              "或在 `vercel.json` 补一条 API 重写（并确保 `route_api()` 有处理分支）。")
        return 1

    print("OK %d 个前端 js、%d 个写死的 /api 路径，全部落在 %d 条 vercel API 重写源内"
          % (len(files), len(found), len(srcs)))
    if verbose:
        for p in sorted(found):
            print("   %-46s <- %-40s [%s]"
                  % (p, matched_by(p, srcs), ", ".join(sorted(found[p]))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
