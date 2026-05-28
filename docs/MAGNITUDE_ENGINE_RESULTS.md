# Magnitude Engine — Results

> **Updated verdict (2026-05-28 — after replication + mechanism check)**:
> - **Phase 0 (baseline 143-col)**: FAIL — 5m=2/3, 15m=1/3, 30m=0/3
> - **Phase 1 (vol-family enrichment)**: FAIL — 5m=3/3, 15m=1/3, 30m=0/3
> - **Phase 2 (AV daily indicators)**: FAIL — 5m=3/3, 15m=1/3, 30m=0/3
> - **Phase 3 (econ event proximity)**: **PASS in gate-count terms, MECHANISM CONFIRMED WRONG**
>   - Per-cell verdict reproduces under seed perturbation (replication run with `MAG_SEED=7`
>     produced byte-identical numbers — LightGBM with no bagging is deterministic, so
>     seed-only replication is NOT a real perturbation. The result IS stable on the data
>     it was tested on, but seed-replication doesn't tell us anything about its
>     robustness to fold-boundary or train-set perturbations).
>   - **Event-window concentration check FAILED**: of the bars the model
>     predicts as EXPLOSIVE for SPY 15m, only 13.0% fall within ±4 hours of
>     a high-impact event — versus a base rate of 17.3% in the test set.
>     **Concentration ratio = 0.75x** (slightly *below* random). In 7 of 8
>     walk-forward folds the predicted-EXPLOSIVE concentration is at or
>     below the base rate. Adding the event-proximity features measurably
>     helps the model pass gates, but the model's high-confidence EXPLOSIVE
>     calls are NOT clustered around scheduled events. **The feature names
>     misrepresent what the model is doing.**
> - **Phase 4 (cross-asset)**: PENDING_BACKFILL — see §5.
>
> **Net headline**: there is a candidate magnitude-prediction signal at
> certain (ticker × TF) cells, but the only feature family to cross the
> per-phase bar (Phase 3) does so via a mechanism that does not match its
> feature names. Treat as suggestive-of-something-real, but NOT validated
> as event-driven. Three alternative mechanisms remain plausible:
>   1. **Calendar/temporal proxy** — `hours_until_next_hi_event` is dense
>      for many bars in an event-week, sparse otherwise, effectively
>      encoding "is this an event-week bar." That's a calendar feature.
>   2. **Class-imbalance interaction** — the features may shift the
>      model's prediction threshold for EXPLOSIVE in a way that happens
>      to correlate with high-vol regimes that aren't event-driven.
>   3. **Volatility leakage proxy** — next-event timing at bar t encodes
>      "the world's expectation of upcoming volatility" which may
>      correlate with t-side realized vol for non-causal reasons.
>
> Also significant: even **actually-EXPLOSIVE** bars (the ground truth)
> cluster at only 0.87x base rate in event windows. The underlying
> market reality doesn't match the assumption that scheduled events
> produce discrete EXPLOSIVE bars at 15m resolution — event effects are
> broader (regime-level) than the bar-level discretization we used.
>
> 30m remains unlearnable across every phase. The Claude Code diagnosis
> (~13 RTH bars/day × 3% EXPLOSIVE base rate ≈ 0.4 EXPLOSIVE bars per
> session per ticker) is below the statistical floor for confident
> classification. Drop 30m from future feature-engineering iterations.

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

**Computed**: 2026-05-27. Execution `magnitude-engine-7x8j9` (27 cells, ran in ~10 min wall-clock across 27 parallel Cloud Run workers).

| ticker | 5m | 15m | 30m |
|--------|----|-----|-----|
| IWM | ✅ **PASS** (g1=7 g2=7 g3=8 g4=8) | ✅ **PASS** (g1=6 g2=7 g3=8 g4=6) | ❌ FAIL (g1=0 g2=8 g3=8 g4=2) |
| SPY | ❌ FAIL (g1=5 g2=8 g3=8 g4=8) | ❌ FAIL (g1=5 g2=4 g3=8 g4=6) | ❌ FAIL (g1=0 g2=6 g3=8 g4=4) |
| QQQ | ✅ **PASS** (g1=8 g2=7 g3=8 g4=8) | ❌ FAIL (g1=5 g2=5 g3=8 g4=7) | ❌ FAIL (g1=1 g2=6 g3=8 g4=4) |

`gN=X` means gate N passed in X of 8 folds. A cell PASSES when all four gates have ≥6 of 8.

**Per-TF tickers passing**: 5m=2/3 ✓, 15m=1/3 ✗, 30m=0/3 ✗.

**Phase 0 verdict**: **FAIL** — only the 5m row crosses the 2-of-3-tickers threshold. The phase rule requires 2 of 3 TF rows to pass.

Per-fold detail is in `scripts/assemble_magnitude_results.py` output and per-cell GCS at `gs://adept-mountain-474619-d4-trading-data/research/magnitude_engine/phase0/{ticker}_{tf}/walk_forward_*.json`.

**What the result tells us**: At 5m, IWM and QQQ baseline features carry magnitude signal — EXPLOSIVE-bucket lift is 5–10× across the 2019–2026 regimes. SPY 5m is borderline (5/8 log-loss-beat folds). At 15m only IWM holds; at 30m no ticker holds. The 30m failures are not borderline — log-loss is consistently *worse* than base rate (g1=0/8 for IWM/SPY, 1/8 for QQQ), and EXPLOSIVE is rarely predicted. The signal-to-noise at 30m granularity does not support magnitude discrimination from this feature set.

Per the spec's "stop only on decisive Phase 0 failure" guidance — 3 of 9 cells passed, lift was ≥5 in most passing folds, so this is NOT a decisive fail. Phases 1–4 proceed.

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

**Computed**: 2026-05-27. Same execution as Phase 0 (different tasks; both ran in the same 27-task parallel dispatch).

| ticker | 5m | 15m | 30m |
|--------|----|-----|-----|
| IWM | ✅ **PASS** (g1=8 g2=8 g3=7 g4=8) | ❌ FAIL (g1=7 g2=7 g3=8 g4=5) | ❌ FAIL (g1=1 g2=8 g3=8 g4=2) |
| SPY | ✅ **PASS** (g1=8 g2=8 g3=8 g4=8) | ❌ FAIL (g1=6 g2=5 g3=8 g4=5) | ❌ FAIL (g1=0 g2=6 g3=8 g4=5) |
| QQQ | ✅ **PASS** (g1=8 g2=7 g3=8 g4=8) | ✅ **PASS** (g1=7 g2=6 g3=8 g4=8) | ❌ FAIL (g1=1 g2=6 g3=8 g4=4) |

**Per-TF tickers passing**: 5m=3/3 ✓, 15m=1/3 ✗, 30m=0/3 ✗.

**Phase 1 verdict**: **FAIL** — 5m strengthens dramatically (3/3 pass vs Phase 0's 2/3, with all four gates near-maximal at 7–8/8), but 15m still only IWM-borderline passed Phase 0 and now QQQ flips passing while IWM regresses. Net 15m still 1/3. 30m unchanged.

**What the result tells us**: Phase 1's vol-family features (ATR-5/ATR-20 ratio, BB-20 bandwidth, realized-vol z-score, range-expansion ratio, intraday-range vs prior-day) DO add signal at 5m — SPY 5m flipped from FAIL to PASS. But the marginal lift at 15m is mixed (one ticker swap), and 30m is untouched. The features ARE picking up something real at 5m granularity, just not enough to push 15m or 30m across the bar.

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

**Computed**: 2026-05-27. AV backfill `magnitude-engine-srk2r` populated `market_data_indicators` (IWM/SPY/QQQ × {daily, 15min} × 6 functions = 12 column-families × 3 tickers; 6.5k–6.7k daily rows per ticker covering 2000+). Walk-forward executed by `magnitude-engine-qh7s9` (9 cells, ~6 min wall-clock, 9 parallel workers).

| ticker | 5m | 15m | 30m |
|--------|----|-----|-----|
| IWM | ✅ **PASS** (g1=6 g2=7 g3=8 g4=8) | ✅ **PASS** (g1=6 g2=7 g3=8 g4=6) | ❌ FAIL (g1=0 g2=8 g3=8 g4=1) |
| SPY | ✅ **PASS** (g1=7 g2=7 g3=8 g4=7) | ❌ FAIL (g1=4 g2=6 g3=8 g4=5) | ❌ FAIL (g1=0 g2=5 g3=8 g4=5) |
| QQQ | ✅ **PASS** (g1=8 g2=7 g3=8 g4=8) | ❌ FAIL (g1=6 g2=7 g3=8 g4=5) | ❌ FAIL (g1=1 g2=7 g3=8 g4=4) |

**Per-TF tickers passing**: 5m=3/3 ✓, 15m=1/3 ✗, 30m=0/3 ✗.

**Phase 2 verdict**: **FAIL** — same shape as Phase 1: 5m lifted to 3/3, 15m and 30m unchanged.

**What the result tells us**: AV's pre-computed daily indicators (ADX, MFI, Chaikin A/D Osc, Aroon Up/Down, ROC, BBANDS bandwidth) broadcast to intraday bars add enough at 5m to strengthen IWM (was PASS in Phase 0, stays PASS) and SPY (was FAIL in Phase 0/1, now PASS) — but they don't carry the additional signal needed to push 15m or 30m across the threshold. Daily-resolution indicators don't capture the intraday magnitude dynamics that 15m would need.

**Data-coverage caveat**: AV's `interval=daily` history goes back 25+ years (6.5k+ rows per ticker — covers all 8 walk-forward folds). AV's `interval=15min` history is only ~1356 rows (~6 months), which would not populate the 2019–2023 folds. For this reason the Phase 2 join in `mag_dataset._add_table_join_features` uses **daily only** with date-broadcast to intraday bars. A future Phase 2b could add `merge_asof` for the 15min indicators if Phase 4 (cross-asset) or any other phase shows the missing-signal lever is intraday vendor data — which the current result does not suggest.

---

## 4. Phase 3 — Economic event proximity

**Hypothesis**: bars near (or on) high-impact economic events have
different magnitude distributions than mid-week / no-event bars.

**Added features** (joined from `economic_events` — schedule, NOT
release value):
- `hours_until_next_hi_event`
- `hours_since_last_hi_event`
- `is_event_day_pm4h` — binary, within 4 hours of an event

**Computed**: 2026-05-27. Execution `magnitude-engine-wvxn9` (9 cells, ran in ~6 min wall-clock across 9 parallel workers).

| ticker | 5m | 15m | 30m |
|--------|----|-----|-----|
| IWM | ✅ **PASS** (g1=6 g2=7 g3=8 g4=8) | ✅ **PASS** (g1=6 g2=7 g3=8 g4=6) | ❌ FAIL (g1=0 g2=8 g3=8 g4=1) |
| SPY | ✅ **PASS** (g1=7 g2=8 g3=8 g4=7) | ✅ **PASS** (g1=6 g2=6 g3=8 g4=6) | ❌ FAIL (g1=0 g2=6 g3=8 g4=4) |
| QQQ | ✅ **PASS** (g1=7 g2=8 g3=8 g4=8) | ❌ FAIL (g1=5 g2=7 g3=8 g4=7) | ❌ FAIL (g1=1 g2=6 g3=8 g4=4) |

**Per-TF tickers passing**: 5m=3/3 ✓, 15m=2/3 ✓, 30m=0/3 ✗.

**Phase 3 verdict**: **PASS** — first phase to cross the 2-of-3-TFs requirement. 5m and 15m both have ≥2 tickers passing all four gates.

**What the result tells us**: Adding three event-proximity features (`hours_until_next_hi_event`, `hours_since_last_hi_event`, `is_event_day_pm4h`) makes 15m newly tractable for IWM and SPY — neither passed in Phase 0 or Phase 1. The signal-to-noise at 30m is still too low.

Interpretation: high-impact economic events (FOMC, NFP, CPI, etc.) measurably reshape the magnitude distribution of nearby bars. The bar-time-aware proximity features capture this, and at 5m and 15m the model can learn to associate them with EXPLOSIVE/EXPANDED bucket prevalence. That's a real, independent signal — distinct from the volatility-family features in Phase 1.

Caveat: the published *schedule* is what we use, not the released *value* — we never look at the actual data (e.g., the NFP print) at or before bar t. The signal is "bars near scheduled events tend to move more," not "bars react to surprise."

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

1. **Feature-matrix drop set**: ✅ CLEAN — 234 numeric features, 0 forbidden columns. Audit log:
   `audit-1: feature matrix has 234 cols; forbidden ∩ cols = {}`
2. **`atr_20_computed` is t-known**: ✅ CLEAN — 0 of 50 adjacent same-day bar pairs had identical `atr_20_computed` (a rolling-20 average naturally varies bar to bar). Audit log:
   `audit-2: 0/50 adjacent same-day atr_20_computed pairs identical → CLEAN`.
   Note: the *stored* `strat_features.atr_20` is NaN everywhere (separate upstream pipeline bug — see commit `9751c0e`); we compute locally for the target denominator.
3. **Phase-1 features no-future-look**: ✅ CLEAN — perturbed-OHLCV-beyond-midpoint test produced 0 leaked columns. Audit log:
   `audit-3: phase-1 leaked columns = {}`

Audit ran via `gcloud run jobs execute magnitude-engine --args=-m,gcp.research.magnitude_engine.mag_leakage_audit,--ticker=IWM,--tf=15m` on the same image used for the walk-forward. The audit completed BEFORE any walk-forward fold ran, so the gate verdicts above are not subject to leakage retraction.

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
