# -*- coding: utf-8 -*-
"""Auto-validation for F2 major-based matching data (majors_2025 + profiles_top30)."""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAJORS = REPO / "data" / "f2" / "majors_2025.json"
PROFILES = REPO / "data" / "f2" / "profiles_top30.json"
REPORT = REPO / "deliverables" / "f2-data-validation-2026-08-06.md"

VALID_LEVELS = {"强", "较强", "较弱", "弱", "无关", "无对应"}
CODE_RE = re.compile(r"^\d{6,7}$")


def main() -> int:
    errors, warnings = [], []
    majors = json.loads(MAJORS.read_text(encoding="utf-8"))
    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))

    cats = majors["categories"]
    major_index = {}
    for cat in cats:
        for cls in cat["classes"]:
            for m in cls["majors"]:
                if m["code"] in major_index:
                    errors.append(f"重复专业代码: {m['code']} {m['name']}")
                major_index[m["code"]] = {
                    "name": m["name"],
                    "class_code": cls["code"],
                    "class_name": cls["name"],
                    "category_code": cat["code"],
                    "category_name": cat["name"],
                }

    if len(cats) != 12:
        errors.append(f"学科门类数量 {len(cats)} != 12")
    n_cls = sum(len(c["classes"]) for c in cats)
    if n_cls != 93:
        errors.append(f"专业类数量 {n_cls} != 93")
    if len(major_index) != 845:
        errors.append(f"专业数量 {len(major_index)} != 845")
    for code in major_index:
        if not CODE_RE.match(code):
            errors.append(f"专业代码格式异常: {code}")
    if majors.get("version") != "2025":
        errors.append("majors version != 2025")
    if not majors.get("source", "").startswith("http"):
        errors.append("majors 缺少官方来源")

    profs = profiles["profiles"]
    seen = set()
    for p in profs:
        code, name = p["code"], p["name"]
        if code in seen:
            errors.append(f"画像重复专业: {code}")
        seen.add(code)
        base = major_index.get(code)
        if base is None:
            errors.append(f"画像专业不在目录中: {code} {name}")
            continue
        if base["name"] != name:
            errors.append(f"画像专业名称与目录不一致: {code} {name} vs {base['name']}")
        direct, deriv = p.get("direct", []), p.get("derivative", [])
        if len(direct) < 2:
            errors.append(f"{code} 对口方向 < 2")
        if len(deriv) < 2:
            errors.append(f"{code} 衍生方向 < 2")
        for kind, items in (("direct", direct), ("derivative", deriv)):
            for it in items:
                if not it.get("occupation"):
                    errors.append(f"{code} {kind} 缺 occupation")
                if it.get("level") not in VALID_LEVELS:
                    errors.append(f"{code} {kind} 等级非法: {it.get('level')}")
                if kind == "direct" and it.get("level") not in {"强", "较强"}:
                    errors.append(f"{code} direct 等级应为强/较强: {it.get('level')}")
                if kind == "derivative" and it.get("level") not in {"较弱", "弱"}:
                    errors.append(f"{code} derivative 等级应为较弱/弱: {it.get('level')}")
                if not it.get("titles") or not it.get("keywords"):
                    errors.append(f"{code} {kind} 缺 titles/keywords")
                if not it.get("description"):
                    warnings.append(f"{code} {kind} 缺 description")
                if not it.get("skills") and kind == "direct":
                    warnings.append(f"{code} direct 缺 skills")

    if not profiles["profiles"][0].get("summary"):
        errors.append("画像缺 summary")
    if profiles.get("version") != "2026-08-06":
        warnings.append("profiles version 非 2026-08-06")

    covered = len(seen)
    lines = [
        "# F2 专业数据自动校验报告（2026-08-06）",
        "",
        f"- 专业目录版本：{majors.get('version')}（官方）",
        f"- 学科门类：{len(cats)}（应为 12）",
        f"- 专业类：{n_cls}（应为 93）",
        f"- 专业总数：{len(major_index)}（应为 845）",
        f"- 画像专业：{covered}/30（Top 30 批次）",
        f"- 错误：{len(errors)} ｜ 警告：{len(warnings)}",
        "",
        "## 错误清单",
    ]
    lines += [f"- {e}" for e in errors] or ["- 无"]
    lines += ["", "## 警告清单"]
    lines += [f"- {w}" for w in warnings] or ["- 无"]
    lines += ["", "## 结论", "", "**通过** 数据可进入 R2-R5。" if not errors else "**未通过**，需修复后重新校验。"]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"majors={len(major_index)} classes={n_cls} cats={len(cats)} "
        f"profiles={covered} errors={len(errors)} warnings={len(warnings)}"
    )
    for e in errors[:20]:
        print("ERR:", e)
    print("report:", REPORT)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
