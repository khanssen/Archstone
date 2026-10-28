#!/usr/bin/env python3
"""Check what the live marketplace shows for listings that dropped out of the export.

For every listing present in an earlier snapshot but missing from the latest
one, this opens its product page (https://www.fedramp.gov/marketplace/products/<ID>/)
in headless Chromium and records whether the page exists and what status it
shows. It also records every product-list JSON response the products page
loads, and whether each dropped ID appears in it, so a listing the product
page shows but the list leaves out can be told apart from a fetch problem.

The result is written to --out (JSON) and read by build_page.py, which uses it
as evidence when classifying removals. A failed or partial run keeps any
earlier results for IDs it could not check.

Usage:
  python3 scripts/fedramp/check_dropped.py --raw data/fedramp/raw --out data/fedramp/dropped-checks.json
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LIST_URL = "https://www.fedramp.gov/marketplace/products/"
PAGE_URL = LIST_URL + "{id}/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36 archstonesecurity.com research snapshot")

STATUS_RE = re.compile(r"\b(FedRAMP Authorized|FedRAMP Certified(?: \(In Remediation\))?|FedRAMP In Process|"
                       r"FedRAMP Ready|Legacy FedRAMP Ready|Initial Implementation|"
                       r"Agency Authorization In Process)\b")
ASOF_RE = re.compile(r"\bAs of\s+(\d{1,2}/\d{1,2}/\d{4})")
IMPACT_RE = re.compile(r"\b(Low|Moderate|High|LI-SaaS)\b")
NOT_FOUND_RE = re.compile(r"\b(page not found|not found|404|no longer available|does not exist)\b", re.I)


def load(path: Path) -> list[dict]:
    data = json.loads(gzip.decompress(path.read_bytes()))
    if isinstance(data, dict):
        data = next(v for v in data.values() if isinstance(v, list))
    return data


def controls(raw: Path, n: int = 2) -> dict[str, dict]:
    """A few listings that ARE in the latest export (Certified, with agencies): their pages must come back live,
    or the check itself is not working and its results are discarded."""
    snaps = sorted(raw.glob("products-*.json.gz"))
    prods = [p for p in load(snaps[-1]) if str(p.get("status", "")).startswith("FedRAMP Certified")
             and p.get("agency_authorizations")]
    prods.sort(key=lambda p: -len(p.get("agency_authorizations") or []))
    return {p["id"]: p for p in prods[:n]}


def dropped(raw: Path) -> tuple[str, dict[str, dict]]:
    snaps = sorted(raw.glob("products-*.json.gz"))
    if len(snaps) < 2:
        return "", {}
    current = {p["id"] for p in load(snaps[-1])}
    gone: dict[str, dict] = {}
    for f in snaps[:-1]:
        for p in load(f):
            if p["id"] not in current:
                gone[p["id"]] = p
    return snaps[-1].name, gone


def products_in(data) -> list[dict] | None:
    if isinstance(data, dict):
        data = next((v for v in data.values() if isinstance(v, list)), None)
    if isinstance(data, list) and data and isinstance(data[0], dict) and "id" in data[0] and "status" in data[0]:
        return data
    return None


def check(gone: dict[str, dict], timeout_s: int) -> tuple[dict, list[dict]]:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    results: dict[str, dict] = {}
    lists: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(user_agent=UA)

        # 1. Every product-list response the products page loads.
        page = ctx.new_page()

        def on_list(resp):
            try:
                ctype = resp.headers.get("content-type", "")
                if resp.request.resource_type in ("xhr", "fetch") or "json" in ctype:
                    lists.append({"url": resp.url.split("?")[0], "status": resp.status, "type": ctype[:40], "records": None})
                if "json" not in ctype:
                    return
                prods = products_in(resp.json())
            except Exception:
                return
            if prods:
                lists.pop()
                ids = {str(p.get("id")) for p in prods}
                lists.append({"url": resp.url.split("?")[0], "records": len(prods),
                              "dropped_present": sorted(i for i in gone if i in ids)})
        page.on("response", on_list)
        try:
            page.goto(LIST_URL, wait_until="domcontentloaded", timeout=timeout_s * 1000)
            page.wait_for_load_state("networkidle", timeout=timeout_s * 1000)
        except PWTimeout:
            pass
        page.close()

        # 2. Each dropped listing's own product page.
        for pid, rec in sorted(gone.items()):
            page = ctx.new_page()
            seen_json: dict = {}

            def on_detail(resp, pid=pid, seen_json=seen_json):
                try:
                    if "json" not in resp.headers.get("content-type", ""):
                        return
                    data = resp.json()
                except Exception:
                    return
                cand = data if isinstance(data, dict) else None
                if cand and str(cand.get("id")) == pid:
                    seen_json["rec"] = cand
                    return
                prods = products_in(data)
                if prods:
                    hit = next((p for p in prods if str(p.get("id")) == pid), None)
                    if hit:
                        seen_json["rec"] = hit
            page.on("response", on_detail)
            r = {"checked": today, "url": PAGE_URL.format(id=pid), "http_status": None, "page": "unknown",
                 "page_status": "", "page_as_of": "", "page_impact": "", "name_on_page": False}
            try:
                resp = page.goto(r["url"], wait_until="domcontentloaded", timeout=timeout_s * 1000)
                r["http_status"] = resp.status if resp else None
                try:
                    page.wait_for_load_state("networkidle", timeout=20_000)
                except PWTimeout:
                    pass
                text = page.inner_text("body", timeout=10_000)
                name = str(rec.get("cso") or "")
                r["name_on_page"] = bool(name) and name.lower() in text.lower()
                if seen_json.get("rec"):
                    j = seen_json["rec"]
                    r["page_status"] = str(j.get("status") or "")
                    r["page_impact"] = str(j.get("impact_level") or "")
                    r["page_as_of"] = str(j.get("status_date") or j.get("cert_date") or "")[:10]
                m = STATUS_RE.search(text)
                if m and not r["page_status"]:
                    r["page_status"] = m.group(1)
                m = ASOF_RE.search(text)
                if m and not r["page_as_of"]:
                    mm, dd, yy = m.group(1).split("/")
                    r["page_as_of"] = f"{yy}-{int(mm):02d}-{int(dd):02d}"
                if not r["page_impact"]:
                    m = IMPACT_RE.search(text)
                    r["page_impact"] = m.group(1) if m else ""
                r["title"] = page.title()[:120]
                r["final_url"] = page.url
                r["snippet"] = re.sub(r"\s+", " ", text)[:300]
                # Decide on what the page shows, not the HTTP status: the marketplace is built in the browser
                # and may answer 404 for a product URL and then render the product anyway.
                if r["name_on_page"] or seen_json.get("rec"):
                    r["page"] = "live"
                elif NOT_FOUND_RE.search(text) or not text.strip():
                    r["page"] = "missing"
            except Exception as e:  # keep going; one bad page should not lose the rest
                r["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            results[pid] = r
            print(f"check: {pid} {r['page']} {r['page_status'] or '-'} {r['page_as_of'] or ''}")
            page.close()
        browser.close()
    return results, lists


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--timeout", type=int, default=60)
    args = ap.parse_args()

    snap, gone = dropped(args.raw)
    prior = json.loads(args.out.read_text()) if args.out.exists() else {}
    if not gone:
        print("check: no dropped listings")
        return
    ctl = controls(args.raw)
    results, lists = check({**gone, **ctl}, args.timeout)
    ctl_res = {i: results.pop(i) for i in ctl}
    ok = all(r["page"] == "live" for r in ctl_res.values())
    for i, r in ctl_res.items():
        print(f"check: control {i} ({ctl[i].get('cso')}) -> {r['page']} http {r.get('http_status')}")
    if not ok:
        # The check could not see a listing that is certainly live, so it cannot see anything: mark every result
        # inconclusive rather than record 31 false "missing" findings.
        for r in results.values():
            r["page"] = "unknown"
            r["note"] = "control listing did not load as live; result discarded"
        print("check: controls failed; all results marked unknown")
    listings = prior.get("listings", {})
    for pid, r in results.items():
        if r["page"] == "unknown" and pid in listings and listings[pid].get("page") != "unknown":
            continue   # keep the last conclusive result rather than overwrite it with a failed check
        listings[pid] = r
    out = {"snapshot": snap, "checked": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "controls": ctl_res, "controls_ok": ok,
           "list_responses": lists, "listings": dict(sorted(listings.items()))}
    args.out.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    live = sum(1 for r in results.values() if r["page"] == "live")
    print(f"check: {len(results)} dropped listings checked, {live} with a live product page; "
          f"{len(lists)} product-list responses on the list page")
    if not results:
        sys.exit(1)


if __name__ == "__main__":
    main()
