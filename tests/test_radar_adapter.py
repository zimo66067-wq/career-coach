# -*- coding: utf-8 -*-
"""test_radar_adapter.py · radar_adapter 测试

测试:
  1. 正常输入生成正确的 ECharts option
  2. 六维数据完整性
  3. low/high 计算正确
  4. 缺少维度时抛异常
"""
import io
import json
import os

import pytest

from radar_adapter import build_option

FIX = os.path.join(os.path.dirname(__file__), "fixtures-synthetic")


def _load_ability():
    with io.open(os.path.join(FIX, "abilities", "ability-01.json"), encoding="utf-8") as f:
        return json.load(f)


class TestRadarAdapter:

    def test_build_option_valid_structure(self):
        """正常输入生成结构正确的 ECharts option"""
        ability = _load_ability()
        option = build_option(ability)

        # 基本结构
        assert "tooltip" in option
        assert "legend" in option
        assert "radar" in option
        assert "series" in option

        # legend 包含三条数据线
        legend_data = option["legend"]["data"]
        assert "C0 基线" in legend_data
        assert "七天推演 low" in legend_data
        assert "七天推演 high" in legend_data

        # series 结构
        assert len(option["series"]) == 1
        assert option["series"][0]["type"] == "radar"
        series_data = option["series"][0]["data"]
        assert len(series_data) == 3

    def test_six_dimensions_completeness(self):
        """六维数据完整性: indicator 恰好 6 维"""
        ability = _load_ability()
        option = build_option(ability)

        indicators = option["radar"]["indicator"]
        assert len(indicators) == 6

        for ind in indicators:
            assert "name" in ind
            assert ind["max"] == 100

        # 基线数据应有 6 个值
        baseline_values = option["series"][0]["data"][0]["value"]
        assert len(baseline_values) == 6

        # low 和 high 也各 6 个值
        low_values = option["series"][0]["data"][1]["value"]
        high_values = option["series"][0]["data"][2]["value"]
        assert len(low_values) == 6
        assert len(high_values) == 6

    def test_low_high_calculation(self):
        """low/high 按比例缩放计算正确"""
        ability = _load_ability()
        base = ability["baseline"]
        low_target = ability["scenario_day7"]["low"]
        high_target = ability["scenario_day7"]["high"]

        ratio_low = low_target / base if base else 1.0
        ratio_high = high_target / base if base else 1.0

        option = build_option(ability)
        dims = ability["dimensions"]

        # 验证 low 值
        low_values = option["series"][0]["data"][1]["value"]
        for i, d in enumerate(dims):
            expected = round(min(100.0, d["score"] * ratio_low), 2)
            assert abs(low_values[i] - expected) < 0.01

        # 验证 high 值
        high_values = option["series"][0]["data"][2]["value"]
        for i, d in enumerate(dims):
            expected = round(min(100.0, d["score"] * ratio_high), 2)
            assert abs(high_values[i] - expected) < 0.01

    def test_low_le_high_le_100(self):
        """low <= high 且均 <= 100"""
        ability = _load_ability()
        option = build_option(ability)

        low_values = option["series"][0]["data"][1]["value"]
        high_values = option["series"][0]["data"][2]["value"]

        for lo, hi in zip(low_values, high_values):
            assert lo <= hi
            assert lo <= 100
            assert hi <= 100

    def test_wrong_dimension_count_raises(self):
        """维度数 != 6 时抛 ValueError"""
        ability = _load_ability()
        # 只保留 3 维
        ability["dimensions"] = ability["dimensions"][:3]
        with pytest.raises(ValueError, match="六维"):
            build_option(ability)

    def test_out_of_range_raises(self):
        """baseline/low/high 越界抛 ValueError"""
        ability = _load_ability()
        ability["baseline"] = 150.0
        with pytest.raises(ValueError, match="越界"):
            build_option(ability)

    def test_baseline_values_match_input(self):
        """基线值与输入 dimension score 一致"""
        ability = _load_ability()
        option = build_option(ability)
        dims = ability["dimensions"]

        baseline_values = option["series"][0]["data"][0]["value"]
        for i, d in enumerate(dims):
            assert baseline_values[i] == d["score"]

    def test_missing_dimensions_key_raises(self):
        """缺少 dimensions 键抛 KeyError"""
        ability = {"baseline": 68.27, "scenario_day7": {"low": 77.79, "high": 90.48}}
        with pytest.raises(KeyError):
            build_option(ability)

    def test_missing_scenario_key_raises(self):
        """缺少 scenario_day7 抛 KeyError"""
        ability = _load_ability()
        del ability["scenario_day7"]
        with pytest.raises(KeyError):
            build_option(ability)
