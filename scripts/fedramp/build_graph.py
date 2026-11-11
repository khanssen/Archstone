#!/usr/bin/env python3
"""Build the built-on / used-by graph between marketplace listings.

Three sources, all from the marketplace export plus one hand-kept file:

  third_party_information_resources  what a listing says it is built on or uses inside its minimum
                                     assessment scope (MAS-CSO-TPR), certified or not. Providers type
                                     the certified resource as free text ("AWS GovCloud",
                                     "AGENCYAMAZONEW (AWS US East/West, ...)"), so each is resolved to a
                                     package ID by an ID in the text, else by the listing's name.
  certified_services                 services inside a listing's own package (FRC-CSO-PKG). On a
                                     platform listed in hosted-services.json, other vendors' products
                                     in that list are hosted inside the platform's boundary.
  hosted-services.json               Archstone's list of hosting platforms.

The Nov 2, 2026 marketplace update replaced the "Dependent Products" tab with "Third-Party
Resources", and FedRAMP carried each listing's old dependents list into the new field, where it reads
as the opposite: products that use the listing appear as resources the listing uses (Okta's 140
"resources" are products that sign in with Okta). An entry with no use case that is on the listing's
Nov 2 dependents list (--dependents) is read in its original direction and flagged.

What it records is what listings declare. Using a certified platform does not put a product inside
that platform's authorization: only the platform's own package (certified_services) can do that.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ID_RE = re.compile(r"\b(FR\d{10}(?:A|XL|XM)?|F\d{10}A?|AGENCY[A-Z0-9]{3,}|MSO365MT|[A-Z]{4,}\d*)\b")
_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|for government|government|gov|fedramp|"
                     r"high|moderate|low|class [a-d]|rev5|20x|the)\b")
URL_TAIL = re.compile(r"\s+-\s+https?://\S+$")
PROVIDED_BY = re.compile(r"^\s*provided\s+(?:and|&)\s+managed\s+by\s+([^,.]+)", re.I)


def key(s: str) -> str:
    s = (s or "").lower().replace("&", "and")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = _SUFFIX.sub(" ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def load_export(path: Path) -> list[dict]:
    data = json.loads(gzip.decompress(path.read_bytes()))
    return data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--snapshot", required=True, type=Path)
    ap.add_argument("--hosted", required=True, type=Path, help="data/fedramp/hosted-services.json")
    ap.add_argument("--off-index", type=Path, help="build_history index, to resolve names of delisted listings")
    ap.add_argument("--dependents", type=Path, help="the Nov 2, 2026 export (last with leveraged_systems), data/fedramp/raw/products-2026-11-02.json.gz")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    products = load_export(args.snapshot)
    by_id = {p["id"]: p for p in products}
    names: dict[str, str] = {}
    for p in products:
        for n in (p.get("cso"), p.get("service_acronym"), f'{p.get("csp","")} {p.get("cso","")}'):
            k = key(n)
            if len(k) >= 4:
                names.setdefault(k, p["id"])
    known_ids = set(by_id)
    if args.off_index and args.off_index.exists():
        for r in json.loads(args.off_index.read_text(encoding="utf-8"))["off_marketplace"]:
            known_ids.add(r["id"])
            if r.get("n"):
                names.setdefault(key(r["n"]), r["id"])

    def resolve(text: str) -> tuple[str | None, str]:
        for tok in ID_RE.findall(text or ""):
            if tok in known_ids:
                return tok, "id"
        k = key(text)
        if k in names:
            return names[k], "name"
        # "Google Cloud Platform" inside "Google Services (Google Cloud Platform Products ...)"
        if len(k) >= 10:
            hits = {pid for pid, p in by_id.items()
                    if k in re.sub(r"[^a-z0-9]+", "", (p.get("cso") or "").lower().replace("&", "and"))}
            if len(hits) == 1:
                return hits.pop(), "name (inside listing name)"
        # "AWS GovCloud" vs "AWS GovCloud High": a unique listing whose key starts with the text's
        if len(k) >= 6:
            hits = {v for n, v in names.items() if n.startswith(k) or k.startswith(n) and len(n) >= 8}
            if len(hits) == 1:
                return hits.pop(), "name (partial)"
        return None, "unresolved"

    old_dep: dict[str, set] = {}
    if args.dependents and args.dependents.exists():
        for p in load_export(args.dependents):
            ids = {l.get("id") for l in (p.get("leveraged_systems") or []) if isinstance(l, dict) and l.get("id")}
            if ids:
                old_dep[p["id"]] = ids
    hosts = json.loads(args.hosted.read_text(encoding="utf-8")).get("hosts", {})
    G: dict[str, dict] = defaultdict(lambda: {"built_on": [], "used_by": [], "hosts": [], "hosted_in": [], "flags": []})
    unresolved = 0
    for p in products:
        t = p.get("third_party_information_resources") or {}
        migrated = 0
        for c in (t.get("certified") or []) if isinstance(t, dict) else []:
            text = c.get("fedRampCertifiedThirdPartyInformationResource") or ""
            if text.strip() in old_dep.get(p["id"], ()) and not (c.get("useCase") or "").strip():
                # A former dependent: it uses this listing, not the other way round.
                dep = text.strip()
                migrated += 1
                G[p["id"]]["used_by"].append({"id": dep, "use": "", "source": "former_dependents"})
                G[dep]["built_on"].append({"id": p["id"], "as_declared": None, "certified": True, "use": "",
                                           "resolved": "id", "listed": p["id"] in by_id, "source": "former_dependents"})
                continue
            rid, how = resolve(text)
            unresolved += rid is None
            G[p["id"]]["built_on"].append({"id": rid, "as_declared": text.strip(), "certified": True,
                                           "use": (c.get("useCase") or "").strip(), "resolved": how,
                                           **({"listed": rid in by_id} if rid else {})})
            if rid:
                G[rid]["used_by"].append({"id": p["id"], "use": (c.get("useCase") or "").strip()})
        for c in (t.get("nonCertified") or []) if isinstance(t, dict) else []:
            G[p["id"]]["built_on"].append({"id": None, "as_declared": (c.get("name") or "").strip(),
                                           "provider": (c.get("provider") or "").strip(), "certified": False,
                                           "use": (c.get("useCase") or "").strip()})
        if migrated:
            G[p["id"]]["flags"].append({"kind": "dependents_shown_as_resources", "count": migrated,
                                        "text": f"FedRAMP's page lists {migrated} products that use this listing as third-party resources inside its minimum assessment scope; they were its Dependent Products until Nov 2, 2026"})
        cfg = hosts.get(p["id"])
        for s in p.get("certified_services") or []:
            name = URL_TAIL.sub("", (s.get("serviceName") or "").strip())
            if not name or not cfg or any(name.startswith(pre) for pre in cfg.get("own_prefix", [])):
                continue
            m = PROVIDED_BY.match(s.get("serviceDescription") or "")
            own, _ = resolve(name)
            G[p["id"]]["hosts"].append({"name": name, "provider": m.group(1).strip() if m else "",
                                        "since": (s.get("dateAvailable") or "")[:10], "own_listing": own})
            if own:
                G[own]["hosted_in"].append({"id": p["id"], "name": name})

    # Flags: what the declarations leave open.
    for pid, g in G.items():
        for b in g["built_on"]:
            if b.get("source") == "former_dependents":
                continue
            if b["certified"] and not b["id"]:
                g["flags"].append({"kind": "certified_resource_not_found",
                                   "text": f'Declares "{b["as_declared"][:80]}" as a FedRAMP Certified resource; no listing by that name or ID'})
            elif b["certified"] and b["id"] and not b.get("listed"):
                g["flags"].append({"kind": "certified_resource_delisted",
                                   "text": f'Declares {b["id"]} as a FedRAMP Certified resource; that listing is no longer on the marketplace'})
        for h in g["hosts"]:
            if not h["own_listing"]:
                g["flags"].append({"kind": "hosted_without_listing",
                                   "text": f'{h["name"]} runs inside this platform\'s package and has no marketplace listing of its own'})
        p = by_id.get(pid)
        if p and any(m in (p.get("service_model") or []) for m in ("PaaS", "IaaS")):
            g["platform_dependents"] = len({u["id"] for u in g["used_by"]})

    out = {"description": __doc__.split("\n\n")[0].strip(), "snapshot": args.snapshot.name,
           "listings": {k: v for k, v in sorted(G.items()) if any(v[x] for x in ("built_on", "used_by", "hosts", "hosted_in"))}}
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    decl = sum(1 for g in G.values() for b in g["built_on"] if b["certified"])
    print(f"build_graph: {len(out['listings'])} listings with relationships; {decl} certified resources declared, "
          f"{unresolved} unresolved; {sum(len(g['hosts']) for g in G.values())} hosted products; "
          f"{sum(len(g['flags']) for g in G.values())} flags -> {args.out}")


if __name__ == "__main__":
    main()
