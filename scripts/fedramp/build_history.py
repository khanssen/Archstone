#!/usr/bin/env python3
"""Build one history file per listing for the marketplace lookup: /fedramp-lookup/l/<package id>.json.

Every package ID any source has ever shown gets a file, delisted ones included. Each file holds:

  current   the fields as today's marketplace export reports them (PMO-reported), or null if the
            listing is not in today's export
  kept      fields today's export leaves empty that an earlier source carried, each with its value,
            the date it was last shown and the source: these are marked * on the page
  timeline  dated events, oldest first: status changes from FedRAMP's status changelog (back to
            2012), field changes in the old feed (Apr 14 to Nov 3, 2026) and in the daily exports
            (Oct 16, 2026 on), and agency ATOs appearing or dropping off in the ATO ledger
  atos      every agency ATO on file for the listing, from the ledger
  sources   which sources carry the listing, with their first and last dates

Sources: data/fedramp/raw/ (exports), data/fedramp/legacy/old-feed-history.json.gz (frozen),
data/fedramp/ato-ledger.json, and FedRAMP's fedramp-status-changelog.json (passed with --status-log).
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from pathlib import Path

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

# Export fields tracked for changes, by the name the page uses. Long free text (descriptions) and
# contact addresses are left out of the change log; agency lists are the ledger's.
TRACKED = ["csp", "cso", "status", "phase", "cert_type", "cert_path", "cert_class", "impact_level",
           "independent_assessor", "partnering_agency", "annual_assessment", "cert_date", "under_cap",
           "service_model", "deployment_model", "business_categories", "fedramp_msg", "ready_status",
           "ip_jab_status", "ip_pmo_status", "ip_agency_status", "ip_prog_status", "small_business", "uei"]
CURRENT = TRACKED + ["service_acronym", "website", "sales_email", "security_email", "trust_center",
                     "secure_configuration_guidance", "certified_services", "third_party_information_resources",
                     "independent_assessor_id", "status_date", "cap_date", "service_desc", "event_log"]
LABELS = {
    "csp": "Provider", "cso": "Offering", "status": "Status", "phase": "Phase", "cert_type": "Track",
    "cert_path": "Path", "cert_class": "Class", "impact_level": "Impact level",
    "independent_assessor": "Assessor", "partnering_agency": "Sponsor", "annual_assessment": "Annual assessment",
    "cert_date": "Certified date", "under_cap": "Under corrective action", "service_model": "Service model",
    "deployment_model": "Deployment model", "business_categories": "Business categories",
    "fedramp_msg": "FedRAMP's listing message", "ready_status": "FedRAMP Ready status",
    "ip_jab_status": "JAB In Process status", "ip_pmo_status": "PMO In Process status",
    "ip_agency_status": "Agency In Process status", "ip_prog_status": "Program In Process status",
    "small_business": "Small business", "uei": "UEI", "fedramp_auth_date": "FedRAMP authorization date",
    "auth_date": "Authorization date", "leveraged_systems": "Leveraged systems",
}


def empty(v) -> bool:
    return v in (None, "", "Unknown", "N/A", "Not Active", [], {}, "0", 0)


def norm(v):
    if isinstance(v, str):
        v = v.strip()
        if DATE_RE.fullmatch(v[:10]) and "T" in v:
            return v[:10]
    return None if empty(v) else v


def load_export(path: Path) -> list[dict]:
    data = json.loads(gzip.decompress(path.read_bytes()))
    return data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", required=True, type=Path)
    ap.add_argument("--old-feed", required=True, type=Path, help="data/fedramp/legacy/old-feed-history.json.gz")
    ap.add_argument("--ledger", required=True, type=Path)
    ap.add_argument("--status-log", type=Path, help="FedRAMP's fedramp-status-changelog.json")
    ap.add_argument("--graph", type=Path, help="relationships from build_graph.py (optional)")
    ap.add_argument("--out", required=True, type=Path, help="directory for <package id>.json files")
    ap.add_argument("--index", type=Path, help="also write a slim index of every listing")
    args = ap.parse_args()

    snaps = sorted(args.raw_dir.glob("products-*.json.gz"))
    if not snaps:
        sys.exit("build_history: no exports in --raw-dir")
    today = DATE_RE.search(snaps[-1].name).group(1)

    L: dict[str, dict] = {}

    def rec(pid: str) -> dict:
        return L.setdefault(pid, {"id": pid, "current": None, "kept": {}, "timeline": [], "atos": [],
                                  "sources": {}, "names": {}})

    def src(r, name, date):
        s = r["sources"].setdefault(name, {"first": date, "last": date})
        s["first"], s["last"] = min(s["first"], date), max(s["last"], date)

    # 1. Old feed (frozen): field values and their dates.
    feed = json.loads(gzip.decompress(args.old_feed.read_bytes()))
    for pid, h in feed["listings"].items():
        r = rec(pid)
        src(r, "old_feed", h["first"]); src(r, "old_feed", h["last"])
        for field, vals in h["fields"].items():
            prev = None
            for v in vals:
                if v["value"] != prev:
                    r["timeline"].append({"date": v["date"], "kind": "field", "source": "old_feed", "field": field,
                                          "label": LABELS.get(field, field), "from": prev, "to": v["value"]})
                prev = v["value"]
            if field in ("csp", "cso") and vals and vals[-1]["value"]:
                r["names"].setdefault(field, vals[-1]["value"])
        if h["last"] < feed["versions"][-1]["date"]:
            r["timeline"].append({"date": h["last"], "kind": "listing", "source": "old_feed",
                                  "text": "Last day in FedRAMP's old marketplace feed"})

    # 2. Daily exports: field changes between consecutive snapshots, and the current record.
    prev_by: dict[str, dict] = {}
    for f in snaps:
        date = DATE_RE.search(f.name).group(1)
        cur = {}
        for p in load_export(f):
            pid = p["id"]
            cur[pid] = p
            r = rec(pid)
            src(r, "export", date)
            old = prev_by.get(pid)
            if old is None and prev_by:
                r["timeline"].append({"date": date, "kind": "listing", "source": "export", "text": "Appears in the marketplace export"})
            for field in TRACKED:
                a, b = (norm(old.get(field)) if old else None), norm(p.get(field))
                if old is not None and a != b:
                    r["timeline"].append({"date": date, "kind": "field", "source": "export", "field": field,
                                          "label": LABELS.get(field, field), "from": a, "to": b,
                                          **({"emptied": True} if b is None else {})})
            for k in ("csp", "cso"):
                if p.get(k):
                    r["names"][k] = p[k].strip()
        for pid in set(prev_by) - set(cur):
            rec(pid)["timeline"].append({"date": date, "kind": "listing", "source": "export",
                                         "text": "Drops out of the marketplace export"})
        prev_by = cur
    for pid, p in prev_by.items():
        L[pid]["current"] = {k: p.get(k) for k in CURRENT if k in p}

    # 3. FedRAMP's status changelog: status changes back to 2012.
    if args.status_log and args.status_log.exists():
        d = json.loads(args.status_log.read_text(encoding="utf-8"))["data"]
        rows = d if isinstance(d, list) else next((v for v in d.values() if isinstance(v, list)), [])
        for t in rows:
            r = rec(t["product_id"])
            date = (t.get("transition_date") or "")[:10]
            src(r, "status_log", date)
            r["timeline"].append({"date": date, "kind": "status", "source": "status_log",
                                  "from": t.get("from_status") or None, "to": t.get("to_status"),
                                  "track": t.get("cert_type"), "path": t.get("cert_path"), "class": t.get("cert_class"),
                                  "recorded": (t.get("recorded_date") or "")[:10]})

    # 4. ATO ledger: every agency ATO, and when each source showed it or stopped.
    led = json.loads(args.ledger.read_text(encoding="utf-8"))
    last = led.get("source_last_seen", {})
    for name, p in led.get("products", {}).items():
        r = rec(name)
        for k in ("csp", "cso"):
            if p.get(k):
                r["names"].setdefault(k, p[k])
    for e in led["atos"]:
        r = rec(e["product_id"])
        r["atos"].append({k: e[k] for k in ("agency_key", "agency", "pmo", "published_now") if k in e}
                         | ({"published_as_parent": True} if e.get("published_as_parent") else {})
                         | {"sources": e["sources"]})
        for s, v in e["sources"].items():
            r["timeline"].append({"date": v["first"], "kind": "ato", "source": s, "agency": e["agency"],
                                  "pmo": e.get("pmo", False), "text": "first shown"})
            if v["last"] < last.get(s, v["last"]):
                r["timeline"].append({"date": v["last"], "kind": "ato", "source": s, "agency": e["agency"],
                                      "pmo": e.get("pmo", False), "text": "last shown"})

    # 5. Kept fields: today's export leaves them empty (or the listing is gone) and an earlier
    #    source carried them. Old feed first (field by field), then the last export that had a value.
    tracked_feed = {f for h in feed["listings"].values() for f in h["fields"]}
    for pid, r in L.items():
        cur = r["current"] or {}
        for field in sorted(set(TRACKED) | tracked_feed):
            if not empty(cur.get(field)):
                continue
            best = None
            for ev in r["timeline"]:
                if ev["kind"] == "field" and ev["field"] == field and ev["to"] is not None:
                    if best is None or ev["date"] >= best["as_of"]:
                        best = {"value": ev["to"], "as_of": ev["date"], "source": ev["source"]}
            if best:
                # last date the value was still shown, not the date it first appeared
                s = r["sources"].get(best["source"], {})
                for ev in r["timeline"]:
                    if ev["kind"] == "field" and ev["field"] == field and ev["source"] == best["source"] and ev["date"] > best["as_of"]:
                        s = {"last": ev["date"]}
                        break
                best["shown_until"] = s.get("last", best["as_of"])
                best["label"] = LABELS.get(field, field)
                r["kept"][field] = best

    if args.graph and args.graph.exists():
        g = json.loads(args.graph.read_text(encoding="utf-8"))
        for pid, rel in g.get("listings", {}).items():
            rec(pid)["relationships"] = rel

    order = {"status": 0, "listing": 1, "field": 2, "ato": 3}
    args.out.mkdir(parents=True, exist_ok=True)
    index = []
    for pid, r in L.items():
        r["timeline"].sort(key=lambda e: (e["date"], order.get(e["kind"], 9)))
        r["on_marketplace"] = r["current"] is not None
        (args.out / f"{re.sub(r'[^A-Za-z0-9_-]', '_', pid)}.json").write_text(
            json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        if not r["on_marketplace"]:
            st = [e for e in r["timeline"] if e["kind"] == "status"]
            index.append({"id": pid, "p": r["names"].get("csp", ""), "n": r["names"].get("cso", ""),
                          "last_status": st[-1]["to"] if st else None,
                          "last_date": max((s["last"] for s in r["sources"].values()), default=""),
                          "track": (st[-1].get("track") if st else None)})
    if args.index:
        args.index.write_text(json.dumps({"built": today, "off_marketplace": sorted(index, key=lambda x: x["id"])},
                                         ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    on = sum(r["on_marketplace"] for r in L.values())
    print(f"build_history: {len(L)} listings ({on} on the marketplace, {len(L) - on} off it); "
          f"{sum(len(r['timeline']) for r in L.values())} timeline events; "
          f"{sum(len(r['kept']) for r in L.values())} kept fields -> {args.out}")


if __name__ == "__main__":
    main()
