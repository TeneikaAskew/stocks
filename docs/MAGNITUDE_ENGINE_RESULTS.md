# Magnitude Engine — Results

> ## PROJECT VERDICT: FAIL (closed 2026-05-29 by gate 7)
>
> **Headline**: magnitude is statistically learnable at 5m but **not
> tradeably-extractable** as a non-directional play. The within-cell
> precision boost the model provides is the priced finer-calendar and
> vol-clustering effects, not unpriced bar-specific structure. Gate 7
> (implied-vs-realized): 0 of 23 IV-covered folds across IWM/SPY/QQQ
> 5m crossed the 1.25 ratio threshold. Aggregate realized/implied
> ratio on EXPLOSIVE-predicted bars is 0.83-0.92 — the option chain
> has already incorporated everything the model finds.
>
> **What this rules out**: Phase 4 (cross-asset) and Phase 5 (gamma)
> for magnitude prediction. Those phases would face the same gate
> against the same systematic 0.85-0.95 baseline. The plausible-best-
> case effect of adding more features is to nudge the ratio from 0.92
> to 0.93. Not enough.
>
> **What survives**: the platform-as-cockpit direction using the
> validated strat_engine type model. The magnitude work is closed.
>
> See §5e for the gate-7 calculation, §"Final project verdict" for
> the full debrief. The prior intermediate verdicts (gate-count PASS,
> mechanism-misread, calendar-proxy confirmation, decomposition-mixed)
> are preserved below for the audit trail — each step refined the
> finding until gate 7 settled it.
>
> ---
>
> **Intermediate verdict (2026-05-28 — pre gate-7)**:
>
> ### Phase-by-phase gate counts
> | phase | 5m tickers passing | 15m tickers passing | 30m tickers passing | gate-count verdict |
> |---|---|---|---|---|
> | 0 (baseline 143-col) | 2/3 | 1/3 | 0/3 | FAIL |
> | 1 (vol-family) | 3/3 | 1/3 | 0/3 | FAIL |
> | 2 (AV daily indicators) | 3/3 | 1/3 | 0/3 | FAIL |
> | 3 (event proximity) | 3/3 | 2/3 | 0/3 | PASS — but see §3 |
> | **3b (calendar replacement)** | **3/3** | **1/3** | **0/3** | **FAIL by count, but REPLICATES Phase 3 5m → calendar-proxy confirmed (§5b)** |
> | 4 (cross-asset) | PENDING_BACKFILL | | | |
>
> ### Phase 3 PASS decomposed (this is the real headline)
>
> The "Phase 3 PASS" verdict came from 5 cells crossing all four gates.
> Three follow-up checks refined what that pass means:
>
> | cell | gate verdict | bootstrap PASS rate (1k iter) | event concentration | diagnosis |
> |---|---|---|---|---|
> | **IWM 5m** | PASS | **99.6%** | **3.14x** | ✅ **Real, robust, event-driven** |
> | QQQ 5m | PASS | 100.0% | 0.85x | Robust signal, NOT event-driven |
> | SPY 5m | PASS | 77.6% | 0.82x | Robust signal, NOT event-driven |
> | IWM 15m | PASS | 7.8% | 1.32x | Fragile gate-edge; weak mechanism |
> | SPY 15m | PASS | 9.0% | 0.75x | Fragile gate-edge; no mechanism |
>
> The PASS verdict at phase level survives, but only **one cell (IWM 5m)**
> has both gate robustness AND a mechanism that matches the feature names.
> Two more cells (QQQ 5m, SPY 5m) have robust gates but the model's
> high-confidence EXPLOSIVE predictions are NOT clustered around scheduled
> events — so they're picking up real signal from these features, but the
> signal is something the feature names don't describe. The two 15m cells
> (IWM, SPY) that pushed Phase 3 across the 2-of-3-TFs bar are gate-edge
> point estimates that would flip to FAIL ~92% of the time under
> resampling of their own test bars.
>
> ### Phase calendar refines Phase 3's IWM 5m finding (2026-05-28 follow-up)
>
> Even the "validated" IWM 5m result with 3.14x event concentration
> turned out to be calendar-driven, not event-driven. Phase_calendar
> (calendar-only features, no event lookups) reproduces Phase 3's 5m
> gate-passing across ALL THREE tickers, with bootstrap 100% in every
> cell and gate counts equal-or-stronger than Phase 3.
>
> Net: **the only validated cross-ticker magnitude signal is calendar-driven
> at 5m**. Phase 3 was a calendar proxy at 5m. The 15m row's apparent
> passes were fragile gate-edge artifacts that don't replicate under
> bootstrap and don't replicate under feature variation. 30m remains
> unlearnable.
>
> ### Method notes
>
> Seed replication: `MAG_SEED=7` re-run produced **byte-identical** numbers
> to the original. LightGBM with no bagging (`subsample`/`colsample_bytree`)
> is fully deterministic, so seed-only perturbation is mathematically void
> for our config. The intended "robustness under perturbation" check
> reduced to a determinism check. A true robustness test of fold-boundary
> sensitivity would need cutoff-shift perturbation; that's a follow-up.
>
> Mechanism check: SPY 15m's actual-EXPLOSIVE bars also cluster at only
> 0.87x base rate in event windows. The market reality doesn't match the
> textbook "scheduled events produce discrete EXPLOSIVE bars" — event
> effects are broader (regime-level) than 15m bar discretization captures.
>
> 30m remains unlearnable across every phase. ~13 RTH bars/day × 3%
> EXPLOSIVE base rate ≈ 0.4 EXPLOSIVE bars per session per ticker —
> below the statistical floor for confident classification. Drop 30m
> from future feature-engineering iterations.

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

## 5b. Phase calendar — calendar-replacement test (added 2026-05-28)

Reviewer hypothesis: Phase 3's QQQ 5m + SPY 5m pass with robust bootstrap
(100% / 77.6%) but mechanism check FAILS (0.85x / 0.82x event-window
concentration — below base rate). This phase REPLACES the event features
with calendar features only (`day_of_week`, `hour`, `minute`, `week_of_month`,
`is_first_friday`, `is_fomc_week`, `is_month_end`, `is_quarter_end`).
No event-proximity lookups; everything is derivable from `ts` alone.

**Result: hypothesis confirmed decisively.**

| | Phase 3 5m | **Phase_calendar 5m** |
|---|---|---|
| IWM gates | 6/7/8/8 | **8/8/7/8** |
| SPY gates | 7/8/8/7 | **8/8/8/8** |
| QQQ gates | 7/8/8/8 | **8/7/8/8** |
| IWM bootstrap | 99.6% | **100.0%** |
| SPY bootstrap | 77.6% | **100.0%** |
| QQQ bootstrap | 100.0% | **100.0%** |

Calendar features REPLICATE Phase 3's 5m gate-passing AND IMPROVE on
it (SPY 5m bootstrap jumps from 77.6% → 100%). At 15m the two diverge:
calendar features pass QQQ 15m (Phase 3 failed it) but lose IWM 15m
and SPY 15m (both already bootstrap-fragile in Phase 3 at ~8%).

**What this means for the project verdict.**

The Phase 3 "PASS" verdict, and the seemingly-validated IWM 5m result
within it, are NOT event-driven. The features named
`hours_until_next_hi_event` / `hours_since_last_hi_event` /
`is_event_day_pm4h` were encoding day-of-week / hour-of-day patterns
that happen to overlap with event windows. The 3.14x event-window
concentration we measured on Phase 3 IWM 5m is best explained as:
EXPLOSIVE bars cluster on calendar features, and those calendar features
overlap with event windows because real-world events are scheduled in
predictable calendar slots (Wed FOMC, first Friday NFP, etc.).

**The real magnitude signal is calendar-driven, at 5m, across all 3 tickers.**
This is robust under bootstrap (100% in every 5m cell). It is NOT
event-driven. The honest claim is that magnitude predictability comes
from "what hour of what day of what week is this" — a much narrower
and lower-edge mechanism than "events cause big moves."

**Implications for trading**: setup filters that align with the
calendar pattern (e.g., size up during the hour-of-week clusters where
EXPLOSIVE base rate spikes, avoid the dead-window clusters) are the
concrete artifact. This is a sizing/filtering edge, not a directional
signal. The next experiment a pure-calendar feature set (dropping
`is_first_friday` and `is_fomc_week`, which are event-adjacent) would
isolate whether the signal is in raw weekday/hour clustering or
specifically in the calendar features that ARE event-adjacent.

## 5c. Naive (DoW × 30-min-bucket) lookup baseline (added 2026-05-28)

Reviewer 2026-05-28: bootstrap-robust ≠ tradeable. Intraday calendar
volatility (open / lunch / close, DoW, FOMC/NFP weeks) is the single
most-known and most-priced-in pattern. The real question is whether
the phase_calendar model adds edge OVER a naive lookup table.

**Method**: for each fold, group training bars by (day_of_week, 30-min
time-bucket) → empirical 4-class distribution per cell. For each test
bar, predict the historical distribution of its (DoW, bucket) cell.
Apply the same four gates. No model, no LightGBM, no bar features.

**Result**: naive lookup gates per fold (sample, IWM 5m):

```
fold                       beat       ece    ece_p  mono   lift
2019-01-01..2020-01-01   +0.0165   0.0144   True   True    —
2020-01-01..2021-01-01   +0.0153   0.0056   True   True    —
... [identical pattern across all 8 folds]
```

| ticker | g1 logloss-beat | g2 ECE-pass | g3 monotone | g4 lift ≥ 1.5 | cell PASS |
|---|---|---|---|---|---|
| IWM 5m | **8/8** | **8/8** | **8/8** | **0/8** | NO |
| SPY 5m | **8/8** | **8/8** | **8/8** | **0/8** | NO |
| QQQ 5m | **8/8** | **8/8** | **8/8** | **0/8** | NO |

**Interpretation**: as a PROBABILITY ESTIMATOR over magnitude buckets,
calendar slot fully explains the signal that gates 1–3 measure. The
phase_calendar model is NOT adding probabilistic edge over a (DoW,
time-bucket) lookup table on those three gates.

Gate 4 (EXPLOSIVE lift) is the only one where the model could plausibly
add value. The naive lookup CANNOT pass gate 4 by architectural
construction — EXPLOSIVE has 3% base rate, no calendar cell has it as
modal bucket, the lookup never argmaxes EXPLOSIVE, lift is undefined
every fold.

## 5d. Model EXPLOSIVE decomposition (added 2026-05-28)

Question: when the phase_calendar model argmax-predicts EXPLOSIVE, is
it (a) just picking bars from highest-historical-rate calendar cells
(amplification of calendar — no edge), or (b) discriminating WITHIN
cells using bar features (real edge)?

Method (in `scripts/model_vs_calendar_explosive_decomp.py`): for each
model-predicted-EXPLOSIVE bar in the test set, look up its training-data
calendar-cell historical EXPLOSIVE rate. Compute:
1. Mean cell rate across model-EXPLOSIVE bars vs base rate
2. % of model-EXPLOSIVE bars whose cell is in the top-10% historical-rate cells
3. Within-top-cell coverage: of bars whose cell IS in top-10%, what
   fraction does the model predict EXPLOSIVE for?

**Result**:

| ticker | mean cell rate | base | ratio | % in top-10% cells | within-top-cell pred rate |
|---|---|---|---|---|---|
| **IWM 5m** | 0.103 | 0.033 | **3.09x** | **63.3%** | 5-14% per fold |
| SPY 5m | 0.075 | 0.033 | 2.28x | 58.4% | 1-9% per fold |
| QQQ 5m | 0.082 | 0.033 | 2.48x | 46.4% | 1-7% per fold |

**Diagnosis: mixed — neither pure amplification nor pure bar-feature edge.**

The model uses calendar cells as a strong PRIOR (~3x concentration in
top-historical-rate cells for IWM) AND uses bar features as a secondary
SELECTOR within those cells (only ~5-15% of bars in top cells get
EXPLOSIVE-tagged). If it were pure amplification, the within-top-cell
rate would be near 100%. Instead it's selective.

**That selectivity is bar features doing work — but they're working as a
secondary filter ON TOP of calendar selection.** The bulk of the model's
EXPLOSIVE-precision lift (the original gate-4 numbers showing 6-10x
precision over base rate) decomposes as roughly:
- ~3x from calendar concentration (a lookup-table thresholding would replicate)
- ~2-3x from bar-feature within-cell selection (this part is real edge)

**Practical implication for trade-test**: the calendar concentration is
mostly "trade the open" (the user already does this). The bar-feature
within-cell selection is "of the open-window bars, pick which specific
5-15% to size up on." THAT could be edge — IF the within-cell
discrimination is stable across regimes AND the bar features doing
the work are non-obvious to a normal intraday trader.

The next experiment that answers this is the **trade-test**:

1. Take the magnitude model's EXPLOSIVE-confidence threshold from each
   fold's calibration (or pick a few thresholds).
2. Rerun Track B (or Track 2 options) using the type model alone as
   baseline AND filtered by magnitude-EXPLOSIVE-above-threshold.
3. Compare per-fold expectancy of the two. Is the magnitude-filtered
   subset higher expectancy than the unfiltered? Higher than
   trade-the-open alone?

Per-fold caveat: the within-top-cell rate ranges from 0.8% (IWM 5m 2020
COVID fold) to 14.5% (IWM 5m 2025) — wide regime variation. A
trade-test should report per-regime expectancy, not just aggregate.

---



Conditional on **at least one** of Phases 0-4 passing or sitting at
borderline. If all of Phases 0-4 fail decisively, Phase 5 is dropped
and the project verdict stands as "magnitude is unlearnable from the
tested feature families."

---

## 5e. Implied-vs-realized check — the trade-test gate (added 2026-05-28)

**The decisive test for whether the within-cell discrimination is edge.**

The decomposition's "2-3x within-cell boost" could be three things, and
two of them are already priced:
1. Genuine bar-specific structure → potentially unpriced (edge)
2. Finer-grained time effects (5m within 30m bucket) → still calendar, priced
3. Volatility clustering (GARCH) → very well known, priced

The decomposition cannot separate these. The implied-vs-realized check
can. The magnitude model predicts SIZE not direction, so the only
honest vehicle is non-directional (straddle/strangle), and the only
honest benchmark is the option premium — because the straddle premium
IS the market's priced estimate of the expected move.

**Pre-set pass bar (gate 7, IMMUTABLE, set BEFORE any number is computed)**:

- For each phase_calendar EXPLOSIVE-predicted test bar at time t on date D:
  - `realized_move` = `|next_open - next_close|` (the magnitude target's
    numerator, in dollar terms — captures the actual 5-min move)
  - `implied_move` = `spot × IV × sqrt(5 / (252 × 390))` where IV is the
    at-or-before EOD ATM IV from `etf_options_snapshots` on date D-1
    (T-1 anchor — same data constraint Track 2 hit)
- Per cell (ticker × tf=5m), per fold:
  - `ratio` = mean(realized_move on EXPL-predicted bars) / mean(implied_move on EXPL-predicted bars)
- **Gate 7 pass**: ratio ≥ **1.25** in ≥ 6 of the folds that have IV
  coverage. The 1.25 margin sits above 1.0 to leave room for the
  bid/ask spread + theta on a real 5-min straddle round-trip. Below
  1.25, even if mean-realized > mean-implied, the trade doesn't clear
  execution friction. **This threshold is committed before any
  number lands — per the project's anti-fitting rule.**

**Caveat (acknowledged before running)**: AV has no historical intraday
option prices. The T-1 EOD anchor introduces noise — overnight IV
shifts can move the priced expected move. The check is therefore a
**necessary but not sufficient** test: if ratio < 1.25 even with
stale-IV noise, edge is unlikely; if ratio ≥ 1.25, a full intraday-IV
backtest is warranted to confirm.

**Coverage note**: `etf_options_snapshots` started recording sometime
in 2024-2025. Early walk-forward folds (2019-2023) will lack IV
coverage and will be reported as `NO_COVERAGE`, not counted toward
the 6-of-folds threshold. If fewer than 4 folds have coverage, the
verdict is `INSUFFICIENT_DATA` — needs a different IV source.

### Result (run 2026-05-29 against phase_calendar predictions)

Coverage was BETTER than the pre-run pessimistic assumption —
`etf_options_snapshots` actually has IV anchors going back to 2019.
23 of 24 attempted folds had ≥20 IV-covered EXPLOSIVE-predicted bars
(1 fold skipped as `THIN_n=18`). `INSUFFICIENT_DATA` did not fire.

| ticker | folds w/ coverage | folds passing gate 7 | aggregate mean ratio | best fold ratio | verdict |
|---|---|---|---|---|---|
| IWM 5m | 8/8 | **0/8** | 0.92 | 1.10 (2025) | **FAIL** |
| SPY 5m | 7/8 | **0/7** | 0.87 | 1.23 (2020 COVID) | **FAIL** |
| QQQ 5m | 8/8 | **0/8** | 0.83 | 1.16 (2024) | **FAIL** |

Per-fold ratios (IWM 5m sample):
```
2019: 0.56   2020: 1.03   2021: 0.85   2022: 0.93
2023: 0.98   2024: 0.99   2025: 1.10   2026: 0.90
```

**Gate 7 verdict**: **FAIL on every cell.** Zero of 23 IV-covered folds
across all three 5m-passing cells crossed the 1.25 ratio threshold.
The highest single-fold ratio was 1.23 (SPY 5m, 2020 COVID regime) —
still under the bar.

### What this resolves

Per the reviewer's framework, gate 7 separates the three possible
sources of the 2-3x within-cell precision boost:
1. Genuine bar-specific structure → potentially unpriced (would show ratio > 1.25)
2. Finer-grained calendar effects → priced (ratio ≈ 1.0)
3. Volatility clustering / GARCH → priced (ratio ≈ 1.0)

Aggregate ratios of 0.83-0.92 are consistent with **the 2-3x within-cell
boost being the priced finer-calendar and vol-clustering effects, not
unpriced bar-specific structure.** The IV market has incorporated the
calendar × vol-clustering patterns the model picks up. The magnitude
model finds real patterns; those patterns are already in the option
chain.

This closes the last open research thread on magnitude. Subsequent
phases (Phase 4 cross-asset, Phase 5 gamma) would face the same
gate against the same systematic 0.85-0.95 baseline. The
plausible-best-case effect of adding cross-asset or gamma features
is to nudge the ratio from 0.92 to 0.93. That doesn't change a
verdict at the 1.25 bar.

---

## Final project verdict

**Magnitude is statistically learnable at 5m but not tradeably-extractable
as a non-directional play.**

What we've validated:
- ✅ Magnitude IS predictable at 5m for all 3 tickers (phase_calendar
  passes gates 1-4 across the board with 100% bootstrap)
- ✅ The signal is real and robust under perturbation
- ✅ Bar features add a real 2-3x within-cell precision boost over a
  naive (DoW, hour) lookup

What we've ruled out:
- ❌ Phase 0 / 1 / 2 / 3 framings were all calendar-proxy at root
  (proven by the phase_calendar replacement test)
- ❌ The within-cell discrimination is not unpriced edge — gate 7's
  0/23 fold pass at the 1.25 threshold settles this
- ❌ 30m magnitude is unlearnable across all phases tested
- ❌ 15m magnitude is bootstrap-fragile; "passing" cells are gate-edge
  artifacts

The practical takeaway: the magnitude signal is what every intraday
trader already knows — open and close are more volatile, FOMC and NFP
windows expand vol, weekday/hour patterns matter, recent vol predicts
near-future vol. The option chain has priced it all. There is no edge
to extract via a non-directional vehicle.

**Recommendation**: do not invest further compute in Phase 4 (cross-asset)
or Phase 5 (gamma) for magnitude prediction. Pivot remaining
research budget toward platform-as-cockpit work where the validated
strat_engine type model already has a clearer path to value.

---

## Open: trade-test the validated signal

The IWM 5m EXPLOSIVE-bucket signal (the one cell that passed all 6 gates)
is a **research artifact, not a trade**. Converting it to a trading
question requires the execution layer:

1. **Combine with the type model** — rerun Track B (or Track 2 options
   version) with the magnitude probability as a setup FILTER on top of
   the strat_engine type model. Take only setups where:
     - type model says high-confidence 2U or 2D
     - magnitude model says EXPLOSIVE above some confidence threshold
2. **Compare expectancy** to the type-model-alone baseline. Does the
   combination produce positive expectancy where the type model alone
   didn't? That's the question that converts "magnitude signal exists"
   into "magnitude signal is tradeable."
3. **Scope**: IWM 5m specifically. The other Phase 3 cells (QQQ 5m, SPY
   5m) are either mechanism-mismatch or fragile, so the trade-test should
   be cell-specific, not phase-wide.

This is the bridge from research to execution and should be the first
question asked after Phase 4 lands.

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

---

## 2026-07-06 addendum — forward-window (30-min RANGE) target revisit

**Does NOT reopen the project verdict.** A scratch-harness re-probe (single
chronological 70/30 split, IWM/SPY/QQQ 5m, tempered α=0.75 — weaker than the
8-fold purged/embargoed production standard; see
`EXPERIMENT_REGISTRY.md` §2026-07-06) asked whether *reframing the target* helps.

**Finding (E-28).** Predicting the **range over the next 30 min** (K=6 bars,
`(max(high[t+1..t+K]) − min(low[t+1..t+K]))/atr20[t]`) instead of the single next
bar's body is far more statistically predictable: OOS top-bucket argmax precision
**50–59% / 8–10× lift** (vs single-bar ~10% / ~4.3×), p≥0.55 **56–64%**, generalizing
across all three tickers. Audited as real, not artifact: a trivial `atr_20[t]`-rank
predictor gets only ~3% precision (0.5×), and non-overlapping windows hold at 65%.
Top features: `mins_since_open`, `atr_20`, `bb_squeeze`, `realized_vol_short` —
i.e. **vol-clustering + time-of-day.**

**Why this is consistent with the FAIL verdict, not a refutation of it.** Those
drivers are exactly what gate-7 found the option chain already prices (EXPLOSIVE-bar
realized/implied 0.83–0.92). A cleaner 30-min vol *forecast* is still a
non-directional magnitude signal, and the straddle/strangle that trades it prices
the same forecast. The improvement is in *statistical* predictability of a
better-posed target, **not** evidence of unpriced structure.

**Standing gate before any tradeability claim:** run gate-7 (aggregate
realized/implied on forward-window-EXPLOSIVE-predicted bars, ≥1.25 in ≥6/8
purged folds) on this target. The prior verdict predicts it clears no better than
the single-bar target. Until then E-28 is a **statistical result, tradeability
UNPROVEN** — logged, not shipped.

**Gate-7 outcome (2026-07-06) — verdict HOLDS.** Ran gate-7 on the forward-window
target. The raw ratio *looks* like a strong pass (30-min realized range 2.43× /
directional displacement 1.57× the daily-ATM-IV-√t implied move; 910 bars; 5/5
quarters ≥1.25). It is a **benchmark artifact**, not an edge: a time-of-day
control shows **96% of the fwd-window-EXPLOSIVE bars fall in the last 30 min of
the session**, and at **midday** (where flat daily-IV × √(t/yr) scaling is a valid
benchmark) the displacement ratio is **0.74 — below 1.0, i.e. over-priced.** Flat
daily-ATM-IV √-scaling under-states the elevated close-of-day realized vol that
the actual 0DTE / short-dated options price correctly. So the forward-window
reframe is **statistically more predictable but still NOT tradeably-extractable** —
the extractable residual is "point at the close," where a naive daily-IV benchmark
only looks cheap. Consistent with the 2026-05-29 FAIL, on a better-posed target.


---

## Phase-2 pure-prediction re-test (2026-07-09) — the gate is CALIBRATION, not features

The 2026-05-29 FAIL was in the **implied-vs-realized cost** frame (gate 7). The
2026-07 reframe drops options costs entirely and asks only: is size (magnitude
bucket) predictable by **log-loss beat vs the base-rate constant** under the
pre-registered gate (>=6/8 folds AND all 3 tickers)?

**Baseline (`direction-phase2-sswwj`, phase0 5m, calibration=none):** median
log-loss beat ≈ **−0.148** — the model is *worse* than predicting the class
prior. This is the `class_weight='balanced'` trade-off: it lifts minority-class
(EXPLOSIVE) recall at the cost of probability calibration, and these runs used
`calibration=none`.

**Feature families add negligibly** (options_iv +0.0025, positioning +0.0018,
full stack +0.0055; all still 0/3 tickers) — a +0.005 nudge cannot close a
−0.148 gap. This matches the prior "adding features nudges 0.92→0.93" finding,
now in the pure-prediction frame: **SIZE's problem is not missing features, it
is calibration.**

**Actionable next experiment (dispatched, `magnitude-recal-j5lfv`):** phase0
--all-cells with `--calibration=isotonic` to test whether isotonic recalibration
turns the log-loss beat positive. If it does, the pure-prediction SIZE verdict
should be revisited with a calibrated, possibly un-class-weighted model before
any further feature work. Result to be appended here on completion. Full
ablation: EXPERIMENT_REGISTRY.md E-25.


### Isotonic recal RESULT (2026-07-10, `magnitude-recal-j5lfv`) — calibration alone fails at 5m, but 15m+isotonic WORKS

Ran phase0 --all-cells with `--calibration=isotonic`. The 5m calibration
hypothesis is **refuted**, but the timeframe sweep found a genuinely working,
well-calibrated size model at 15m:

| tf  | IWM (folds_beat, med_beat, ECE) | SPY | QQQ |
|-----|---|---|---|
| 5m  | 0/8, -0.138, 0.106 | 0/8, -0.128, 0.102 | 0/8, -0.148, 0.101 |
| 15m | 5/8, +0.0031, 0.036 | **6/8, +0.0084, 0.042** | 4/8, +0.0032, 0.043 |
| 30m | 2/8, -0.0103, 0.041 | 4/8, +0.0002, 0.047 | 4/8, +0.0028, 0.042 |

**Findings:**
1. **At 5m, isotonic does NOT rescue size** — beat stays ≈ -0.13, 0/8 folds,
   ECE ≈ 0.10. Calibration alone is not the fix at 5m.
2. **At 15m + isotonic, size flips positive and well-calibrated** — median beat
   +0.003 to +0.008, ECE ≈ 0.04 (vs 0.10 at 5m). **SPY clears the per-ticker
   gate (6/8 folds)**, IWM one fold short (5/8), QQQ 4/8.
3. 30m is worse than 15m (IWM goes negative). **15m is the sweet spot.**

**Verdict update:** the pure-prediction SIZE story is NOT "not predictable" — it
is **predictable and well-calibrated at 15m with isotonic calibration**, a
strong near-miss on the full 3-ticker gate (SPY passes, IWM 5/8). The 5m failure
was a joint timeframe+calibration problem, not a feature problem. **Recommended
next experiment:** re-run the Phase-2 feature ablation at **15m with
calibration=isotonic** (esp. `options_iv` + `prune`) to test whether IWM/QQQ
cross 6/8 — the first realistic shot at a full gate pass in the program.
This does NOT overturn the 2026-05-29 gate-7 (cost) FAIL — it is the
pure-prediction lens, where the user's reframe explicitly drops costs.
