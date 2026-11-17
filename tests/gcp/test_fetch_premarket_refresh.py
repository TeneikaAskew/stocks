"""Unit tests for ``gcp/fetchers/fetch_premarket_refresh.py``.

The pre-market refresh job is the link that lets the 8:45 AM brief see
today's gap_pct. Tests cover universe selection, the UPSERT idempotency,
and graceful degradation when AV / Cloud SQL aren't reachable.

Live AV calls are stubbed via monkeypatch — see test_fetch_market_data*
for the AV integration tests.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest


# ──────────────────────────────────────────────────────────────────────
# resolve_universe — priority ordering + filter on options_volume
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def stub_db(monkeypatch):
    """Stub out gcp.database.is_cloud_sql_configured + query_to_dataframe.

    Returns a setter that lets each test feed a list of (sql, params, df)
    triples — the stubbed query_to_dataframe matches by which columns are
    in the SQL so we can route the watchlist call vs. the earnings calls
    independently.
    """
    from gcp import database

    captured = {"calls": []}

    routes = {}  # match-key → df

    def install_route(match_substring: str, df: pd.DataFrame):
        routes[match_substring] = df

    def fake_query(sql, params=None):
        captured["calls"].append((sql, params))
        for key, df in routes.items():
            if key in sql:
                return df.copy() if df is not None else pd.DataFrame()
        return pd.DataFrame()

    monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(database, "query_to_dataframe", fake_query)

    return install_route, captured


def test_resolve_universe_includes_watchlist_first(stub_db, monkeypatch):
    install, _ = stub_db
    # Today's earnings reporters
    install("MAX(options_volume) AS opt_vol",
            pd.DataFrame({'ticker': ['AMZN', 'MSFT'],
                          'opt_vol': [200_000, 100_000],
                          'mcap': [1.3e12, 3e12]}))
    # Yesterday's AMC reporters
    install("SELECT DISTINCT ticker FROM earnings_calendar",
            pd.DataFrame({'ticker': ['SBUX']}))

    # Stub the watchlist
    import gcp.fetchers._watchlist as wl
    monkeypatch.setattr(wl, "load_watchlist", lambda: ['SPY', 'QQQ', 'IWM'])

    from gcp.fetchers.fetch_premarket_refresh import resolve_universe
    universe = resolve_universe(date(2026, 4, 30), max_tickers=50)

    # Watchlist + today's earnings + yesterday's AMC, all unique
    assert set(universe) == {'SPY', 'QQQ', 'IWM', 'AMZN', 'MSFT', 'SBUX'}


def test_resolve_universe_caps_with_watchlist_priority(stub_db, monkeypatch):
    """When max_tickers is hit, watchlist tickers (priority 0) survive
    and earnings names (priority 1+) get trimmed."""
    install, _ = stub_db
    install("MAX(options_volume) AS opt_vol",
            pd.DataFrame({'ticker': [f'EARN{i}' for i in range(20)],
                          'opt_vol': [10_000] * 20,
                          'mcap': [1e9] * 20}))
    install("SELECT DISTINCT ticker FROM earnings_calendar",
            pd.DataFrame({'ticker': []}))

    import gcp.fetchers._watchlist as wl
    monkeypatch.setattr(wl, "load_watchlist", lambda: ['SPY', 'QQQ', 'IWM', 'SPX'])

    from gcp.fetchers.fetch_premarket_refresh import resolve_universe
    universe = resolve_universe(date(2026, 4, 30), max_tickers=8)

    # All 4 watchlist tickers must survive the trim
    assert {'SPY', 'QQQ', 'IWM', 'SPX'}.issubset(set(universe))
    assert len(universe) == 8


def test_resolve_universe_no_cloud_sql_returns_empty(monkeypatch):
    """No DB → empty list, not a crash."""
    from gcp import database
    monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: False)

    from gcp.fetchers.fetch_premarket_refresh import resolve_universe
    assert resolve_universe(date(2026, 4, 30)) == []


def test_resolve_universe_walks_back_over_weekend(stub_db, monkeypatch):
    """If target_date is Monday, yesterday's-AMC lookup should hit the
    most recent weekday (Friday), not Sunday."""
    install, captured = stub_db
    install("MAX(options_volume) AS opt_vol",
            pd.DataFrame({'ticker': [], 'opt_vol': [], 'mcap': []}))
    install("SELECT DISTINCT ticker FROM earnings_calendar",
            pd.DataFrame({'ticker': []}))

    import gcp.fetchers._watchlist as wl
    monkeypatch.setattr(wl, "load_watchlist", lambda: [])

    from gcp.fetchers.fetch_premarket_refresh import resolve_universe
    # Monday 2026-05-04
    resolve_universe(date(2026, 5, 4), max_tickers=10)

    # Inspect AMC query params — should be 2026-05-01 (Friday), not 2026-05-03 (Sunday)
    amc_call = next((c for c in captured["calls"]
                     if "SELECT DISTINCT ticker FROM earnings_calendar" in c[0]), None)
    assert amc_call is not None
    assert amc_call[1]['d'] == date(2026, 5, 1)


# ──────────────────────────────────────────────────────────────────────
# compute_premarket_for_ticker — null-safe
# ──────────────────────────────────────────────────────────────────────


def test_compute_returns_none_when_no_intraday_bars(monkeypatch):
    """AV intraday returned 0 bars (early run, weekend, holiday) → None."""
    from gcp.fetchers import fetch_market_data
    monkeypatch.setattr(fetch_market_data, "fetch_minute_data",
                        lambda tk, d, k: pd.DataFrame())

    from gcp.fetchers.fetch_premarket_refresh import compute_premarket_for_ticker
    assert compute_premarket_for_ticker("AAPL", date(2026, 4, 30), "key") is None


def test_compute_returns_none_when_no_premarket_window(monkeypatch):
    """Bars exist but none fall in the 4am-9:30am pre-market window —
    e.g. only 10am-4pm regular session bars. → None."""
    from gcp.fetchers import fetch_market_data
    # Single regular-hours bar at 10:00am ET
    bars = pd.DataFrame(
        {'Open': [180.0], 'High': [181.0], 'Low': [179.0],
         'Close': [180.5], 'Volume': [1_000_000]},
        index=pd.DatetimeIndex(['2026-04-30 10:00:00']),
    )
    monkeypatch.setattr(fetch_market_data, "fetch_minute_data",
                        lambda tk, d, k: bars)
    # No prev_close lookup needed for this test — short-circuit it
    from gcp.fetchers import fetch_premarket_refresh as fpr
    monkeypatch.setattr(fpr, "_prior_session_from_db", lambda tk, d: {"close": 178.0, "atr_14": 10.0})

    result = fpr.compute_premarket_for_ticker("AAPL", date(2026, 4, 30), "key")
    assert result is None


def test_compute_returns_metrics_when_premarket_bars_present(monkeypatch):
    """Pre-market bars present → dict with pre_high/low/vwap/volume/gap_pct."""
    bars = pd.DataFrame(
        {
            'Open': [180.0, 182.0, 183.0],
            'High': [181.0, 182.5, 184.0],
            'Low':  [179.5, 181.5, 182.0],
            'Close': [180.5, 182.0, 183.5],
            'Volume': [10_000, 8_000, 12_000],
        },
        index=pd.DatetimeIndex([
            '2026-04-30 04:00:00',
            '2026-04-30 06:30:00',
            '2026-04-30 08:15:00',
        ]),
    )
    from gcp.fetchers import fetch_market_data
    from gcp.fetchers import fetch_premarket_refresh as fpr
    monkeypatch.setattr(fetch_market_data, "fetch_minute_data",
                        lambda tk, d, k: bars)
    monkeypatch.setattr(fpr, "_prior_session_from_db", lambda tk, d: {"close": 175.0, "atr_14": 10.0})

    result = fpr.compute_premarket_for_ticker("AAPL", date(2026, 4, 30), "key")
    assert result is not None
    assert result['ticker'] == 'AAPL'
    assert result['date'] == date(2026, 4, 30)
    # FEAT-PLAYBOOK-001 B7: 184.0 and 179.5 are one bar's lone wick each, so
    # the extremes are the highest and lowest open or close (the 08:15 close
    # and the 04:00 open), which lie beyond the second bar high and low.
    assert result['pre_high'] == 183.5
    assert result['pre_low'] == 180.0
    # gap_pct = (180.0 - 175.0) / 175.0 * 100 ≈ +2.86%
    assert result['gap_pct'] is not None
    assert abs(result['gap_pct'] - 2.857) < 0.01


# ──────────────────────────────────────────────────────────────────────
# upsert_premarket — filter rows with no useful pre-market data
# ──────────────────────────────────────────────────────────────────────


class TestUpsertFiltering:
    """Regression: AV occasionally returns no pre-market bars for a
    ticker (early run, weekend, extended-hours not enabled). Without
    this filter, upsert would INSERT a row with all NULLs, which
    crashed the morning brief's compute_current_levels."""

    def test_skips_rows_with_all_pre_fields_null(self, monkeypatch):
        """Row where every pre_* field is None must NOT trigger INSERT."""
        from gcp.fetchers import fetch_premarket_refresh as fpr

        # Stub get_engine so we can detect any execute() call
        executed = []
        class FakeConn:
            def execute(self, sql, params):
                executed.append(params)
        class FakeBegin:
            def __enter__(self): return FakeConn()
            def __exit__(self, *a): return False
        class FakeEngine:
            def begin(self): return FakeBegin()
        from gcp import database
        monkeypatch.setattr(database, "get_engine", lambda: FakeEngine())

        n = fpr.upsert_premarket([
            {'ticker': 'EMPTY', 'date': date(2026, 4, 30),
             'pre_high': None, 'pre_low': None, 'pre_vwap': None,
             'pre_volume': None, 'gap_pct': None},
        ])
        assert n == 0
        assert executed == [], "no INSERT should fire for all-null row"

    def test_keeps_rows_with_at_least_one_pre_field(self, monkeypatch):
        from gcp.fetchers import fetch_premarket_refresh as fpr

        executed = []
        class FakeConn:
            def execute(self, sql, params):
                executed.append(params)
        class FakeBegin:
            def __enter__(self): return FakeConn()
            def __exit__(self, *a): return False
        class FakeEngine:
            def begin(self): return FakeBegin()
        from gcp import database
        monkeypatch.setattr(database, "get_engine", lambda: FakeEngine())

        # Row with only gap_pct → keep
        n = fpr.upsert_premarket([
            {'ticker': 'GAP_ONLY', 'date': date(2026, 4, 30),
             'pre_high': None, 'pre_low': None, 'pre_vwap': None,
             'pre_volume': None, 'gap_pct': 0.42},
        ])
        assert n == 1
        assert len(executed) == 1
        assert executed[0]['ticker'] == 'GAP_ONLY'

    def test_mixed_useful_and_empty_rows(self, monkeypatch):
        """Useful rows persist; empty ones are silently dropped."""
        from gcp.fetchers import fetch_premarket_refresh as fpr

        executed = []
        class FakeConn:
            def execute(self, sql, params):
                executed.append(params)
        class FakeBegin:
            def __enter__(self): return FakeConn()
            def __exit__(self, *a): return False
        class FakeEngine:
            def begin(self): return FakeBegin()
        from gcp import database
        monkeypatch.setattr(database, "get_engine", lambda: FakeEngine())

        n = fpr.upsert_premarket([
            {'ticker': 'GOOD', 'date': date(2026, 4, 30),
             'pre_high': 180.0, 'pre_low': 178.0, 'pre_vwap': 179.0,
             'pre_volume': 100, 'gap_pct': 1.5},
            {'ticker': 'EMPTY', 'date': date(2026, 4, 30),
             'pre_high': None, 'pre_low': None, 'pre_vwap': None,
             'pre_volume': None, 'gap_pct': None},
        ])
        assert n == 1
        assert {e['ticker'] for e in executed} == {'GOOD'}


# ──────────────────────────────────────────────────────────────────────
# The newest premarket bar per ticker (FEAT-PLAYBOOK-001, the late slot)
# ──────────────────────────────────────────────────────────────────────


def _minute_bars(first: str, last: str) -> pd.DataFrame:
    """One-minute bars of 2026-04-30 from `first` through `last`, in the
    vendor's naive Eastern wall time."""
    idx = pd.date_range(f'2026-04-30 {first}', f'2026-04-30 {last}', freq='1min')
    return pd.DataFrame({'Open': 180.0, 'High': 181.0, 'Low': 179.5, 'Close': 180.5,
                         'Volume': 1_000}, index=idx)


def test_compute_logs_the_newest_premarket_bar(monkeypatch, caplog):
    """How late the vendor's newest bar is at the fetch is what the late
    brief's levels depend on, and nothing recorded it. One INFO record per
    ticker names the premarket bar count, the newest premarket bar (the
    vendor's own Eastern wall time) and the fetch time in America/New_York.
    Nothing is stored."""
    import logging
    from datetime import datetime, timezone

    from gcp.fetchers import fetch_market_data
    from gcp.fetchers import fetch_premarket_refresh as fpr

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 4, 30, 13, 20, 41, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(fpr, 'datetime', FrozenDatetime)
    monkeypatch.setattr(fpr, '_prior_session_from_db',
                        lambda tk, d: {'close': 178.0, 'atr_14': 10.0})
    frames = {}
    monkeypatch.setattr(fetch_market_data, 'fetch_minute_data', lambda tk, d, k: frames['bars'])

    def record():     # the INFO records of the module that name a bar time
        return [r.getMessage() for r in caplog.records
                if r.name == 'gcp.fetchers.fetch_premarket_refresh'
                and r.levelno == logging.INFO and 'newest_bar=' in r.getMessage()]

    with caplog.at_level(logging.INFO, logger='gcp.fetchers.fetch_premarket_refresh'):
        # 04:00 through 09:19: 320 premarket bars
        frames['bars'] = _minute_bars('04:00', '09:19')
        snapshot = fpr.compute_premarket_for_ticker('AAPL', date(2026, 4, 30), 'key')
        assert snapshot is not None
        (line,) = record()
        assert 'AAPL' in line and 'bars=320' in line and 'newest_bar=09:19 ET' in line
        assert 'fetched_at=09:20:41 ET' in line
        # the record stores nothing: the snapshot is what it was
        assert snapshot['pre_fetched_at'] == datetime(2026, 4, 30, 13, 20, 41, tzinfo=timezone.utc)
        assert not any('newest' in key for key in snapshot)

        # 04:00 through 15:59: the newest premarket bar is 09:29, not the last bar of the day
        caplog.clear()
        frames['bars'] = _minute_bars('04:00', '15:59')
        assert fpr.compute_premarket_for_ticker('AAPL', date(2026, 4, 30), 'key') is not None
        (line,) = record()
        assert 'bars=330' in line and 'newest_bar=09:29 ET' in line

        # one bar at 10:00: no premarket bar, no record
        caplog.clear()
        frames['bars'] = _minute_bars('10:00', '10:00')
        assert fpr.compute_premarket_for_ticker('AAPL', date(2026, 4, 30), 'key') is None
        assert record() == []


@pytest.mark.parametrize('index,newest', [
    (pd.DatetimeIndex(['2026-04-30 03:59:00', '2026-04-30 04:00:00', '2026-04-30 09:29:00',
                       '2026-04-30 09:30:00']), '2026-04-30 09:29:00'),
    # a zone-aware index is read in Eastern: 13:19Z is 09:19 EDT
    (pd.DatetimeIndex(['2026-04-30 08:00:00', '2026-04-30 13:19:00', '2026-04-30 13:30:00'],
                      tz='UTC'), '2026-04-30 09:19:00'),
    (pd.DatetimeIndex(['2026-04-30 03:59:00', '2026-04-30 09:30:00']), None),
    (pd.DatetimeIndex([]), None),
])
def test_newest_premarket_bar(index, newest):
    from gcp.fetchers import fetch_premarket_refresh as fpr

    got = fpr._newest_premarket_bar(index)
    if newest is None:
        assert got is None
    else:
        assert got.strftime('%Y-%m-%d %H:%M:%S') == newest
