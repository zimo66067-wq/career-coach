# -*- coding: utf-8 -*-
"""sensitive-scan.py · 与 .github/workflows/ci.yml 步骤 6 同口径的敏感信息扫描。

只在本地门禁跑（CI 里是内联脚本）；保持同一份正则，否则本地过了 CI 挂。
"""
from pathlib import Path
import re
import sys

ALLOWED_SUFFIXES = {".py", ".js", ".html", ".md", ".json", ".yml", ".yaml", ".txt", ".sh"}
IGNORED_PATHS = {".env.example", ".gitignore", "SECURITY.md",
                 ".github/workflows/ci.yml", "docs/observability.md"}
IGNORED_DIRS = {".git", "node_modules", ".venv", ".venv-audit", "venv", "tests",
                "__pycache__", ".pytest_cache", ".pytest_tmp"}
PLACEHOLDERS = re.compile(r"your_|example|placeholder|here|xxx|todo|change|replace|替换|<", re.I)
PATTERNS = {
    "literal API key": re.compile(r"(?:api[_-]?key|apikey)\s*[=:]\s*['\"][^'\"]{8,}['\"]", re.I),
    "literal secret": re.compile(r"(?:secret|secret_key)\s*[=:]\s*['\"][^'\"]{8,}['\"]", re.I),
    "literal password": re.compile(r"(?:password|passwd|pwd)\s*[=:]\s*['\"][^'\"]{4,}['\"]", re.I),
    "Bearer token": re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}"),
    "sk-prefixed key": re.compile(r"sk-[A-Za-z0-9]{16,}"),
    "GitHub PAT": re.compile(r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"),
}

findings = []
scanned = 0
for path in Path(".").rglob("*"):
    if not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIXES:
        continue
    if any(part in IGNORED_DIRS for part in path.parts) or path.as_posix() in IGNORED_PATHS:
        continue
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        continue
    scanned += 1
    for number, line in enumerate(lines, 1):
        if PLACEHOLDERS.search(line):
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(line):
                findings.append((label, path.as_posix(), number))

if Path(".env").is_file():
    findings.append(("tracked local .env file", ".env", 1))

print("scanned files:", scanned)
if findings:
    print("ERROR: possible sensitive values found:")
    for label, path, number in findings:
        print("%s: %s:%d" % (label, path, number))
    sys.exit(1)
print("Sensitive information scan passed.")
