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

# Phase 0.7.2 — relaxed "3-of-last-5" momentum gate. The strict
# `Consecutive_Up >= 3` (3-of-3) misses obvious uptrends with one
# pullback bar. The relaxed gate counts up-bars in a 5-bar window and
# fires when at least CONSECUTIVE_THRESHOLD of them are up. Reads from
# the `Consecutive_Up_5` / `Consecutive_Down_5` columns populated by
# `lib.indicators.add_all_indicators`.
CONSECUTIVE_WINDOW: int = 5
CONSECUTIVE_THRESHOLD: int = 3

# Phase 0.7.x — `rvol_above_recent` momentum condition. Fires when
# current bar volume exceeds the rolling median over the last 20 bars
# by at least this multiple. Reads from the `RVol_Recent_20` column
# populated by `lib.indicators.add_all_indicators`. Median-based to be
# robust to single-bar volume spikes (news, opening minute) that bias
# the mean-based `RVOL` column downward on subsequent bars.
RVOL_RECENT_THRESHOLD: float = 1.2

# Minimum number of conditions met (out of 5/6) for a signal to fire.
# Same definition across both strategies for comparability.
MIN_CONDITIONS: int = 3
