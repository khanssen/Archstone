#!/usr/bin/env python3
"""Report marketplace listings whose certification track changed between two snapshots.

The lookup's verdicts rest on the track (traditional Rev5 vs 20x / 20x Pilot)
deciding before the class. If listings start moving between tracks in the
export, that has to be seen the day it happens. Compares cert_type, and also
reports changes to cert_path and cert_class, for every listing present in both
snapshots.

Writes a Markdown issue body to --body and found=true|false to $GITHUB_OUTPUT.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_page as bp  # noqa: E402

FIELDS = ("cert_type", "cert_path", "cert_class")


def changes(old: list[dict], new: list[dict]) -> list[dict]:
    before = {p["id"]: p for p in old}
    out = []
    for p in new:
        q = before.get(p["id"])
        if not q:
            continue
        diff = {f: (q.get(f) or "", p.get(f) or "") for f in FIELDS if (q.get(f) or "") != (p.get(f) or "")}
        # Only a track change, or a path/class change on a listing that isn't just being classified for the
        # first time, is worth a look; "Unknown" -> a class is ordinary intake progress.
        if "cert_type" in diff or any(a not in ("", "Unknown") for f, (a, b) in diff.items()):
            out.append({"id": p["id"], "csp": p.get("csp", ""), "cso": p.get("cso", ""),
                        "status": p.get("status", ""), "diff": diff})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--old", required=True, type=Path)
    ap.add_argument("--new", required=True, type=Path)
    ap.add_argument("--body", required=True, type=Path)
    args = ap.parse_args()

    old, _ = bp.load_snapshot(args.old)
    new, _ = bp.load_snapshot(args.new)
    found = changes(old, new)
    track = [c for c in found if "cert_type" in c["diff"]]

    lines = []
    if found:
        lines += [f"Between `{args.old.name}` and `{args.new.name}`, {len(found)} "
                  f"{'listing changed' if len(found) == 1 else 'listings changed'} track, path or class"
                  f" ({len(track)} changed track).", "",
                  "A track change moves a listing between traditional and 20x rules on /fedramp-lookup/. "
                  "Check whether the change reflects the listing's actual certification before the next rebuild.", ""]
        for c in sorted(found, key=lambda c: ("cert_type" not in c["diff"], c["csp"].lower())):
            lines.append(f"### {c['csp']} — {c['cso']} (`{c['id']}`)")
            lines.append(f"{c['status']} · [marketplace]({bp.MARKETPLACE_URL}{c['id']}/) · "
                         f"[lookup](https://www.archstonesecurity.com/fedramp-lookup/?id={c['id']})")
            lines += [f"- **{f}**: `{a or 'blank'}` → `{b or 'blank'}`" for f, (a, b) in c["diff"].items()]
            lines.append("")
    args.body.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"found={'true' if found else 'false'}\n")
    print(f"track_changes: {len(found)} listing(s) changed track, path or class ({len(track)} track)")


if __name__ == "__main__":
    main()
