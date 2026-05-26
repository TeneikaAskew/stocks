"""Strat Directionality Engine — shared config.

Single source of truth for tickers, timeframes, indicator columns, table
names, default train/test split, FTFC weights, and acceptance thresholds.
Every stage script imports from here; no ticker / TF / threshold is hardcoded
anywhere else.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence


# ─────────────────────── Scope ───────────────────────
# Tickers in scope. SPX has no intraday source — see open decision #1.
# Default: drop SPX from intraday scope (will reconsider if user picks
# SPY-proxy or daily-only later).
TICKERS: tuple[str, ...] = ("IWM", "SPY", "QQQ")

# Timeframes in scope. 4h must be built (aggregate from 60m — open
# decision #2 default).
TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m", "30m", "60m", "4h")
TF_MINUTES: dict[str, int] = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60, "4h": 240,
}

# Train cutoff for OOS evaluation
DEFAULT_TRAIN_UNTIL = "2026-01-01"


# ─────────────────────── Features ───────────────────────
# The full numeric feature set. Stage 1 NEVER subsets — downstream stages
# may select. (PRD §"Data includes all indicators")
NUMERIC_FEATURES: tuple[str, ...] = (
    # Trend
    "ema_9", "ema_20", "ema_50", "ema_200", "sma_50", "sma_200",
    # Momentum
    "rsi_9", "rsi_14", "stoch_rsi_k", "stoch_rsi_d",
    "macd", "macd_signal", "macd_histogram",
    # Volatility
    "atr_14", "atr_20", "bb_upper", "bb_lower", "bb_width", "bb_pct",
    # Volume
    "obv", "rvol", "rvol_10",
    # VWAP / relative
    "vwap", "price_vs_vwap", "price_vs_ema9", "price_vs_ema20",
    # Price action
    "consecutive_up", "consecutive_down",
    "intraday_return", "high_low_spread_pct",
    # Regime
    "vix_close", "total_gex", "total_vex",
    "flip_price", "distance_to_king_pct", "distance_to_gate_pct",
)

# Categorical/sequence features. The PRD requires prev1/prev2/prev3 — only
# prev_strat_candle (=prev1) exists in strat_features today; strat_dataset.py
# adds prev2/prev3 via shift.
STRAT_SEQUENCE_FEATURES: tuple[str, ...] = (
    "strat_candle",
    "prev1_candle",     # = strat_features.prev_strat_candle
    "prev2_candle",     # NEW: shift(2) of strat_candle
    "prev3_candle",     # NEW: shift(3) of strat_candle
    "strat_combo",
)

REGIME_FEATURES: tuple[str, ...] = (
    "vix_tercile", "gex_tercile", "vex_tercile",
    "dealer_regime", "gamma_regime",
)

CATEGORICAL_FEATURES: tuple[str, ...] = STRAT_SEQUENCE_FEATURES + REGIME_FEATURES

# Target label
LABEL_COL = "next_bar_type"
LABEL_CLASSES: tuple[str, ...] = ("1", "2U", "2D", "3")
LABEL_TO_IDX: dict[str, int] = {c: i for i, c in enumerate(LABEL_CLASSES)}


# ─────────────────────── Storage ───────────────────────
GCS_BUCKET_DEFAULT = "adept-mountain-474619-d4-trading-data"
GCS_PREFIX = "research/strat_engine"


def strat_features_table(tf: str) -> str:
    """Source table per TF — already populated for 1m/5m/15m/30m/60m;
    Stage 1 build creates 4h."""
    return f"strat_features_{tf}"


def strat_pred_table(tf: str) -> str:
    """Stage 4 output: calibrated per-bar probabilities."""
    return f"strat_pred_{tf}"


STRAT_CORR_TABLE = "strat_corr_ranked"
STRAT_FTFC_TABLE = "strat_ftfc"


def gcs_model_prefix(ticker: str, tf: str) -> str:
    return f"{GCS_PREFIX}/{ticker.lower()}_{tf}"


# ─────────────────────── Acceptance thresholds ───────────────────────
# PRD §"Definition of done" — configurable. Defaults are reviewer-recommended
# starting points; tune after first M2 cell.
DEFAULT_BASE_RATE_BEAT_PP = 5.0    # OOS accuracy must beat the base rate by >= this many pp
DEFAULT_ECE_CEILING = 0.05         # Expected Calibration Error must be <= this


# ─────────────────────── FTFC weights ───────────────────────
# Stage 5 weights each TF's contribution to the continuity score. Higher TFs
# carry more weight (the longer-term trend dominates the alignment read).
# Sum = 1.0.
FTFC_WEIGHTS: dict[str, float] = {
    "1m": 0.05, "5m": 0.10, "15m": 0.15,
    "30m": 0.20, "60m": 0.25, "4h": 0.25,
}


# ─────────────────────── Open decisions (defaults locked here) ───────────────────────
# Defaults selected per reviewer guidance. Override via CLI flags on each
# stage; lock in this file once user confirms.
DEFAULT_CALIBRATION = "sigmoid"           # LOCKED 2026-05-26 on IWM 15m: sigmoid passes
                                          # gate (ECE 0.0439 vs ceiling 0.050) while
                                          # isotonic cv=3 misses by 0.001 and isotonic
                                          # cv=5 misses by 2x. Sigmoid fixes the mid-range
                                          # underconfidence the isotonic calibrator left.
DEFAULT_CORR_METRIC = "mutual_info"       # open #4 — captures nonlinear
DEFAULT_4H_SOURCE = "aggregate_from_60m"  # open #2 — simplest; "raw_intraday" also supported
DEFAULT_READOUT_FORM = "table"            # open #5 — JSON/table; "dashboard"/"pine" later


@dataclass(frozen=True)
class StratConfig:
    """Snapshot of effective config for one run. Stages stamp this into their
    output JSON so we can re-create the exact run config later."""
    tickers: Sequence[str] = TICKERS
    timeframes: Sequence[str] = TIMEFRAMES
    train_until: str = DEFAULT_TRAIN_UNTIL
    bucket: str = GCS_BUCKET_DEFAULT
    base_rate_beat_pp: float = DEFAULT_BASE_RATE_BEAT_PP
    ece_ceiling: float = DEFAULT_ECE_CEILING
    calibration: str = DEFAULT_CALIBRATION
    corr_metric: str = DEFAULT_CORR_METRIC
    four_h_source: str = DEFAULT_4H_SOURCE
    readout_form: str = DEFAULT_READOUT_FORM
