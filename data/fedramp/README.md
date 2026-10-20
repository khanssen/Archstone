# FedRAMP marketplace data

Feeds the page at `/fedramp-20x-adoption/`.

- `raw/products-YYYY-MM-DD.json.gz` — marketplace product exports, one per day the export changed. Not deployed.
- `history.csv` — one row of headline counts per snapshot. Deployed.
- `grc-vendors.json` — providers counted as GRC / compliance vendors. Edit and push to rebuild.
- `ai-vendors.json` — providers whose 20x product is an AI platform (20x only). Edit and push to rebuild.
- `inbox/` — manual fallback. Drop a marketplace JSON export here and push; the workflow uses it and removes it.

Everything is rebuilt by `.github/workflows/fedramp-marketplace.yml` using the scripts in `scripts/fedramp/`.
