# Magnitude Engine — Results

> **Verdict: PENDING** — Phase 0 dispatched; results pending the
> walk-forward Cloud Run Job completion. Subsequent phases are
> serially dependent on Phase 0's verdict.

This document records, per-phase / per-cell / per-fold, the magnitude
model's performance against the **pre-set success bar** below. Any line
on this page is post-hoc reporting — none of the thresholds, none of
the fold counts, none of the per-TF ceilings have been or will be
modified after a walk-forward run lands.

---

## 0. Pre-set success bar (IMMUTABLE)

The four gates a single (phase × ticker × tf) cell must clear:

| gate | metric | threshold | min folds passing (of 8) |
|------|--------|-----------|--------------------------|
| G1   | log-loss beat over train-prior base rate | `> 0` (i.e. model beats base) | **6** |
| G2   | Expected Calibration Error (ECE) | `≤ 0.05` for 5m/15m; `≤ 0.075` for 30m | **6** |
| G3   | decisive-call hit rate monotone non-decreasing across `[0.40, 0.50, 0.60, 0.70]` confidence thresholds | monotone | **6** |
| G4   | EXPLOSIVE-bucket lift over base rate | `≥ 1.5` | **6** |

A **phase passes** if it produces cell-passes in **≥ 2 of 3 tickers**
on **≥ 2 of 3 timeframes** (5m, 15m, 30m). The 9-cell grid is treated
as 3 timeframe-rows: a passing phase has at least 2 of those 3 rows
where 2+ tickers pass.

If **Phase 0 fails badly** (all three cells fail, lift near 1.0), the
project stops with the verdict "magnitude is unlearnable from these
features." No subsequent phases are dispatched, no tuning is applied,
no rescues. That's the test.

**Sub-test for moving on**: if Phase 0 passes, Phases 1–4 each test
their additions IN ISOLATION on top of the baseline — not stacked. The
question being answered is "does this feature family add independent
signal," not "what's the best feature stack."

---

## 1. Phase 0 — Baseline (143-col enrichment)

**Hypothesis**: the same feature set that supports the strat-engine
type model carries enough volatility/regime information to discriminate
magnitude buckets.

**Cutoffs**: `2019..2026` (identical to strat-engine walk-forward).

**Dataset**: `strat_features_{tf}` LEFT JOIN `strat_features_levels_{tf}`,
labelled with `magnitude_bucket` (target derived in `mag_dataset.py`).

| ticker | 5m | 15m | 30m |
|--------|----|-----|-----|
| IWM    | PENDING | PENDING | PENDING |
| SPY    | PENDING | PENDING | PENDING |
| QQQ    | PENDING | PENDING | PENDING |

Per-fold detail (filled when Phase 0 completes):

```
ticker  tf  fold              n_test  logloss  base  beat   ece   ECE-pass  lift  G-status
─────────────────────────────────────────────────────────────────────────────────────────
...     ... ...               ...     ...      ...   ...    ...   ...       ...   ...
```

**Phase 0 verdict**: PENDING

---

## 2. Phase 1 — Volatility-family enrichment

**Hypothesis**: features that explicitly measure volatility expansion
(ATR ratios, BB bandwidth, realized-vol z, range expansion, intraday-
range vs prior-day) carry magnitude signal that the type-model
features omit.

**Added features** (computed on-the-fly in `mag_dataset._add_phase1_features`):
- `atr5_atr20_ratio` — short-term vol expansion
- `bb20_bandwidth` — rolling vol envelope width
- `realized_vol_z15` — 15-bar rolling z of log-return std
- `range_expansion_ratio` — current-bar range / avg prior-5-bar range
- `intraday_range_vs_prior_day` — cumulative intraday range / prior-day full range

| ticker | 5m | 15m | 30m |
|--------|----|-----|-----|
| IWM    | PENDING | PENDING | PENDING |
| SPY    | PENDING | PENDING | PENDING |
| QQQ    | PENDING | PENDING | PENDING |

**Phase 1 verdict**: PENDING

---

## 3. Phase 2 — AlphaVantage indicator enrichment

**Backfill required**: `market_data_indicators` table must contain rows
from `gcp/fetchers/fetch_av_indicators.py` for IWM/SPY/QQQ × {daily,
15min}. Until the fetcher runs and rows exist, this phase reports
**PENDING_BACKFILL**.

**Added features** (joined from `market_data_indicators` — AV's
pre-computed values, NOT a local substitute):
- `av_adx` — trend strength
- `av_mfi` — money flow index
- `av_chaikin_ad_osc` — Chaikin A/D oscillator
- `av_aroon_up`, `av_aroon_down`
- `av_roc` — rate of change
- `av_bbands_bandwidth` — derived from AV's BBANDS endpoint

| ticker | 5m | 15m | 30m |
|--------|----|-----|-----|
| IWM    | PENDING_BACKFILL | PENDING_BACKFILL | PENDING_BACKFILL |
| SPY    | PENDING_BACKFILL | PENDING_BACKFILL | PENDING_BACKFILL |
| QQQ    | PENDING_BACKFILL | PENDING_BACKFILL | PENDING_BACKFILL |

**Phase 2 verdict**: PENDING_BACKFILL

---

## 4. Phase 3 — Economic event proximity

**Hypothesis**: bars near (or on) high-impact economic events have
different magnitude distributions than mid-week / no-event bars.

**Added features** (joined from `economic_events` — schedule, NOT
release value):
- `hours_until_next_hi_event`
- `hours_since_last_hi_event`
- `is_event_day_pm4h` — binary, within 4 hours of an event

| ticker | 5m | 15m | 30m |
|--------|----|-----|-----|
| IWM    | PENDING | PENDING | PENDING |
| SPY    | PENDING | PENDING | PENDING |
| QQQ    | PENDING | PENDING | PENDING |

**Phase 3 verdict**: PENDING

---

## 5. Phase 4 — Cross-asset

**Backfill required**: `market_data_cross_asset` (see scaffold at
`gcp/fetchers/fetch_cross_asset.py`).

**Added features**:
- `vix_5m_delta`, `vix_z_15`
- `ust10y_delta`
- `dxy_delta`
- `oil_z`, `gold_z`

| ticker | 5m | 15m | 30m |
|--------|----|-----|-----|
| IWM    | PENDING_BACKFILL | PENDING_BACKFILL | PENDING_BACKFILL |
| SPY    | PENDING_BACKFILL | PENDING_BACKFILL | PENDING_BACKFILL |
| QQQ    | PENDING_BACKFILL | PENDING_BACKFILL | PENDING_BACKFILL |

**Phase 4 verdict**: PENDING_BACKFILL

---

## 6. Phase 5 — Gamma exposure (deferred)

Conditional on **at least one** of Phases 0-4 passing or sitting at
borderline. If all of Phases 0-4 fail decisively, Phase 5 is dropped
and the project verdict stands as "magnitude is unlearnable from the
tested feature families."

---

## 7. Leakage audit

`mag_leakage_audit.py` runs three checks:

1. **Feature-matrix drop set**: `next_open`, `next_close`, `next_high`,
   `next_low`, `magnitude_bucket`, `next_bar_type` must all be in the
   featurize() drop set. PENDING run.
2. **`atr_20` is t-known**: stored values must vary bar-to-bar
   (not silently ffill'd from future). PENDING run.
3. **Phase-1 features no-future-look**: perturbing OHLCV at times > T
   must not change any phase-1 feature value at times ≤ T. PENDING run.

The audit must pass before any phase result is published as a verdict.
If it fails, the result is `LEAK_SUSPECT` regardless of the gate
numbers.

---

## 8. How this file is updated

The walk-forward harness writes per-fold rows to
`magnitude_walk_forward_results` in Cloud SQL and a JSON summary to
GCS (`gs://adept-mountain-474619-d4-trading-data/research/magnitude_engine/{phase}/{ticker}_{tf}/walk_forward_*.json`).
This markdown file is updated by a follow-up commit AFTER each phase
dispatch completes — by querying the results table via `db-query.yml`,
not by editing during a live run. **Edits to this file during a run
are not allowed** because they'd let post-hoc number-fitting back into
the workflow.
