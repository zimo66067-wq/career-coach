# -*- coding: utf-8 -*-
"""test_log_sanitize.py · 日志脱敏测试

测试:
  1. PII 脱敏（手机号/邮箱/身份证）
  2. 凭据脱敏（Bearer/API Key/JWT）
  3. 管道模式（stdin/stdout）
"""
import io
import os
import subprocess
import sys

import pytest

from log_sanitize import sanitize, RE_PHONE, RE_EMAIL, RE_ID, RE_BEARER, RE_APIKEY, RE_JWT

TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")


class TestPIISanitize:

    def test_phone_redacted(self):
        """手机号脱敏"""
        text = "联系电话 13800138000 请回拨"
        result = sanitize(text)
        assert "13800138000" not in result
        assert "[REDACTED_PHONE]" in result

    def test_email_redacted(self):
        """邮箱脱敏"""
        text = "发送到 test@example.com 即可"
        result = sanitize(text)
        assert "test@example.com" not in result
        assert "[REDACTED_EMAIL]" in result

    def test_id_card_redacted(self):
        """身份证号脱敏"""
        text = "身份证号 110101199001011234"
        result = sanitize(text)
        assert "110101199001011234" not in result
        assert "[REDACTED_ID]" in result

    def test_name_field_redacted(self):
        """姓名字段脱敏"""
        text = "姓名：张三\n姓名: 李四"
        result = sanitize(text)
        assert "[REDACTED_NAME]" in result

    def test_multiple_pii_in_one_line(self):
        """一行包含多种 PII 同时脱敏"""
        text = "张三 13800138000 test@example.com 110101199001011234"
        result = sanitize(text)
        assert "13800138000" not in result
        assert "test@example.com" not in result
        assert "110101199001011234" not in result

    def test_no_false_positive_on_short_numbers(self):
        """短数字不误脱敏"""
        text = "订单号 12345 状态码 200"
        result = sanitize(text)
        assert "12345" in result
        assert "200" in result


class TestCredentialSanitize:

    def test_bearer_token_redacted(self):
        """Bearer token 脱敏"""
        text = 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test_payload.signature123'
        result = sanitize(text)
        assert "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        # JWT 整体也可能被脱敏
        assert result.count("[REDACTED") >= 1

    def test_api_key_redacted(self):
        """API Key 脱敏"""
        text = 'api_key=sk-abcdefghijklmnop1234567890'
        result = sanitize(text)
        assert "sk-abcdefghijklmnop1234567890" not in result
        assert "[REDACTED_KEY]" in result

    def test_access_key_redacted(self):
        """access_key 脱敏"""
        text = 'access_key: AKIAIOSFODNN7EXAMPLE'
        result = sanitize(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "[REDACTED_KEY]" in result

    def test_secret_key_redacted(self):
        """secret_key 脱敏"""
        text = 'secret_key="mySecretKey12345678"'
        result = sanitize(text)
        assert "mySecretKey12345678" not in result
        assert "[REDACTED_KEY]" in result

    def test_jwt_redacted(self):
        """JWT token 脱敏"""
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        text = "token: %s" % jwt
        result = sanitize(text)
        assert jwt not in result
        assert "[REDACTED_JWT]" in result

    def test_bearer_with_different_case(self):
        """Bearer 大小写不敏感"""
        text = 'bearer abcdefghij1234567890'
        result = sanitize(text)
        assert "abcdefghij1234567890" not in result


class TestPipelineMode:

    def test_stdin_stdout_pipe(self):
        """管道模式: stdin -> stdout"""
        proc = subprocess.run(
            [sys.executable, os.path.join(TOOLS_DIR, "log_sanitize.py")],
            input="phone 13800138000".encode("utf-8"),
            capture_output=True,
            timeout=10,
        )
        assert proc.returncode == 0
        output = proc.stdout.decode("utf-8")
        assert "13800138000" not in output
        assert "[REDACTED_PHONE]" in output

    def test_file_in_file_out(self, tmp_path):
        """文件模式: --input -> --output"""
        in_file = tmp_path / "dirty.log"
        out_file = tmp_path / "clean.log"
        in_file.write_text("电话 13912345678 邮箱 a@b.com", encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, os.path.join(TOOLS_DIR, "log_sanitize.py"),
             "--input", str(in_file), "--output", str(out_file)],
            capture_output=True,
            timeout=10,
        )
        assert proc.returncode == 0
        cleaned = out_file.read_text(encoding="utf-8")
        assert "13912345678" not in cleaned
        assert "a@b.com" not in cleaned
        assert "[REDACTED_PHONE]" in cleaned
        assert "[REDACTED_EMAIL]" in cleaned

    def test_clean_text_passthrough(self):
        """无 PII 文本原样通过"""
        text = "这是一条正常日志，没有敏感信息"
        result = sanitize(text)
        assert result == text
