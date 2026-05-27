"""Options Exec-Backtest — strat playbook traded via SPY 0DTE ATM options.

Parallels lib.exec_backtest (Track B, IWM underlying-space). This module
keeps stop/target/time-stop in UNDERLYING price space, but the trade
vehicle is a long ATM 0DTE call (for 2U setups) or put (for 2D setups).
P&L is realized in OPTION premium space via BSM pricing walked through
the trade window with a constant entry IV (no IV path modeling — the
conservative read).

Modules:
  - pricing  : pure-numpy BSM helpers (price, ATM-strike rounding)
  - iv_lookup: pull entry IV from etf_options_snapshots (intraday or EOD-prev)
  - engine   : trade lifecycle simulator — copies Track B's underlying
               stop/target detection, then prices the option at entry/exit
  - runner   : walk-forward orchestrator, SPY-only, 2022-2026 (5 folds)
  - cli      : Cloud Run Job entry point
"""
from lib.options_exec_backtest.pricing import (  # noqa: F401
    bs_price, bs_price_vec, atm_strike,
)
