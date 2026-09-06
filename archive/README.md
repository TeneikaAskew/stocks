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

## The Earnings Whispers exports — preserved, NOT drop-in usable

`google-apps-script/data/reference/` holds four CSVs committed because they are
the only copy: the Apps Script scraper that produced them is retired, and they
existed on one disk. They are kept as **provenance**, not as a working input.

`scripts/match_earnings_strategy.py` cannot read them as they stand, and four
separate things are wrong before it could — all found in review of the commit
that added them, and all verified:

| | |
|---|---|
| **Filenames** | The loader looks for `LongCalls.csv`, `CoveredCalls.csv`, `BullSpreads.csv`, `BearSpreads.csv` directly under `.../data`. These are named `Stocks from Earnings Whisper - ...` and live under `.../data/reference`. `--data-dir` fixes the directory but not the basenames. There is no Bear Spreads export at all. |
| **Empty rows** | Long Calls is 913 comma-only rows out of 1,000 — roughly 87 real records. Their `strike` is NaN and `create_lookup_keys` does `(df['strike'] * 1000).astype(int)`, which raises `IntCastingNaNError`. |
| **Spread schema** | Bull Spreads has `longStrike` and `shortStrike`, no `strike`. `--strategy bullspreads` raises `KeyError: 'strike'`; the loader has to pick a leg or normalize. |
| **Covered-call premium** | Covered Calls has `bid`, no `price`. `calculate_profit_loss` reads `price_EW` and substitutes an all-NaN series when `price` is absent, so every P&L comes out NaN. |
| **Duplicates** | Bull Spreads contains 54 exact duplicate records out of 237 non-empty. The matcher carries them through the merge, double-weighting `total_pnl` and the winner/loser counts. |

So treat a run against these as needing a cleaning pass first. Nothing here is
a regression — the files were never in a state the script could consume, which
is why whoever ran it last must have renamed and cleaned them by hand.
