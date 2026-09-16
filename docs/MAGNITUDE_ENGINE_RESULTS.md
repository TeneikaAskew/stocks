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

> **Amendment 2026-09-14 (gate 4 population).** G4's metric (realised
> EXPLOSIVE lift over base rate) and threshold (≥ 1.5 in ≥ 6/8 folds) are
> unchanged. What changed is *which bars count as "predicted EXPLOSIVE"*:
> the served decision rule (`decide_bucket`: P(EXPLOSIVE) ≥ 2.0 × its
> training prior) rather than argmax. Under argmax a calibrated model
> named EXPLOSIVE on ~12 bars per fold and the gate passed on noise (4 of
> 12 right read as 13.4× lift). Under the rule it is scored on the same
> population the consumer sees. Every gate count before this date was
> computed on the argmax population; see the 2026-09-14 section.

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
dispatch completes — by querying the results table via
`./scripts/db_query_cr.sh` (the `db-query.yml` workflow it replaced was
deleted 2026-05-30) and the GCS summaries, not by editing during a live
run. **Edits to this file during a run
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


### GATE PASS (2026-07-11, `direction-phase2-cmv2d`) — SIZE is PREDICTABLE at 15m+isotonic

Re-ran the Phase-2 size ablation at **15m with calibration=isotonic** (7 configs,
config-tagged GCS results). Result: **every config clears the pre-registered gate
(>=6/8 folds on ALL 3 tickers).**

| config | IWM | SPY | QQQ | tickers_pass | predictable | med_beat |
|---|---|---|---|---|---|---|
| baseline | 6/8 | 7/8 | 6/8 | 3/3 | **True** | +0.0090 |
| prune | 8/8 | 7/8 | 6/8 | 3/3 | **True** | +0.0120 |
| options_iv | 7/8 | 7/8 | 6/8 | 3/3 | True | +0.0097 |
| positioning | 6/8 | 7/8 | 6/8 | 3/3 | True | +0.0100 |
| cross_asset | 7/8 | 7/8 | 6/8 | 3/3 | True | +0.0076 |
| calendar | 6/8 | 7/8 | 6/8 | 3/3 | True | +0.0088 |
| full stack | 8/8 | 7/8 | 6/8 | 3/3 | True | +0.0115 |

**This is the program's first pre-registered gate pass.** The winning
configuration is **timeframe (15m) + isotonic calibration**, NOT features — even
the baseline (no new families) passes. **`prune` adds the most margin** (IWM 6→8/8,
best median beat +0.012); the options/cross-asset/calendar families add little on
top. ECE ≈ 0.04 (well-calibrated).

**Caveats / rigor:** the edge is modest (median log-loss beat +0.009 to +0.012)
and IWM/QQQ baseline sit exactly at the 6/8 threshold — run-to-run CV variance is
real (the earlier `magnitude-recal` all-cells run showed IWM 5/8, QQQ 4/8 for the
same cell; this properly-tagged ablation shows 6/8, 6/8). The **pruned** config is
the robust one (IWM 8/8 gives margin). Recommended before production: a bootstrap/
repeat run to confirm the pruned config holds >=6/8 across resamples, and note
this is the PURE-PREDICTION lens (log-loss), distinct from the 2026-05-29 gate-7
(implied-vs-realized cost) FAIL — which the user's reframe explicitly set aside.

**Bottom line:** SIZE (magnitude bucket) IS walk-forward predictable and
calibrated at 15m; the 5m failure was a joint timeframe+calibration problem.
Deploy target: 15m + isotonic + prune.


### Bootstrap confirmation (2026-07-11) — pass holds; QQQ is the marginal leg

Bootstrapped the 8 fold-beats per ticker (5000 resamples, P of still >=6/8) for
the winning `prune` config at 15m+isotonic:

| ticker | folds_beat | fold beats | boot P(>=6/8) |
|---|---|---|---|
| IWM | 8/8 | all +0.004..+0.012 | **1.00** (rock solid) |
| SPY | 7/8 | one -0.005, rest +0.009..+0.025 | 0.94 (strong) |
| QQQ | 6/8 | two neg (-0.005,-0.020) in earliest folds, rest +0.009..+0.019 | **0.69** (marginal) |

IWM and SPY are robust; **QQQ sits at the threshold** — its two earliest test
folds (least training data) are negative, so ~31% of resamples drop it below 6/8.
`prune` beats `baseline` (baseline had an IWM fold at -0.036). **Before trusting
SIZE live, confirm QQQ** with a shifted-cutoffs run and/or more history. The pass
is real; QQQ is the leg to watch.


### Shifted-cutoffs CONFIRMATION (2026-07-11, `magnitude-recal-jcv9r`) — gate pass is FOLD-FRAGILE

Re-ran the winning config (15m + isotonic + prune) with **mid-year fold
boundaries** (2018-07..2025-07 instead of Jan-1) to test whether the gate pass
was cutoff-luck.

| ticker | folds_beat (shifted) | median_beat | min_beat | ECE | vs Jan-1 |
|---|---|---|---|---|---|
| SPY | 8/8 | +0.0172 | +0.0015 | 0.038 | 7/8 → 8/8 (stronger) |
| QQQ | 6/8 | +0.0117 | -0.0406 | 0.053 | 6/8 → 6/8 (held) |
| IWM | 5/8 | +0.0031 | -0.0139 | 0.036 | 8/8 → **5/8 (dropped)** |

**Finding: the strict per-ticker gate is FRAGILE to fold placement.** QQQ (the
Jan-1 marginal leg) held at 6/8, but IWM fell from 8/8 to 5/8 — the marginal
ticker SWAPS with the cutoff scheme. So "≥6/8 folds on all 3 tickers" passes on
Jan-1 folds and FAILS on mid-year folds (IWM 5/8).

**Corrected verdict:** the underlying SIZE edge is real and robust — *every
ticker has a positive median log-loss beat under BOTH cutoff schemes* (+0.003 to
+0.017) with consistent good calibration (ECE ~0.04). But the strict
pre-registered gate is a **near-threshold, fold-sensitive pass, not a solid
one** — 1-2 early/hard folds per ticker dip negative. This supersedes the clean
"GATE PASS" framing above: SIZE is best described as **a real but modest,
calibrated edge that does not ROBUSTLY clear the strict 3-ticker gate.**

**Not productionized** on this basis. Options to firm it up: (a) lengthen the
minimum training window / add pre-2016 history so the early folds aren't
train-starved; (b) relax the gate to a median-beat criterion (which IS robust);
(c) deploy as a low-confidence modest edge with monitoring. Decision pending.


### CORRECTION (2026-07-11) — RETRACT the "fold-fragile" finding above (bad data provenance)

The shifted-cutoffs "fragility" entry above (IWM 8/8->5/8) is **retracted**. Root
cause: the `magnitude-recal --all-cells` confirmation runs (`jcv9r`, `psvhw`)
persisted only scattered cells to `magnitude_walk_forward_results` and GCS (mostly
30m QQQ; the needed 15m IWM/QQQ rows were never written). The DB "latest run_id"
queries used to read them therefore returned OLD `magnitude-engine` default-cutoff
runs, not the confirmation runs. So the shifted-cutoffs robustness was **never
actually measured** — neither confirmed nor refuted.

**What remains reliable** (config-tagged GCS written directly by
`phase2_ablation.run_config`, `direction-phase2-cmv2d`):
- SIZE @ 15m + isotonic + prune (default Jan-1 cutoffs): **IWM 8/8, SPY 7/8,
  QQQ 6/8 -> gate PASS**, ECE ~0.04. Bootstrap on the raw per-fold beats:
  IWM P(>=6/8)=1.00, SPY 0.94, QQQ 0.69 (QQQ the marginal leg).

**Standing verdict:** SIZE is a real, calibrated edge that PASSES the pre-registered
gate at 15m+isotonic+prune on the standard folds, with QQQ near-threshold.
**Cross-fold-placement robustness is UNCONFIRMED** — the confirmation must be
re-run through the reliable config-tagged GCS path (phase2_ablation with a
cutoffs parameter), NOT the mag --all-cells DB path which persisted unreliably.
Not productionized pending that clean robustness check.


### ROBUSTNESS CONFIRMED (2026-07-11, `direction-phase2-v5lxx`, reliable GCS path)

Re-ran the shifted-cutoffs confirmation through the config-tagged GCS path
(PHASE2_CUTOFFS env, phase2_ablation — NOT the flaky mag --all-cells DB path).
Result: **the gate pass HOLDS across fold placements.**

| fold scheme | prune config | verdict |
|---|---|---|
| Jan-1 (default) | IWM 8/8, SPY 7/8, QQQ 6/8 | 3/3 PASS |
| Shifted (mid-year) | IWM 7/8, SPY 8/8, QQQ 7/8 | 3/3 PASS |

Every ticker >=6/8 under BOTH schemes; median beat ~+0.012, ECE ~0.04. QQQ (the
Jan-1 marginal leg) went 6/8 -> 7/8 under shifted folds — MORE robust. This
supersedes and confirms the retraction: there is no fold-fragility; the earlier
"IWM 8/8->5/8" was purely the bad-data artifact (old magnitude-engine runs).

**FINAL SIZE VERDICT: predictable, calibrated (ECE ~0.04), and ROBUSTLY gate-
passing at 15m + isotonic + prune.** Deploy target confirmed. This is the pure-
prediction lens (log-loss); orthogonal to the 2026-05-29 gate-7 (cost) FAIL.


---

## 2026-09-14 — the promotion criteria measured one fact from two sides; nothing could satisfy both

**Question.** Which configuration belongs in production? The June runs
(`rmcwj`, `r7c4q`) passed gates 1-4 on several 5m cells; the serving
`c49qf` cells fail gate 4 at 0/8. Was calibration the lever, and is
anything actually promotable?

**Runs.** `hbb6v` (27 cells, phases 0+1+3, body, calibration none,
default class weight α=0.75, 2026-09-14 14:04 → 14:32 UTC), then a
class-weight sweep on phase1 (9 cells each): `54nrr` α=0.00, `tbkpt`
α=0.30, `gfsnt` α=0.45, `mj95j` α=0.60. Gate 6 via `direction-probe`
executions `wptxx` / `kdr97` / `72pfg`. Every LATEST pointer was captured
before dispatch and was byte-identical after: nothing promoted.

### 1. A persistence bug, found on the way

`magnitude_per_bar_predictions` held 16,666 rows, **all** `source='inference'`,
zero `source='walk_forward'`, `fold_label` NULL throughout. The CSV-harvest
loop in `walk_forward` popped `_predictions` off every fold dict *before*
`_persist_predictions_table` read them, so the SQL write received empty
folds and logged "no per-bar predictions to persist" on every run. The GCS
CSVs were complete because that writer reads the harvested list. Fixed in
`66a2daae` (pop moved after the SQL write, before the summary is
serialised; two ordering tests pin both ends). GCS was and is the complete
record.

### 2. `hbb6v`: 0 of 27, and the base rates prove it is not the market

Gate 1 was 0/8 on 25 of 27 cells (1/8 on the other two); median ECE 0.078
against a 0.05 ceiling. Same cell, same folds, June vs today:

| fold | rmcwj (June) logloss / base / beat | hbb6v (today) logloss / base / beat |
|---|---|---|
| 2019 | 0.9066 / 0.9154 / **+0.0089** | 1.1157 / 0.9154 / **−0.2003** |
| 2021 | 0.9210 / 0.9435 / +0.0225 | 1.0507 / 0.9435 / −0.1073 |
| 2025 | 0.8760 / 0.9007 / +0.0247 | 1.1080 / 0.9007 / −0.2074 |

`base_logloss` is identical on every historical fold, as are `n_train`
(55,788) and `n_test` (18,632). Same data, same labels; the model got
worse on fixed data. Cause: the June runs trained unweighted; the current
default is a tempered class weight at α=0.75 (`MAG_CLASS_WEIGHT_POWER`,
`mag_pred_train.resolve_class_weight`). Predicted vs true distribution:

```
                predicted TIGHT/NORMAL/EXPANDED/EXPLOSIVE   true
rmcwj  (α=0)    97.1 / 2.5 / 0.1 / 0.3                      63.6 / 26.9 / 6.9 / 2.6
hbb6v  (α=.75)  70.6 / 17.9 / 6.1 / 5.4                     64.2 / 26.4 / 6.8 / 2.6
```

rmcwj is argmax-collapsed: 97% TIGHT, never EXPANDED. It wins gate 1
because collapsing to the majority class is a strong log-loss play, wins
gate 2 because a confident majority predictor is calibrated on the
majority, and wins gate 4 because its dozen EXPLOSIVE calls per fold are
high-precision. The promotion verdict would refuse it at 97.1% modal share
and +33.5 pp excess. **So on 2026-09-14 the four walk-forward gates and
the promotion criteria pointed in opposite directions, and nothing
satisfied both.**

This also revises the calibration story: isotonic and α were confounded in
every earlier comparison (the isotonic runs 4jhx2/c49qf/w4gn7 all ran at
the later default; rmcwj/r7c4q unweighted). c49qf's α is **unrecoverable**:
the engine directory was squashed into this repo in `1e93ae97` on
2026-08-28, one day after c49qf ran, and no summary recorded the exponent.
Every summary now does (`class_weight_power`).

### 3. The α sweep: a strict monotone trade-off, no dial setting works

SPY 5m phase1, 8 folds:

| α | modal share | excess vs true modal | gate 1 folds | median beat |
|---|---|---|---|---|
| 0.00 | 97.3% | +33.2 pp | 8 | +0.0213 |
| 0.30 | 92.3% | +28.1 pp | 4 | −0.0019 |
| 0.45 | 89.3% | +25.1 pp | 2 | −0.0273 |
| 0.60 | 82.1% | +17.9 pp | 1 | −0.0689 |
| 0.75 | 70.6% | +6.4 pp | 0 | ≈ −0.13 |

Across all 36 sweep cells: **0 satisfy both** the gates and the
distribution criteria. Exactly one (SPY 15m, α=0.60, excess +9.1 pp)
clears the distribution checks; its gate 1 is 0/8. The α=0 control
reproduced rmcwj's collapse on today's data and features (97.0% / 97.3%
vs 97.1%), so class weighting alone explains the June-vs-today difference;
the two-feature swap between the runs was a red herring.

### 4. Prior correction: tested, and it lands in the collapsed corner

Dividing the α=0.60 probabilities by the training weights and
renormalising (the textbook fix) recovers log-loss and re-collapses argmax:

| SPY 5m fold | raw beat | corrected beat | raw modal | corrected modal | true modal |
|---|---|---|---|---|---|
| 2019 | −0.0932 | +0.0124 | 74.0% | 96.9% | 63.7% |
| 2022 | −0.1053 | +0.0088 | 70.3% | 97.1% | 62.5% |
| 2025 | −0.0782 | +0.0299 | 88.7% | 99.5% | 64.9% |

Positive corrected beat on 23 of 24 fold-cells (SPY/QQQ/IWM 5m); corrected
argmax at 94-99.8%. Robust to the weight proxy: sweeping the assumed
exponent from 0 to 1.0, beat is positive only between 0.3 and 0.75 and
modal share is 93.7%-99.1% across that whole range. No transform of the
probability vector satisfies both.

### 5. Why: the excess criterion's premise was false

`mag_config` said "a perfectly calibrated model predicts TIGHT on ~68.5%
of bars." Measured on the α=0 model (SPY 5m, 138,717 bars):

```
mean predicted p   0.634 / 0.264 / 0.073 / 0.029
true rate          0.642 / 0.264 / 0.068 / 0.026
argmax share TIGHT 97.3%
```

Calibrated to within a point on every class, and argmax TIGHT on 97% of
bars, because TIGHT genuinely is the most likely bucket on nearly every
bar. The criterion conflated *mean probability* with *argmax frequency*.
Gate 1 scores the probability vector; the collapse and excess criteria
scored the argmax; a calibrated model with weak tail signal fails the
second by construction, and the gap between them is a direct measurement
of the signal that is missing. slv7m (2026-09-07, withdrawn for gate 1 at
0/8, modal share 68-73%) was the high-α end of this same line; c49qf the
collapsed end. Neither incident was new; both were this.

### 6. What was serving

The `c49qf` artifacts, measured on their own walk-forward CSVs:

| cell | predicted TIGHT/NORMAL/EXPANDED/EXPLOSIVE | true |
|---|---|---|
| IWM 15m | **100.0** / 0.0 / 0.0 / 0.0 | 68.7 / 24.6 / 5.2 / 1.5 |
| SPY 5m | **100.0** / 0.0 / 0.0 / 0.0 | 64.0 / 26.5 / 6.8 / 2.6 |
| IWM 5m | 99.9 / 0.1 / 0.0 / 0.0 | 63.1 / 27.4 / 7.1 / 2.4 |
| QQQ 5m | 99.9 / 0.1 / 0.0 / 0.0 | 64.2 / 26.7 / 6.7 / 2.4 |

A constant. `audit-magnitude-drift` has flagged this HIGH every weekday
(2026-09-14 13:56: `argmax=TIGHT on 300/300 bars (100.0%)` on SPY 5m, and
the same on the other three). The detector worked; the argmax column it
was reading was the problem.

### 7. Gates 5 and 6 on the June passers (for the record)

Gate 5 (1,000-sample bootstrap over test bars, no retraining) on every
June cell passing gates 1-4: SPY 5m phase1 **100%** under both `r7c4q`
and `rmcwj`; QQQ 5m phase1/phase3 100%; IWM 5m phase1 100%; all other 5m
93.6-99.9%; **SPY 15m phase0 12.2%, phase3 7.4%**. SPY 15m cleared gates
1-4 deterministically and reproduces one time in ten. Gate 6
(event-window concentration, run in GCP via `direction-probe`): SPY 5m
0.23×, QQQ 5m 0.23×, IWM 5m 0.63× — not a calendar lookup. Both are
recorded because they were run, not because they rank anything: every
one of these cells is argmax-collapsed (§2), and under the amended gate 4
its counts will change.

### 8. The change: score the decision the consumer sees

`decide_bucket(proba, priors, lift_min)` names the highest bucket whose
probability is at least `lift_min` × its training-class prior, else TIGHT.
Operating curve on the calibrated α=0 model (and, for contrast, the
serving c49qf artifact):

| model | L | non-TIGHT calls | EXPLOSIVE calls | EXPLOSIVE precision | realised lift | folds lift ≥ 1.5 | modal share |
|---|---|---|---|---|---|---|---|
| 54nrr SPY 5m | 1.5 | 31.2% | 19.6% | 7.0% | 2.69× | 8/8 | 68.8% |
| 54nrr SPY 5m | **2.0** | 18.2% | 13.1% | 8.5% | 3.27× | 8/8 | 81.8% |
| 54nrr SPY 5m | 3.0 | 8.2% | 7.0% | 11.3% | 4.36× | 8/8 | 91.8% |
| c49qf SPY 5m | 2.0 | 36.5% | 11.5% | 5.4% | 2.07× | 7/8 | 63.5% |
| c49qf QQQ 5m | 2.0 | 2.4% | 0.5% | 10.6% | 4.46× | 4/8 | 97.6% |
| c49qf IWM 5m | 2.0 | 3.7% | 3.5% | 9.2% | 3.78× | 8/8 | 96.3% |

At L=2.0 a calibrated model makes tail calls on a real population, clears
gate 4's 1.5× in every fold with margin, and lands at 82% modal share; at
L=1.5 its modal share lands *at the true TIGHT share*, which is the
property the excess criterion wanted and misattributed to argmax. What
shipped, with the evidence above in the code comments:

- `DECISION_LIFT_MIN = 2.0`. Recorded in `CONTRACT.json` as
  `decision_lift_min` with the cell's `class_priors`; `mag_inference`
  refuses an artifact lacking either and refuses one stamped under a
  different bar, so `pred_bucket` means one thing fleet-wide.
- `pred_bucket` (predictions table, `/api/magnitude`, the movement
  statement) is now this decision. Field names and the OpenAPI schema are
  unchanged; the meaning is not.
- Gate 4 and the per-bar CSV's `pred_bucket_idx` use the same rule, so
  gates 5 and 6 resample the calls the gate counted.
- `promotion_verdict(proba, priors)`: `PROMOTION_MIN_DISTINCT_CLASSES`,
  the 90% collapse ceiling, and a new `PROMOTION_MIN_TAIL_CALL_SHARE =
  0.10` (the ceiling's complement, so the label-free live detector reads
  the same line), all on the decision output. The relative excess
  criterion is removed. No labels needed; the verdict is exactly what the
  drift auditor and render backstop can check against live rows.
- `class_weight_power` is recorded in every run summary and every
  `PROMOTION_BLOCKED` marker.
- `scripts/backfill_model_contracts.py` upgrades a legacy contract in
  place with priors measured from the cell's own prediction CSV.
- `scripts/dispatch_magnitude_phase.sh --class-weight-power=`.
- `scripts/bootstrap_gate_fragility.py` and
  `scripts/naive_calendar_lookup_baseline.py` recompute gate 4 under the
  same rule (the fold's truth distribution stands in for the training
  prior in the bootstrap, the substitution it already made for base
  log-loss).

Gate 5 re-run under the amended gate 4, on the α=0 run (`54nrr`, SPY 5m
phase1, 138,717 bars, 200 resamples): deterministic **8 / 8 / 8 / 8**,
cell-level pass rate **100%**, gate 4 now scored on ~13% of bars instead
of ~12 per fold. By the measurements in this section that model also
clears the new distribution checks (81.8% modal, 18.2% tail calls), which
would make it promotable under the amended criteria. That has **not** been
exercised: `54nrr` ran under the old code and promoted nothing; a fresh
dispatch at `--class-weight-power=0.0` is how it gets tested for real.

### 9. Precisely what is and is not established

- Only phase1 was swept. The structural argument does not depend on the
  feature set, so phase0/phase3 are not expected to differ, but that is
  unmeasured.
- The honest product number at L=2.0 is an EXPLOSIVE call on ~13% of bars
  with 8-9% precision against a 2.6% base rate. That is the tail signal
  this feature set has. The three real options remain: gate on
  probabilities rather than argmax (done), rebalance the labels via
  `MAG_THRESHOLDS`, or find features that raise P(EXPLOSIVE) on the bars
  that are.
- The four constant-output cells are **still serving, now under the new
  rule**. 2026-09-15: contracts stamped with measured priors, research
  image rebuilt (`ad36961a`, digest `79940375…`), both jobs updated, and
  `magnitude-inference-pfr64` re-scored the latest session (bars of
  2026-09-14) with the decision rule. Live decision distribution:

  | cell | bars | tail calls | EXPLOSIVE calls | mean P(EXPLOSIVE) |
  |---|---|---|---|---|
  | IWM 15m | 23 | 0 (0.0%) | 0 | 0.010 |
  | IWM 5m | 75 | 35 (46.7%) | 35 | 0.055 |
  | QQQ 5m | 75 | 5 (6.7%) | 5 | 0.018 |
  | SPY 5m | 75 | 1 (1.3%) | 1 | 0.018 |

  Three of four sit under the 10% tail floor and would be blocked at
  promotion. IWM 5m is the opposite failure: isotonic compressed its
  P(EXPLOSIVE) into a band around 0.05, which is right at 2× its 0.024
  prior, so half the bars clear the bar and every tail call is EXPLOSIVE.
  Neither shape is a usable model; the walk-forward measurement (§6) and
  the live one agree. Withdrawal, or replacement by a promoted α=0 model,
  is the open product decision in `docs/product/15-OPEN-DECISIONS.md`.
- `magnitude_per_bar_predictions.computed_at` is the FIRST insert time
  for a bar: the upsert keys on `(ticker, tf, ts, model_version)` and a
  re-score does not advance it. Read decisions by `ts`, not `computed_at`.
- `audit-magnitude-drift` still runs on the base image (not rebuilt this
  round); its logic is unchanged and its `argmax=` wording lags the code.
- No gate count in any section above this one was computed under the
  amended gate 4. Re-running the walk-forward under the new rule is how
  the phase table gets re-established.

### 10. First runs on the deployed code (2026-09-15)

**`magnitude-engine-vpj2r`** — phase1, α=0 (`--class-weight-power=0.0`),
9 cells on the new engine (`79940375…`). Every summary records
`class_weight_power=0.0` and `decision_lift_min=2.0`. Gate 4 is now scored
on the decision-rule population: EXPLOSIVE calls per fold went from 3-43
(argmax, `54nrr`) to 78-2,076, realised lift 3.3-5.2× on every cell.

| cell | g1 g2 g3 g4 | gates 1-4 | gate 5 (1,000 resamples) | gate 6 event conc. (pred / realised) |
|---|---|---|---|---|
| IWM 5m | 8 8 8 8 | PASS | **100%** | 1.15× / 0.92× |
| QQQ 5m | 8 8 8 8 | PASS | **100%** | 0.99× / 0.94× |
| SPY 5m | 8 8 8 8 | PASS | **100%** | 0.90× / 0.83× |
| SPY 15m | 7 7 8 8 | PASS | **86.5%** | 0.58× / 0.78× |
| IWM 15m | 7 8 8 8 | PASS | 34.4% | 0.95× / 0.86× |
| SPY 30m | 6 6 8 7 | PASS | 4.8% | 0.45× / 0.69× |
| IWM 30m | 1 8 8 8 | fail (g1) | — | — |
| QQQ 15m | 5 7 8 8 | fail (g1) | — | — |
| QQQ 30m | 2 6 8 8 | fail (g1) | — | — |

Six of nine clear gates 1-4; **four survive gate 5** (the 5m cells at 100%,
SPY 15m at 86.5% against the 80% bar). IWM 15m and SPY 30m pass
deterministically on noise, the same shape gate 5 caught in June. Gate 6:
predicted-EXPLOSIVE concentration within ±4 h of a high-impact event is
0.45-1.15× the base rate on every cell, so none is a calendar lookup; the
2.0× mechanism bar (`SUCCESS_BAR_MECHANISM_RATIO_MIN`) was written for the
phase3 event-proximity features and makes no claim about phase1's vol
family, so it is reported, not applied. Executions: gate 6 via
`direction-probe` x645p / 4rncr / tn4nm / mwvrx / mj6nc / jmlzf.

At the served operating point these models name EXPLOSIVE on 10-12% of
5m bars, matching the curve in §8. **`vpj2r` could not promote**: the
production-artifact path runs for phase0 only, and this was phase1; no
`LATEST` moved and nothing was written under `production/`. The
promotion test proper is `magnitude-engine-6hp7l` (phase0, α=0), reported
below when it completes.

**`magnitude-engine-6hp7l`** — phase0, α=0, 9 cells on the new engine: the
promotion test proper. Every cell wrote its artifacts and a
`CONTRACT.json` with `class_priors_source: training_labels` and
`decision_lift_min: 2.0`.

| cell | g1 g2 g3 g4 | verdict | reason |
|---|---|---|---|
| SPY 5m | 8 8 8 8 | **PROMOTED** | — |
| QQQ 5m | 8 8 8 8 | **PROMOTED** | — |
| IWM 5m | 7 8 8 8 | **PROMOTED** | — |
| SPY 15m | 5 7 8 8 | blocked | g1 5/8 (modal 84.3%, tail 15.7%: distribution checks pass) |
| IWM 15m | 5 7 8 8 | blocked | g1 5/8 (modal 84.9%, tail 15.1%) |
| QQQ 15m | 5 6 8 8 | blocked | g1 5/8 (modal 84.4%, tail 15.6%) |
| SPY 30m | 5 7 8 7 | blocked | g1 5/8 (modal 81.2%, tail 18.8%) |
| QQQ 30m | 2 7 8 7 | blocked | g1 2/8 |
| IWM 30m | 1 8 8 8 | blocked | g1 1/8 |

Three `LATEST` pointers flipped from `c49qf` to `6hp7l` (SPY 5m, QQQ 5m,
IWM 5m). **Every block is on gate 1**, with the distribution checks passing
on all six: the new verdict is no longer failing calibrated models on
argmax, and log-loss is the discriminator, which is the design. The 15m
cells sit one fold under the bar under phase0 features (phase1's vol
family lifted SPY 15m to 7/8 in `vpj2r`, which could not promote).

Promoted cells, post-hoc: gate 5 **100% / 100% / 100%** (IWM / QQQ / SPY
5m, 1,000 resamples; g1 P(<6) = 0.0% on each); gate 6 predicted-EXPLOSIVE
concentration 1.20× / 1.05× / 0.90× (`direction-probe` 9w8sh / rxwvj /
bp6r2). `magnitude-inference-h4hk7` then served them (75 rows per cell).
Live decision distribution on the 2026-09-14 session:

| cell | model | tail calls | EXPLOSIVE | mean P(EXPLOSIVE) |
|---|---|---|---|---|
| IWM 5m | 6hp7l | 32.0% | 19 / 75 | 0.054 |
| QQQ 5m | 6hp7l | 10.7% | 8 / 75 | 0.018 |
| SPY 5m | 6hp7l | 2.7% | 0 / 75 | 0.007 |
| IWM 15m | c49qf (unchanged) | 0.0% | 0 / 23 | 0.010 |

**A detector consequence to decide on.** `audit-magnitude-drift-d9kkm`
flagged SPY 5m `6hp7l` **HIGH** (TIGHT on 73/75, 97.3%) and IWM/QQQ 5m
MEDIUM. SPY 5m's model averages 11-13% EXPLOSIVE calls across eight years
and reproduces at 100% bootstrap; on one calm session it legitimately
named almost none (mean P(EXPLOSIVE) 0.007 against a 0.026 prior). The
auditor evaluates any model version with ≥ `DRIFT_MIN_SAMPLE` = 50 rows in
its 7-day window, so a single 75-bar session is enough to page. Under
argmax that never mattered, because argmax share did not move with the
session. Under the decision rule it does, by design. The honest fix is
a minimum sample for the HIGH tier of at least one week of bars (≈ 375
at 5m), not a wider ceiling; it is a one-line default change in
`gcp/audit_magnitude_drift.py` plus its test, and it is **not** made
here because the auditor also runs on the base image, which this round
did not rebuild. Until then, expect a HIGH finding on any promoted 5m
cell after a calm session, and read the 7-day tail share rather than
the page. The `c49qf` rows remain in the window as their own
model-version groups and age out over the week.

**Rollback**, if wanted: write `magnitude-engine-c49qf` back to
`magnitude-models/production/{SPY,QQQ,IWM}/5m/LATEST` (their contracts
already carry priors); both jobs back to
`trading-system@sha256:7c3afb98…`.

### 11. First served session, predicted vs actual (2026-09-14 bars, read 2026-09-15)

Per-bar data: `docs/research/2026-09-15/magnitude_0914_predicted_vs_actual.csv`
(450 rows: both models × three tickers × the session). "Actual" is the
training label, `|next_close − next_open| / atr_20` on the next bar of the
same session, bucketed at 0.5 / 1.0 / 1.5, computed in SQL from
`strat_features_5m`; the last bar of the session has no next bar and is
excluded (74 scored bars per ticker).

Argmax would have named TIGHT on 74/74 bars for every model and ticker.
The decision rule, on the promoted `6hp7l` models:

| ticker | actual T/N/X/EXPL | tail calls | EXPLOSIVE calls | exact EXPLOSIVE hits | real EXPLOSIVE bars caught |
|---|---|---|---|---|---|
| QQQ | 66/6/0/2 | 8 | 8 | 2 (25% vs 2.7% base, lift 9.3×) | 2/2 |
| IWM | 45/17/10/2 | 24 | 19 | 2 (11%, lift 3.9×); 8/19 landed ≥ EXPANDED | 2/2 |
| SPY | 70/1/3/0 | 2 | 0 | none occurred; 1/2 EXPANDED calls hit | — |

IWM's EXPLOSIVE calls form one block, 12:00-13:55 ET, which is where the
session's large moves were (1.86 and 2.10 ATR at 12:40 / 12:50, P(EXPLOSIVE)
0.30 and 0.23 on exactly those bars). QQQ's two real EXPLOSIVE bars (11:45,
11:50: 1.83 and 2.43 ATR) were both called. SPY was calm and the calibrated
model said so. `c49qf` on the same bars: IWM 35 EXPLOSIVE calls for the same
2 hits (lift 2.1×, the compressed-band shape of §9), QQQ 5 calls / 1 hit,
SPY 1 call / 0 hits. One session and four real EXPLOSIVE events: consistent
with the walk-forward lift of 3-5×, not evidence beyond it.

**Detector change shipped (same day).** `audit-magnitude-drift`'s HIGH
tier now requires the share to hold across `MIN_SESSIONS_FOR_HIGH` (5)
distinct sessions; a share over the 90% ceiling on fewer is MEDIUM with
the reason in the finding. This is what SPY 5m's calm session needed. A
constant model is now MEDIUM for its first week and HIGH after; the render
backstop covers the card in the meantime. (As first shipped the rule was a
bar quota, sessions times RTH bars per timeframe, 390 at 5m; §12 records
why that number was unreachable and the correction.)

Deployed the same day (base image `a4d72306` → `24f89de6…`, auditor
generation 4). First run, `audit-magnitude-drift-x6hgq`: no HIGH findings;
SPY 5m `6hp7l` MEDIUM with the reason in the finding; IWM 15m (`c49qf`,
still a constant, 115 bars) crosses its 130-bar minimum on the next
session and pages HIGH then, as it should.

### 12. Review round on #1117 (2026-09-16): five findings, one latent write failure

Codex reviewed the decision-rule PR at `153218c7` and filed five findings.
Every one held against the code; working them surfaced a sixth defect that
predates the PR. Each item names the fix and the test that pins it.

**The auditor's HIGH tier could never fire.** The 2026-09-15 rule required
`MIN_SESSIONS_FOR_HIGH × bars-per-session` bars (390 at 5m, 130 at 15m,
65 at 30m). Inference drops the three warmup bars of every session
(`_load_recent_features`, `prev3_candle` NaN), so a session contributes
75/23/10 bars and a 7-day window tops out at 375/115/50: the quota was a
claim about the calendar the data did not meet. `fetch_distribution` now
counts distinct ET sessions per cell (`n_sessions`, named zone per §3.9)
and `check_modal_dominance` gates HIGH on that count. Measured against the
live table the same morning, the query returns five sessions for every
`c49qf` cell and one for the `6hp7l` cells. Two consequences: a holiday
week (four sessions) defers HIGH to the following week, and the check
now judges only the model version each cell is SERVING (newest inference
write), because the replaced `c49qf` rows sat in the window at 340/375 =
90.7% on IWM 5m and would have paged HIGH on a model that no longer
serves. `tests/audits/test_audit_magnitude_drift.py`.

**Gate 5 moved its own threshold.** `bootstrap_gate_fragility.fold_gates`
recomputed the substitute prior from each resample, so gate 4 was scored
under a different lift bar on every draw. `fold_prior` is now computed
once per original fold and passed into every resample and the
deterministic pass. The 2026-09-15 gate-5 numbers (100% on the 5m cells,
86.5 / 34.4 / 4.8% on SPY 15m / IWM 15m / SPY 30m) were produced under
the moving rule and are not re-run here; the 5m promotions rest on gates
1-4 and 6 as well and are unchanged. `tests/gcp/test_magnitude_gates.py`
(`TestAnalysisScriptsUseTheDecisionRule`).

**Walk-forward rows would beat the served model on the live reads, and
never had, because the write always failed.** `_persist_predictions_table`
writes every phase0 fold's test predictions, promoted or blocked, into
`magnitude_per_bar_predictions` with `ts` up to the newest labelled bar.
`/api/magnitude/{ticker}/{tf}/latest`, `/at/{ts}` and
`_build_expected_move` ordered by `ts`/`computed_at` with no `source`
filter, so the first successful walk-forward write would have served a
blocked candidate's call. It never happened because the write has failed
on every run since it was added: the fold rows carry `ts` as
`str(datetime64)`, bound as VARCHAR, and Postgres refuses it into
TIMESTAMPTZ (SQLSTATE 42804, logged nine times by `6hp7l`). The table
holds zero `walk_forward` rows. Both are fixed: the three live reads take
`source = 'inference'` only (the degeneracy backstop already did), and the
writer parses `ts` to tz-aware UTC before binding.
`tests/api/test_magnitude_router.py`, `tests/lib/test_movement_statement.py`,
`tests/gcp/test_magnitude_predictions_persistence.py`.

**`max_proba` beside a tail `pred_bucket` read as its confidence.** It is
the argmax bucket's probability, TIGHT's on nearly every bar. The API and
the expected-move block now carry `pred_bucket_proba`, the served bucket's
own probability (EXPLOSIVE at 0.08 against a 0.026 prior is a call;
`max_proba` on that row is 0.62). `max_proba` stays as the drift metric the
auditor averages. OpenAPI snapshot regenerated; solyra's vendored copy,
`MovementExpectedMove` type and dashboard mock updated on the same branch.

**The stamped priors omitted every pre-2019 training row.** The 2026-09-15
backfill measured `class_priors` from the walk-forward prediction CSV,
which holds only the held-out test bars from 2019 on: for IWM 15m that is
16,575 of 58,932 labels missing. The population the decision rule scales
by is the full training label set, and the walk-forward records exactly
that in every `CONTRACT.json` it writes, promoted or blocked
(`class_priors_source: "training_labels"`), so `6hp7l` had already
measured it for all nine cells on 2026-09-15. The backfill now takes the
newest sibling artifact's training-label priors under the same label
contract and records which run they came from (`class_priors_from_run`);
a cell with none is refused. The reader (`contract_mismatch`) refuses any
`class_priors_source` other than `training_labels`. Re-stamped with
`--commit` the same morning, three cells (the ones still on `c49qf`):

| cell | test-label priors (2026-09-15) | training-label priors (from `6hp7l`) |
|---|---|---|
| IWM 15m | 0.6868 / 0.2456 / 0.0523 / 0.0152 | 0.6780 / 0.2495 / 0.0556 / 0.0169 |
| QQQ 30m | 0.7207 / 0.2176 / 0.0456 / 0.0160 | 0.7179 / 0.2208 / 0.0456 / 0.0157 |
| IWM 30m | 0.7223 / 0.2201 / 0.0451 / 0.0125 | 0.7164 / 0.2241 / 0.0465 / 0.0130 |

The EXPLOSIVE threshold on IWM 15m moves from 0.0305 to 0.0338. The
`6hp7l` measurement is taken 19 days after `c49qf`'s training set closed
(264 more rows out of 58,932), which the contract discloses by naming the
run. The pre-restamp payloads are kept in the session scratchpad. All six
serving artifacts verify under the new reader.
`tests/gcp/test_magnitude_inference.py`.

**Second pass (Codex on `7cfad58a`, one P2).** `_model_degeneracy` in
`lib/movement_statement.py`, the render backstop, applied the 90% ceiling
with no session minimum, so the same calm SPY 5m session the auditor now
declines to page on (73/75 TIGHT) would have withheld the Expected-Move
block as "decision-collapsed" for days after a promotion. Its aggregate
is now grouped by ET session as well as bucket; a share over the ceiling
on fewer than five sessions renders, with `insufficient_sessions`,
`n_sessions` and `min_sessions` in the payload saying why it was not
withheld. The literal is asserted equal to the auditor's
`MIN_SESSIONS_FOR_HIGH` in the tests, the same discipline as the shared
90% ceiling. `tests/lib/test_movement_statement.py`
(`test_one_calm_session_is_insufficient_evidence_not_collapse`).

**Deployed the same morning.** Research image `sha256:a0366260…`
(`magnitude-engine` gen 178, `magnitude-inference` gen 13), base image
`sha256:3eecbe92…` (`audit-magnitude-drift` gen 5). Verification runs:
`magnitude-inference-l9cz5` verified all four serving contracts, IWM 15m
under the re-stamped priors, and wrote the 2026-09-15 session at 75 bars
per 5m cell and 23 for IWM 15m, the post-warmup counts the session rule
was built on. `audit-magnitude-drift-t5p82`, the first run under the
session rule: HIGH on IWM 15m `c49qf` (TIGHT on 138/138 bars over six
sessions, the constant model that the bar quota could never have paged
and that open decision (a) is about), SPY 5m `6hp7l` MEDIUM at 146/150
with "only 2 sessions" in the reason, IWM and QQQ 5m MEDIUM at 81-83%.
The retired `c49qf` 5m rows still in the window were not judged.
