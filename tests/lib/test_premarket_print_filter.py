"""FEAT-STRAT-001 done_when 4: premarket prints.

lib.indicators.calculate_premarket_context drops, before taking pre_high,
pre_low and pre_vwap, (a) every one-minute open, high, low or close equal
to the prior session's close to the cent when that bar's open-close
midpoint is more than 0.1 x ATR(14) away from it, and (b) a bar's high or
low more than 0.5 x ATR(14) beyond both its own body and the bodies of the
two bars on each side. Fixtures: tests/fixtures/premarket_2026-11-06/*.csv
(Alpha Vantage TIME_SERIES_INTRADAY 1min, extended hours, unadjusted),
with the prior session's close and Wilder ATR(14) through 2026-11-05.

On origin/main these fail: the function takes no prev_open, returns no
exclusion counts and keeps every print (QQQ pre_low 647.05, pre_high
683.50).
"""
from __future__ import annotations

import pandas as pd
import pytest

from lib.indicators import calculate_premarket_context
from tests.lib import strat_2026_11_06 as fx

# Values computed from the committed bars (the spec's figures, except the
# QQQ spike count: QQQ drops the 08:05 high 683.50 AND the 08:32 low
# 647.535, two spikes, which is what gives the spec's own pre_low 649.62).
FILTERED = {
    #        pre_high  pre_low  prior-close prints  spikes
    "QQQ": (660.398, 649.62, 15, 2),
    "IWM": (272.50, 269.13, 3, 1),
    "SPY": (738.04, 730.64, 15, 1),
}
RAW = {
    "QQQ": (683.50, 647.05),
    "IWM": (283.745, 269.13),
    "SPY": (765.5267, 730.64),
}


@pytest.mark.parametrize("ticker", sorted(FILTERED))
def test_filtered_extremes_and_counts(ticker):
    hi, lo, n_echo, n_spike = FILTERED[ticker]
    pm = fx.premarket_context(ticker)
    assert pm["pre_high"] == pytest.approx(hi)
    assert pm["pre_low"] == pytest.approx(lo)
    assert pm["excluded_prior_close_prints"] == n_echo
    assert pm["excluded_spike_prints"] == n_spike


@pytest.mark.parametrize("ticker", sorted(RAW))
def test_raw_extremes_without_an_atr(ticker):
    """With no ATR(14) nothing is dropped: the raw extremes come back."""
    hi, lo = RAW[ticker]
    pm = fx.premarket_context(ticker, raw=True)
    assert pm["pre_high"] == pytest.approx(hi)
    assert pm["pre_low"] == pytest.approx(lo)
    assert pm["excluded_prior_close_prints"] == 0
    assert pm["excluded_spike_prints"] == 0


@pytest.mark.parametrize("ticker", sorted(FILTERED))
def test_one_0805_high_spike_per_ticker(ticker):
    """The 08:05 bar's isolated high is dropped on every ticker."""
    bars = fx.premarket_bars(ticker)
    at_0805 = bars[bars["timestamp"].dt.strftime("%H:%M") == "08:05"].iloc[0]
    pm = fx.premarket_context(ticker)
    assert pm["pre_high"] < at_0805["high"]
    assert pm["pre_high"] == pytest.approx(FILTERED[ticker][0])


def test_iwm_real_low_is_kept():
    """IWM's 04:00 low 269.13 is a real trade (not the prior close 270.98,
    not isolated), so it stays the premarket low."""
    pm = fx.premarket_context("IWM")
    assert pm["pre_low"] == pytest.approx(269.13)
    assert pm["excluded_prior_close_prints"] == 3


def test_avgo_prior_close_prints_are_never_an_extreme():
    """AVGO printed the prior close 291.53 fourteen times while trading
    near 305; none of them is the premarket low."""
    pm = fx.premarket_context("AVGO")
    assert pm["pre_low"] != pytest.approx(291.53, abs=0.005)
    assert pm["pre_low"] == pytest.approx(299.00)
    assert pm["excluded_prior_close_prints"] == 14


@pytest.mark.xfail(strict=True, reason=(
    "Data disagreement with the spec: AVGO's 08:05 high 312.00 sits 7.097 "
    "above its own body (304.50 to 304.9029) and the neighbours' bodies, "
    "under 0.5 x Wilder ATR(14) through 2026-11-05 = 7.143 (and under "
    "0.5 x SMA ATR 14.401 = 7.20), so the spec's own rule keeps it. It "
    "would be dropped only with an ATR below 14.19 (ATR through "
    "2026-11-04 is 12.666). Owner decision; not fudged."))
def test_avgo_0805_high_is_not_an_extreme():
    pm = fx.premarket_context("AVGO")
    assert pm["pre_high"] != pytest.approx(312.00)


def test_pre_vwap_drops_a_bar_with_no_surviving_price():
    """Five equal-volume bars at 100, one with a spiked high: the spike is
    removed and the bar keeps its low and close, so the typical price stays
    100 and pre_vwap is 100.00."""
    times = pd.Series(pd.date_range("2026-11-06 08:00", periods=5, freq="min"))
    o = pd.Series([100.0] * 5)
    h = pd.Series([100.0, 100.0, 110.0, 100.0, 100.0])
    lo = pd.Series([100.0] * 5)
    c = pd.Series([100.0] * 5)
    v = pd.Series([1000] * 5)
    pm = calculate_premarket_context(times, o, h, lo, c, v, prev_close=95.0, atr14=4.0)
    assert pm["excluded_spike_prints"] == 1
    assert pm["pre_high"] == pytest.approx(100.0)
    assert pm["pre_vwap"] == pytest.approx(100.00)


def test_pre_vwap_bar_with_every_price_dropped_adds_no_volume():
    """A bar whose high, low and close are all prior-close echoes drops out
    of numerator and denominator alike (origin/main counted its volume)."""
    times = pd.Series(pd.date_range("2026-11-06 08:00", periods=4, freq="min"))
    o = pd.Series([100.0, 100.0, 100.0, 100.0])
    h = pd.Series([100.0, 100.0, 95.0, 100.0])
    lo = pd.Series([100.0, 100.0, 95.0, 100.0])
    c = pd.Series([100.0, 100.0, 95.0, 100.0])
    v = pd.Series([1000, 1000, 50000, 1000])
    pm = calculate_premarket_context(times, o, h, lo, c, v, prev_close=95.0, atr14=4.0)
    assert pm["excluded_prior_close_prints"] == 3
    assert pm["pre_low"] == pytest.approx(100.0)
    assert pm["pre_vwap"] == pytest.approx(100.00)
