#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""`.env.example` 与代码实际读取的 env 必须双向一致（Phase 7a 门禁第 12 步）。

为什么需要它：Phase 7a 打开这个文件时发现三类毛病 ——

  1. 有一行**未注释**的 `====` 分隔符（会被当成一行非法内容）；
  2. 一整块重复的表头与变量（`DUMATE_CONSENT_SECRET` / `_MAX_AGE_SECONDS` 各 3 次，
     `ZHIPU_API_KEY` / `ZHIPU_BASE_URL` 各 2 次），另有 `LOG_LEVEL` / `ENV`
     两个**全仓 0 消费者**的变量；
  3. **漏掉了 13 个代码里真的在读取的变量** —— 包括服务端游客会话的签名材料
     `DUMATE_GUEST_SECRET`。部署时漏配它不会被任何测试发现（代码里有回退），
     但"哪些密钥必须配"这件事就没人说得清了。

第 3 类是真正危险的那一类：**模板短了，不会红**。所以这里把它变成判据。

判据：
  1. 每行只能是空行 / `#` 注释 / `NAME=VALUE`；
  2. 每个变量名恰好出现一次；
  3. 模板里的每个变量都必须在代码里被读到（否则是废弃变量）；
  4. 代码里读到的每个变量都必须在模板里（例外见 NOT_DOCUMENTED，且**每条都要写理由**）；
  5. **反引号里的每个路径都必须存在**（2026-09-21 新增，见下）。

观察面：`api/`、`services/`、`domain/`、`repositories/`、`providers/`、`scripts/` 下的
`.py` / `.js`，只认 `os.environ.get("X")` / `os.environ["X"]` / `getenv("X")` 这三种读法。
`tests/` 不在观察面内 —— 测试用 `monkeypatch.setenv` 造变量是测试夹具，不是部署清单。

## 第 5 条为什么长在这里（2026-09-21）

第 1~4 条只判**变量名**。于是"用途"那几行里写的路径**没人看** —— 而它恰好是一个空洞：
第 10 步的活文档判据观察面是 **md 文件**（逐条登记在 `contracts/living-docs.json`），
`.env.example` 不是 md，两边都没它的份。实测结果：它攒了 **10 处**指向本轮之前那一层
工具的路径（Phase 7d 已把那一层整层并入 `domain/` + `providers/`），外加 2 处把常量指到了
`api/index.py`（7c 拆分后它在 `api/constants.py`，游客令牌签发在 `api/security.py`）。
一个模板把读者指到已经不存在的文件上，就是一份会误导部署的文档。

（措辞刻意不写成路径形态：`tests/test_phase7d_contract.py` 会把**字符串常量**里
路径形态的旧层名全部扫出来，这里说的是"那一层"，不是在引用它 —— 与它同一份白名单里
另外几条"出处说明"是同一种情况，所以也不去给白名单加行。）

**已知边界（这是决定，不是遗漏）**：这里只判"路径存在"，不判散文断言的正确性 ——
"未设置时用 `api/constants.py` 里的 `DEFAULT_GUEST_MAX_AGE_SECONDS`"里，
"那个常量在那个文件里"是判不了的（要判它得读自然语言）。机械可判的那一半先关掉，
剩下的一半只能靠人读；**不假装有判据**。

用法：python scripts/env-example-check.py [--root .] [--verbose]
退出码 0 = 通过；1 = 有漂移 / 判据失效。
"""
from __future__ import print_function

import io
import os
import re
import sys

ENV_FILE = ".env.example"
CODE_DIRS = ["api", "services", "domain", "repositories", "providers", "scripts"]
CODE_EXT = (".py", ".js")
SKIP_PREFIX = (".venv", "node_modules", "__pycache__")
# 本脚本自身要排除：它的自检探针与文档字符串里必然写出 `os.environ.get("A_ONE")` 这类
# **样例字符串**，把观察面打在它自己身上会制造自指误报（第一版实测报了 4 条 "代码在读 A_ONE"）。
SKIP_FILES = ("scripts/env-example-check.py",)

ASSIGN_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
READ_RE = re.compile(r"""(?:environ(?:\.get)?\(|getenv\(|environ\[)\s*['"]([A-Z][A-Z0-9_]*)['"]""")
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
#: 反引号里的**路径**（第 5 条）。扩展名白名单刻意收窄：`` `DEFAULT_GUEST_MAX_AGE_SECONDS` ``
#: 这种常量名、`` `====` `` 这种分隔符都不是路径，不该被卷进来；
#: `` `providers/model.py::build_model_router` `` 这种带成员的写法只取到 `.py` 为止。
PATH_RE = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:py|js|json|md|sh|yml|yaml))`")

# 代码里读、但**有意不进模板**的变量。白名单必须逐条写理由 —— 这是判据，
# 不是"先放行再说"：下面有探针检查这些键真的还在被读取，避免名单腐烂成一张护身符。
NOT_DOCUMENTED = {
    "GITHUB_TOKEN":
        "scripts/push-via-api*.py 的一次性推提交脚本专用；"
        "dependency-map §4.6 已判定该批脚本被「Git Credential Manager + git push」取代",
    "P0_MODEL":
        "scripts/p0-03-real-model-test.py 的一次性模型复测脚本专用",
    "QIANFAN_ACCESS_KEY":
        "同上（p0-03 脚本沿用的旧版千帆 AK 命名）",
    "QIANFAN_SECRET_KEY":
        "同上（p0-03 脚本沿用的旧版千帆 SK 命名）",
}


def parse_env(path):
    """返回 (names, problems)；names 是 [(name, lineno)]。"""
    names, problems = [], []
    for i, raw in enumerate(io.open(path, encoding="utf-8", newline="").read()
                              .replace("\r\n", "\n").split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = ASSIGN_RE.match(line)
        if not m:
            problems.append("%s:%d 既不是注释也不是 NAME=VALUE：%r"
                            % (ENV_FILE, i, raw[:60]))
            continue
        names.append((m.group(1), i))
    return names, problems


def code_reads(root):
    """返回 {name: {相对路径}}。"""
    found = {}
    for d in CODE_DIRS:
        base = os.path.join(root, d)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if not x.startswith(SKIP_PREFIX)]
            for fn in filenames:
                if not fn.endswith(CODE_EXT):
                    continue
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, root).replace("\\", "/")
                if rel in SKIP_FILES:
                    continue
                src = io.open(p, encoding="utf-8", errors="replace").read()
                for m in READ_RE.finditer(src):
                    found.setdefault(m.group(1), set()).add(rel)
    return found


def path_refs(env_path):
    """返回 [(行号, 路径)] —— 模板里反引号包住的全部路径引用（第 5 条的观察面）。"""
    refs = []
    for i, raw in enumerate(io.open(env_path, encoding="utf-8", newline="").read()
                              .replace("\r\n", "\n").split("\n"), 1):
        for match in PATH_RE.finditer(raw):
            refs.append((i, match.group(1)))
    return refs


def path_ref_problems(env_path, root):
    """第 5 条：反引号里的路径必须存在。理由与已知边界见模块文档。"""
    problems, refs = [], path_refs(env_path)
    for lineno, rel in refs:
        if not os.path.exists(os.path.join(root, rel.replace("/", os.sep))):
            problems.append("%s:%d 反引号里的路径不存在：%s" % (ENV_FILE, lineno, rel))
    return problems, refs


def check(root, verbose=False):
    """返回 (problems, declared_unique, used, path_refs)。外部可用来做探针。"""
    env_path = os.path.join(root, ENV_FILE)
    problems = []
    if not os.path.exists(env_path):
        return ["找不到 %s" % ENV_FILE], set(), {}, []

    names, parse_problems = parse_env(env_path)
    problems.extend(parse_problems)

    seen = {}
    for name, lineno in names:
        seen.setdefault(name, []).append(lineno)
    dups = sorted(n for n, ls in seen.items() if len(ls) > 1)
    for n in dups:
        problems.append("变量 %s 出现了 %d 次（行 %s）"
                        % (n, len(seen[n]), ", ".join(str(x) for x in seen[n])))

    declared = set(seen)
    used = code_reads(root)

    for n in sorted(declared - set(used)):
        problems.append("模板里的 %s 在代码里没有任何消费者（废弃变量，应删）" % n)

    for n in sorted(set(used) - declared):
        if n not in NOT_DOCUMENTED:
            problems.append("代码在读 %s，但模板里没有它（%s）"
                            % (n, ", ".join(sorted(used[n]))))

    ref_problems, refs = path_ref_problems(env_path, root)
    problems.extend(ref_problems)

    if verbose:
        for n in sorted(declared & set(used)):
            print("   %-34s %s" % (n, ", ".join(sorted(used[n]))))
        for lineno, rel in refs:
            print("   第 %-4d 行引用 %s" % (lineno, rel))
    return problems, declared, used, refs


def main():
    root = "."
    argv = sys.argv[1:]
    if "--root" in argv:
        root = argv[argv.index("--root") + 1]
    verbose = "--verbose" in argv

    problems, declared, used, refs = check(root, verbose)

    # ── 判据自检：空判防线 + 探针 ──
    self_check = []
    if len(declared) < 15:
        self_check.append("模板只解析出 %d 个变量，判据近乎空判" % len(declared))
    if len(used) < 20:
        self_check.append("代码只解析出 %d 个读取点，判据近乎空判" % len(used))
    # 第 5 条也有空判形态：模板里一个反引号路径都没有 ⇒ 那条判据什么都没看。
    if len(refs) < 5:
        self_check.append("模板里只解析出 %d 个路径引用，第 5 条近乎空判" % len(refs))
    # 探针 1：白名单里的每个键必须**真的还在被读取**，否则名单腐烂成了护身符
    for n in sorted(NOT_DOCUMENTED):
        if n not in used:
            self_check.append("白名单里的 %s 已经没有任何读取点了，应把它从 NOT_DOCUMENTED 删掉" % n)
        elif not NOT_DOCUMENTED[n].strip():
            self_check.append("白名单里的 %s 没有写理由" % n)
    # 探针 2：`NAME=value` 的解析要稳 —— 带空格、带引号、空值都要认出来
    for sample in ("ZHIPU_API_KEY=", "DUMATE_MODEL=glm-4.7-flash", "X_A=\"a b\""):
        if not ASSIGN_RE.match(sample):
            self_check.append("探针失效：%r 没被认成 NAME=VALUE" % sample)
    # 探针 3：非 NAME=VALUE 的行必须被拒（旧版那行未注释的 `====` 就是这一类）
    for sample in ("====", "# comment", "  ZHIPU_API_KEY =x", "1BAD=x"):
        if ASSIGN_RE.match(sample):
            self_check.append("探针失效：%r 被误认成 NAME=VALUE" % sample)
    # 探针 4：读取点的三种写法都要认
    probe_src = ('os.environ.get("A_ONE")\nos.environ["A_TWO"]\ngetenv("A_THREE")')
    hit = set(READ_RE.findall(probe_src))
    if hit != {"A_ONE", "A_TWO", "A_THREE"}:
        self_check.append("探针失效：env 读取点只认出了 %s" % sorted(hit))
    # 探针 5：第 5 条必须**两头都判得出来** —— 负向（不存在的路径）要被抓，
    # 正向（现存路径）要放行。只测一头的话，恒绿和恒红都看不出来。
    for sample, should_exist in (("`definitely/missing/path.py`", False),
                                 ("`api/index.py`", True)):
        match = PATH_RE.search(sample)
        if not match:
            self_check.append("探针失效：反引号里的路径没被认出来 —— %s" % sample)
            continue
        found = os.path.exists(os.path.join(root, match.group(1).replace("/", os.sep)))
        if found != should_exist:
            self_check.append("探针失效：%s 的存在性判成了 %s（应为 %s）"
                              % (match.group(1), found, should_exist))
    # 探针 6：非路径的反引号内容**不该**被卷进来（常量名、分隔符都是模板里的常客）
    for sample in ("`DEFAULT_GUEST_MAX_AGE_SECONDS`", "`====`", "`os.environ.get`"):
        if PATH_RE.search(sample):
            self_check.append("探针失效：%r 被误认成路径引用" % sample)

    if self_check:
        print("FAIL 判据自检未通过：")
        for p in self_check:
            print("  " + p)
        return 1

    if problems:
        print("FAIL %s 与代码的实际 env 读取 / 路径引用不一致（%d 处）：" % (ENV_FILE, len(problems)))
        for p in problems:
            print("  " + p)
        print("  修法：模板里的废弃变量删掉；代码在读但模板没有的补进模板"
              "（确实不该进模板的一次性脚本变量，加到本脚本的 NOT_DOCUMENTED 并写明理由）；"
              "反引号里的路径改成它现在真正所在的位置。")
        return 1

    print("OK %s：%d 个变量（无重复）、每行合法、与代码读取点双向一致、"
          "%d 个反引号路径引用全部存在"
          "（代码共读 %d 个变量，其中 %d 个按理由豁免）"
          % (ENV_FILE, len(declared), len(refs), len(used), len(NOT_DOCUMENTED)))
    if verbose:
        print("   豁免：%s" % ", ".join(sorted(NOT_DOCUMENTED)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
