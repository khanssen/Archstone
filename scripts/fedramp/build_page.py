#!/usr/bin/env python3
"""Build the FedRAMP 20x adoption page from a FedRAMP Marketplace export.

Reads one marketplace snapshot (the JSON the marketplace "Export JSON" button
produces, optionally gzipped) and writes a self-contained static page: all
numbers computed here, charts drawn as inline SVG, data embedded, nothing
fetched by the visitor's browser.

Usage:
  python3 scripts/fedramp/build_page.py \
      --snapshot data/fedramp/raw/products-2026-10-16.json.gz \
      --grc data/fedramp/grc-vendors.json \
      --out fedramp-20x-adoption \
      --history data/fedramp/history.csv

Fails loudly (non-zero exit) if the export no longer looks like the schema
this was written against, so a marketplace redesign breaks the build instead
of silently publishing wrong numbers.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import html
import io
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

PMO = "Federal Risk and Authorization Management Program"
GRC_TAG = "Governance, Risk, and Compliance (GRC)"
REQUIRED_FIELDS = {"id", "csp", "cso", "status", "cert_type", "cert_date",
                   "cert_path", "cert_class", "impact_level",
                   "agency_authorizations", "independent_assessor"}
MIN_RECORDS = 300
SITE = "https://www.archstonesecurity.com"
PAGE_PATH = "/fedramp-20x-adoption/"
MARKETPLACE_URL = "https://www.fedramp.gov/marketplace/products/"


# --------------------------------------------------------------------------
# Loading and validation
# --------------------------------------------------------------------------

def load_snapshot(path: Path) -> tuple[list[dict], str]:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    digest = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw)
    if isinstance(data, dict):
        data = next((v for v in data.values() if isinstance(v, list)), None)
    if not isinstance(data, list) or len(data) < MIN_RECORDS:
        sys.exit(f"build_page: expected a list of >= {MIN_RECORDS} products, got "
                 f"{type(data).__name__} of length {len(data) if hasattr(data, '__len__') else '?'}")
    missing = REQUIRED_FIELDS - set(data[0].keys())
    if missing:
        sys.exit(f"build_page: export schema changed, missing fields: {sorted(missing)}")
    types = Counter(p.get("cert_type") for p in data)
    if "Rev5" not in types or not any(str(t).startswith("20x") for t in types):
        sys.exit(f"build_page: cert_type values unexpected: {dict(types)}")
    return data, digest


def snapshot_date(path: Path) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    if not m:
        sys.exit(f"build_page: snapshot filename must contain a YYYY-MM-DD date: {path.name}")
    return m.group(1)


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

def status_target(desc: str) -> str:
    if " to " in desc and desc.startswith("Status changed from"):
        return desc.rsplit(" to ", 1)[1].strip()
    return desc.replace("Status set to", "").strip()


def timeline(p: dict, rev5: bool) -> dict:
    """Start of process, first authorization and later re-certifications from the status log."""
    ev = sorted((e for e in (p.get("event_log") or []) if e.get("date") and e.get("description")),
                key=lambda e: e["date"])
    certs = [e["date"][:10] for e in ev if status_target(e["description"]).startswith("FedRAMP Certified")]
    if rev5:
        starts = [e["date"][:10] for e in ev if status_target(e["description"]) == "Agency Authorization In Process"]
    else:
        starts = [e["date"][:10] for e in ev if not status_target(e["description"]).startswith("FedRAMP Certified")]
    first_cert = certs[0] if certs else ""
    start = next((d for d in starts if not first_cert or d <= first_cert), "")
    return {"start": start, "first_cert": first_cert,
            "recert": [d for d in certs[1:] if d != first_cert]}


def normalise(p: dict, grc: set[str]) -> dict:
    agencies = [a for a in (p.get("agency_authorizations") or []) if a and a != PMO]
    assessor = (p.get("independent_assessor") or "").strip()
    if len(assessor) > 80:          # free-text notes have appeared in this field
        assessor = ""
    return {
        "id": p["id"],
        "csp": (p.get("csp") or "").strip(),
        "product": (p.get("cso") or "").strip(),
        "track": "Rev5" if p.get("cert_type") == "Rev5" else "20x",
        "cert_type": p.get("cert_type") or "",
        "status": p.get("status") or "",
        "certified": str(p.get("status") or "").startswith("FedRAMP Certified"),
        "path": p.get("cert_path") or "",
        "cls": p.get("cert_class") or "",
        "impact": p.get("impact_level") or "",
        "date": (p.get("cert_date") or "")[:10],
        "tl": timeline(p, p.get("cert_type") == "Rev5"),
        "agencies": agencies,
        "n_agencies": len(agencies),
        "assessor": assessor,
        "grc": (p.get("csp") or "").strip().lower() in grc,
        "grc_tag": GRC_TAG in (p.get("business_categories") or []),
    }


def name_key(s: str) -> str:
    s = s.lower().replace("for government", "").replace("government", "")
    return re.sub(r"[^a-z0-9]", "", s)


def months_between(start: str, end: str) -> list[str]:
    y, m = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def shift_months(d: str, months: int) -> str:
    y, m = int(d[:4]), int(d[5:7]) - months
    while m <= 0:
        y, m = y - 1, m + 12
    day = min(int(d[8:10]), 28)
    return f"{y}-{m:02d}-{day:02d}"


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

def stats(ps: list[dict]) -> dict:
    n = len(ps)
    w = sum(1 for p in ps if p["n_agencies"] > 0)
    t = sum(p["n_agencies"] for p in ps)
    return {"n": n, "with": w, "atos": t,
            "share": (w / n) if n else None, "mean": (t / n) if n else None}


def analyse(rows: list[dict], snap: str) -> dict:
    cert = [r for r in rows if r["certified"]]
    tw_cert = [r for r in cert if r["track"] == "20x"]
    tw_dated = sorted([r for r in tw_cert if r["date"]], key=lambda r: r["date"])
    if not tw_dated:
        sys.exit("build_page: no dated 20x authorizations found")
    first = tw_dated[0]["date"]
    since = [r for r in cert if r["date"] and r["date"] >= first]
    aged_cut = shift_months(snap, 9)

    def pair(f):
        return {t: stats([r for r in since if r["track"] == t and f(r)]) for t in ("Rev5", "20x")}

    comparisons = [
        {"label": f"All authorized since {fmt_date(first)}", "rows": pair(lambda r: True)},
        {"label": f"Authorized at least nine months ago (by {fmt_date(aged_cut)})",
         "rows": pair(lambda r: r["date"] <= aged_cut)},
        {"label": "Moderate impact only", "rows": pair(lambda r: r["impact"] == "Moderate")},
    ]

    months = months_between(first, snap)
    monthly = []
    for mo in months:
        ps = [r for r in tw_dated if r["date"][:7] == mo]
        monthly.append({
            "month": mo,
            "grc": sum(1 for r in ps if r["grc"] and r["n_agencies"] == 0),
            "other": sum(1 for r in ps if not r["grc"] and r["n_agencies"] == 0),
            "agency": sum(1 for r in ps if r["n_agencies"] > 0),
            "products": [r["product"] for r in ps],
        })

    grc_cert = [r for r in tw_cert if r["grc"]]
    grc_providers = sorted({r["csp"] for r in grc_cert}, key=str.lower)

    ambiguous = [r for r in rows if r["track"] == "Rev5" and r["status"] == "Initial Implementation"
                 and not r["agencies"]]
    pipeline = [r for r in rows if r["track"] == "20x" and not r["certified"]
                and r["status"] not in ("Legacy FedRAMP Ready", "Unknown")]

    # Products listed on both tracks: same provider and product name, or the
    # 20x record id is the Rev5 id with a suffix (the marketplace uses "XL").
    rev5 = [r for r in rows if r["track"] == "Rev5"]
    by_id = {r["id"]: r for r in rev5}
    dual = []
    for t in [r for r in rows if r["track"] == "20x"]:
        matches = [r for r in rev5 if r["csp"].lower() == t["csp"].lower()
                   and (name_key(r["product"]) == name_key(t["product"])
                        or name_key(r["product"]) in name_key(t["product"])
                        or name_key(t["product"]) in name_key(r["product"]))]
        base = re.sub(r"[A-Z]+$", "", t["id"])
        if base != t["id"] and base in by_id and by_id[base] not in matches:
            matches.append(by_id[base])
        for r in matches:
            if r["certified"] or t["certified"]:
                dual.append({"rev5": r, "x20": t})
    dual.sort(key=lambda d: (-d["rev5"]["n_agencies"], d["x20"]["product"].lower()))

    by_class = []
    order = ["Class A", "Class B", "Class C", "Class D"]
    present = sorted({r["cls"] for r in tw_cert}, key=lambda c: order.index(c) if c in order else 99)
    for c in present:
        ps = [r for r in tw_cert if r["cls"] == c]
        impacts = Counter(r["impact"] for r in ps)
        by_class.append({"cls": c if c in order else "Class not listed",
                         "impacts": impacts, **stats(ps)})

    rev5_by_agency = Counter(a for r in cert if r["track"] == "Rev5" for a in set(r["agencies"]))
    x20_by_agency = defaultdict(list)
    for r in tw_cert:
        for ag in set(r["agencies"]):
            x20_by_agency[ag].append(r)
    all_agencies = set(rev5_by_agency) | set(x20_by_agency)
    agency_adopters = sorted(
        ({"agency": ag, "x20": sorted(ps, key=lambda r: r["date"]), "rev5": rev5_by_agency.get(ag, 0)}
         for ag, ps in x20_by_agency.items()),
        key=lambda d: (-len(d["x20"]), -d["rev5"], d["agency"]))
    top_rev5 = [{"agency": ag, "rev5": n, "x20": len(x20_by_agency.get(ag, []))}
                for ag, n in rev5_by_agency.most_common(10)]

    def share(ps, key):
        n = len(ps)
        k = sum(1 for r in ps if r[key])
        return {"n": n, "k": k, "share": (k / n) if n else None}

    rev5_cert = [r for r in cert if r["track"] == "Rev5"]

    def days(a_, b_):
        return (date.fromisoformat(b_) - date.fromisoformat(a_)).days

    def median(xs):
        xs = sorted(xs)
        if not xs:
            return None
        m = len(xs) // 2
        return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2

    tl_rows = []
    for r in tw_cert:
        t = r["tl"]
        if t["start"] and t["first_cert"]:
            recert = list(t["recert"])
            if r["date"] and r["date"] > t["first_cert"] and r["date"] not in recert:
                recert.append(r["date"])
            tl_rows.append({"r": r, "start": t["start"], "auth": t["first_cert"], "recert": sorted(recert),
                            "to_auth": days(t["start"], t["first_cert"]),
                            "since": days(t["first_cert"], snap)})
    tl_rows.sort(key=lambda d: (d["r"]["cert_type"] == "20x Pilot", d["start"], d["auth"]))
    rev5_durs = [days(r["tl"]["start"], r["tl"]["first_cert"]) for r in since
                 if r["track"] == "Rev5" and r["tl"]["start"] and r["tl"]["first_cert"]
                 and r["tl"]["first_cert"] >= first]
    def quart(xs):
        xs = sorted(xs)
        if len(xs) < 4:
            return None, None
        import statistics
        q = statistics.quantiles(xs, n=4)
        return q[0], q[2]

    for d in tl_rows:
        d["elapsed"] = days(d["start"], snap)
    r5_q1, r5_q3 = quart(rev5_durs)
    r5_med = median(rev5_durs)
    pil_wait = [d for d in tl_rows if d["r"]["cert_type"] == "20x Pilot" and d["r"]["n_agencies"] == 0]
    timing = {
        "rev5_q1": r5_q1, "rev5_q3": r5_q3,
        "pilot_elapsed_median": median([d["elapsed"] for d in pil_wait]),
        "pilot_wait_n": len(pil_wait),
        "pilot_past_rev5": sum(1 for d in pil_wait if r5_med is not None and d["elapsed"] > r5_med),
        "x20_median": median([d["to_auth"] for d in tl_rows if d["r"]["cert_type"] != "20x Pilot"]),
        "x20_n": sum(1 for d in tl_rows if d["r"]["cert_type"] != "20x Pilot"),
        "pilot_median": median([d["to_auth"] for d in tl_rows if d["r"]["cert_type"] == "20x Pilot"]),
        "pilot_n": sum(1 for d in tl_rows if d["r"]["cert_type"] == "20x Pilot"),
        "rev5_median": median(rev5_durs), "rev5_n": len(rev5_durs),
        "waiting_median": median([d["since"] for d in tl_rows
                                  if d["r"]["n_agencies"] == 0 and d["r"]["cert_type"] != "20x Pilot"]),
        "waiting_n": sum(1 for d in tl_rows if d["r"]["n_agencies"] == 0 and d["r"]["cert_type"] != "20x Pilot"),
    }
    grc_share = [
        {"label": "20x authorized", "sub": "self-declared GRC tag", "kind": "tag", **share(tw_cert, "grc_tag")},
        {"label": "20x authorized", "sub": "GRC classification feed", "kind": "list", **share(tw_cert, "grc")},
        {"label": "20x in process", "sub": "self-declared GRC tag", "kind": "tag", **share(pipeline, "grc_tag")},
        {"label": f"Rev5 authorized since {fmt_date(first)}", "sub": "self-declared GRC tag", "kind": "tag",
         **share([r for r in since if r["track"] == "Rev5"], "grc_tag")},
        {"label": "Rev5 authorized, all", "sub": "self-declared GRC tag", "kind": "tag", **share(rev5_cert, "grc_tag")},
    ]
    grc_products = sorted([r for r in tw_cert if r["grc"] or r["grc_tag"]],
                          key=lambda r: (not (r["grc"] and r["grc_tag"]), r["date"] or "9999"))

    adopters = [r for r in tw_cert if r["n_agencies"] > 0]
    adopter_agencies = Counter(a for r in adopters for a in r["agencies"])

    return {
        "snapshot": snap,
        "first": first,
        "days": (date.fromisoformat(snap) - date.fromisoformat(first)).days,
        "records": len(rows),
        "tw_cert": tw_cert,
        "tw_dated": tw_dated,
        "tw_undated": [r for r in tw_cert if not r["date"]],
        "tw_stats": stats(tw_cert),
        "by_class": by_class,
        "grc_share": grc_share,
        "tl_rows": tl_rows,
        "timing": timing,
        "grc_by_track": {
            t: sorted([r for r in cert if r["track"] == t and r["grc"]],
                      key=lambda r: (-r["n_agencies"], r["date"] or "9999", r["product"].lower()))
            for t in ("Rev5", "20x")},
        "grc_products": grc_products,
        "n_agencies_total": len(all_agencies),
        "agency_adopters": agency_adopters,
        "top_rev5": top_rev5,
        "gsa_rev5": rev5_by_agency.get("General Services Administration"),
        "gsa_x20": len(x20_by_agency.get("General Services Administration", [])),
        "grc_cert": grc_cert,
        "grc_stats": stats(grc_cert),
        "grc_providers": grc_providers,
        "comparisons": comparisons,
        "monthly": monthly,
        "pipeline": stats(pipeline),
        "ambiguous": ambiguous,
        "dual": dual,
        "adopters": adopters,
        "adopter_agencies": adopter_agencies,
        "rev5_since": stats([r for r in since if r["track"] == "Rev5"]),
    }


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------

def esc(s) -> str:
    return html.escape(str(s), quote=True)


def fmt_date(d: str) -> str:
    if not d:
        return "No date"
    return datetime.strptime(d, "%Y-%m-%d").strftime("%b %-d, %Y")


def fmt_month(m: str, short: bool = True) -> str:
    dt = datetime.strptime(m + "-01", "%Y-%m-%d")
    return dt.strftime("%b" if short else "%B %Y")


def pct(x) -> str:
    return "—" if x is None else f"{x:.0%}"


def dec(x) -> str:
    return "—" if x is None else f"{x:.2f}"


def words(n: int) -> str:
    small = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
             "eleven", "twelve"]
    return small[n] if 0 <= n < len(small) else f"{n:,}"


# --------------------------------------------------------------------------
# SVG figures
# --------------------------------------------------------------------------

def dot_chart(a: dict) -> str:
    items = a["tw_dated"] + a["tw_undated"]
    cols = 12
    cell = 34
    r = 11
    rows_n = (len(items) + cols - 1) // cols
    w, h = cols * cell, rows_n * cell
    parts = [f'<svg class="dots" viewBox="0 0 {w} {h}" width="100%" role="img" '
             f'aria-labelledby="dots-title"><title id="dots-title">{len(items)} FedRAMP 20x '
             f'authorizations; {a["tw_stats"]["with"]} with an agency ATO</title>']
    for i, p in enumerate(items):
        cx = (i % cols) * cell + cell / 2
        cy = (i // cols) * cell + cell / 2
        cls = "has" if p["n_agencies"] else "none"
        tip = (f'{p["product"]} ({p["csp"]}). {fmt_date(p["date"])}. '
               + (f'Agencies: {", ".join(p["agencies"])}' if p["agencies"] else "No agency ATO")
               + (". GRC / compliance vendor" if p["grc"] else ""))
        if p["grc"]:
            shape = (f'<rect x="{cx - r + 1:.1f}" y="{cy - r + 1:.1f}" width="{2 * r - 2}" '
                     f'height="{2 * r - 2}" rx="2" class="mk {cls}"/>')
        else:
            shape = f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r - 1}" class="mk {cls}"/>'
        parts.append(f'<g tabindex="0"><title>{esc(tip)}</title>{shape}</g>')
    parts.append("</svg>")
    return "".join(parts)


def bar_chart(a: dict) -> str:
    data = a["monthly"]
    W, H = 760, 300
    ml, mr, mt, mb = 34, 8, 14, 40
    maxv = max([d["grc"] + d["other"] + d["agency"] for d in data] + [1])
    top = max(4, -(-maxv // 2) * 2)
    plot_w, plot_h = W - ml - mr, H - mt - mb
    band = plot_w / len(data)
    bw = min(30, band * 0.68)

    def y(v):
        return mt + plot_h - v / top * plot_h

    parts = [f'<svg class="bars" viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-labelledby="bars-title"><title id="bars-title">FedRAMP 20x authorizations '
             f'per month, split by GRC vendors, other providers, and those with an agency ATO</title>']
    step = 2 if top <= 8 else max(1, top // 4)
    for v in range(0, top + 1, step):
        parts.append(f'<line x1="{ml}" x2="{W - mr}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="gridline"/>'
                     f'<text x="{ml - 6}" y="{y(v):.1f}" dy="0.32em" text-anchor="end" class="tick">{v}</text>')
    every = max(1, -(-len(data) * 44 // plot_w))
    for i, d in enumerate(data):
        x = ml + i * band + (band - bw) / 2
        base = 0
        segs = [("grc", "seg-grc", "GRC / compliance vendors"),
                ("other", "seg-other", "Other providers"),
                ("agency", "seg-agency", "With an agency ATO")]
        tip_lines = [fmt_month(d["month"], short=False)]
        for key, cls, label in segs:
            v = d[key]
            tip_lines.append(f"{label}: {v}")
            if v:
                parts.append(f'<rect x="{x:.1f}" y="{y(base + v):.1f}" width="{bw:.1f}" '
                             f'height="{y(base) - y(base + v):.1f}" class="{cls}"/>')
            base += v
        if d["products"]:
            tip_lines.append("")
            tip_lines.extend(d["products"])
        parts.append(f'<rect x="{ml + i * band:.1f}" y="{mt}" width="{band:.1f}" height="{plot_h}" '
                     f'class="hit" tabindex="0"><title>{esc(chr(10).join(tip_lines))}</title></rect>')
        if i % every == 0:
            mo = d["month"]
            parts.append(f'<text x="{ml + i * band + band / 2:.1f}" y="{H - mb + 18}" '
                         f'text-anchor="middle" class="tick">{fmt_month(mo)}</text>')
            if mo.endswith("-01") or i == 0:
                parts.append(f'<text x="{ml + i * band + band / 2:.1f}" y="{H - mb + 33}" '
                             f'text-anchor="middle" class="tick yr">{mo[:4]}</text>')
    parts.append(f'<line x1="{ml}" x2="{W - mr}" y1="{y(0):.1f}" y2="{y(0):.1f}" class="axis"/>')
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------

CSS = """
.wrap{max-width:1080px;margin:0 auto;padding:var(--s-6) max(20px,env(safe-area-inset-right,0px)) var(--s-7) max(20px,env(safe-area-inset-left,0px))}
.site-mast{display:inline-flex;align-items:center;gap:10px;margin:var(--s-4) 0 0 max(20px,env(safe-area-inset-left,0px));text-decoration:none;color:var(--ink);font-weight:600}
.site-mast:hover{text-decoration:underline}
.site-mast img{display:block}
.eyebrow{margin:0 0 var(--s-3)}
h1{margin:0}
.lede{font-size:var(--t-lede);color:var(--ink-soft);margin:var(--s-4) 0 0;max-width:68ch}
.lede b{color:var(--ink);font-weight:600}
.meta{display:flex;flex-wrap:wrap;gap:var(--s-2) var(--s-5);margin-top:var(--s-4);padding-top:var(--s-3);border-top:1px solid var(--rule);font-size:var(--t-small);color:var(--ink-soft)}
.meta b{color:var(--ink);font-weight:600}
.figs{display:grid;gap:var(--s-4);grid-template-columns:repeat(2,minmax(0,1fr));margin-top:var(--s-5)}
@media (max-width:720px){.figs{grid-template-columns:1fr}}
.fig{background:var(--surface);border:1px solid var(--rule);border-radius:10px;padding:var(--s-4);min-width:0}
.fig.wide{grid-column:1/-1}
.fig h2{margin:0 0 var(--s-2)}
.fig .note{margin:0 0 var(--s-3);color:var(--ink-soft);font-size:var(--t-small);max-width:var(--measure-wide)}
.big{display:flex;flex-wrap:wrap;gap:var(--s-3) var(--s-5);align-items:flex-start;margin:var(--s-2) 0 var(--s-2)}
.big div{display:grid;gap:2px}
.big .num{font-size:var(--t-display);font-weight:600;line-height:1;letter-spacing:-0.02em}
.big .num.gap{color:var(--gap)}
.big .lbl{font-size:var(--t-small);color:var(--ink-soft);max-width:22ch}
.cls{display:grid;gap:var(--s-3);margin:var(--s-2) 0 0}
.cls-row{display:grid;grid-template-columns:minmax(8rem,12rem) 1fr 13rem;gap:var(--s-2) var(--s-4);align-items:center}
.cls-row.total{border-top:1px solid var(--rule);padding-top:var(--s-3)}
.cls-name{font-weight:600}
.cls-name small{display:block;font-weight:400;font-size:var(--t-small);color:var(--ink-soft)}
.track{height:28px;background:var(--gap-fill);border:1px solid var(--gap);border-radius:4px;position:relative;overflow:hidden}
.fill{position:absolute;inset:0 auto 0 0;background:var(--referent)}
.cls-val{display:flex;align-items:baseline;gap:var(--s-2);font-variant-numeric:tabular-nums}
.cls-val .pc{font-size:var(--t-title);font-weight:600;min-width:4.4ch;text-align:right}
.cls-val .pc.zero{color:var(--gap)}
.cls-val .of{font-size:var(--t-small);color:var(--ink-soft)}
@media (max-width:640px){.cls-row{grid-template-columns:1fr auto}.cls-row .track{grid-column:1/-1;grid-row:2}}
h3.sub{font-size:var(--t-body);margin:var(--s-4) 0 var(--s-2)}
.fill.grc{background:var(--gap)}
.track.grc{background:var(--manual-fill);border-color:var(--rule-strong)}
.cls-row.sep{border-top:1px solid var(--rule);padding-top:var(--s-3)}
td.ck{text-align:center;font-family:var(--mono)}
.tracks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--s-4) var(--s-5);margin-top:var(--s-3)}
@media (max-width:720px){.tracks{grid-template-columns:1fr}}
.trk h3{margin:0 0 var(--s-1);font-size:var(--t-title)}
.trk .tot{display:flex;flex-wrap:wrap;gap:var(--s-1) var(--s-4);font-size:var(--t-small);color:var(--ink-soft);margin:0 0 var(--s-3);padding-bottom:var(--s-2);border-bottom:1px solid var(--rule-strong)}
.trk .tot b{font-size:var(--t-lede);color:var(--ink);font-weight:600}
.trk .tot b.zero{color:var(--gap)}
.prow{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px var(--s-3);padding:var(--s-2) 0;border-bottom:1px solid var(--rule)}
.prow .pn{font-weight:600;font-size:var(--t-small);min-width:0}
.prow .pn small{display:block;font-weight:400;color:var(--ink-soft)}
.prow .pc{font-variant-numeric:tabular-nums;font-weight:600;align-self:start}
.prow .pc.zero{color:var(--gap)}
.units{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:4px;min-height:14px}
.u{width:14px;height:14px;border-radius:3px;background:var(--referent)}
.u.none{width:auto;height:auto;background:none;border:0;font-size:var(--t-micro);font-family:var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--gap)}
.b-r5{fill:var(--referent)}
.b-20{fill:var(--gap)}
.gb .val{font-size:15px;font-weight:600;fill:var(--ink)}
.gb .val.zero{fill:var(--gap)}
.gb .glabel{font-size:13px;font-weight:600;fill:var(--ink)}
.gbwrap{margin-bottom:var(--s-5)}
.sbs{display:grid;gap:var(--s-3)}
.sb-row{display:grid;grid-template-columns:minmax(8rem,12rem) 1fr 13rem;gap:var(--s-2) var(--s-4);align-items:center}
.sb-row.total{border-top:1px solid var(--rule);padding-top:var(--s-3)}
.sb-track{min-width:0}
.sb{display:flex;gap:3px;height:34px}
.sb .seg{flex:1 1 0;border-radius:3px;min-width:0}
.sb .seg.has,.sb-has{fill:var(--referent);background:var(--referent)}
.sb .seg.none{background:var(--gap-fill);box-shadow:inset 0 0 0 1.5px var(--gap)}
.sb-none{fill:var(--gap-fill);stroke:var(--gap);stroke-width:1.5}
.sb-val{font-size:var(--t-small);color:var(--ink-soft);line-height:1.35}
.sb-val b{font-size:var(--t-title);color:var(--ink);font-weight:600;margin-right:4px}
.sb-val .zero{color:var(--gap);font-weight:600}
.sb-val small{display:block;font-size:var(--t-micro);font-family:var(--mono)}
@media (max-width:640px){.sb-row{grid-template-columns:1fr auto}.sb-row .sb-track{grid-column:1/-1;grid-row:2}}
.tl text{font-family:var(--sans)}
.tl .gridline{stroke:var(--grid);stroke-width:1}
.tl .today{stroke:var(--ink-soft);stroke-width:1;stroke-dasharray:2 3}
.tl .tick{fill:var(--ink-soft);font-size:11px}
.tl .tln{fill:var(--ink);font-size:12px}
.proc{fill:var(--manual)}
.r5band{fill:var(--referent-fill)}
.r5med{stroke:var(--referent);stroke-width:2}
.tl .r5lab{fill:var(--referent);font-size:12px;font-weight:600}
.tl .r5sub{fill:var(--referent);font-size:11px}
.endpt{fill:var(--gap)}
.endpt.has{fill:var(--referent)}
.proc.pil{fill:var(--manual-fill);stroke:var(--manual);stroke-width:1}
.tl .tlg{fill:var(--ink);font-size:12px;font-weight:600;font-family:var(--mono);letter-spacing:.06em;text-transform:uppercase}
.tl .tlgl{stroke:var(--rule-strong);stroke-width:1}
.auth{fill:var(--ink)}
.tail{stroke:var(--gap);stroke-width:2;stroke-dasharray:5 4}
.tail-has{stroke:var(--referent);stroke-width:3}
.recert{stroke:var(--ink);stroke-width:2}
.tl .tlv{fill:var(--gap);font-size:11px;font-weight:600;paint-order:stroke;stroke:var(--surface);stroke-width:4px;stroke-linejoin:round}
.tl .tlv.has{fill:var(--referent)}
.tl .tlhit{fill:transparent}
.tl .tlr:hover .tlhit,.tl .tlr:focus .tlhit{fill:var(--ink);fill-opacity:.04}
.tl .tlr:focus{outline:none}
.scroll .tl{min-width:760px;display:block}
.stats3{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,12rem),1fr));gap:var(--s-3) var(--s-5);margin:var(--s-2) 0 var(--s-3)}
.stats3 div{display:grid;gap:2px;align-content:start}
.stats3 .num{font-size:var(--t-display);font-weight:600;line-height:1;letter-spacing:-.02em}
.stats3 .num small{font-size:var(--t-lede);font-weight:600;margin-left:3px}
.stats3 .num.gap{color:var(--gap)}
.stats3 .lbl{font-size:var(--t-small);color:var(--ink-soft)}
.legend{display:flex;flex-wrap:wrap;gap:var(--s-2) var(--s-4);font-size:var(--t-small);color:var(--ink-soft);margin:0 0 var(--s-3)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.legend svg{flex:none}
svg text{font-family:var(--sans)}
.dots{max-width:560px;display:block}
.scroll{overflow-x:auto}
.scroll .bars{min-width:560px;display:block}
.mk{stroke-width:2}
.mk.none{fill:var(--surface);stroke:var(--gap)}
.mk.has{fill:var(--referent);stroke:var(--referent)}
.dots g:focus{outline:none}
.dots g:focus .mk,.dots g:hover .mk{stroke:var(--ink);stroke-width:3}
.bars .gridline{stroke:var(--grid);stroke-width:1}
.bars .axis{stroke:var(--rule-strong);stroke-width:1}
.bars .tick{fill:var(--ink-soft);font-size:11px}
.bars .tick.yr{font-family:var(--mono)}
.seg-grc{fill:var(--gap)}
.seg-other{fill:var(--gap-fill);stroke:var(--gap);stroke-width:1}
.seg-agency{fill:var(--referent)}
.bars .hit{fill:transparent}
.bars .hit:hover,.bars .hit:focus{fill:var(--ink);fill-opacity:.05;outline:none}
.tbl{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:var(--t-small);background:var(--surface)}
th{text-align:left;font-weight:600;color:var(--ink-soft);border-bottom:1px solid var(--rule-strong);padding:var(--s-2) var(--s-2);vertical-align:bottom}
td{border-bottom:1px solid var(--rule);padding:var(--s-2) var(--s-2);vertical-align:top}
td.n,th.n{text-align:right;white-space:nowrap}
td.zero{color:var(--gap);font-weight:600}
tr.grp td{font-weight:600;color:var(--ink);border-bottom-color:var(--rule-strong);padding-top:var(--s-3)}
.tag{font-family:var(--mono);font-size:var(--t-micro);letter-spacing:.06em;text-transform:uppercase;border:1px solid currentColor;border-radius:4px;padding:1px 6px;white-space:nowrap}
.tag.grc{color:var(--gap)}
.tag.ag{color:var(--referent)}
.list{max-height:34rem;overflow:auto;border:1px solid var(--rule);border-radius:6px}
.list th{position:sticky;top:0;background:var(--surface)}
section.read{margin-top:var(--s-6)}
section.read h2{margin:0 0 var(--s-3)}
section.read ul{margin:0;padding-left:1.1rem;display:grid;gap:var(--s-2);max-width:var(--measure-wide);color:var(--ink-soft)}
section.read li b{color:var(--ink);font-weight:600}
footer{margin-top:var(--s-6);padding-top:var(--s-3);border-top:1px solid var(--rule);font-size:var(--t-small);color:var(--ink-soft);display:flex;flex-wrap:wrap;gap:var(--s-2) var(--s-5)}
footer a{color:var(--ink-soft)}
@media (max-width:640px){.hide-sm{display:none}}
"""


def timeline_chart(a: dict) -> str:
    rows = a["tl_rows"]
    if not rows:
        return "<p>No 20x products have both a start and an authorization date in their status history.</p>"
    tm = a["timing"]
    groups = [("Open 20x", [d for d in rows if d["r"]["cert_type"] != "20x Pilot"]),
              ("20x Pilot · invitation-only", [d for d in rows if d["r"]["cert_type"] == "20x Pilot"])]
    groups = [g for g in groups if g[1]]
    W, rh, gh, ml, mr, mt, mb = 1000, 24, 30, 220, 118, 52, 44
    H = mt + rh * len(rows) + gh * len(groups) + mb
    top_days = max([d["elapsed"] for d in rows] + [tm["rev5_q3"] or 0])
    top_days = int(-(-top_days // 90) * 90)
    xw = W - ml - mr

    def x(v):
        return ml + v / top_days * xw

    out = [f'<svg class="tl" viewBox="0 0 {W} {H}" width="100%" role="img" aria-labelledby="tl-t">'
           f'<title id="tl-t">Days since each 20x product entered the process: time to authorization, then time '
           f'without an agency, against the usual Rev5 time to an agency-backed authorization</title>']
    if tm["rev5_q1"] is not None:
        x1, x3 = x(tm["rev5_q1"]), x(tm["rev5_q3"])
        out.append(f'<rect x="{x1:.1f}" y="{mt - 8}" width="{x3 - x1:.1f}" height="{H - mb - mt + 8}" class="r5band"/>')
    if tm["rev5_median"] is not None:
        xm = x(tm["rev5_median"])
        out.append(f'<line x1="{xm:.1f}" x2="{xm:.1f}" y1="{mt - 8}" y2="{H - mb}" class="r5med"/>'
                   f'<text x="{xm:.1f}" y="{mt - 30}" text-anchor="middle" class="r5lab">Rev5 median: {round(tm["rev5_median"])} days</text>'
                   f'<text x="{xm:.1f}" y="{mt - 17}" text-anchor="middle" class="r5sub">to an authorization with an agency behind it</text>')
    for v in range(0, top_days + 1, 90):
        out.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{mt - 8}" y2="{H - mb}" class="gridline"/>')
    layout, yy = [], mt
    for gname, gl in groups:
        layout.append(("hdr", gname, yy)); yy += gh
        for d in gl:
            layout.append(("row", d, yy)); yy += rh
    for kind, d, top in layout:
        if kind == "hdr":
            out.append(f'<text x="0" y="{top + gh - 9:.1f}" class="tlg">{esc(d)}</text>'
                       f'<line x1="0" x2="{W}" y1="{top + gh - 2:.1f}" y2="{top + gh - 2:.1f}" class="tlgl"/>')
            continue
        r = d["r"]
        pilot = r["cert_type"] == "20x Pilot"
        cy = top + rh / 2
        xa, xe = x(d["to_auth"]), x(d["elapsed"])
        has = r["n_agencies"] > 0
        tip = (f'{r["product"]} ({r["csp"]}). Entered the process {fmt_date(d["start"])}; authorized after '
               f'{d["to_auth"]} days ({fmt_date(d["auth"])}). {d["elapsed"]} days since entering. '
               + (f'Agency ATOs: {", ".join(r["agencies"])}.' if has else 'No agency ATO.')
               + (f' Listing re-certified {", ".join(fmt_date(z) for z in d["recert"])}.' if d["recert"] else ""))
        name = r["product"] if len(r["product"]) <= 30 else r["product"][:29] + "…"
        out.append(f'<g class="tlr{" has" if has else ""}" tabindex="0"><title>{esc(tip)}</title>'
                   f'<rect x="0" y="{cy - rh / 2:.1f}" width="{W}" height="{rh}" class="tlhit"/>'
                   f'<text x="{ml - 10}" y="{cy:.1f}" dy="0.32em" text-anchor="end" class="tln">{esc(name)}</text>'
                   f'<line x1="{xa:.1f}" x2="{xe:.1f}" y1="{cy:.1f}" y2="{cy:.1f}" class="{"tail-has" if has else "tail"}"/>'
                   f'<rect x="{ml:.1f}" y="{cy - 5:.1f}" width="{max(xa - ml, 2):.1f}" height="10" rx="2" class="{"proc pil" if pilot else "proc"}"/>'
                   f'<circle cx="{xa:.1f}" cy="{cy:.1f}" r="4.5" class="auth"/>'
                   f'<circle cx="{xe:.1f}" cy="{cy:.1f}" r="2.5" class="{"endpt has" if has else "endpt"}"/>')
        for z in d["recert"]:
            xz = x(days_between(d["start"], z))
            out.append(f'<line x1="{xz:.1f}" x2="{xz:.1f}" y1="{cy - 7:.1f}" y2="{cy + 7:.1f}" class="recert"/>')
        lab = (f'{len(r["agencies"])} agency ATO' + ("" if len(r["agencies"]) == 1 else "s")) if has else f'{d["elapsed"]} days, no agency'
        out.append(f'<text x="{max(xe, x(top_days * 0.0)) + 8:.1f}" y="{cy:.1f}" dy="0.32em" class="{"tlv has" if has else "tlv"}">{lab}</text></g>')
    for v in range(0, top_days + 1, 90):
        out.append(f'<text x="{x(v):.1f}" y="{H - mb + 16}" text-anchor="middle" class="tick">{v}</text>')
    out.append(f'<text x="{ml + xw / 2:.1f}" y="{H - mb + 34}" text-anchor="middle" class="tick">Days since entering the process</text>')
    out.append("</svg>")
    return "".join(out)


def days_between(a_: str, b_: str) -> int:
    return (date.fromisoformat(b_) - date.fromisoformat(a_)).days


def legend_swatch(kind: str) -> str:
    if kind == "dot-none":
        return '<svg width="16" height="16" aria-hidden="true"><circle cx="8" cy="8" r="6" class="mk none"/></svg>'
    if kind == "dot-has":
        return '<svg width="16" height="16" aria-hidden="true"><circle cx="8" cy="8" r="6" class="mk has"/></svg>'
    if kind == "tl-proc":
        return '<svg width="22" height="12" aria-hidden="true"><rect x="1" y="1" width="20" height="10" rx="2" class="proc"/></svg>'
    if kind == "tl-band":
        return '<svg width="22" height="14" aria-hidden="true"><rect x="1" y="1" width="20" height="12" class="r5band"/><line x1="11" x2="11" y1="0" y2="14" class="r5med"/></svg>'
    if kind == "tl-pil":
        return '<svg width="22" height="12" aria-hidden="true"><rect x="1" y="1" width="20" height="10" rx="2" class="proc pil"/></svg>'
    if kind == "tl-auth":
        return '<svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4.5" class="auth"/></svg>'
    if kind == "tl-tail":
        return '<svg width="26" height="12" aria-hidden="true"><line x1="1" x2="25" y1="6" y2="6" class="tail"/></svg>'
    if kind == "tl-has":
        return '<svg width="26" height="12" aria-hidden="true"><line x1="1" x2="25" y1="6" y2="6" class="tail-has"/></svg>'
    if kind == "tl-recert":
        return '<svg width="10" height="14" aria-hidden="true"><line x1="5" x2="5" y1="0" y2="14" class="recert"/></svg>'
    if kind == "sq":
        return '<svg width="16" height="16" aria-hidden="true"><rect x="2" y="2" width="12" height="12" rx="2" class="mk none"/></svg>'
    return (f'<svg width="14" height="14" aria-hidden="true"><rect x="1" y="1" width="12" height="12" '
            f'class="{kind}"/></svg>')


def prov(a: dict, digest: str, basis: str) -> str:
    return (f'<div class="prov"><span><b>Source</b> FedRAMP Marketplace export, {fmt_date(a["snapshot"])}</span>'
            f'<span><b>Basis</b> {esc(basis)}</span>'
            f'<span><b>sha256</b> {digest[:12]}</span></div>')


def render(a: dict, digest: str, built: str) -> str:
    tw, grc = a["tw_stats"], a["grc_stats"]
    dated = len(a["tw_dated"])
    dated_with = sum(1 for r in a["tw_dated"] if r["n_agencies"])
    low = (tw["share"] or 0) < 0.25
    h1 = ("Agencies are not relying on FedRAMP 20x." if low
          else "How many agencies rely on FedRAMP 20x.")
    shared = [ag for ag, c in a["adopter_agencies"].items() if c == len(a["adopters"]) and c > 1]
    adopters_txt = ", ".join(r["product"] for r in a["adopters"]) or "none"

    lede = (f'FedRAMP has issued <b>{tw["n"]} 20x authorizations</b> in the {a["days"]} days since '
            f'the first, on {fmt_date(a["first"])}. <b>{tw["with"]} of them</b> have an agency '
            f'authorization from anyone other than the FedRAMP PMO, which records one on every 20x '
            f'listing. Of the {grc["n"]} held by GRC and compliance-automation vendors, '
            f'<b>{words(grc["with"])} {"has" if grc["with"] == 1 else "have"} an agency customer</b>.')

    # comparison table
    comp_rows = []
    for c in a["comparisons"]:
        comp_rows.append(f'<tr class="grp"><td colspan="5">{esc(c["label"])}</td></tr>')
        for t in ("Rev5", "20x"):
            s = c["rows"][t]
            zero = ' class="n zero"' if t == "20x" and s["n"] and (s["share"] or 0) < 0.25 else ' class="n"'
            comp_rows.append(
                f'<tr><td>{t}</td><td class="n">{s["n"]}</td><td{zero}>{s["with"]} ({pct(s["share"])})</td>'
                f'<td class="n">{s["atos"]}</td><td class="n">{dec(s["mean"])}</td></tr>')

    dual_rows = []
    for d in a["dual"]:
        r, t = d["rev5"], d["x20"]
        dual_rows.append(
            f'<tr><td>{esc(t["product"])}<br><span class="hide-sm" style="color:var(--ink-soft)">{esc(t["csp"])}</span></td>'
            f'<td>{esc(r["status"])}<br><span style="color:var(--ink-soft)">{esc(r["impact"])} · {fmt_date(r["date"]) if r["date"] else "not authorized"}</span></td>'
            f'<td class="n">{r["n_agencies"]}</td>'
            f'<td>{esc(t["status"])}<br><span style="color:var(--ink-soft)">{esc(t["impact"])} · {fmt_date(t["date"]) if t["date"] else "not authorized"}</span></td>'
            f'<td class="n{" zero" if t["n_agencies"] == 0 else ""}">{t["n_agencies"]}</td></tr>')

    list_rows = []
    ordered = sorted(a["tw_cert"], key=lambda r: (r["n_agencies"] == 0, r["date"] == "", r["date"]))
    for p in ordered:
        tags = []
        if p["grc"]:
            tags.append('<span class="tag grc">GRC</span>')
        list_rows.append(
            f'<tr><td class="n">{p["date"] or "—"}</td><td>{esc(p["product"])} {" ".join(tags)}</td>'
            f'<td class="hide-sm">{esc(p["csp"])}</td><td class="hide-sm">{esc(p["cert_type"])}</td>'
            f'<td class="hide-sm">{esc(p["cls"])}</td><td class="hide-sm">{esc(p["impact"])}</td>'
            f'<td class="n{" zero" if p["n_agencies"] == 0 else ""}">{p["n_agencies"]}</td>'
            f'<td class="hide-sm">{esc("; ".join(p["agencies"])) or "—"}</td>'
            f'<td class="hide-sm">{esc(p["assessor"]) or "—"}</td></tr>')

    def class_row(name, sub, st, total=False):
        share = st["share"] or 0
        z = " zero" if st["with"] == 0 else ""
        return (f'<div class="cls-row{" total" if total else ""}"><div class="cls-name">{esc(name)}<small>{esc(sub)}</small></div>'
                f'<div class="track" role="img" aria-label="{st["with"]} of {st["n"]} with an agency ATO">'
                f'<div class="fill" style="width:{share * 100:.1f}%"></div></div>'
                f'<div class="cls-val"><span class="pc{z}">{share:.0%}</span>'
                f'<span class="of">{st["with"]} of {st["n"]} {"product" if st["n"] == 1 else "products"}</span></div></div>')

    def impact_txt(imp):
        known = {k: v for k, v in imp.items() if k and k != "Unknown"}
        if not known:
            return "impact level not listed"
        if len(known) == 1 and sum(known.values()) == sum(imp.values()):
            return f"all {next(iter(known))}"
        return ", ".join(f"{v} {k}" for k, v in sorted(known.items(), key=lambda x: -x[1])) + (
            f", {imp.get('Unknown', 0)} not listed" if imp.get("Unknown") else "")

    class_rows = "".join(class_row(c["cls"], impact_txt(c["impacts"]), c) for c in a["by_class"])
    pil = [r for r in a["tw_cert"] if r["cert_type"] == "20x Pilot"]
    opn = [r for r in a["tw_cert"] if r["cert_type"] != "20x Pilot"]
    class_rows += class_row("20x Pilot", "invitation-only, all classes", stats(pil), total=True)
    class_rows += class_row("Open 20x", "all classes", stats(opn))
    class_rows += class_row("All 20x", f'{a["tw_stats"]["n"]} authorized', a["tw_stats"], total=True)

    adopter_rows = "".join(
        f'<tr><td>{esc(d["agency"])}</td><td>{esc(", ".join(r["product"] for r in d["x20"]))}</td>'
        f'<td class="n">{len(d["x20"])}</td><td class="n">{d["rev5"]}</td></tr>' for d in a["agency_adopters"])
    top_rows = "".join(
        f'<tr><td>{esc(d["agency"])}</td><td class="n">{d["rev5"]}</td>'
        f'<td class="n{" zero" if d["x20"] == 0 else ""}">{d["x20"]}</td></tr>' for d in a["top_rev5"])
    gsa_txt = ""
    if a["gsa_rev5"] is not None:
        gsa_txt = (f' The General Services Administration, which runs FedRAMP, relies on {a["gsa_rev5"]} '
                   f'Rev5 products and {a["gsa_x20"]} 20x {"product" if a["gsa_x20"] == 1 else "products"}.')

    grc_rows = ""
    for i, g in enumerate(a["grc_share"]):
        sh = g["share"] or 0
        sep = " sep" if g["label"] != a["grc_share"][i - 1]["label"] and i else ""
        grc_rows += (f'<div class="cls-row{sep}"><div class="cls-name">{esc(g["label"])}<small>{esc(g["sub"])}</small></div>'
                     f'<div class="track grc" role="img" aria-label="{g["k"]} of {g["n"]} are GRC tools">'
                     f'<div class="fill grc" style="width:{sh * 100:.1f}%"></div></div>'
                     f'<div class="cls-val"><span class="pc">{sh:.0%}</span>'
                     f'<span class="of">{g["k"]} of {g["n"]} {"product" if g["n"] == 1 else "products"}</span></div></div>')
    grc_prod_rows = "".join(
        f'<tr><td>{esc(r["product"])}</td><td class="hide-sm">{esc(r["csp"])}</td><td class="n">{r["date"] or "—"}</td>'
        f'<td class="ck">{"✓" if r["grc_tag"] else "–"}</td><td class="ck">{"✓" if r["grc"] else "–"}</td>'
        f'<td class="n{" zero" if r["n_agencies"] == 0 else ""}">{r["n_agencies"]}</td></tr>' for r in a["grc_products"])

    def track_col(title, ps):
        n_atos = sum(r["n_agencies"] for r in ps)
        n_ag = len({ag for r in ps for ag in r["agencies"]})
        z = lambda v: ' class="zero"' if v == 0 else ""
        rows_html = ""
        for r in ps:
            units = "".join(f'<span class="u" title="{esc(ag)}"></span>' for ag in r["agencies"]) or '<span class="u none">No agency</span>'
            rows_html += (f'<div class="prow"><div class="pn">{esc(r["product"])}<small>{esc(r["csp"])} · '
                          f'{esc(r["impact"]) if r["impact"] != "Unknown" else "impact not listed"} · '
                          f'{fmt_date(r["date"]) if r["date"] else "no date"}</small></div>'
                          f'<div class="pc{" zero" if r["n_agencies"] == 0 else ""}">{r["n_agencies"]}</div>'
                          f'<div class="units" aria-label="{esc("; ".join(r["agencies"]) or "No agency ATO")}">{units}</div></div>')
        return (f'<div class="trk"><h3>{title}</h3><p class="tot"><span><b>{len(ps)}</b> GRC products</span>'
                f'<span><b{z(n_atos)}>{n_atos}</b> agency ATOs</span><span><b{z(n_ag)}>{n_ag}</b> distinct agencies</span></p>'
                f'{rows_html or "<p>No GRC products on this track.</p>"}</div>')

    def grc_by_type():
        order = [("Rev5", "Agency", "Rev5, agency path", "sponsored by an agency from the start"),
                 ("Rev5", "JAB", "Rev5, JAB path", "Joint Authorization Board"),
                 ("20x Pilot", "Program", "20x Pilot", "authorized by the FedRAMP PMO"),
                 ("20x", "Program", "20x", "authorized by the FedRAMP PMO")]
        ps_all = a["grc_by_track"]["Rev5"] + a["grc_by_track"]["20x"]
        rows_ = []
        for ctype, path, name, sub in order:
            ps = [r for r in ps_all if r["cert_type"] == ctype and r["path"] == path]
            if ps:
                rows_.append((name, sub, ps, False))
        x20 = a["grc_by_track"]["20x"]
        if len({r["cert_type"] for r in x20}) > 1:
            rows_.append(("All 20x", "Pilot and current combined", x20, True))
        top = max(len(r[2]) for r in rows_)
        out = ""
        for name, sub, ps, total in rows_:
            ps = sorted(ps, key=lambda r: -r["n_agencies"])
            w = f"{len(ps) / top * 100:.2f}%"
            segs = "".join(
                f'<span class="seg {"has" if r["n_agencies"] else "none"}" '
                f'title="{esc(r["product"])}: {r["n_agencies"]} agency {"ATO" if r["n_agencies"] == 1 else "ATOs"}"></span>'
                for r in ps)
            st = stats(ps)
            if st["with"] == st["n"]:
                txt = f'all {st["n"]} with an agency ATO'
            elif st["with"] == 0:
                txt = f'none with an agency ATO'
            else:
                txt = f'{st["with"]} with an agency ATO'
            out += (f'<div class="sb-row{" total" if total else ""}"><div class="cls-name">{esc(name)}<small>{esc(sub)}</small></div>'
                    f'<div class="sb-track"><div class="sb" style="width:{w}" role="img" '
                    f'aria-label="{st["n"]} GRC products, {st["with"]} with an agency ATO">{segs}</div></div>'
                    f'<div class="sb-val"><b>{st["n"]}</b> <span class="{"zero" if st["with"] == 0 else ""}">{txt}</span>'
                    f'<small>{st["atos"]} agency {"ATO" if st["atos"] == 1 else "ATOs"}</small></div></div>')
        return out

    grc_track_html = (track_col("Traditional FedRAMP (Rev5)", a["grc_by_track"]["Rev5"])
                      + track_col("FedRAMP 20x", a["grc_by_track"]["20x"]))

    fmt_days = lambda v: "—" if v is None else f"{round(v):,}"
    tm_x20, tm_r5, tm_pel = (fmt_days(a["timing"]["x20_median"]), fmt_days(a["timing"]["rev5_median"]),
                             fmt_days(a["timing"]["pilot_elapsed_median"]))

    n_amb = len(a["ambiguous"])
    amb_txt = (f' <b>The count may be low.</b> Another {n_amb} {"listing is" if n_amb == 1 else "listings are"} in the same Initial Implementation intake status but labeled Rev5, with no sponsoring agency. One of them describes its own trust center as a FedRAMP 20x trust center, and the same provider also has a separate 20x listing, so the marketplace\'s track label for listings in intake is not reliable.'
               if n_amb else "")

    removed_html = ""
    if a.get("removed"):
        rm = a["removed"]
        rm20 = [r for r in rm if r["track"] == "20x"]
        rm20c = [r for r in rm20 if r["certified"]]
        rows_rm = "".join(
            f'<tr><td>{esc(r["product"])}<br><span class="hide-sm" style="color:var(--ink-soft)">{esc(r["csp"])}</span></td>'
            f'<td>{esc(r["cert_type"])}</td><td>{esc(r["status"])}</td><td class="n">{r["date"] or "—"}</td>'
            f'<td class="n{" zero" if r["n_agencies"] == 0 else ""}">{r["n_agencies"]}</td><td class="n">{r["last_seen"]}</td></tr>'
            for r in rm)
        removed_html = f"""<section class="fig wide" id="removed">
      <h2>Removed from the marketplace</h2>
      <div class="big">
        <div><span class="num gap">{len(rm20)}</span><span class="lbl">20x listings removed since tracking began</span></div>
        <div><span class="num">{len(rm20c)}</span><span class="lbl">of them had been authorized</span></div>
        <div><span class="num">{sum(1 for r in rm20c if r["n_agencies"] == 0)}</span><span class="lbl">authorized, removed, never relied on by an agency</span></div>
      </div>
      <p class="note">Listings that appeared in an earlier snapshot of the marketplace export and are missing from the current one, with their status as last seen. The export does not say why a listing was removed.</p>
      <div class="tbl"><table>
        <thead><tr><th>Product</th><th>Track</th><th>Status when last seen</th><th class="n">Authorized</th><th class="n">Agencies</th><th class="n">Last seen</th></tr></thead>
        <tbody>{rows_rm}</tbody>
      </table></div>
      {prov(a, digest, "comparison of dated marketplace snapshots")}
    </section>
"""

    rev5_since = a["rev5_since"]
    shared_txt = (f' The {esc(shared[0])} appears on all {len(a["adopters"])}.' if len(shared) == 1 else "")
    grc_list = ", ".join(esc(x) for x in a["grc_providers"])
    title = "FedRAMP 20x agency adoption"
    desc = (f'{tw["n"]} FedRAMP 20x authorizations, {tw["with"]} with an agency ATO. '
            f'Updated from the FedRAMP Marketplace on {fmt_date(a["snapshot"])}.')

    return f"""<!DOCTYPE html>
<!-- generated by scripts/fedramp/build_page.py from products-{a["snapshot"]} ({digest[:12]}) at {built}. Do not edit by hand. -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title} | Archstone Security</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{SITE}{PAGE_PATH}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Archstone Security">
<meta property="og:title" content="{esc(h1)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{SITE}{PAGE_PATH}">
<meta name="twitter:card" content="summary">
<meta name="data-snapshot" content="{a["snapshot"]}">
<meta name="data-sha256" content="{digest}">
<link rel="icon" href="/favicon.ico">
<link rel="stylesheet" href="/css/tokens.css">
<style>{CSS}</style>
</head>
<body>
<a href="/" class="site-mast"><img src="/images/logo.png" alt="" height="26"><span>Archstone Security</span></a>
<main class="wrap">
  <p class="eyebrow">Archstone Security · Research · FedRAMP</p>
  <h1>{esc(h1)}</h1>
  <p class="lede">{lede}</p>
  <div class="meta">
    <span><b>Data</b> FedRAMP Marketplace, {fmt_date(a["snapshot"])}</span>
    <span><b>Records</b> {a["records"]:,}</span>
    <span><b>Last checked</b> {fmt_date(a["checked"])}</span>
    <span><a href="20x-products.csv">Download the 20x rows (CSV)</a></span>
  </div>

  <div class="figs">
    <section class="fig wide" id="by-class">
      <h2>Agency adoption of 20x, by class and program</h2>
      <p class="note">Share of authorized 20x products in each class with at least one agency ATO besides the FedRAMP PMO. The filled part of each bar is agency adoption; the rest is authorizations no agency has relied on.</p>
      <div class="cls">{class_rows}</div>
      {prov(a, digest, f'{len(a["tw_cert"])} 20x products with FedRAMP Certified status, by marketplace class')}
    </section>

    <section class="fig wide" id="agencies">
      <h2>Which agencies have relied on 20x</h2>
      <div class="big">
        <div><span class="num gap">{len(a["agency_adopters"])}</span><span class="lbl">agencies with any 20x ATO</span></div>
        <div><span class="num">{a["n_agencies_total"]}</span><span class="lbl">agencies with any FedRAMP ATO on the marketplace</span></div>
      </div>
      <p class="note">Agencies as the marketplace names them, so departments and their components count separately. FedRAMP PMO excluded.{gsa_txt}</p>
      <div class="tbl"><table>
        <thead><tr><th>Agency</th><th>20x products it relies on</th><th class="n">20x ATOs</th><th class="n">Rev5 ATOs</th></tr></thead>
        <tbody>{adopter_rows or '<tr><td colspan="4">No agency other than the FedRAMP PMO is listed on any 20x product.</td></tr>'}</tbody>
      </table></div>
      <h3 class="sub">The ten heaviest Rev5 users</h3>
      <div class="tbl"><table>
        <thead><tr><th>Agency</th><th class="n">Rev5 ATOs</th><th class="n">20x ATOs</th></tr></thead>
        <tbody>{top_rows}</tbody>
      </table></div>
      {prov(a, digest, "Agencies listed on FedRAMP Certified products; each agency counted once per product")}
    </section>

    <section class="fig wide" id="grc-share">
      <h2>How much of 20x is GRC tooling</h2>
      <p class="note">Share of products that are governance, risk and compliance tools, counted two ways. The <b>self-declared tag</b> is the "Governance, Risk, and Compliance (GRC)" business category providers choose for their own marketplace listing; it applies to both tracks the same way. The <b>classification feed</b> is a separately maintained list of providers whose product is compliance automation (feed data as of {fmt_date(a["grc_date"])}); it catches vendors that did not tag themselves, and is applied here to authorized 20x products only.</p>
      <div class="cls">{grc_rows}</div>
      <h3 class="sub">Authorized 20x products counted as GRC, by either method</h3>
      <div class="tbl"><table>
        <thead><tr><th>Product</th><th class="hide-sm">Provider</th><th class="n">Authorized</th><th class="ck">Self-tagged</th><th class="ck">Classified</th><th class="n">Agencies</th></tr></thead>
        <tbody>{grc_prod_rows}</tbody>
      </table></div>
      {prov(a, digest, f'business categories each provider chose for its listing; GRC classification feed, {fmt_date(a["grc_date"])}')}
    </section>

    <section class="fig wide" id="grc-adoption">
      <h2>Which ATOs do agencies prefer for GRC tools?</h2>
      <p class="note">GRC products are those from providers in the GRC classification feed (data as of {fmt_date(a["grc_date"])}), applied identically to both tracks. Agency ATOs exclude the FedRAMP PMO.</p>
      <h3 class="sub">GRC tool adoption by authorization type</h3>
      <p class="note">One block per authorized GRC product, on a common scale. Filled blocks have at least one agency ATO; open blocks have none. A Rev5 agency-path authorization has a sponsoring agency by definition, so that row is filled by construction. Hover a block for the product.</p>
      <div class="legend"><span>{legend_swatch("sb-has")}With an agency ATO</span><span>{legend_swatch("sb-none")}No agency ATO</span></div>
      <div class="sbs gbwrap">{grc_by_type()}</div>
      <h3 class="sub">Every GRC product, one square per agency ATO</h3>
      <p class="note">Hover a square for the agency.</p>
      <div class="tracks">{grc_track_html}</div>
      {prov(a, digest, f'FedRAMP Certified products from providers in the GRC classification feed, {fmt_date(a["grc_date"])}')}
    </section>

    <section class="fig" id="headline">
      <p class="eyebrow">GRC and compliance vendors</p>
      <div class="big">
        <div><span class="num gap">{grc["with"]}</span><span class="lbl">with an agency ATO</span></div>
        <div><span class="num">{grc["n"]}</span><span class="lbl">20x authorizations held by GRC vendors</span></div>
      </div>
      <p class="note">The companies selling 20x readiness hold {grc["n"]} 20x authorizations between them. {"None has" if grc["with"] == 0 else f'{grc["with"]} {"has" if grc["with"] == 1 else "have"}'} an agency customer on it. Vendors counted: {grc_list}.</p>
      {prov(a, digest, f'20x products with FedRAMP Certified status, provider in the GRC classification feed, {fmt_date(a["grc_date"])}')}
    </section>

    <section class="fig" id="pipeline">
      <p class="eyebrow">In the 20x pipeline now</p>
      <div class="big">
        <div><span class="num">{a["pipeline"]["n"]}</span><span class="lbl">20x products in process</span></div>
        <div><span class="num gap">{a["pipeline"]["with"]}</span><span class="lbl">with an agency named</span></div>
      </div>
      <p class="note">Products in Initial Implementation or In Process on the 20x track. A Rev5 agency-path authorization needs a sponsoring agency before it starts; a 20x one does not, and so far none in the queue has one.{amb_txt}</p>
      {prov(a, digest, "20x products not yet certified, excluding Legacy FedRAMP Ready")}
    </section>

    <section class="fig wide" id="dots">
      <h2>Every 20x authorization, one mark each</h2>
      <p class="note">Filled marks have at least one agency ATO besides the FedRAMP PMO. Squares are GRC and compliance vendors. Ordered by authorization date; undated Class A entries last. Hover or focus a mark for the product.</p>
      <div class="legend"><span>{legend_swatch("dot-has")}Agency ATO</span><span>{legend_swatch("dot-none")}No agency ATO</span><span>{legend_swatch("sq")}GRC / compliance vendor</span></div>
      {dot_chart(a)}
      <p class="note" style="margin-top:var(--s-3)">With an agency ATO: {esc(adopters_txt)}.{shared_txt}</p>
      {prov(a, digest, f'{len(a["tw_cert"])} 20x products with FedRAMP Certified status ({dated} dated, {len(a["tw_undated"])} undated)')}
    </section>

    <section class="fig wide" id="monthly">
      <h2>20x authorizations per month</h2>
      <p class="note">By marketplace authorization date, from the first 20x authorization to {fmt_date(a["snapshot"])}. GRC vendors are a large share of what the program has authorized; agency reliance barely registers.</p>
      <div class="legend"><span>{legend_swatch("seg-grc")}GRC / compliance vendors, no agency</span><span>{legend_swatch("seg-other")}Other providers, no agency</span><span>{legend_swatch("seg-agency")}With an agency ATO</span></div>
      <div class="scroll">{bar_chart(a)}</div>
      {prov(a, digest, f'{dated} dated 20x authorizations, {dated_with} with an agency ATO')}
    </section>

    <section class="fig wide" id="timeline">
      <h2>20x moved the certificate, not the finish line.</h2>
      <p class="note">Every row starts on the day the product's marketplace listing entered the process. The grey bar runs to its 20x authorization; the dashed line runs from there to today. The shaded band is where a Rev5 authorization usually lands, middle half of products, measured the same way from the listing date. A Rev5 agency-path authorization comes with its sponsoring agency, so it is the point where an agency is relying on the product. For 20x that point has not arrived.</p>
      <div class="stats3">
        <div><span class="num">{tm_x20}<small>days</small></span><span class="lbl">median to an open 20x authorization ({a["timing"]["x20_n"]} products; pilots excluded because the pilot was invitation-only)</span></div>
        <div><span class="num">{tm_r5}<small>days</small></span><span class="lbl">median to a Rev5 authorization, which arrives with its sponsoring agency</span></div>
        <div><span class="num gap">{tm_pel}<small>days</small></span><span class="lbl">median time since entering for the {a["timing"]["pilot_wait_n"]} pilot products still without an agency; {a["timing"]["pilot_past_rev5"]} are past the Rev5 median</span></div>
      </div>
      <div class="legend"><span>{legend_swatch("tl-proc")}In process</span><span>{legend_swatch("tl-pil")}In process, pilot</span><span>{legend_swatch("tl-auth")}Authorized</span><span>{legend_swatch("tl-tail")}Since authorization, no agency ATO</span><span>{legend_swatch("tl-has")}Has an agency ATO</span><span>{legend_swatch("tl-recert")}Listing re-certified</span><span>{legend_swatch("tl-band")}Rev5, middle half of products</span></div>
      <div class="scroll">{timeline_chart(a)}</div>
      <p class="note" style="margin-top:var(--s-3)">{len(a["tw_cert"]) - len(a["tl_rows"])} authorized 20x {"product is" if len(a["tw_cert"]) - len(a["tl_rows"]) == 1 else "products are"} left out because {"its" if len(a["tw_cert"]) - len(a["tl_rows"]) == 1 else "their"} status history starts at authorization. Agency ATO dates are not in the export, so a filled tail means an agency relies on the product now, not since the date it was authorized. Pilots are included here because the question is how long agency adoption takes, which the invitation did not shorten. Both tracks are timed from the marketplace listing; preparation before a listing appears is not visible on either.</p>
      {prov(a, digest, f'status history of {len(a["tl_rows"])} 20x and {a["timing"]["rev5_n"]} Rev5 listings authorized since {fmt_date(a["first"])}; days counted from each listing\'s first In Process status (Agency Authorization In Process for Rev5)')}
    </section>

    {removed_html}
    <section class="fig wide" id="compare">
      <h2>The obvious objections, answered from the same data</h2>
      <p class="note">"It's too new" and "20x is mostly Low" are the two replies this gets. Both are checked below against Rev5 authorizations issued in the same window. Rev5 agency-path authorizations start with a sponsor by design, so the Rev5 share is close to 100% by construction; the comparison that matters is how far 20x sits from it after the same amount of time.</p>
      <div class="tbl"><table>
        <thead><tr><th>Track</th><th class="n">Authorized</th><th class="n">With agency ATO</th><th class="n">Agency ATOs</th><th class="n">Per authorization</th></tr></thead>
        <tbody>{"".join(comp_rows)}</tbody>
      </table></div>
      {prov(a, digest, "FedRAMP Certified products with an authorization date; FedRAMP PMO excluded from agency counts")}
    </section>

    <section class="fig wide" id="dual">
      <h2>Same product, both tracks</h2>
      <p class="note">Products that hold a listing on each track. Where agencies are relying on one of these products, they are relying on its Rev5 authorization.</p>
      <div class="tbl"><table>
        <thead><tr><th>Product</th><th>Rev5 listing</th><th class="n">Rev5 agencies</th><th>20x listing</th><th class="n">20x agencies</th></tr></thead>
        <tbody>{"".join(dual_rows) or '<tr><td colspan="5">No products are listed on both tracks in this export.</td></tr>'}</tbody>
      </table></div>
      {prov(a, digest, "Matched on provider and product name, or 20x record ID equal to the Rev5 ID plus a suffix")}
    </section>

    <section class="fig wide" id="list">
      <h2>All authorized 20x products</h2>
      <p class="note">Products with an agency ATO first, then by authorization date.</p>
      <div class="list tbl"><table>
        <thead><tr><th class="n">Authorized</th><th>Product</th><th class="hide-sm">Provider</th><th class="hide-sm">Track</th><th class="hide-sm">Class</th><th class="hide-sm">Impact</th><th class="n">Agencies</th><th class="hide-sm">Which</th><th class="hide-sm">Assessor</th></tr></thead>
        <tbody>{"".join(list_rows)}</tbody>
      </table></div>
      {prov(a, digest, "20x and 20x Pilot products with FedRAMP Certified status")}
    </section>
  </div>

  <section class="read" id="method">
    <h2>How these numbers are made</h2>
    <ul>
      <li><b>Source.</b> The FedRAMP Marketplace's own JSON export, downloaded on a schedule and kept as dated snapshots. The page is rebuilt whenever the export changes.</li>
      <li><b>Agency ATO</b> means an agency other than the FedRAMP PMO listed on the product. The PMO records an agency use on every 20x authorization, so the marketplace's own authorization count shows at least one for every 20x product. That entry is removed everywhere on this page.</li>
      <li><b>Authorization date</b> is the marketplace's certification date for the product. The export lists the agencies on each product but not the date each agency signed, so this measures reliance as it stands today, not when it happened.</li>
      <li><b>GRC and compliance vendors</b> are identified from a separately maintained provider classification feed (data as of {fmt_date(a["grc_date"])}), matched by provider name, and shown alongside the GRC business category providers choose for their own marketplace listings.</li>
      <li><b>Reclassification.</b> No 20x record in the current export carries status history from before 2025 or an agency ATO inherited from a Rev5 authorization. Products the marketplace lists on both tracks are shown above; their agencies count toward Rev5. Snapshots are kept so that a record converted in place will show up when two exports are compared.</li>
      <li><b>Track labels for new listings.</b> Listings in the Initial Implementation intake status carry a Rev5 or 20x label that does not always match the program the provider is pursuing, and at least one provider is listed twice, once on each track. Authorized products and agency ATOs are not affected; counts of products still in process should be read as approximate.</li>
      <li><b>Limits.</b> Withdrawn and expired products are not in the export. Class A 20x entries without an authorization date are included in totals and left out of anything plotted by date.</li>
    </ul>
  </section>

  <footer>
    <span>Archstone Security</span>
    <span>Data as of {fmt_date(a["snapshot"])}</span>
    <span><a href="{MARKETPLACE_URL}">FedRAMP Marketplace</a></span>
    <span><a href="/research.html">More research</a></span>
    <span><a href="mailto:contact@archstonesecurity.com?subject=20x%20adoption%20%E2%80%94%20correction">Corrections welcome</a></span>
  </footer>
</main>
</body>
</html>
"""


def find_removed(raw_dir: Path, current: Path, products: list[dict], grc: set[str]) -> list[dict]:
    """Listings present in an earlier snapshot and absent from the current one, with their last-seen state."""
    now_ids = {p["id"] for p in products}
    cur_date = snapshot_date(current)
    last_seen: dict[str, tuple[str, dict]] = {}
    for f in sorted(raw_dir.glob("products-*.json.gz")):
        d = snapshot_date(f)
        if d >= cur_date:
            continue
        try:
            prods, _ = load_snapshot(f)
        except SystemExit:
            continue
        for p in prods:
            if p["id"] not in now_ids:
                last_seen[p["id"]] = (d, p)
    out = []
    for pid, (d, p) in last_seen.items():
        r = normalise(p, grc)
        r["last_seen"] = d
        out.append(r)
    out.sort(key=lambda r: (r["track"] != "20x", not r["certified"], r["product"].lower()))
    return out


def write_csv(a: dict, path: Path) -> None:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["snapshot", "id", "provider", "product", "cert_type", "status", "class", "impact",
                "authorized", "grc_vendor", "grc_self_tagged", "agency_count", "agencies", "assessor"])
    for p in sorted(a["tw_cert"], key=lambda r: (r["date"] or "9999", r["product"].lower())):
        w.writerow([a["snapshot"], p["id"], p["csp"], p["product"], p["cert_type"], p["status"], p["cls"],
                    p["impact"], p["date"], "yes" if p["grc"] else "no", "yes" if p["grc_tag"] else "no", p["n_agencies"],
                    "; ".join(p["agencies"]), p["assessor"]])
    path.write_text(buf.getvalue(), encoding="utf-8")


def update_history(a: dict, digest: str, path: Path) -> None:
    fields = ["snapshot", "sha256", "records", "x20_authorized", "x20_with_agency", "x20_agency_atos",
              "grc_authorized", "grc_with_agency", "x20_in_process", "rev5_since_first_20x",
              "rev5_since_with_agency", "x20_removed_total"]
    rows = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["snapshot"] != a["snapshot"]]
    rows.append({
        "snapshot": a["snapshot"], "sha256": digest, "records": a["records"],
        "x20_authorized": a["tw_stats"]["n"], "x20_with_agency": a["tw_stats"]["with"],
        "x20_agency_atos": a["tw_stats"]["atos"], "grc_authorized": a["grc_stats"]["n"],
        "grc_with_agency": a["grc_stats"]["with"], "x20_in_process": a["pipeline"]["n"],
        "rev5_since_first_20x": a["rev5_since"]["n"], "rev5_since_with_agency": a["rev5_since"]["with"],
        "x20_removed_total": sum(1 for r in a.get("removed", []) if r["track"] == "20x"),
    })
    rows.sort(key=lambda r: r["snapshot"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--snapshot", required=True, type=Path)
    ap.add_argument("--grc", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--history", type=Path)
    ap.add_argument("--raw-dir", type=Path, help="directory of earlier snapshots, to find listings removed since")
    ap.add_argument("--checked", help="date the marketplace was last checked (YYYY-MM-DD); defaults to the snapshot date")
    args = ap.parse_args()

    products, digest = load_snapshot(args.snapshot)
    snap = snapshot_date(args.snapshot)
    grc_feed = json.loads(args.grc.read_text())
    grc = {s.strip().lower() for s in grc_feed["providers"]}
    rows = [normalise(p, grc) for p in products]
    a = analyse(rows, snap)
    a["checked"] = args.checked or snap
    a["grc_date"] = grc_feed.get("updated") or snap
    a["removed"] = find_removed(args.raw_dir, args.snapshot, products, grc) if args.raw_dir else []

    built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "index.html").write_text(render(a, digest, built), encoding="utf-8")
    write_csv(a, args.out / "20x-products.csv")
    if args.history:
        update_history(a, digest, args.history)

    print(f"build_page: {snap}: {a['tw_stats']['n']} 20x authorized, {a['tw_stats']['with']} with agency; "
          f"GRC {a['grc_stats']['with']}/{a['grc_stats']['n']}; pipeline {a['pipeline']['n']}")


if __name__ == "__main__":
    main()
