# archstonesecurity.com

Source for [archstonesecurity.com](https://archstonesecurity.com), the site of Archstone Security LLC: federal cybersecurity compliance engineering for NIST SP 800-171, FedRAMP, FISMA and GovRAMP.

The site is static HTML, CSS and JavaScript. There is no CMS and no build step for the pages themselves.

## Deployment

Pushes to `main` deploy to GitHub Pages through `.github/workflows/pages.yml`. The workflow copies the repository into `_site/`, minus everything listed in `.deployignore`, and publishes that. Anything that should stay in the repository but off the public site (templates, working files, raw data, tooling) belongs in `.deployignore`.

GitHub Pages cannot issue server-side redirects. Retired pages are kept as `noindex` stubs that forward with a meta refresh and declare the new page as canonical. `stateramp.html` and `states/*.html` are stubs of this kind, pointing at `govramp.html`.

## Layout

| Path | Contents |
|---|---|
| `*.html` | Site pages. Framework pages (`nist-800-171.html`, `fedramp.html`, `fisma.html`, `govramp.html`) share `css/framework.css`. |
| `research.html` and exhibit pages | Published research. See "Research exhibits" below. |
| `cui-regulatory-map/` | Interactive map of the federal CUI regulatory stack. |
| `fedramp-20x-adoption/` | FedRAMP 20x adoption page, rebuilt automatically from FedRAMP Marketplace data. |
| `data/fedramp/` | Marketplace snapshots and history behind the adoption page. See `data/fedramp/README.md`. |
| `scripts/` | Build and validation scripts. Not deployed. |
| `css/`, `js/`, `font/`, `images/` | Site assets. `css/tokens.css` holds the design tokens. |

## Automation

- **FedRAMP marketplace snapshot** (`.github/workflows/fedramp-marketplace.yml`). Runs daily. Downloads the FedRAMP Marketplace export, keeps a dated snapshot when it changes, rebuilds `/fedramp-20x-adoption/` and the dated 20x carousel on `fedramp.html`, commits the result and triggers a deploy. If the download fails, commit a JSON export by hand to `data/fedramp/inbox/` and push; the workflow uses it instead.
- **CodeQL and Dependabot** are configured under `.github/`.

## Pre-push validation

`.githooks/pre-push` runs `scripts/validate-map.js` whenever a push includes changes to `cui-regulatory-map/index.html`, and blocks the push if the map fails validation. Enable the hook once per clone:

```sh
git config core.hooksPath .githooks
```

The validator needs Node. Its jsdom smoke test runs when jsdom is installed (`npm install`) and is skipped otherwise.

## Research exhibits

Research has been cited in a federal submission. The URLs and the data of published exhibits are frozen: do not rename, move or change them. Their presentation can be restyled. New research goes under the GRC Lab path rather than `/research`.

## Security

See [SECURITY.md](SECURITY.md) for how to report a vulnerability.

---

&copy; 2026 Archstone Security LLC. Compliance as Infrastructure&trade; is a trademark of Archstone Security LLC.
