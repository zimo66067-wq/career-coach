# -*- coding: utf-8 -*-
"""publish 树镜像同步：`public/` 是唯一源，`docs/` 是发布镜像。

规则（按事实推导，没有硬编码清单）：
  1. `public/` 下每个 **非 `.md`** 文件，`docs/` 必须有同名文件且**逐字节相同**；
  2. 反向也成立：`docs/` 下不得存在 `public/` 没有的非 `.md` 文件（防镜像侧长孤儿）。

为什么排除 `.md`：`docs/` 合法地多出 29 份内部文档（`phase*-report.md`、`product-scope.md`、
`dependency-map.md` …），它们是**文档树**而不是前端资源。哪些内部文档该公开属产品/隐私决策，
不在这里自动决定 —— 见 `docs/phase6a-report.md` 的「剩余与口径」。

用法::

    python scripts/sync_mirror.py            # 同步：把 public 的差异文件复制到 docs
    python scripts/sync_mirror.py --check    # 只校验；有漂移则退出码 1（门禁用）
"""
import argparse
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "public"
MIRROR = ROOT / "docs"
EXCLUDED_SUFFIX = ".md"


def collect(root):
    """返回 {相对路径: Path}，相对路径统一用斜杠，排除 .md。"""
    if not root.is_dir():
        raise SystemExit("目录不存在：%s" % root)
    found = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() == EXCLUDED_SUFFIX:
            continue
        found[path.relative_to(root).as_posix()] = path
    return found


def compare(source_files, mirror_files):
    """纯函数，便于自检：返回 (missing, extra, differing) 三份相对路径列表。"""
    missing = sorted(set(source_files) - set(mirror_files))
    extra = sorted(set(mirror_files) - set(source_files))
    differing = sorted(
        rel for rel in (set(source_files) & set(mirror_files))
        if not filecmp.cmp(source_files[rel], mirror_files[rel], shallow=False)
    )
    return missing, extra, differing


def report(missing, extra, differing):
    for rel in missing:
        print("  缺失（docs 侧没有）：%s" % rel)
    for rel in extra:
        print("  孤儿（docs 侧多出）：%s" % rel)
    for rel in differing:
        print("  内容不一致：%s" % rel)
    total = len(missing) + len(extra) + len(differing)
    if total:
        print("镜像漂移 %d 处" % total)
    else:
        print("镜像一致：%d 个非 md 文件逐字节相同" % len(collect(SOURCE)))
    return total


def main(argv=None):
    parser = argparse.ArgumentParser(description="public -> docs 发布镜像同步")
    parser.add_argument("--check", action="store_true", help="只校验，不写盘")
    args = parser.parse_args(argv)

    source_files = collect(SOURCE)
    mirror_files = collect(MIRROR)
    # 防空转：规则若一条都没匹配上，后面所有断言都会"假绿"
    if not source_files:
        raise SystemExit("public/ 下没有可镜像的非 md 文件，规则失效，拒绝执行")

    missing, extra, differing = compare(source_files, mirror_files)

    if args.check:
        drift = report(missing, extra, differing)
        return 1 if drift else 0

    copied = 0
    for rel in missing + differing:
        target = MIRROR / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_files[rel], target)
        copied += 1
        print("  已同步：%s" % rel)
    print("同步完成：复制 %d 个文件" % copied)
    if extra:
        # 不自动删——镜像侧多出的文件要人确认它是不是真的没人要
        print("以下文件只存在于 docs/，需人工确认后再删：")
        for rel in extra:
            print("  %s" % rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
