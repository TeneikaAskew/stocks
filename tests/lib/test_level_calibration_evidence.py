"""FEAT-STRAT-001 per-ticker params, done_when 4 and 5 (the offline part):
the evidence rows the implementation PR shows beside each calibrated value.

* window_exceedance_by_year: per year, the share of sessions whose excursion
  from the prior close passed the trigger window.
* premarket_drops: every premarket print each threshold drops, through the
  production filter (lib.indicators.premarket_print_filter, the rule
  calculate_premarket_context applies). On the committed 2026-11-06 Alpha
  Vantage fixtures with the #1753 thresholds it lists the 08:05 prints
  (SPY 765.5267, QQQ 683.50, IWM 283.745) and QQQ's prior-close prints at
  647.05, keeps SPY's 04:04 close 731.28 and IWM's 269.13 low, and its
  counts are calculate_premarket_context's own excluded counts.
* break_counts_by_year: the break counts per side and year.

The 2015-01-02 to 2026-11-06 figures need production bars; these tests pin
the functions that produce them. On origin/main and the #1753 head neither
lib.level_calibration nor premarket_print_filter exists.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from lib.indicators import premarket_print_filter
from lib.level_calibration import (
    Break, break_counts_by_year, premarket_drops, window_exceedance_by_year,
)
from tests.lib import strat_2026_11_06 as fx
from tests.lib.level_params_fixtures import LEGACY_1753_VALUES

STALE = LEGACY_1753_VALUES["pm_stale_print_atr"]
SPIKE = LEGACY_1753_VALUES["pm_spike_atr"]


def _daily_with_atr(ticker):
    d = fx.daily(ticker, through=fx.PRIOR)
    return d.assign(atr_14=fx.wilder_atr(d))


def _drops(ticker, stale=STALE, spike=SPIKE):
    return premarket_drops(_daily_with_atr(ticker), fx.premarket_bars(ticker), "atr_14",
                           [fx.SESSION], stale_print_atr=stale, spike_atr=spike)


def test_window_exceedance_by_year_counts_sessions_past_the_window():
    days = pd.bdate_range("2024-12-23", "2025-01-10")
    high = np.full(len(days), 100.5)
    high[3] = 103.0            # 2024-12-26: 3.0 ATR, past 2.5
    high[8] = 102.5            # 2025-01-02: 2.5 ATR, on the window, not past it
    high[10] = 104.0           # 2025-01-06: 4.0 ATR
    daily = pd.DataFrame({"date": days, "open": 100.0, "high": high, "low": 99.5,
                          "close": 100.0, "atr_14": 1.0})
    got = window_exceedance_by_year(daily, "atr_14", date(2025, 1, 11), "long", 2.5)
    # The first session has no prior close; 2024 keeps 6 sessions, 2025 8.
    assert got["year"].tolist() == [2024, 2025]
    assert got["sessions"].tolist() == [6, 8] and got["passed"].tolist() == [1, 1]
    assert got["share"].tolist() == pytest.approx([1 / 6, 1 / 8])
    # Bars on or after as_of are not read.
    cut = window_exceedance_by_year(daily, "atr_14", date(2025, 1, 6), "long", 2.5)
    assert cut["passed"].tolist() == [1, 0] and cut["sessions"].tolist() == [6, 3]
    short = window_exceedance_by_year(daily, "atr_14", date(2025, 1, 11), "short", 2.5)
    assert short["passed"].sum() == 0


@pytest.mark.parametrize("ticker", ["SPY", "QQQ", "IWM"])
def test_premarket_drops_are_the_production_filters_own(ticker):
    drops = _drops(ticker)
    pm = fx.premarket_context(ticker)
    assert (drops["rule"] == "stale_prior_close").sum() == pm["excluded_prior_close_prints"]
    assert (drops["rule"] == "spike").sum() == pm["excluded_spike_prints"]
    assert set(drops["session"]) == {fx.SESSION}


def test_premarket_drops_list_the_bad_prints_and_keep_the_real_ones():
    by = {t: _drops(t) for t in ("SPY", "QQQ", "IWM")}
    for t, price in (("SPY", 765.5267), ("QQQ", 683.50), ("IWM", 283.745)):
        spikes = by[t][(by[t]["rule"] == "spike") & (by[t]["field"] == "high")]
        hit = spikes[np.isclose(spikes["price"], price)]
        assert len(hit) == 1 and hit["timestamp"].iloc[0].strftime("%H:%M") == "08:05"
    qqq_stale = by["QQQ"][by["QQQ"]["rule"] == "stale_prior_close"]
    assert len(qqq_stale) and set(qqq_stale["price"].round(2)) == {647.05}
    assert not (np.isclose(by["SPY"]["price"], 731.28)
                & (by["SPY"]["timestamp"].dt.strftime("%H:%M") == "04:04")).any()
    assert not ((by["IWM"]["field"] == "low") & np.isclose(by["IWM"]["price"], 269.13)).any()


def test_premarket_drops_follow_the_thresholds():
    loose = _drops("QQQ", stale=STALE, spike=SPIKE * 10)
    assert (loose["rule"] == "spike").sum() == 0
    assert (loose["rule"] == "stale_prior_close").sum() == (_drops("QQQ")["rule"] == "stale_prior_close").sum()
    assert _drops("QQQ", stale=None, spike=SPIKE).empty


def test_premarket_print_filter_drops_nothing_without_thresholds():
    bars = fx.premarket_bars("SPY")
    f = premarket_print_filter(bars["open"], bars["high"], bars["low"], bars["close"],
                               prev_close=731.0, atr=fx.prior_atr("SPY"),
                               stale_print_atr=None, spike_atr=SPIKE)
    assert f["filtered"] is False
    assert not any(m.any() for m in f["stale"].values())
    assert not any(m.any() for m in f["spike"].values())
    pd.testing.assert_series_equal(f["high"], bars["high"])


def test_break_counts_by_year_per_side():
    def brk(day, side, held):
        return Break(session=pd.Timestamp(day), side=side, trigger=100.0, atr=1.0, held=held,
                     bars=pd.DataFrame())

    got = break_counts_by_year([
        brk("2025-03-03", "long", True), brk("2025-03-04", "long", False),
        brk("2025-06-02", "short", True), brk("2026-01-05", "long", True),
    ])
    assert got.to_dict("records") == [
        {"side": "long", "year": 2025, "breaks": 2, "held": 1},
        {"side": "long", "year": 2026, "breaks": 1, "held": 1},
        {"side": "short", "year": 2025, "breaks": 1, "held": 1},
    ]
