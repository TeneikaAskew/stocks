"""Phase 0.5 — hermetic tests for the signal-quality report pipeline.

No Cloud SQL, no live network. Synthetic bars and dict source rows.

Coverage:
  1. classify() — every label, including INSUFFICIENT_DATA / NaN handling
  2. classify() — boundary values exactly at CLEAN_THRESHOLD/NOISE_THRESHOLD
  3. best_clean_timeframe — picks the SHORTEST clean tf
  4. determine_status — historical always 'final'; rolling 'pending'
     when any tf missing, 'final' when all present
  5. extend_returns_from_intraday — CALL favorable = max(High); PUT = min(Low)
  6. extend_returns_from_intraday — empty bars and pre-entry bars handled
  7. compute_atr_pct — None when too few bars, fraction-of-price otherwise
  8. compute_metrics_for_signal — full pipeline on a synthetic row
  9. compute_metrics_for_signal — mfe_60m_atrs is None when ATR unavailable
 10. parse_args — required flags and defaults
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.signal_quality_report import (  # noqa: E402
    CLEAN_THRESHOLD,
    NOISE_THRESHOLD,
    best_clean_timeframe,
    classify,
    compute_atr_pct,
    compute_metrics_for_signal,
    determine_status,
    extend_returns_from_intraday,
    parse_args,
)


# ── 1) classify — every label ──────────────────────────────────────────

def test_classify_clean_hit():
    assert classify(0.010) == "CLEAN_HIT"
    assert classify(CLEAN_THRESHOLD) == "CLEAN_HIT"   # boundary


def test_classify_wrong_direction():
    assert classify(-0.010) == "WRONG_DIRECTION"
    assert classify(-CLEAN_THRESHOLD) == "WRONG_DIRECTION"  # boundary


def test_classify_noise_below_noise_threshold():
    assert classify(0.001) == "NOISE"
    assert classify(-0.001) == "NOISE"


def test_classify_mixed_between_noise_and_clean():
    """A return between NOISE_THRESHOLD and CLEAN_THRESHOLD is MIXED."""
    mid = (NOISE_THRESHOLD + CLEAN_THRESHOLD) / 2
    assert classify(mid) == "MIXED"
    assert classify(-mid) == "MIXED"


def test_classify_insufficient_data_on_none():
    assert classify(None) == "INSUFFICIENT_DATA"


def test_classify_insufficient_data_on_nan():
    assert classify(float("nan")) == "INSUFFICIENT_DATA"


# ── 2) best_clean_timeframe ────────────────────────────────────────────

def test_best_clean_timeframe_picks_shortest():
    """Multiple clean timeframes → shortest wins."""
    rets = {5: 0.001, 15: 0.010, 30: 0.012, 60: 0.020}
    assert best_clean_timeframe(rets) == "15m"


def test_best_clean_timeframe_none_clean_returns_none():
    rets = {5: 0.001, 15: 0.001, 30: -0.001, 60: 0.002}
    assert best_clean_timeframe(rets) is None


def test_best_clean_timeframe_includes_all_input_tfs():
    """Doesn't restrict to a fixed list — uses whatever keys are in the dict."""
    rets = {5: 0.001, 90: 0.010, 240: 0.015}
    assert best_clean_timeframe(rets) == "90m"


# ── 3) determine_status ────────────────────────────────────────────────

def test_determine_status_historical_always_final():
    assert determine_status({5: None, 60: None}, mode="historical") == "final"
    assert determine_status({5: 0.001}, mode="historical") == "final"


def test_determine_status_rolling_final_when_all_present():
    rets = {tf: 0.001 for tf in (5, 15, 30, 60, 90, 120, 240)}
    assert determine_status(rets, mode="rolling") == "final"


def test_determine_status_rolling_pending_on_missing():
    rets = {5: 0.001, 60: 0.002, 240: None}
    assert determine_status(rets, mode="rolling") == "pending"


def test_determine_status_rolling_pending_on_nan():
    rets = {5: 0.001, 60: float("nan")}
    assert determine_status(rets, mode="rolling") == "pending"


# ── 4) extend_returns_from_intraday ────────────────────────────────────

def _make_synthetic_intraday(entry_time: pd.Timestamp,
                             entry_price: float = 100.0,
                             bars: int = 250) -> pd.DataFrame:
    """One bar per minute starting at entry_time. Price drifts up by
    1¢/min, with each bar's High = price+0.05, Low = price-0.05."""
    times = pd.date_range(entry_time, periods=bars, freq="1min")
    closes = entry_price + np.arange(bars) * 0.01
    return pd.DataFrame({
        "Time":  times,
        "Open":  closes - 0.005,
        "High":  closes + 0.05,
        "Low":   closes - 0.05,
        "Close": closes,
    })


def test_extend_returns_call_uses_max_high():
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    bars = _make_synthetic_intraday(entry)
    out = extend_returns_from_intraday(bars, entry, entry_price=100.0, direction="CALL")
    # window_end = entry + Nm is INCLUSIVE, so bar at index N (= entry + N min) is in.
    # Bar N close = 100 + N*0.01; high = close + 0.05.
    assert out[90]  == pytest.approx((100.0 + 90 * 0.01 + 0.05 - 100.0) / 100.0, rel=1e-6)
    assert out[120] == pytest.approx((100.0 + 120 * 0.01 + 0.05 - 100.0) / 100.0, rel=1e-6)
    assert out[240] == pytest.approx((100.0 + 240 * 0.01 + 0.05 - 100.0) / 100.0, rel=1e-6)


def test_extend_returns_put_uses_min_low():
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    bars = _make_synthetic_intraday(entry)
    out = extend_returns_from_intraday(bars, entry, entry_price=100.0, direction="PUT")
    # The low at entry minute = 100 - 0.05 = 99.95 → favorable PUT excursion
    expected = (100.0 - 99.95) / 100.0
    assert out[90] == pytest.approx(expected, rel=1e-6)


def test_extend_returns_empty_intraday_returns_none_for_each_tf():
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    out = extend_returns_from_intraday(pd.DataFrame(), entry, 100.0, "CALL")
    assert out == {90: None, 120: None, 240: None}


def test_extend_returns_drops_pre_entry_bars():
    """Bars before entry_time must not influence the favorable excursion."""
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    pre = _make_synthetic_intraday(entry - timedelta(minutes=60), bars=60)
    pre["High"] = 200.0  # huge spike *before* entry — must be ignored
    post = _make_synthetic_intraday(entry, bars=250)
    bars = pd.concat([pre, post], ignore_index=True)
    out = extend_returns_from_intraday(bars, entry, 100.0, "CALL")
    # Pre-entry $200 high must NOT bleed into the result
    assert out[90] is not None
    assert out[90] < 0.05  # would be ~1.0 if pre-entry bar leaked


# ── 5) compute_atr_pct ─────────────────────────────────────────────────

def test_compute_atr_pct_returns_none_with_too_few_bars():
    bars = pd.DataFrame({
        "High":  [101] * 5,
        "Low":   [99] * 5,
        "Close": [100] * 5,
    })
    assert compute_atr_pct(bars, 100.0, period=14) is None


def test_compute_atr_pct_returns_fraction_of_price():
    bars = pd.DataFrame({
        "High":  [101.0] * 30,
        "Low":   [99.0] * 30,
        "Close": [100.0] * 30,
    })
    out = compute_atr_pct(bars, 100.0, period=14)
    # All bars have TR = 2.0; ATR = 2.0; ATR/price = 0.02
    assert out == pytest.approx(0.02, rel=1e-3)


def test_compute_atr_pct_none_on_zero_entry_price():
    bars = pd.DataFrame({"High": [101] * 30, "Low": [99] * 30, "Close": [100] * 30})
    assert compute_atr_pct(bars, 0.0) is None


# ── 6) compute_metrics_for_signal end-to-end ───────────────────────────

def test_compute_metrics_for_signal_full_pipeline():
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    intraday = _make_synthetic_intraday(entry, bars=250)
    lookback = pd.DataFrame({
        "High":  [101.0] * 30,
        "Low":   [99.0] * 30,
        "Close": [100.0] * 30,
    })
    src = {
        "ticker":         "SPY",
        "entry_time":     entry,
        "strategy":       "momentum",
        "trade_type":     "CALL",
        "entry_price":    100.0,
        "return_5min":    0.0006,    # NOISE
        "return_15min":   0.0040,    # MIXED
        "return_30min":   0.0070,    # CLEAN_HIT
        "return_60min":   0.0150,    # CLEAN_HIT
    }
    m = compute_metrics_for_signal(src, intraday=intraday,
                                    intraday_lookback=lookback, mode="historical")
    assert m.ticker == "SPY"
    assert m.strategy == "momentum"
    assert m.cls_5m == "NOISE"
    assert m.cls_15m == "MIXED"
    assert m.cls_30m == "CLEAN_HIT"
    assert m.cls_60m == "CLEAN_HIT"
    # extended timeframes: synthetic bars produce favorable returns > CLEAN_THRESHOLD
    assert m.cls_90m == "CLEAN_HIT"
    assert m.cls_240m == "CLEAN_HIT"
    assert m.best_tf == "30m"   # shortest clean
    assert m.atr_5m_pct == pytest.approx(0.02, rel=1e-3)
    # mfe_60m_atrs = 0.015 / 0.02 = 0.75
    assert m.mfe_60m_atrs == pytest.approx(0.75, rel=1e-3)
    assert m.status == "final"  # historical mode


def test_compute_metrics_for_signal_no_intraday_marks_extended_insufficient():
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    src = {
        "ticker":         "SPY",
        "entry_time":     entry,
        "strategy":       "momentum",
        "trade_type":     "CALL",
        "entry_price":    100.0,
        "return_5min":    0.001,
        "return_15min":   0.001,
        "return_30min":   0.001,
        "return_60min":   0.001,
    }
    m = compute_metrics_for_signal(src, intraday=None, intraday_lookback=None,
                                    mode="historical")
    assert m.cls_90m == "INSUFFICIENT_DATA"
    assert m.cls_120m == "INSUFFICIENT_DATA"
    assert m.cls_240m == "INSUFFICIENT_DATA"
    assert m.atr_5m_pct is None
    assert m.mfe_60m_atrs is None    # can't normalize without ATR


def test_compute_metrics_for_signal_rolling_mode_pending_when_extended_missing():
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    src = {
        "ticker": "SPY", "entry_time": entry, "strategy": "momentum",
        "trade_type": "CALL", "entry_price": 100.0,
        "return_5min": 0.001, "return_15min": 0.001,
        "return_30min": 0.001, "return_60min": 0.001,
    }
    m = compute_metrics_for_signal(src, intraday=None, intraday_lookback=None,
                                    mode="rolling")
    assert m.status == "pending"   # missing 90/120/240


def test_compute_metrics_for_signal_default_strategy_momentum():
    """Backwards-compat: rows without strategy default to 'momentum'."""
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    src = {
        "ticker": "SPY", "entry_time": entry,
        "trade_type": "CALL", "entry_price": 100.0,
        "return_5min": 0.001,
    }
    m = compute_metrics_for_signal(src, mode="historical")
    assert m.strategy == "momentum"


# ── 7) parse_args ──────────────────────────────────────────────────────

def test_parse_args_historical_requires_start_end():
    args = parse_args(["--mode", "historical", "--start", "2026-04-01", "--end", "2026-05-01"])
    assert args.mode == "historical"
    assert args.start == "2026-04-01"
    assert args.end == "2026-05-01"


def test_parse_args_rolling_default_lookback_4h():
    args = parse_args(["--mode", "rolling"])
    assert args.mode == "rolling"
    assert args.lookback_hours == 4


def test_parse_args_strategy_default_all():
    args = parse_args(["--mode", "rolling"])
    assert args.strategy == "all"


def test_parse_args_rejects_unknown_mode():
    with pytest.raises(SystemExit):
        parse_args(["--mode", "garbage"])
