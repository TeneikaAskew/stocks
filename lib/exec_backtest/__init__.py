"""Exec-backtest — realistic execution-cost backtest for the strat engine.

Track B deliverable: measure whether the strat type-model's high-confidence
2U/2D predictions, mechanically executed under realistic friction
(commission + spread + slippage, intrabar 1m fills), produce
regime-stable positive net expectancy on IWM across 8 walk-forward folds.

Modules:
  - engine: trade lifecycle simulator (per-prediction-row → trade-or-skip)
  - runner: orchestrates per-fold model training + prediction + simulation
  - cli: entry point for Cloud Run Job (`python -m lib.exec_backtest.cli`)
"""
