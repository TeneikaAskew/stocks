# Strat Directionality Engine

Movement prediction only — **no money in v1.** For a given ticker, at the
close of each bar, output `P(next bar is 1 / 2U / 2D / 3)` per timeframe,
plus the FTFC stacked read and the indicator drivers.

See `STRAT_DIRECTIONALITY_ENGINE_PRD.md` + `..._TECH_PLAN.md` for product
intent. This README is the engineering reference.

## File map

```
gcp/research/strat_engine/
├── README.md                    this file
├── __init__.py
├── strat_config.py              shared config (tickers, TFs, thresholds,
│                                FTFC weights, GCS paths, ALL 6 open
│                                decisions defaulted with reviewer values)
├── strat_dataset.py             shared loader. SELECT strat_features
│                                LEFT JOIN strat_features_levels +
│                                session-aware prev1/2/3 lags +
│                                next_bar_type label.
│                                Exposes discover_numeric_features().
├── strat_data_builder.py        SOURCE-OF-TRUTH data builder. Copied
│                                2026-05-26 from p7_build_multi_tf_features
│                                with forward-compat hooks for ORB /
│                                historical / current-period / order-block
│                                cols (computation wired, emit commented
│                                pending schema migration).
├── strat_data_pipeline.py      Thin admin/dispatch wrapper. Modes:
│                                  --mode=summary        coverage report
│                                  --mode=verify         label / leak gate
│                                  --mode=ensure-coverage dispatches the
│                                                       data builder for
│                                                       any missing TFs
│                                                       (uniform path for
│                                                       1m..4h — 4h is
│                                                       now native to the
│                                                       builder)
├── strat_enrich_levels.py       Stage 1b — backfill ORB + historical
│                                levels + current-period + order blocks
│                                into strat_features_levels_{tf}.
├── strat_eda_baserates.py       Stage 2 — base rates + transition matrices.
├── strat_corr_indicators.py     Stage 3 — per-class MI ranking + curves.
├── strat_pred_train.py          Stage 4 — calibrated 4-class LightGBM,
│                                walk-forward OOS, ECE.
├── strat_ftfc_assemble.py       Stage 5 — multi-TF as-of stack, bar-close
│                                stamped, weighted continuity score.
├── strat_readout.py             Stage 6 — per-ticker JSON read-out.
└── strat_orchestrator.py        Chains stages 1→6 with gate enforcement.
                                 Modes: full / from-stage / only-stage /
                                 all-tickers. Soft gate: log-loss + ECE
                                 hard, accuracy advisory.
```

## Cloud Run Job

**One job hosts the whole pipeline:** `strat-engine`. Entry point selected via `--args`:

```bash
# Full pipeline for one cell (the default)
gcloud run jobs execute strat-engine --region=us-east1

# Just the data builder for a specific gap
gcloud run jobs execute strat-engine --region=us-east1 \
  --args="-m,gcp.research.strat_engine.strat_data_builder,--tickers=IWM,--tf-only=15m"

# Coverage report
gcloud run jobs execute strat-engine --region=us-east1 \
  --args="-m,gcp.research.strat_engine.strat_data_pipeline,--mode=summary"

# Backfill the enrichment companion table
gcloud run jobs execute strat-engine --region=us-east1 \
  --args="-m,gcp.research.strat_engine.strat_enrich_levels,--mode=backfill,--ticker=IWM,--tf=15m"
```

The job is defined in `gcp/deploy.sh::deploy_strat_engine`. Run
`./deploy.sh strat-engine` to (re)create.

## Dependency graph

```
strat_orchestrator.py  ─┬─►  strat_data_pipeline.py    (Stage 1, admin)
                        │     ├── strat_config.py
                        │     ├── strat_dataset.py
                        │     └── DISPATCHES via subprocess gcloud:
                        │           └── strat-engine job →
                        │               strat_data_builder.py
                        │               (handles all 6 TFs uniformly,
                        │                4h via TF_LIST + FOUR_H_DDL)
                        │
                        ├─►  strat_eda_baserates.py  (Stage 2)
                        ├─►  strat_corr_indicators.py (Stage 3)
                        ├─►  strat_pred_train.py     (Stage 4)
                        ├─►  strat_ftfc_assemble.py  (Stage 5)
                        │     └── reuses strat_pred_train.featurize
                        └─►  strat_readout.py        (Stage 6)
                              └── strat_ftfc_assemble.assemble_ftfc

strat_enrich_levels.py  (Stage 1b — standalone, not in orchestrator chain)
  ├── strat_config.py
  └── lib.indicators (calculate_all_orb, calculate_historical_levels,
                       calculate_current_period_levels,
                       calculate_order_blocks, calculate_atr)

Shared by all scripts:
  gcp.database (get_engine, bulk_copy_upsert, execute_sql)
  lib.logging_config
```

## Tables

| table | populated by | rows | purpose |
|---|---|---|---|
| `strat_features_{1m,5m,15m,30m,60m,4h}` | `strat_data_builder.py` (or the legacy `p7_build_multi_tf_features.py`) | 17k-1M per ticker | OHLCV + strat sequence + core indicators + regime context |
| `strat_features_levels_{tf}` | `strat_enrich_levels.py` | mirrors `strat_features_{tf}` | ORB + historical levels + current-period + order blocks. Will fold into strat_features after schema migration. |
| `strat_pred_{tf}` | `strat_pred_train.py` | per-bar | Calibrated 4-class probabilities. |
| `strat_corr_ranked` | `strat_corr_indicators.py` | per (ticker, tf, class) × feature | MI rank + direction. |
| `strat_ftfc` | `strat_ftfc_assemble.py` | per 1m clock bar | Multi-TF stacked read + continuity. |

## Gates

Stage 1 (`--mode=verify`): row count, label correctness on 50 random
bars, no `vix_close` same-day leak, class balance > 0 per class.

Stage 4 (the model gate):
- **HARD**: model log-loss < base-rate log-loss
- **HARD**: ECE ≤ `DEFAULT_ECE_CEILING` (0.05)
- **ADVISORY**: accuracy beats base by ≥ `DEFAULT_BASE_RATE_BEAT_PP` (5pp)

If Stage 4 fails its HARD gate, Stages 5 + 6 are skipped for that cell.

## Open decisions (defaulted, locked here, override-able via CLI)

1. SPX intraday: **dropped** — no intraday source available.
2. 4h source: **aggregate from 60m** (ET 09:30 origin).
3. Calibration: **isotonic** (vs sigmoid).
4. Correlation primary metric: **mutual information** (vs linear).
5. Read-out form: **JSON/table** (Pine label feed deferred to M4).
6. Acceptance thresholds: **+5pp accuracy advisory, ≤0.05 ECE hard, log-loss < base hard**.

All defaults in `strat_config.py`; override per-run via `--ticker`,
`--tf`, `--train-until`, `--calibration`, `--base-rate-beat-pp`, etc.

## What is NOT here

- The retired P7 modeling pipeline (p7a/b/c/d/e/f/g) — quarantined in
  `gcp/research/_archive/`. Read those for prior-research methodology
  only; never re-deploy.
- The pure backtest framework — `lib/backtest.py`. The strat_engine
  predicts movement, not P&L. Backtests live elsewhere.
