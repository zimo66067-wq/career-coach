# -*- coding: utf-8 -*-
"""Parse MOE《普通高等学校本科专业目录（2025年）》PDF into structured JSON.

Source PDF: 教育部官网附件2 (W020250422312780837078.pdf)
Output: data/f2/majors_2025.json
"""
import json
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    print("pdfplumber required: pip install pdfplumber")
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
PDF_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:\tmp\moe2025_2.pdf")
OUT_PATH = REPO / "data" / "f2" / "majors_2025.json"

CAT_RE = re.compile(r"^(\d{2})\s+学科门类[:：]\s*(.+)$")
CLASS_RE = re.compile(r"^(\d{4})\s+([^\s]+?类)$")
MAJOR_RE = re.compile(r"^(\d{6,7}[TK]*)\s+(.+)$")


def main() -> int:
    categories = []
    current_cat = None
    current_cls = None
    counts = {"major": 0, "cls": 0, "cat": 0}

    with pdfplumber.open(str(PDF_PATH)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                m = CAT_RE.match(line)
                if m:
                    current_cat = {"code": m.group(1), "name": m.group(2).strip(), "classes": []}
                    categories.append(current_cat)
                    current_cls = None
                    counts["cat"] += 1
                    continue
                m = CLASS_RE.match(line)
                if m:
                    if current_cat is None:
                        continue
                    current_cls = {"code": m.group(1), "name": m.group(2), "majors": []}
                    current_cat["classes"].append(current_cls)
                    counts["cls"] += 1
                    continue
                m = MAJOR_RE.match(line)
                if m and current_cls is not None:
                    code_raw = m.group(1)
                    name_raw = m.group(2).strip()
                    note = ""
                    if "（注：" in name_raw:
                        name_raw, note = name_raw.split("（注：", 1)
                        note = "注：" + note.rstrip("）")
                    elif "（" in name_raw and "）" in name_raw:
                        # annotations like （注：...） already handled; keep other parens out of name
                        name_raw = re.sub(r"（[^）]*）", "", name_raw).strip()
                    flags = re.sub(r"\d", "", code_raw)
                    code = re.match(r"\d+", code_raw).group()
                    current_cls["majors"].append(
                        {"code": code, "name": name_raw, "flags": flags, "note": note}
                    )
                    counts["major"] += 1

    data = {
        "version": "2025",
        "title": "普通高等学校本科专业目录（2025年）",
        "source": "http://www.moe.gov.cn/srcsite/A08/moe_1034/s4930/202504/t20250422_1188239.html",
        "counts": {"categories": counts["cat"], "classes": counts["cls"], "majors": counts["major"]},
        "categories": categories,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False))
    print("written:", OUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
