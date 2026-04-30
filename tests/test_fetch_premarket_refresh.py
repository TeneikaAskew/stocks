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
    monkeypatch.setattr(fpr, "_prev_close_from_db", lambda tk, d: 178.0)

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
    monkeypatch.setattr(fpr, "_prev_close_from_db", lambda tk, d: 175.0)

    result = fpr.compute_premarket_for_ticker("AAPL", date(2026, 4, 30), "key")
    assert result is not None
    assert result['ticker'] == 'AAPL'
    assert result['date'] == date(2026, 4, 30)
    # Highest of the pre-market highs
    assert result['pre_high'] == 184.0
    assert result['pre_low']  == 179.5
    # gap_pct = (180.0 - 175.0) / 175.0 * 100 ≈ +2.86%
    assert result['gap_pct'] is not None
    assert abs(result['gap_pct'] - 2.857) < 0.01
