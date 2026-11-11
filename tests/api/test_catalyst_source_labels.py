"""Catalyst earnings events name their actual sources and exclude retired
EarningsWhispers rows (RETIREMENT-DESIGN section 4.1 sites 2 and 3).

The real router runs over a TestClient. Each earnings_calendar query runs in
SQLite over the fixture rows; every other source returns no rows; provider
acquisition is forbidden. The negative control strips the predicate from the
router's own SQL, which leaves main's text.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lib.earnings_reactions import EARNINGS_NOT_RETIRED_SQL
from tests.fixtures.earnings_calendar_sources import (
    av, ew_only, ew_raw_alias, make_db, null_source, run_earnings_sql,
    unknown_source, uw, yahoo,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "platform"))
from api.routers import catalysts  # noqa: E402
from gcp import database  # noqa: E402

D = date(2026, 11, 10)
DAY = D.isoformat()


def event_rows():
    return [
        # T: the EW row is stored first, so main's first-row dedupe takes it.
        ew_only('T', D, earnings_time='premarket'),
        av('T', D, earnings_time='postmarket'),
        uw('T', D, earnings_time='postmarket'),
        ew_only('E', D),
        ew_raw_alias('R', D),
        yahoo('Y', D, company_name='Yco', earnings_time='premarket'),
        null_source('N', D, company_name='NullCo'),
        unknown_source('K', D, company_name='UnknownCo'),
    ]


@pytest.fixture
def api(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("External provider/database I/O forbidden")

    import requests
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(database, "get_engine", forbidden)
    monkeypatch.setattr(catalysts, "_fetch_live_events", forbidden)
    cache = tmp_path / "catalysts.json"
    cache.write_text(json.dumps({"events": []}), encoding="utf-8")
    monkeypatch.setattr(catalysts, "CATALYSTS_FILE", cache)
    state = {"rows": event_rows(), "sql": [], "strip": False}

    def query(sql, params=None):
        if "FROM earnings_calendar" in sql:
            state["sql"].append(sql)
            if state["strip"]:
                assert sql.count("AND " + EARNINGS_NOT_RETIRED_SQL) == 1
                sql = sql.replace("AND " + EARNINGS_NOT_RETIRED_SQL, "")
            return run_earnings_sql(make_db(state["rows"]), sql, params)
        return pd.DataFrame()

    monkeypatch.setattr(database, "query_to_dataframe", query)
    app = FastAPI()
    app.include_router(catalysts.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, state


def _earnings_events(client):
    resp = client.get("/api/catalysts/events", params={"date_from": DAY, "date_to": DAY})
    assert resp.status_code == 200
    events = resp.json()["events_by_date"].get(DAY, [])
    return [e for e in events if e["catalyst_type"] == "EARNINGS"]


def test_events_query_carries_the_predicate(api):
    client, state = api
    _earnings_events(client)
    (sql,) = state["sql"]
    assert "AND " + EARNINGS_NOT_RETIRED_SQL in sql
    assert "data_source" in sql.split("FROM earnings_calendar")[0]


def test_event_source_names_the_actual_sources(api):
    client, _ = api
    events = _earnings_events(client)
    assert all(e["source"] != "AV earnings_calendar" for e in events)
    by_tk = {e["ticker"]: e for e in events}
    assert [e["ticker"] for e in events].count("T") == 1
    assert by_tk["T"]["source"] == "earnings_calendar (alphavantage, unusual_whales)"
    assert by_tk["T"]["title"] == "Acme earnings (postmarket, est 1.23)"
    assert by_tk["Y"]["source"] == "earnings_calendar (yahoo)"
    assert by_tk["K"]["source"] == "earnings_calendar (unknown)"
    assert by_tk["N"]["source"] == "earnings_calendar (source not recorded)"


def test_ew_only_tickers_are_absent(api):
    client, _ = api
    tickers = {e["ticker"] for e in _earnings_events(client)}
    assert tickers == {"T", "Y", "N", "K"}


def test_main_shaped_events_query_keeps_ew(api):
    """Negative control: without the predicate the EW-only tickers appear and
    the EW row decides T's title."""
    client, state = api
    state["strip"] = True
    by_tk = {e["ticker"]: e for e in _earnings_events(client)}
    assert {"E", "R"} <= set(by_tk)
    assert by_tk["T"]["title"] == "Zz Corp earnings (premarket)"
    assert "earnings_whispers" in by_tk["T"]["source"]


def _next_earnings(client, ticker):
    resp = client.get(f"/api/catalysts/asof/{ticker}", params={"as_of": DAY})
    assert resp.status_code == 200
    return resp.json()["next_earnings"]


def test_ticker_detail_next_earnings_ignores_ew(api):
    client, state = api
    state["rows"] = [
        av('T', D + timedelta(days=5)),
        ew_only('T', D + timedelta(days=1)),
        ew_only('E', D + timedelta(days=2)),
        ew_raw_alias('R', D + timedelta(days=2)),
    ]
    assert _next_earnings(client, "T")["earnings_date"] == (D + timedelta(days=5)).isoformat()
    assert _next_earnings(client, "E") is None
    assert _next_earnings(client, "R") is None
    assert all("AND " + EARNINGS_NOT_RETIRED_SQL in s for s in state["sql"])


def test_main_shaped_next_earnings_takes_the_ew_date(api):
    client, state = api
    state["rows"] = [av('T', D + timedelta(days=5)), ew_only('T', D + timedelta(days=1))]
    state["strip"] = True
    assert _next_earnings(client, "T")["earnings_date"] == (D + timedelta(days=1)).isoformat()
