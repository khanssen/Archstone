# FedRAMP marketplace data

Feeds the pages at `/fedramp-20x-adoption/` and `/fedramp-lookup/`.

- `raw/products-YYYY-MM-DD.json.gz` — marketplace product exports, one per day the export changed. Not deployed.
- `history.csv` — one row of headline counts per snapshot. Deployed.
- `grc-vendors.json` — providers counted as GRC / compliance vendors. Edit and push to rebuild.
- `ai-vendors.json` — providers whose 20x product is an AI platform (20x only). Edit and push to rebuild.
- `usability-rules.json` — the lookup's rules: the six questions, their citations, and the answer every case gives. Hand-maintained; edit the wording and push to rebuild. The build fails if a case doesn't answer every question.
- `lookup-overrides.json` — corrections to miscategorized listings (each with a public note) and disclosures shown on a listing's card. Hand-maintained.
- `hosted-services.json` — platform listings (Project Hosts, stackArmor, Knox) that carry other vendors' products inside their boundary. Those products get their own lookup results, marked not established. Hand-maintained; `not_hosts` records listings reviewed and found not to be hosts. `scripts/fedramp/flag_hosts.py` opens a `possible-host` issue when a new listing looks like one.
- Track changes: `scripts/fedramp/track_changes.py` compares each new snapshot with the previous one and opens or comments on a `track-change` issue when a listing's track, path or class changes.
- `inbox/` — manual fallback. Drop a marketplace JSON export here and push; the workflow uses it and removes it.

Everything is rebuilt by `.github/workflows/fedramp-marketplace.yml` using the scripts in `scripts/fedramp/`.
