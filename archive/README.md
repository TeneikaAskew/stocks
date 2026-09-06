# archive/

Retired code, kept for reference rather than deleted. Nothing here runs in
production, and nothing under `lib/`, `gcp/`, `platform/` or `scripts/`
imports from it — with the two documented exceptions below.

## Layout

| path | what it is |
|---|---|
| `earnings_options_analytics/` | standalone earnings-options analysis app and dashboard |
| `google-apps-script/` | the original Apps Script project (Earnings Whispers scraping, sheet automation), plus its `appsscript.json` manifest and `requirements-google-api.txt` |
| `old-apps/` | earlier static apps, incl. options-heatseeker (retired in #255 at the FastAPI cutover) |
| `success-report-site/` | static success-report page |
| `website/` | static marketing/dashboard pages |
| `notebooks/` | exploratory Jupyter notebooks |
| `standalone-scripts/` | root-level scripts that nothing imported |
| `static-pages/` | the old root `index.html` landing page linking to the apps |
| `notes/` | one-off notes and test artifacts |

## Still referenced from live code

Two paths here are load-bearing despite living in the archive. Check before
moving or deleting them:

- `archive/google-apps-script/data/` — the default `--data-dir` for
  `scripts/match_earnings_strategy.py`.
- `archive/success-report-site/` and `archive/website/` — served by the
  Playwright smoke tests in `tests/test_e2e.py` (`make test-e2e`; excluded
  from `make test` and not run in CI).

## Before removing anything from here

Grep for the path, not the bare directory name — several of these names
(`reports`, `insights`, `website`) are ordinary English words and a
name-only search returns mostly prose. Match `<dir>/` instead.
