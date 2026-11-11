#!/usr/bin/env python3
"""Freeze the traditional (Rev5) marketplace fields that FedRAMP's export stopped carrying.

From the Nov 3, 2026 export on, the marketplace export lists every impact level as "Unknown",
empties the sponsoring agency, the In Process / Ready statuses and their dates, and drops the
agency ATO list from 129 listings. This script records, for every traditional listing seen in
any snapshot up to the cutoff, the last value each of those fields held, with the snapshot it
came from and that snapshot's SHA-256.

The output (data/fedramp/legacy/rev5-legacy-<cutoff>.json) is written once and committed. The
snapshots it reads cannot change, so neither should it; the script refuses to overwrite an
existing file unless --force is given. build_page.py and build_lookup.py read it with --legacy
and mark every value they take from it.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

# Every field the Nov 3 export emptied, whether or not a page shows it today.
LEGACY_FIELDS = [
    "impact_level", "impact_level_number", "partnering_agency",
    "agency_authorizations", "agency_reuse", "authorization", "reuse",
    "annual_assessment", "cert_date",
    "ready_status", "ready_date",
    "ip_jab_status", "ip_jab_date", "ip_prog_status", "ip_prog_date", "ip_prog_date2",
    "ip_agency_status", "ip_agency_date", "ip_pmo_status", "ip_pmo_date",
    "leveraged_systems", "fedramp_msg", "service_last_90", "all_others", "filter_classes",
]
IDENTITY = ["csp", "cso", "status", "cert_type", "cert_path", "cert_class", "independent_assessor"]
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def empty(v) -> bool:
    return v in (None, "", "Unknown", [], {}, "0", 0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw", required=True, type=Path, help="data/fedramp/raw")
    ap.add_argument("--cutoff", default="2026-11-02", help="last snapshot date before the fields were emptied")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--force", action="store_true", help="overwrite an existing frozen file")
    args = ap.parse_args()

    if args.out.exists() and not args.force:
        sys.exit(f"freeze_legacy: {args.out} exists and is frozen; pass --force to rebuild it")

    snaps = []
    for f in sorted(args.raw.glob("products-*.json.gz")):
        m = DATE_RE.search(f.name)
        if m and m.group(1) <= args.cutoff:
            snaps.append((m.group(1), f))
    if not snaps or snaps[-1][0] != args.cutoff:
        sys.exit(f"freeze_legacy: no snapshot dated {args.cutoff} in {args.raw}")

    sources, products = [], {}
    for date, f in snaps:
        blob = f.read_bytes()
        data = json.loads(gzip.decompress(blob))
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [])
        sha = hashlib.sha256(blob).hexdigest()
        sources.append({"file": f.name, "date": date, "sha256": sha, "records": len(data)})
        for p in data:
            if p.get("cert_type") != "Rev5":
                continue
            rec = products.setdefault(p["id"], {"fields": {}})
            rec.update({k: p.get(k) for k in IDENTITY}, last_seen=date)
            for k in LEGACY_FIELDS:
                if not empty(p.get(k)):
                    rec["fields"][k] = {"value": p[k], "as_of": date}

    out = {
        "description": ("Last values of the traditional (Rev5) marketplace fields that FedRAMP's export stopped "
                        "carrying from the November 3, 2026 export on, taken from Archstone's daily snapshots up to "
                        f"{args.cutoff}. 'as_of' is the latest snapshot in which the field held a value. Frozen: do not "
                        "regenerate."),
        "cutoff": args.cutoff,
        "fields": LEGACY_FIELDS,
        "sources": sources,
        "products": dict(sorted(products.items())),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n_imp = sum(1 for r in products.values() if "impact_level" in r["fields"])
    n_ag = sum(1 for r in products.values() if "agency_authorizations" in r["fields"])
    n_sp = sum(1 for r in products.values() if "partnering_agency" in r["fields"])
    print(f"freeze_legacy: {len(products)} traditional listings from {len(sources)} snapshots; "
          f"impact level {n_imp}, agency ATOs {n_ag}, sponsor {n_sp} -> {args.out}")


if __name__ == "__main__":
    main()
