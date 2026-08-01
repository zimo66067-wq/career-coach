# -*- coding: utf-8 -*-
"""radar_adapter.py · AbilityProfile -> ECharts radar option（WF-05 输出给前端）

用法:
  python tools/radar_adapter.py --input ability.json --output option.json

输出可直接被 ui/prototype/js/radar.js 消费（indicator 六维 max=100，
series 含 C0 基线 + 七天推演 low/high 两条）。
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
    low = ability["scenario_day7"]["low"]
    high = ability["scenario_day7"]["high"]
    if not (0 <= base <= 100 and 0 <= low <= 100 and 0 <= high <= 100):
        raise ValueError("baseline/low/high 越界 [0,100]")
    ratio_low = low / base if base else 1.0
    ratio_high = high / base if base else 1.0

    def scaled(ratio):
        return [round(min(100.0, d["score"] * ratio), 2) for d in dims]

    return {
        "tooltip": {},
        "legend": {"bottom": 0, "data": ["C0 基线", "七天推演 low", "七天推演 high"]},
        "radar": {
            "indicator": [{"name": d["name"], "max": 100} for d in dims],
            "radius": "62%",
        },
        "series": [{
            "type": "radar",
            "data": [
                {"value": [d["score"] for d in dims], "name": "C0 基线",
                 "areaStyle": {"opacity": 0.25}, "lineStyle": {"color": "#2563eb"}, "itemStyle": {"color": "#2563eb"}},
                {"value": scaled(ratio_low), "name": "七天推演 low",
                 "lineStyle": {"color": "#93c5fd", "type": "dashed"}, "itemStyle": {"color": "#93c5fd"}},
                {"value": scaled(ratio_high), "name": "七天推演 high",
                 "lineStyle": {"color": "#16a34a", "type": "dashed"}, "itemStyle": {"color": "#16a34a"}},
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
