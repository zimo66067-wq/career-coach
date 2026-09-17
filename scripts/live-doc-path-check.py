#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""活文档里的页面与脚本路径必须真实存在（Phase 6b-2b 建，Phase 7a 扩面）。

为什么需要这条：6b-2 把页面文件改成"用户语言"名字（f1-resume.html → resume-evidence.html
等）。测试里的路径扫描只覆盖**发布树**且**排除 .md**，于是活文档里指向旧路径的行不会被任何
判据抓到 —— 但真人是照着这些文档找文件的。漂移就是这么产生的：代码改完、测试全绿，文档
还在指路到一个不存在的文件。本脚本就是那次实际漏掉的那一步。

观察面（Phase 7a 扩面后）：
  * `pages/<name>.html` —— 页面，存在性对照 `public/pages/`
  * `js/<name>.js`      —— 脚本（带目录前缀），存在性对照 `public/js/`
  * `` `name.js` ``     —— 脚本（**反引号内的裸名**，不带任何目录前缀）

第三条是 7a 补的洞：6b-3 记录过 `docs/architecture.md` 里一句
「`ENDPOINTS` 映射 + `account.js` + `kb.js`」—— `kb.js` 早已随知识库页删除，
但它写的不是 `js/kb.js` 而是裸名，于是**任何一种带目录前缀的扫描都看不见它**。
判据的观察面必须覆盖作者真实会写的写法，否则"扩面"只是换了个地方漏。

判据：活文档里每个引用要么
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

# 同义措辞容忍。人写的是"已**整条**删除 / 已**整块**删除 / 已**全部**删除"，
# 而子串匹配只认"已删除" —— 语义相同、字符串不同，于是一条**完全正确的**历史注记
# 被判成漂移，下一个人就会去删注记而不是留注记。
#
# 这是 6b-3 那条教训的镜像：6b-3 是"判据的观察面比语义**宽**"（把注释当实现），
# 这里是"比语义**窄**"（等价的正确写法不认）。两次都指向同一件事 ——
# 判据的观察面必须与它要判的那个语义重合，宽和窄同样会失效。
#
# 刻意不放进来的词：
#   * "快照" —— 6b-2b 实测过：把 §2 标题写成"（快照：8 个 HTML）"会让整节落进豁免区，
#     从此那一节里的真漂移再也抓不到。快照是**范围说明**，不是**历史结论**。
#   * 裸"删除"（无"已"）—— "删除 A + B" 是待办/动作条目，不是"已经删掉了"。
MARKER_RE = re.compile(
    # 「已」与动词之间常插一个状语：「已**于 2026-09-13** 整条删除」「已**于 Phase 1** 全部删除」。
    # 允许夹一段不含标点的状语（标点即止，避免跨句吞掉半个段落）。
    r"已(?:于[^，。；、（）()]{0,18})?(?:整条|整块|全部|整体)?(?:删除|删掉|移除|退役|下线|废弃|作废)"
)

PAGE_RE = re.compile(r"(?:public/)?pages/([A-Za-z0-9._-]+\.html)")
JS_DIR_RE = re.compile(r"(?:public/|docs/|\.\./)?js/([A-Za-z0-9._-]+\.js)")
# 裸脚本名：整个反引号内容就是一个不含目录分隔符的 *.js。
# 锚在反引号上是刻意的 —— 活文档里提到脚本名一律加反引号，这样既不误伤散文，
# 也不会把 `tests/test_job_upload.js`（含 /）当成裸名。`.json` 不会被吞成 `.js`：
# 正则结尾需要词边界，而 `.json` 里 `s` 后面紧跟的 `o` 仍是词字符。
JS_BARE_RE = re.compile(r"`([A-Za-z0-9._-]+\.js)`")

HEADING_RE = re.compile(r"^#{1,6} ")

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".workbuddy"}


def read(root, rel):
    with io.open(os.path.join(root, rel), "r", encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n")


def declared(root):
    """返回 {"page": {公开的 html 名}, "js": {仓库里所有 js 名}}。

    js 取全仓基名而不是只看 public/js：活文档里也会指 `echarts.min.js`（在
    `public/assets/vendor/`）或 `test_publish_mirror.js`（在 `tests/`）。判据要问的是
    "这个名字还存不存在"，不是"它属不属于某个特定目录"—— 后者会制造一批假阳性，
    而假阳性会让下一个人把这条判据删掉。
    """
    pages = set()
    d = os.path.join(root, "public", "pages")
    if os.path.isdir(d):
        pages = set(n for n in os.listdir(d) if n.endswith(".html"))

    js = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS and not x.startswith(".venv")]
        for n in filenames:
            if n.endswith(".js"):
                js.add(n)
    return {"page": pages, "js": js}


def section_heading(lines, idx):
    for j in range(idx, -1, -1):
        if HEADING_RE.match(lines[j]):
            return lines[j]
    return ""


def hits(text):
    """返回该行里命中的历史语境措辞（字面词表 + 同义措辞正则）。"""
    out = [m for m in MARKERS if m in text]
    for m in MARKER_RE.finditer(text):
        if m.group(0) not in out:
            out.append(m.group(0))
    return out


def refs_in(line):
    """返回该行上的 (kind, basename) 去重列表；kind ∈ page / js。"""
    out = []
    for m in PAGE_RE.finditer(line):
        out.append(("page", m.group(1)))
    for m in JS_DIR_RE.finditer(line):
        out.append(("js", m.group(1)))
    for m in JS_BARE_RE.finditer(line):
        item = ("js", m.group(1))
        if item not in out:
            out.append(item)
    return out


def classify(lines, idx, have, kind=None, base=None):
    """返回 (kind, basename, verdict, detail)；verdict ∈ exists / excused / offender。

    不传 kind/base 时按该行第一个引用判定（自检探针用）。
    """
    line = lines[idx]
    if kind is None:
        found = refs_in(line)
        if not found:
            return None, None, "none", ""
        kind, base = found[0]
    if base in have[kind]:
        return kind, base, "exists", ""
    mk = hits(line)
    if mk:
        return kind, base, "excused", "行内：" + "/".join(mk)
    mk = hits(section_heading(lines, idx))
    if mk:
        return kind, base, "excused", "节标题：" + "/".join(mk)
    return kind, base, "offender", ""


def audit(root):
    """返回 (total, counts, excused, offenders, have)。"""
    have = declared(root)
    counts = {"page": {"exists": 0}, "js": {"exists": 0}}
    total, excused, offenders = 0, [], []
    for rel in LIVING_DOCS:
        if not os.path.exists(os.path.join(root, rel)):
            continue
        lines = read(root, rel).split("\n")
        for i in range(len(lines)):
            for kind, base in refs_in(lines[i]):
                total += 1
                kind, base, verdict, detail = classify(lines, i, have, kind, base)
                if verdict == "exists":
                    counts[kind]["exists"] += 1
                elif verdict == "excused":
                    excused.append((rel, i + 1, kind, base, detail))
                else:
                    offenders.append((rel, i + 1, kind, base))
    return total, counts, excused, offenders, have


def main():
    root = "."
    argv = sys.argv[1:]
    if "--root" in argv:
        root = argv[argv.index("--root") + 1]
    verbose = "--verbose" in argv

    total, counts, excused, offenders, have = audit(root)

    # ── 判据自检：空集与探针 ──
    problems = []
    if total < 10:
        problems.append("活文档里只找到 %d 处路径引用，判据近乎空判" % total)
    if len(have["page"]) < 4:
        problems.append("public/pages/ 只找到 %d 个 html，判据近乎空判" % len(have["page"]))
    if len(have["js"]) < 10:
        problems.append("全仓只找到 %d 个 js，判据近乎空判" % len(have["js"]))
    # 探针 1：干净段落里一个不存在的页面路径必须被判为 offender
    probe = ["## 2. 用户页面", "", "| `public/pages/definitely-not-a-page.html` | 1 | x | ✅ |"]
    if classify(probe, 2, have)[2] != "offender":
        problems.append("探针失效：干净段落里的页面死链没有被判为 offender")
    # 探针 2：带历史标记的同一行必须被判为 excused
    probe2 = ["| `public/pages/gone.html` | 1 | ~~旧页~~ | **已删除** |"]
    if classify(probe2, 0, have)[2] != "excused":
        problems.append("探针失效：带『已删除』的行没有被判为 excused")
    # 探针 3：带目录前缀的脚本死链必须被判为 offender
    probe3 = ["## 3. 前端", "", "→ 来源是 `public/js/definitely-not-a-script.js`"]
    if classify(probe3, 2, have)[2] != "offender":
        problems.append("探针失效：js/ 前缀的脚本死链没有被判为 offender")
    # 探针 4：**裸脚本名**死链必须被判为 offender（7a 扩的就是这一类）
    probe4 = ["## 3. 前端", "", "→ 来源是 `ENDPOINTS` 映射 + `definitely-not-a-script.js`"]
    if classify(probe4, 2, have)[2] != "offender":
        problems.append("探针失效：裸脚本名死链没有被判为 offender")
    # 探针 5：反引号里的 *.json 不得被当成 *.js（7a 扩面时真实踩过的坑）
    if refs_in("见 `package.json`、`vercel.json`、`blind-test-summary.json`"):
        problems.append("探针失效：*.json 被误判为 *.js（词边界没生效）")
    # 探针 6：同义措辞必须被认下 —— "已整条删除" 与 "已删除" 语义相同，字符串不同
    probe6 = ["## 9. 处置", "", "- `public/js/gone.js` 已整条删除（Phase 1）"]
    if classify(probe6, 2, have)[2] != "excused":
        problems.append("探针失效：『已整条删除』没有被认作历史语境（判据太窄）")
    # 探针 7：裸"删除"（没有"已"）是动作条目，**不得**豁免 —— 这是探针 6 的反面，
    #         两条一起把同义措辞容忍的边界钉住：认"已删掉"，不认"要去删"。
    probe7 = ["## 9. 处置", "", "- 删除 `public/js/definitely-not-a-script.js`"]
    if classify(probe7, 2, have)[2] != "offender":
        problems.append("探针失效：裸『删除』被误当作历史语境（判据太宽）")
    # 探针 8：动词前夹状语（「已于 … 整条删除」）同样要认 —— 这是活文档里最常见的写法
    probe8 = ["## 9. 处置", "", "- `public/js/gone.js` 已于 2026-09-13 整条删除"]
    if classify(probe8, 2, have)[2] != "excused":
        problems.append("探针失效：『已于 <日期> 整条删除』没有被认作历史语境")

    if problems:
        print("FAIL 判据自检未通过：")
        for p in problems:
            print("  " + p)
        return 1

    if offenders:
        print("FAIL 活文档指向不存在的文件，且没有任何历史语境标记（%d 处）：" % len(offenders))
        for rel, ln, kind, base in offenders:
            print("  %s:%d -> %s/%s" % (rel, ln, "pages" if kind == "page" else "js", base))
        print("  修法：改成本阶段的真实路径；确实是历史记录就补上『已删除/已修/Phase 6a』之类的措辞。")
        return 1

    print("OK %d 份活文档、%d 处路径引用：%d 处存在（页面 %d / 脚本 %d）、%d 处处于历史语境；"
          "现存 %d 个页面、%d 个脚本"
          % (len(LIVING_DOCS), total,
             counts["page"]["exists"] + counts["js"]["exists"],
             counts["page"]["exists"], counts["js"]["exists"],
             len(excused), len(have["page"]), len(have["js"])))
    if verbose:
        for rel, ln, kind, base, detail in excused:
            print("   hist %s:%d -> %s/%s（%s）"
                  % (rel, ln, "pages" if kind == "page" else "js", base, detail))
    print("   现存页面：%s" % ", ".join(sorted(have["page"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
