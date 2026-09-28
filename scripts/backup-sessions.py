#!/usr/bin/env python3
"""Legacy resume/diagnosis export, NOT a complete database backup.

Output must be explicitly selected outside the repository and must not exist.
Treat the export as sensitive user data; use encrypted, access-controlled storage.
Production Postgres recovery requires provider-native backup/PITR and an isolated
restore drill; this script does not replace that process.
"""
import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from repositories.database import export_all  # noqa: E402


def export_destination(value):
    path = Path(value).expanduser().resolve()
    if not Path(value).is_absolute() or path == ROOT or ROOT in path.parents:
        raise ValueError("Export must use an absolute path outside the repository")
    if path.exists():
        raise ValueError("Export destination already exists; refusing overwrite")
    return path


def main():
    ap = argparse.ArgumentParser(description="仅导出简历/诊断，不是完整数据库备份")
    ap.add_argument("--out", required=True, help="仓库外安全目录的绝对 JSON 路径；拒绝覆盖")
    args = ap.parse_args()
    out_path = export_destination(args.out)
    data = export_all()
    data.pop("db_path", None)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(str(out_path), "x", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("简历/诊断导出完成；不包含完整核心业务数据，不构成生产恢复验收。")
    print("  简历条数: %d" % len(data.get("resumes", [])))
    print("  诊断条数: %d" % len(data.get("diagnoses", [])))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("Export failed: %s (details suppressed)" % type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
