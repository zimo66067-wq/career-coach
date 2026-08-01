# -*- coding: utf-8 -*-
"""test_fault_injection.py · 故障注入：非法输入必须被拒绝或置 flag"""
import io
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures-synthetic")
PY = sys.executable
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


def run_validator(schema, instance_path):
    return subprocess.run(
        [PY, os.path.join(ROOT, "tools", "validate_schema.py"),
         "--schema", os.path.join(ROOT, "contracts", schema),
         "--instance", str(instance_path)],
        capture_output=True, text=True, encoding="utf-8", env=ENV)


def run_redflag(out_path, against):
    return subprocess.run(
        [PY, os.path.join(ROOT, "tools", "redflag.py"),
         "--output", str(out_path)] + ["--against"] + list(against),
        capture_output=True, text=True, encoding="utf-8", env=ENV)


@pytest.fixture()
def ability_good():
    with io.open(os.path.join(FIX, "abilities", "ability-01.json"), encoding="utf-8") as f:
        return json.load(f)


def _write(tmp_path, obj):
    p = tmp_path / "case.json"
    with io.open(str(p), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return p


def test_score_over_100_rejected(tmp_path, ability_good):
    ability_good["baseline"] = 120
    r = run_validator("ability-profile.schema.json", _write(tmp_path, ability_good))
    assert r.returncode == 1 and "INVALID" in r.stdout


def test_plan_six_items_rejected(tmp_path, ability_good):
    ability_good["plan"] = ability_good["plan"][:6]
    r = run_validator("ability-profile.schema.json", _write(tmp_path, ability_good))
    assert r.returncode == 1


def test_plan_duplicate_day_rejected(tmp_path, ability_good):
    ability_good["plan"][1]["day"] = 1
    r = run_validator("ability-profile.schema.json", _write(tmp_path, ability_good))
    assert r.returncode == 1
    assert "重复" in r.stdout


def test_plan_minutes_out_of_range_rejected(tmp_path, ability_good):
    ability_good["plan"][0]["minutes"] = 60
    r = run_validator("ability-profile.schema.json", _write(tmp_path, ability_good))
    assert r.returncode == 1


def test_plan_missing_artifact_rejected(tmp_path, ability_good):
    del ability_good["plan"][0]["artifact"]
    r = run_validator("ability-profile.schema.json", _write(tmp_path, ability_good))
    assert r.returncode == 1


def test_answer_quote_not_substring_rejected(tmp_path):
    turn = {
        "turn_id": 1, "question": "q", "targets": ["t"], "answer": "我的回答是 A 和 B。",
        "answer_quote": "原文里没有这句话", "missing_elements": [], "follow_up": None,
        "asr_confidence": None,
        "subscores": {"structure": 50, "relevance": 50, "specificity": 50, "followup_adaptation": 50, "clarity": 50},
    }
    r = run_validator("interview-turn.schema.json", _write(tmp_path, turn))
    assert r.returncode == 1
    assert "子串" in r.stdout


def test_missing_required_field_rejected(tmp_path):
    bad = {"version": "1.0", "pii_removed": True}  # 缺 subscores/suggestions
    r = run_validator("resume-profile.schema.json", _write(tmp_path, bad))
    assert r.returncode == 1


def _load_resume_profile():
    with io.open(os.path.join(FIX, "resumes", "resume-01-swe.expected.json"), encoding="utf-8") as f:
        return json.load(f)


def test_redflag_blocks_fabricated_number(tmp_path):
    """模型输出中注入语料外数字 → 必须 block_release:true 且退出码 1"""
    profile = _load_resume_profile()
    profile["suggestions"][0]["suggestion"] += "（曾将系统稳定性提升 99.99%）"  # 语料外数字
    out = _write(tmp_path, profile)
    r = run_redflag(out, [os.path.join(FIX, "resumes", "resume-01-swe.txt")])
    assert r.returncode == 1, r.stdout
    report = json.loads(r.stdout)
    assert report["block_release"] is True
    assert any(x["value"] == "99.99" for x in report["red"])


def test_redflag_placeholder_number_allowed(tmp_path):
    """「待用户核实：」前缀的占位数字不阻断"""
    profile = _load_resume_profile()
    profile["suggestions"][0]["rewrite_draft"] += "，留存待用户核实：提升30%"
    out = _write(tmp_path, profile)
    r = run_redflag(out, [os.path.join(FIX, "resumes", "resume-01-swe.txt")])
    assert r.returncode == 0, r.stdout


def test_redflag_clean_output_passes():
    r = run_redflag(os.path.join(FIX, "resumes", "resume-01-swe.expected.json"),
                    [os.path.join(FIX, "resumes", "resume-01-swe.txt")])
    assert r.returncode == 0, r.stdout


def test_redflag_ability_clean_with_full_corpus():
    """聚合产物对上游合同语料 + scoring.md 校验：派生数字可回指则通过"""
    r = run_redflag(os.path.join(FIX, "abilities", "ability-01.json"),
                    [os.path.join(FIX, "resumes", "resume-01-swe.expected.json"),
                     os.path.join(FIX, "jobs", "job-01-swe.expected.json"),
                     os.path.join(FIX, "interviews", "interview-01.json"),
                     os.path.join(ROOT, "contracts", "scoring.md")])
    assert r.returncode == 0, r.stdout


def test_job04_injection_quote_flagged():
    """注入文本必须可在 JobProfile 中置 flag（契约层验证）"""
    with io.open(os.path.join(FIX, "jobs", "job-04-injection.expected.json"), encoding="utf-8") as f:
        data = json.load(f)
    assert data["prompt_injection_flags"], "注入未被标记"
    r = run_validator("job-profile.schema.json",
                      os.path.join(FIX, "jobs", "job-04-injection.expected.json"))
    assert r.returncode == 0
