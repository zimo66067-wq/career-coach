#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""活文档里的页面路径必须真实存在（Phase 6b-2 门禁第 10 步）。

为什么需要这条：6b-2 把页面文件改成"用户语言"名字（f1-resume.html → resume-evidence.html
等）。测试里的路径扫描只覆盖**发布树**且**排除 .md**，于是活文档里指向旧路径的行不会被任何
判据抓到 —— 但真人是照着这些文档找文件的。漂移就是这么产生的：代码改完、测试全绿，文档
还在指路到一个不存在的文件。本脚本就是这次实际漏掉的那一步。

判据：活文档里每个 `pages/<name>.html` 引用要么
  (a) 指向真实存在的文件，要么
  (b) 明确待在历史语境里 —— **同一行**或**本节标题**里能看到"已删除 / 已下线 / 已修 /
      审计 / Phase 6a / 完成记录"这类措辞。
其余一律失败。这条门槛是刻意收窄的：早期版本用了"上下 ±10 行"的窗口，结果 §2 现况表格
里任何一行都能被 8 行之外的注记给"开脱" —— 下次再改名就抓不到了。

范围只含"活文档"（描述现在是什么样）。历史报告（docs/phase*-report.md、CHANGELOG.md、
docs/iteration-*.md、handoffs/、deliverables/）记录的是当时是什么样，不改写，也不在这里查。

用法：python scripts/live-doc-path-check.py [--root .] [--verbose]
退出码 0 = 通过；1 = 有漂移 / 判据失效。
"""
from __future__ import print_function

import io
import os
import re
import sys

LIVING_DOCS = [
    "docs/architecture.md",
    "docs/dependency-map.md",
    "docs/product-scope.md",
    "docs/README.md",
    "public/README.md",
]

# 历史语境措辞。只认"同一行"或"本节标题"，不做邻近行放宽（见文件头说明）。
MARKERS = [
    "已删除", "已下线", "勿再引用", "已过时", "已经不存在", "下线", "退役",
    "已修", "审计", "完成记录", "影响面", "当时", "原来", "改造前",
    "Phase 1", "Phase 6a", "Phase 6b",
]

PATH_RE = re.compile(r"(?:public/)?pages/([A-Za-z0-9._-]+\.html)")
HEADING_RE = re.compile(r"^#{1,6} ")


def read(root, rel):
    with io.open(os.path.join(root, rel), "r", encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n")


def declared(root):
    d = os.path.join(root, "public", "pages")
    if not os.path.isdir(d):
        return set()
    return set(n for n in os.listdir(d) if n.endswith(".html"))


def section_heading(lines, idx):
    for j in range(idx, -1, -1):
        if HEADING_RE.match(lines[j]):
            return lines[j]
    return ""


def hits(text):
    return [m for m in MARKERS if m in text]


def classify(lines, idx, have):
    """返回 (basename, verdict, detail)；verdict ∈ exists / excused / offender。"""
    line = lines[idx]
    m = PATH_RE.search(line)
    base = m.group(1)
    if base in have:
        return base, "exists", ""
    mk = hits(line)
    if mk:
        return base, "excused", "行内：" + "/".join(mk)
    mk = hits(section_heading(lines, idx))
    if mk:
        return base, "excused", "节标题：" + "/".join(mk)
    return base, "offender", ""


def audit(root):
    """返回 (refs_total, existing, excused, offenders)。"""
    have = declared(root)
    total, existing, excused, offenders = 0, 0, [], []
    for rel in LIVING_DOCS:
        if not os.path.exists(os.path.join(root, rel)):
            continue
        lines = read(root, rel).split("\n")
        for i in range(len(lines)):
            if not PATH_RE.search(lines[i]):
                continue
            total += 1
            base, verdict, detail = classify(lines, i, have)
            if verdict == "exists":
                existing += 1
            elif verdict == "excused":
                excused.append((rel, i + 1, base, detail))
            else:
                offenders.append((rel, i + 1, base))
    return total, existing, excused, offenders, have


def main():
    root = "."
    argv = sys.argv[1:]
    if "--root" in argv:
        root = argv[argv.index("--root") + 1]
    verbose = "--verbose" in argv

    total, existing, excused, offenders, have = audit(root)

    # ── 判据自检：空集与探针 ──
    problems = []
    if total < 4:
        problems.append("活文档里只找到 %d 处页面引用，判据近乎空判" % total)
    if len(have) < 4:
        problems.append("public/pages/ 只找到 %d 个 html，判据近乎空判" % len(have))
    # 探针 1：干净段落里一个不存在的路径必须被判为 offender
    probe = ["## 2. 用户页面", "", "| `public/pages/definitely-not-a-page.html` | 1 | x | ✅ |"]
    if classify(probe, 2, have)[1] != "offender":
        problems.append("探针失效：干净段落里的死链没有被判为 offender")
    # 探针 2：带历史标记的同一行必须被判为 excused
    probe2 = ["| `public/pages/gone.html` | 1 | ~~旧页~~ | **已删除** |"]
    if classify(probe2, 0, have)[1] != "excused":
        problems.append("探针失效：带『已删除』的行没有被判为 excused")

    if problems:
        print("FAIL 判据自检未通过：")
        for p in problems:
            print("  " + p)
        return 1

    if offenders:
        print("FAIL 活文档指向不存在的页面，且没有任何历史语境标记（%d 处）：" % len(offenders))
        for rel, ln, base in offenders:
            print("  %s:%d -> pages/%s" % (rel, ln, base))
        print("  修法：改成本阶段的真实路径；确实是历史记录就补上『已删除/已修/Phase 6a』之类的措辞。")
        return 1

    print("OK %d 份活文档、%d 处页面引用：%d 处路径存在、%d 处处于历史语境；"
          "现存 %d 个页面" % (len(LIVING_DOCS), total, existing, len(excused), len(have)))
    if verbose:
        for rel, ln, base, detail in excused:
            print("   hist %s:%d -> pages/%s（%s）" % (rel, ln, base, detail))
    print("   现存页面：%s" % ", ".join(sorted(have)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
