#!/usr/bin/env python3
"""Copy partials/header.html into every site page.

Static site, no build step: each page carries its own copy of the header so it
works without JavaScript. This script keeps those copies identical. Run it
after editing partials/header.html:

    python scripts/apply-header.py          # rewrite pages
    python scripts/apply-header.py --check  # exit 1 if any page has drifted

A page is in scope if it has a <header class="header ..."> element and is not
under an excluded path. Research exhibits and /research have their own
mastheads and are never touched.
"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PARTIAL = (ROOT / "partials" / "header.html").read_text(encoding="utf-8").rstrip("\n")
SKIP_DIRS = {"Archive", "Content", "HTML Template", "documentation", "app", "owl carousel",
             "partials", "node_modules", ".git", "cui-regulatory-map", "font"}
SKIP_FILES = {"research.html", "v18.html", "index new.html", "test.html", "faqs_new.html"}
SKIP_PREFIXES = ("index-PRODUCTION-BACKUP",)  # backups, not served
# The block we own: from the "Header Start" comment (if any) through </header> and
# the "Header End" comment (if any).
BLOCK = re.compile(
    r'(?:[ \t]*<!--\s*Header Start[^>]*-->\s*)?'
    r'[ \t]*<header class="header[^"]*">.*?</header>'
    r'(?:\s*<!--\s*Header End\s*-->)?',
    re.S)

def pages():
    for p in sorted(ROOT.rglob("*.html")):
        rel = p.relative_to(ROOT)
        if rel.parts[0] in SKIP_DIRS or rel.name in SKIP_FILES or rel.name.startswith(SKIP_PREFIXES):
            continue
        yield p

def main(check):
    drift = []
    for p in pages():
        s = p.read_text(encoding="utf-8")
        m = BLOCK.search(s)
        if not m:
            continue
        if m.group(0) == PARTIAL:
            continue
        drift.append(p.relative_to(ROOT))
        if not check:
            p.write_text(s[:m.start()] + PARTIAL + s[m.end():], encoding="utf-8")
    verb = "out of date" if check else "updated"
    for d in drift:
        print(f"{verb}: {d}")
    print(f"{len(drift)} page(s) {verb}.")
    return 1 if (check and drift) else 0

if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
