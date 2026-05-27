# Strat Engine — Operations Manual

**Status: ON THE SHELF.** The strat-engine candle-type prediction model is finalized as a production-grade deliverable. It is callable on demand. **It is NOT activated** — no schedulers, no user-facing routes, no live brief integration. The deploy gate at the bottom of this doc defines what would need to be true to activate any production trigger.

---

## 1. What the model is

A multi-class LightGBM classifier that predicts the next bar's **strat candle type** (1, 2U, 2D, or 3) given the current state of the market.

| Property | Value |
|---|---|
| Target | Next bar's strat candle type (4-class) |
| Algorithm | LightGBM `LGBMClassifier` (objective=`multiclass`, 4 classes) |
| Calibration | **`none`** — raw native softmax (the 24-fold walk-forward proved sigmoid Platt scaling hurt calibration in 24/24 folds) |
| Feature set | 143-column enriched feature set (technicals + ORB + historical levels + order blocks + gamma + VIX context) |
| Deployed cells | IWM, SPY, QQQ × 5m, 15m, 30m timeframes (9 cells; 1m and 60m excluded per the locked FTFC config) |
| Training method | Anchored expanding walk-forward, 8 cutoffs (2019/2020/2021/2022/2023/2024/2025/2026), no recalibration between folds |

The model is **frozen**. The configuration, hyperparameters, feature set, and calibration policy are not changed by routine operations. Retraining is allowed (and expected — see §5), but the configuration is fixed.

## 2. What the model is NOT

| Not validated | Evidence |
|---|---|
| Bar-body direction (close > open) | Track C R&D: 0/24 walk-forward folds had positive log-loss beat across news / cross-asset / vol-regime feature families. See [`DIRECTION_FEATURES_R&D.md`](DIRECTION_FEATURES_R&D.md). |
| Net-P&L-after-friction edge under the strat execution playbook | Track B exec backtest: 0/8 walk-forward folds positive net expectancy, in all 3 cells, on 88k trades. Friction is structurally larger than the gross edge. See [`EXEC_BACKTEST_RESULTS.md`](EXEC_BACKTEST_RESULTS.md). |
| Magnitude / how far the next bar travels | Out of scope; the model is a class predictor, not a regression. |
| Earnings-window, gap-day, or pre-market edge | Not tested; the training window includes those bars but the model is not specialized. |

The model is a **structure predictor**, not a directional or P&L surface. The verbatim scope statement used everywhere this is surfaced (brief, API, dev page):

> Calibrated structure prediction. Not a directional or P&L edge. Use with discretion.

## 3. Where the artifacts live

### GCS

| Path | Contents |
|---|---|
| `gs://${BUCKET}/research/strat_engine/{ticker}_{tf}/model.pkl` | Pickled `lgb.LGBMClassifier` (the frozen production config) |
| `gs://${BUCKET}/research/strat_engine/{ticker}_{tf}/features.txt` | Feature-column list used at training time |
| `gs://${BUCKET}/research/strat_engine/{ticker}_{tf}/classes.txt` | Class-label order used by `predict_proba` |
| `gs://${BUCKET}/research/strat_engine/{ticker}_{tf}/metrics.json` | OOS metrics + `run_id` + training timestamps |
| `gs://${BUCKET}/research/strat_engine/{ticker}_{tf}/runs/{run_id}/` | Per-run archive (every training run lands here too) |
| `gs://${BUCKET}/research/strat_engine/structure_brief_latest.json` | (Future) live-ECE rolling-window snapshot — read by `/api/admin/structure-brief` and `/api/admin/strat-engine/predict` for the mute decision. Out of scope for this closeout. |

`${BUCKET}` is `adept-mountain-474619-d4-trading-data` in production.

### Cloud SQL

The `trading` database holds the feature surface read by the model:

| Table | Purpose |
|---|---|
| `strat_features_{tf}` (one per timeframe) | Per-bar strat structure + ~140 indicators / gamma / VIX columns |
| `strat_features_levels_{tf}` | Enrichment companion tables: ORB / historical levels / order blocks |
| `market_data_intraday` (partitioned by ticker) | 1-minute OHLCV bars |
| `market_data_daily` | Daily OHLCV + VIX |

The model **never reads** intraday/daily directly. It reads from the strat_features tables that were built off them. See [`docs/STRAT_ENGINE_ERD.md`](STRAT_ENGINE_ERD.md).

## 4. How to refresh predictions

The model is on-demand only. There are three call paths.

### Path A — admin API endpoint (preferred for one-off lookups)

```bash
curl -X POST \
    -H "X-Admin-Token: $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"ticker": "IWM", "timeframe": "15m"}' \
    https://${PLATFORM_HOST}/api/admin/strat-engine/predict
```

Optional `as_of_timestamp` in the body for a historical bar. Response shape:

```json
{
  "ticker": "IWM",
  "timeframe": "15m",
  "ts": "2026-05-22T19:45:00+00:00",
  "available": true,
  "top_class": "2U",
  "top_prob": 0.62,
  "class_probs": {"1": 0.10, "2U": 0.62, "2D": 0.23, "3": 0.05},
  "model_version": "...",
  "last_train_date": "2026-05-26T13:00:00Z",
  "live_ece": null,
  "muted": false,
  "mute_reason": null,
  "scope_statement": "Calibrated structure prediction. Not a directional or P&L edge. Use with discretion.",
  "note": null
}
```

When `muted` is true (live ECE breach), `top_class` / `top_prob` / `class_probs` are stripped and `mute_reason` is populated.

### Path B — Cloud Run Job (preferred for bulk refreshes)

```bash
gcloud run jobs execute strat-engine \
  --region=us-east1 --project=adept-mountain-474619-d4 \
  --args="-m,gcp.research.strat_engine.strat_pred_serve,--ticker=IWM,--tf=15m" \
  --wait
```

This runs the same code path as the API endpoint but inside the Cloud Run Job environment. Useful when you want to log the prediction to the job's stdout or chain it into another job.

### Path C — Cloud Run Job, retrain + refresh (rare)

When you actually want to retrain the model (see §5 for triggers), dispatch the Stage 4 trainer:

```bash
gcloud run jobs execute strat-engine \
  --region=us-east1 --project=adept-mountain-474619-d4 \
  --args="-m,gcp.research.strat_engine.strat_pred_train,--ticker=IWM,--tf=15m,--train-until=2026-05-27" \
  --wait
```

`--train-until` defaults to the locked OOS cutoff. The LOCKED-default config (`calibration=none`) overwrites `model.pkl`; variants archive to `runs/{run_id}/` without trampling.

## 5. Live ECE monitoring & self-mute

The model carries a self-mute discipline: when its rolling out-of-sample ECE exceeds the per-cell ceiling of **0.05**, the brief and the predict endpoint hide the prediction and return a mute message.

### What's live today

- The mute logic is implemented end-to-end (`StructureBrief.tsx` client-side, `_build_brief_cell` + `predict_one` server-side).
- The ECE source is `gs://${BUCKET}/research/strat_engine/structure_brief_latest.json`.

### What's NOT live today (deferred, out of scope for the closeout)

- **The snapshot writer that updates `structure_brief_latest.json`.** Without it, every cell shows `live_ece: null` and the mute logic is a no-op. The model surface degrades cleanly to "available but no calibration health reading," which is honest.
- A scheduled re-calibration job. None exists. None scheduled.

To activate the live-ECE monitor, build a Cloud Run Job that:
1. For each (ticker, tf) cell, computes the rolling-window ECE on the last N actuals
2. Writes the per-cell summary to `structure_brief_latest.json`
3. Runs on a schedule (e.g. nightly)

That job's deploy is gated — see §8.

## 6. When to retrain

Retrain triggers (any one is sufficient):

1. **A new market regime emerges that wasn't in the training span.** Heuristic: the rolling 20-session structure-distribution Wasserstein distance to the training-distribution baseline exceeds a threshold. (Threshold TBD — not specified at finalization.)
2. **Rolling live ECE drifts above the ceiling for 5 consecutive sessions.** Self-mute will already have kicked in; retraining is the recovery move.
3. **A new ticker or timeframe is added to scope.** Each (ticker, tf) cell trains independently.
4. **A new feature is added to the production featurize() path.** This requires a fresh walk-forward validation pass on top of retraining (see §8).

Retraining is mechanical — dispatch the Stage 4 trainer (Path C above). The LOCKED-default writes back to the top-level model.pkl path; the per-run archive preserves the prior model for rollback.

## 7. Reference artifacts (do not revive without new evidence)

| Path | Status | Why it's in repo |
|---|---|---|
| `lib/exec_backtest/` | FAIL verdict | Reference baseline for any future "can we trade this?" experiment. See [`docs/EXEC_BACKTEST_RESULTS.md`](EXEC_BACKTEST_RESULTS.md). |
| `lib/features/experimental/` | FAIL × 3 + INFEASIBLE × 1 | Reference baseline for any future "what would unlock direction?" experiment. See [`docs/DIRECTION_FEATURES_R&D.md`](DIRECTION_FEATURES_R&D.md). |
| `gcp/research/strat_engine/strat_dir_walk_forward.py` | FAIL baseline (24/24 folds) | The harness that proved direction is not learnable from the production feature set. |

If anyone proposes to revive any of these, the bar is: produce new evidence that contradicts the FAIL verdict (a new feature, a new label, a new dataset, a new ticker, a new market regime). Reviving without new evidence is reproducing the same failure.

## 8. Activation gate (NON-NEGOTIABLE)

Activating any **production trigger** on the strat engine — scheduler, user-facing route, live-brief integration, autonomous trading — requires ALL of the following:

1. **A documented use case** that names the consumer (which surface, who reads it, when, what action it informs) and addresses the FAIL verdicts of Tracks B + C (i.e., explains why the consumer accepts the validated quantity (structure) and never claims the unvalidated quantities (direction, P&L)).
2. **A fresh validation pass** against the original PRD's success bars. The success bars are not relaxed. The validation is a fresh walk-forward against the current model + ticker + cell, with whatever new evidence the use case introduces.
3. **An explicit deploy approval** from the project owner, recorded in the PR description.

Until all three are present, the strat-engine job stays callable but quiescent. No schedulers, no triggers, no integrations.

## 9. Quick operational reference

| Task | Command |
|---|---|
| Predict (admin API) | `curl -X POST -H "X-Admin-Token: $ADMIN_TOKEN" -d '{"ticker":"IWM","timeframe":"15m"}' .../api/admin/strat-engine/predict` |
| Predict (Cloud Run Job) | `gcloud run jobs execute strat-engine --args="-m,gcp.research.strat_engine.strat_pred_serve,--ticker=IWM,--tf=15m" --wait` |
| Retrain | `gcloud run jobs execute strat-engine --args="-m,gcp.research.strat_engine.strat_pred_train,--ticker=IWM,--tf=15m" --wait` |
| Walk-forward (validation) | `gcloud run jobs execute strat-engine --args="-m,gcp.research.strat_engine.strat_walk_forward,--ticker=IWM,--tf=15m" --wait` |
| Read structure-brief snapshot | `gsutil cat gs://${BUCKET}/research/strat_engine/structure_brief_latest.json` |
| Dev page snapshot | open `https://${PLATFORM_HOST}/dev` (IAP-authenticated as the admin email) |
| Check scheduler status | `gcloud scheduler jobs list --location=us-east1 --filter="name~strat-engine"` (should return zero rows) |
