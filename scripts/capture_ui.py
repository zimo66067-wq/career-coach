#!/usr/bin/env python3
"""截取 UI 原型 6 个页面截图"""
from playwright.sync_api import sync_playwright
from pathlib import Path
import time

PROJECT = Path(__file__).resolve().parent.parent
UI_DIR = PROJECT / "ui" / "prototype"
SHOTS_DIR = PROJECT / "deliverables" / "wf-evidence-20260803" / "screenshots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

pages = [
    ("homepage", UI_DIR / "index.html"),
    ("f1-resume", UI_DIR / "pages" / "f1-resume.html"),
    ("f2-match", UI_DIR / "pages" / "f2-match.html"),
    ("f3-interview", UI_DIR / "pages" / "f3-interview.html"),
    ("f4-report", UI_DIR / "pages" / "f4-report.html"),
    ("states", UI_DIR / "pages" / "states.html"),
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})

    for name, html_path in pages:
        url = f"file:///{str(html_path).replace(chr(92), '/')}"
        page.goto(url, wait_until="networkidle")
        time.sleep(1)
        out = SHOTS_DIR / f"{name}.png"
        page.screenshot(path=str(out), full_page=True)
        print(f"  {name}.png  ({out.stat().st_size // 1024} KB)")

    browser.close()

print(f"\n{len(pages)} screenshots saved to {SHOTS_DIR}")
