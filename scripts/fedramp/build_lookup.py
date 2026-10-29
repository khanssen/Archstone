#!/usr/bin/env python3
"""Build /fedramp-lookup/: a searchable list of every FedRAMP Marketplace listing with a usability chart per listing.

Reads the latest marketplace snapshot, the hand-maintained rules
(data/fedramp/usability-rules.json) and corrections/disclosures
(data/fedramp/lookup-overrides.json), assigns each listing one rules case,
and writes:

  <out>/listings.json   slim per-listing data plus the rules the page renders
  <out>/index.html      the page itself, with the homepage navigation copied in

The verdicts are decided here, not in the browser, so they can be tested and
reviewed in a diff. The page only displays them.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_page as bp  # noqa: E402  (shared loaders, nav and assessor matching)

PAGE_PATH = "/fedramp-lookup/"
STATES = {"lev", "dec", "no", "wait"}
OVERRIDABLE = ("cert_type", "cert_class", "impact_level", "status")
CLASS_TO_LEVEL = {"Class D": "High", "Class C": "Moderate", "Class B": "Low"}
LEVEL_CASE = {"High": "trad_high", "Moderate": "trad_mod", "Low": "trad_low", "LI-SaaS": "trad_low"}


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------

def load_rules(path: Path) -> dict:
    rules = json.loads(path.read_text(encoding="utf-8"))
    rows = [r["key"] for r in rules["rows"]]
    if set(rules["states"]) != STATES:
        sys.exit(f"build_lookup: rules states must be exactly {sorted(STATES)}")
    for r in rules["rows"]:
        if set(r["cite"]) != {"trad", "20x", "hosted"}:
            sys.exit(f"build_lookup: row {r['key']} needs a 'trad', a '20x' and a 'hosted' citation")
    if "hosted" not in rules["cases"] or not all(rules.get(k) for k in ("hosted_banner", "host_banner", "pilot_banner")):
        sys.exit("build_lookup: rules need a 'hosted' case, a hosted_banner, a host_banner and a pilot_banner")
    for name, case in rules["cases"].items():
        missing = set(rows) - set(case)
        extra = set(case) - set(rows)
        if missing or extra:
            sys.exit(f"build_lookup: case {name} rows mismatch (missing {sorted(missing)}, extra {sorted(extra)})")
        for k, (state, note) in case.items():
            if state not in STATES or not note.strip():
                sys.exit(f"build_lookup: case {name} row {k} has state {state!r} or an empty note")
    return rules


def is_trad(cert_type: str) -> bool:
    return cert_type == "Rev5"


def assign_case(r: dict) -> tuple[str, str]:
    """Rules case for an (already corrected) listing, plus the level inferred from its class label, if any.

    Track decides before class: anything that is not the traditional (Rev5) track is
    judged as 20x, so an unexpected new track label can never earn a CUI tick.
    """
    status = r["status"]
    if status == "Legacy FedRAMP Ready":
        return "legacy_ready", ""
    if not status.startswith("FedRAMP Certified"):
        return "not_certified", ""
    if is_trad(r["cert_type"]):
        if r["impact_level"] in LEVEL_CASE:
            return LEVEL_CASE[r["impact_level"]], ""
        inferred = CLASS_TO_LEVEL.get(r["cert_class"], "")
        return (LEVEL_CASE[inferred], inferred) if inferred else ("trad_unknown", "")
    letter = (r["cert_class"] or "").replace("Class", "").strip()
    # Pilot listings were certified before classes existed and later relabeled; they get their own cases.
    if r["cert_type"] == "20x Pilot" and letter in ("B", "C"):
        return f"x20p_{letter}", ""
    return (f"x20_{letter}", "") if letter in ("A", "B", "C", "D") else ("x20_unknown", "")


# --------------------------------------------------------------------------
# Listings
# --------------------------------------------------------------------------

def track_label(cert_type: str) -> str:
    return bp.trk(cert_type) if cert_type else "Unknown"


def build_listings(products: list[dict], rules: dict, ov: dict) -> list[dict]:
    overrides, disclosures = ov.get("overrides", {}), ov.get("disclosures", {})
    ids = {p["id"] for p in products}
    for k in list(overrides) + list(disclosures):
        if k not in ids:
            print(f"build_lookup: {k} in lookup-overrides.json is not in this snapshot", file=sys.stderr)

    out = []
    for p in products:
        rec = {f: (p.get(f) or "") for f in OVERRIDABLE}
        corrected = {}
        o = overrides.get(p["id"])
        if o:
            if not str(o.get("note", "")).strip():
                sys.exit(f"build_lookup: override for {p['id']} has no public note")
            for f in OVERRIDABLE:
                if f in o and o[f] != rec[f]:
                    corrected[f] = [rec[f], o[f]]
                    rec[f] = o[f]
        case, inferred = assign_case(rec)
        agencies = [a for a in (p.get("agency_authorizations") or []) if a and a != bp.PMO]
        kind, name = bp.classify_assessor(p.get("independent_assessor") or "")
        out.append({
            "id": p["id"],
            "p": (p.get("csp") or "").strip(),
            "n": (p.get("cso") or "").strip(),
            "pk": bp.provider_key(p.get("csp") or ""),
            "t": rec["cert_type"],
            "tl": track_label(rec["cert_type"]),
            "tk": "trad" if is_trad(rec["cert_type"]) else "20x",
            "s": rec["status"],
            "c": rec["cert_class"] if rec["cert_class"] != "Unknown" else "",
            "i": rec["impact_level"] if rec["impact_level"] != "Unknown" else "",
            "path": p.get("cert_path") or "",
            # Some 20x listings carry no cert_date; fall back to the first "Certified" event in the status log.
            "d": ((p.get("cert_date") or "")[:10] or bp.timeline(p, p.get("cert_type") == "Rev5")["first_cert"])
                 if str(rec["status"]).startswith("FedRAMP Certified") else "",
            "ag": agencies,
            "a": bp.assessor_label(name) if kind == "3pao" else name,
            "case": case,
            "inf": inferred,
            "cui": rules["cases"][case]["cuiD"][0] == "lev",
            **({"ov": {"fields": corrected, "note": o["note"]}} if o else {}),
            **({"dis": disclosures[p["id"]]} if p["id"] in disclosures else {}),
        })
    out.sort(key=lambda r: (not r["s"].startswith("FedRAMP Certified"), r["p"].lower(), r["n"].lower()))
    return out


_URL_TAIL = re.compile(r"\s+-\s+https?://\S+$")
_PROVIDED_BY = re.compile(r"^\s*provided\s+(?:and|&)\s+managed\s+by\s+([^,.]+)", re.I)


def norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower().replace("™", "").replace("®", "")).strip()


def add_services(products: list[dict], listings: list[dict], hosted_cfg: dict) -> list[dict]:
    """Attach marketplace service lists to their listings and split out hosted third-party products.

    A host's own components stay search aliases of the host listing. Every other service on a
    designated host is a hosted product: it gets its own search result and card, decided by the
    rules' 'hosted' case, never by the host's verdicts.
    """
    hosts = hosted_cfg.get("hosts", {})
    by_id = {r["id"]: r for r in listings}
    for k in hosts:
        if k not in by_id:
            print(f"build_lookup: host {k} in hosted-services.json is not in this snapshot", file=sys.stderr)
    # Names a hosted product might also carry as a listing of its own.
    names: dict[str, str] = {}
    for r in listings:
        for n in (r["n"], r["p"]):
            names.setdefault(norm_name(n), r["id"])

    hosted = []
    for p in products:
        r = by_id[p["id"]]
        svcs = [s for s in (p.get("certified_services") or []) if (s.get("serviceName") or "").strip()]
        own, cfg = [], hosts.get(p["id"])
        for s in svcs:
            name = _URL_TAIL.sub("", s["serviceName"].strip())
            if not cfg or any(name.startswith(pre) for pre in cfg.get("own_prefix", [])):
                own.append(name)
                continue
            desc = (s.get("serviceDescription") or "").strip()
            m = _PROVIDED_BY.match(desc)
            hid = f"{p['id']}~{re.sub(r'[^A-Za-z0-9]+', '-', name).strip('-')[:48]}"
            hosted.append({
                "id": hid,
                "kind": "h",
                "p": m.group(1).strip() if m else "",
                "n": name,
                "pk": "",
                "t": "hosted",
                "tl": "Hosted product",
                "tk": "hosted",
                "s": "Hosted service",
                "host": p["id"],
                "since": (s.get("dateAvailable") or "")[:10],
                "own": names.get(norm_name(name), ""),
                "case": "hosted",
                "cui": False,
            })
        if own:
            r["sv"] = own
        hp = [h["id"] for h in hosted if h["host"] == p["id"]]
        if hp:
            r["hp"] = hp
    hosted.sort(key=lambda h: h["n"].lower())
    return hosted


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------

PAGE = r"""<!DOCTYPE html>
<!-- generated by scripts/fedramp/build_lookup.py from %%SNAPNAME%% (%%DIGEST%%). Do not edit by hand. -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>FedRAMP Marketplace usability lookup | Archstone Security</title>
<meta name="description" content="What every FedRAMP Marketplace listing can actually be used for: federal data by impact level and CUI, by published rule. %%N%% listings, updated %%SNAPHUMAN%%.">
<link rel="canonical" href="%%SITE%%%%PATH%%">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Archstone Security">
<meta property="og:title" content="What can this FedRAMP listing actually be used for?">
<meta property="og:description" content="Federal data by impact level and CUI, for every marketplace listing, by published rule. Updated %%SNAPHUMAN%%.">
<meta property="og:url" content="%%SITE%%%%PATH%%">
<meta name="data-snapshot" content="%%SNAP%%">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="96x96" href="/favicon/favicon-96x96.png">
<link rel="apple-touch-icon" href="/favicon/apple-touch-icon.png">
<link rel="preload" href="/font/IBMPlexSans-Regular.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/font/IBMPlexSans-SemiBold.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/font/IBMPlexMono-Medium.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="listings.json?v=%%SNAP%%" as="fetch" crossorigin>
<link rel="stylesheet" href="/css/tokens.css">
<style>
%%NAVCSS%%
.wrap{max-width:1240px;margin:0 auto;padding:var(--s-6) max(20px,env(safe-area-inset-right,0px)) var(--s-7) max(20px,env(safe-area-inset-left,0px))}
.eyebrow{margin:0 0 var(--s-3)}
h1{margin:0;max-width:24ch}
.lede{font-size:var(--t-lede);color:var(--ink-soft);margin:var(--s-4) 0 0}
.pmo{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--s-3);margin:var(--s-5) 0 0}
@media (max-width:760px){.pmo{grid-template-columns:1fr}}
.pmo blockquote{margin:0;background:var(--surface);border:1px solid var(--rule);border-left:0;border-radius:10px;padding:var(--s-3) var(--s-4)}
.pmo p{margin:0;font-weight:600;max-width:none}
.pmo cite{display:block;margin-top:var(--s-2);font:500 var(--t-micro)/1.4 var(--mono);letter-spacing:.06em;color:var(--ink-soft);font-style:normal}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}

.lk{display:grid;grid-template-columns:minmax(300px,400px) minmax(0,1fr);gap:var(--s-4);margin-top:var(--s-5);align-items:start}
.lk-list{background:var(--surface);border:1px solid var(--rule);border-radius:10px;display:flex;flex-direction:column;position:sticky;top:12px;max-height:calc(100vh - 24px)}
.lk-tools{padding:var(--s-3);border-bottom:1px solid var(--rule);display:grid;gap:var(--s-2)}
.lk-tools input[type=search]{width:100%;font:inherit;font-size:16px;padding:10px 12px;border:1px solid var(--rule-strong);border-radius:8px;background:var(--paper);color:var(--ink)}
.lk-f{display:flex;flex-wrap:wrap;gap:var(--s-2)}
.lk-f select{font:inherit;font-size:var(--t-small);padding:8px 10px;border:1px solid var(--rule-strong);border-radius:8px;background:var(--surface);color:var(--ink);min-height:40px;flex:1 1 130px}
.lk-f label.ck{display:flex;align-items:center;gap:8px;font-size:var(--t-small);min-height:40px;padding:0 4px;cursor:pointer;flex:1 1 100%}
.lk-f label.ck input{width:18px;height:18px;margin:0}
.lk-count{margin:0;font:500 var(--t-micro)/1.4 var(--mono);letter-spacing:.06em;color:var(--ink-soft)}
.lk-items{list-style:none;margin:0;padding:0;overflow-y:auto;flex:1 1 auto;min-height:200px}
.lk-items li+li{border-top:1px solid var(--rule)}
.lk-it{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px var(--s-2);width:100%;text-align:left;font:inherit;color:var(--ink);background:none;border:0;padding:12px var(--s-3);cursor:pointer;min-height:44px}
.lk-it:hover{background:var(--referent-fill)}
.lk-it[aria-current="true"]{background:var(--ink);color:#fff}
.lk-it[aria-current="true"] .mt{color:#D5DEE5}
.lk-it .pv{font-weight:600;font-size:var(--t-body);min-width:0;overflow-wrap:anywhere}
.lk-it .pr{grid-column:1/-1;font-size:var(--t-small);overflow-wrap:anywhere}
.lk-it .mt{grid-column:1/-1;font:var(--t-micro)/1.4 var(--mono);color:var(--ink-soft)}
.lk-it .cuitag{align-self:start;font:500 var(--t-micro)/1 var(--mono);padding:4px 6px;border-radius:5px;border:1px solid var(--referent);color:var(--referent);background:var(--referent-fill);white-space:nowrap}
.lk-it[aria-current="true"] .cuitag{border-color:#fff;color:#fff;background:transparent}
.lk-it .htag{align-self:start;font:500 var(--t-micro)/1 var(--mono);padding:4px 6px;border-radius:5px;border:1px dashed var(--gap);color:var(--gap);background:var(--gap-fill);white-space:nowrap}
.lk-it[aria-current="true"] .htag{border-color:#fff;color:#fff;background:transparent}
.lk-none{padding:var(--s-4) var(--s-3);color:var(--ink-soft);font-size:var(--t-small)}

.lk-panel{background:var(--surface);border:1px solid var(--rule);border-radius:12px;padding:var(--s-4);position:sticky;top:12px;max-height:calc(100vh - 24px);overflow-y:auto;min-width:0}
.lk-panel:focus{outline:none}
.lk-empty h2{margin:0 0 var(--s-2)}
.lk-empty p{color:var(--ink-soft);margin:0 0 var(--s-3)}
.back{display:none;align-items:center;gap:6px;font:inherit;font-weight:600;color:var(--referent);background:none;border:0;padding:8px 0;margin:0 0 var(--s-2);cursor:pointer;min-height:44px}
.cd-hd{display:flex;flex-wrap:wrap;justify-content:space-between;gap:var(--s-2) var(--s-4);align-items:baseline}
.cd-hd h2{margin:0;font-size:26px;overflow-wrap:anywhere}
.cd-hd .by{margin:var(--s-1) 0 0;color:var(--ink-soft)}
.facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:8px;overflow:hidden;margin:var(--s-4) 0 0}
@media (max-width:1100px){.facts{grid-template-columns:repeat(2,minmax(0,1fr))}}
.facts div{background:var(--paper);padding:10px 12px;min-width:0}
.facts dt{font:500 var(--t-micro)/1.4 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--ink-soft)}
.facts dd{margin:3px 0 0;font-weight:600;overflow-wrap:anywhere}
.facts dd small{display:block;font-weight:400;font-size:var(--t-small);color:var(--ink-soft)}
.bn{margin:var(--s-3) 0 0;padding:12px 14px;border-radius:8px;font-size:var(--t-small);line-height:1.55;max-width:none;border:1px solid var(--rule-strong);background:var(--referent-fill)}
.bn.warn{border:2px solid var(--gap);background:var(--gap-fill);margin-top:var(--s-4)}
.bn.warn b{color:var(--gap)}
.lk-warn{padding:12px var(--s-3);font-size:var(--t-small);line-height:1.5;background:var(--gap-fill);border-bottom:2px solid var(--gap)}
.lk-warn b{color:var(--gap)}
.bn.mine{border:1px solid var(--accent);background:var(--accent-fill)}
.bn.mine b{color:var(--accent)}
.bn ul{margin:6px 0 0;padding:0;list-style:none;display:grid;gap:4px}
.facts .lnk{font:inherit;font-weight:600;color:var(--referent);background:none;border:0;padding:0;text-align:left;text-decoration:underline;text-underline-offset:2px;cursor:pointer}
.bn button{font:inherit;color:var(--referent);background:none;border:0;padding:4px 0;text-align:left;text-decoration:underline;text-underline-offset:2px;cursor:pointer;min-height:32px}
.ch{margin:var(--s-4) 0 0}
.ch .r{display:grid;grid-template-columns:minmax(0,1.1fr) 200px minmax(0,1.4fr);gap:var(--s-2) var(--s-4);align-items:center;padding:14px 0;border-bottom:1px solid var(--rule)}
.ch .r.gate{border-bottom:2px solid var(--ink)}

@media (max-width:1100px){.ch .r{grid-template-columns:minmax(0,1fr) auto}.ch .r .nt{grid-column:1/-1}}
.ch .q{margin:0;font-weight:600;max-width:none}
.ch .ct{margin:3px 0 0;font:var(--t-micro)/1.4 var(--mono);color:var(--ink-soft);max-width:none}
.ch .nt{margin:0;font-size:var(--t-small);max-width:none}
.bd{display:inline-flex;align-items:center;gap:6px;padding:5px 11px;border-radius:999px;font-size:var(--t-small);font-weight:600;border-width:2px;white-space:nowrap}
.bd .ic{font-family:var(--mono);font-weight:500}
.bd.lev{border-style:solid;border-color:var(--referent);background:var(--referent);color:#fff}
.bd.dec{border-style:dashed;border-color:var(--partial);background:var(--partial-fill);color:var(--partial)}
.bd.no{border-style:solid;border-color:var(--gap);background:var(--gap-fill);color:var(--gap)}
.bd.wait{border-style:dotted;border-color:var(--manual);background:var(--surface);color:var(--manual)}
.legend{display:flex;flex-wrap:wrap;gap:var(--s-2) var(--s-3);margin:var(--s-3) 0 0}
.ags{margin:var(--s-4) 0 0}
.ags h3{margin:0 0 var(--s-2);font-size:var(--t-body)}
.ags ul{margin:0;padding-left:1.2em;columns:2 280px;column-gap:var(--s-5)}
.ags li{font-size:var(--t-small);margin:0 0 4px;break-inside:avoid}
.ags .ct{margin:var(--s-2) 0 0;font:var(--t-micro)/1.4 var(--mono);color:var(--ink-soft);max-width:none}
.fn{margin:var(--s-4) 0 0;padding-top:var(--s-3);border-top:1px solid var(--rule);display:grid;gap:var(--s-2)}
.fn p{margin:0;font-size:var(--t-small);color:var(--ink-soft);max-width:none}
.fn b{color:var(--ink)}

@media (max-width:860px){
  .lk{grid-template-columns:1fr}
  .lk-list{position:static;max-height:none}
  .lk-items{max-height:70vh}
  .lk-panel{display:none}
  body.lk-open{overflow:hidden}
  body.lk-open .lk-panel{display:block;position:fixed;inset:0;z-index:100;border-radius:0;border:0;max-height:none;padding:var(--s-3) max(16px,env(safe-area-inset-right,0px)) var(--s-6) max(16px,env(safe-area-inset-left,0px))}
  .back{display:inline-flex}
  .lk-empty{display:none}
}
footer{display:flex;flex-wrap:wrap;gap:var(--s-2) var(--s-4);margin-top:var(--s-6);padding-top:var(--s-3);border-top:1px solid var(--rule);font-size:var(--t-small);color:var(--ink-soft)}
</style>
</head>
<body>
%%NAV%%
<main class="wrap">
  <p class="eyebrow">FedRAMP Marketplace · usability lookup · snapshot %%SNAPHUMAN%%</p>
  <h1>What can this listing actually be used for?</h1>
  <p class="lede">Every listing on the FedRAMP Marketplace, checked against the published rules for federal data and CUI. Pick one to see what its authorization supports and what it doesn’t. Each answer cites the rule it comes from.</p>
  <div class="pmo">
    <blockquote><p>Certification Classes indicate the level of assurance provided, not the level of security or protection provided.</p><cite>FedRAMP CR26 · Certification Classes</cite></blockquote>
    <blockquote><p>Agencies should not treat Certification Classes as one-for-one replacements for Low, Moderate, or High impact levels.</p><cite>FedRAMP CR26 · Certification Classes</cite></blockquote>
  </div>

  <div class="lk">
    <section class="lk-list" aria-label="Marketplace listings">
      <div class="lk-tools">
        <label class="sr" for="lk-q">Search listings</label>
        <input id="lk-q" type="search" placeholder="Search provider, product, assessor or FR ID" autocomplete="off" spellcheck="false">
        <div class="lk-f">
          <label class="sr" for="lk-track">Track</label>
          <select id="lk-track">
            <option value="">All tracks</option>
            <option value="Rev5">Traditional</option>
            <option value="20x">20x</option>
            <option value="20x Pilot">20x Pilot</option>
            <option value="hosted">Hosted products (no listing of their own)</option>
          </select>
          <label class="sr" for="lk-status">Status</label>
          <select id="lk-status">
            <option value="">Any status</option>
            <option value="cert">Certified</option>
            <option value="ip">In process</option>
            <option value="ii">Initial implementation</option>
            <option value="ready">Legacy FedRAMP Ready</option>
          </select>
          <label class="ck"><input id="lk-cui" type="checkbox"> Meets DFARS 7012 for CUI</label>
        </div>
        <p class="lk-count" id="lk-count" aria-live="polite">Loading %%N%% listings…</p>
      </div>
      <ul class="lk-items" id="lk-items"></ul>
    </section>

    <section class="lk-panel" id="lk-panel" aria-label="Usability chart" tabindex="-1">
      <div class="lk-empty" id="lk-empty">
        <h2>Pick a listing</h2>
        <p>The chart answers six questions for the listing you choose. A ✓ means an agency can start from the package. It never replaces the agency’s own ATO.</p>
        <div class="legend" id="lk-legend"></div>
      </div>
      <div id="lk-card" hidden></div>
    </section>
  </div>
  <noscript><p class="lede">This lookup needs JavaScript. The data behind it is at <a href="listings.json">listings.json</a>.</p></noscript>

  <p class="prov"><span>FedRAMP Marketplace export %%SNAPHUMAN%%</span><span>sha256 %%DIGEST%%</span><span>%%N%% listings</span><span>rules: data/fedramp/usability-rules.json</span></p>
  <footer>
    <span>Archstone Security</span>
    <span>Data as of %%SNAPHUMAN%%</span>
    <span><a href="%%MARKET%%">FedRAMP Marketplace</a></span>
    <span><a href="/fedramp-20x-adoption/">20x adoption, by the numbers</a></span>
    <span><a href="mailto:contact@archstonesecurity.com?subject=Marketplace%20lookup%20%E2%80%94%20correction">Corrections welcome</a></span>
  </footer>
</main>
%%NAVJS%%
<script>
(function () {
  var MARKET = '%%MARKET%%';
  var DATA = null, ALL = [], byId = {}, rowsEl = document.getElementById('lk-items');
  var q = document.getElementById('lk-q'), fTrack = document.getElementById('lk-track'),
      fStatus = document.getElementById('lk-status'), fCui = document.getElementById('lk-cui'),
      count = document.getElementById('lk-count'), panel = document.getElementById('lk-panel'),
      card = document.getElementById('lk-card'), empty = document.getElementById('lk-empty');
  var selected = null, lastBtn = null;
  var mobile = window.matchMedia('(max-width: 860px)');

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function fmtDate(d) {
    if (!d) return '';
    var m = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    var p = d.split('-');
    return (+p[2]) + ' ' + m[+p[1] - 1] + ' ' + p[0];
  }
  function statusGroup(s) {
    if (s === 'Hosted service') return 'hosted';
    if (s.indexOf('FedRAMP Certified') === 0) return 'cert';
    if (s === 'Legacy FedRAMP Ready') return 'ready';
    if (s === 'Initial Implementation') return 'ii';
    return 'ip';
  }
  function shortStatus(s) {
    return { cert: 'Certified', ready: 'Legacy Ready', ii: 'Initial implementation', ip: 'In process', hosted: 'No listing of its own' }[statusGroup(s)];
  }
  function levelText(r) {
    if (r.kind === 'h') return 'inside ' + byId[r.host].n;
    if (r.tk === 'trad') return r.i || r.c || 'Level not listed';
    return r.c || 'Class not assigned';
  }
  function fill(t, r) {
    var h = r.kind === 'h' ? byId[r.host] : null;
    return t.split('{status}').join(r.s).split('{host}').join(h ? h.n : '')
      .split('{hostProvider}').join(h ? h.p.replace(/\.$/, '') : '').split('{hostId}').join(h ? h.id : '')
      .split('{service}').join(r.n);
  }
  function hasTerm(hay, t) { return /\d/.test(t) ? hay.indexOf(t) >= 0 : hay.indexOf(' ' + t) >= 0; }
  function badge(state) {
    var s = DATA.rules.states[state];
    return '<span class="bd ' + state + '"><span class="ic" aria-hidden="true">' + esc(s.icon) + '</span>' + esc(s.label) + '</span>';
  }

  function matches(r, terms) {
    if (fTrack.value && r.t !== fTrack.value) return false;
    if (fStatus.value && statusGroup(r.s) !== fStatus.value) return false;
    if (fCui.checked && !r.cui) return false;
    // Words match from their start ("vanta" finds Vanta, not Advantage); anything with a digit
    // matches anywhere, so a partial FR ID still finds its listing.
    for (var i = 0; i < terms.length; i++) if (!hasTerm(r._hay, terms[i])) return false;
    return true;
  }

  function renderList() {
    var terms = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    var shown = ALL.filter(function (r) { return matches(r, terms); });
    var html = shown.map(function (r) {
      var cur = selected && selected.id === r.id ? 'true' : 'false';
      if (r.kind === 'h') {
        var h = byId[r.host];
        return '<li><button type="button" class="lk-it" data-id="' + esc(r.id) + '" aria-current="' + cur + '">' +
          '<span class="pv">' + esc(r.n) + '</span><span class="htag" title="No FedRAMP listing of its own">Hosted</span>' +
          '<span class="pr">' + (r.p ? 'by ' + esc(r.p) : 'Vendor not stated') + '</span>' +
          '<span class="mt">Hosted product · inside ' + esc(h.n) + ' (' + esc(h.p.replace(/\.$/, '')) + ')</span></button></li>';
      }
      // Say why a listing matched when the hit was one of its listed services, not its name.
      var via = '';
      if (terms.length && r.sv && !terms.every(function (t) { return hasTerm(r._base, t); })) {
        var hit = r.sv.filter(function (n) { var hay = ' ' + n.toLowerCase().replace(/[^a-z0-9]+/g, ' '); return terms.some(function (t) { return hasTerm(hay, t); }); });
        if (hit.length) via = '<span class="mt">Listed service: ' + esc(hit.slice(0, 2).join('; ')) + '</span>';
      }
      return '<li><button type="button" class="lk-it" data-id="' + esc(r.id) + '" aria-current="' + cur + '">' +
        '<span class="pv">' + esc(r.p) + '</span>' +
        (r.cui ? '<span class="cuitag" title="Meets DFARS 7012 for CUI">7012 ✓</span>' : '<span></span>') +
        '<span class="pr">' + esc(r.n) + '</span>' +
        '<span class="mt">' + esc(r.tl) + ' · ' + esc(levelText(r)) + ' · ' + esc(shortStatus(r.s)) + '</span>' + via +
        '</button></li>';
    }).join('');
    var idHosts = terms.length === 1 && /^[a-z]*\d{6,}[a-z]*$/.test(terms[0])
      ? DATA.listings.filter(function (r) { return r.hp && r.id.toLowerCase().indexOf(terms[0]) >= 0; }) : [];
    var notice = idHosts.map(function (h) {
      return '<li class="lk-warn"><b>' + esc(h.id) + ' is ' + esc(h.n) + ' (' + esc(h.p.replace(/\.$/, '')) + ').</b> ' +
        h.hp.length + ' other vendors’ products are listed inside it with no FedRAMP listing of their own. ' +
        'If a vendor gave you this ID for their product, it is the host’s ID; find the product below.</li>';
    }).join('');
    rowsEl.innerHTML = notice + (html || '<li class="lk-none">No listings match. Try fewer words or clear a filter.</li>');
    var nl = DATA.listings.length, nh = DATA.hosted.length;
    count.textContent = shown.length === ALL.length
      ? nl + ' listings · ' + nh + ' hosted products'
      : shown.length + ' of ' + ALL.length + ' results';
  }

  function banners(r) {
    var b = [];
    if (r.ov) {
      var bits = Object.keys(r.ov.fields).map(function (f) {
        var v = r.ov.fields[f];
        return esc(f.replace('cert_', '').replace('_', ' ')) + ' “' + esc(v[0] || 'blank') + '” → “' + esc(v[1]) + '”';
      });
      b.push('<p class="bn mine"><b>Corrected by Archstone.</b> ' + (bits.length ? 'Marketplace ' + bits.join('; ') + '. ' : '') + esc(r.ov.note) + '</p>');
    }
    if (r.dis) b.push('<p class="bn mine"><b>Disclosure.</b> ' + esc(r.dis) + '</p>');
    var certified = statusGroup(r.s) === 'cert';
    if (r.tk === 'trad' && certified && r.c && r.i) {
      b.push('<p class="bn"><b>Same label, different meaning.</b> The marketplace now labels traditional listings with a class too. Here “' +
        esc(r.c) + '” stands for a traditional ' + esc(r.i) + ' authorization. A 20x listing labeled “' + esc(r.c) +
        '” carries the same words and different standing, including for CUI. The track decides; the class label doesn’t.</p>');
    }
    if (r.inf) {
      b.push('<p class="bn"><b>No impact level listed.</b> The baseline is taken from the “' + esc(r.c) +
        '” label, which on the traditional track stands for ' + esc(r.inf) + '. Confirm it in the package.</p>');
    }
    if (r.t === '20x Pilot' && r.c) {
      var pb = DATA.rules.pilotBanner.split('{class}').join(r.c).split('{date}').join(fmtDate(r.d) || 'an unlisted date');
      b.push('<p class="bn"><b>' + esc(pb).replace(/^([^.]*\.)/, '$1</b>') + '</p>');
    }
    if (r.tk === '20x' && r.i) {
      b.push('<p class="bn"><b>Impact label ignored.</b> The marketplace lists this 20x listing at “' + esc(r.i) +
        '” impact. A 20x class is not an impact-level authorization, and FedRAMP says not to treat classes as replacements for impact levels, so the chart doesn’t use that field.</p>');
    }
    if (r.kind === 'h') {
      b.push('<p class="bn mine"><b>' + esc(fill(DATA.rules.hostedBanner, r)).replace(/^([^.]*\.)/, '$1</b>') + '</p>');
      if (r.own) b.push('<p class="bn"><b>This product also has a listing of its own.</b> <button type="button" data-go="' + esc(r.own) + '">' + esc(byId[r.own].n) + '</button> — check that listing’s card instead.</p>');
      return b.join('');
    }
    var sib = DATA.listings.filter(function (o) { return o.pk === r.pk && o.id !== r.id && r.pk; });
    if (sib.length) {
      b.push('<div class="bn"><b>Other listings from ' + esc(r.p.replace(/\.$/, '')) + '.</b> Check these too; an uplift or a second track appears as a separate listing.<ul>' +
        sib.map(function (o) {
          return '<li><button type="button" data-go="' + esc(o.id) + '">' + esc(o.n) + '</button> <span class="ct">' +
            esc(o.tl) + ' · ' + esc(levelText(o)) + ' · ' + esc(shortStatus(o.s)) + '</span></li>';
        }).join('') + '</ul></div>');
    }
    return b.join('');
  }

  // Vendors hosted inside a platform's boundary hand out the platform's FR ID as their own.
  // Anyone landing on such an ID, by search or deep link, sees that before any tick.
  function hostWarning(r) {
    if (!r.hp) return '';
    var hb = DATA.rules.hostBanner.split('{host}').join(r.n).split('{hostId}').join(r.id);
    return '<div class="bn warn" role="note"><b>' + esc(hb).replace(/^([^?]*\?)/, '$1</b>') + '<ul>' +
      r.hp.map(function (id) {
        var o = byId[id];
        return '<li><button type="button" data-go="' + esc(o.id) + '">' + esc(o.n) + '</button>' + (o.p ? ' <span class="ct">by ' + esc(o.p) + '</span>' : '') + ' <span class="ct">✕ not covered</span></li>';
      }).join('') + '</ul></div>';
  }

  function renderCard(r) {
    var rules = DATA.rules, cs = rules.cases[r.case];
    var gateWait = cs.gate[0] === 'wait';
    var h = r.kind === 'h' ? byId[r.host] : null;
    var facts = h ? [
      ['Track', 'Hosted product<small>no FedRAMP listing of its own</small>'],
      ['Provided by', esc(r.p || 'Not stated in the listing')],
      ['Listed inside', '<button type="button" class="lnk" data-go="' + esc(h.id) + '">' + esc(h.n) + '</button><small>' + esc(h.p) + '</small>'],
      ['Host authorization', esc(h.tl) + ' · ' + esc(levelText(h)) + '<small>' + esc(h.s) + '</small>'],
      ['Listed since', esc(fmtDate(r.since) || 'Not stated')],
      ['Own listing', r.own ? '<button type="button" class="lnk" data-go="' + esc(r.own) + '">' + esc(byId[r.own].id) + '</button>' : 'None'],
      ['Host assessor', esc(h.a || 'None listed')],
      ['Host marketplace ID', '<a href="' + MARKET + encodeURIComponent(h.id) + '/" rel="noopener">' + esc(h.id) + '</a>']
    ] : [
      ['Track', esc(r.tl)],
      [r.tk === 'trad' ? 'Impact level' : 'Class', esc(levelText(r)) + (r.tk === 'trad' && r.c ? '<small>labeled ' + esc(r.c) + '</small>' : '')],
      ['Status', esc(r.s || '—')],
      ['Certified', esc(fmtDate(r.d) || '—')],
      ['Path', esc(r.path || '—')],
      ['Agency ATOs', r.ag.length ? r.ag.length + '<small><a href="#lk-ag">listed below</a></small>' : '0'],
      ['Assessor', esc(r.a || 'None listed')],
      ['Marketplace ID', '<a href="' + MARKET + encodeURIComponent(r.id) + '/" rel="noopener">' + esc(r.id) + '</a>']
    ];
    var rows = rules.rows.map(function (row) {
      var c = cs[row.key], st = c[0], note = fill(c[1], r);
      var cls = 'r' + (row.key === 'gate' ? ' gate' : '') + (gateWait && row.key !== 'gate' ? ' dim' : '');
      return '<div class="' + cls + '" role="row">' +
        '<div role="rowheader"><p class="q">' + esc(row.q) + '</p><p class="ct">' + esc(row.cite[r.tk]) + '</p></div>' +
        '<div role="cell">' + badge(st) + '</div>' +
        '<p class="nt" role="cell">' + esc(note) + '</p></div>';
    }).join('');
    card.innerHTML =
      '<button type="button" class="back" data-back><span aria-hidden="true">←</span> All listings</button>' +
      '<div class="cd-hd"><div><p class="eyebrow">' + esc(h ? 'Hosted in ' + h.id : r.id) + '</p><h2 id="lk-h" tabindex="-1">' + esc(r.n) + '</h2><p class="by">' + esc(h ? (r.p ? r.p + ' · inside ' + h.n : 'inside ' + h.n) : r.p) + '</p></div></div>' +
      hostWarning(r) +
      '<dl class="facts">' + facts.map(function (f) { return '<div><dt>' + f[0] + '</dt><dd>' + f[1] + '</dd></div>'; }).join('') + '</dl>' +
      banners(r) +
      '<div class="ch" role="table" aria-label="What this listing supports">' + rows + '</div>' +
      (!h && r.ag.length ? '<section class="ags" id="lk-ag" aria-label="Agency authorizations"><h3>Agency ATOs (' + r.ag.length + ')</h3><ul>' +
        r.ag.map(function (i) { return DATA.agencies[i]; }).sort().map(function (a) { return '<li>' + esc(a) + '</li>'; }).join('') +
        '</ul><p class="ct">Agencies the marketplace lists as having authorized this offering, other than the FedRAMP PMO.</p></section>' : '') +
      '<div class="fn">' +
        '<p><b>A ✓ is a starting point, not a permission.</b> For federal data and agency CUI, the agency still categorizes its own system, runs RMF and issues its own ATO. DFARS 7012 has no agency ATO step, so for DoD contractors the listing’s status is the bar itself.</p>' +
        '<p>DoD Impact Levels (IL2–IL5) are a separate DISA authorization and aren’t covered here. Listings are shown as the marketplace lists them, as of ' + esc(DATA.snapshotHuman) + ', unless marked as corrected.</p>' +
      '</div>';
    card.hidden = false;
    empty.hidden = true;
  }

  function select(id, opts) {
    var r = byId[id];
    if (!r) return;
    selected = r;
    renderCard(r);
    Array.prototype.forEach.call(rowsEl.querySelectorAll('.lk-it'), function (b) {
      var on = b.getAttribute('data-id') === id;
      b.setAttribute('aria-current', on ? 'true' : 'false');
      if (on && !mobile.matches) {
        // Scroll only the list, never the page, so a deep link doesn't jump the window.
        var br = b.getBoundingClientRect(), lr = rowsEl.getBoundingClientRect();
        if (br.top < lr.top || br.bottom > lr.bottom) rowsEl.scrollTop += br.top - lr.top - rowsEl.clientHeight / 3;
      }
    });
    try { history.replaceState(null, '', '?id=' + encodeURIComponent(id)); } catch (e) {}
    document.title = r.n + ' — FedRAMP usability lookup | Archstone Security';
    if (mobile.matches) document.body.classList.add('lk-open');
    panel.scrollTop = 0;
    if (!opts || !opts.quiet) {
      var h = document.getElementById('lk-h');
      if (h) h.focus({ preventScroll: !mobile.matches });
    }
  }

  function closeMobile() {
    document.body.classList.remove('lk-open');
    if (lastBtn && document.body.contains(lastBtn)) lastBtn.focus();
  }

  rowsEl.addEventListener('click', function (e) {
    var b = e.target.closest('.lk-it');
    if (!b) return;
    lastBtn = b;
    select(b.getAttribute('data-id'));
  });
  card.addEventListener('click', function (e) {
    if (e.target.closest('[data-back]')) { closeMobile(); return; }
    var g = e.target.closest('[data-go]');
    if (g) select(g.getAttribute('data-go'));
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && document.body.classList.contains('lk-open')) closeMobile();
  });
  [q, fTrack, fStatus, fCui].forEach(function (el) {
    el.addEventListener(el === q ? 'input' : 'change', function () { if (DATA) renderList(); });
  });

  fetch('listings.json?v=%%SNAP%%').then(function (res) {
    if (!res.ok) throw new Error(res.status);
    return res.json();
  }).then(function (d) {
    DATA = d;
    function hay(s) { return (' ' + s).toLowerCase().replace(/[^a-z0-9]+/g, ' '); }
    d.listings.forEach(function (r) {
      byId[r.id] = r;
      r._base = hay(r.p + ' ' + r.n + ' ' + r.id + ' ' + r.a);
      r._hay = r.sv ? r._base + hay(r.sv.join(' ')) : r._base;
    });
    d.hosted.forEach(function (r) {
      var h = byId[r.host];
      byId[r.id] = r;
      r._hay = hay(r.n + ' ' + r.p + ' ' + h.n + ' ' + h.p + ' ' + h.id);
    });
    ALL = d.listings.concat(d.hosted);
    document.getElementById('lk-legend').innerHTML = ['lev', 'dec', 'no', 'wait'].map(badge).join('');
    var params = new URLSearchParams(location.search);
    if (params.get('q')) q.value = params.get('q');
    renderList();
    var id = params.get('id');
    if (id && byId[id]) select(id, { quiet: true });
    else if (params.get('q')) {
      var first = rowsEl.querySelector('.lk-it');
      if (first && !mobile.matches) select(first.getAttribute('data-id'), { quiet: true });
    }
  }).catch(function () {
    count.textContent = 'The listing data didn’t load. Reload the page, or open listings.json directly.';
  });
})();
</script>
</body>
</html>
"""


def nav_css() -> str:
    """The navigation block from the adoption page's stylesheet, so both pages draw the same header."""
    start = bp.CSS.index("/* Site navigation:")
    end = bp.CSS.index(".eyebrow{", start)
    return bp.CSS[start:end].strip()


def render(snap: str, digest: str, snapname: str, n: int, nav_items: list) -> str:
    human = bp.fmt_date(snap)
    out = PAGE
    for k, v in {
        "%%NAVCSS%%": nav_css(),
        "%%NAVJS%%": bp.NAV_JS,
        "%%NAV%%": bp.render_nav(nav_items or bp.FALLBACK_NAV),
        "%%SNAPNAME%%": html.escape(snapname),
        "%%DIGEST%%": digest[:12],
        "%%SNAPHUMAN%%": html.escape(human),
        "%%SNAP%%": snap,
        "%%N%%": str(n),
        "%%SITE%%": bp.SITE,
        "%%PATH%%": PAGE_PATH,
        "%%MARKET%%": bp.MARKETPLACE_URL,
    }.items():
        out = out.replace(k, v)
    if "%%" in out:
        sys.exit("build_lookup: unreplaced template token in page")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--snapshot", required=True, type=Path)
    ap.add_argument("--rules", required=True, type=Path)
    ap.add_argument("--overrides", required=True, type=Path)
    ap.add_argument("--hosted", required=True, type=Path, help="hand-maintained list of hosting platforms (data/fedramp/hosted-services.json)")
    ap.add_argument("--assessors", type=Path)
    ap.add_argument("--nav-source", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    products, digest = bp.load_snapshot(args.snapshot)
    snap = bp.snapshot_date(args.snapshot)
    bp.load_assessors(args.assessors)
    rules = load_rules(args.rules)
    ov = json.loads(args.overrides.read_text(encoding="utf-8"))
    listings = build_listings(products, rules, ov)
    hosted = add_services(products, listings, json.loads(args.hosted.read_text(encoding="utf-8")))

    # Agencies repeat across hundreds of listings; send each name once and index it.
    agencies = sorted({a for r in listings for a in r["ag"]})
    idx = {a: i for i, a in enumerate(agencies)}
    for r in listings:
        r["ag"] = [idx[a] for a in r["ag"]]

    payload = {
        "snapshot": snap,
        "snapshotHuman": bp.fmt_date(snap),
        "sha256": digest,
        "rules": {"states": rules["states"], "rows": rules["rows"], "cases": rules["cases"],
                  "hostedBanner": rules["hosted_banner"], "hostBanner": rules["host_banner"],
                  "pilotBanner": rules["pilot_banner"]},
        "agencies": agencies,
        "listings": listings,
        "hosted": hosted,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    (args.out / "listings.json").write_text(data + "\n", encoding="utf-8")
    page = render(snap, digest, args.snapshot.name, len(listings), bp.read_nav(args.nav_source))
    (args.out / "index.html").write_text(page, encoding="utf-8")

    from collections import Counter
    cases = Counter(r["case"] for r in listings)
    print(f"build_lookup: {len(listings)} listings from {args.snapshot.name}; "
          f"{len(hosted)} hosted products; {sum(r['cui'] for r in listings)} meet 7012; cases {dict(sorted(cases.items()))}; "
          f"listings.json {len(data.encode()) // 1024} KB")


if __name__ == "__main__":
    main()
