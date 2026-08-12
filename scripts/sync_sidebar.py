# -*- coding: utf-8 -*-
"""Inject the account sidebar into docs/ and public/ publish trees (idempotent).

Source of truth: ui/prototype markup (sidebar.css, aside, auth modal).
Run after adding/changing the sidebar so both publish mirrors stay in sync.
"""
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREES = [ROOT / "docs", ROOT / "public"]
PAGES = [
    "index.html",
    "pages/f1-resume.html",
    "pages/f2-match.html",
    "pages/f3-interview.html",
    "pages/f4-report.html",
    "pages/states.html",
]

ASIDE = """<aside class="zy-sidebar" id="zySidebar" aria-label="账号与历史记录">
  <div class="zy-sidebar-head">
    <div class="zy-user-card">
      <div class="zy-avatar" id="zyAvatar">访</div>
      <div class="zy-user-meta">
        <div class="zy-user-name" id="zyUserName">未登录游客</div>
        <div class="zy-user-sub" id="zyUserSub">登录后历史可长期保存</div>
        <button class="zy-user-action" id="zyLoginBtn" type="button">登录 / 注册</button>
        <button class="zy-user-action zy-hidden" id="zyLogoutBtn" type="button">退出登录</button>
      </div>
    </div>
  </div>
  <div class="zy-history">
    <div class="zy-history-title"><span>历史检测记录</span><button class="zy-history-clear zy-hidden" id="zyHistoryClear" type="button">清空</button></div>
    <ul class="zy-history-list" id="zyHistoryList"></ul>
    <div class="zy-history-empty" id="zyHistoryEmpty">还没有检测记录<br>完成一次诊断并登录后，记录会自动出现在这里</div>
    <div class="zy-sidebar-demo-note zy-hidden" id="zyDemoNote">· 以下为演示数据 ·</div>
    <button class="zy-add-record zy-hidden" id="zyAddRecord" type="button">＋ 模拟一次检测</button>
  </div>
</aside>
<div class="zy-sidebar-backdrop" id="zySidebarBackdrop"></div>
<div class="zy-modal zy-hidden" id="zyAuthModal" role="dialog" aria-modal="true" aria-labelledby="zyAuthTitle">
  <div class="zy-modal-box">
    <button class="zy-modal-close" id="zyAuthClose" type="button" aria-label="关闭">×</button>
    <h3 id="zyAuthTitle">登录 / 注册</h3>
    <div class="zy-tabs">
      <button class="zy-tab active" data-tab="login" type="button">登录</button>
      <button class="zy-tab" data-tab="register" type="button">注册</button>
    </div>
    <form class="zy-form" id="zyLoginForm">
      <label>手机号或邮箱<input name="account" type="text" placeholder="手机号或邮箱" required></label>
      <label>登录密码<input name="password" type="password" placeholder="登录密码" required></label>
      <button class="zy-btn" type="submit">登 录</button>
    </form>
    <form class="zy-form zy-hidden" id="zyRegisterForm">
      <label>手机号<input name="phone" type="tel" placeholder="11 位手机号" required></label>
      <label>邮箱<input name="email" type="email" placeholder="you@example.com" required></label>
      <label>邮箱密码<input name="emailPwd" type="password" placeholder="设置平台登录密码" required>
        <span class="zy-hint">请设置专用登录密码，勿使用邮箱本身的密码</span>
      </label>
      <label>账户名<input name="name" type="text" placeholder="2-16 个字符，如：小张" required></label>
      <button class="zy-btn" type="submit">注 册</button>
    </form>
    <p class="zy-form-msg" id="zyAuthMsg"></p>
  </div>
</div>
"""


def relative_prefix(page_path):
    return "../" if page_path.parent.name == "pages" else ""


def inject(page_path):
    text = page_path.read_text(encoding="utf-8")
    prefix = relative_prefix(page_path)
    changed = False

    wrong_css = 'href="css/sidebar.css"' if prefix else 'href="../css/sidebar.css"'
    if wrong_css in text:
        text = text.replace(wrong_css, 'href="%scss/sidebar.css"' % prefix, 1)
        changed = True
    elif 'href="%scss/sidebar.css"' % prefix not in text and "sidebar.css" not in text:
        text = text.replace(
            "</head>",
            '<link rel="stylesheet" href="%scss/sidebar.css">\n</head>' % prefix,
            1,
        )
        changed = True

    if 'id="zySidebarToggle"' not in text:
        button = (
            '<button class="zy-sidebar-toggle" id="zySidebarToggle" type="button" '
            'aria-label="切换侧边栏" aria-expanded="true">☰</button>\n  '
        )
        if '<span class="brand">' in text:
            text = text.replace('<span class="brand">', button + '<span class="brand">', 1)
            changed = True
        else:
            text = text.replace('<nav class="topnav"', '<nav class="topnav"\n  ' + button, 1)
            changed = True

    if 'id="zySidebar"' not in text:
        text = text.replace("</body>", ASIDE + '\n<script src="%sjs/account.js"></script>\n</body>' % prefix, 1)
        changed = True
    else:
        wrong = 'src="js/account.js"' if prefix else 'src="../js/account.js"'
        right = 'src="%sjs/account.js"' % prefix
        if wrong in text:
            text = text.replace(wrong, right, 1)
            changed = True
        elif right not in text:
            text = text.replace("</body>", '\n<script src="%sjs/account.js"></script>\n</body>' % prefix, 1)
            changed = True

    if changed:
        page_path.write_text(text, encoding="utf-8")
        print("updated:", page_path)
    else:
        print("already ok:", page_path)


def main():
    for tree in TREES:
        for page in PAGES:
            path = tree / page
            if not path.exists():
                print("missing:", path)
                continue
            inject(path)


if __name__ == "__main__":
    main()
