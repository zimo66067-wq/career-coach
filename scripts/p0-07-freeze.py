#!/usr/bin/env python3
"""P0-07 G9 提交包冻结脚本"""
import subprocess, json
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PROJECT = Path(__file__).resolve().parent.parent
EVIDENCE = PROJECT / "deliverables/wf-evidence-20260803"

print("="*60)
print("P0-07 提交包冻结")
print("="*60)

# 1. 文件清单
manifest = {}
for category, patterns in [
    ("code", ["tools/*.py", "scripts/*.py"]),
    ("contracts", ["contracts/*.json", "contracts/*.md"]),
    ("docs", ["docs/*.md", "README.md"]),
    ("tests", ["tests/*.py", "tests/fixtures-synthetic/**/*"]),
    ("evidence", ["deliverables/**/*"]),
    ("ui", ["ui/prototype/**/*"]),
    ("workflows", ["workflows/*.md"]),
    ("prompts", ["prompts/**/*.md"]),
    ("handoffs", ["handoffs/*.md"]),
]:
    files = []
    for pat in patterns:
        files.extend(PROJECT.glob(pat))
    manifest[category] = sorted(
        str(f.relative_to(PROJECT)).replace(chr(92), "/")
        for f in files
    )

total = sum(len(v) for v in manifest.values())

# 2. 生成提交清单
freeze_info = {
    "project": "career-coach",
    "freeze_tag": "v1.0.0-g9-freeze",
    "freeze_date": datetime.now().isoformat(),
    "freeze_commit": None,
    "branch": "main",
    "total_files": total,
    "manifest": manifest,
    "p0_status": {
        "p0-01_real_model": "pending_api_key",
        "p0-02_automation": "completed",
        "p0-03_real_data": "pending_p0-01",
        "p0-04_voice": "completed",
        "p0-05_links": "completed",
        "p0-06_user_validation": "pending",
        "p0-07_freeze": "in_progress",
    }
}

checklist_path = EVIDENCE / "g9-submission-checklist.json"
with open(checklist_path, 'w', encoding='utf-8') as f:
    json.dump(freeze_info, f, ensure_ascii=False, indent=2)

print(f"提交清单已生成")
print(f"  总文件数: {total}")
print(f"  清单路径: {checklist_path}")
print()
for cat, files in manifest.items():
    print(f"  {cat}: {len(files)} 个文件")

print()
print("P0 状态:")
for k, v in freeze_info["p0_status"].items():
    icon = "✅" if v == "completed" else "⏳" if "pending" in v else "🔧"
    print(f"  {icon} {k}: {v}")
