# Strat Directionality Engine — PRD

**Status:** TYPE model finalized & ON THE SHELF (callable, not activated).
DIRECTION target tested and REJECTED. Scope validated for **IWM only**.
**Last verified:** 2026-06-04 against the saved walk-forward artifacts in
`gs://adept-mountain-474619-d4-trading-data/research/strat_engine/iwm_{tf}/`.

**Companion docs:** [`README.md`](README.md) (engineering reference),
[`../../../docs/STRAT_ENGINE_OPERATIONS.md`](../../../docs/STRAT_ENGINE_OPERATIONS.md)
(operations manual), [`../../../docs/DIRECTION_FEATURES_R&D.md`](../../../docs/DIRECTION_FEATURES_R&D.md)
(the direction-features FAIL writeup).

> This document was reconstructed 2026-06-04. The original
> `STRAT_DIRECTIONALITY_ENGINE_PRD.md` referenced by `README.md` was never
> committed; the success bars survived only as constants in
> `strat_config.py` and gate logic in `strat_pred_train.py`. This PRD makes
> those bars, the two models, and their verified verdicts auditable in one
> place.

---

## 0. One-paragraph intent

For a given ticker, at the close of each bar, output a probability
distribution over what the **next bar** looks like — and do it well enough
that the probabilities are *trustworthy* (calibrated), not just
rank-ordered. "Movement prediction only — **no money in v1**." The engine
predicts market *structure*, never a P&L edge and never (validated) a
buy/sell direction.

---

## 1. Two models, one spine

The engine trains **two different targets** on an otherwise identical
pipeline. They share the data loader, the feature matrix, the LightGBM
hyperparameters, the regime-spanning walk-forward cutoffs, and the ECE
metric. They differ **only** in the target and the final estimator's
objective.

| Shared component | Source | Notes |
|---|---|---|
| Label loader | `strat_dataset.py:load_labeled_dataset` | `strat_features_{tf} LEFT JOIN strat_features_levels_{tf}`, session-aware `prev1/2/3` lags, t+1 label. The ONLY place the label is computed. |
| Feature matrix | `strat_pred_train.py:featurize` | one-hot categoricals; drop identity/OHLCV/forward-looking cols; `fillna(0)` → ~143 float cols |
| Estimator | LightGBM | `n_estimators=300, lr=0.05, max_depth=6, num_leaves=31, min_child_samples=100, random_state=42` |
| Walk-forward | `strat_walk_forward.py:DEFAULT_CUTOFFS` | 8 anchored expanding folds 2019→2026, spanning recovery / COVID / bull / bear / recovery / bull / current / locked-OOS |
| ECE | `strat_pred_train.py:expected_calibration_error` | max-confidence binned, 10 bins, ceiling 0.05 |

**Leakage guardrail (both models):** label is strictly `t+1`; features known
at bar-`t` close; the last bar of each session is dropped; `next_*` OHLC
columns are hard-excluded from the feature matrix
(`strat_pred_train.py` drop-set). Leak audit completed 2026-05-26.

---

## 2. Model A — TYPE (structure)  ✅ VALIDATED

| Dimension | Specification |
|---|---|
| **Goal** | Predict the *shape* of the next candle |
| **Target** | `next_bar_type` ∈ {`1`, `2U`, `2D`, `3`} — the Strat candle class of bar t+1 |
| **Objective** | 4-class `LGBMClassifier(objective="multiclass", num_class=4)` |
| **Purpose** | Read whether the next bar is an inside bar (1), directional continuation (2U/2D), or outside/expansion bar (3) — a structure / volatility-regime signal. NOT a directional or P&L claim. |
| **Calibration** | `none` — raw native softmax. The sigmoid-Platt wrapper was tested across 24 folds and HURT ECE in every one (raw 0.013–0.049 median by cell; sigmoid 0.042–0.125), so the shipped model carries no calibrator. LightGBM multiclass already minimizes cross-entropy, which *is* a calibration loss; Platt on top is double-calibration. |
| **Served by** | `strat_pred_serve.py:predict_one` → `POST /api/admin/strat-engine/predict`. Frozen. No schedulers. |
| **Scope statement (shipped verbatim)** | "Calibrated structure prediction. Not a directional or P&L edge. Use with discretion." |

### Success bars (the gate)

From `strat_config.py` + `strat_pred_train.py:run_train`:

- **HARD** — model log-loss < base-rate log-loss (primary; accuracy is gameable)
- **HARD** — ECE ≤ `DEFAULT_ECE_CEILING` = 0.05
- **ADVISORY** — accuracy beats base rate by ≥ `DEFAULT_BASE_RATE_BEAT_PP` = 5pp

A cell may ship on the two HARD gates even if the advisory misses (a
calibrated, informative model on a noisier cell can beat base-rate log-loss
without +5pp accuracy — killing it on accuracy would be a false negative).

### Verified evidence (IWM 15m, `walk_forward_adaptive_none`, computed 2026-05-27)

| fold | log-loss beat | accuracy beat | ECE |
|---|---:|---:|---:|
| 2019 | +0.158 | +17.4pp | 0.018 |
| 2020 (COVID) | +0.162 | +17.3pp | 0.021 |
| 2021 | +0.169 | +17.2pp | 0.019 |
| 2022 (bear) | +0.206 | +21.1pp | 0.021 |
| 2023 | +0.201 | +18.7pp | 0.021 |
| 2024 | +0.188 | +18.8pp | 0.016 |
| 2025 | +0.170 | +16.8pp | 0.033 |
| 2026 (OOS) | +0.191 | +17.9pp | 0.030 |
| **summary** | **8/8 positive, median +0.179** | **median +17.7pp** | **8/8 ≤ 0.05, median 0.021** |

**Verdict: PASS.** Regime-stable across COVID, the 2022 bear, and the locked
2026 OOS. This is the finalized deliverable.

### Cross-ticker generalization (SPY, QQQ — verified 2026-06-04)

SPY and QQQ were built (levels backfilled to match IWM's 143-col surface) and
run through the **same** adaptive `mode=none` walk-forward. They replicate
IWM almost exactly — the structure edge is not IWM-specific.

| cell | log-loss beat>0 | beat median | acc median | ECE ≤ 0.05 | verdict |
|---|---:|---:|---:|---:|---|
| IWM 5m  | 8/8 | +0.193 | +19.0pp | 8/8 | PASS |
| SPY 5m  | 8/8 | +0.204 | +18.1pp | 8/8 | PASS |
| QQQ 5m  | 8/8 | +0.206 | +18.3pp | 8/8 | PASS |
| IWM 15m | 8/8 | +0.179 | +17.7pp | 8/8 | PASS |
| SPY 15m | 8/8 | +0.194 | +17.6pp | 8/8 | PASS |
| QQQ 15m | 8/8 | +0.197 | +17.6pp | 8/8 | PASS |
| IWM 30m | 8/8 | +0.160 | +15.4pp | 4/8 | PARTIAL |
| SPY 30m | 8/8 | +0.155 | +15.6pp | 5/8 | PARTIAL |
| QQQ 30m | 8/8 | +0.160 | +16.3pp | 5/8 | PARTIAL |

**Reading:** 5m and 15m are clean PASS on all three tickers (log-loss beat
*and* calibration). 30m is uniformly PARTIAL — every ticker beats base
log-loss 8/8 but only ~half the folds hold ECE ≤ 0.05 (median ECE ~0.04–0.05,
right at the ceiling). That is a **property of the 30m cell, not the ticker**:
the coarser grid has fewer bars per fold, so the native softmax is mildly
over-confident out-of-regime. SPY/QQQ track IWM cell-for-cell.

---

## 3. Model B — DIRECTION (`strat_dir_walk_forward`)  ❌ REJECTED

| Dimension | Specification |
|---|---|
| **Goal** | Predict which way the next bar's body closes |
| **Target** | binary `next_close > next_open` (flat bars dropped as ambiguous) |
| **Objective** | binary `LGBMClassifier(objective="binary")` — same hyperparams as TYPE |
| **Purpose** | The ONLY leg that could justify a **call-vs-put** decision. This is the question "does the engine predict direction well enough to trade calls vs puts?" |
| **Features** | Identical 143-col matrix to TYPE — the experiment is whether the structure-predicting feature surface also carries directional edge |
| **Calibration** | none (binary softmax) |
| **Served by** | nothing — reference-only, FAIL-tagged |

### Success bar (per `DIRECTION_FEATURES_R&D.md`)

A cell PASSES only if all three hold: log-loss beat > 0 on ≥ 6 of 8 folds,
AND ECE ≤ 0.05 on those folds, AND median decisive-call hit-rate rises
monotonically across confidence thresholds [0.50, 0.55, 0.60].

### Verified evidence (IWM 5m/15m/30m baseline, computed 2026-05-27)

| cell | folds w/ positive log-loss beat | decisive-call hit-rate @ ≥0.70 conf |
|---|---:|---:|
| 5m | 0/8 | ~0.50 |
| 15m | 0/8 | ~0.49 |
| 30m | 0/8 | ~0.53 |
| **total** | **0/24** | **median ≈ 0.50 (coin flip)** |

Three additional orthogonal feature families were tested (news_sentiment,
cross_asset, vol_regime) — **0/8 each**; a fourth (options_derived) was
INFEASIBLE at production-data scale. See `DIRECTION_FEATURES_R&D.md`.

**Verdict: FAIL.** Direction is not learnable from this feature surface in
any tested regime. Confidence does not discriminate direction even when the
model is over-confident. **The engine cannot drive a call-vs-put decision
today.**

### Cross-ticker confirmation (SPY, QQQ — verified 2026-06-04)

The DIRECTION FAIL is also not IWM-specific. All three tickers × 5m/15m/30m =
9 cells, **0/8 positive log-loss beat in every cell**, decisive-call hit-rate
at ≥0.70 confidence stuck at a coin flip:

| cell | log-loss beat>0 | beat median | hit-rate @ ≥0.70 conf |
|---|---:|---:|---:|
| IWM 5m/15m/30m | 0/8, 0/8, 0/8 | −0.006 / −0.015 / −0.021 | 0.50 / 0.49 / 0.53 |
| SPY 5m/15m/30m | 0/8, 0/8, 0/8 | −0.007 / −0.010 / −0.020 | 0.56 / 0.52 / 0.55 |
| QQQ 5m/15m/30m | 0/8, 0/8, 0/8 | −0.005 / −0.009 / −0.017 | 0.52 / 0.50 / 0.55 |

Direction fails identically across all three liquid index ETFs. This is an
information-content failure of the feature surface, not a per-ticker quirk.

To revive this leg the bar is *new evidence*: a new feature surface
(microstructure / order-flow tick data), a new label, or a new dataset —
not a re-run of the same features.

---

## 4. The 6-point validation contract

A cell is "adequate and correct" only when all six hold. This is the
checklist any re-verification (or new ticker) must pass.

| # | Requirement | How it's checked | TYPE | DIRECTION |
|---|---|---|---|---|
| 1 | **Leak-free** | label t+1, no `next_*`/same-day-VIX features, session-aware shifts; leak audit | ✅ | ✅ |
| 2 | **Beats base log-loss** (HARD) | walk-forward `beat > 0` every fold | ✅ 8/8 | ❌ 0/24 |
| 3 | **Calibrated, ECE ≤ 0.05** (HARD) | walk-forward `ece ≤ 0.05` every fold | ✅ 8/8 | ❌ |
| 4 | **Regime-stable** | beat holds across all 8 regime folds, not just OOS | ✅ | ❌ |
| 5 | **Confidence discriminates** | decisive hit-rate rises with confidence | ✅ | ❌ flat at 0.50 |
| 6 | **Reproducible via production replay** | `strat_walk_forward.py` (TYPE) / `strat_dir_walk_forward.py` (DIRECTION), no throwaway harness | ✅ (after the 2026-06-04 harness fix) | ✅ |

### How to reproduce (production replay paths — CLAUDE.md Rule 3.6)

```bash
# TYPE walk-forward (production config = raw softmax, no calibration)
gcloud run jobs execute strat-engine --region=us-east1 \
  --args="-m,gcp.research.strat_engine.strat_walk_forward,--ticker=IWM,--tf=15m,--calibration=none" --wait

# TYPE calibration diagnostic (reproduces the sigmoid-hurts finding)
gcloud run jobs execute strat-engine --region=us-east1 \
  --args="-m,gcp.research.strat_engine.strat_walk_forward,--ticker=IWM,--tf=15m,--calibration=sigmoid" --wait

# DIRECTION walk-forward (the 0/24 FAIL)
gcloud run jobs execute strat-engine --region=us-east1 \
  --args="-m,gcp.research.strat_engine.strat_dir_walk_forward,--ticker=IWM,--tf=15m" --wait
```

Artifacts land at
`gs://${BUCKET}/research/strat_engine/iwm_{tf}/walk_forward_{calibration}_{epoch}.json`
(TYPE) and `.../dir_walk_forward_{epoch}.json` (DIRECTION).

---

## 5. Known scope limits (what is NOT yet validated)

These do not change the verdicts above but bound where they apply:

1. **All 3 tickers now built & validated (2026-06-04).** IWM, SPY, and QQQ ×
   5m/15m/30m all have walk-forward evidence and a trained `model.pkl`. The
   `calibration="none"` decision, originally scoped "IWM only; re-verify
   per-ticker" (`strat_config.py`), is now **confirmed cross-ticker**: raw
   softmax holds ECE ≤ 0.05 on 5m/15m for SPY and QQQ exactly as for IWM
   (and 30m is borderline for all three — a cell property). The 1m/60m/4h
   cells remain out of scope per the locked FTFC config.
2. **Live-ECE self-mute is a no-op.** The writer that populates
   `structure_brief_latest.json` is not implemented, so `live_ece` is always
   `null` and the ECE-breach mute never fires (`strat_pred_serve.py`). The
   model degrades to "available, no calibration-health reading."
3. **Provenance.** There is no top-level `metrics.json`; only
   `metrics_<epoch>.json` sidecars. `predict_one` picks the metrics file by
   mtime-proximity to the served `model.pkl`, which can surface a diagnostic
   *variant* run's metadata. Treat `model_version` as best-effort.

---

## 6. Activation gate (NON-NEGOTIABLE)

Activating any production trigger (scheduler, user-facing route, live-brief
integration, autonomous trading) requires ALL of:

1. A documented use case naming the consumer, accepting only the validated
   quantity (structure) and never claiming the unvalidated ones (direction,
   P&L).
2. A fresh walk-forward against the success bars in §2 for the exact
   (model, ticker, cell) being activated — bars are not relaxed.
3. Explicit deploy approval from the project owner, recorded in the PR.

Until all three are present, the engine stays callable but quiescent.
