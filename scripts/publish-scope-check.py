# -*- coding: utf-8 -*-
"""公开范围判据：`public/` 下对公网可读的 md，必须与 `contracts/publish-scope.json` 完全一致。

**为什么需要它**：Vercel 静态根是 `public/`（实测 200），所以「把文档放进 public/」与
「把文档发布出去」是同一个动作 —— 没有中间态。这个集合此前是隐式的：没有清单、没有判据，
`docs/phase6a-report.md` 与 6b-1 两次把它记成「属产品/隐私决策」后挂起，而挂起没有触发条件，
于是它第三次出现。本判据把「挂起」换成「有记录的决定」：任何增 / 删 / 改名都必须同时改清单。

## 观察面（明确写在这里，免得下一个人以为它管得比实际宽）

只看两处：

- **A.** `public/**/*.md` 的实际文件集合（相对路径，posix 分隔符）；
- **B.** `contracts/publish-scope.json` 的 `entries[].path`。

**不看**：非 md 文件（那由 `scripts/sync_mirror.py` 的镜像不变量管）、`docs/**` 下的 md
（`docs/` 合法地多出内部文档，它们不是发布树）、以及 md 的内容（内容由
`scripts/sensitive-scan.py` 与人工 review 管）。本判据只回答一个问题：
**公开的 md 集合有没有在没人注意的情况下变了。**

用法::

    python scripts/publish-scope-check.py            # 校验；漂移则退出码 1
    python scripts/publish-scope-check.py --list     # 只打印当前公开集合

退出码 0 = 通过，1 = 公开范围漂移 / 清单结构错误 / 判据自检未过（探针失效）。
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
MANIFEST = ROOT / "contracts" / "publish-scope.json"


def normalize(rel):
    """相对路径归一：反斜杠→斜杠、去掉前导 './'、去空白。

    没有这一步，`./README.md` 与 `README.md` 会被当成两个文件 —— 一个假阳性足以
    让下一个人删掉这条判据（6b-2b 的教训）。
    """
    text = str(rel).strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def tree_md(public_dir):
    """public/ 下实际存在的 md，返回归一后的相对路径集合。"""
    if not public_dir.is_dir():
        return set()
    found = set()
    for path in public_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".md":
            found.add(normalize(path.relative_to(public_dir).as_posix()))
    return found


def guard_empty(collection, label):
    """空判防线：规则一条都没匹配上时，后面所有断言都会假绿，必须拒绝执行。

    返回错误串或 None（纯函数，便于自检）。
    """
    if not collection:
        return "%s 为空，规则失效，拒绝执行" % label
    return None


def validate_entries(data, known_classes):
    """清单结构校验，返回 (声明路径集合, 错误列表)。纯函数，便于自检。"""
    errors = []
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        return set(), ["清单没有 entries（或为空）—— 空清单会让下面所有断言假绿"]
    declared = set()
    for index, entry in enumerate(entries):
        where = "entries[%d]" % index
        if not isinstance(entry, dict):
            errors.append("%s 不是对象" % where)
            continue
        path = normalize(entry.get("path") or "")
        if not path:
            errors.append("%s 缺 path" % where)
            continue
        if path in declared:
            errors.append("path 重复：%s" % path)
        declared.add(path)
        if not normalize(entry.get("reason") or ""):
            errors.append("%s（%s）缺 reason —— 决定必须留理由" % (where, path))
        if entry.get("class") not in known_classes:
            errors.append("%s（%s）的 class 不在 classes 里：%r"
                          % (where, path, entry.get("class")))
    return declared, errors


def compare(tree, declared):
    """返回 (未记录=树里有清单没有, 失效=清单有树里没有)，均为排序列表。"""
    return sorted(tree - declared), sorted(declared - tree)


def self_check(known_classes):
    """判据自检：每条断言都要能自己失效。返回探针失败列表。"""
    failures = []

    def probe(name, condition):
        if not condition:
            failures.append(name)

    probe("探针 1（空判防线）：空集合必须被拦下，不能静默放行",
          guard_empty(set(), "public/ 的 md") is not None
          and guard_empty({"a.md"}, "public/ 的 md") is None)

    unrecorded, stale = compare({"new-doc.md", "README.md"}, {"README.md"})
    probe("探针 2：树里多出一份未记录的 md 必须被判为漂移",
          unrecorded == ["new-doc.md"] and not stale)

    unrecorded, stale = compare({"README.md"}, {"README.md", "gone.md"})
    probe("探针 3：清单里有而树里没有必须被判为漂移",
          stale == ["gone.md"] and not unrecorded)

    probe("探针 4：前导 './' 与反斜杠必须归一成同一个路径",
          normalize("./a.md") == "a.md" and normalize("sub\\b.md") == "sub/b.md")

    unrecorded, _ = compare({"blind-test-results/blind-test-report.md"}, set())
    probe("探针 5：子目录下的 md 必须能被观察到",
          unrecorded == ["blind-test-results/blind-test-report.md"])

    _, errors = validate_entries(
        {"entries": [{"path": "a.md", "class": known_classes[0]}]}, known_classes)
    probe("探针 6：条目缺 reason 必须报错", any("reason" in e for e in errors))

    _, errors = validate_entries(
        {"entries": [{"path": "a.md", "class": "不存在的分类", "reason": "x"}]}, known_classes)
    probe("探针 7：分类不在白名单里必须报错", any("class" in e for e in errors))

    _, errors = validate_entries(
        {"entries": [{"path": "a.md", "class": known_classes[0], "reason": "x"},
                     {"path": "./a.md", "class": known_classes[0], "reason": "y"}]},
        known_classes)
    probe("探针 8：归一后重复的 path 必须报错", any("重复" in e for e in errors))

    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="public/ 公开 md 集合 vs contracts/publish-scope.json")
    parser.add_argument("--list", action="store_true", help="只打印当前公开 md 集合")
    args = parser.parse_args(argv)

    if not MANIFEST.is_file():
        raise SystemExit("清单不存在：%s" % MANIFEST)
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    known_classes = data.get("classes") or []
    if not known_classes:
        raise SystemExit("清单缺少 classes 白名单，分类校验会假绿，拒绝执行")

    tree = tree_md(PUBLIC)
    if args.list:
        for rel in sorted(tree):
            print(rel)
        return 0

    empties = [guard_empty(tree, "public/ 的 md"), guard_empty(known_classes, "classes")]
    for item in empties:
        if item:
            print("  " + item)
            return 1

    failures = self_check(known_classes)
    if failures:
        for item in failures:
            print("  自检失败：%s" % item)
        print("判据自检未通过（%d 项）—— 判据本身有问题，先修判据" % len(failures))
        return 1

    declared, errors = validate_entries(data, known_classes)
    if errors:
        for item in errors:
            print("  清单错误：%s" % item)
        return 1

    unrecorded, stale = compare(tree, declared)
    for rel in unrecorded:
        print("  未记录（public/ 下存在但清单没有）：%s" % rel)
    for rel in stale:
        print("  失效（清单里有但 public/ 下已不存在）：%s" % rel)

    if unrecorded or stale:
        print("公开范围漂移 %d 处 —— 若确属有意变更，请同步改 contracts/publish-scope.json"
              % (len(unrecorded) + len(stale)))
        return 1

    print("OK 公开 md 集合与清单一致：%d 份（自检 8 项通过）" % len(tree))
    return 0


if __name__ == "__main__":
    sys.exit(main())
