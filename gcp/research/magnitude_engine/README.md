# Magnitude Engine

Research-only model that predicts the **magnitude bucket** of the next
bar's `|close - open|` move in ATR-20 multiples. Companion to (not
replacement for) `strat_engine` — that one predicts SHAPE, this one
predicts DISTANCE.

> **No production hooks**, no schedulers, no live integration. Walk-
> forward research only until the verdict in
> [`docs/MAGNITUDE_ENGINE_RESULTS.md`](../../../docs/MAGNITUDE_ENGINE_RESULTS.md)
> is PASS or FAIL.

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
│                                success bar
└── mag_leakage_audit.py         3 audits: feature drop set, atr_20
                                 t-known, phase-1 no-future-look
```

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
4. EXPLOSIVE-bucket lift over base ≥ 1.5 in ≥ 6/8 folds

Per-phase: cell-passes in ≥ 2 of 3 tickers on ≥ 2 of 3 timeframes.

## What is NOT here

- Production prediction job (strat_pred output table).
  Magnitude engine writes ONLY to `magnitude_walk_forward_results` and
  GCS run reports.
- An orchestrator that chains multiple phases. Each phase is dispatched
  independently and its result feeds the verdict-update step manually.
- Phase 5 (options-derived gamma exposure). Conditional on Phases 0–4.
