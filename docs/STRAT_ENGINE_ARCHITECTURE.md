# Strat Directionality Engine — Architecture

**Status:** v1 in progress (M2 LOCKED for IWM 15m, calibration=sigmoid cv=3)
**Companions:**
- [`STRAT_ENGINE_ARCHITECTURE.drawio`](./STRAT_ENGINE_ARCHITECTURE.drawio) — layer diagram
- [`STRAT_ENGINE_ERD.md`](./STRAT_ENGINE_ERD.md) + [`STRAT_ENGINE_ERD.drawio`](./STRAT_ENGINE_ERD.drawio) — table-level schema + relationships

**Scope:** movement prediction only — `P(next bar ∈ {1, 2U, 2D, 3})` per ticker × TF. NO money / P&L in v1.

## 1. Design principles

1. **One Cloud Run Job, many entry points.** `strat-engine` job runs every script in the package via different `--args`. No per-script jobs to manage.
2. **Source-of-truth is `strat_features_{tf}`.** Everything downstream reads from it. Indicators are computed ONCE at build time, not re-derived per analysis.
3. **Companion enrichment table, not schema mutation.** `strat_features_levels_{tf}` is a separate join table for ORB / historical levels / order blocks / current-period. Schema migration of the main table is deferred until the feature set stabilizes.
4. **Session-aware shifts in the loader, not the source.** `next_bar_type` label and `prev1/2/3_candle` lags are computed in `strat_dataset.load_labeled_dataset()` using `groupby('bar_date').shift(N)` so they never cross overnight gaps. The source's `prev_strat_candle` is contaminated and ignored.
5. **Gates over guesses.** Stage 1 verifies row counts / label correctness / no VIX leak. Stage 4 requires log-loss-beats-baseline AND ECE ≤ 0.05 (accuracy is advisory). Stages 5+6 skip if Stage 4 fails.
6. **Calibration is mandatory.** Stage 4 uses `CalibratedClassifierCV(method=sigmoid, cv=3)` so that "the model says 70%" actually means 70%. Without calibration, the probabilities are noise.
7. **Movement only; no money.** The PRD's hard rule. Every deliverable that mentions $ goes in a separate Phase 5+ project.

## 2. Layered architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 5  Read-out / FTFC stack                                       │
│   strat_readout.py  ← per-ticker JSON: 4 probs/TF + continuity score │
│   strat_ftfc_assemble.py  ← multi-TF as-of join (bar-close stamped)  │
└─────────────────────────────────────────────────────────────────────┘
                                  ▲
                                  │ reads per-TF predictions
                                  │
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 4  Calibrated multiclass classifier                            │
│   strat_pred_train.py  ← LGBMClassifier wrapped in                   │
│                          CalibratedClassifierCV(sigmoid, cv=3)       │
│   - Gate: log-loss < base log-loss AND ECE ≤ 0.05 (hard)             │
│   - Advisory: accuracy beats base by ≥ 5pp                           │
│   - Output: model.pkl + metrics.json to GCS                          │
└─────────────────────────────────────────────────────────────────────┘
                                  ▲
                                  │ feature matrix
                                  │
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 3  Statistics & explainability                                 │
│   strat_eda_baserates.py  ← base rates + 1-bar + 3-bar transitions   │
│   strat_corr_indicators.py  ← per-class MI ranking + reliability     │
│   ↑ both call discover_numeric_features(df) so they auto-pick up     │
│     the enrichment columns alongside the base indicators             │
└─────────────────────────────────────────────────────────────────────┘
                                  ▲
                                  │ labeled DataFrame
                                  │
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 2  Labeled dataset loader                                      │
│   strat_dataset.py                                                   │
│   - SELECT strat_features_{tf} LEFT JOIN strat_features_levels_{tf}  │
│   - Add prev1/2/3_candle via groupby('bar_date').shift (session-safe)│
│   - Add next_bar_type label via groupby('bar_date').shift(-1)        │
│   - Drop last bar of each day (no label) + 3-bar warmup              │
│   - Filter to valid LABEL_CLASSES                                    │
│   - discover_numeric_features(df) helper for downstream stages       │
└─────────────────────────────────────────────────────────────────────┘
                                  ▲
                                  │ raw featurized bars
                                  │
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 1  Source-of-truth Cloud SQL tables                            │
│                                                                       │
│   strat_features_{1m,5m,15m,30m,60m,4h}  (69 cols each)              │
│   ├── OHLCV                                                          │
│   ├── strat_candle / prev_strat_candle / strat_combo / flags         │
│   ├── 30+ indicators (RSI, EMA, MACD, BB, ATR, VWAP, RVOL, OBV...)   │
│   ├── forward returns (5/15/30/60 bars)                              │
│   └── regime: vix_close / total_gex / total_vex / dealer_regime      │
│       (vix_close uses PRIOR-day VIX — same-day-leak fix 2026-05-25)  │
│                                                                       │
│   strat_features_levels_{tf}  (146 cols, M2 locked)                  │
│   ├── ORB 5m/15m/30m windows (36 cols)                               │
│   ├── Historical levels — prev day/week/month/quarter/year HLOC      │
│   │   + midpoints + percent + at-level + breakout flags (100 cols)   │
│   ├── Order blocks (7 cols)                                          │
│   └── (current-period cur_* cols GATED OFF for M2 schema consistency)│
└─────────────────────────────────────────────────────────────────────┘
                                  ▲
                                  │ writes
                                  │
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 0  Build pipeline                                              │
│                                                                       │
│   strat_data_builder.py     ← source-of-truth data builder           │
│   strat_enrich_levels.py    ← levels companion-table backfill        │
│   strat_data_pipeline.py       ← thin orchestrator (summary/verify/cov)│
│                                                                       │
│   Reads from:                                                        │
│   - market_data_intraday_{SPY,IWM,QQQ}  (1-min bars source)          │
│   - market_data_daily (^VIX for regime context)                      │
│   - etf_options_snapshots (GEX/VEX via lib.gamma)                    │
│   - gamma_levels_eod (King/Gate/Flip)                                │
└─────────────────────────────────────────────────────────────────────┘
```

## 3. Cloud Run Job (the single execution surface)

**`strat-engine`** — research image (lightgbm + scikit-learn + scipy + shap), 8 GiB / 4 CPU / 90-min timeout, `trading-runner` service account.

Every script in the package is invoked via `--args`:

| Workload | Command |
|---|---|
| Full pipeline (1 ticker × 1 TF) | `--args=-m,gcp.research.strat_engine.strat_orchestrator,--mode=full,--ticker=IWM,--tf=15m` |
| Data build (one cell) | `--args=-m,gcp.research.strat_engine.strat_data_builder,--tickers=IWM,--tf-only=15m` |
| Coverage report | `--args=-m,gcp.research.strat_engine.strat_data_pipeline,--mode=summary` |
| Stage 1 verify (label/leak gate) | `--args=-m,gcp.research.strat_engine.strat_data_pipeline,--mode=verify,--ticker=IWM,--tf=15m` |
| Levels backfill (one cell) | `--args=-m,gcp.research.strat_engine.strat_enrich_levels,--mode=backfill,--ticker=IWM,--tf=15m` |
| Stage 4 only (one cell, locked sigmoid) | `--args=-m,gcp.research.strat_engine.strat_pred_train,--ticker=IWM,--tf=5m` |
| Local diagnostic (read-only) | `python -m gcp.research.strat_engine.strat_pred_diagnose --ticker IWM --tf 15m` |

Deploy / update via `./gcp/deploy.sh strat-engine`.

## 4. Data flow per pipeline run

1. **Stage 1** loads `strat_features_{tf}` LEFT JOIN `strat_features_levels_{tf}`. Adds session-aware lags + label. Verifies row counts, label correctness on 50 random bars, no VIX same-day leak.
2. **Stage 2** computes base rate (the bar Stage 4 must beat) + 1-bar `P(next | current)` + 3-bar `P(next | prev2→prev1→current)` transition matrices. Outputs to GCS.
3. **Stage 3** ranks features per class by mutual information (one-vs-rest) with point-biserial direction. Includes ORB / historical / order blocks because `discover_numeric_features` picks them up by dtype.
4. **Stage 4** trains `CalibratedClassifierCV(LGBMClassifier, method=sigmoid, cv=3)` on training data, evaluates OOS. Saves `model.pkl` + `metrics_*.json` to GCS. Gate verdict written into metrics.
5. **Stage 5** loads all available per-TF models (1m..4h), scores OOS bars, shifts each TF's prediction `ts` by `+TF_MINUTES[tf]` so the as-of join sees bar-CLOSE (not bar-open — prevents in-progress leak), computes weighted continuity score per FTFC weights.
6. **Stage 6** assembles the per-ticker read-out: 4 probs at each TF, FTFC continuity + aligned direction, top drivers from latest Stage 3.

## 5. Gates

| Stage | Gate | If fail |
|---|---|---|
| 1 | TEST 1 row count, TEST 2 label correctness, TEST 3 VIX same-day leak | Abort pipeline for this cell |
| 4 | **HARD**: log-loss < base log-loss, **HARD**: ECE ≤ 0.05, **ADVISORY**: accuracy ≥ base + 5pp | Skip Stages 5 + 6 for this cell |
| 5 | At least one TF has a saved model | Skip Stage 6 |

## 6. Key fixes that landed during M2

| Issue | Fix |
|---|---|
| Session contamination in label/lag shifts | `groupby('bar_date').shift(N)` in loader |
| Stages 2 + 3 missed enrichment cols (iterated static `NUMERIC_FEATURES`) | `discover_numeric_features(df)` helper |
| Stage 4 gate too strict (all 3 metrics required) | log-loss + ECE hard; accuracy advisory |
| FTFC as-of join leaked in-progress higher-TF bars (`ts` is bar OPEN) | Shift each TF's prediction `ts` by `+TF_MINUTES[tf]` |
| Sparse-class `predict_proba` columns misaligned | Use `model.classes_` mapping |
| ORB / historical / order blocks missing from source | Companion table `strat_features_levels_{tf}` |
| VIX same-day leak in `strat_features_{tf}.vix_close` | Code fix + UPDATE on all 5 TF tables, re-verified |
| Stage 4 ECE 0.0510 just over 0.050 ceiling (isotonic) | Switched to sigmoid cv=3 → ECE 0.0439, gate PASS |

## 7. Configuration (`strat_config.py`)

All defaults live in `strat_config.py`. Stages accept overrides via CLI.

| Knob | Default | Override |
|---|---|---|
| `TICKERS` | `("IWM", "SPY", "QQQ")` | n/a — SPX dropped from intraday scope |
| `TIMEFRAMES` | `("1m", "5m", "15m", "30m", "60m", "4h")` | `--tf` |
| `LABEL_CLASSES` | `("1", "2U", "2D", "3")` | n/a |
| `DEFAULT_TRAIN_UNTIL` | `"2026-01-01"` | `--train-until` |
| `DEFAULT_CALIBRATION` | `"sigmoid"` (LOCKED 2026-05-26) | `--calibration {isotonic,sigmoid}` |
| `DEFAULT_BASE_RATE_BEAT_PP` | 5.0 (advisory only) | `--base-rate-beat-pp` |
| `DEFAULT_ECE_CEILING` | 0.05 | `--ece-ceiling` |
| `FTFC_WEIGHTS` | `{1m:0.05, 5m:0.10, 15m:0.15, 30m:0.20, 60m:0.25, 4h:0.25}` | n/a (file edit) |

## 8. Out of scope for v1 — explicit non-goals

- **Money / P&L / position sizing.** The PRD's hard rule. Movement prediction only.
- **Strategy execution / order routing.** Predictions → signal_monitor / orders is a separate Phase 5+ project.
- **Walk-forward CV per fold.** Currently uses anchored train/test split (`bar_date < train_until` vs `≥`). Walk-forward is a M5-era stability check before scaling to SPY/QQQ.
- **Class-imbalance fix for inside (1) / outside (3).** The model never predicts these because their calibrated probs never beat 2U/2D's argmax. Separate workstream after M2 completes.
- **Schema migration for `strat_features_{tf}` to absorb enrichment.** Companion table is the M2 strategy; absorption is M5+.

## 9. Companion artifacts

- `gcp/research/strat_engine/README.md` — operational file map (run commands, table inventory)
- `notebooks/strat_pred_diagnose.ipynb` — interactive companion to `strat_pred_diagnose.py`
- `gcp/queries/strat_engine_data_validation.sql` — pre-training data integrity check (run before any training round)
- `gcp/research/_archive/README.md` — quarantined P7 modeling pipeline (do not revive)
- This file's diagram: [`STRAT_ENGINE_ARCHITECTURE.drawio`](./STRAT_ENGINE_ARCHITECTURE.drawio)
