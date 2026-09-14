# -*- coding: utf-8 -*-
"""test_deidentify.py · 合成简历脱敏后无 PII 残留"""
import re
import time

import deidentify

RE_PHONE = re.compile(r"1[3-9]\d{9}")
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RE_ID = re.compile(r"\d{17}[\dXx]")
RE_NAME_FIELD = re.compile(r"姓\s*名\s*[:：]\s*[\u4e00-\u9fa5·]{2,4}")


def test_all_resumes_deidentified(resume_txts):
    assert len(resume_txts) >= 20
    for fn, text in resume_txts.items():
        cleaned, mapping = deidentify.deidentify(text)
        assert not RE_PHONE.search(cleaned), "%s 手机号残留" % fn
        assert not RE_EMAIL.search(cleaned), "%s 邮箱残留" % fn
        assert not RE_ID.search(cleaned), "%s 身份证残留" % fn
        assert not RE_NAME_FIELD.search(cleaned), "%s 姓名字段残留" % fn
        # 预脱敏简历（pii_removed:true）mapping 可能为空，仅检查有 PII 的简历
        if "pii_removed:true" not in text:
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


# ------------------------------------------------------------------ #
# 复杂度回归：邮箱规则不得退化为二次复杂度
# ------------------------------------------------------------------ #

def test_long_resume_text_is_processed_in_linear_time():
    """回归：`[A-Za-z0-9._%+-]+@` 曾是二次复杂度。

    简历正文上限是 20 万字符（见 tests/test_api_boundary.py 的
    test_text_maximum_length_accepted，该用例断言 200_000 字必须被接受），而
    脱敏是 WF-01 的必经环节。未限长时 20 万字符要 ~100 秒 —— 一次**合法**上传就能
    把请求线程占满。这里用前瞻 + RFC 长度上限把它压成线性。

    阈值取得很松（3 秒），只用于拦住复杂度回退，不是性能基准；修复后实测约 10ms。
    """
    big = "a" * 200_000
    started = time.perf_counter()
    cleaned, _ = deidentify.deidentify(big)
    elapsed = time.perf_counter() - started

    assert cleaned == big, "无 PII 的长文本不应被改写"
    assert elapsed < 3.0, "20 万字符耗时 %.1f 秒，疑似退化为二次复杂度" % elapsed


def test_email_redaction_still_matches_after_the_linearisation():
    """加前瞻后不能漏掉真实邮箱，也不能把普通文本当邮箱。"""
    should_match = [
        "foo@bar.com",
        "zhang.san+job@sub.example.co.uk",
        "前缀xxxxfoo@bar.com 结尾",   # 从「局部段起点」开始匹配
        "a@b.co",
    ]
    for text in should_match:
        cleaned, _ = deidentify.deidentify(text)
        assert "[REDACTED_EMAIL]" in cleaned, "漏掉邮箱：%s -> %s" % (text, cleaned)

    should_not_match = [
        "没有邮箱的一段中文简历内容",
        "不是邮箱的 at 符号 a @ b",
        "邮箱空缺：@",
    ]
    for text in should_not_match:
        cleaned, _ = deidentify.deidentify(text)
        assert "[REDACTED_EMAIL]" not in cleaned, "误伤：%s -> %s" % (text, cleaned)
