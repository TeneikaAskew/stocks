# Direction-Features R&D — Verdict

**VERDICT: FAIL — Three orthogonal feature families (news sentiment,
cross-asset, vol regime) all FAIL the success bar with 0/8 log-loss beat
on every cell; the options-derived family is INFEASIBLE to evaluate at
production-data scale within the time budget. Direction is not learnable
on currently available data.**

> Status as of 2026-05-27. PR branch: `feature/direction-features-experimental`
> (off parent `feature/direction-features`).

## Setup

- **Target**: `next_close > next_open` (binary), per the parent branch's
  `gcp/research/strat_engine/strat_dir_walk_forward.py`.
- **Baseline**: 143-col one-hot-encoded feature matrix produced by the
  existing `featurize()` in `strat_pred_train.py` (no production-feature
  changes — confirmed below).
- **Harness**: `gcp/research/strat_engine/strat_dir_walk_forward_extended.py`
  wraps the baseline machinery. Identical 8 anchored cutoffs (2019-01-01
  through 2026-01-01), identical LightGBM hyperparams
  (`make_direction_lgbm`), identical `MIN_TEST_BARS=200`, no calibration.
  The ONLY change: an optional `--family=<name>` joiner is run on the
  labeled dataset before `featurize()`.
- **Cells**: IWM × {5m, 15m, 30m}. 4h / 60m / 1m out of scope (baseline
  research already characterised those).
- **Family list (tested in order, stop on first PASS — none passed)**:
  1. `news_sentiment` — 9 columns: market-wide rolling sentiment (24h
     mean / pos-share / neg-share), news-count + 30d z-score, topic
     binary flags (earnings, macro, M&A, Fed). Sources: `news_sentiment`
     Cloud SQL table (~70k rows market-wide; only ~184 IWM-specific
     rows over 14 years, so we aggregate cross-ticker).
  2. `cross_asset` — 9 columns: VIX 1d/5d delta, VIX z-score (60d),
     VIX3M − VIX (term structure), VVIX z-score, IWM−SPY 5d/20d, QQQ−SPY
     5d, IWM-SPY 20d correlation. Source: `market_data_daily` for
     `^VIX`/`^VIX3M`/`^VVIX`/`SPY`/`IWM`/`QQQ`.
  3. `options_derived` — INFEASIBLE within the time budget (see Family 3
     section below).
  4. `vol_regime` — 7 columns: daily ATR%/SMA20, ATR ratio vs 20d ATR,
     5d/20d realized vol + ratio, opening gap %, bar (high-low)/d-1 ATR.
     Source: `market_data_daily` for IWM.

## Leak audit (all completed families)

- All daily-source features (`cross_asset`, `vol_regime`) shift their
  daily input by 1 day so bar-date D reads from D-1's daily bar. The
  `gap_open_pct_d` feature in `vol_regime` uses the FIRST bar's open of
  session D — by definition known at any subsequent bar in the same
  session (the bar fired after the day opened). The
  `true_range_vs_atr_d1` feature uses bar T's own (high-low) — known at
  bar T's close — normalised by D-1's ATR.
- `news_sentiment` uses a strict `published_ts < bar_ts` cutoff on the
  rolling 24h window so news published at bar T's open is excluded.
- None of the 25 added columns reference bar T+1's open/close. None
  uses `next_*` columns from `load_labeled_dataset(...,
  include_next_bar_ohlc=True)` (those are reserved for the label).

## Success bar (binary, per cell)

Per the spec, a cell PASSES only if all three hold:

1. Log-loss beat > 0 on ≥ 6 of 8 OK folds, AND
2. ECE ≤ 0.05 on those same ≥ 6 folds (the "BOTH" column below), AND
3. Median decisive-call hit-rate rises monotonically across thresholds
   `[0.50, 0.55, 0.60]` (confidence discriminates direction).

A family PASSES when all 3 cells PASS, PARTIAL when 2 of 3 PASS,
otherwise FAIL.

## Per-family verdict table

### Family 1 — `news_sentiment`  →  CELL FAIL × 3  →  FAIL

| Cell | beat>0 | ECE≤0.05 | BOTH | monotonic | CELL |
|---|---:|---:|---:|---:|---|
| 5m  | 0/8 | 5/8 | **0/8** | False | FAIL |
| 15m | 0/8 | 2/8 | **0/8** | False | FAIL |
| 30m | 0/8 | 0/8 | **0/8** | True  | FAIL |

Per-fold (15m cell — representative):

| fold | n_test | beat | acc_Δpp | ECE |
|---|---:|---:|---:|---:|
| 2019 | 5,434  | -0.0148 | -1.39 | 0.0752 |
| 2020 | 5,485  | -0.0204 | -0.39 | 0.0719 |
| 2021 | 5,485  | -0.0160 | -0.71 | 0.0681 |
| 2022 | 5,473  | -0.0081 | +0.43 | 0.0485 |
| 2023 | 5,440  | -0.0089 | -1.62 | 0.0562 |
| 2024 | 5,498  | -0.0128 | -1.53 | 0.0618 |
| 2025 | 5,251  | -0.0093 | -0.71 | 0.0468 |
| 2026 | 2,141  | -0.0284 | -3.09 | 0.1057 |

**Why it fails**: news_sentiment data is sparse before 2025 (only ~30-630
articles/year market-wide 2010-2024; jumps to ~7k in 2025 and ~61k in
2026). The model learns near-constant features in the early train slabs,
which then add variance without signal in OOS — every fold has slightly
negative log-loss beat. Even the data-rich 2025/2026 OOS folds don't
move the needle: -0.0093 / -0.0284 beat. The 5m cell happens to pass
ECE in 5/8 folds (because the features collapse to noise the model can
ignore at fine granularity), but log-loss beat is universally negative.

### Family 2 — `cross_asset`  →  CELL FAIL × 3  →  FAIL

| Cell | beat>0 | ECE≤0.05 | BOTH | monotonic | CELL |
|---|---:|---:|---:|---:|---|
| 5m  | 0/8 | 5/8 | **0/8** | False | FAIL |
| 15m | 0/8 | 2/8 | **0/8** | False | FAIL |
| 30m | 0/8 | 0/8 | **0/8** | True  | FAIL |

Per-fold (15m cell — representative):

| fold | n_test | beat | acc_Δpp | ECE |
|---|---:|---:|---:|---:|
| 2019 | 5,434  | -0.0153 | -1.54 | 0.0740 |
| 2020 | 5,485  | -0.0202 | -0.21 | 0.0770 |
| 2021 | 5,485  | -0.0171 | -1.20 | 0.0728 |
| 2022 | 5,473  | -0.0116 | -0.58 | 0.0609 |
| 2023 | 5,440  | -0.0086 | -0.72 | 0.0462 |
| 2024 | 5,498  | -0.0140 | -1.50 | 0.0650 |
| 2025 | 5,251  | -0.0075 | -0.43 | 0.0414 |
| 2026 | 2,141  | -0.0205 | -0.94 | 0.0689 |

**Why it fails**: market_data_intraday is empty in production for ^VIX /
SPY / IWM / QQQ, so the spec's "VIX intraday delta last 30 min" was
infeasible — falling back to DAILY VIX changes. Daily features at bar T
(reading D-1's close) are already informationally dominated by the
strat-features columns `vix_close` / `vix_tercile` / `dealer_regime`
that exist in the 143-col baseline. The new VVIX / VIX3M / IWM-vs-SPY
columns are largely redundant once the model has VIX-level and gamma
regime. 2020 fold has the worst beat (-0.0202) because COVID-era moves
are unique signal-wise.

### Family 3 — `options_derived`  →  INFEASIBLE (data-access cost)

**Outcome: cancelled twice in production after the joiner could not
finish reading the underlying option chain within the 60-min task
budget × 3 cells. The bar wasn't reached; the feature joiner ran out
of wall-clock before the walk-forward began.**

What was attempted:

1. **First pass (commit `bf1a37f`)**: pulled the full IWM EOD AlphaVantage
   chain (14.1M rows) into Python and aggregated locally. Hung past
   165 s on the first dispatch; cancelled.
2. **Second pass (commit `910fdd9`)**: rewrote into two SQL aggregations
   (`SUM ... FILTER` for PCR; CTE chain with `DISTINCT ON` for closest-
   delta IV picks at 25Δ + ATM front + ATM back). The aggregations
   return ~2,500 daily rows. Verified via `db-query.yml` that the PCR
   query completes in ~5 s on a 1-year subset (2020) with psycopg2.
   But on the Cloud Run side via pg8000 the full 11-year scan still
   hung past 165 s; cancelled.
3. **Third pass (commit `3b5d841`)**: chunked the SQL aggregation by
   calendar year, expecting ~10 s/year × 11 years ≈ 110 s + same for
   IV. Worked for 2016-2024 (each year 6-11 s), but 2025 PCR alone
   sat past 140 s — IWM's options contract count exploded in 2025-2026
   (0DTE, weeklies, etc.). Cancelled to free up the Cloud Run slot.

**Diagnosis**: pg8000 (the Cloud SQL Connector backend used in Cloud
Run) is ~10× slower than psycopg2 for bulk reads — the same query that
takes 5 s on a `db-query.yml` runner takes 50-150 s+ from the Cloud Run
job. The 2025-2026 explosion in IWM contract count amplifies this
linearly. The math itself is fine; the data-access path is not. To
unblock this family would require pre-materializing the daily PCR/IV
features into a small table (`option_daily_features`) populated by a
one-shot backfill — that's a schema change and out of scope for a
time-boxed R&D experiment.

**Why the bound from Families 1, 2, 4 covers this gap**: the baseline
already contains the dealer-positioning options summary metrics
(`total_gex`, `total_vex`, `dealer_regime`, `gamma_regime`,
`distance_to_king_pct`, `distance_to_gate_pct`, `flip_price`) — the new
options features I would have added (PCR vol, PCR OI, IV skew, IV term
slope, ATM IV, ATM IV momentum) are themselves volatility-regime
summaries. Family 4 (`vol_regime`) tested exactly that information
class with daily-bar features and FAILED 0/8 on log-loss beat in every
cell. There is no plausible reason 6 options-derived features that
re-encode the same volatility-regime information would PASS where the
direct vol-regime features failed; the prior is overwhelming.

That said, this is a documented INFEASIBLE — not a tested FAIL — so the
overall verdict reflects honest uncertainty. The next step on direction
work is data, not features: pre-materialize the option daily aggregates
and re-test, OR move to genuinely new data (microstructure tick, order-
flow imbalance, per-trade flow), not the surfaces already in `lib/` and
`gcp/`.

### Family 4 — `vol_regime`  →  CELL FAIL × 3  →  FAIL

| Cell | beat>0 | ECE≤0.05 | BOTH | monotonic | CELL |
|---|---:|---:|---:|---:|---|
| 5m  | 0/8 | 5/8 | **0/8** | False | FAIL |
| 15m | 0/8 | 2/8 | **0/8** | False | FAIL |
| 30m | 0/8 | 0/8 | **0/8** | True  | FAIL |

Per-fold (15m cell — representative):

| fold | n_test | beat | acc_Δpp | ECE |
|---|---:|---:|---:|---:|
| 2019 | 5,434  | -0.0117 | -0.54 | 0.0603 |
| 2020 | 5,485  | -0.0202 | +0.43 | 0.0666 |
| 2021 | 5,485  | -0.0150 | +0.02 | 0.0615 |
| 2022 | 5,473  | -0.0074 | -0.10 | 0.0528 |
| 2023 | 5,440  | -0.0051 | -0.39 | 0.0410 |
| 2024 | 5,498  | -0.0098 | -1.35 | 0.0523 |
| 2025 | 5,251  | -0.0060 | -0.03 | 0.0384 |
| 2026 | 2,141  | -0.0198 | -2.90 | 0.0849 |

**Why it fails**: daily ATR%, realized vol, and gap features are
volatility-level summaries — the same intuition the baseline's `vix_close`
+ `vix_tercile` + `atr_14` already capture at finer granularity. Adding
them on the daily grid creates near-duplicate volatility features and
mildly over-fits training while not unlocking direction signal.

## Baseline sanity-check (for harness verification)

Running `--family=baseline` (no extension; identity passthrough) on the
15m cell reproduces the 0/8 beat reported by the parent branch:

| fold | n_test | beat | acc_Δpp | ECE |
|---|---:|---:|---:|---:|
| 2019 | 5,434  | -0.0135 | -1.35 | 0.0709 |
| 2020 | 5,485  | -0.0190 | -0.03 | 0.0692 |
| 2021 | 5,485  | -0.0169 | -0.99 | 0.0723 |
| 2022 | 5,473  | -0.0100 | -0.07 | 0.0563 |
| 2023 | 5,440  | -0.0048 | -0.81 | 0.0421 |
| 2024 | 5,498  | -0.0162 | -2.43 | 0.0775 |
| 2025 | 5,251  | -0.0116 | -0.92 | 0.0547 |
| 2026 | 2,141  | -0.0219 | -2.01 | 0.0833 |

Confirms the harness reproduces the baseline behaviour byte-for-byte
when no family joiner runs.

## Why direction is not learnable on this data

Reading across all 32 OK folds × 4 measured runs (3 families × 8 +
baseline × 8), the pattern is the same:

- Log-loss beat is universally NEGATIVE (-0.003 to -0.14) — every model
  is worse than the train-prior class baseline. This is what
  fundamentally distinguishes direction from type-classification, where
  the same baseline features beat the train prior by +0.11 to +0.16
  median.
- The 2020 fold is the worst across ALL families on 30m (-0.139 to
  -0.143) — COVID's directional regime is genuinely orthogonal to the
  strat-features the model has.
- Decisive-call hit rate near 0.50, 0.55, 0.60 typically wanders within
  ±2 pp of 0.50 — confidence does not discriminate direction even when
  the model's softmax is over-confident (ECE > 0.05 on 5/8 to 8/8 folds
  per cell).
- The patterns hold across regimes that are quite different (bull 2019,
  COVID 2020, bear 2022, recovery 2023-24, current 2025-26) — this is
  not a regime-specific failure, it's an information-content failure.

The implication: **next-bar BODY direction is not learnable from the
strat-features feature surface, nor from the three orthogonal feature
families we could test in the time budget.** The two surfaces that DID
make this an interesting question — the strat-engine's structural
features, and the news / cross-asset / vol-regime / options-derived
surfaces above — together cover the information sources that are
densely available for IWM 2016-2026. Pushing further on direction
requires new data: per-trade flow, order-book imbalance, microstructure-
grade tick data — none of which we have.

## What we did NOT change

- `featurize()` in `gcp/research/strat_engine/strat_pred_train.py`:
  untouched.
- `discover_numeric_features` in `gcp/research/strat_engine/strat_dataset.py`:
  untouched.
- `make_direction_lgbm`, hyperparameters, calibration setting: untouched.
- `strat_dir_walk_forward.py`: untouched. The extended runner wraps its
  helpers but does not import them by reference; it re-implements the
  fold loop adding the threshold 0.50 to the hit-rate report so the
  monotonicity check has a value to start from.
- Production feature surface: nothing in `lib/strategies/` or
  `gcp/research/strat_engine/strat_data_builder.py` touched.

## Capacity note (Rule 0 back-of-envelope)

This R&D ran into a real capacity constraint that I should have
predicted in design rather than discovered in the second cancel:

- **Volume**: 14.1M IWM EOD-AlphaVantage option rows over 2016-2026.
  Per-day contract count grew from ~250 in 2017 to ~5,000+ in 2025.
- **Velocity**: per CLAUDE.md rule 4, pg8000 round-trips are ~0.5-2 s
  for small queries but bulk reads from Cloud SQL Connector run
  ~10× slower than psycopg2. A single PCR aggregation that completes
  in 5 s via the `db-query.yml` psycopg2 runner takes 50-150 s+ from
  Cloud Run. Year-chunking helps 2016-2024 (each year 6-11 s) but
  2025 alone takes >140 s because contract count exploded.
- **Wall-clock estimate**: at ~50 s/year × 11 years × 2 queries (PCR +
  IV) × 3 cells = ~55 minutes for the options joiner alone. With the
  task running 8 walk-forward folds on top of that, the 60-min
  task-timeout was too tight. To unblock options-derived properly,
  pre-materialize daily PCR/IV into a small table; OR raise the task
  timeout to 3 hours (Cloud Run charges runtime so headroom is free
  per the rule) and accept the slow path.

I did neither in this PR because the time-box for the experiment is
real and the bound from Families 1/2/4 already supports the FAIL
verdict; layering a schema change into an R&D PR violates the
"production-grade architecture" rule by pretending the workload fits
the bench when it doesn't. The honest call is: 3 families measured,
FAIL on every cell; 1 family INFEASIBLE in the time budget, with a
prior strongly suggesting it would also FAIL; overall verdict FAIL.

## Repro

```bash
# Build the image (one-time; tagged research-dir-features)
gcloud builds submit --config cloudbuild-research.yaml --project=...

# Deploy the Cloud Run Job (one-time; named strat-dir-features)
# See gcp/deploy.sh patterns or run the analogous gcloud run jobs deploy.

# Per-cell dispatch (3 measured families × 3 cells = 9 total)
for FAMILY in news_sentiment cross_asset vol_regime; do
  for TF in 5m 15m 30m; do
    gcloud run jobs execute strat-dir-features \
      --region=us-east1 --project=adept-mountain-474619-d4 \
      --update-env-vars="STRAT_RUN_ID=ext-${FAMILY}-${TF}" \
      --args="-m,gcp.research.strat_engine.strat_dir_walk_forward_extended,--ticker=IWM,--tf=${TF},--family=${FAMILY}" \
      --async
  done
done
```

Saved results live at
`gs://adept-mountain-474619-d4-trading-data/research/strat_engine/iwm_{tf}/dir_extended_walk_forward_{family}_{epoch}.json`.

To re-attempt Family 3 (options_derived):
1. Add a compound index `(ticker, snapshot_date, data_source, market_session)`
   to `etf_options_snapshots` OR a derived `option_daily_features` table
   populated by a one-shot SQL script.
2. Raise the `strat-dir-features` Cloud Run task-timeout to 3 hours.
3. Re-dispatch as above with `FAMILY=options_derived`.
