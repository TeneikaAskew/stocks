"""Most-active ticker bar (Task 2) -- GET /api/market/most-active.

Reads `top_movers_intraday` (Task 1: snapshot_ts TIMESTAMPTZ true-UTC,
snapshot_date DATE ET, rank 1..20, ticker, price, change_amount,
change_pct float TRUE PERCENT, volume BIGINT; unique (snapshot_ts,ticker)).

One SQL pulls every row for the latest `snapshot_date` (CLAUDE.md Rule 0:
batch, never per-ticker); the router groups it in memory:
  - items = the latest snapshot_ts's rows, ordered by rank.
  - spark  = each ticker's price series across the date's snapshots,
    ordered by snapshot_ts -- omitted entirely (Rule 3.7: no synthesized
    single-point series) when a ticker has <2 points.
  - label = "live" if the latest snapshot is <90min old AND now is within
    RTH (09:30-16:00 ET), else the ET snapshot_date string.

Empty table -> honest 200 {"items": [], "label": None, "snapshot_ts": None,
"snapshot_date": None} (the bar is decorative and just hides). A real DB
failure -> 503, mirroring the sibling /api/market/sectors and
/api/market/coverage endpoints in this same file (query_to_dataframe_strict
+ 503-on-exception).

Auth: same gate as GET /api/market/dates/{ticker} -- neither path is in
auth._OPEN_API_PREFIXES, so both are gated identically in firebase mode
(and unaffected identically in iap/open mode). No new auth code is added
for this endpoint; parity is verified directly against auth._path_requires_auth.

Scaffold: TestClient + monkeypatch conventions from tests/test_journal_examples.py
(sys.path setup, chdir-guarded import of api.main, SQL-text pinning inside the
fake query so a mutation that drops the WHERE/ORDER BY clauses fails loudly)
combined with tests/test_market_sectors.py's simpler single-function-monkeypatch
shape, since /api/market/most-active lives in the same main.py module as its
sibling /api/market/sectors.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("fastapi")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_DIR = PROJECT_ROOT / "platform"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

_original_cwd = os.getcwd()
os.chdir(str(PLATFORM_DIR))
try:
    from api import main, auth
finally:
    os.chdir(_original_cwd)

from fastapi.testclient import TestClient  # noqa: E402


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


# Two snapshot_dates. 2026-07-10 is older and must be excluded entirely (the
# SQL scopes to the latest snapshot_date only). 2026-07-11 has two snapshots
# (13:30Z and 14:30Z): NVDA and TSLA appear in both (>=2 points -> spark),
# AAPL appears only in the latest snapshot (1 point -> spark omitted).
_ALL_ROWS = pd.DataFrame([
    {"snapshot_ts": _ts("2026-07-10T14:30:00"), "snapshot_date": "2026-07-10",
     "rank": 1, "ticker": "OLD", "price": 10.0, "change_amount": 0.1,
     "change_pct": 1.0, "volume": 1_000_000},
    {"snapshot_ts": _ts("2026-07-11T13:30:00"), "snapshot_date": "2026-07-11",
     "rank": 1, "ticker": "NVDA", "price": 181.2, "change_amount": 1.0,
     "change_pct": 0.55, "volume": 300_000_000},
    {"snapshot_ts": _ts("2026-07-11T13:30:00"), "snapshot_date": "2026-07-11",
     "rank": 2, "ticker": "TSLA", "price": 250.0, "change_amount": 2.0,
     "change_pct": 0.80, "volume": 200_000_000},
    {"snapshot_ts": _ts("2026-07-11T14:30:00"), "snapshot_date": "2026-07-11",
     "rank": 1, "ticker": "NVDA", "price": 182.4, "change_amount": 2.2,
     "change_pct": 1.21, "volume": 312_000_000},
    {"snapshot_ts": _ts("2026-07-11T14:30:00"), "snapshot_date": "2026-07-11",
     "rank": 2, "ticker": "TSLA", "price": 252.0, "change_amount": 4.0,
     "change_pct": 1.60, "volume": 210_000_000},
    {"snapshot_ts": _ts("2026-07-11T14:30:00"), "snapshot_date": "2026-07-11",
     "rank": 3, "ticker": "AAPL", "price": 190.0, "change_amount": 0.5,
     "change_pct": 0.26, "volume": 50_000_000},
])


def _make_fake_query(calls: list, df: pd.DataFrame = _ALL_ROWS):
    """Fake `_most_active_query`.

    Mutation-proof SQL-text pins (mirrors tests/test_journal_examples.py's
    `_make_fake_query`): the real query must scope to `top_movers_intraday`,
    filter to the MAX(snapshot_date), and order by snapshot_ts then rank. The
    fake then applies that exact filter/order itself so the endpoint's
    in-memory grouping is exercised against realistic (already-scoped) rows,
    the same way Postgres would hand them back.
    """

    def fake_query(sql, params=None):
        calls.append((sql, params or {}))
        sql_lower = sql.lower()
        assert "from top_movers_intraday" in sql_lower, \
            f"must read top_movers_intraday, got: {sql}"
        assert "select max(snapshot_date)" in sql_lower, \
            f"must scope to the latest snapshot_date (single SQL, no per-ticker queries), got: {sql}"
        assert "order by snapshot_ts" in sql_lower, \
            f"must order by snapshot_ts (spark ordering depends on it), got: {sql}"

        out = df.copy()
        if out.empty:
            return out
        latest_date = out["snapshot_date"].max()
        out = out[out["snapshot_date"] == latest_date]
        return out.sort_values(["snapshot_ts", "rank"]).reset_index(drop=True)

    return fake_query


@pytest.fixture
def client():
    return TestClient(main.app)


class TestShape:
    def test_response_shape_and_ranks_ordered(self, client, monkeypatch):
        calls = []
        monkeypatch.setattr(main, "_most_active_query", _make_fake_query(calls), raising=True)

        r = client.get("/api/market/most-active")
        assert r.status_code == 200
        body = r.json()

        assert len(calls) == 1  # one SQL, not per-ticker
        assert set(body.keys()) == {"snapshot_ts", "snapshot_date", "label", "items"}
        assert body["snapshot_date"] == "2026-07-11"
        assert body["snapshot_ts"].startswith("2026-07-11T14:30:00")

        items = body["items"]
        assert [it["ticker"] for it in items] == ["NVDA", "TSLA", "AAPL"]
        assert [it["rank"] for it in items] == [1, 2, 3]  # ranks ordered

        nvda = items[0]
        assert nvda["price"] == 182.4
        assert nvda["change_pct"] == 1.21
        assert nvda["volume"] == 312_000_000

    def test_old_snapshot_date_excluded(self, client, monkeypatch):
        calls = []
        monkeypatch.setattr(main, "_most_active_query", _make_fake_query(calls), raising=True)
        r = client.get("/api/market/most-active")
        tickers = [it["ticker"] for it in r.json()["items"]]
        assert "OLD" not in tickers


class TestSpark:
    def test_spark_present_and_ordered_for_multi_snapshot_ticker(self, client, monkeypatch):
        calls = []
        monkeypatch.setattr(main, "_most_active_query", _make_fake_query(calls), raising=True)
        r = client.get("/api/market/most-active")
        items = {it["ticker"]: it for it in r.json()["items"]}
        # NVDA has 2 points across the date's 2 snapshots, ordered by snapshot_ts.
        assert items["NVDA"]["spark"] == [181.2, 182.4]
        assert items["TSLA"]["spark"] == [250.0, 252.0]

    def test_spark_omitted_when_fewer_than_two_points(self, client, monkeypatch):
        calls = []
        monkeypatch.setattr(main, "_most_active_query", _make_fake_query(calls), raising=True)
        r = client.get("/api/market/most-active")
        items = {it["ticker"]: it for it in r.json()["items"]}
        # AAPL only appears in the latest snapshot -> 1 point -> key omitted
        # entirely (Rule 3.7: never synthesize a 1-point "series").
        assert "spark" not in items["AAPL"]


class TestEmptyTable:
    def test_empty_table_returns_honest_empty_200(self, client, monkeypatch):
        calls = []
        empty_df = pd.DataFrame(columns=[
            "snapshot_ts", "snapshot_date", "rank", "ticker", "price",
            "change_amount", "change_pct", "volume",
        ])
        monkeypatch.setattr(main, "_most_active_query", _make_fake_query(calls, empty_df), raising=True)

        r = client.get("/api/market/most-active")
        assert r.status_code == 200
        body = r.json()
        assert body == {
            "items": [],
            "label": None,
            "snapshot_ts": None,
            "snapshot_date": None,
        }


class TestDbUnavailable:
    def test_query_exception_surfaces_as_503(self, client, monkeypatch):
        def boom(sql, params=None):
            raise RuntimeError("db down")

        monkeypatch.setattr(main, "_most_active_query", boom, raising=True)
        r = client.get("/api/market/most-active")
        assert r.status_code == 503
        assert "items" not in r.json()


class TestAuthParity:
    def test_gated_the_same_as_market_dates(self):
        """Neither path is in auth._OPEN_API_PREFIXES: both are gated
        identically in firebase mode (verify, don't assume -- CLAUDE.md
        brief instruction)."""
        most_active_gated = auth._path_requires_auth("/api/market/most-active")
        dates_gated = auth._path_requires_auth("/api/market/dates/NVDA")
        assert most_active_gated == dates_gated
        assert most_active_gated is True  # both require auth in firebase mode


class TestLabel:
    """Pure-helper tests for the "live" vs ET-date label rule (mirrors
    test_market_sectors.py's approach of unit-testing the pure math
    separately from the endpoint's I/O)."""

    def test_live_when_recent_and_within_rth(self):
        # 2026-07-13 is a Monday (real trading day) -- must NOT collide with
        # the weekend/holiday cases below, which intentionally reuse dates
        # that pass the bare clock-time check but are not trading days.
        latest_ts = _ts("2026-07-13T14:30:00")  # 10:30 ET
        now = datetime(2026, 7, 13, 15, 0, 0, tzinfo=timezone.utc)  # 11:00 ET, 30min later
        assert main._most_active_label(latest_ts, "2026-07-13", now_utc=now) == "live"

    def test_not_live_when_older_than_90_minutes(self):
        latest_ts = _ts("2026-07-13T14:30:00")  # 10:30 ET, Monday
        now = datetime(2026, 7, 13, 16, 30, 0, tzinfo=timezone.utc)  # 12:30 ET, 120min later
        assert main._most_active_label(latest_ts, "2026-07-13", now_utc=now) == "2026-07-13"

    def test_not_live_when_outside_rth_even_if_recent(self):
        latest_ts = _ts("2026-07-13T20:30:00")  # 16:30 ET (after close), Monday
        now = datetime(2026, 7, 13, 21, 0, 0, tzinfo=timezone.utc)  # 17:00 ET, 30min later, after close
        assert main._most_active_label(latest_ts, "2026-07-13", now_utc=now) == "2026-07-13"

    def test_not_live_when_saturday_even_if_recent_and_within_clock_rth(self):
        """Regression for T2 review (Important): the old implementation
        only checked 09:30-16:00 ET clock time and had no weekday/holiday
        awareness, so a fresh snapshot with a Saturday `now` would
        incorrectly render "live". 2026-07-11 is a Saturday.
        """
        latest_ts = _ts("2026-07-11T14:30:00")  # 10:30 ET clock time
        now = datetime(2026, 7, 11, 15, 0, 0, tzinfo=timezone.utc)  # 11:00 ET, 30min later, Saturday
        assert main._most_active_label(latest_ts, "2026-07-11", now_utc=now) == "2026-07-11"

    def test_not_live_on_market_holiday_even_if_recent_and_within_clock_rth(self):
        """Same regression as the Saturday case, for a US market holiday.
        2026-07-03 (Independence Day, observed) is a Friday and is in
        live.MARKET_HOLIDAYS_2026, so it passes the weekday check but must
        still not report "live".
        """
        pytest.importorskip("api.routers.live")
        from api.routers import live as live_router
        assert __import__("datetime").date(2026, 7, 3) in live_router.MARKET_HOLIDAYS_2026

        latest_ts = _ts("2026-07-03T14:30:00")  # 10:30 ET clock time
        now = datetime(2026, 7, 3, 15, 0, 0, tzinfo=timezone.utc)  # 11:00 ET, 30min later
        assert main._most_active_label(latest_ts, "2026-07-03", now_utc=now) == "2026-07-03"
