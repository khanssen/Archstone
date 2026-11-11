#!/usr/bin/env python3
"""Keep an append-only ledger of every agency ATO any FedRAMP source has ever published.

Sources, each read from FedRAMP's own repository (github.com/FedRAMP/marketplace-fedramp-gov-data)
or from Archstone's daily snapshots:

  legacy   data.json, the old marketplace feed. Its AtoMapping (initial ATOs), ReuseMapping (reuse
           ATOs) and per-product agency_authorizations lists. Its content stopped changing on
           Nov 3, 2026, when the marketplace moved to the new ATO table.
  table    fedramp-atos.json, the per-ATO export "from GSA system" the marketplace has used since
           Nov 3, 2026. One record per ATO, with an active flag and a log reason.
  export   Archstone's daily marketplace product exports (data/fedramp/raw/).

An ATO is a (product, agency) pair. Agencies are keyed by FedRAMP's agency ID (22-xxx, the most
specific one a record gives) where a source provides one, and matched by name otherwise. Once a pair
is in the ledger it is never removed: each source records when it first and last showed the pair,
so an ATO that a source drops stays on file with the date it disappeared.

  Backfill:  build_ato_ledger.py --fr-repo <full clone> --history --raw-dir data/fedramp/raw --ledger L
  Daily:     build_ato_ledger.py --fr-dir <checkout> --raw-dir data/fedramp/raw --ledger L
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import gzip
import json
import re
import subprocess
import sys
from pathlib import Path

PMO_ID = "22-092"          # the FedRAMP PMO's own entry in the ATO table (absent from the agency list)
PMO_NAME = "Federal Risk and Authorization Management Program"
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def norm(s: str) -> str:
    s = re.sub(r"^(U\.S\.|US|United States)\s+", "", " ".join((s or "").split()), flags=re.I)
    return re.sub(r"[^a-z0-9]+", " ", s.lower().replace("&", "and")).strip()


class Ledger:
    def __init__(self, doc: dict | None):
        doc = doc or {}
        self.atos: dict[str, dict] = {e["key"]: e for e in doc.get("atos", [])}
        self.products: dict[str, dict] = doc.get("products", {})
        self.agencies: dict[str, str] = doc.get("agencies", {})      # id -> display name
        self.by_name: dict[str, str] = {}                              # normalized name -> id
        self.seen: dict[str, str] = doc.get("source_last_seen", {})    # source -> latest date read
        # The old feed is re-stamped daily with unchanged content; read it only when the content changes.
        self.legacy_sha: str = doc.get("legacy_content_sha256", "")
        for i, n in self.agencies.items():
            self.by_name.setdefault(norm(n), i)

    # ---- agencies -------------------------------------------------------------------------------
    def add_agency(self, aid: str, parent: str, sub: str = "") -> None:
        if not aid:
            return
        name = f"{parent} / {sub}" if sub and sub != parent else parent
        if name and (aid not in self.agencies or len(name) > len(self.agencies[aid])):
            self.agencies[aid] = name
        for n in (sub, parent if not sub else ""):
            if n:
                self.by_name.setdefault(norm(n), aid)

    def agency_key(self, aid: str = "", name: str = "") -> str:
        if aid:
            return aid
        if name == PMO_NAME:
            return PMO_ID
        return self.by_name.get(norm(name)) or f"name:{norm(name)}"

    # ---- observations ---------------------------------------------------------------------------
    def product(self, pid: str, p: dict, date: str) -> None:
        cur = self.products.setdefault(pid, {})
        if date >= cur.get("as_of", ""):
            cur.update({k: p.get(k) for k in ("csp", "cso", "cert_type", "status") if p.get(k)}, as_of=date)

    def see(self, source: str, date: str, pid: str, akey: str, name: str, kind: str, **facts) -> None:
        key = f"{pid}|{akey}"
        e = self.atos.setdefault(key, {"key": key, "product_id": pid, "agency_key": akey,
                                       "agency": name, "sources": {}})
        if name and (not e["agency"] or e["agency"].startswith("name:")):
            e["agency"] = name
        s = e["sources"].setdefault(source, {"first": date, "last": date, "kinds": []})
        s["first"], s["last"] = min(s["first"], date), max(s["last"], date)
        if kind and kind not in s["kinds"]:
            s["kinds"].append(kind)
        for k, v in facts.items():
            if v not in (None, "", []):
                if k == "uuids":
                    s["uuids"] = sorted(set(s.get("uuids", [])) | set(v))
                elif date >= s.get("facts_as_of", ""):
                    s[k] = v
        if facts and date >= s.get("facts_as_of", ""):
            s["facts_as_of"] = date

    # ---- sources --------------------------------------------------------------------------------
    def read_legacy(self, doc: dict, date: str) -> None:
        d = doc["data"]
        for a in d.get("Agencies", []):
            self.add_agency(a.get("id", ""), a.get("parent", ""), a.get("sub", ""))
        for m in d.get("AtoMapping", []):
            aid = self.agency_key(m.get("agency_id", ""), m.get("sub") or m.get("parent", ""))
            self.add_agency(m.get("agency_id", ""), m.get("parent", ""), m.get("sub", ""))
            self.see("legacy", date, m["id"], aid, self.agencies.get(aid, m.get("parent", "")), "initial",
                     ato_date=(m.get("ato_date") or "")[:10], auth_date=(m.get("auth_date") or "")[:10],
                     exp_date=(m.get("exp_date") or "")[:10])
        for m in d.get("ReuseMapping", []):
            self.add_agency(m.get("agency_id", ""), m.get("parent", ""))
            self.add_agency(m.get("sub_id", ""), m.get("parent", ""), m.get("sub", ""))
            aid = self.agency_key(m.get("sub_id") or m.get("agency_id", ""), m.get("sub") or m.get("parent", ""))
            self.see("legacy", date, m["id"], aid, self.agencies.get(aid, m.get("sub") or m.get("parent", "")), "reuse",
                     ato_date=(m.get("ato_date") or "")[:10], auth_date=(m.get("auth_date") or "")[:10],
                     exp_date=(m.get("exp_date") or "")[:10])
        for p in d.get("Products", []):
            self.product(p["id"], {"csp": p.get("csp"), "cso": p.get("cso"), "status": p.get("status")}, date)
            for n in p.get("agency_authorizations") or []:
                if n:
                    self.see("legacy", date, p["id"], self.agency_key(name=n), n, "listed")
            sp = p.get("partnering_agency")
            if sp and norm(sp) in self.by_name:       # the field sometimes holds a status ("Not In Process")
                self.see("legacy", date, p["id"], self.agency_key(name=sp), sp, "sponsor")
        self.seen["legacy"] = max(self.seen.get("legacy", ""), date)

    def read_agency_table(self, doc: dict) -> None:
        # Earlier versions of the file used other layouts; take the first list of records with an "id".
        def rows(o):
            if isinstance(o, list) and o and isinstance(o[0], dict) and "id" in o[0]:
                return o
            if isinstance(o, dict):
                for v in o.values():
                    r = rows(v)
                    if r:
                        return r
            return []
        for a in rows(doc):
            self.add_agency(str(a.get("id", "")), a.get("parent_agency_name") or a.get("parent", ""),
                            a.get("sub_agency_name") or a.get("sub", ""))

    def read_table(self, doc: dict, date: str) -> None:
        for a in doc["data"]["atos"]:
            aid = a.get("agency_id", "")
            name = self.agencies.get(aid, PMO_NAME if aid == PMO_ID else aid)
            kind = "uplift" if a.get("is_uplift") else ("reuse" if a.get("is_reuse") else "initial")
            self.see("table", date, a["product_id"], aid, name, kind,
                     uuids=[a["uuid"]], active=bool(a.get("is_active")), ato_date=(a.get("ato_date") or "")[:10],
                     exp_date=(a.get("exp_date") or "")[:10], log_reason=a.get("log_reason") or "")
        self.seen["table"] = max(self.seen.get("table", ""), date)

    def read_export(self, path: Path) -> None:
        date = DATE_RE.search(path.name).group(1)
        data = json.loads(gzip.decompress(path.read_bytes()))
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [])
        for p in data:
            self.product(p["id"], p, date)
            for n in p.get("agency_authorizations") or []:
                if not n:
                    continue
                if n == "General Services Administration" and p.get("cert_type") != "Rev5" and date >= "2026-11-03":
                    n = PMO_NAME                       # the PMO's own entry, shown under GSA from Nov 3, 2026
                self.see("export", date, p["id"], self.agency_key(name=n), n, "listed")
            sp = p.get("partnering_agency")
            if sp and norm(sp) in self.by_name:
                self.see("export", date, p["id"], self.agency_key(name=sp), sp, "sponsor")
        self.seen["export"] = max(self.seen.get("export", ""), date)

    # ---- output ---------------------------------------------------------------------------------
    def finish(self) -> dict:
        # Merge name-keyed entries into ID-keyed ones once the agency names have resolved.
        for k in [k for k, e in self.atos.items() if e["agency_key"].startswith("name:")]:
            e = self.atos[k]
            aid = self.by_name.get(e["agency_key"][5:])
            if not aid:
                continue
            tgt = self.atos.setdefault(f'{e["product_id"]}|{aid}', {"key": f'{e["product_id"]}|{aid}',
                                       "product_id": e["product_id"], "agency_key": aid,
                                       "agency": self.agencies.get(aid, e["agency"]), "sources": {}})
            for src, s in e["sources"].items():
                t = tgt["sources"].setdefault(src, dict(s))
                t["first"], t["last"] = min(t["first"], s["first"]), max(t["last"], s["last"])
                t["kinds"] = sorted(set(t["kinds"]) | set(s["kinds"]))
            del self.atos[k]
        def now(e):
            s = e["sources"]
            in_table = "table" in s and s["table"]["last"] == self.seen.get("table") and s["table"].get("active")
            in_export = "export" in s and s["export"]["last"] == self.seen.get("export")
            return bool(in_table or in_export)
        for e in self.atos.values():
            e["agency"] = self.agencies.get(e["agency_key"], e["agency"])
            e["published_now"] = now(e)
            e["pmo"] = e["agency_key"] == PMO_ID
        # From Nov 3, 2026 the export names only the parent department. A component's ATO whose
        # parent is still listed on the same product is published, just under the parent's name.
        for e in self.atos.values():
            m = re.match(r"^(\d{2}-\d{3})-", e["agency_key"])
            e.pop("published_as_parent", None)
            if not e["published_now"] and m:
                par = self.atos.get(f'{e["product_id"]}|{m.group(1)}')
                if par and "export" in par["sources"] and par["sources"]["export"]["last"] == self.seen.get("export"):
                    e["published_as_parent"] = True
        atos = sorted(self.atos.values(), key=lambda e: (e["product_id"], e["agency"]))
        return {"description": __doc__.split("\n\n")[0].strip(), "source_last_seen": self.seen,
                "legacy_content_sha256": self.legacy_sha,
                "agencies": dict(sorted(self.agencies.items())), "products": dict(sorted(self.products.items())),
                "atos": atos}


def git_versions(repo: Path, file: str) -> list[tuple[str, str]]:
    out = subprocess.run(["git", "-C", str(repo), "log", "--reverse", "--format=%H %cI", "--", file],
                         capture_output=True, text=True, check=True).stdout.split("\n")
    return [(l.split()[0], l.split()[1][:10]) for l in out if l.strip()]


def git_json(repo: Path, rev: str, file: str) -> dict | None:
    raw = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{file}"], capture_output=True).stdout
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def write_csv(doc: dict, path: Path) -> None:
    cols = ["product_id", "csp", "cso", "cert_type", "agency_key", "agency", "pmo", "published_now",
            "legacy_first", "legacy_last", "legacy_kinds", "table_first", "table_last", "table_kinds",
            "table_active", "ato_date", "exp_date", "log_reason", "export_first", "export_last"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for e in doc["atos"]:
            p, s = doc["products"].get(e["product_id"], {}), e["sources"]
            g = lambda src, k: s.get(src, {}).get(k, "")
            w.writerow([e["product_id"], p.get("csp", ""), p.get("cso", ""), p.get("cert_type", ""),
                        e["agency_key"], e["agency"], e["pmo"], e["published_now"],
                        g("legacy", "first"), g("legacy", "last"), " ".join(g("legacy", "kinds") or []),
                        g("table", "first"), g("table", "last"), " ".join(g("table", "kinds") or []),
                        g("table", "active"), g("table", "ato_date") or g("legacy", "ato_date"),
                        g("table", "exp_date") or g("legacy", "exp_date"), g("table", "log_reason"),
                        g("export", "first"), g("export", "last")])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", required=True, type=Path, help="data/fedramp/ato-ledger.json (read, then rewritten)")
    ap.add_argument("--fr-repo", type=Path, help="clone of FedRAMP/marketplace-fedramp-gov-data")
    ap.add_argument("--history", action="store_true", help="read every committed version (needs a full clone)")
    ap.add_argument("--fr-dir", type=Path, help="checkout of that repository: read the current files only")
    ap.add_argument("--raw-dir", type=Path, help="Archstone's daily exports (data/fedramp/raw)")
    ap.add_argument("--csv", type=Path, help="also write a flat CSV")
    args = ap.parse_args()

    old = json.loads(args.ledger.read_text(encoding="utf-8")) if args.ledger.exists() else None
    L = Ledger(old)
    n_before = len(L.atos)

    if args.fr_repo and args.history:
        for rev, _ in git_versions(args.fr_repo, "fedramp-agencies.json"):
            doc = git_json(args.fr_repo, rev, "fedramp-agencies.json")
            if doc:
                L.read_agency_table(doc)
        last = None
        for rev, date in git_versions(args.fr_repo, "data.json"):
            doc = git_json(args.fr_repo, rev, "data.json")
            if not doc or not doc.get("data", {}).get("Products"):
                continue
            body = json.dumps(doc["data"], sort_keys=True)
            if body == last:          # the feed is re-stamped daily; skip unchanged content
                continue
            last = body
            L.legacy_sha = hashlib.sha256(body.encode()).hexdigest()
            L.read_legacy(doc, date)
        for rev, date in git_versions(args.fr_repo, "fedramp-atos.json"):
            doc = git_json(args.fr_repo, rev, "fedramp-atos.json")
            if doc:
                L.read_table(doc, date)
    elif args.fr_dir:
        ag = args.fr_dir / "fedramp-agencies.json"
        if ag.exists():
            L.read_agency_table(json.loads(ag.read_text(encoding="utf-8")))
        dj = args.fr_dir / "data.json"
        if dj.exists():
            doc = json.loads(dj.read_text(encoding="utf-8"))
            sha = hashlib.sha256(json.dumps(doc.get("data", {}), sort_keys=True).encode()).hexdigest()
            stamp = DATE_RE.search(doc.get("meta", {}).get("last_change", "") or "")
            if stamp and sha != L.legacy_sha:
                L.legacy_sha = sha
                L.read_legacy(doc, stamp.group(1))
        at = args.fr_dir / "fedramp-atos.json"
        if at.exists():
            doc = json.loads(at.read_text(encoding="utf-8"))
            stamp = DATE_RE.search(doc.get("metadata", {}).get("export_timestamp", "") or "")
            if not stamp:
                sys.exit("build_ato_ledger: fedramp-atos.json has no export_timestamp")
            L.read_table(doc, stamp.group(1))

    if args.raw_dir:
        for f in sorted(args.raw_dir.glob("products-*.json.gz")):
            if DATE_RE.search(f.name).group(1) > L.seen.get("export", "") or not old:
                L.read_export(f)

    doc = L.finish()
    if old and len(doc["atos"]) < n_before:
        sys.exit(f"build_ato_ledger: ledger would shrink from {n_before} to {len(doc['atos'])} entries. Not writing.")
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    args.ledger.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.csv:
        write_csv(doc, args.csv)
    a = doc["atos"]
    print(f"build_ato_ledger: {len(a)} agency ATOs on file ({len(a) - n_before:+d}); "
          f"{sum(e['published_now'] for e in a)} published now, {sum(not e['published_now'] for e in a)} no longer "
          f"published; sources last read {doc['source_last_seen']}")


if __name__ == "__main__":
    main()
