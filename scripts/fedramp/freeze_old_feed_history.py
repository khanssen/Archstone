#!/usr/bin/env python3
"""Freeze the field-by-field history of FedRAMP's old marketplace feed (data.json).

The feed lived in github.com/FedRAMP/marketplace-fedramp-gov-data from Apr 14, 2026 and stopped
changing on Nov 3, 2026 (it is still re-committed daily with unchanged content). This reads every
version whose content changed and records, per listing and per field, each value the feed showed
and the date it first showed it. Agency ATOs are left to the ATO ledger.

Written once to data/fedramp/legacy/old-feed-history.json.gz; refuses to overwrite without --force.
Needs a full clone of that repository.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

# Old-feed field -> the name the listing page uses (the export's name where there is one).
FIELDS = {
    "csp": "csp", "cso": "cso", "status": "status", "impact_level": "impact_level",
    "auth_type": "cert_path", "fedramp_auth": "fedramp_auth_date", "auth_date": "auth_date",
    "independent_assessor": "independent_assessor", "partnering_agency": "partnering_agency",
    "annual_assessment": "annual_assessment", "service_model": "service_model",
    "deployment_model": "deployment_model", "business_function": "business_categories",
    "fedramp_msg": "fedramp_msg", "ready_status": "ready_status", "ready_date": "ready_date",
    "ip_jab_status": "ip_jab_status", "ip_pmo_status": "ip_pmo_status",
    "ip_agency_status": "ip_agency_status", "ip_prog_status": "ip_prog_status",
    "leveraged_systems": "leveraged_systems", "small_business": "small_business", "uei": "uei",
}


# Text the feed puts in data fields to mean "nothing here".
PLACEHOLDERS = {"", "N/A", "Unknown", "Not Active", "Not In Process", "No FRR Date", "No", "None"}
ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})T[\d:.]+Z?$")


def clean(v, field=""):
    if isinstance(v, str):
        v = v.strip()
        if field == "small_business" and v in ("Yes", "No"):
            return v
        if v in PLACEHOLDERS:
            return None
        m = ISO.match(v)
        return m.group(1) if m else v
    if isinstance(v, list):
        v = [x for x in v if x not in ("", None)]
        return v or None
    return v


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fr-repo", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if args.out.exists() and not args.force:
        sys.exit(f"freeze_old_feed_history: {args.out} exists and is frozen; pass --force to rebuild it")

    log = subprocess.run(["git", "-C", str(args.fr_repo), "log", "--reverse", "--format=%H %cI", "--", "data.json"],
                         capture_output=True, text=True, check=True).stdout.split("\n")
    hist: dict[str, dict] = {}
    versions, prev = [], None
    for line in filter(None, log):
        rev, stamp = line.split()
        raw = subprocess.run(["git", "-C", str(args.fr_repo), "show", f"{rev}:data.json"], capture_output=True).stdout
        try:
            data = json.loads(raw)["data"]
        except (json.JSONDecodeError, KeyError):
            continue
        body = json.dumps(data, sort_keys=True)
        if body == prev:
            continue
        prev, date = body, stamp[:10]
        versions.append({"commit": rev, "date": date, "sha256": hashlib.sha256(raw).hexdigest()})
        seen = set()
        for p in data.get("Products", []):
            pid = p["id"]
            seen.add(pid)
            h = hist.setdefault(pid, {"first": date, "last": date, "fields": {}})
            h["last"] = date
            for src, name in FIELDS.items():
                v = clean(p.get(src), name)
                vals = h["fields"].setdefault(name, [])
                if not vals or vals[-1]["value"] != v:
                    if v is None and not vals:
                        continue
                    vals.append({"date": date, "value": v})
        for pid, h in hist.items():          # a listing that left the feed and came back
            if pid not in seen and h.get("gone") != h["last"]:
                h.setdefault("absent_from", []).append(date) if h["last"] < date and (not h.get("absent_from") or h["absent_from"][-1] <= h["last"]) else None

    out = {"description": __doc__.split("\n\n")[0].strip(), "repository": "https://github.com/FedRAMP/marketplace-fedramp-gov-data",
           "file": "data.json", "versions": versions, "listings": dict(sorted(hist.items()))}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.out, "wt", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    n = sum(len(v) for h in hist.values() for v in h["fields"].values())
    print(f"freeze_old_feed_history: {len(versions)} content versions, {len(hist)} listings, {n} field values -> {args.out}")


if __name__ == "__main__":
    main()
