"""API default windows count from the exchange's date (FEAT-DATA-001, stage 1).

The API container's clock is UTC. From 19:00 Eastern in winter (20:00 in
summer) until midnight Eastern, ``date.today()`` there is tomorrow, so a
request with no explicit date got a window, a cutoff, a default expiration or
an age check counted from tomorrow.

Every request goes through ``TestClient`` (the changed response, not a helper),
with the clock frozen through ``tests/fixtures/market_clock.py``, which also
makes the host clock raise inside the router under test. The evening instant
is 2026-11-14T01:30Z: Friday 2026-11-13 20:30 EST. Each test also runs at the
other three standard instants, where the host date agrees with the exchange's
or it is a summer evening.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("fastapi")

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO, REPO / "platform", REPO / "platform" / "api"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import gcp.database as database  # noqa: E402
from api.routers import catalysts, dashboard  # noqa: E402
from routers import admin as admin_router  # noqa: E402
from routers import grid  # noqa: E402
from tests.fixtures.market_clock import STANDARD_INSTANTS, freeze_market_clock  # noqa: E402

EVENING = "2026-11-14T01:30:00Z"  # Friday 2026-11-13 20:30 EST
assert STANDARD_INSTANTS[0] == (EVENING, date(2026, 11, 13))

four_instants = pytest.mark.parametrize("instant, eastern", STANDARD_INSTANTS)


def _iso(day: date) -> str:
    return day.isoformat()


# ── catalysts ───────────────────────────────────────────────────────────────


@pytest.fixture
def catalyst_client(monkeypatch):
    monkeypatch.setattr(catalysts, "_load_cached_events", lambda: {"events": []})
    app = FastAPI()
    app.include_router(catalysts.router)
    return TestClient(app)


@four_instants
def test_catalyst_events_default_window(monkeypatch, catalyst_client, instant, eastern):
    freeze_market_clock(monkeypatch, instant, catalysts)
    asked = []
    monkeypatch.setattr(catalysts, "_fetch_live_events", lambda *a, **k: [])
    monkeypatch.setattr(catalysts, "_db_catalyst_events",
                        lambda d_from, d_to, tickers: (asked.append((d_from, d_to)), [])[1])

    response = catalyst_client.get("/api/catalysts/events")

    want = (_iso(eastern - timedelta(days=3)), _iso(eastern + timedelta(days=14)))
    assert response.status_code == 200, response.text
    assert asked == [want]
    assert response.json()["date_range"] == {"from": want[0], "to": want[1]}
    assert [len(text) for text in want] == [10, 10]
    if instant == EVENING:
        assert want == ("2026-11-10", "2026-11-27")


@four_instants
def test_catalysts_for_ticker_window(monkeypatch, catalyst_client, instant, eastern):
    freeze_market_clock(monkeypatch, instant, catalysts)
    asked = []

    def recording_live(date_from, date_to, tickers=None, calendar_types=None):
        asked.append((date_from, date_to, tickers))
        return []

    monkeypatch.setattr(catalysts, "_fetch_live_events", recording_live)

    response = catalyst_client.get("/api/catalysts/ticker/SPY")

    want = (_iso(eastern - timedelta(days=7)), _iso(eastern + timedelta(days=30)))
    assert response.status_code == 200, response.text
    assert asked == [(want[0], want[1], ["SPY"])]
    assert response.json()["date_range"] == {"from": want[0], "to": want[1]}
    if instant == EVENING:
        assert want == ("2026-11-06", "2026-12-13")


@four_instants
def test_catalyst_snapshot_cutoff(monkeypatch, catalyst_client, instant, eastern):
    # stdlib=True: the unmodified handler imports date inside itself.
    freeze_market_clock(monkeypatch, instant, catalysts, stdlib=True)
    bound = []

    def recording_query(sql, params=None):
        bound.append(dict(params))
        return pd.DataFrame()

    monkeypatch.setattr(database, "query_to_dataframe", recording_query)

    response = catalyst_client.get("/api/catalysts/asof/SPY")

    assert response.status_code == 200, response.text
    assert bound, "the snapshot issued no query"
    assert {p["cutoff"] for p in bound} == {_iso(eastern)}
    assert {p["start"] for p in bound if "start" in p} == {_iso(eastern - timedelta(days=7))}
    if instant == EVENING:
        assert _iso(eastern) == "2026-11-13"

    # A caller that passes its own date is unaffected by the clock.
    bound.clear()
    response = catalyst_client.get("/api/catalysts/asof/SPY", params={"as_of": "2026-11-01"})
    assert response.status_code == 200, response.text
    assert {p["cutoff"] for p in bound} == {"2026-11-01"}



def test_catalyst_snapshot_news_window_is_the_eastern_day(monkeypatch, catalyst_client):
    """The cutoff is an Eastern date, so the news window must end at the
    Eastern midnight after it. Ending it at 23:59 UTC of that date dropped
    every article published after 19:00 EST (20:00 EDT) on the cutoff day,
    which is the evening the request is made in."""
    freeze_market_clock(monkeypatch, EVENING, catalysts, stdlib=True)
    news_sql = []

    def recording_query(sql, params=None):
        if "FROM news_sentiment" in sql:
            news_sql.append(" ".join(sql.split()))
        return pd.DataFrame()

    monkeypatch.setattr(database, "query_to_dataframe", recording_query)
    response = catalyst_client.get("/api/catalysts/asof/SPY")

    assert response.status_code == 200, response.text
    assert len(news_sql) == 1
    sql = news_sql[0]
    assert ("published_ts < ((CAST(:cutoff AS date) + 1)::timestamp "
            "AT TIME ZONE 'America/New_York')") in sql
    assert ("published_ts >= (CAST(:start AS date)::timestamp "
            "AT TIME ZONE 'America/New_York')") in sql
    assert "23 hours 59 minutes" not in sql
    assert "AS timestamptz" not in sql


# ── options grid ────────────────────────────────────────────────────────────


@pytest.fixture
def grid_client(monkeypatch):
    monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: True)
    for cache in (grid._LIVE_GRID_CACHE, grid._HIST_GRID_CACHE, grid._NODES_CACHE,
                  grid._HIST_NODES_CACHE, grid._TIMESERIES_CACHE, grid._ONDEMAND_RATE_CACHE):
        cache.clear()
    app = FastAPI()
    app.include_router(grid.router)
    return TestClient(app)


def _realtime_rows(frozen, expirations) -> pd.DataFrame:
    """Three realtime snapshots five minutes apart, two strikes, the given expirations."""
    rows = []
    for minutes in (15, 10, 5):
        snap = pd.Timestamp(frozen) - pd.Timedelta(minutes=minutes)
        for expiration in expirations:
            for strike, gamma in ((100.0, 0.05), (105.0, 0.04)):
                for side, open_interest in (("calls", 1000), ("puts", 800)):
                    rows.append({
                        "snapshot_ts": snap, "snapshot_date": snap.date(),
                        "expiration": expiration, "strike": strike, "option_type": side,
                        "open_interest": open_interest, "gamma": gamma, "vega": 0.20,
                    })
    return pd.DataFrame(rows)


@four_instants
def test_grid_timeseries_default_expiration(monkeypatch, grid_client, instant, eastern):
    frozen = freeze_market_clock(monkeypatch, instant, grid)
    rows = _realtime_rows(frozen, [eastern, eastern + timedelta(days=7)])
    monkeypatch.setattr(database, "query_to_dataframe", lambda sql, params=None: rows.copy())

    response = grid_client.get("/api/options/SPY/grid/timeseries")

    # An expiration dated today is still today's until midnight Eastern.
    assert response.status_code == 200, response.text
    assert response.json()["expiration"] == _iso(eastern)
    if instant == EVENING:
        assert _iso(eastern) == "2026-11-13"


def test_grid_timeseries_moves_to_the_next_expiration_after_eastern_midnight(monkeypatch, grid_client):
    frozen = freeze_market_clock(monkeypatch, "2026-11-14T05:30:00Z", grid)  # Saturday 00:30 EST
    rows = _realtime_rows(frozen, [date(2026, 11, 13), date(2026, 11, 20)])
    monkeypatch.setattr(database, "query_to_dataframe", lambda sql, params=None: rows.copy())

    response = grid_client.get("/api/options/SPY/grid/timeseries")

    assert response.status_code == 200, response.text
    assert response.json()["expiration"] == "2026-11-20"


@four_instants
def test_live_chain_floor(monkeypatch, grid_client, instant, eastern):
    freeze_market_clock(monkeypatch, instant, grid)
    floors = []

    def recording_query(sql, params=None):
        if params and "floor" in params:
            floors.append(params["floor"])
        return pd.DataFrame()

    monkeypatch.setattr(database, "query_to_dataframe", recording_query)

    response = grid_client.get("/api/options/SPY/grid")

    assert response.status_code == 200, response.text
    assert floors and set(floors) == {str(eastern - timedelta(days=20))}
    if instant == EVENING:
        assert set(floors) == {"2026-10-24"}

    # A caller that passes its own date is unaffected by the clock.
    floors.clear()
    grid._load_chain_for_live("SPY", today=date(2026, 1, 5))
    assert set(floors) == {"2025-12-16"}


# ── reference levels (the app of platform/api/main.py) ──────────────────────


@pytest.fixture
def main_client():
    """The whole app, reached as tests/api/test_platform_api.py reaches it.

    Function-scoped: a host-clock read is a BaseException, which ends the
    client's portal, and the next case must not inherit a dead one.
    """
    original_cwd = os.getcwd()
    os.chdir(REPO / "platform")
    from api.main import app

    with TestClient(app) as client:
        yield client
    os.chdir(original_cwd)


@four_instants
def test_reference_levels_recency(monkeypatch, main_client, instant, eastern):
    import api.main as main_module

    freeze_market_clock(monkeypatch, instant, main_module)
    requested = eastern - timedelta(days=29)   # 29 days back is still "recent" (under 30)
    stored = requested - timedelta(days=6)
    row = pd.DataFrame([{
        "date": stored, "open": 121.0, "high": 125.0, "low": 118.0, "close": 120.5, "rsi_14": 41.0,
    }])
    monkeypatch.setattr(main_module, "_CLOUD_SQL", True)
    monkeypatch.setattr(main_module, "_daily_reference_query", lambda sql, params=None: row.copy())

    response = main_client.get(f"/api/market/reference/SPY/{_iso(requested)}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["date"] == _iso(stored).replace("-", "")
    # Recent, and the newest stored row is 6 days behind it (over the 3 allowed).
    assert body["stale_days"] == 6
    if instant == EVENING:
        assert (_iso(requested), _iso(stored)) == ("2026-10-15", "2026-10-09")


# ── strat-engine predict ────────────────────────────────────────────────────

ADMIN_EMAIL = "admin@example.com"
ADMIN_HEADERS = {"x-goog-authenticated-user-email": f"accounts.google.com:{ADMIN_EMAIL}"}


class _FeaturesAsked(Exception):
    """Raised by the feature-loader stub once it has recorded its arguments."""


@four_instants
def test_predict_one_feature_window(monkeypatch, instant, eastern):
    # The predict stack needs the research extras (requirements-research.txt); the
    # test job without them skips this test, as tests/api/test_strat_engine_predict.py
    # skips itself there.
    pytest.importorskip("lightgbm")
    import gcp.research.strat_engine.strat_pred_serve as serve

    # pandas=True: the unmodified function reads pd.Timestamp.utcnow().
    freeze_market_clock(monkeypatch, instant, serve, pandas=True)
    asked = []

    def recording_features(engine, ticker, tf, since=None, **kwargs):
        asked.append(since)
        raise _FeaturesAsked

    # Signed in as the admin, with the model load stubbed, as
    # tests/api/test_strat_engine_predict.py does.
    import api.auth

    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setattr(api.auth, "AUTH_MODE", "iap")
    monkeypatch.setattr(database, "get_engine", lambda: None)
    monkeypatch.setattr(serve, "_load_model", lambda ticker, tf: object())
    monkeypatch.setattr(serve, "_load_metrics", lambda ticker, tf: {"run_id": "r1", "trained_at": "t"})
    monkeypatch.setattr(serve, "_load_live_ece_snapshot", lambda: {})
    monkeypatch.setattr(serve, "load_strat_features_with_levels", recording_features)
    app = FastAPI()
    app.include_router(admin_router.router)

    with pytest.raises(_FeaturesAsked):
        TestClient(app).post(
            "/api/admin/strat-engine/predict",
            json={"ticker": "IWM", "timeframe": "15m"},
            headers=ADMIN_HEADERS,
        )

    assert asked == [_iso(eastern - timedelta(days=30))]
    if instant == EVENING:
        assert asked == ["2026-10-14"]


# ── dashboard live overlay ──────────────────────────────────────────────────


@four_instants
def test_live_overlay_replaces_todays_row(monkeypatch, instant, eastern):
    import lib.indicators as indicators

    freeze_market_clock(monkeypatch, instant, dashboard)
    # Newest first, as the query returns them; the newest row is today's.
    history = pd.DataFrame({
        "date": [eastern - timedelta(days=i) for i in range(30)],
        "close": [100.0 + i for i in range(30)],
    })
    lengths = []
    real_rsi = indicators.calculate_rsi

    async def live_quote(ticker):
        return {"price": 500.0}

    monkeypatch.setattr(dashboard, "_query_fn", lambda sql, params=None: history.copy())
    monkeypatch.setattr(dashboard, "get_live_quote", live_quote)
    monkeypatch.setattr(dashboard, "ET_TZ", None)
    monkeypatch.setattr(indicators, "calculate_rsi",
                        lambda series, period: (lengths.append(len(series)), real_rsi(series, period))[1])

    overlay = asyncio.run(dashboard._apply_live_overlay("SPY", {}))

    assert overlay["price"] == 500.0
    # Today's stored close is replaced by the live price, not followed by a 31st bar.
    assert lengths == [30]
