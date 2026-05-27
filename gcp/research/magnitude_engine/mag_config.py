"""Magnitude Engine — shared config.

Single source of truth for tickers, timeframes, target buckets,
ATR thresholds, phase definitions, and pre-set success bar.

The success bar is documented here AND in docs/MAGNITUDE_ENGINE_RESULTS.md
and MUST NOT be tuned after running. Per the project spec:

    "Each phase tested ONCE through the walk-forward. No tuning after
     a failed phase."
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence


# ─────────────────────── Scope ───────────────────────
# Same 3 tickers as strat_engine. 1m + 60m dropped for the same reasons
# (1m: pathological probs; 60m: too few bars per fold).
TICKERS: tuple[str, ...] = ("IWM", "SPY", "QQQ")
TIMEFRAMES: tuple[str, ...] = ("5m", "15m", "30m")
TF_MINUTES: dict[str, int] = {"5m": 5, "15m": 15, "30m": 30}

# Anchored / expanding-window cutoffs — IDENTICAL to strat_engine so cross-
# experiment comparisons stay apples-to-apples.
DEFAULT_CUTOFFS = [
    "2019-01-01",  # test 2019 (recovery)
    "2020-01-01",  # test 2020 (COVID)
    "2021-01-01",  # test 2021 (bull)
    "2022-01-01",  # test 2022 (bear)
    "2023-01-01",  # test 2023 (recovery)
    "2024-01-01",  # test 2024 (bull continuation)
    "2025-01-01",  # test 2025
    "2026-01-01",  # test Jan-May 2026 (locked OOS)
]
MIN_TEST_BARS = 200  # below this a fold is reported but excluded from gate counts


# ─────────────────────── Target ───────────────────────
# Bucketed |next_close - next_open| in ATR-20 multiples.
LABEL_COL = "magnitude_bucket"
LABEL_CLASSES: tuple[str, ...] = ("TIGHT", "NORMAL", "EXPANDED", "EXPLOSIVE")
LABEL_TO_IDX: dict[str, int] = {c: i for i, c in enumerate(LABEL_CLASSES)}

# ATR-20 multiplier thresholds. Bucket = bisect_right(THRESHOLDS, move/atr).
# move < 0.5     → TIGHT (0)
# 0.5 <= move<1.0 → NORMAL (1)
# 1.0 <= move<1.5 → EXPANDED (2)
# move >= 1.5    → EXPLOSIVE (3)
MAGNITUDE_THRESHOLDS: tuple[float, ...] = (0.5, 1.0, 1.5)


# ─────────────────────── Phases ───────────────────────
# Each phase is an additive feature set tested ONCE through walk-forward.
# Phase 0 (baseline) uses the existing 143-col enrichment as-is.
# Phase 1+ adds new features computed on-the-fly in mag_dataset.
# Phase 2+ requires backfilled tables (deferred for first dispatch).
PHASES: tuple[str, ...] = ("phase0", "phase1", "phase2", "phase3", "phase4")

# Per-phase feature additions. Phase N includes Phase N-1's features
# ONLY IF a prior phase passed. The spec says: "do not retrain Phase 0
# with later phases combined unless one of the later phases shows
# independent signal." So each phase tests its additions in isolation
# on top of the baseline.
PHASE_FEATURES: dict[str, tuple[str, ...]] = {
    "phase0": (),  # baseline 143-col only
    "phase1": (
        "atr5_atr20_ratio",        # short-term vol expansion
        "bb20_bandwidth",          # rolling vol envelope width
        "realized_vol_z15",        # 15-bar realized-vol z-score
        "range_expansion_ratio",   # cur range / avg prior-5-bar range
        "intraday_range_vs_prior_day",
    ),
    "phase2": (
        # AlphaVantage-sourced. Backfilled into market_data_indicators.
        # NOT computed locally — substitution forbidden by spec.
        "av_adx",
        "av_mfi",
        "av_chaikin_ad_osc",
        "av_aroon_up",
        "av_aroon_down",
        "av_roc",
        "av_bbands_bandwidth",
    ),
    "phase3": (
        "hours_until_next_hi_event",
        "hours_since_last_hi_event",
        "is_event_day_pm4h",       # within 4h of high-impact event
    ),
    "phase4": (
        # Cross-asset. Backfilled into market_data_cross_asset.
        "vix_5m_delta",
        "vix_z_15",
        "ust10y_delta",
        "dxy_delta",
        "oil_z",
        "gold_z",
    ),
    # Phase 5 (gamma) intentionally omitted from default config — only
    # built if Phases 0-4 hint at signal.
}


# ─────────────────────── Success bar (PRE-SET, IMMUTABLE) ───────────────────────
# Per spec: pre-set in PR description AND code BEFORE running experiments.
# Per-cell-per-phase gates:
#   1. log-loss beat positive in at least 6 of 8 walk-forward folds
#   2. ECE within ceiling on the same 6 folds
#        (0.05 for 5m + 15m; 0.075 for 30m)
#   3. confidence discriminates: decisive-call hit rate rises monotonically
#        across thresholds [0.40, 0.50, 0.60, 0.70]
#   4. top-bucket (EXPLOSIVE) lift over base rate >= 1.5 in at least 6 folds
SUCCESS_BAR_MIN_FOLDS_LOGLOSS = 6      # of 8
SUCCESS_BAR_MIN_FOLDS_ECE = 6          # of 8
SUCCESS_BAR_MIN_FOLDS_LIFT = 6         # of 8
SUCCESS_BAR_EXPLOSIVE_LIFT_MIN = 1.5
SUCCESS_BAR_CONFIDENCE_THRESHOLDS: tuple[float, ...] = (0.40, 0.50, 0.60, 0.70)

# ECE ceiling by timeframe (per spec: 0.05 for 5m + 15m, 0.075 for 30m)
ECE_CEILING_BY_TF: dict[str, float] = {
    "5m": 0.05,
    "15m": 0.05,
    "30m": 0.075,
}

# A phase PASSES if all four gates hold across at least 2 of 3 cells per TF
# (i.e. 2 of 3 tickers). Repeated for each (TF) cell-row of the 3×3 grid.
SUCCESS_BAR_MIN_PASSING_TICKERS_PER_TF = 2  # of 3


# ─────────────────────── Calibration (mirror strat_engine production) ───────────────────────
# DEFAULT_CALIBRATION = "none" — same evidence-based decision as
# strat_engine production. Raw LightGBM-softmax cross-entropy IS a
# calibration loss. We will re-check ECE on the new target; if it
# breaches the ceiling on this dataset, the per-phase report will flag
# and we can switch to "isotonic" or "sigmoid" — but ONLY after Phase 0
# results land (not pre-emptively).
DEFAULT_CALIBRATION = "none"
DEFAULT_CV = 3


# ─────────────────────── Storage ───────────────────────
GCS_BUCKET_DEFAULT = "adept-mountain-474619-d4-trading-data"
GCS_PREFIX = "research/magnitude_engine"


def gcs_run_prefix(phase: str, ticker: str, tf: str) -> str:
    return f"{GCS_PREFIX}/{phase}/{ticker.lower()}_{tf}"


# Tables for Phase 2 + 4 (NOT created by default — only when those phases
# are dispatched).
NEW_INDICATORS_TABLE = "market_data_indicators"
NEW_CROSS_ASSET_TABLE = "market_data_cross_asset"


@dataclass(frozen=True)
class MagConfig:
    """Snapshot of effective config for one walk-forward dispatch."""
    phase: str = "phase0"
    tickers: Sequence[str] = TICKERS
    timeframes: Sequence[str] = TIMEFRAMES
    cutoffs: Sequence[str] = tuple(DEFAULT_CUTOFFS)
    calibration: str = DEFAULT_CALIBRATION
    cv: int = DEFAULT_CV
