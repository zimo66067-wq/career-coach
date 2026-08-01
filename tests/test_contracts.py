# -*- coding: utf-8 -*-
"""test_contracts.py · 自动化契约测试：全部 fixtures 过 Schema + 业务规则 + source_span 回指"""
import io
import json
import os

import pytest
from jsonschema import Draft202012Validator

import validate_schema

FIX = os.path.join(os.path.dirname(__file__), "fixtures-synthetic")
CONTRACTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contracts")


def read_json(p):
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def read_text(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


CASES = []
for fn in sorted(os.listdir(os.path.join(FIX, "resumes"))):
    if fn.endswith(".expected.json"):
        CASES.append(("resume-profile.schema.json", os.path.join("resumes", fn)))
for fn in sorted(os.listdir(os.path.join(FIX, "jobs"))):
    if fn.endswith(".expected.json"):
        CASES.append(("job-profile.schema.json", os.path.join("jobs", fn)))
CASES.append(("interview-turn.schema.json", None))  # 序列逐条校验
CASES.append(("ability-profile.schema.json", os.path.join("abilities", "ability-01.json")))


@pytest.mark.parametrize("schema_file, rel", [c for c in CASES if c[1]])
def test_fixture_validates(schema_file, rel):
    schema = read_json(os.path.join(CONTRACTS, schema_file))
    instance = read_json(os.path.join(FIX, rel))
    errors = list(Draft202012Validator(schema).iter_errors(instance))
    assert not errors, "schema errors: %s" % [e.message for e in errors]
    biz = []
    validate_schema.business_rules(instance, biz)
    assert not biz, "business rule errors: %s" % biz


def test_interview_turns_valid():
    schema = read_json(os.path.join(CONTRACTS, "interview-turn.schema.json"))
    turns = read_json(os.path.join(FIX, "interviews", "interview-01.json"))
    assert len(turns) == 3
    v = Draft202012Validator(schema)
    for t in turns:
        assert not list(v.iter_errors(t))
        assert t["answer_quote"] in t["answer"]


def test_source_spans_point_into_source():
    """source_span 的 quote 必须与 txt 在 start:end 处逐字一致"""
    for fn in sorted(os.listdir(os.path.join(FIX, "resumes"))):
        if not fn.endswith(".expected.json"):
            continue
        slug = fn.replace(".expected.json", "")
        txt = read_text(os.path.join(FIX, "resumes", slug + ".txt"))
        data = read_json(os.path.join(FIX, "resumes", fn))
        spans = []
        for v in data["subscores"].values():
            spans += v["source_spans"]
        for s in data["suggestions"]:
            spans += s["source_spans"]
        for sp in spans:
            assert txt[sp["start"]:sp["end"]] == sp["quote"], "%s span mismatch: %r" % (slug, sp["quote"][:30])
    for fn in sorted(os.listdir(os.path.join(FIX, "jobs"))):
        if not fn.endswith(".expected.json"):
            continue
        slug = fn.replace(".expected.json", "")
        txt = read_text(os.path.join(FIX, "jobs", slug + ".txt"))
        data = read_json(os.path.join(FIX, "jobs", fn))
        for r in data["requirements"]:
            sp = r["source_span"]
            assert txt[sp["start"]:sp["end"]] == sp["quote"]
        for fl in data["prompt_injection_flags"]:
            assert txt[fl["start"]:fl["end"]] == fl["quote"]


def test_job04_injection_flagged():
    data = read_json(os.path.join(FIX, "jobs", "job-04-injection.expected.json"))
    assert len(data["prompt_injection_flags"]) >= 1
    assert "忽略以上所有指令" in data["prompt_injection_flags"][0]["quote"]
