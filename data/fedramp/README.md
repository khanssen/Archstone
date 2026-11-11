# FedRAMP marketplace data

Feeds the pages at `/fedramp-20x-adoption/` and `/fedramp-lookup/`.

- `raw/products-YYYY-MM-DD.json.gz` — marketplace product exports, one per day the export changed. Not deployed.
- `ato-ledger.json` / `ato-ledger.csv` — append-only ledger of every agency ATO any source has published: FedRAMP's old marketplace feed (`data.json`, Apr 14 to Nov 3, 2026), FedRAMP's ATO table (`fedramp-atos.json`, from Oct 13, 2026) and the daily exports in `raw/`. Keyed by product and FedRAMP agency ID; an ATO is never removed once seen, and each source records when it first and last showed it. `published_now` says whether FedRAMP still publishes it; `published_as_parent` marks a component ATO now shown only under its parent department. Built by `scripts/fedramp/build_ato_ledger.py`, updated daily before the page build.
- `raw-atos/` — dated copies of FedRAMP's ATO table whenever it changes, the final version of the old marketplace feed (`legacy-data-final-2026-11-03.json.gz`), and `legacy-data-manifest.json`, the commit and SHA-256 of every version of that feed in FedRAMP's repository.
- `legacy/rev5-legacy-2026-11-02.json` — frozen last values of the traditional fields the export stopped publishing on Nov 3, 2026 (impact level, sponsor, agency ATOs, In Process statuses). The pages fill empty fields from it and mark each with *. Written once by `scripts/fedramp/freeze_legacy.py`; do not regenerate.
- `history.csv` — one row of headline counts per snapshot. Deployed.
- `grc-vendors.json` — providers counted as GRC / compliance vendors. Edit and push to rebuild.
- `ai-vendors.json` — providers whose 20x product is an AI platform (20x only). Edit and push to rebuild.
- `usability-rules.json` — the lookup's rules: the six questions, their citations, and the answer every case gives. Hand-maintained; edit the wording and push to rebuild. The build fails if a case doesn't answer every question.
- `lookup-overrides.json` — corrections to miscategorized listings (each with a public note) and disclosures shown on a listing's card. Hand-maintained.
- `hosted-services.json` — platform listings (Project Hosts, stackArmor, Knox) that carry other vendors' products inside their boundary. Those products get their own lookup results, marked not established. Hand-maintained; `not_hosts` records listings reviewed and found not to be hosts. `scripts/fedramp/flag_hosts.py` opens a `possible-host` issue when a new listing looks like one.
- Track changes: `scripts/fedramp/track_changes.py` compares each new snapshot with the previous one and opens or comments on a `track-change` issue when a listing's track, path or class changes.
- `inbox/` — manual fallback. Drop a marketplace JSON export here and push; the workflow uses it and removes it.

Everything is rebuilt by `.github/workflows/fedramp-marketplace.yml` using the scripts in `scripts/fedramp/`.
