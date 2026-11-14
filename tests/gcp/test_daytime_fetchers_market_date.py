"""The daytime fetchers read the exchange's date (FEAT-DATA-001, stage 1).

These seven jobs run between 02:30 and 17:00 America/New_York, hours at which
the container's UTC date and the exchange's date agree, so nothing they store
is wrong today. Nothing but the schedule kept them right: a run moved into the
evening would have dated its rows tomorrow. Each test runs at an evening
instant in both seasons (where the old code was a day ahead) and at two
instants where the host date agrees (where the value must not move).
"""
from __future__ import annotations

import sys
from datetime import timedelta

import pandas as pd
import pytest
import sqlalchemy

import gcp.database as database
import gcp.fetchers.backfill_daily_indicators as backfill
import gcp.fetchers.fetch_economic_events as economic_events
import gcp.fetchers.fetch_fred_rates as fred_rates
import gcp.fetchers.fetch_insider_transactions as insider
import gcp.fetchers.fetch_premarket_refresh as premarket_refresh
import gcp.fetchers.fetch_sec_filings as sec_filings
import gcp.fetchers.fetch_top_movers as top_movers
from lib.eastern_time import market_today_sql
from tests.fixtures.market_clock import STANDARD_INSTANTS, freeze_market_clock

four_instants = pytest.mark.parametrize("instant, eastern", STANDARD_INSTANTS)


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@four_instants
def test_top_movers_snapshot_date(monkeypatch, instant, eastern):
    freeze_market_clock(monkeypatch, instant, top_movers)
    payload = {"top_gainers": [{"ticker": "AAA", "price": "1.0", "change_amount": "0.1",
                                "change_percentage": "10%", "volume": "100"}]}
    monkeypatch.setattr(top_movers.requests, "get", lambda *a, **k: _Response(payload))

    out = top_movers.fetch_top_movers("k")

    assert len(out) == 1
    assert set(out["snapshot_date"]) == {eastern}


@four_instants
def test_premarket_refresh_default_target(monkeypatch, instant, eastern):
    freeze_market_clock(monkeypatch, instant, premarket_refresh)
    targets = []

    def recording_universe(target_date, max_tickers=50):
        targets.append(target_date)
        return []

    monkeypatch.setattr(premarket_refresh, "resolve_universe", recording_universe)
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
    monkeypatch.setattr(sys, "argv", ["x"])

    premarket_refresh.main()

    assert targets == [eastern]


@four_instants
def test_fred_release_window(monkeypatch, instant, eastern):
    freeze_market_clock(monkeypatch, instant, economic_events)
    asked = []

    def recording_get(url, params=None, timeout=None):
        asked.append(params)
        return _Response({"release_dates": []})

    monkeypatch.setattr("requests.get", recording_get)
    monkeypatch.setenv("FRED_API_KEY", "k")

    economic_events.fetch_fred_releases()

    assert len(asked) == 1
    assert asked[0]["realtime_start"] == eastern.isoformat()
    assert asked[0]["realtime_end"] == (eastern + timedelta(days=90)).isoformat()


@four_instants
def test_fred_rates_default_range(monkeypatch, instant, eastern):
    freeze_market_clock(monkeypatch, instant, fred_rates)
    ranges = []

    def recording_fetch(api_key, start, end):
        ranges.append((start, end))
        return pd.DataFrame()

    monkeypatch.setattr(fred_rates, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(fred_rates, "fetch_dgs3mo", recording_fetch)
    monkeypatch.setattr(fred_rates, "upsert_daily_rates", lambda df, div_yld: 0)
    monkeypatch.setenv("FRED_API_KEY", "k")
    monkeypatch.setattr(sys, "argv", ["x"])

    assert fred_rates.main() == 0
    assert ranges == [((eastern - timedelta(days=14)).isoformat(), eastern.isoformat())]


@four_instants
def test_sec_filings_since(monkeypatch, instant, eastern):
    freeze_market_clock(monkeypatch, instant, sec_filings)
    cutoffs = []

    def recording_filter(rows, forms, since):
        cutoffs.append(since)
        return pd.DataFrame()

    monkeypatch.setattr(sec_filings, "load_ticker_to_cik", lambda user_agent: {"SPY": "1"})
    monkeypatch.setattr(sec_filings, "fetch_submissions",
                        lambda ticker, cik, user_agent: [{"ticker": "SPY", "form": "8-K"}])
    monkeypatch.setattr(sec_filings, "filter_and_normalize", recording_filter)
    monkeypatch.setattr(sys, "argv", ["x", "--tickers", "SPY", "--since-days", "3", "--dry-run"])

    sec_filings.main()

    assert cutoffs == [eastern - timedelta(days=3)]


@four_instants
def test_insider_future_cutoff(monkeypatch, instant, eastern):
    # pandas=True: the unmodified function reads pd.Timestamp.utcnow().
    freeze_market_clock(monkeypatch, instant, insider, pandas=True)
    days = [eastern + timedelta(days=7), eastern + timedelta(days=8)]
    payload = {"data": [
        {"transaction_date": day.isoformat(), "executive": "A", "shares": "1", "share_price": "1"}
        for day in days
    ]}
    monkeypatch.setattr(insider.requests, "get", lambda *a, **k: _Response(payload))

    out = insider.fetch_for_ticker("SPY", "k")

    # A date more than a week ahead of the exchange's today is vendor garbage.
    assert list(out["transaction_date"]) == [days[0]]


@four_instants
def test_recent_rows_cutoff(monkeypatch, instant, eastern):
    # stdlib=True: the unmodified function imports date inside itself.
    freeze_market_clock(monkeypatch, instant, backfill, stdlib=True)
    rows = [
        {"ticker": "SPY", "date": eastern - timedelta(days=7)},
        {"ticker": "SPY", "date": eastern - timedelta(days=8)},
    ]

    assert backfill._filter_recent_rows(rows, 7) == rows[:1]


@pytest.mark.parametrize("name, times, binds", [
    ("sec", 2, {"w"}),
    ("insider", 2, {"w"}),
    ("backfill", 3, {"d"}),
])
def test_the_three_statements_read_the_exchange_date(monkeypatch, name, times, binds):
    issued = []

    def recording(sql, params=None):
        issued.append((sql, params))
        return pd.DataFrame({"ticker": []})

    if name == "backfill":
        monkeypatch.setattr(backfill, "query_to_dataframe", recording)
        backfill._tickers_with_gaps(7)
    else:
        monkeypatch.setattr(database, "query_to_dataframe", recording)
        {"sec": sec_filings, "insider": insider}[name]._earnings_calendar_tickers(7)

    (sql, params), = issued
    assert sql.count(market_today_sql()) == times
    assert "CURRENT_DATE" not in sql
    # The helper's text brings a :: cast; the statement keeps exactly the bind it had.
    assert set(sqlalchemy.text(sql)._bindparams) == binds
    assert set(params) == binds
