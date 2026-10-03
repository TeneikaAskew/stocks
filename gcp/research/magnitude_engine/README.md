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
├── evaluation_windows.py        immutable America/New_York development,
│                                validation and one-time final-test periods
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
├── mag_leakage_audit.py         3 audits: feature drop set, atr_20
│                                t-known, phase-1 no-future-look
├── binary_config.py             immutable binary utility/artifact contract
└── binary_research.py           isolated EXPLOSIVE-vs-rest benchmarks
```

## Binary rare-event research

`binary_research.py` is a separate, research-only experiment. It compares
unweighted and capped-weight LightGBM, focal-equivalent rare-event weighting,
calibrated logistic regression, and a train base-rate baseline. Per-ticker
chronological validation selects and locks each operating threshold using the
pre-declared `+5 TP / -1 FP` utility (optionally subject to minimum precision).
The untouched test partition reports PR AUC (primary), ROC AUC, log loss, Brier
score, calibration/ECE, precision, recall, false alerts per session, and
expected net utility.

Artifacts are confined to
`magnitude-binary-research/v1/<TICKER>/<TIMEFRAME>/report.json`, never the four-class
production path. There is no fleet threshold or implicit pooled model. A future
pooled experiment must independently beat the ticker-specific validation PR
AUC for every ticker before it can be selected.

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

## Evaluation isolation

Every run selects `--evaluation-window development`, `validation`, or
`final_test`. Boundaries and the criteria/final-test versions live in
`evaluation_windows.py` and are half-open Eastern-session ranges. Walk-forward
folds keep an entire trading session together and purge one observed session
(the prediction horizon) before evaluation. The final-test marker is created
atomically in GCS; reusing the same final-test version for the same cell is
rejected rather than silently re-reading the holdout, and the claim is
refused while the window is still open on the market date, so a partial
year can never consume the one-time version. The claim is taken after an
unlabelled preflight and before the labelled load, so a rerun after the
marker exists, or the loser of a concurrent claim, never constructs a
final-test label. The preflight compares the WHOLE window against the NYSE
schedule (`evaluation_windows.expected_session_bars`): every session
present, each holding at least its regular-hours bar count for the
timeframe (an early close expects fewer), no rows on a non-session date.
The marker is one per (version, ticker, timeframe), not per phase, and
only the serving phase (`phase0`) under the frozen serving configuration
may take it: the serving label contract, the baseline feature set,
`DEFAULT_CALIBRATION` / `DEFAULT_CV`, and no `MAG_CLASS_WEIGHT_POWER` or
`MAG_SEED` override (`mag_walk_forward.final_test_config_refusal`).
`dispatch_magnitude_phase.sh` refuses `--evaluation-window=final_test` for
any plan but `phase0`.

The claim is a state machine. It is written as `claimed`; once the run's
summary is durable it moves to `evaluated` and the cell can never be
reclaimed. Two recoveries exist, neither of which re-evaluates a holdout
that has a recorded verdict:

- **Staging failed after the verdict** (`production_model_staging_failed`
  in the summary): `--resume-staging=<run id> --ticker --tf` stages the
  candidate from that run's recorded gates 1-4 verdict. It refuses unless
  the current dataset fingerprint, code commit, seed, class-weight power and
  feature columns equal the ones the run recorded, so the staged model is
  the candidate that was judged, and it scores no fold and writes no
  prediction.
- **The holder died before ANY durable output** (state still `claimed`, no
  summary, no predictions): `--reclaim-incomplete=<run id> --ticker --tf`
  moves the claim to a new run and runs the final test. Each transition
  writes an immutable audit blob per holder and appends to the marker's
  `history`; at most `FINAL_RECLAIM_LIMIT` (2) reclaims per cell.

The final-test folds are fixed at `[window.start]`; custom `--cutoffs` are
refused there, and the one-time version is the `FINAL_TEST_VERSION` constant,
not a flag. Only a `final_test` run may publish a production model:
`--persist-production-model` under development or validation logs a refusal
and records it as `production_model_refused` in the summary, since the
deployed job's default window is development. A final-test run that clears
gates 1-4 STAGES its candidate (artifacts plus a `PROMOTION_STAGED` marker
under the run prefix, recorded as `production_model_staged`) and leaves
`LATEST` untouched, because gates 5-7 (bootstrap, mechanism,
implied-vs-realized) are scored afterwards on the run's predictions.
A phase-0 final run stages whether or not the flag was passed, since it
has consumed the one-time version. Promotion is the operator writing the
run id to `LATEST` once gates 5-7 pass; `mag_inference` reads a staged-only
prefix as never promoted. Gate 7's requirements scale like gates 1-4
(`mag_config.gate7_requirements`: 8 -> 6 passing of 4 covered, 5 -> 4/3,
2 -> 2/1, 1 -> 1/1) over the folds the run's summary scheduled, and every
post-hoc script reads the dataset only through its window's end.
`scripts/naive_calendar_lookup_baseline.py` refuses the final window
outright and builds its masks with the harness's session purge.

A run reads the dataset only through its window's end (`until`), so a
development or validation run never labels, class-balances or fingerprints
final-test rows. Gates 1-4 keep the 6-of-8 bar as a fraction of the folds
the run holds (`mag_config.min_folds_required`: 8 -> 6, 5 -> 4, 2 -> 2,
1 -> 1); the bar and the fold count are recorded in the summary's `gates`.

Validation and final-test artifacts are written under their own
`research/magnitude_engine/_windows/<name>/` root (development keeps the
historical path), and every reader (`assemble_magnitude_results`, the
analysis scripts' `--evaluation-window`) selects a window and checks the
summary's `split_name` against it. Provenance records the image digest the
job was deployed with (`CONTAINER_IMAGE_DIGEST`, set by
`deploy_magnitude_engine`) and the source commit baked into the image
(`gcp/build_info.json`, written by `deploy.sh _stamp_build_info`); either is
NULL, never a placeholder, when unavailable.

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

Per-cell. The original eight-fold schedule requires 6/8 folds; an
evaluation window holds fewer yearly folds, so the evaluator applies the
same bar as a ceiling-rounded fraction of the folds the run ATTEMPTED
(`mag_config.min_folds_required`: 8 -> 6, 5 -> 4, 2 -> 2, 1 -> 1). A thin or
errored fold still counts in the denominator; it can never lower the bar.

1. log-loss beat positive in ≥ 6/8 of attempted folds
2. ECE within ceiling (0.05 for 5m + 15m; 0.075 for 30m) in ≥ 6/8 of attempted folds
3. decisive-call hit rate rises monotonically across thresholds 0.40 → 0.70 in ≥ 6/8 of attempted folds
4. EXPLOSIVE-bucket lift over base ≥ 1.5 in ≥ 6/8 of attempted folds — since
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
