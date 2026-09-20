#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""living-docs-scope-check.py · 观察面清单 `contracts/living-docs.json` 的**独立复算**。

## 为什么要有这个脚本（Phase 8 新增，gate8 第 16 步）

Phase 8 把「活文档观察面」从写死在判据里的 8 份，改成从清单读的 56 份。
**清单化本身引入了一个新失效模式：清单与实仓漂移。** 它的四种形态里，只有第一种
是判据自己能看见的：

| 漂移形态 | 谁看得见 |
| --- | --- |
| 清单里写了不存在的文件（幽灵条目） | `live-doc-path-check.py` 自检 A |
| 新加一份含引用的 md 却没登记（漏登记） | 同上，自检 B |
| 某条 historical glob 写错，命中面塌成 0 | 同上，自检 C（只要求 ≥1） |
| **某条 glob 命中面塌成「全是 living」——它什么都没豁免** | **没人看得见** |
| **整仓被吞进豁免区，观察面悄悄变成空** | **没人看得见** |

后两种就是"空判"：判据照样返回 OK，但那条规则已经不再约束任何东西。
本脚本存在的唯一理由，是把这四种形态**换一套实现**再算一遍 —— 它刻意
**不 import** `live-doc-path-check.py`：同一份实现自查，只能证明"它和自己一致"。

## 与判据的分工（判据是规格，本脚本是反例搜索器）

判据回答"每处引用落不落得下"；本脚本回答"清单这个对象本身立不立得住"。
所以本脚本**不抽路径正则**（那部分与判据重合，重合了也测不出新东西），
只判清单的结构契约 + 两条空判防线 + 一条反向控制探针。
"""
import fnmatch
import hashlib
import io
import json
import os
import sys

MANIFEST = "contracts/living-docs.json"

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".workbuddy"}

#: 反向控制探针用的一对文件。判据用它证明「同名 ≠ 镜像」这条规则是**可判**的：
#: 它俩同名（都叫 index.md）、同目录名（docs/ 与 public/），但内容不同，
#: 而且清单里**刻意没有**把它们登记成镜像对。若某天有人"顺手"把两份同步成一样，
#: 说明他误把同名当成了镜像 —— 探针必须红，因为那会抹掉 `docs/index.md` 的目录索引语义。
PROBE_A = "docs/index.md"
PROBE_B = "public/index.md"


def read_bytes(path):
    with io.open(path, "rb") as f:
        return f.read()


def sha256(path):
    return hashlib.sha256(read_bytes(path)).hexdigest()


def all_md(root):
    """全仓 `.md` 相对路径（与判据同口径：跳过 SKIP_DIRS 与虚拟环境目录）。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [x for x in dirnames
                       if x not in SKIP_DIRS and not x.startswith(".venv")]
        for n in filenames:
            if n.endswith(".md"):
                out.append(os.path.relpath(os.path.join(dirpath, n), root)
                           .replace(os.sep, "/"))
    return sorted(out)


def matches(rel, glob):
    """`fnmatch` 的 `*` 跨 `/`（与 glob 不同），与本判据族的语义一致。"""
    return fnmatch.fnmatch(rel, glob)


def main():
    root = os.getcwd()
    problems = []

    # ── 0. 空判防线之一：清单必须存在且可解析。缺了就红，不降级。 ──
    # "退回默认观察面"是最糟的失败形态：它让判据继续绿，而观察面已经不是清单说的那个。
    mpath = os.path.join(root, MANIFEST)
    if not os.path.exists(mpath):
        print("FAIL 清单不存在：%s" % MANIFEST)
        return 1
    try:
        with io.open(mpath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as exc:
        print("FAIL 清单不是合法 JSON：%s（%s）" % (MANIFEST, exc))
        return 1

    living = [(i or {}).get("path") for i in (data.get("living") or [])]
    living = [p for p in living if p]
    historical = [(i or {}).get("glob") for i in (data.get("historical") or [])]
    historical = [g for g in historical if g]
    mirrors = [(i["a"], i["b"]) for i in (data.get("mirrors") or [])
               if i and i.get("a") and i.get("b")]

    print("清单：%d 条 living、%d 条 historical、%d 对镜像"
          % (len(living), len(historical), len(mirrors)))

    # ── 1. 空判防线之二：三组都不得为空。 ──
    # 空清单会让下游每一条循环都跑 0 次 —— 全绿，且全空。
    if not living:
        problems.append("`living` 为空：观察面是空集，判据必然全绿")
    if not historical:
        problems.append("`historical` 为空：没有任何豁免族（要么漏登记，要么豁免逻辑已失效）")
    if not mirrors:
        problems.append("`mirrors` 为空：镜像不变量不再被任何清单约束")

    # ── 2. 幽灵条目：清单里的 living 文件必须真实存在。 ──
    for p in living:
        if not os.path.exists(os.path.join(root, p)):
            problems.append("幽灵条目：living 里的 `%s` 不存在" % p)

    # ── 3. 缺理由：每个条目都必须写 why（清单是"可判对象"，理由就是判据）。 ──
    for key in ("living", "historical"):
        for item in (data.get(key) or []):
            if not item:
                continue
            name = item.get("path") or item.get("glob") or "(无名条目)"
            if not item.get("why"):
                problems.append("%s 条目缺 `why`：`%s`" % (key, name))

    # ── 4. 失效 glob：每条 historical 必须真的命中文件，否则它是一条装饰。 ──
    repo_md = all_md(root)
    matched_all = {}
    for g in historical:
        hit = [m for m in repo_md if matches(m, g)]
        matched_all[g] = hit
        if not hit:
            problems.append("失效 glob：`%s` 命中 0 个文件（它不在豁免任何东西）" % g)

    # ── 5. 空判防线之三（判据看不见的那条）：glob 命中面不得**全是** living。 ──
    # `deliverables/**` 命中 53 个文件、其中只有 `deliverables/README.md` 是 living —— 有效。
    # 但如果某条 glob 命中的每一个文件都已经是 living，那这条豁免是**空判**：
    # 它写在那里像一条规则，实际一个文件都没豁免。判据的自检 C 只要求"命中 ≥1"，
    # 所以这种形态只有本脚本能看见。
    living_set = set(living)
    for g, hit in matched_all.items():
        if hit and all(h in living_set for h in hit):
            problems.append(
                "空判豁免：`%s` 命中的 %d 个文件**全部**已是 living，它没豁免任何东西"
                % (g, len(hit)))

    # ── 6. 镜像对：两份都必须存在且逐字节相同。 ──
    for a, b in mirrors:
        pa, pb = os.path.join(root, a), os.path.join(root, b)
        if not os.path.exists(pa):
            problems.append("镜像对左侧不存在：`%s`" % a)
            continue
        if not os.path.exists(pb):
            problems.append("镜像对右侧不存在：`%s`" % b)
            continue
        if sha256(pa) != sha256(pb):
            problems.append("镜像漂移：`%s` 与 `%s` 内容不同" % (a, b))

    # ── 7. 反向控制探针：证明"内容不同"这件事**判得出来**。 ──
    # 与 `live-doc-path-check.py` 的探针 19 同题不同法：这里直接比字节。
    # 少了这条，第 6 节全绿可能只是因为 sha 比较恒真（比如路径拼错、读的是同一份文件）。
    pa, pb = os.path.join(root, PROBE_A), os.path.join(root, PROBE_B)
    if os.path.exists(pa) and os.path.exists(pb):
        if sha256(pa) == sha256(pb):
            problems.append(
                "探针失效：`%s` 与 `%s` 内容相同了 —— 有人把「同名」当成了「镜像」。"
                "这一对**刻意不是**镜像（前者是 docs 目录索引，后者是发布树公开清单）"
                % (PROBE_A, PROBE_B))
        else:
            print("探针：`%s` ≠ `%s`（同名非镜像，判得出来）✓" % (PROBE_A, PROBE_B))
    else:
        problems.append("探针无法运行：`%s` 或 `%s` 不存在" % (PROBE_A, PROBE_B))

    # ── 8. 裸名豁免必须写明理由（`excluded_forms`），否则"不收"这件事没有判据。 ──
    forms = data.get("excluded_forms") or []
    if len(forms) < 3:
        problems.append("`excluded_forms` 少于 3 条：不判的形态必须逐条写明理由")
    for item in forms:
        if not (item or {}).get("why"):
            problems.append("excluded_forms 条目缺 `why`：`%s`"
                            % ((item or {}).get("form") or "(无名)"))

    # ── 9. precedence 必须显式声明（living 与 historical 重叠时的裁决）。 ──
    if not (data.get("precedence") or "").strip():
        problems.append("清单缺 `precedence`：living 与 historical 重叠时无裁决规则")

    if problems:
        print("FAIL 结构契约 %d 处不成立：" % len(problems))
        for p in problems:
            print("  - %s" % p)
        return 1

    print("OK 清单结构契约全部成立（幽灵条目 0、失效 glob 0、空判豁免 0、镜像漂移 0）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
