# -*- coding: utf-8 -*-
"""radar_adapter.py · AbilityProfile -> ECharts radar option（WF-05 输出给前端）

用法:
  python tools/radar_adapter.py --input ability.json --output option.json

输出可直接被 js/radar.js 消费（indicator 六维 max=100，series 只有一条
「当前证据快照」）。历史上的「七天推演 low/high」两条曲线依赖固定 0.30/0.70
演示假设，属预测型展示，已于 2026-09-13 删除。

Radar 现在只是**可选可视化组件**，不再是一级功能；C0 只是当前证据快照，
不代表真实就业概率。
"""
import argparse
import io
import json
import sys


def build_option(ability):
    dims = ability["dimensions"]
    if len(dims) != 6:
        raise ValueError("dimensions 必须恰好六维（当前 %d）" % len(dims))
    base = ability["baseline"]
    if not (0 <= base <= 100):
        raise ValueError("baseline 越界 [0,100]")

    return {
        "tooltip": {},
        "legend": {"bottom": 0, "data": ["当前证据快照"]},
        "radar": {
            "indicator": [{"name": d["name"], "max": 100} for d in dims],
            "radius": "62%",
        },
        "series": [{
            "type": "radar",
            "data": [
                {"value": [d["score"] for d in dims], "name": "当前证据快照",
                 "areaStyle": {"opacity": 0.25}, "lineStyle": {"color": "#2563eb"}, "itemStyle": {"color": "#2563eb"}},
            ],
        }],
    }


def main():
    ap = argparse.ArgumentParser(description="AbilityProfile -> ECharts radar option")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    try:
        ability = json.load(io.open(args.input, encoding="utf-8"))
        option = build_option(ability)
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
        print("[radar_adapter] 输入错误：%s" % e, file=sys.stderr)
        sys.exit(2)

    with io.open(args.output, "w", encoding="utf-8") as f:
        json.dump(option, f, ensure_ascii=False, indent=2)
    print("[radar_adapter] OK %s -> %s（6 维，max=100）" % (args.input, args.output))


if __name__ == "__main__":
    main()
