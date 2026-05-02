"""Phase 0.5 #9 — indicator-sharing audit.

Two indicator code paths exist in this repo:

  1. `lib.indicators` (module-level functions) — what `gcp/signal_monitor.py`
     uses for the live rolling window: `calculate_rsi`, `calculate_ema`,
     `calculate_atr`, `calculate_vwap`, `calculate_stoch_rsi`,
     `calculate_rvol`.

  2. `lib.trading_analysis.MarketAnalyzer` (instance methods) — what the
     research pipeline (`scripts/run_historical_signals.py` →
     `MarketAnalyzer.add_technical_indicators`) uses for batch backfills.

Both paths SHOULD produce numerically equivalent indicator values for
the same input bars. The Phase 0.5 spec item #9 ("indicator-sharing
audit") flagged that NEITHER path delegates to the other, so they can
silently drift — a refactor in one place wouldn't break the other's
tests, and a `signal_alerts` row written by the live monitor wouldn't
match the `historical_signals` row the research path would have
written from the same bars.

This test pins the equivalence with a deterministic 100-bar fixture
so any drift is caught before it reaches production. If a future
refactor INTENTIONALLY changes the math in one path, this test must
be updated to assert the new tolerance.

Tolerance: 1e-9 absolute. The math is identical-by-design (Wilder
smoothing, standard EMA, classic VWAP) so there should be no
floating-point drift at all on small fixtures.
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

from lib.indicators import (  # noqa: E402
    calculate_atr as lib_atr,
    calculate_ema as lib_ema,
    calculate_rsi as lib_rsi,
    calculate_stoch_rsi as lib_stoch_rsi,
    calculate_vwap as lib_vwap,
)
from lib.trading_analysis import MarketAnalyzer  # noqa: E402


# Indicator fixture — deterministic bars so values can be cross-
# referenced if a regression appears.
def _make_bars(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """100 1-min bars across two trading days so VWAP gets exercised
    against its session-reset behavior."""
    rng = np.random.default_rng(seed)
    closes = 100.0 + np.cumsum(rng.normal(0, 0.10, size=n))
    highs = closes + np.abs(rng.normal(0, 0.05, size=n))
    lows = closes - np.abs(rng.normal(0, 0.05, size=n))
    volumes = rng.integers(1_000, 5_000, size=n).astype(int)

    # Span two dates so VWAP's per-day reset is exercised.
    half = n // 2
    times = (
        list(pd.date_range("2026-04-29 09:30", periods=half, freq="1min"))
        + list(pd.date_range("2026-04-30 09:30", periods=n - half, freq="1min"))
    )
    return pd.DataFrame({
        "Time":   times,
        "Open":   np.roll(closes, 1).clip(min=0.01),
        "High":   highs,
        "Low":    lows,
        "Last":   closes,
        "Close":  closes,
        "Volume": volumes,
    })


# ── ATR ───────────────────────────────────────────────────────────────

def test_atr_matches_between_module_and_market_analyzer():
    """`MarketAnalyzer.calculate_atr` and `lib.indicators.calculate_atr`
    must produce identical Wilder-smoothed ATR for the same bars."""
    bars = _make_bars()
    ma = MarketAnalyzer()
    ma_atr = ma.calculate_atr(bars, period=14)
    lib_out = lib_atr(bars["High"], bars["Low"], bars["Last"], period=14)

    # Drop the warmup NaNs and compare the rest.
    common = ma_atr.dropna().index.intersection(lib_out.dropna().index)
    assert len(common) > 0, "both should have non-NaN values past the warmup window"
    np.testing.assert_allclose(
        ma_atr.loc[common].values,
        lib_out.loc[common].values,
        atol=1e-9,
        err_msg="ATR drift between MarketAnalyzer and lib.indicators",
    )


# ── RSI ───────────────────────────────────────────────────────────────

def test_rsi_matches_between_module_and_market_analyzer():
    bars = _make_bars()
    ma = MarketAnalyzer()
    ma_rsi = ma.calculate_rsi(bars["Last"], period=14)
    lib_out = lib_rsi(bars["Last"], period=14)

    common = ma_rsi.dropna().index.intersection(lib_out.dropna().index)
    assert len(common) > 0
    np.testing.assert_allclose(
        ma_rsi.loc[common].values,
        lib_out.loc[common].values,
        atol=1e-9,
        err_msg="RSI drift between MarketAnalyzer and lib.indicators",
    )


# ── EMA ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("period", [9, 20])
def test_ema_matches_between_module_and_market_analyzer(period):
    """EMA9 and EMA20 — both used by the live monitor's strategy logic."""
    bars = _make_bars()
    ma = MarketAnalyzer()
    ma_ema = ma.calculate_ema(bars["Last"], period=period)
    lib_out = lib_ema(bars["Last"], period=period)

    common = ma_ema.dropna().index.intersection(lib_out.dropna().index)
    assert len(common) > 0
    np.testing.assert_allclose(
        ma_ema.loc[common].values,
        lib_out.loc[common].values,
        atol=1e-9,
        err_msg=f"EMA{period} drift between MarketAnalyzer and lib.indicators",
    )


# ── VWAP ──────────────────────────────────────────────────────────────

def test_vwap_matches_between_module_and_market_analyzer():
    """VWAP resets per session — the test fixture spans two days so the
    reset logic is exercised."""
    bars = _make_bars()
    ma = MarketAnalyzer()
    ma_vwap = ma.calculate_vwap(bars)
    # lib.indicators VWAP signature takes high, low, close, volume, dates
    dates = pd.to_datetime(bars["Time"]).dt.date
    lib_out = lib_vwap(bars["High"], bars["Low"], bars["Last"],
                       bars["Volume"], dates)

    np.testing.assert_allclose(
        ma_vwap.values,
        lib_out.values,
        atol=1e-9,
        err_msg="VWAP drift between MarketAnalyzer and lib.indicators",
    )


# ── StochRSI ──────────────────────────────────────────────────────────

def test_stoch_rsi_matches_between_module_and_market_analyzer():
    """StochRSI consumes RSI as input. We use the same RSI series for
    both paths so we're comparing the StochRSI math, not transitively
    re-asserting RSI parity (already covered above)."""
    bars = _make_bars()
    ma = MarketAnalyzer()
    rsi = lib_rsi(bars["Last"], period=14)

    ma_k, ma_d = ma.calculate_stoch_rsi(rsi)
    lib_k, lib_d = lib_stoch_rsi(rsi)

    common = ma_k.dropna().index.intersection(lib_k.dropna().index)
    if len(common) == 0:
        pytest.skip("Both StochRSI implementations produced all-NaN "
                    "for the synthetic fixture (warmup window too short)")
    np.testing.assert_allclose(
        ma_k.loc[common].values,
        lib_k.loc[common].values,
        atol=1e-9,
        err_msg="StochRSI %K drift between MarketAnalyzer and lib.indicators",
    )


# ── Sanity: the fixture itself exercises both warmup and post-warmup ─

def test_fixture_has_enough_bars_for_meaningful_comparison():
    """Defensive: if the fixture shrinks below the warmup window, the
    parity tests above silently pass on near-empty common indexes."""
    bars = _make_bars()
    assert len(bars) >= 30, "fixture must exceed the 14-bar Wilder warmup"
    # Two distinct dates ensures VWAP's session-reset is exercised
    assert pd.to_datetime(bars["Time"]).dt.date.nunique() >= 2
