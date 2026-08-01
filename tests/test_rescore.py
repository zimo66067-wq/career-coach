# -*- coding: utf-8 -*-
"""test_rescore.py · rescore 对拍 scoring.md 手算示例 + 边界"""
import pytest

import rescore


def test_handcalc_example(score_input):
    """与 contracts/scoring.md 第6节手算示例对拍（±0.5，实际应完全相等）"""
    result = rescore.compute(score_input)
    exp = score_input["expected"]
    for k in ("R", "M", "I", "C0", "C7_low", "C7_high"):
        assert abs(result[k] - exp[k]) <= 0.5, "%s: got %s expect %s" % (k, result[k], exp[k])


def test_unknown_excluded_from_denominator():
    data = {
        "R": {"structure": 80, "clarity": 80, "achievement_evidence": 80, "skill_evidence": 80, "ats_readability": 80},
        "M": {"requirements": [
            {"type": "hard", "status": "covered"},
            {"type": "hard", "status": "unknown"},  # 剔出分母
        ]},
        "I": {"structure": 80, "relevance": 80, "specificity": 80, "followup_adaptation": 80, "clarity": 80},
    }
    result = rescore.compute(data)
    # hard: 仅 covered 计入 → 100；其余三类全 unknown → 权重归一 → M=100
    assert result["M"] == 100.0
    assert result["M_categories"]["hard"] == 100.0
    assert result["M_categories"]["preferred"] == "insufficient_evidence"


def test_all_unknown_is_insufficient_evidence():
    data = {
        "R": {"structure": 50, "clarity": 50, "achievement_evidence": 50, "skill_evidence": 50, "ats_readability": 50},
        "M": {"requirements": [{"type": "hard", "status": "unknown"}]},
        "I": {"structure": 50, "relevance": 50, "specificity": 50, "followup_adaptation": 50, "clarity": 50},
    }
    result = rescore.compute(data)
    assert result.get("insufficient_evidence") is True
    assert "C0" not in result


def test_score_out_of_range_rejected():
    data = {
        "R": {"structure": 120, "clarity": 80, "achievement_evidence": 80, "skill_evidence": 80, "ats_readability": 80},
        "M": {"requirements": []},
        "I": {"structure": 80, "relevance": 80, "specificity": 80, "followup_adaptation": 80, "clarity": 80},
    }
    with pytest.raises(ValueError):
        rescore.compute(data)


def test_c7_capped_at_100():
    data = {
        "R": {"structure": 100, "clarity": 100, "achievement_evidence": 100, "skill_evidence": 100, "ats_readability": 100},
        "M": {"requirements": [{"type": "hard", "status": "covered"}]},
        "I": {"structure": 100, "relevance": 100, "specificity": 100, "followup_adaptation": 100, "clarity": 100},
    }
    result = rescore.compute(data)
    assert result["C0"] == 100.0
    assert result["C7_low"] == 100.0 and result["C7_high"] == 100.0
