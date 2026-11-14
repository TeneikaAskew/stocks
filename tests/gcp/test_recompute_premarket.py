"""The premarket columns of market_data_daily, computed in one function and
recomputed from stored bars (FEAT-DATA-001): `premarket_snapshot` and the
--recompute-premarket mode of gcp/fetchers/fetch_market_data.py.

Hermetic: every read is answered in the test and nothing reaches a vendor.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone

import numpy as np
import pandas as pd
import pytest

import gcp.database as database
from gcp.fetchers import fetch_market_data as fmd
from tests.lib.level_params_fixtures import legacy_db

UTC = timezone.utc
READ_AT = datetime(2026, 11, 14, 12, 0, 0, 123456, tzinfo=UTC)
PRIOR = {"close": 99.0, "open": 99.0, "atr_14": 2.0, "atr_5": 2.0}


def premarket_bars(day: date, inserted: str = "2026-11-14") -> pd.DataFrame:
    """330 bars, 04:00 to 09:29 Eastern: open 100.0, high 100.5, low 99.5,
    close 100.0, volume 1000."""
    from lib.eastern_time import eastern_bounds_utc

    start, end = eastern_bounds_utc(day, time(4), time(9, 30))
    ts = pd.date_range(start, end, freq="1min", inclusive="left")
    return pd.DataFrame({
        "ts": ts, "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0,
        "volume": 1000, "inserted_at": pd.Timestamp(inserted, tz="UTC"),
    })


def daily_history(last: date, sessions: int = 40) -> pd.DataFrame:
    """Business days ending on *last*: open 99.0, high 100.0, low 98.0,
    close 99.0, so every true range is 2.0."""
    days = pd.bdate_range(end=last, periods=sessions)
    return pd.DataFrame({
        "date": [d.date() for d in days], "Open": 99.0, "High": 100.0, "Low": 98.0,
        "Close": 99.0, "Volume": 1_000_000,
    })


# ── one function for the computation ──────────────────────────────────


def test_the_snapshot_is_the_one_place(monkeypatch):
    from lib.strat_levels import premarket_filter_inputs

    day = date(2026, 10, 6)
    params = legacy_db(("SPY", "QQQ")).load(["SPY", "QQQ"], day)["SPY"]
    snapshot = fmd.premarket_snapshot("SPY", day, premarket_bars(day), PRIOR, params, READ_AT)

    assert list(snapshot) == list(fmd.PREMARKET_COLUMNS)
    assert snapshot == {
        "pre_high": 100.5,
        "pre_low": 99.5,
        "pre_vwap": 100.0,
        "pre_volume": 330000,
        "gap_pct": 1.0101,
        "pre_range_atr": 0.5,
        "pre_fetched_at": READ_AT,
        "pre_excluded_stale_prints": 0,
        "pre_excluded_spikes": 0,
        "pre_filter_status": "ok",
        "pre_filter_params": premarket_filter_inputs(
            params, {"atr_14": 2.0, "atr_5": 2.0})["params"],
    }

    # A session before the ticker's first parameter row: unfiltered, and it says so.
    early = date(2026, 9, 24)
    later_params = legacy_db(("SPY", "QQQ"), effective_from=date(2026, 10, 1)).load(
        ["SPY", "QQQ"], early)["SPY"]
    unfiltered = fmd.premarket_snapshot(
        "SPY", early, premarket_bars(early), PRIOR, later_params, READ_AT)
    assert unfiltered["pre_filter_status"] == "params_unavailable"
    assert unfiltered["pre_range_atr"] is None
    assert unfiltered["pre_excluded_stale_prints"] is None
    assert unfiltered["pre_excluded_spikes"] is None
    assert [unfiltered[c] for c in ("pre_high", "pre_low", "pre_vwap", "pre_volume",
                                    "gap_pct")] == [100.5, 99.5, 100.0, 330000, 1.0101]
    assert unfiltered["pre_fetched_at"] == READ_AT

    # The run could not read the parameter tables: what the nightly records.
    unread = fmd.premarket_snapshot("SPY", day, premarket_bars(day), PRIOR, None, READ_AT)
    assert unread["pre_filter_status"] == "level_params_unavailable"
    assert unread["pre_filter_params"] is None

    empty = premarket_bars(day).iloc[0:0]
    assert fmd.premarket_snapshot("SPY", day, empty, PRIOR, params, READ_AT) is None

    # Bars outside the premarket window only: no snapshot.
    session_only = premarket_bars(day)
    session_only["ts"] = session_only["ts"] + pd.Timedelta(hours=6)
    assert fmd.premarket_snapshot("SPY", day, session_only, PRIOR, params, READ_AT) is None

    import lib.indicators as indicators

    failure = KeyError("close")

    def broken(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(indicators, "calculate_premarket_context", broken)
    with pytest.raises(KeyError) as caught:
        fmd.premarket_snapshot("SPY", day, premarket_bars(day), PRIOR, params, READ_AT)
    assert caught.value is failure


def test_prior_session_inputs():
    from lib.indicators import add_all_indicators

    df = daily_history(date(2026, 10, 6))
    enriched = add_all_indicators(df, close_col="Close")
    assert fmd.prior_session_inputs(df, enriched) == {
        "close": 99.0, "open": 99.0, "atr_14": 2.0, "atr_5": 2.0}

    holed = df.copy()
    holed.loc[holed.index[-2], "Close"] = np.nan
    assert fmd.prior_session_inputs(holed, enriched)["close"] is None
    assert fmd.prior_session_inputs(holed, enriched)["open"] == 99.0

    assert fmd.prior_session_inputs(df.iloc[-1:], enriched.iloc[-1:]) == {
        "close": None, "open": None, "atr_14": None, "atr_5": None}

    # A frame add_all_indicators gave no ATR column: no ATR, not an error.
    no_atr = enriched.drop(columns=["ATR14", "ATR5"])
    assert fmd.prior_session_inputs(df, no_atr) == {
        "close": 99.0, "open": 99.0, "atr_14": None, "atr_5": None}

    with pytest.raises(KeyError):
        fmd.prior_session_inputs(df.drop(columns=["Close"]), enriched)


def test_the_nightly_calls_the_snapshot(monkeypatch):
    day = date(2026, 10, 6)
    params = legacy_db(("SPY", "QQQ")).load(["SPY", "QQQ"], day)["SPY"]
    history = daily_history(day)
    bars = premarket_bars(day).drop(columns=["inserted_at"])

    def query(sql, params=None):
        if "FROM market_data_intraday" in sql:
            return bars
        assert "FROM market_data_daily" in sql
        return history.iloc[::-1].reset_index(drop=True)  # newest first, as the query orders

    calls = []
    real = fmd.premarket_snapshot

    def recording(*args, **kwargs):
        calls.append(real(*args, **kwargs))
        return calls[-1]

    written = []
    monkeypatch.setattr(database, "query_to_dataframe", query)
    monkeypatch.setattr(database, "upsert_dataframe",
                        lambda df, table, keys: written.append((table, df.iloc[0].to_dict())))
    monkeypatch.setattr(fmd, "premarket_snapshot", recording)

    fmd.compute_and_upsert_daily_indicators("SPY", "2026-10-06", level_params=params)

    assert len(calls) == 1
    (table, row), = written
    assert table == "market_data_daily"
    for column in fmd.PREMARKET_COLUMNS:
        assert row[column] == calls[0][column], column
    assert row["pre_filter_status"] == "ok"
    assert row["pre_high"] == 100.5
    assert row["pre_range_atr"] == 0.5


def test_the_nightly_keeps_a_stored_price_when_the_new_one_is_none(monkeypatch):
    """The nightly's own write rule: a price column is set only when the new
    value is not None; the provenance columns always."""
    day = date(2026, 10, 6)
    history = daily_history(day)
    bars = premarket_bars(day).drop(columns=["inserted_at"])

    def query(sql, params=None):
        return bars if "FROM market_data_intraday" in sql else history.iloc[::-1].reset_index(drop=True)

    written = []
    monkeypatch.setattr(database, "query_to_dataframe", query)
    monkeypatch.setattr(database, "upsert_dataframe",
                        lambda df, table, keys: written.append(df.iloc[0].to_dict()))
    fmd.compute_and_upsert_daily_indicators("SPY", "2026-10-06", level_params=None)

    (row,) = written
    assert "pre_range_atr" not in row            # None: the stored value is kept
    assert row["pre_filter_status"] == "level_params_unavailable"
    assert row["pre_excluded_spikes"] is None    # provenance: always written
    assert row["pre_filter_params"] is None
    assert row["pre_high"] == 100.5
