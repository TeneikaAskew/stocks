# Magnitude Engine

**Last reviewed:** unknown · **Last scanned:** 2026-09-18 · **Owner:** TBD

Research-only model that predicts the **magnitude bucket** of the next
bar's `|close - open|` move in ATR-20 multiples. Companion to (not
replacement for) `strat_engine` — that one predicts SHAPE, this one
predicts DISTANCE.

> **This note is stale and kept for history.** The engine has served
> production since 2026-08: `magnitude-inference-daily` (09:25 ET,
> weekdays) scores the promoted artifact per cell into
> `magnitude_per_bar_predictions`, `/api/magnitude` and the movement
> statement read it, and `audit-magnitude-drift-daily` (09:55 ET) watches
> it. The research verdict in
> [`docs/MAGNITUDE_ENGINE_RESULTS.md`](../../../docs/MAGNITUDE_ENGINE_RESULTS.md)
> is FAIL by gate 7 (2026-05-29); what is served is the pure-prediction
> probability surface, with the caveats in that doc's 2026-09-14 section.

## File map

```
gcp/research/magnitude_engine/
├── README.md                    this file
├── __init__.py
├── mag_config.py                tickers, TFs, label buckets, ATR
│                                thresholds, PHASE_FEATURES, the
│                                PRE-SET success bar (immutable)
├── mag_dataset.py               wraps strat_engine loader, computes
│                                magnitude target, attaches phase-
│                                specific features
├── mag_pred_train.py            featurize + LightGBM + ECE +
│                                decisive-call hit rate + EXPLOSIVE lift
├── mag_walk_forward.py          8-fold anchored walk-forward, per-cell
│                                + per-phase verdict against the
│                                success bar; promotion verdict and the
│                                production artifact + CONTRACT.json
├── mag_inference.py             daily scorer: loads LATEST per cell,
│                                verifies CONTRACT.json, applies the
│                                decision rule, upserts predictions
└── mag_leakage_audit.py         3 audits: feature drop set, atr_20
                                 t-known, phase-1 no-future-look
```

## The served decision (2026-09-14)

`pred_bucket` is **not argmax**. `mag_pred_train.decide_bucket` names the
highest bucket whose probability is at least `DECISION_LIFT_MIN` (2.0) ×
its training-class prior, else TIGHT. The priors and the bar are recorded
in each artifact's `CONTRACT.json` and verified at serve time. On a
64%-TIGHT label set the argmax of a calibrated model is TIGHT on ~97% of
bars; the serving c49qf artifacts were at 99.9-100%. Gate 4, the promotion
verdict, the per-bar CSV and inference all use the same rule, so what the
gate measures is what the consumer sees. Evidence and operating curve:
`mag_config.py` (comment on `DECISION_LIFT_MIN`) and the results doc.

Class weighting (`MAG_CLASS_WEIGHT_POWER`, default 0.75) is the
hyperparameter the promotion trade-off turns on; it is recorded in every
run summary as `class_weight_power`, and
`scripts/dispatch_magnitude_phase.sh --class-weight-power=` dispatches it.

## Cloud Run Job

Hosted in the same image as `strat-engine` (lightgbm + sklearn). Deploy
target is `magnitude-engine` — see `gcp/deploy.sh::deploy_magnitude_engine`.

```bash
# Phase 0 — all 9 cells (3 tickers × 3 TFs)
gcloud run jobs execute magnitude-engine --region=us-east1 \
  --args="-m,gcp.research.magnitude_engine.mag_walk_forward,--phase=phase0,--all-cells" \
  --async

# One cell
gcloud run jobs execute magnitude-engine --region=us-east1 \
  --args="-m,gcp.research.magnitude_engine.mag_walk_forward,--phase=phase0,--ticker=IWM,--tf=15m"

# Leakage audit
gcloud run jobs execute magnitude-engine --region=us-east1 \
  --args="-m,gcp.research.magnitude_engine.mag_leakage_audit,--ticker=IWM,--tf=15m"
```

## Target

`magnitude_bucket` = bisect of `|next_close - next_open| / atr_20`:

| bucket    | range          |
|-----------|----------------|
| TIGHT     | < 0.5 × ATR-20 |
| NORMAL    | 0.5–1.0 × ATR-20 |
| EXPANDED  | 1.0–1.5 × ATR-20 |
| EXPLOSIVE | ≥ 1.5 × ATR-20 |

## Phases

| phase  | features added                                | tables required                | runnable today |
|--------|------------------------------------------------|--------------------------------|----------------|
| phase0 | (baseline 143-col enrichment as-is)           | existing                       | ✅             |
| phase1 | atr5/atr20 ratio, BB20 bw, RV-z15, range-exp ratio, intraday-range vs prior-day | existing | ✅             |
| phase2 | AV ADX, MFI, ADOSC, AROON, ROC, BBANDS bw    | `market_data_indicators` (PR) | ❌ needs backfill |
| phase3 | hrs-until / hrs-since high-impact event, event-day flag | `economic_events`     | ✅             |
| phase4 | VIX delta/z, UST10Y/DXY deltas, oil/gold z   | `market_data_cross_asset` (PR) | ❌ needs backfill |
| phase5 | gamma exposure features (deferred)            | `etf_options_snapshots`        | ⏭ deferred    |

Phase 2 + 4 need their fetcher backfills run first (see
`gcp/fetchers/fetch_av_indicators.py` + `fetch_cross_asset.py`). Until
those land, those phases will report `PENDING_BACKFILL` in the results
doc instead of a passing/failing verdict.

## Success bar (PRE-SET, IMMUTABLE)

Documented in `mag_config.py` AND `docs/MAGNITUDE_ENGINE_RESULTS.md`.
Per the spec's hard guardrail: "Document the success bar in the PR
description BEFORE running the experiments." Re-read both before
proposing any tweak to the gate.

Per-cell:
1. log-loss beat positive in ≥ 6/8 folds
2. ECE within ceiling (0.05 for 5m + 15m; 0.075 for 30m) in ≥ 6/8 folds
3. decisive-call hit rate rises monotonically across thresholds 0.40 → 0.70 in ≥ 6/8 folds
4. EXPLOSIVE-bucket lift over base ≥ 1.5 in ≥ 6/8 folds — since
   2026-09-14 measured on the bars the decision rule names EXPLOSIVE,
   not argmax (metric and threshold unchanged; see the results doc §0
   amendment)

Per-phase: cell-passes in ≥ 2 of 3 tickers on ≥ 2 of 3 timeframes.

## What is NOT here

- ~~Production prediction job.~~ Stale: `mag_inference.py` is the
  production job (see the file map). The walk-forward writes
  `magnitude_walk_forward_results`, `magnitude_per_bar_predictions`
  (`source='walk_forward'`, phase0 only) and the GCS run reports.
- An orchestrator that chains multiple phases. Each phase is dispatched
  independently and its result feeds the verdict-update step manually.
- Phase 5 (options-derived gamma exposure). Conditional on Phases 0–4.
