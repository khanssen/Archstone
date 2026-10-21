#!/usr/bin/env python3
"""Social preview cards (Open Graph images, 1200x630) for archstonesecurity.com.

Cards are HTML rendered to PNG with headless Chromium (Playwright, already
installed by the marketplace workflow). Fonts and the logo are inlined, so the
card renders the same with no network access.

  python3 scripts/fedramp/og_card.py --default images/og-default.png   # site-wide card
  (the 20x card is written by build_page.py on every rebuild)
"""
from __future__ import annotations

import argparse
import base64
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
W, H = 1200, 630


def _data(path: Path, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def _frame(body: str) -> str:
    font = ROOT / "font"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:Plex;font-weight:400;src:url({_data(font / "IBMPlexSans-Regular.woff2", "font/woff2")}) format("woff2")}}
@font-face{{font-family:Plex;font-weight:600;src:url({_data(font / "IBMPlexSans-SemiBold.woff2", "font/woff2")}) format("woff2")}}
@font-face{{font-family:PlexMono;font-weight:500;src:url({_data(font / "IBMPlexMono-Medium.woff2", "font/woff2")}) format("woff2")}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{W}px;height:{H}px}}
body{{font-family:Plex,sans-serif;color:#1f2a30;background:linear-gradient(to bottom,#fff 0%,#fff 38%,#bdced7 100%);
     border-bottom:10px solid #455359;position:relative;overflow:hidden}}
.logo{{display:block}}
.eyebrow{{font:500 22px/1 PlexMono,monospace;letter-spacing:.14em;text-transform:uppercase;color:#4a5a66}}
</style></head><body>{body}</body></html>"""


def default_card_html() -> str:
    logo = _data(ROOT / "images" / "logo-1200.png", "image/png")
    return _frame(f"""
<div style="position:absolute;inset:0 0 10px 0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:44px">
  <img class="logo" src="{logo}" style="width:820px">
  <div style="font-size:34px;font-weight:600;color:#455359;text-align:center;line-height:1.3">
    Compliance engineering for NIST SP 800-171,<br>FedRAMP and GovRAMP
  </div>
</div>""")


def x20_card_html(title: str, stats: list[tuple[str, str, bool]], footer: str) -> str:
    """stats: (number, label, emphasise)."""
    logo = _data(ROOT / "images" / "logo-1200.png", "image/png")
    cells = "".join(
        f'<div style="flex:{1.7 if len(n) > 3 else 1};min-width:0"><div style="font-size:104px;font-weight:600;line-height:1;'
        f'white-space:nowrap;color:{"#b4441c" if hot else "#1f2a30"}">{html.escape(n)}</div>'
        f'<div style="font-size:26px;line-height:1.25;color:#4a5a66;margin-top:12px">{html.escape(l)}</div></div>'
        for n, l, hot in stats)
    return _frame(f"""
<div style="position:absolute;inset:52px 64px 52px 64px;display:flex;flex-direction:column">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div class="eyebrow">Archstone Security · Research</div>
    <img class="logo" src="{logo}" style="width:250px;margin-top:-14px">
  </div>
  <div style="font-size:56px;font-weight:600;line-height:1.08;margin-top:14px;max-width:880px">{html.escape(title)}</div>
  <div style="display:flex;gap:44px;margin-top:auto">{cells}</div>
  <div style="font-size:22px;color:#4a5a66;margin-top:28px">{html.escape(footer)}</div>
</div>""")


def render_png(card_html: str, out: Path) -> None:
    from playwright.sync_api import sync_playwright   # imported here so build_page works without it
    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H})
        page.set_content(card_html, wait_until="load")
        page.evaluate("document.fonts.ready")
        page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": W, "height": H})
        browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--default", type=Path, required=True, help="where to write the site-wide card")
    args = ap.parse_args()
    render_png(default_card_html(), args.default)
    print(f"og_card: wrote {args.default}")
