#!/usr/bin/env python3
"""Download the FedRAMP Marketplace product export and keep it as a dated snapshot.

The marketplace builds its JSON export in the browser, so there is no file URL
to curl. This opens the products page in headless Chromium and takes the
product list one of two ways:

  1. from the page's own network traffic (any JSON response that is the
     product list), or
  2. by clicking Export, then JSON, and saving the download.

A file dropped into data/fedramp/inbox/ is used instead of the browser, which
is the manual fallback if the marketplace changes in a way that breaks both.

A new snapshot is written only when the product list differs from the latest
one already kept. Writes `changed` and `snapshot` to $GITHUB_OUTPUT when run
in Actions.

Usage:
  python3 scripts/fedramp/fetch_marketplace.py --raw data/fedramp/raw --inbox data/fedramp/inbox
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

URL = "https://www.fedramp.gov/marketplace/products/"
MIN_RECORDS = 300
REQUIRED = {"id", "csp", "cso", "status", "cert_type", "agency_authorizations"}


def as_products(data):
    """Return the product list if `data` looks like the marketplace export, else None."""
    if isinstance(data, dict):
        data = next((v for v in data.values() if isinstance(v, list)), None)
    if (isinstance(data, list) and len(data) >= MIN_RECORDS
            and isinstance(data[0], dict) and REQUIRED <= set(data[0])):
        return data
    return None


def canonical(products) -> bytes:
    return json.dumps(sorted(products, key=lambda p: str(p.get("id"))),
                      sort_keys=True, separators=(",", ":")).encode()


def read_any(path: Path):
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return json.loads(raw)


def from_inbox(inbox: Path):
    files = sorted([p for p in inbox.glob("*") if p.suffix in (".json", ".gz")],
                   key=lambda p: p.stat().st_mtime)
    if not files:
        return None, None
    newest = files[-1]
    products = as_products(read_any(newest))
    if products is None:
        sys.exit(f"fetch: {newest} is not a marketplace product export")
    print(f"fetch: using manual export {newest.name}")
    return products, files


def from_browser(url: str, timeout_s: int):
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    found = {}

    def on_response(resp):
        if "products" in found:
            return
        ctype = resp.headers.get("content-type", "")
        if "json" not in ctype and not resp.url.split("?")[0].endswith(".json"):
            return
        try:
            products = as_products(resp.json())
        except Exception:
            return
        if products:
            found["products"] = products
            found["via"] = f"network response {resp.url}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(accept_downloads=True, user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36 archstonesecurity.com research snapshot"))
        page = ctx.new_page()
        page.on("response", on_response)
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
        try:
            page.wait_for_load_state("networkidle", timeout=timeout_s * 1000)
        except PWTimeout:
            pass

        if "products" not in found:
            export = page.get_by_role("button", name=re.compile(r"export", re.I))
            if export.count() == 0:
                export = page.get_by_text(re.compile(r"^\s*export", re.I))
            if export.count() == 0:
                browser.close()
                sys.exit("fetch: no product JSON in network traffic and no Export control on the page")
            export.first.click()
            choice = page.get_by_role("menuitem", name=re.compile(r"json", re.I))
            if choice.count() == 0:
                choice = page.get_by_role("button", name=re.compile(r"json", re.I))
            if choice.count() == 0:
                choice = page.get_by_text(re.compile(r"json", re.I))
            with page.expect_download(timeout=timeout_s * 1000) as dl_info:
                if choice.count():
                    choice.first.click()
            dl = dl_info.value
            tmp = Path(dl.path())
            products = as_products(json.loads(tmp.read_bytes()))
            if products is None:
                browser.close()
                sys.exit(f"fetch: downloaded {dl.suggested_filename} is not a product export")
            found["products"] = products
            found["via"] = f"Export download {dl.suggested_filename}"
        browser.close()
    print(f"fetch: {len(found['products'])} products via {found['via']}")
    return found["products"]


def latest_snapshot(raw: Path):
    snaps = sorted(raw.glob("products-*.json.gz"))
    return snaps[-1] if snaps else None


def emit(**kw):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            for k, v in kw.items():
                f.write(f"{k}={v}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--inbox", type=Path, required=True)
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--url", default=URL, help="products page (override for testing)")
    args = ap.parse_args()
    args.raw.mkdir(parents=True, exist_ok=True)
    args.inbox.mkdir(parents=True, exist_ok=True)

    products, used = from_inbox(args.inbox)
    if products is None:
        products = from_browser(args.url, args.timeout)

    body = canonical(products)
    prev = latest_snapshot(args.raw)
    if prev and canonical(as_products(read_any(prev)) or []) == body:
        print(f"fetch: unchanged since {prev.name}")
        emit(changed="false", snapshot=str(prev))
    else:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dest = args.raw / f"products-{today}.json.gz"
        dest.write_bytes(gzip.compress(json.dumps(products, ensure_ascii=False).encode(), 9, mtime=0))
        print(f"fetch: wrote {dest}")
        emit(changed="true", snapshot=str(dest))

    for f in used or []:
        f.unlink()


if __name__ == "__main__":
    main()
