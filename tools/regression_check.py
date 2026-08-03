# -*- coding: utf-8 -*-
"""职跃AI 前端严格回归：四档视口 × 五页 × 五态，真实渲染检查"""
import json, os, sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8932"
OUT = r"C:\Users\Administrator\WorkBuddy\2026-08-03-14-14-45\cc-fresh\deliverables\regression"
os.makedirs(OUT, exist_ok=True)

PAGES = ["index.html", "pages/f1-resume.html", "pages/f2-match.html",
         "pages/f3-interview.html", "pages/f4-report.html", "pages/states.html"]
VIEWPORTS = [375, 768, 1024, 1440]
STATES = ["empty", "processing", "success", "error", "degraded"]

report = {"overflow": [], "console_errors": [], "touch": [], "state_view": [],
          "mock": [], "focus": [], "reduced_motion": [], "voice_fallback": [], "contrast": []}

JS_OVERFLOW = """() => {
  const de = document.documentElement;
  const over = de.scrollWidth - de.clientWidth;
  let culprits = [];
  if (over > 0) {
    document.querySelectorAll('*').forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.width > de.clientWidth + 1 && culprits.length < 5)
        culprits.push(el.tagName + '.' + (el.className && el.className.baseVal === undefined ? String(el.className).split(' ')[0] : ''));
    });
  }
  return {over, culprits};
}"""

JS_TOUCH = """() => {
  const bad = [];
  document.querySelectorAll('a, button, .btn, input, textarea, [role=button]').forEach(el => {
    if (el.offsetParent === null) return;
    const r = el.getBoundingClientRect();
    if (r.height > 0 && r.height < 24 && bad.length < 8)
      bad.push((el.tagName) + ':' + (el.textContent||'').trim().slice(0,12) + ' h=' + Math.round(r.height));
  });
  return bad;
}"""

JS_STATE_VIEW = """(want) => {
  const body = document.body.getAttribute('data-state');
  const vis = [];
  document.querySelectorAll('[data-state-view]').forEach(el => {
    if (getComputedStyle(el).display !== 'none') vis.push(el.getAttribute('data-state-view'));
  });
  return {body, vis};
}"""

JS_MOCK = """() => ({
  APP: typeof window.APP !== 'undefined' && typeof window.APP.getState === 'function',
  MOCK: typeof window.MOCK !== 'undefined',
  DataBridge: typeof window.DataBridge !== 'undefined'
})"""

JS_FOCUS = """() => new Promise(res => {
  const els = [...document.querySelectorAll('a, button, .btn, input, textarea')].filter(e => e.offsetParent !== null);
  if (!els.length) return res({ok: false, why: 'no focusable'});
  const el = els[Math.min(2, els.length - 1)];
  el.focus();
  const cs = getComputedStyle(el);
  const hasRing = cs.boxShadow !== 'none' || cs.outlineStyle !== 'none';
  res({ok: hasRing, el: el.tagName, boxShadow: cs.boxShadow.slice(0, 60)});
})"""

JS_RM = """() => {
  const el = document.querySelector('.ai-orb') || document.querySelector('.skel') || document.body;
  const cs = getComputedStyle(el);
  return {animDur: cs.animationDuration, transDur: cs.transitionDuration};
}"""

JS_CONTRAST = """() => {
  function lum(c) {
    const m = c.match(/[\\d.]+/g).map(Number);
    const f = v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
    return 0.2126*f(m[0]) + 0.7152*f(m[1]) + 0.0722*f(m[2]);
  }
  function eff(el) { // 有效背景：向上找非透明
    let e = el;
    while (e && e !== document.documentElement) {
      const bg = getComputedStyle(e).backgroundColor;
      if (bg && !bg.includes('0, 0, 0, 0') && !bg.endsWith(', 0)')) return bg;
      e = e.parentElement;
    }
    return 'rgb(247, 246, 244)';
  }
  const out = [];
  document.querySelectorAll('p, h1, h3, .badge, .page-sub, .subbar .meta, .who').forEach(el => {
    if (el.offsetParent === null || !el.textContent.trim()) return;
    const cs = getComputedStyle(el);
    const fg = cs.color, bg = eff(el);
    const L1 = lum(fg), L2 = lum(bg);
    const ratio = (Math.max(L1,L2)+0.05) / (Math.min(L1,L2)+0.05);
    const sz = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700;
    const need = (sz >= 18 || (sz >= 14 && bold)) ? 3.0 : 4.5;
    if (ratio < need && out.length < 10)
      out.push(el.tagName + '.' + String(el.className).split(' ')[0] + ' ' + ratio.toFixed(2) + ':1 need ' + need + ' "' + el.textContent.trim().slice(0,16) + '"');
  });
  return out;
}"""

def check(pw):
    browser = pw.chromium.launch()
    for page_path in PAGES:
        name = page_path.replace("pages/", "").replace(".html", "") or "index"
        for w in VIEWPORTS:
            ctx = browser.new_context(viewport={"width": w, "height": 900})
            pg = ctx.new_page()
            errors = []
            pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: errors.append(str(e)))
            url = f"{BASE}/{page_path}"
            pg.goto(url, wait_until="networkidle", timeout=20000)
            pg.wait_for_timeout(600)
            key = f"{name}@{w}"
            ov = pg.evaluate(JS_OVERFLOW)
            if ov["over"] > 0:
                report["overflow"].append({"page": key, "over": ov["over"], "culprits": ov["culprits"]})
            tc = pg.evaluate(JS_TOUCH)
            if tc:
                report["touch"].append({"page": key, "items": tc})
            if errors:
                report["console_errors"].append({"page": key, "errors": errors[:5]})
            if w == 375:
                pg.screenshot(path=os.path.join(OUT, f"{name}-375.png"), full_page=False)
            if w == 1440:
                pg.screenshot(path=os.path.join(OUT, f"{name}-1440.png"), full_page=False)
            ctx.close()
        # 五态 + 功能检查（1280 宽度）
        if name in ("f1-resume", "f2-match", "f3-interview", "f4-report"):
            for st in STATES:
                ctx = browser.new_context(viewport={"width": 1280, "height": 900})
                pg = ctx.new_page()
                pg.goto(f"{BASE}/{page_path}?state={st}", wait_until="networkidle", timeout=20000)
                pg.wait_for_timeout(400)
                sv = pg.evaluate(JS_STATE_VIEW, st)
                ok = sv["body"] == st and sv["vis"] == [st]
                if not ok:
                    report["state_view"].append({"page": name, "state": st, "got": sv})
                pg.screenshot(path=os.path.join(OUT, f"{name}-{st}.png"), full_page=False)
                ctx.close()
            # 功能钩子 / 焦点 / MOCK / 语音回退
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            pg = ctx.new_page()
            pg.goto(f"{BASE}/{page_path}?state=success", wait_until="networkidle", timeout=20000)
            pg.wait_for_timeout(500)
            report["mock"].append({"page": name, **pg.evaluate(JS_MOCK)})
            report["focus"].append({"page": name, **(pg.evaluate(JS_FOCUS))})
            report["contrast"].append({"page": name, "issues": pg.evaluate(JS_CONTRAST)})
            if name == "f3-interview":
                ind = pg.eval_on_selector("#voice-state-indicator", "el => el.textContent")
                cls = pg.eval_on_selector("#voice-state-indicator", "el => el.className")
                mic_disabled = pg.eval_on_selector("#micBtn", "el => el.classList.contains('disabled')")
                report["voice_fallback"].append({"indicator": ind, "class": cls, "mic_disabled": mic_disabled})
            ctx.close()
            # reduced-motion
            ctx = browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
            pg = ctx.new_page()
            pg.goto(f"{BASE}/{page_path}?state=processing", wait_until="networkidle", timeout=20000)
            pg.wait_for_timeout(300)
            report["reduced_motion"].append({"page": name, **pg.evaluate(JS_RM)})
            ctx.close()
    browser.close()

with sync_playwright() as pw:
    check(pw)

print(json.dumps(report, ensure_ascii=False, indent=1)[:3900])
