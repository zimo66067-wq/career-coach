# -*- coding: utf-8 -*-
"""test_radar_adapter.py · radar_adapter 测试

测试:
  1. 正常输入生成正确的 ECharts option
  2. 六维数据完整性
  3. 只输出「当前证据快照」一条曲线（预测型的七天推演已于 2026-09-13 删除）
  4. 缺少维度 / 越界时抛异常
"""
import io
import json
import os

import pytest

from domain.internal.radar_adapter import build_option

FIX = os.path.join(os.path.dirname(__file__), "fixtures-synthetic")


def _load_ability():
    with io.open(os.path.join(FIX, "abilities", "ability-01.json"), encoding="utf-8") as f:
        return json.load(f)


class TestRadarAdapter:

    def test_build_option_valid_structure(self):
        """正常输入生成结构正确的 ECharts option"""
        ability = _load_ability()
        option = build_option(ability)

        assert "tooltip" in option
        assert "legend" in option
        assert "radar" in option
        assert "series" in option

        assert option["legend"]["data"] == ["当前证据快照"]

        assert len(option["series"]) == 1
        assert option["series"][0]["type"] == "radar"
        series_data = option["series"][0]["data"]
        assert len(series_data) == 1
        assert series_data[0]["name"] == "当前证据快照"

    def test_no_predictive_series(self):
        """不得再出现任何预测型的七天推演曲线（Phase 1 删除项）"""
        option = build_option(_load_ability())
        blob = json.dumps(option, ensure_ascii=False)
        for banned in ("七天推演", "C7", "scenario", "推演 low", "推演 high"):
            assert banned not in blob, "radar option must not contain %r" % banned

    def test_six_dimensions_completeness(self):
        """六维数据完整性: indicator 恰好 6 维"""
        ability = _load_ability()
        option = build_option(ability)

        indicators = option["radar"]["indicator"]
        assert len(indicators) == 6

        for ind in indicators:
            assert "name" in ind
            assert ind["max"] == 100

        baseline_values = option["series"][0]["data"][0]["value"]
        assert len(baseline_values) == 6

    def test_wrong_dimension_count_raises(self):
        """维度数 != 6 时抛 ValueError"""
        ability = _load_ability()
        ability["dimensions"] = ability["dimensions"][:3]
        with pytest.raises(ValueError, match="六维"):
            build_option(ability)

    def test_out_of_range_raises(self):
        """baseline 越界抛 ValueError"""
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
        ability = {"baseline": 68.27}
        with pytest.raises(KeyError):
            build_option(ability)

    def test_scenario_key_is_ignored(self):
        """即使输入里残留 scenario_day7，也不得再被读取或输出"""
        ability = _load_ability()
        ability["scenario_day7"] = {"low": 1.0, "high": 2.0, "assumptions": ["x"]}
        option = build_option(ability)
        assert len(option["series"][0]["data"]) == 1
        assert "scenario" not in json.dumps(option, ensure_ascii=False)
