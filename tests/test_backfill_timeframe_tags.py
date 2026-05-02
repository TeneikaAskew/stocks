"""Hermetic tests for the timeframe_tag backfill script.

Coverage:
  1. assign_timeframe_for_backfill — every branch of the approximate heuristic
  2. apply_tags — vectorized over a synthetic DataFrame
  3. parse_args — flag handling
  4. apply_tags handles NaN / None ATR gracefully
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.strategies.timeframe import (  # noqa: E402
    HIGH_ATR_5M_PCT,
    STRONG_CONFIRMATION,
    assign_timeframe_for_backfill,
)
from scripts.backfill_timeframe_tags import apply_tags, parse_args  # noqa: E402


# ── 1) assign_timeframe_for_backfill — every branch ──────────────────

def test_high_vol_strong_confirmation_gives_15m():
    tag, hold = assign_timeframe_for_backfill(
        strategy="momentum", signal_strength=STRONG_CONFIRMATION,
        atr_5m_pct=(HIGH_ATR_5M_PCT / 100.0) + 0.001,
    )
    assert tag == "15m"
    assert hold == 15


def test_high_vol_weak_confirmation_gives_30m():
    tag, _ = assign_timeframe_for_backfill(
        strategy="momentum", signal_strength=STRONG_CONFIRMATION - 1,
        atr_5m_pct=(HIGH_ATR_5M_PCT / 100.0) + 0.001,
    )
    assert tag == "30m"


def test_mean_reversion_at_avg_vol_gives_30m():
    tag, _ = assign_timeframe_for_backfill(
        strategy="mean_reversion", signal_strength=3, atr_5m_pct=0.002,
    )
    assert tag == "30m"


def test_momentum_at_avg_vol_gives_15m():
    tag, _ = assign_timeframe_for_backfill(
        strategy="momentum", signal_strength=3, atr_5m_pct=0.002,
    )
    assert tag == "15m"


def test_unknown_strategy_at_avg_vol_falls_through_to_30m():
    tag, _ = assign_timeframe_for_backfill(
        strategy=None, signal_strength=3, atr_5m_pct=0.002,
    )
    assert tag == "30m"


def test_no_atr_treated_as_avg_vol():
    """Missing ATR shouldn't force the high-vol branch — falls through
    to strategy-default."""
    tag, _ = assign_timeframe_for_backfill(
        strategy="momentum", signal_strength=5, atr_5m_pct=None,
    )
    assert tag == "15m"   # momentum at avg vol


def test_zero_signal_strength_doesnt_qualify_as_strong():
    tag, _ = assign_timeframe_for_backfill(
        strategy="momentum", signal_strength=0,
        atr_5m_pct=(HIGH_ATR_5M_PCT / 100.0) + 0.001,
    )
    assert tag == "30m"


def test_none_signal_strength_treated_as_zero():
    tag, _ = assign_timeframe_for_backfill(
        strategy="momentum", signal_strength=None,
        atr_5m_pct=(HIGH_ATR_5M_PCT / 100.0) + 0.001,
    )
    assert tag == "30m"


# ── 2) apply_tags — vectorized over DataFrame ────────────────────────

def test_apply_tags_populates_columns_per_row():
    df = pd.DataFrame([
        {"ticker": "SPY", "entry_time": "2026-04-29 14:30",
         "strategy": "momentum", "signal_strength": 4, "atr_5m_pct": 0.005},
        {"ticker": "QQQ", "entry_time": "2026-04-29 14:31",
         "strategy": "mean_reversion", "signal_strength": 3, "atr_5m_pct": 0.002},
    ])
    out = apply_tags(df)
    assert "timeframe_tag" in out.columns
    assert "expected_hold_min" in out.columns
    assert out["timeframe_tag"].iloc[0] == "15m"
    assert out["expected_hold_min"].iloc[0] == 15
    assert out["timeframe_tag"].iloc[1] == "30m"
    assert out["expected_hold_min"].iloc[1] == 30


def test_apply_tags_empty_df_returns_empty():
    out = apply_tags(pd.DataFrame())
    assert out.empty


def test_apply_tags_handles_nan_atr():
    """signal_metrics may not exist for some rows → atr_5m_pct comes
    back as NaN from the LEFT JOIN. Must not crash."""
    df = pd.DataFrame([
        {"ticker": "SPY", "entry_time": "2026-04-29 14:30",
         "strategy": "momentum", "signal_strength": 5, "atr_5m_pct": np.nan},
    ])
    out = apply_tags(df)
    # NaN ATR → NOT high vol, momentum strategy → 15m (default)
    assert out["timeframe_tag"].iloc[0] == "15m"


def test_apply_tags_handles_none_atr():
    df = pd.DataFrame([
        {"ticker": "SPY", "entry_time": "2026-04-29 14:30",
         "strategy": "momentum", "signal_strength": 5, "atr_5m_pct": None},
    ])
    out = apply_tags(df)
    assert out["timeframe_tag"].iloc[0] == "15m"


# ── 3) parse_args ────────────────────────────────────────────────────

def test_parse_args_defaults():
    args = parse_args([])
    assert args.tickers == ""
    assert args.limit is None
    assert args.chunk_size == 1000
    assert args.dry_run is False


def test_parse_args_with_tickers_and_limit():
    args = parse_args(["--tickers", "SPY,QQQ", "--limit", "100",
                       "--chunk-size", "50", "--dry-run"])
    assert args.tickers == "SPY,QQQ"
    assert args.limit == 100
    assert args.chunk_size == 50
    assert args.dry_run is True
