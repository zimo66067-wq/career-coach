# -*- coding: utf-8 -*-
"""test_deidentify.py · 5 份合成简历脱敏后无 PII 残留"""
import re

import deidentify

RE_PHONE = re.compile(r"1[3-9]\d{9}")
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RE_ID = re.compile(r"\d{17}[\dXx]")
RE_NAME_FIELD = re.compile(r"姓\s*名\s*[:：]\s*[\u4e00-\u9fa5·]{2,4}")


def test_all_resumes_deidentified(resume_txts):
    assert len(resume_txts) == 5
    for fn, text in resume_txts.items():
        cleaned, mapping = deidentify.deidentify(text)
        assert not RE_PHONE.search(cleaned), "%s 手机号残留" % fn
        assert not RE_EMAIL.search(cleaned), "%s 邮箱残留" % fn
        assert not RE_ID.search(cleaned), "%s 身份证残留" % fn
        assert not RE_NAME_FIELD.search(cleaned), "%s 姓名字段残留" % fn
        assert mapping, "%s 应有脱除记录" % fn


def test_scan_residue_clean(resume_txts):
    for fn, text in resume_txts.items():
        cleaned, _ = deidentify.deidentify(text)
        assert deidentify.scan_residue(cleaned) == [], "%s scan_residue 非空" % fn


def test_markers_present(resume_txts):
    sample = list(resume_txts.values())[0]
    cleaned, _ = deidentify.deidentify(sample)
    assert "[REDACTED_PHONE]" in cleaned
    assert "[REDACTED_EMAIL]" in cleaned
