#!/usr/bin/env python3
"""Flag marketplace listings that look like they host other vendors' products.

The lookup treats a listing as a host only when it is named in
data/fedramp/hosted-services.json. This script finds listings that look like
hosts but aren't in that file (or in the reviewed not-a-host list), and reports
the ones that are new since the previous snapshot, so a person decides.

Signals, any one of which is enough:
  - a listed service carries the name of another marketplace provider or product;
  - a service description uses hosting language ("provided and managed by",
    "hosted tenant", "deployed within ... boundary", "third-party product");
  - at least two services, and a third or more of the list, describe themselves as
    standalone products ("Acme is a ... platform") with none of the provider's name.

Writes a Markdown issue body to --body and found=true|false to $GITHUB_OUTPUT.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_page as bp  # noqa: E402

HOSTING = re.compile(
    r"provided\s+(?:and|&)\s+managed\s+by"
    r"|hosted\s+tenant"
    r"|third[- ]party\s+(?:product|application|saas|offering)"
    r"|deployed\s+(?:with)?in\s+the\s+[\w\s.-]{0,40}?(?:authorization\s+)?boundary",
    re.I)
MIN_NAME = 5  # ignore matches on very short names ("Box", "Zoom") that collide with feature words
STOP = {"inc", "llc", "corp", "the", "systems", "technologies", "solutions", "software", "services", "corporation",
        "company", "group", "cloud", "government", "federal", "for", "and", "platform", "gov"}
PRODUCT = re.compile(r"\b(platform|software|solution|saas|software-as-a-service|application|suite|system)\b", re.I)


def toks(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2 and t not in STOP}


def standalone(name: str, desc: str, own: set[str]) -> bool:
    """A service described as its own product ("Hyperproof delivers a ... platform"), not a feature of the provider's."""
    if toks(name) & own:
        return False
    first = re.split(r"[\s(,]", name.strip())[0].lower()
    lead = (desc or "")[:160]
    return len(first) > 2 and lead.lower().startswith(first) and bool(PRODUCT.search(lead)) and not (toks(lead) & own)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower().replace("™", "").replace("®", "")).strip()


def candidates(products: list[dict], skip: set[str]) -> dict[str, dict]:
    names: dict[str, str] = {}
    for p in products:
        for n in (p.get("csp"), p.get("cso")):
            k = norm(n)
            if len(k) >= MIN_NAME:
                names.setdefault(k, bp.provider_key(p.get("csp") or ""))
    out = {}
    for p in products:
        if p["id"] in skip:
            continue
        own = bp.provider_key(p.get("csp") or "")
        own_toks = toks(p.get("csp")) | toks(p.get("cso"))
        svcs = p.get("certified_services") or []
        hits, solo = [], []
        for s in svcs:
            name = (s.get("serviceName") or "").strip()
            if standalone(re.sub(r"\s+-\s+https?://\S+$", "", name), s.get("serviceDescription") or "", own_toks):
                solo.append(f"{name} (described as a standalone product)")
            other = names.get(norm(re.sub(r"\s+-\s+https?://\S+$", "", name)))
            if other and other != own:
                hits.append(f"{name} (another marketplace provider or product)")
            elif HOSTING.search(s.get("serviceDescription") or ""):
                hits.append(f"{name} (hosting language in its description)")
        if len(solo) >= 2 and len(solo) * 3 >= len(svcs):
            hits += [h for h in solo if h.split(" (")[0] not in {x.split(" (")[0] for x in hits}]
        if hits:
            out[p["id"]] = {"csp": p.get("csp", ""), "cso": p.get("cso", ""), "status": p.get("status", ""),
                            "n": len(p.get("certified_services") or []), "hits": hits}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--old", type=Path, help="previous snapshot; omit to report every candidate")
    ap.add_argument("--new", required=True, type=Path)
    ap.add_argument("--hosted", required=True, type=Path)
    ap.add_argument("--body", required=True, type=Path)
    args = ap.parse_args()

    cfg = json.loads(args.hosted.read_text(encoding="utf-8"))
    skip = set(cfg.get("hosts", {})) | set(cfg.get("not_hosts", {}))
    new, _ = bp.load_snapshot(args.new)
    found = candidates(new, skip)
    if args.old:
        old, _ = bp.load_snapshot(args.old)
        before = candidates(old, skip)
        # New candidates, or existing ones whose matching services changed.
        found = {k: v for k, v in found.items() if k not in before or set(v["hits"]) != set(before[k]["hits"])}

    lines = []
    if found:
        one = len(found) == 1
        lines += [f"{len(found)} marketplace {'listing looks like it hosts' if one else 'listings look like they host'} "
                  f"other vendors' products and {'is' if one else 'are'} not in `data/fedramp/hosted-services.json`.",
                  "",
                  "For each one, decide and edit `data/fedramp/hosted-services.json`:",
                  "- **A host:** add it under `hosts`, with `own_prefix` for the platform's own components. "
                  "Its other services then become hosted products on /fedramp-lookup/, marked not established.",
                  "- **Not a host** (feature names, its own dependencies): add it under `not_hosts` with a short reason, "
                  "so it isn't flagged again.",
                  ""]
        for k, v in sorted(found.items(), key=lambda kv: kv[1]["csp"].lower()):
            lines.append(f"### {v['csp']} — {v['cso']} (`{k}`)")
            lines.append(f"{v['status']} · {v['n']} listed services · "
                         f"[marketplace]({bp.MARKETPLACE_URL}{k}/) · [lookup](https://www.archstonesecurity.com/fedramp-lookup/?id={k})")
            lines += [f"- {h}" for h in v["hits"][:12]]
            if len(v["hits"]) > 12:
                lines.append(f"- …and {len(v['hits']) - 12} more")
            lines.append("")
    args.body.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"found={'true' if found else 'false'}\n")
    print(f"flag_hosts: {len(found)} listing(s) flagged")


if __name__ == "__main__":
    main()
