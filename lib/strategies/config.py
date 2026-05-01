"""Phase 0.8 — Tier-B + Tier-C constants for the strategies package.

Per the three-tier classification in
docs/plans/SIGNAL_QUALITY_TEST_PLAN.md Phase 0.6:

  Tier A — per-ticker, calibrated. Lives in `ticker_calibration` Cloud
           SQL table; loaded at runtime via lib.strategies.calibration.
  Tier B — universal across tickers but TESTED. Lives here. Future
           tests/test_universal_param_validity.py asserts each value
           is still appropriate by grid-searching alternates against
           60-day per-ticker history.
  Tier C — universal, structural definitions. Lives here. Don't
           tune; changing them changes the meaning of the setup.

If `tests/test_universal_param_validity.py` fails for a constant, the
fix is either to update the constant OR promote it to Tier A in
`ticker_calibration`.
"""
from __future__ import annotations

# ── Tier B — universal but tested ──────────────────────────────────────

# RSI bands for CALL/PUT setups (mean-reversion uses the same bands as
# momentum to keep score-distribution comparable across strategies).
CALL_RSI_RANGE: tuple[float, float] = (25.0, 50.0)
PUT_RSI_RANGE:  tuple[float, float] = (50.0, 75.0)

# How close to EMAs counts as "near" (% from price).
EMA_PROXIMITY: float = 0.1

# Stochastic RSI thresholds for "oversold" / "overbought" gating.
STOCH_RSI_OVERSOLD:   float = 30.0
STOCH_RSI_OVERBOUGHT: float = 70.0


# ── Tier C — universal, structural ─────────────────────────────────────

# How many bars in a row constitute a "consecutive" run for the
# Consecutive_Up / Consecutive_Down conditions. This is part of the
# DEFINITION of the setup ("3 bars in a row"), not a vol-scaling number.
# Don't tune.
CONSECUTIVE_PERIODS: int = 3

# Minimum number of conditions met (out of 5/6) for a signal to fire.
# Same definition across both strategies for comparability.
MIN_CONDITIONS: int = 3
