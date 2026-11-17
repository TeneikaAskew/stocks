"""FEAT-STRAT-001 spec revision 2: the premarket print filter on the
committed 2026-11-06 bars with the production calibration in force that
day (tests/fixtures/level_params_2026-11-06.json, written by the
calibration job in history mode from production bars; pm_spike_atr learns
from premarket wicks, method premarket_wick_excess_quantile).

The 08:05 isolated high is dropped on every ticker with the calibrated
thresholds, as it is at the #1753 constants. QQQ's 08:32 low 647.535
sits less than QQQ's calibrated 1.07 x ATR beyond the bodies around it,
so the calibrated filter keeps it where the 0.5 constant dropped it.
"""
from __future__ import annotations

from datetime import date

import pytest

from lib.strat_levels import load_level_params
from tests.lib import strat_2026_11_06 as fx
from tests.lib.level_params_fixtures import calibrated_db

TICKERS = ("SPY", "QQQ", "IWM")
# pre_high, pre_low, prior-close prints, spikes (computed from the committed
# bars and the committed calibration)
CALIBRATED = {
    "SPY": (738.04, 730.64, 16, 1),
    "QQQ": (660.398, 647.535, 15, 1),
    "IWM": (272.50, 269.13, 9, 1),
}
# The extremes above are what rules (a) and (b) give (confirmed.raw_high and
# raw_low). Each was one bar's lone wick, so under the confirmed rule
# (FEAT-PLAYBOOK-001 B7) pre_high and pre_low are the next bar's:
#   SPY 04:36 high 738.04 -> 737.9285 (04:40); 04:04 low 730.64 -> 730.70 (04:01, 04:05).
#   QQQ 04:36 high 660.398 -> 660.29 (04:37); 08:32 low 647.535 -> 649.62 (04:04).
#   IWM 08:29 high 272.50 -> 272.41 (08:28); 04:01 low 269.13 -> 269.36 (04:04).
CONFIRMED = {
    "SPY": (737.9285, 730.70),
    "QQQ": (660.29, 649.62),
    "IWM": (272.41, 269.36),
}


@pytest.fixture(scope="module")
def params():
    db = calibrated_db()
    return load_level_params(db.query, list(TICKERS), fx.SESSION)


@pytest.mark.parametrize("ticker", TICKERS)
def test_spike_threshold_is_the_premarket_wick_calibration(params, ticker):
    p = params[ticker]
    assert p.ok("pm_spike_atr") and p.ok("pm_stale_print_atr")
    assert p.params["pm_spike_atr"].method_id == "premarket_wick_excess_quantile"
    assert p.params["pm_spike_atr"].sample_n >= 40


@pytest.mark.parametrize("ticker", TICKERS)
def test_calibrated_filter_on_the_2026_11_06_bars(params, ticker):
    hi, lo, n_echo, n_spike = CALIBRATED[ticker]
    pm = fx.premarket_context(ticker, params=params[ticker])
    assert pm["filtered"] is True
    assert pm["confirmed"]["raw_high"] == pytest.approx(hi)
    assert pm["confirmed"]["raw_low"] == pytest.approx(lo)
    assert pm["pre_high"] == pytest.approx(CONFIRMED[ticker][0])
    assert pm["pre_low"] == pytest.approx(CONFIRMED[ticker][1])
    assert pm["excluded_prior_close_prints"] == n_echo
    assert pm["excluded_spike_prints"] == n_spike


@pytest.mark.parametrize("ticker", TICKERS)
def test_calibrated_filter_drops_the_0805_high(params, ticker):
    bars = fx.premarket_bars(ticker)
    at_0805 = bars[bars["timestamp"].dt.strftime("%H:%M") == "08:05"].iloc[0]
    pm = fx.premarket_context(ticker, params=params[ticker])
    assert pm["pre_high"] < at_0805["high"]


def test_insufficient_history_keys_stay_unavailable(params):
    """SPY's aggressive and conservative stops have too few samples; the
    loader reports them not ok rather than a value."""
    spy = params["SPY"]
    assert not spy.ok("stop_aggressive_atr")
    assert not spy.ok("stop_conservative_atr")
    assert spy.ok("stop_neutral_atr")


def test_calibrated_filter_keeps_spy_0404_and_drops_qqq_prior_close_prints(params):
    """done_when 5: SPY's 04:04 bar (close 731.28, low 730.64) is a real
    trade and rules (a) and (b) keep it (confirmed.raw_low); QQQ's prints at
    the prior close 647.05 never set an extreme. Under the confirmed rule
    (FEAT-PLAYBOOK-001 B7) the 04:04 low is one bar's lone wick, so pre_low
    is 730.70, which 04:01 and 04:05 both reach."""
    spy = fx.premarket_context("SPY", params=params["SPY"])
    bars = fx.premarket_bars("SPY")
    at_0404 = bars[bars["timestamp"].dt.strftime("%H:%M") == "04:04"].iloc[0]
    assert at_0404["close"] == pytest.approx(731.28)
    assert spy["confirmed"]["raw_low"] == pytest.approx(at_0404["low"])
    assert spy["pre_low"] == pytest.approx(730.70)
    qqq = fx.premarket_context("QQQ", params=params["QQQ"])
    assert qqq["pre_low"] != pytest.approx(647.05, abs=0.005)
    assert qqq["excluded_prior_close_prints"] > 0
