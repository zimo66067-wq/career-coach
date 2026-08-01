# -*- coding: utf-8 -*-
"""log_sanitize.py · 日志脱敏管道（WF 日志落盘前必经，见 docs/privacy.md 第4节）

用法:
  type app.log | python tools/log_sanitize.py > app.clean.log
  python tools/log_sanitize.py --input app.log --output app.clean.log

规则:
  - 复用 deidentify 的 PII 规则（姓名/手机号/邮箱/身份证）
  - 追加：token / AK-SK / Bearer / api_key 等凭据模式
"""
import argparse
import io
import re
import sys

RE_PHONE = re.compile(r"1[3-9]\d{9}")
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RE_ID = re.compile(r"\d{17}[\dXx]")
RE_NAME_FIELD = re.compile(r"(姓\s*名\s*[:：]\s*)([\u4e00-\u9fa5·]{2,4})")
RE_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}")
RE_APIKEY = re.compile(r"(?i)((?:api[_-]?key|access[_-]?key|secret[_-]?key|token|ak|sk)\s*[:=]\s*[\"']?)[A-Za-z0-9._\-]{8,}")
RE_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")


def sanitize(text):
    text = RE_ID.sub("[REDACTED_ID]", text)
    text = RE_PHONE.sub("[REDACTED_PHONE]", text)
    text = RE_EMAIL.sub("[REDACTED_EMAIL]", text)
    text = RE_NAME_FIELD.sub(lambda m: m.group(1) + "[REDACTED_NAME]", text)
    text = RE_JWT.sub("[REDACTED_JWT]", text)
    text = RE_BEARER.sub(lambda m: m.group(1) + "[REDACTED_TOKEN]", text)
    text = RE_APIKEY.sub(lambda m: m.group(1) + "[REDACTED_KEY]", text)
    return text


def main():
    ap = argparse.ArgumentParser(description="日志脱敏管道")
    ap.add_argument("--input", default=None)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    if args.input:
        text = io.open(args.input, encoding="utf-8", errors="replace").read()
    else:
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace")

    cleaned = sanitize(text)

    if args.output:
        with io.open(args.output, "w", encoding="utf-8") as f:
            f.write(cleaned)
        print("[log_sanitize] OK %s -> %s" % (args.input, args.output), file=sys.stderr)
    else:
        sys.stdout.write(cleaned)


if __name__ == "__main__":
    main()
