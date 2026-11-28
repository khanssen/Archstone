#!/usr/bin/env python3
"""Check data/fedramp/assessors.json against FedRAMP's published directory of recognized assessors.

FedRAMP publishes one JSON file per recognized 3PAO in
github.com/FedRAMP/marketplace-fedramp-gov-data (assessors/). The workflow
clones that folder and runs this script against it.

  * Same assessors (by A2LA ID and name): sets "checked" in assessors.json to
    today, so the page can say the list was verified today.
  * Any assessor added, dropped or renamed: leaves assessors.json alone (the
    page keeps the last date it was verified), writes a report for an issue,
    and sets found=true for the workflow. Aliases need a person, so this never
    edits the list itself.

Descriptions, contacts and other profile fields are ignored: the page only
uses who is recognized.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

UPSTREAM = "https://github.com/FedRAMP/marketplace-fedramp-gov-data/tree/main/assessors"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def load_upstream(folder: Path) -> dict[str, dict]:
    out = {}
    for f in sorted(folder.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        aid = str(d.get("a2laId") or f.stem).strip()
        out[aid] = {"name": (d.get("assessorName") or "").strip(),
                    "recognized": (d.get("fedramp_recognized_timestamp") or "")[:10]}
    return out


def output(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", required=True, type=Path, help="the assessors/ folder of FedRAMP's data repository")
    ap.add_argument("--assessors", required=True, type=Path, help="data/fedramp/assessors.json")
    ap.add_argument("--today", required=True, help="YYYY-MM-DD")
    ap.add_argument("--body", required=True, type=Path, help="where to write the issue body if anything changed")
    args = ap.parse_args()

    up = load_upstream(args.dir)
    if len(up) < 10:
        # A clone that came back empty or half-written must not read as "every assessor dropped".
        sys.exit(f"check_assessors: only {len(up)} assessor files in {args.dir}; not comparing")

    doc = json.loads(args.assessors.read_text(encoding="utf-8"))
    # A firm can sit in FedRAMP's directory under more than one A2LA identifier: the older
    # files use the A2LA organization number (e.g. 137046), the schema-2.0 files use the
    # certificate number (e.g. 3706.01), and FedRAMP has left both in place while it migrates.
    # "a2la" is the primary ID; "a2la_other" lists the rest. Every ID maps to the same firm.
    local = {}
    for a in doc["assessors"]:
        for i in [a["a2la"]] + a.get("a2la_other", []):
            local[str(i)] = a

    def names_of(a: dict) -> set[str]:
        return {norm(n) for n in [a["name"], a.get("display", "")] + a.get("aliases", []) if n}

    added = [(i, up[i]) for i in sorted(up) if i not in local]
    # A firm is dropped only when none of its IDs is still in the directory.
    dropped = [(str(a["a2la"]), a) for a in doc["assessors"]
               if not any(str(i) in up for i in [a["a2la"]] + a.get("a2la_other", []))]
    # A rename is an upstream name that matches none of the firm's names or aliases.
    renamed = [(i, local[i]["name"], up[i]["name"]) for i in sorted(up)
               if i in local and norm(up[i]["name"]) not in names_of(local[i])]

    if not (added or dropped or renamed):
        if doc.get("checked") != args.today:
            doc["checked"] = args.today
            args.assessors.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"check_assessors: {len(up)} recognized assessors, same as assessors.json; checked {args.today}")
        output("found", "false")
        return

    # No run date in the text: the workflow compares bodies to avoid a duplicate comment every day.
    lines = [f"FedRAMP's directory of recognized assessors no longer matches `data/fedramp/assessors.json`. "
             f"The 20x page still matches assessors against the old list, and its \"last confirmed\" date "
             f"stays at {doc.get('checked') or doc.get('updated')} until the file is fixed.", ""]
    # An "added" ID whose name matches a firm already on the list is usually FedRAMP re-issuing
    # that firm's record under its A2LA certificate number, not a new firm.
    by_name = {n: a for a in doc["assessors"] for n in names_of(a)}
    new_id = [(i, u, by_name[norm(u["name"])]) for i, u in added if norm(u["name"]) in by_name]
    added = [(i, u) for i, u in added if norm(u["name"]) not in by_name]
    if added:
        lines += ["**Newly recognized** (listings naming these firms are currently shown as *not* recognized):", ""]
        lines += [f"- {a['name']} — A2LA {i}" + (f", recognized {a['recognized']}" if a["recognized"] else "") for i, a in added]
        lines.append("")
    if new_id:
        lines += ["**New A2LA ID for a firm already listed** (add it to that firm's `a2la_other`, don't add a new firm):", ""]
        lines += [f"- {u['name']} — A2LA {i} (listed as {a['name']}, A2LA {a['a2la']})" for i, u, a in new_id]
        lines.append("")
    if dropped:
        lines += ["**No longer in the directory** (still shown as recognized):", ""]
        lines += [f"- {a['name']} — A2LA {i}" for i, a in dropped]
        lines.append("")
    if renamed:
        lines += ["**Renamed:**", ""]
        lines += [f"- A2LA {i}: {old} → {new}" for i, old, new in renamed]
        lines.append("")
    lines += ["**To fix:** edit `data/fedramp/assessors.json` — add each new firm with `name`, `display`, `a2la` "
              "and any `aliases` providers use for it on the marketplace; remove dropped firms; update `name` for "
              "renames. Set `updated` to today. Pushing the file rebuilds the page, and the next daily check "
              "will close the gap and move `checked` forward.", "",
              f"Source: [{UPSTREAM}]({UPSTREAM})"]
    args.body.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"check_assessors: {len(added)} added, {len(new_id)} new IDs for listed firms, {len(dropped)} dropped, {len(renamed)} renamed; report at {args.body}")
    output("found", "true")


if __name__ == "__main__":
    main()
