#!/usr/bin/env python3
"""One-off: inspect or delete an old Cloudflare Pages project.

Cloudflare refuses to delete a Pages project with 100+ deployments from the
dashboard, so this deletes the deployments through the API and then the project.

  CLOUDFLARE_API_TOKEN=... python3 scripts/cloudflare/pages_cleanup.py archstone inspect
  CLOUDFLARE_API_TOKEN=... python3 scripts/cloudflare/pages_cleanup.py archstone delete
"""
import json, os, sys, time, urllib.request, urllib.error

API = "https://api.cloudflare.com/client/v4"
TOKEN = os.environ["CLOUDFLARE_API_TOKEN"]


def call(method, path, ok404=False, tolerate=()):
    req = urllib.request.Request(API + path, method=method,
                                 headers={"Authorization": f"Bearer {TOKEN}"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code == 429 or e.code >= 500:
                time.sleep(2 ** attempt); continue
            if ok404 and e.code == 404:
                return None
            if any(str(c) in body for c in tolerate):
                return None
            raise SystemExit(f"{method} {path} -> {e.code}: {body[:500]}")
    raise SystemExit(f"{method} {path}: gave up after retries")


def main():
    name, mode = sys.argv[1], sys.argv[2]
    accts = call("GET", "/accounts")["result"]
    acct = os.environ.get("CLOUDFLARE_ACCOUNT_ID") or (accts[0]["id"] if len(accts) == 1 else None)
    if not acct:
        raise SystemExit("token sees several accounts: " + ", ".join(a["name"] for a in accts))
    base = f"/accounts/{acct}/pages/projects"

    projects = call("GET", base)["result"]
    print("Pages projects on this account:")
    for p in projects:
        print(f"  - {p['name']}: {p.get('subdomain')}  domains={p.get('domains')}  "
              f"source={(p.get('source') or {}).get('config', {}).get('repo_name', 'direct upload')}  "
              f"created={p.get('created_on', '')[:10]}")
    proj = call("GET", f"{base}/{name}", ok404=True)
    if not proj:
        print(f"\nProject '{name}' not found (already deleted?)."); return
    proj = proj["result"]
    custom = [d for d in proj.get("domains", []) if not d.endswith(".pages.dev")]
    first = call("GET", f"{base}/{name}/deployments?per_page=1")
    total = first.get("result_info", {}).get("total_count")
    latest = (proj.get("latest_deployment") or {})
    print(f"\nProject '{name}': {total} deployments; latest {latest.get('created_on', '')[:10]} "
          f"({latest.get('environment')}); custom domains: {custom or 'none'}")

    if mode != "delete":
        print("\nInspect only; nothing changed."); return
    if any("archstonesecurity.com" in d for d in custom):
        raise SystemExit("Refusing to delete: archstonesecurity.com is attached to this project. "
                         "Remove the custom domain in the dashboard first and check DNS still points at GitHub.")

    ids, pg = [], 1
    while True:
        res = call("GET", f"{base}/{name}/deployments?per_page=25&page={pg}")["result"]
        ids += [d["id"] for d in res]
        if len(res) < 25:
            break
        pg += 1
    deleted = 0
    for i, dep in enumerate(ids, 1):
        # 8000034: the active production deployment can't be deleted; the project delete takes it
        if call("DELETE", f"{base}/{name}/deployments/{dep}?force=true", ok404=True, tolerate=(8000034,)) is not None:
            deleted += 1
        if i % 25 == 0:
            print(f"  {i}/{len(ids)} processed, {deleted} deleted")
    call("DELETE", f"{base}/{name}")
    print(f"\nDeleted {deleted} deployments and the project '{name}'.")


if __name__ == "__main__":
    main()
