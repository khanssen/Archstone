#!/usr/bin/env python3
"""Compare two FedRAMP Marketplace snapshots and write a GitHub issue body.

Product-level, not byte-level: the export changes for reasons that do not
touch the page (event-log wording, descriptions, logos). Only changes that
move a number or a row on /fedramp-20x-adoption/ count as material.

Usage:
  python3 scripts/fedramp/diff_snapshots.py \
      --old data/fedramp/raw/products-2026-10-16.json.gz \
      --new data/fedramp/raw/products-2026-10-21.json.gz \
      --grc data/fedramp/grc-vendors.json \
      --history data/fedramp/history.csv \
      --body issue.md

Writes GITHUB_OUTPUT: material=true|false, headline=true|false, title=...
Exit code is 0 either way; the workflow decides what to do with the outputs.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_page import load_assessors, load_snapshot, normalise, provider_key, snapshot_date  # noqa: E402

PAGE = "https://archstonesecurity.com/fedramp-20x-adoption/"

# Fields whose change moves something on the page.
WATCH = [("status", "Status"), ("csp", "Provider name"), ("cls", "Class"),
         ("impact", "Impact"), ("date", "Authorization date"), ("assessor", "Assessor")]

# history.csv columns, in the order they read best in the issue.
METRICS = [
    ("x20_authorized", "20x authorizations"),
    ("x20_with_agency", "20x with an agency ATO"),
    ("x20_agency_atos", "20x agency ATOs (total)"),
    ("grc_authorized", "GRC-vendor 20x authorizations"),
    ("grc_with_agency", "GRC-vendor 20x with an agency ATO"),
    ("x20_in_process", "20x in process"),
    ("rev5_since_first_20x", "Traditional authorized since first 20x"),
    ("rev5_since_with_agency", "  … of which with an agency ATO"),
    ("x20_removed_total", "20x listings removed (cumulative)"),
]


def label(r: dict) -> str:
    return f'**{r["product"]}** ({r["csp"]})'


def index(path: Path, grc: set[str]) -> dict[str, dict]:
    prods, _ = load_snapshot(path)
    return {p["id"]: normalise(p, grc) for p in prods}


def history_rows(path: Path, old: str, new: str) -> tuple[dict | None, dict | None]:
    if not path or not path.exists():
        return None, None
    with path.open(newline="", encoding="utf-8") as f:
        rows = {r["snapshot"]: r for r in csv.DictReader(f)}
    return rows.get(old), rows.get(new)


def emit(**kw) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            for k, v in kw.items():
                f.write(f"{k}={v}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--old", required=True, type=Path)
    ap.add_argument("--new", required=True, type=Path)
    ap.add_argument("--grc", required=True, type=Path)
    ap.add_argument("--history", type=Path)
    ap.add_argument("--body", required=True, type=Path)
    ap.add_argument("--assessors", type=Path, help="recognized assessor list, so spelling variants don't read as changes")
    args = ap.parse_args()

    load_assessors(args.assessors)
    grc = {provider_key(s) for s in json.loads(args.grc.read_text())["providers"]}
    d_old, d_new = snapshot_date(args.old), snapshot_date(args.new)
    old, new = index(args.old, grc), index(args.new, grc)

    sec: dict[str, list[str]] = {k: [] for k in
                                 ("headline", "agency20", "new20", "changed20", "gone20", "rev5")}

    # ---- 20x track, product by product -------------------------------------
    ids20 = {i for i, r in old.items() if r["track"] == "20x"} | \
            {i for i, r in new.items() if r["track"] == "20x"}
    for i in sorted(ids20, key=lambda i: (new.get(i) or old[i])["product"].lower()):
        o, n = old.get(i), new.get(i)
        if o is None:
            cert = "authorized" if n["certified"] else n["status"]
            sec["new20"].append(f'- {label(n)} — new listing, {cert}'
                                f'{", " + n["cls"] if n["cls"] else ""}'
                                f'{", GRC vendor" if n["grc"] else ""}')
            if n["n_agencies"]:
                sec["agency20"].append(f'- {label(n)} arrives with agencies: {"; ".join(n["agencies"])}')
            continue
        if n is None:
            sec["gone20"].append(f'- {label(o)} — no longer in the export (was {o["status"]}, '
                                 f'{o["n_agencies"]} agency ATO{"s" if o["n_agencies"] != 1 else ""})')
            continue
        if o["cert_type"] != n["cert_type"]:
            sec["changed20"].append(f'- {label(n)} — track label moved {o["cert_type"]} → {n["cert_type"]}')
        if not o["certified"] and n["certified"]:
            sec["changed20"].append(f'- {label(n)} — **newly authorized** {n["date"] or "(no date)"}'
                                    f'{" — GRC vendor" if n["grc"] else ""}')
        for f, name in WATCH:
            if f in ("status", "date") and not o["certified"] and n["certified"]:
                continue
            if o[f] != n[f]:
                note = ""
                if f == "csp" and o["grc"] != n["grc"]:
                    note = " ⚠️ **GRC classification changed** — check `grc-vendors.json`"
                sec["changed20"].append(f'- {label(n)} — {name}: {o[f] or "—"} → {n[f] or "—"}{note}')
        added = [a for a in n["agencies"] if a not in o["agencies"]]
        dropped = [a for a in o["agencies"] if a not in n["agencies"]]
        for a in added:
            tag = " ⚠️ **GRC vendor**" if n["grc"] else ""
            sec["agency20"].append(f'- {label(n)} + **{a}**{tag}')
        for a in dropped:
            sec["agency20"].append(f'- {label(n)} − {a} (removed)')

    # ---- Rev5: counted, not itemised, except new authorizations ------------
    r5_new_auth, r5_agency_moves = [], 0
    for i, n in new.items():
        if n["track"] != "Rev5":
            continue
        o = old.get(i)
        if n["certified"] and (o is None or not o["certified"]):
            r5_new_auth.append(f'- {label(n)} — {n["impact"] or "impact n/a"}, '
                               f'{n["n_agencies"]} agenc{"y" if n["n_agencies"] == 1 else "ies"}'
                               f'{", GRC vendor" if n["grc"] else ""}')
        if o is not None and set(o["agencies"]) != set(n["agencies"]):
            r5_agency_moves += 1
    if r5_new_auth:
        sec["rev5"].append(f"New traditional authorizations ({len(r5_new_auth)}):")
        sec["rev5"] += sorted(r5_new_auth)
    if r5_agency_moves:
        sec["rev5"].append(f"- Agency lists changed on {r5_agency_moves} existing traditional product"
                           f'{"s" if r5_agency_moves != 1 else ""} (moves the "heaviest users of traditional FedRAMP" table)')

    # ---- Headline numbers ---------------------------------------------------
    h_old, h_new = history_rows(args.history, d_old, d_new)
    metric_rows, headline = [], False
    if h_old and h_new:
        for key, name in METRICS:
            a, b = int(h_old[key]), int(h_new[key])
            if a != b:
                metric_rows.append(f"| {name} | {a} | {b} | {b - a:+d} |")
        # Claims written into the page's prose that this change could break.
        ga, gb = int(h_old["grc_with_agency"]), int(h_new["grc_with_agency"])
        if ga == 0 and gb > 0:
            headline = True
            sec["headline"].append("- **A GRC vendor's 20x authorization now has an agency customer.** "
                                   "The lede's \"zero have an agency customer\" is no longer true; "
                                   "the build rewrites the number, but read the surrounding argument.")
        if int(h_new["x20_with_agency"]) > int(h_old["x20_with_agency"]):
            headline = True
            sec["headline"].append("- **A new 20x product has an agency ATO.** Check the "
                                   "\"Which agencies have relied on 20x\" narrative still holds.")

    # Export-wide loss of business categories (the self-declared GRC tag depends on them).
    po, pn = load_snapshot(args.old)[0], load_snapshot(args.new)[0]
    cov = lambda ps: sum(1 for p in ps if p.get("business_categories")) / max(len(ps), 1)
    if cov(pn) < 0.7 * cov(po):
        headline = True
        sec["headline"].insert(0, f"- **The export lost most business categories** ({cov(po):.0%} of listings had one "
                                  f"on {d_old}, {cov(pn):.0%} on {d_new}). The build carries the last known category "
                                  "forward and says so on the page; check whether the marketplace restores them.")

    material = any(sec[k] for k in ("agency20", "new20", "changed20", "gone20", "rev5")) or bool(metric_rows)

    # ---- Body ---------------------------------------------------------------
    out = [f"The FedRAMP Marketplace export changed between **{d_old}** and **{d_new}**. "
           f"The page has already been rebuilt and redeployed from the new snapshot: {PAGE}", ""]
    if not material:
        out.append("No change affects the page — the export differs only in fields this page doesn't use.")
    blocks = [
        ("headline", "⚠️ Claims to re-read"),
        ("agency20", "20x agency ATOs"),
        ("new20", "New 20x listings"),
        ("changed20", "Changed 20x listings"),
        ("gone20", "20x listings no longer in the export"),
        ("rev5", "Traditional FedRAMP"),
    ]
    if metric_rows:
        out += ["### Headline numbers", "", "| Metric | Before | After | Δ |", "|---|--:|--:|--:|",
                *metric_rows, ""]
    for k, title in blocks:
        if sec[k]:
            out += [f"### {title}", "", *sec[k], ""]
    out += ["---",
            f"Snapshots: `{args.old.name}` → `{args.new.name}`. "
            "Opened by `.github/workflows/fedramp-marketplace.yml`. "
            "Close once the page reads correctly; if the export is wrong, say so here and "
            "drop a corrected export in `data/fedramp/inbox/`."]
    args.body.write_text("\n".join(out) + "\n", encoding="utf-8")

    n_items = sum(len(v) for k, v in sec.items() if k != "headline")
    title = (f"20x adoption: marketplace update {d_new}"
             + (" — headline claims changed" if headline else "")
             + (f" ({n_items} change{'s' if n_items != 1 else ''})" if n_items else ""))
    emit(material=str(material).lower(), headline=str(headline).lower(), title=title)
    print(f"diff: {d_old} → {d_new}: material={material} headline={headline} items={n_items}")


if __name__ == "__main__":
    main()
