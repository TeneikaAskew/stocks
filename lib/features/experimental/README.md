# Direction Features R&D (Track C reference artifact)

**Status: FAIL — 3 of 4 families tested, all FAIL. 4th INFEASIBLE in the time-box. DO NOT REVIVE WITHOUT NEW DATA.**
See [`docs/DIRECTION_FEATURES_R&D.md`](../../../docs/DIRECTION_FEATURES_R&D.md) for per-family per-fold verdict tables.

This package holds experimental feature joiners that were tested **on top of** the 143-col production strat-features set to see whether direction (`next_close > next_open`) becomes learnable when augmented. None passed.

## What's here

- `news_sentiment.py` — rolling sentiment scores, topic flags, news-volume z-scores from `news_sentiment` table
- `cross_asset.py` — VIX 1d/5d delta, VIX z-60, VIX3M − VIX, VVIX z-60, IWM−SPY 5d/20d, QQQ−SPY 5d, IWM-SPY 20d correlation
- `options_derived.py` — put-call ratios (vol + OI), optional IV-skew + GEX proxy under `OPTIONS_FAMILY_INCLUDE_IV=1`
- `vol_regime.py` — daily ATR%, ATR ratio, realized vol 5d/20d, ratio, opening gap %, intraday range vs daily ATR

## What was tested

| Family | 5m | 15m | 30m | Verdict |
|---|---|---|---|---|
| news_sentiment | 0/8 log-loss beat | 0/8 | 0/8 | **FAIL × 3** |
| cross_asset | 0/8 | 0/8 | 0/8 | **FAIL × 3** |
| options_derived | — | — | — | **INFEASIBLE** (14.1M-row Cloud SQL table; pg8000 ~10× slower than psycopg2 for bulk reads) |
| vol_regime | 0/8 | 0/8 | 0/8 | **FAIL × 3** |

Every fold across 24 OK fold runs (3 families × 3 cells × 8 folds, minus 4h cross-bar adjustments) had **negative log-loss beat** — the augmented feature set produces probabilities consistently worse than always-predicting-majority direction. Production featurize and direction walk-forward harness were unchanged.

## Why this lives in-repo

Per Track C's spec, the experimental joiners stay under `lib/features/experimental/` (NOT under the production feature builder) so any future direction work has a baseline to start from. Production `featurize()`, `discover_numeric_features()`, and `make_direction_lgbm()` were not touched.

## If anyone ever revisits Family 4 (options_derived)

The 4th family's per-bar joiner is tractable in principle but blocked on infrastructure:
- Add compound index `(ticker, snapshot_date, data_source, market_session)` on `etf_options_snapshots`, OR materialize a small `option_daily_features` table
- Raise `strat-dir-features` Cloud Run task-timeout to 3 hours
- Re-dispatch with `OPTIONS_FAMILY_INCLUDE_IV=1`

Given the consistent 0/8 log-loss-beat pattern across the 3 measured families, the prior strongly suggests options-derived would also FAIL — but the test was not run, so the FAIL verdict reflects the three measured families plus the documented INFEASIBLE.
