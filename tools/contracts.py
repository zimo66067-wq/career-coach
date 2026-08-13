# -*- coding: utf-8 -*-
"""Shared validation contracts (phase 5).

Resume/job profile JSON schema validators plus cross-module constants that
were previously defined in api/index.py.
"""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

MIN_TEXT_CHARS = 20
MAX_TEXT_CHARS = 200_000

SUBSCORE_DEFAULTS = {
    "structure": "结构完整度",
    "clarity": "表达清晰度",
    "achievement_evidence": "成果证据",
    "skill_evidence": "技能证据",
    "ats_readability": "ATS 可读性",
}

with (REPOSITORY_ROOT / "contracts" / "resume-profile.schema.json").open(
    encoding="utf-8"
) as schema_file:
    RESUME_PROFILE_VALIDATOR = Draft202012Validator(json.load(schema_file))

with (REPOSITORY_ROOT / "contracts" / "job-profile.schema.json").open(
    encoding="utf-8"
) as schema_file:
    JOB_PROFILE_VALIDATOR = Draft202012Validator(json.load(schema_file))
