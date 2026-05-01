"""Unit tests for scripts/calibrate_thresholds.py.

These tests are hermetic — they don't hit Cloud SQL. They:

1. Feed synthetic 1-min bars with known statistics into the helpers
   (compute_atr_pct, compute_rsi, compute_rvol, resample_to_tf) and
   assert the outputs match expected values.
2. Run the full calibrate_ticker() pipeline on synthetic data and
   verify the produced row has every required column populated, with
   thresholds derived correctly from ATR.

This catches regressions in the calibration math BEFORE the quarterly
Cloud Run Job runs in production.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from scripts.calibrate_thresholds import (
    CLEAN_ATR_MULT,
    NOISE_ATR_MULT,
    TIMEFRAMES_MIN,
    WRONG_ATR_MULT,
    calibrate_ticker,
    compute_atr_pct,
    compute_rsi,
    compute_rvol,
    resample_to_tf,
)


# ── Synthetic-bar fixtures ──────────────────────────────────────────────

def synthetic_bars(
    n: int = 1500,
    base_price: float = 100.0,
    daily_vol_pct: float = 0.5,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate n synthetic 1-min OHLCV bars with controlled volatility."""
    rng = np.random.default_rng(seed)
    # Random-walk close
    returns = rng.normal(0, daily_vol_pct / 100 / np.sqrt(390), size=n)
    closes = base_price * np.cumprod(1 + returns)
    # Highs and lows wrapped around close with modest noise
    spreads = np.abs(rng.normal(0, daily_vol_pct / 100 * 0.3, size=n)) * closes
    highs = closes + spreads * 0.6
    lows  = closes - spreads * 0.4
    opens = np.roll(closes, 1)
    opens[0] = base_price
    volumes = rng.integers(1000, 10000, size=n).astype(np.int64)

    start = datetime(2026, 4, 1, 13, 30, tzinfo=timezone.utc)
    ts = [start + timedelta(minutes=i) for i in range(n)]
    return pd.DataFrame({
        "ts": ts, "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    })


# ── compute_atr_pct ─────────────────────────────────────────────────────

def test_atr_pct_returns_empty_when_too_few_bars():
    bars = synthetic_bars(n=10)
    out = compute_atr_pct(bars, period=14)
    assert out.empty


def test_atr_pct_warmup_observed():
    """The first several bars should be NaN during the rolling-window
    warmup; well past warmup, values should be valid."""
    bars = synthetic_bars(n=200)
    out = compute_atr_pct(bars, period=14)
    # First few bars NaN (warmup of rolling-14 + the c.shift(1) NaN)
    assert out.iloc[:13].isna().all(), "first 13 bars should be NaN during warmup"
    # Well past warmup, plenty of valid values
    assert out.iloc[20:].notna().sum() > 100


def test_atr_pct_scales_with_volatility():
    """High-vol bars should produce a higher ATR than low-vol bars."""
    low_vol  = synthetic_bars(n=500, daily_vol_pct=0.3)
    high_vol = synthetic_bars(n=500, daily_vol_pct=2.0)
    atr_low  = float(compute_atr_pct(low_vol).dropna().median())
    atr_high = float(compute_atr_pct(high_vol).dropna().median())
    assert atr_high > atr_low * 2, (
        f"high-vol ATR ({atr_high:.4f}%) should be at least 2× low-vol ATR ({atr_low:.4f}%)"
    )


# ── compute_rsi ─────────────────────────────────────────────────────────

def test_rsi_returns_in_range():
    bars = synthetic_bars(n=500)
    rsi = compute_rsi(bars["close"]).dropna()
    assert rsi.min() >= 0
    assert rsi.max() <= 100


def test_rsi_for_strongly_rising_close_approaches_100():
    """A strongly-rising series (with tiny noise so loss > 0) should
    push Wilder RSI very high. Threshold >80; real-market signals
    rarely exceed 90 even on momentum rallies."""
    rng = np.random.default_rng(0)
    base = np.linspace(100, 200, 500)
    noise = rng.normal(0, 0.05, size=500)  # tiny chop so loss != 0
    closes = pd.Series(base + noise)
    rsi = compute_rsi(closes).dropna()
    assert len(rsi) > 0, "RSI should have non-NaN values on a noisy series"
    assert rsi.iloc[-1] > 80, (
        f"RSI on strongly-rising series should be >80, got {rsi.iloc[-1]:.2f}"
    )


def test_rsi_for_strongly_falling_close_approaches_0():
    """Mirror of the rising test."""
    rng = np.random.default_rng(1)
    base = np.linspace(200, 100, 500)
    noise = rng.normal(0, 0.05, size=500)
    closes = pd.Series(base + noise)
    rsi = compute_rsi(closes).dropna()
    assert len(rsi) > 0
    assert rsi.iloc[-1] < 20, (
        f"RSI on strongly-falling series should be <20, got {rsi.iloc[-1]:.2f}"
    )


# ── compute_rvol ────────────────────────────────────────────────────────

def test_rvol_centered_around_1_for_uniform_volume():
    """Volume drawn from the same distribution should have RVOL median ≈ 1."""
    rng = np.random.default_rng(0)
    vol = pd.Series(rng.integers(1000, 10000, size=500))
    rvol = compute_rvol(vol, period=20).dropna()
    assert 0.85 < float(rvol.median()) < 1.15, (
        f"RVOL median should be near 1.0 for stationary volume, got {rvol.median():.3f}"
    )


# ── resample_to_tf ─────────────────────────────────────────────────────

def test_resample_5m_groups_5_bars_into_1():
    bars = synthetic_bars(n=100)  # 100 1-min bars
    out = resample_to_tf(bars, 5)
    # ~100/5 = 20 5-min bars (give or take edge effects)
    assert 18 <= len(out) <= 22, f"5-min resample of 100 1-min bars should produce ~20 rows, got {len(out)}"
    # OHLC integrity
    assert (out["high"] >= out["low"]).all()
    assert (out["high"] >= out["close"]).all()
    assert (out["high"] >= out["open"]).all()


def test_resample_60m_volume_is_sum_not_average():
    """Resampled total volume across all hourly bars should equal
    the total volume across all 1-min bars (volume is conserved under
    sum-aggregation)."""
    bars = synthetic_bars(n=120)
    out = resample_to_tf(bars, 60)
    expected_total = bars["volume"].sum()
    actual_total = out["volume"].sum()
    # Edge bars at boundaries may shift slightly under closed='right' so
    # check totals match within a 5% tolerance (which would catch a
    # mean vs sum bug — that'd be a 60× difference, not 5%).
    assert abs(actual_total - expected_total) / expected_total < 0.05, (
        f"resampled volume total ({actual_total}) should be ~equal to "
        f"raw volume total ({expected_total}); large diff = mean instead of sum"
    )
    # And: sum-aggregation produces values 30-100× larger than mean would
    if len(out) > 0:
        assert out["volume"].iloc[0] > bars["volume"].mean() * 5, (
            "resampled bar volume should be much larger than 1-min average"
        )


# ── calibrate_ticker (end-to-end on synthetic data) ─────────────────────

def test_calibrate_ticker_produces_required_columns():
    bars = synthetic_bars(n=2000)
    cal = calibrate_ticker("TEST", bars, lookback_days=60)

    required = {"ticker", "calibration_date", "lookback_days", "n_bars_used",
                "earliest_bar_date", "latest_bar_date",
                "threshold_clean", "threshold_wrong", "threshold_noise",
                "rvol_min", "rvol_max", "atr_expansion_x",
                "rvol_p25", "rvol_p50", "rvol_p75", "rvol_p95",
                "rsi_p10", "rsi_p25", "rsi_p50", "rsi_p75", "rsi_p90"}
    for tf in TIMEFRAMES_MIN:
        required.add(f"atr_{tf}_median")
    missing = required - set(cal.keys())
    assert not missing, f"calibrate_ticker missing required keys: {missing}"


def test_calibrate_ticker_thresholds_are_atr_multiplied():
    """clean threshold per timeframe must equal ATR × CLEAN_ATR_MULT."""
    bars = synthetic_bars(n=2000)
    cal = calibrate_ticker("TEST", bars, lookback_days=60)

    clean = json.loads(cal["threshold_clean"])
    wrong = json.loads(cal["threshold_wrong"])
    noise = json.loads(cal["threshold_noise"])

    for tf in clean:
        atr = cal[f"atr_{tf}_median"]
        assert atr is not None
        # Clean threshold = ATR × CLEAN_ATR_MULT
        assert clean[tf] == pytest.approx(atr * CLEAN_ATR_MULT, abs=1e-3), (
            f"{tf} clean threshold {clean[tf]} should equal atr_{tf}={atr} × {CLEAN_ATR_MULT}"
        )
        # Wrong threshold is signed negative
        assert wrong[tf] < 0
        assert wrong[tf] == pytest.approx(-atr * WRONG_ATR_MULT, abs=1e-3)
        # Noise threshold (smaller than clean)
        assert noise[tf] == pytest.approx(atr * NOISE_ATR_MULT, abs=1e-3)
        assert noise[tf] < clean[tf]


def test_calibrate_ticker_rvol_band_is_subset_of_distribution():
    bars = synthetic_bars(n=2000)
    cal = calibrate_ticker("TEST", bars, lookback_days=60)

    assert cal["rvol_min"] >= cal["rvol_p25"] - 0.01, (
        f"rvol_min ({cal['rvol_min']}) should be near or below P25 ({cal['rvol_p25']})"
    )
    assert cal["rvol_max"] <= cal["rvol_p95"] + 0.01, (
        f"rvol_max ({cal['rvol_max']}) should be near or below P95 ({cal['rvol_p95']})"
    )
    assert cal["rvol_min"] < cal["rvol_max"]


def test_high_vol_ticker_has_higher_thresholds_than_low_vol_ticker():
    """A volatile ticker should get LOOSER thresholds than a calm one
    — that's the whole point of per-ticker calibration."""
    low_vol  = synthetic_bars(n=2000, daily_vol_pct=0.3, seed=1)
    high_vol = synthetic_bars(n=2000, daily_vol_pct=2.0, seed=2)
    cal_low  = calibrate_ticker("LOW",  low_vol,  60)
    cal_high = calibrate_ticker("HIGH", high_vol, 60)

    clean_low  = json.loads(cal_low["threshold_clean"])
    clean_high = json.loads(cal_high["threshold_clean"])
    for tf in clean_low:
        assert clean_high[tf] > clean_low[tf] * 2, (
            f"{tf}: high-vol ticker's clean threshold ({clean_high[tf]}) should be "
            f"≥ 2× low-vol ticker's ({clean_low[tf]}) — proves calibration is per-ticker"
        )


def test_calibrate_ticker_returns_empty_for_empty_bars():
    cal = calibrate_ticker("EMPTY", pd.DataFrame(columns=["ts","open","high","low","close","volume"]), 60)
    assert cal == {}, "empty bars should produce empty calibration dict (skip, not crash)"
