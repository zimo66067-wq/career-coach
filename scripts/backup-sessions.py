#!/usr/bin/env python3
"""backup-sessions.py · 会话数据自动备份

从本地 SQLite 会话存储导出全部去标识化数据到 deliverables/ 下的日期化 JSON，
用于缓解 Vercel /tmp 临时文件系统冷启动丢数据的问题（配合 admin/export 定期备份）。

用法:
  python scripts/backup-sessions.py [--out <path.json>]
"""
import argparse
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.database import export_all  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="导出会话数据备份")
    ap.add_argument("--out", default=None, help="输出 JSON 路径（默认 deliverables/session-backup-YYYYMMDD.json）")
    args = ap.parse_args()

    data = export_all()
    if args.out:
        out_path = Path(args.out)
    else:
        out_dir = ROOT / "deliverables"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / ("session-backup-%s.json" % datetime.now().strftime("%Y%m%d"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(str(out_path), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("备份完成: %s" % out_path)
    print("  简历条数: %d" % len(data.get("resumes", [])))
    print("  诊断条数: %d" % len(data.get("diagnoses", [])))
    print("  数据库路径: %s" % data.get("db_path"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
