"""Phase 0.8 — Tier-B + Tier-C constants for the strategies package.

Per the three-tier classification in
docs/plans/SIGNAL_QUALITY_TEST_PLAN.md Phase 0.6:

  Tier A — per-ticker, calibrated. Lives in `ticker_calibration` Cloud
           SQL table (refreshed quarterly by
           `scripts/calibrate_thresholds.py`). Loaded at runtime via
           `lib.strategies.calibration` — see that module for the
           resolution chain. PUT range derives from (rsi_p50, rsi_p90);
           CALL range from (rsi_p10, rsi_p50).
  Tier B — universal across tickers but TESTED. Lives here. Used as
           the FALLBACK when Tier-A is missing, stale, or has NULL
           percentile columns. Future tests/test_universal_param_validity.py
           asserts each value is still appropriate by grid-searching
           alternates against 60-day per-ticker history.
  Tier C — universal, structural definitions. Lives here. Don't
           tune; changing them changes the meaning of the setup.

If `tests/test_universal_param_validity.py` fails for a constant, the
fix is either to update the constant OR rely on Tier-A (per-ticker)
calibration to override it for the affected tickers.
"""
from __future__ import annotations

# ── Tier B — universal but tested (FALLBACK for Tier-A) ────────────────

# RSI bands for CALL/PUT setups (mean-reversion uses the same bands as
# momentum to keep score-distribution comparable across strategies).
# Per-ticker overrides resolve via lib.strategies.calibration.get_*_rsi_range().
CALL_RSI_RANGE: tuple[float, float] = (25.0, 50.0)
PUT_RSI_RANGE:  tuple[float, float] = (50.0, 75.0)

# How close to EMAs counts as "near" (% from price).
EMA_PROXIMITY: float = 0.1

# Stochastic RSI thresholds for "oversold" / "overbought" gating.
# These are SIGNAL-GATING values (when does a strategy include
# "stoch_rsi_oversold" as a scoring condition). They are deliberately
# different from the 20/80 values used in `gcp/premarket_brief.py` and
# the React HelpPage glossary — those are NARRATIVE REGIME LABELS for
# display, not signal gates. The two concepts are intentionally distinct.
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

# Phase 0.7.x — `atr_expansion` momentum condition. Fires when the
# 5-bar ATR exceeds the 20-bar ATR by at least this multiple, indicating
# current volatility is above its longer-window baseline (regime
# expansion = tradeable conditions). Direction-agnostic — vol regime
# confirms either side of a setup. Reads from the `ATR_Expansion`
# column populated by `lib.indicators.add_all_indicators`.
ATR_EXPANSION_THRESHOLD: float = 1.15

# Phase 0.7.x — `rsi_thrust` momentum condition. Directional, unlike
# rvol/atr_expansion. CALL fires when the 3-bar RSI delta exceeds
# +RSI_THRUST_THRESHOLD (RSI accelerating up); PUT fires when it falls
# below -RSI_THRUST_THRESHOLD (RSI accelerating down). Complements the
# existing `rsi_bullish_recovery` band check (which is a level test):
# a bar with RSI=70 (out of recovery band) but +10 over 3 bars has
# thrust without recovery. Reads from the `RSI_Thrust_3` column
# populated by `lib.indicators.add_all_indicators`.
RSI_THRUST_THRESHOLD: float = 5.0

# Minimum number of conditions met (out of 7) for a signal to fire.
# Same definition across both strategies for comparability.
MIN_CONDITIONS: int = 3

# Phase 0.7.x — tiered scoring. PRs 2-4 added three CONFIRMING conditions
# (rvol_above_recent, atr_expansion, rsi_thrust) but kept MIN_CONDITIONS=3
# flat, walking the gate from 75% → 43% required. A bar can now fire from
# 3 confirmers with zero CORE conditions — "noise + activity," not a setup.
# This floor enforces "setup first, then confirmation" as a discretionary
# trader thinks about it. CORE = defines the setup; CONFIRMING = validates
# it but can't define it.
#
# Provisional: `2` is asserted from the truth table, NOT measured against
# production data. PR-6 (production-replay calibration) decides whether
# this stays at 2, moves to 3 (stricter), or stays at 2 with a stricter
# total-score floor.
#
# Forward-compatibility: every new condition added after this point gets
# a tier classification at addition time. Default is CONFIRMING unless
# the condition independently defines a setup. Failure to classify =
# the next person repeats PR-2's mistake.
MIN_CORE_CONDITIONS: int = 2

CORE_CALL_CONDITIONS: frozenset = frozenset({
    "consecutive_up",
    "rsi_bullish_recovery",
    "above_vwap",
    "above_ema9",
})

CORE_PUT_CONDITIONS: frozenset = frozenset({
    "consecutive_down",
    "rsi_bearish_recovery",
    "below_vwap",
    "below_ema9",
})
