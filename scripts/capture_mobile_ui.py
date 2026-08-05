#!/usr/bin/env python3
"""capture_mobile_ui.py · 移动端视口截图（G8/P1-09 证据）

以 375x812（iPhone 尺寸）打开 docs/ 发布镜像各页面并截图，
同时记录页面 JS 错误，供移动端适配与无障碍检查使用。

用法:
  python scripts/capture_mobile_ui.py
"""
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "deliverables" / ("mobile-screenshots-%s" % datetime.now().strftime("%Y%m%d"))
SHOTS.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("index", "index.html"),
    ("f1-resume", "pages/f1-resume.html"),
    ("f2-match", "pages/f2-match.html"),
    ("f3-interview", "pages/f3-interview.html"),
    ("f4-report", "pages/f4-report.html"),
    ("states", "pages/states.html"),
]


def main():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 375, "height": 812})
        page.on("pageerror", lambda exc: errors.append("pageerror: %s" % exc))
        page.on("console", lambda msg: errors.append("console: %s" % msg.text) if msg.type == "error" else None)
        for name, rel in PAGES:
            url = (ROOT / "docs" / rel).as_uri()
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(500)
            out = SHOTS / ("%s-375.png" % name)
            page.screenshot(path=str(out), full_page=True)
            print("  %s" % out.name)
            # 降级态（仅功能页）
            if name.startswith("f") and name != "index":
                page.goto(url + "?demo=1&state=degraded", wait_until="networkidle")
                page.wait_for_timeout(500)
                out = SHOTS / ("%s-degraded-375.png" % name)
                page.screenshot(path=str(out), full_page=True)
                print("  %s" % out.name)
        browser.close()
    print("截图目录: %s" % SHOTS)
    print("JS 错误数: %d" % len(errors))
    for e in errors[:10]:
        print("  - %s" % e[:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
