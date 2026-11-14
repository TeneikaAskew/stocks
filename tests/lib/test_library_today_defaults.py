"""Library defaults for "today" are the exchange's date (FEAT-DATA-001, stage 1).

These functions take an optional ``today`` / ``as_of`` and defaulted it to the
host date. Their callers run in containers whose clock is UTC, where the host
date is tomorrow from 19:00 Eastern in winter (20:00 in summer) until
midnight, so every age they computed in the evening was one day too many. A
caller that passes its own date is unaffected.

The evening instant is 2026-11-14T01:30Z, Friday 2026-11-13 20:30 EST. Each
date test also runs at the daytime instant and at the two summer instants
(Friday 2026-07-10), with its dates counted back from that day.
"""
from __future__ import annotations

from datetime import date, time, timedelta

import numpy as np
import pandas as pd
import pytest

import gcp.database as database
import lib.agents.summarizers as summarizers
import lib.data_loader as data_loader
import lib.indicators as indicators
import lib.trading_analysis as trading_analysis
from lib.strategies import calibration
from lib.strategies import exit_config_overrides as overrides
from tests.agents.test_agent_summarizers import _eod_chain_fixture
from tests.fixtures.market_clock import STANDARD_INSTANTS, freeze_market_clock

EVENING = "2026-11-14T01:30:00Z"
assert STANDARD_INSTANTS[0] == (EVENING, date(2026, 11, 13))

four_instants = pytest.mark.parametrize("instant, eastern", STANDARD_INSTANTS)


def _sessions_back(day: date, count: int) -> date:
    """*count* weekdays before *day* (every standard instant falls on a weekday)."""
    return np.busday_offset(day, -count, roll="backward").astype(date)


@four_instants
def test_chain_freshness_counts_from_the_exchange_date(monkeypatch, instant, eastern):
    freeze_market_clock(monkeypatch, instant, summarizers)
    two_back, three_back = _sessions_back(eastern, 2), _sessions_back(eastern, 3)
    if instant == EVENING:
        assert (two_back, three_back) == (date(2026, 11, 11), date(2026, 11, 10))

    # MAX_OPTIONS_STALE_TRADING_DAYS is 2: two trading days behind is fresh.
    assert summarizers.MAX_OPTIONS_STALE_TRADING_DAYS == 2
    assert summarizers._check_chain_freshness(two_back) is None
    stale = summarizers._check_chain_freshness(three_back)
    assert stale is not None and f"behind {eastern}" in stale

    # A caller that passes its own date is unaffected by the clock.
    passed = summarizers._check_chain_freshness(three_back, target_date=date(2026, 11, 20))
    assert passed is not None and "behind 2026-11-20" in passed


@four_instants
def test_gamma_levels_freshness_tier(monkeypatch, instant, eastern):
    freeze_market_clock(monkeypatch, instant, summarizers)
    chain = _eod_chain_fixture(_sessions_back(eastern, 2))

    def fake_query(sql, params=None):
        # No realtime rows; the EOD chain is two trading days old.
        return chain if "market_session = 'EOD'" in sql else pd.DataFrame()

    monkeypatch.setattr(summarizers, "_query", fake_query)
    monkeypatch.setattr(summarizers, "_query_strict", fake_query)

    # From the host's date in the evening the chain reads three days old: another tier.
    assert summarizers.classify_gamma_freshness(3) != summarizers.classify_gamma_freshness(2)

    out = summarizers.summarize_gamma_levels("SPY")

    assert out["available"] is True
    assert out["data_source"] == summarizers.classify_gamma_freshness(2)


def _daily_frame(newest: date) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(newest - timedelta(days=i)) for i in (2, 1, 0)])
    return pd.DataFrame({"Close": [1.0, 2.0, 3.0]}, index=index)


@four_instants
def test_staleness_age(monkeypatch, instant, eastern):
    freeze_market_clock(monkeypatch, instant, data_loader)
    one_day_old = _daily_frame(eastern - timedelta(days=1))
    two_days_old = _daily_frame(eastern - timedelta(days=2))
    if instant == EVENING:
        assert one_day_old.index.max().date() == date(2026, 11, 12)

    data_loader._check_staleness(one_day_old, "SPY", max_age_days=1, on_stale="error")
    with pytest.raises(RuntimeError):
        data_loader._check_staleness(two_days_old, "SPY", max_age_days=1, on_stale="error")

    # A caller that passes its own date is unaffected by the clock.
    for frame in (one_day_old, two_days_old):
        with pytest.raises(RuntimeError):
            data_loader._check_staleness(frame, "SPY", max_age_days=1, on_stale="error",
                                         today=date(2026, 12, 1))


@pytest.fixture
def one_stored_row(monkeypatch):
    """Cloud SQL "configured", and pandas.read_sql answering one stored row."""
    rows: list[dict] = []
    monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(database, "get_engine", lambda: None)
    monkeypatch.setattr(pd, "read_sql", lambda sql, engine, params=None: pd.DataFrame(rows))
    calibration._latest_calibration.cache_clear()
    overrides._latest_overrides.cache_clear()
    yield rows
    calibration._latest_calibration.cache_clear()
    overrides._latest_overrides.cache_clear()


@four_instants
def test_calibration_age(monkeypatch, one_stored_row, instant, eastern):
    freeze_market_clock(monkeypatch, instant, calibration)
    assert calibration._STALE_DAYS == 180
    # Exactly 180 days old from the exchange's date (usable); 181 from the host's in the evening.
    one_stored_row.append({
        "calibration_date": eastern - timedelta(days=180),
        "rsi_p10": 30.0, "rsi_p25": 40.0, "rsi_p50": 50.0, "rsi_p75": 60.0, "rsi_p90": 70.0,
        "lookback_days": 90, "n_bars_used": 1000, "drift_flagged": False,
    })

    row = calibration._latest_calibration("SPY")

    assert row is not None and row["calibration_date"] == eastern - timedelta(days=180)


@four_instants
def test_override_age(monkeypatch, one_stored_row, instant, eastern):
    freeze_market_clock(monkeypatch, instant, overrides)
    assert overrides._STALE_DAYS == 180
    one_stored_row.append({
        "calibration_date": eastern - timedelta(days=180),
        "call_target": 0.003, "put_target": 0.002, "call_stop": 0.00075, "put_stop": 0.00075,
        "call_time_stop": 20, "put_time_stop": 25, "consecutive_periods": 3,
        "disabled_conditions": None, "disabled_directions": None,
        "blue_sky_atr_offset": None, "notes": "test",
    })

    row = overrides._latest_overrides("SPY")

    assert row is not None and row["calibration_date"] == eastern - timedelta(days=180)


def _orb_inputs() -> pd.DataFrame:
    stamps = pd.to_datetime([
        "2026-03-02 09:30", "2026-03-02 09:33", "2026-03-02 09:35",
        "2026-03-02 09:36", "2026-03-02 10:00",
    ])
    return pd.DataFrame({
        "Time": stamps,
        "High": [10.0, 11.0, 12.0, 13.0, 14.0],
        "Low": [9.0, 9.5, 9.8, 10.0, 11.0],
        "Close": [9.5, 10.5, 11.5, 12.5, 13.5],
    })


def _both_orbs() -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = _orb_inputs()
    library = indicators.calculate_orb(frame["Time"], frame["High"], frame["Low"], frame["Close"])
    analyzer_in = frame.assign(Date=frame["Time"].dt.date, TimeOnly=frame["Time"].dt.time,
                               Last=frame["Close"])
    analyzer = trading_analysis.MarketAnalyzer()._calculate_orb(
        analyzer_in, time(9, 30), minutes=5, label="5m")
    return library, analyzer


def test_orb_end_time_does_not_depend_on_the_day(monkeypatch):
    # stdlib=True: MarketAnalyzer._calculate_orb imports datetime inside itself.
    freeze_market_clock(monkeypatch, EVENING, indicators, trading_analysis, stdlib=True)
    winter = _both_orbs()
    freeze_market_clock(monkeypatch, "2026-07-10T15:00:00Z", indicators, trading_analysis, stdlib=True)
    summer = _both_orbs()

    for first, second in zip(winter, summer):
        pd.testing.assert_frame_equal(first, second)
    # The 09:35 bar is the last one inside the five-minute opening range.
    assert winter[0]["ORB_5m_High"].iloc[0] == 12.0
    assert winter[1]["ORB_5m_High"].iloc[0] == 12.0
