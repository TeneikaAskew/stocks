# Execution-System Backtest (Track B reference artifact)

**Status: FAIL — DO NOT REVIVE WITHOUT NEW EVIDENCE.**
See [`docs/EXEC_BACKTEST_RESULTS.md`](../../docs/EXEC_BACKTEST_RESULTS.md) for the per-cell, per-fold verdict tables.

This module is the reference implementation of the strat-methodology execution playbook applied mechanically to the type model's confident calls. It was tested against the original PRD's success bar across 88,137 trades on IWM × {5m, 15m, 30m} × 8 walk-forward folds (2019-2026). **Every cell failed every condition of the binary success bar.** The type model is a structure predictor, not a magnitude predictor — the 1.5R × 40% hit-rate construction is break-even by design, and the 5¢ round-trip friction makes net expectancy negative across every regime.

The module stays in-tree as a reference for "tried, didn't work" rather than being deleted, so any future revival has a baseline to compare against. The strat-engine type model itself is unmodified by this work.

## What's here

- `engine.py` — hermetic per-prediction trade lifecycle simulator
- `runner.py` — per-cell walk-forward orchestrator (8 anchored folds)
- `ftfc.py` — strat-candle FTFC weighted score (used by variant 1, never run)
- `cli.py` — Cloud Run Job entry point: `python -m lib.exec_backtest.cli`

## What was tested

| Cell | n trades | hit rate | net exp / sh | pos-exp folds | Verdict |
|---|---:|---:|---:|---:|:---|
| 5m | 62,138 | 40.5% | −$0.052 | 0 / 8 | FAIL |
| 15m | 18,542 | 43.1% | −$0.054 | 0 / 8 | FAIL |
| 30m | 7,456 | 43.3% | −$0.061 | 0 / 8 | FAIL |

Per the original spec, variants (FTFC filter, higher confidence threshold, 2.0× target) were NOT dispatched because all three cells failed the base case decisively.

## Why this lives in-repo

Per Track B's spec: "Do not modify the type model in any track. Track B and C code stays merged as reference." This module is a load-bearing piece of evidence that the type model cannot be naively traded on its body-direction; any future direction or execution work must start from this baseline.
