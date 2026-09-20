#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""活文档里的页面与脚本路径必须真实存在（Phase 6b-2b 建，Phase 7a 扩面，Phase 7d 扩第三种形态）。

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

第四条（`path`，Phase 7d 补的洞）：`<层>/…/<文件>.py|md|json` —— 仓库内路径。
7d 归并 `tools/` 时，`contracts/README.md` 与 `contracts/scoring.md` 里那两处失效引用
**没有任何判据在看着**，是人工扫出来的（见 `docs/phase7d-report.md` §7）。前三条正则
只认 `pages/*.html` 与反引号里的 `*.js`，`tools/validate_schema.py` 这类写法根本抽不出来。

`path` 类多了两条收窄规则，都是 7d 实测逼出来的：

  收窄 1（第一段必须是**仓库顶层的目录名**，外加一个**已消失的层**清单）。
    不加这条时，一次实测报了 68 处，其中 `work/verify7d-moves.py`（在仓库外，门禁脚本
    住的那层）与 `/blind-test-results/blind-test-report.md`（**部署站点的 URL 路径**，
    仓库里根本没有这个目录）都是假阳性。假阳性会让下一个人把整条判据删掉。
    但"仓库顶层"如果只按 `os.listdir` 算，`tools/` 恰好会被排除 —— 而"指向已消失的层"
    正是最该抓的形态。所以 `GONE_LAYERS` 显式列出来（每项必须写理由）。

  收窄 2（`基线` / `旧路径` 两种措辞进词表）。
    这三份审计文档（`docs/architecture.md` / `dependency-map.md` / `product-scope.md`）
    的正文是**某个 commit 上的现状快照**，头部有逐阶段的更新账本。它们正文里的
    `tools/redflag.py` 是"当时那个文件的引述"，不是"现在去打开这个文件" ——
    §11.3 那张覆盖率基线表里 `tools/redflag.py 19%` 是 2026-09-13 的实测值，
    把路径改写成 `domain/redflag.py` 等于**伪造测量结果**。
    所以这类章节的标题必须自己声明是基线（`（Phase 0 基线）` / `（… 实测）`），
    判据才放行；而 §1 技术栈、§6 Provider 这类**现况断言**没有这层声明，走的是"改对"。

判据：活文档里每个引用要么
  (a) 指向真实存在的文件，要么
  (b) 明确待在历史语境里 —— **同一行**或**祖先章节标题**里能看到"已删除 / 已下线 / 已修 /
      审计 / 完成记录 / 基线 / 旧路径"这类措辞。
其余一律失败。这条门槛是刻意收窄的：早期版本用了"上下 ±10 行"的窗口，结果 §2 现况表格
里任何一行都能被 8 行之外的注记给"开脱" —— 下次再改名就抓不到了。

节点标题的遗传范围（Phase 7d 明确）：章节标题沿**父子链**生效（`## X` 上的标记管到
`### X.1`），但**不含 H1** —— H1 是文档标题，不是章节。把标题里的字当章节判据，
会把整份文档一次性豁免：`docs/architecture.md` 的 H1 里就有"审计"两个字，
7d 实测正是它让整份文件的检查形同虚设。

范围只含"活文档"（描述现在是什么样）。历史报告（docs/phase*-report.md、CHANGELOG.md、
docs/iteration-*.md、handoffs/、deliverables/）记录的是当时是什么样，不改写，也不在这里查。

观察面**不再写死在本文件里**（Phase 8 改）：改读 `contracts/living-docs.json`。
理由是 7d 暴露的老问题 —— 观察面写死 = 一份隐式清单，谁都不知道"今天到底看着几份、
漏了哪几份"。7d 实测：本文件只看着 8 份，而仓里 85 份 md 含路径引用、其中 409 处是死链，
**没有任何判据在看着它们**。把清单变成可判对象之后，加一份活文档就必须改一处显式的地方。

配套三条**双向**自检（只判"清单里的都通过了"是不够的 —— 那只证明清单没写错，
不证明清单没漏）：

  自检 A：清单里列的每个 `living` 路径必须真实存在。—— 清单本身也会过期（文档改名/
          删除后没人改清单），过期清单会让整条判据看着很宽、实际什么都没看。
  自检 B：**含路径引用的 md 必须全部被登记**（在 `living` 里，或命中某条 `historical`）。
          这条是 Phase 8 补的核心洞：新写一份带路径引用的文档而不登记，以前是"静默不查"，
          现在是"红"。含 0 处引用的 md 无需登记（判据本来也不看它）。
  自检 C：`historical` 的每条 glob 至少要命中 1 个文件。—— 否则那条规则是**废话**：
          它一条都不豁免，读者却以为"这类文件已经处理过了"。

另有一条**反向**自检（Phase 8 加的，最容易踩）：
  若一个路径同时命中 `living` 与 `historical`，**以 `living` 为准**。
  实例：`deliverables/README.md` 是交付包的现状索引（活文档），而 `deliverables/**`
  整体是冻结证据。不加这条优先级，前者会被后者静默豁免。

用法：python scripts/live-doc-path-check.py [--root .] [--verbose]
退出码 0 = 通过；1 = 有漂移 / 判据失效。
"""
from __future__ import print_function

import fnmatch
import hashlib
import io
import json
import os
import re
import sys

MANIFEST = "contracts/living-docs.json"

#: 由 `load_manifest()` 填充。**不再写死在本文件里** —— 见文件头「观察面不再写死」。
LIVING_DOCS = []
#: [(glob, why)] 历史记录族。命中的文件不查；`living` 优先于它。
HISTORICAL = []
#: [(a, b, why)] 逐字节镜像对。同名 ≠ 镜像，所以必须逐对显式登记（见清单里的 why_note）。
MIRRORS = []

# 历史语境措辞。只认"同一行"或"祖先章节标题"，不做邻近行放宽（见文件头说明）。
#
# 「基线」（Phase 7d 加的）：审计文档用「（Phase 0 基线）」「（2026-09-13 实测）」声明某节
# 是**冻结的记录**，这类节里的路径是引述，改写成新路径等于篡改记录。
# 与「快照」的区别就在这：快照说的是**范围**（这一节里有 8 个 HTML），
# 基线说的是**时间点**（这一节的数字是 2026-09-13 量的）。所以只收「基线」。
#
# 「旧路径」（Phase 7d 加的）：更新账本里逐条引用旧名字时，作者显式标注的那两个字。
# 收它的理由和 `MARKER_RE` 收「已整条删除」一样 —— 语义已经写在纸面上了，
# 判据不该因为字面不同而否掉一条**完全正确**的注记。
MARKERS = [
    "已删除", "已下线", "勿再引用", "已过时", "已经不存在", "下线", "退役",
    "已修", "审计", "完成记录", "影响面", "当时", "原来", "改造前",
    "Phase 1", "Phase 6a", "Phase 6b",
    "基线", "旧路径",
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
    # 「已」与动词之间常插一个状语：「已**于 2026-09-13** 整条删除」「已**于 Phase 1** 全部删除」
    # 「已**随 #5 一并**删除」（7d 实测：product-scope.md §2 第 15 行的写法，语义与
    # 「已删除」完全相同）。状语**必须**以「于/随/由/经/被」这类介词开头 —— 这一条是
    # 7d 加的，否则"已记录：删除 A"（待办）也会被认成历史结论。
    # 状语内不含标点（含全角冒号）：冒号/顿号即止，避免跨句吞掉半个段落。
    r"已(?:[于随由经被][^，。；、：（）()]{0,18})?(?:整条|整块|全部|整体)?(?:删除|删掉|移除|退役|下线|废弃|作废)"
)

PAGE_RE = re.compile(r"(?:public/)?pages/([A-Za-z0-9._-]+\.html)")
JS_DIR_RE = re.compile(r"(?:public/|docs/|\.\./)?js/([A-Za-z0-9._-]+\.js)")
# 裸脚本名：整个反引号内容就是一个不含目录分隔符的 *.js。
# 锚在反引号上是刻意的 —— 活文档里提到脚本名一律加反引号，这样既不误伤散文，
# 也不会把 `tests/test_job_upload.js`（含 /）当成裸名。`.json` 不会被吞成 `.js`：
# 正则结尾需要词边界，而 `.json` 里 `s` 后面紧跟的 `o` 仍是词字符。
JS_BARE_RE = re.compile(r"`([A-Za-z0-9._-]+\.js)`")

#: 仓库内**带目录**的路径（`<层>/…/<文件>`）—— Phase 7d 新增。
#: 为什么必须要它：`PAGE_RE` / `JS_DIR_RE` 的抽取面只认 `pages/*.html` 与 `js/*.js`，
#: 于是活文档里 `tools/validate_schema.py` 这类路径**根本抽不出来**。
#: 7d 归并 `tools/` 时，`contracts/README.md` 与 `contracts/scoring.md` 里那两处失效引用
#: 就是**没有任何判据在看着**的情况下被人工扫出来的（见 docs/phase7d-report.md §7）。
#: 观察面比语义窄，就会"绿着漏"。
PY_PATH_RE = re.compile(
    r"\b([a-z][a-z0-9_]*(?:/[a-z][a-z0-9_]*)*)"
    r"/[A-Za-z0-9_./-]*[A-Za-z0-9_-]\.(?:py|md|json)\b")

#: 已经**消失的层**名 → 理由。这些名字不再出现在 `os.listdir(root)` 里，但判据必须
#: 继续认它们，否则"指向已消失的层"这个最该抓的形态会连同假阳性一起被排除。
#: （假阳性是本条正则上线当天实测的：`work/verify7d-moves.py` 在**仓库外**，
#:   `/blind-test-results/blind-test-report.md` 是**部署站点的 URL 路径**。）
GONE_LAYERS = {
    "tools": "Phase 7d 整层归并掉 —— 指向它的引用就是漂移，必须继续判",
}

#: 由 `declared()` 填充：仓库**顶层目录**名 ∪ `GONE_LAYERS`。
#: `path` 类引用的第一段必须落在里面。见文件头「收窄 1」。
LAYER_ROOTS = set()

#: 打印用的 kind 名。**不要写成 `"pages" if kind == "page" else "js"`** ——
#: 加第三个 kind（`path`）时那个二元表达式会把 `path` 的死链印成 `js/…`，
#: 于是"哪一类引用失效"这个信息在日志里直接丢掉（7d 实测踩到）。
KIND_LABEL = {"page": "pages", "js": "js", "path": "path"}

HEADING_RE = re.compile(r"^(#{1,6}) (.+)$")

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".workbuddy"}


def read(root, rel):
    with io.open(os.path.join(root, rel), "r", encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n")


def all_md(root):
    """全仓 `.md` 相对路径（跳过 SKIP_DIRS 与虚拟环境目录）。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [x for x in dirnames
                       if x not in SKIP_DIRS and not x.startswith(".venv")]
        for n in filenames:
            if n.endswith(".md"):
                out.append(os.path.relpath(os.path.join(dirpath, n), root)
                           .replace(os.sep, "/"))
    return sorted(out)


def ref_count(root, rel):
    """该文件里有多少处路径引用（`refs_in` 的口径）。0 处的 md 无需登记。"""
    return sum(len(refs_in(line)) for line in read(root, rel).split("\n"))


def is_historical(rel, historical=None):
    """`rel` 是否命中某条历史记录族。

    `fnmatch` 的 `*` 会跨 `/`（与 glob 不同），所以 `deliverables/**` 能匹配深层文件 ——
    这正是这里要的语义："整个交付树都是冻结记录"。命中即返回那条 glob（便于打印）。
    """
    for glob, _why in (HISTORICAL if historical is None else historical):
        if fnmatch.fnmatch(rel, glob):
            return glob
    return None


def load_manifest(root):
    """读 `contracts/living-docs.json`，填充 LIVING_DOCS / HISTORICAL / MIRRORS。

    返回问题列表（空 = 好）。清单缺失/损坏**不降级**：宁可红，也不要"悄悄退回写死的 8 份"
    —— 那正是 7d 那种"看着很宽其实只看了 8 份"的状态。
    """
    global LIVING_DOCS, HISTORICAL, MIRRORS
    LIVING_DOCS, HISTORICAL, MIRRORS = [], [], []
    path = os.path.join(root, MANIFEST)
    if not os.path.exists(path):
        return ["观察面清单缺失：`%s` 不存在，判据无观察面" % MANIFEST]
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as exc:
        return ["观察面清单不是合法 JSON：`%s`（%s）" % (MANIFEST, exc)]

    problems = []
    for item in data.get("living") or []:
        p = (item or {}).get("path")
        if not p:
            problems.append("清单里有 living 条目缺 `path`")
            continue
        if not (item or {}).get("why"):
            problems.append("living 条目缺 `why`：`%s`（每项必须写理由）" % p)
        LIVING_DOCS.append(p)
    for item in data.get("historical") or []:
        g = (item or {}).get("glob")
        if not g:
            problems.append("清单里有 historical 条目缺 `glob`")
            continue
        if not (item or {}).get("why"):
            problems.append("historical 条目缺 `why`：`%s`（每项必须写理由）" % g)
        HISTORICAL.append((g, (item or {}).get("why", "")))
    for item in data.get("mirrors") or []:
        if not item or not item.get("a") or not item.get("b"):
            continue          # `why_note` 这类说明性条目，不是镜像对
        MIRRORS.append((item["a"], item["b"], item.get("why", "")))
    return problems


def sha(path):
    h = hashlib.sha256()
    with io.open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def declared(root):
    """返回 {"page":…, "js":…, "path":…, "layer":…}。

    js 取全仓基名而不是只看 public/js：活文档里也会指 `echarts.min.js`（在
    `public/assets/vendor/`）或 `test_publish_mirror.js`（在 `tests/`）。判据要问的是
    "这个名字还存不存在"，不是"它属不属于某个特定目录"—— 后者会制造一批假阳性，
    而假阳性会让下一个人把这条判据删掉。

    path 取**相对路径**（`domain/validate_schema.py`）而不是基名 —— 因为这一类的失效
    恰恰是"文件还在，但不在那个目录里了"。layer 是 path 类引用的合法首段集合。
    """
    global LAYER_ROOTS
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

    # 带目录的仓库内路径：这里比的是**相对路径**（`domain/validate_schema.py`），
    # 不是基名 —— 因为这一类的失效恰恰是"文件还在，但不在那个目录里了"。
    repo_paths = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS and not x.startswith(".venv")]
        for n in filenames:
            if n.endswith((".py", ".md", ".json")):
                repo_paths.add(os.path.relpath(os.path.join(dirpath, n), root)
                               .replace(os.sep, "/"))

    # 顶层目录（实测，不是写死的名单）+ 已消失的层（写死，但每项带理由）。
    LAYER_ROOTS = set(GONE_LAYERS)
    for n in os.listdir(root):
        if os.path.isdir(os.path.join(root, n)) and n not in SKIP_DIRS \
                and not n.startswith(".venv"):
            LAYER_ROOTS.add(n)
    return {"page": pages, "js": js, "path": repo_paths, "layer": LAYER_ROOTS}


def section_headings(lines, idx):
    """返回 idx 之上、该行的**祖先章节标题**链（由近及远；不含 H1）。

    为什么不是"最近的一行标题"：审计文档的惯例是 `## 3. 依赖违规清单（Phase 0 基线）`
    声明整节，明细写在 `### 3.1`。只认最近一行，父标题上的声明就永远看不见 ——
    于是要么漏判（父标题声明了却不生效），要么逼作者在 5 个子标题上抄 5 遍同一句话。

    为什么排除 H1：H1 是**文档标题**，不是章节。`docs/architecture.md` 的 H1 里写着
    "（Phase 0 只读审计）" —— 一旦让 H1 参与，整份文档会被"审计"两个字一次性豁免，
    观察面看着很宽、实际判据已经失效。7d 实测就是这个结果。
    """
    out, level_seen = [], 7
    for j in range(idx, -1, -1):
        m = HEADING_RE.match(lines[j])
        if not m:
            continue
        level = len(m.group(1))
        if level == 1:
            break
        if level < level_seen:
            out.append(lines[j])
            level_seen = level
    return out


def hits(text):
    """返回该行里命中的历史语境措辞（字面词表 + 同义措辞正则）。"""
    out = [m for m in MARKERS if m in text]
    for m in MARKER_RE.finditer(text):
        if m.group(0) not in out:
            out.append(m.group(0))
    return out


def refs_in(line):
    """返回该行上的 (kind, basename) 去重列表；kind ∈ page / js / path。"""
    out = []
    for m in PAGE_RE.finditer(line):
        out.append(("page", m.group(1)))
    for m in JS_DIR_RE.finditer(line):
        out.append(("js", m.group(1)))
    for m in JS_BARE_RE.finditer(line):
        item = ("js", m.group(1))
        if item not in out:
            out.append(item)
    for m in PY_PATH_RE.finditer(line):
        # 收窄 1：第一段必须是顶层目录名或已消失的层。否则 `work/…`（仓库外）、
        # `/blind-test-results/…`（部署 URL）这类会被当成仓库内路径 —— 7d 实测 68 处里
        # 有 7 处是这么来的，全是假阳性。
        if m.group(1).split("/", 1)[0] not in LAYER_ROOTS:
            continue
        item = ("path", m.group(0))
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
    for h in section_headings(lines, idx):
        mk = hits(h)
        if mk:
            return kind, base, "excused", "节标题：" + "/".join(mk)
    return kind, base, "offender", ""


def audit(root):
    """返回 (total, counts, excused, offenders, have, missing, unregistered)。

    刻意返回 `missing` / `unregistered` 而不是自己跳过 —— 早期版本用 `continue` 跳过不存在的
    清单条目，结果"清单过期"与"文档干净"在输出上长得一模一样（Phase 8 修）。
    """
    have = declared(root)
    counts = {"page": {"exists": 0}, "js": {"exists": 0}, "path": {"exists": 0}}
    total, excused, offenders = 0, [], []
    missing = []
    for rel in LIVING_DOCS:
        if not os.path.exists(os.path.join(root, rel)):
            missing.append(rel)
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
    # 自检 B：含路径引用的 md 必须全部被登记（living 或命中 historical）。
    unregistered = []
    living_set = set(LIVING_DOCS)
    for rel in all_md(root):
        if rel in living_set or is_historical(rel) is not None:
            continue
        n = ref_count(root, rel)
        if n:
            unregistered.append((rel, n))
    return total, counts, excused, offenders, have, missing, unregistered


def main():
    root = "."
    argv = sys.argv[1:]
    if "--root" in argv:
        root = argv[argv.index("--root") + 1]
    verbose = "--verbose" in argv

    problems = list(load_manifest(root))
    total, counts, excused, offenders, have, missing, unregistered = audit(root)

    # ── 判据自检：空集与探针 ──
    if len(LIVING_DOCS) < 20:
        problems.append("观察面只有 %d 份活文档，判据近乎空判（清单是不是被删空了？）"
                        % len(LIVING_DOCS))
    if total < 10:
        problems.append("活文档里只找到 %d 处路径引用，判据近乎空判" % total)
    if len(have["page"]) < 4:
        problems.append("public/pages/ 只找到 %d 个 html，判据近乎空判" % len(have["page"]))
    if len(have["js"]) < 10:
        problems.append("全仓只找到 %d 个 js，判据近乎空判" % len(have["js"]))
    if len(have["path"]) < 50:
        problems.append("全仓只找到 %d 个 .py/.md/.json，判据近乎空判" % len(have["path"]))
    if len(have["layer"]) < 8:
        problems.append("只认到 %d 个顶层目录，path 类的首段过滤近乎空判" % len(have["layer"]))

    # ── 自检 A：清单里列的 must 存在（清单本身也会过期）──
    for rel in missing:
        problems.append("观察面清单过期：`%s` 在 living 里但文件不存在"
                        "（改名/删除后没人改清单，这条判据就在看空气）" % rel)
    # ── 自检 B：含路径引用的 md 必须全部被登记 ──
    for rel, n in unregistered:
        problems.append("未登记的活文档：`%s`（含 %d 处路径引用，却既不在 living 里、"
                        "也不命中任何 historical 族）—— 要么登记它，要么给 historical 补一条规则"
                        % (rel, n))
    # ── 自检 C：historical 的每条 glob 至少要命中 1 个文件（否则是废话规则）──
    allrel = all_md(root)
    for glob, _why in HISTORICAL:
        if not any(fnmatch.fnmatch(rel, glob) for rel in allrel):
            problems.append("historical 规则是废话：`%s` 一个文件都没命中"
                            "（它一条都不豁免，读者却以为这类文件已经处理过了）" % glob)
    # ── 反向自检：同名 ≠ 镜像；登记了的镜像对必须逐字节一致 ──
    for a, b, _why in MIRRORS:
        if not os.path.exists(os.path.join(root, a)):
            problems.append("镜像对的左侧不存在：`%s`" % a)
            continue
        if not os.path.exists(os.path.join(root, b)):
            problems.append("镜像对的右侧不存在：`%s`" % b)
            continue
        if sha(os.path.join(root, a)) != sha(os.path.join(root, b)):
            problems.append("镜像漂移：`%s` 与 `%s` 内容不一致（改了一边没改另一边）"
                            % (a, b))
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
    # 探针 9：状语也可以是「随/由/经/被」—— product-scope.md §2 里写的是
    #         "已随 #5 一并删除"，语义与"已删除"完全相同（7d 实测被误判）。
    probe9 = ["## 9. 处置", "", "- `public/js/gone.js` 已随 #5 一并删除"]
    if classify(probe9, 2, have)[2] != "excused":
        problems.append("探针失效：『已随 … 一并删除』没有被认作历史语境")
    # 探针 10：`path` 类 —— **指向已消失的层**必须仍被判为 offender。
    #          这是扩面的核心：`tools/` 不在 `os.listdir` 里了，若只按顶层目录过滤，
    #          最该抓的形态会连同假阳性一起被放过。
    probe10 = ["## 7. 数据库", "", "`tools/database.py` 1579 行同时承担：连接、DDL、CRUD。"]
    if classify(probe10, 2, have)[2] != "offender":
        problems.append("探针失效：指向已消失的层（tools/）的引用没有被判为 offender")
    # 探针 11：仓库**外**的路径不得被抽出来（`work/` 是门禁脚本住的那层，不在仓库里）
    bad11 = "- 脚本 `work/verify7d-moves.py` 证明只有引用变了"
    if [k for k, _ in refs_in(bad11) if k == "path"]:
        problems.append("探针失效：仓库外的路径（work/…）被当成仓库内路径")
    # 探针 12：**部署 URL 路径**不得被抽出来（`blind-test-results/` 只存在于站点上）
    bad12 = "- 实测 16 份 md 对公网可读（15 顶层 + `blind-test-results/blind-test-report.md`）"
    if [k for k, _ in refs_in(bad12) if k == "path"]:
        problems.append("探针失效：部署 URL 路径被当成仓库内路径")
    # 探针 13：章节标题沿**父子链**生效 —— 父标题上的「基线」要管到子标题底下
    probe13 = ["## 3. 依赖违规清单（Phase 0 基线）", "", "### 3.1 倒置", "",
               "| 位置 | `api/f2_major.py:14` |"]
    if classify(probe13, 4, have)[2] != "excused":
        problems.append("探针失效：父标题的『基线』没有遗传到子标题（章节链没生效）")
    # 探针 14：但**兄弟节点不得互相豁免** —— 同级的另一节没有被声明
    probe14 = ["### 3.1 倒置（Phase 0 基线）", "", "| `api/f2_major.py:14` |", "",
               "### 3.2 明细", "", "| `api/f2_major.py:14` |"]
    if classify(probe14, 6, have)[2] != "offender":
        problems.append("探针失效：兄弟节点的『基线』越界豁免了另一节")
    # 探针 15：H1 是文档标题，**不得**参与豁免 —— architecture.md 的 H1 里就有「审计」，
    #          一旦让 H1 生效，整份文件会被一次豁免（7d 实测）。
    probe15 = ["# 只读审计报告", "", "## 1. 现状", "", "- `public/js/definitely-not-a-script.js`"]
    if classify(probe15, 4, have)[2] != "offender":
        problems.append("探针失效：H1 标题里的词把整份文档豁免了（H1 不该参与）")
    # 探针 16：「快照」**不得**豁免 —— 6b-2b 实测过：把 §2 标题写成"（快照：8 个 HTML）"
    #          会让整节落进豁免区。快照是范围说明，不是历史结论。
    probe16 = ["## 2. 用户页面（快照：8 个 HTML）", "",
               "| `public/pages/definitely-not-a-page.html` | 1 |"]
    if classify(probe16, 2, have)[2] != "offender":
        problems.append("探针失效：『快照』被当成了历史语境（6b-2b 那条教训回退了）")

    # 探针 17：`historical` 族必须真的能豁免**深层**文件，且不得顺手吞掉活文档。
    #          （`fnmatch` 的 `*` 跨 `/`，所以 `deliverables/**` 能匹配深层路径 —— 这是要的语义；
    #           但同一个特性也意味着写太宽的 glob 会把活文档一起豁免，所以两面都要钉住。）
    if not is_historical("deliverables/p0-03-evidence/RUN_EVIDENCE_REPORT.md"):
        problems.append("探针失效：`deliverables/**` 没有豁免深层文件（glob 语义不对）")
    if is_historical("docs/capability_matrix.md"):
        problems.append("探针失效：一份活文档被某条 historical 规则吞掉了")
    # 探针 18：**living 优先于 historical**。`deliverables/README.md` 是交付包的现状索引（活文档），
    #          同时又落在 `deliverables/**` 里。少了这条优先级，它会被静默豁免。
    if is_historical("deliverables/README.md") and "deliverables/README.md" not in LIVING_DOCS:
        problems.append("探针失效：既是活文档又命中 historical 的路径被历史族豁免了（缺优先级）")
    # 探针 19：镜像判据必须**能红**。`docs/index.md` 与 `public/index.md` 同名但内容不同，
    #          用它做反向对照 —— 若这两份被判成一致，说明 sha 比对是空判。
    _pa = os.path.join(root, "docs", "index.md")
    _pb = os.path.join(root, "public", "index.md")
    if os.path.exists(_pa) and os.path.exists(_pb) and sha(_pa) == sha(_pb):
        problems.append("探针失效：两份已知不同的同名文件被判为逐字节一致（镜像比对是空判）")

    if problems:
        print("FAIL 判据自检未通过：")
        for p in problems:
            print("  " + p)
        return 1

    if offenders:
        print("FAIL 活文档指向不存在的文件，且没有任何历史语境标记（%d 处）：" % len(offenders))
        for rel, ln, kind, base in offenders:
            print("  %s:%d -> [%s] %s" % (rel, ln, KIND_LABEL.get(kind, kind), base))
        print("  修法：改成本阶段的真实路径；确实是历史记录就补上『已删除/已修/Phase 6a』之类的措辞。")
        return 1

    by_kind = "、".join("%s %d" % (KIND_LABEL.get(k, k), counts[k]["exists"]) for k in counts)
    print("OK 观察面 %d 份活文档（清单 `%s`：%d 条历史族、%d 对镜像）、%d 处路径引用："
          "%d 处存在（%s）、%d 处处于历史语境；"
          "现存 %d 个页面、%d 个脚本、%d 个仓库内路径、%d 个顶层目录；未登记 0 份、镜像无漂移"
          % (len(LIVING_DOCS), MANIFEST, len(HISTORICAL), len(MIRRORS), total,
             sum(counts[k]["exists"] for k in counts), by_kind,
             len(excused), len(have["page"]), len(have["js"]), len(have["path"]),
             len(have["layer"])))
    if verbose:
        for rel, ln, kind, base, detail in excused:
            print("   hist %s:%d -> [%s] %s（%s）"
                  % (rel, ln, KIND_LABEL.get(kind, kind), base, detail))
    print("   现存页面：%s" % ", ".join(sorted(have["page"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
