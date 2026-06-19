"""
Platform API integration tests — verifies all endpoints used by the frontend.

Tests cover:
- Live-mode API contracts (Dashboard, LiveMarket, Charts, Signals pages)
- Historical review-mode API contracts (end_date/end_time filtering)
- Reference endpoint source routing (AlphaVantage vs Cloud SQL)
- Dashboard brief stale-data reporting
- Non-review page endpoints (Backtest, Playbook, Reports, Journal)
- Frontend route serving (SPA shell)
"""
import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

# Ensure project root is on sys.path so the platform API can import lib/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# Every test class in this file is hermetic: endpoints that read from
# Cloud SQL or GCS have their data-access layer monkeypatched with
# synthetic DataFrames / blob lists (and any module-level _CLOUD_SQL guard
# flipped to True), so they exercise the real route logic without a data
# backend. Nothing here is gated behind @requires_data_backend — the whole
# file runs in the no-DB CI `Run Tests` job.


@pytest.fixture(scope="module")
def client():
    """Create a TestClient for the FastAPI app (no live server needed)."""
    import os

    original_cwd = os.getcwd()
    platform_dir = str(PROJECT_ROOT / "platform")
    if platform_dir not in sys.path:
        sys.path.insert(0, platform_dir)
    os.chdir(platform_dir)

    from starlette.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        yield c

    # Restore cwd so subsequent test files aren't affected
    os.chdir(original_cwd)


# ── Health & Infrastructure ─────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "cloud_sql" in data
        # `data/` is gitignored (removed in f287259b); GCS is the source of
        # truth for raw files and Cloud SQL for structured queries. The
        # liveness check therefore reports lib/ presence, not data/.
        assert "lib_dir_exists" in data

    def test_live_status(self, client):
        r = client.get("/api/live/status")
        assert r.status_code == 200
        data = r.json()
        assert "is_open" in data
        assert "session" in data
        assert "current_time_et" in data


# ── Signals API ─────────────────────────────────────────────────────────────

# Hermetic: patches signals._CLOUD_SQL=True and gcp.database.query_to_dataframe
# so the /api/signals/{ticker} endpoint exercises its real Cloud SQL code path
# against synthetic DataFrames — no real Cloud SQL backend. Runs in no-DB CI.
class TestSignalsAPI:
    """`GET /api/signals/{ticker}` — historical signal list from Cloud SQL.

    The router calls `query_to_dataframe` twice: a COUNT(*) query, then a
    SELECT of the most-recent N rows (already sliced by the SQL WHERE for
    direction / min_score / end_date). Tests mock both so the response
    logic is exercised without a DB.
    """

    def _patch_query(self, monkeypatch, count_df, rows_df):
        """Force Cloud SQL mode and install a fake `query_to_dataframe` that
        returns the COUNT(*) df first, then the rows df.

        The endpoint applies direction / min_score / end_date filtering
        inside the SQL WHERE clause, so the mock returns rows already
        consistent with the request — the test's job is to assert the
        router's envelope and serialization, not re-implement SQL.
        """
        from gcp import database
        from api.routers import signals as signals_module

        monkeypatch.setattr(signals_module, "_CLOUD_SQL", True)

        calls = {"n": 0}

        def fake_query(sql, params=None):
            calls["n"] += 1
            return count_df.copy() if calls["n"] == 1 else rows_df.copy()

        monkeypatch.setattr(database, "query_to_dataframe", fake_query)
        return calls

    def test_signals_live(self, client, monkeypatch):
        count_df = pd.DataFrame([{"n": 3}])
        rows_df = pd.DataFrame([
            {"time": pd.Timestamp("2025-05-30 09:35:00"), "direction": "CALL",
             "close": 200.1, "rsi": 56.0, "ema9": 199.8, "ema20": 199.5,
             "volume": 120000, "score": 4, "conditions_met": 4, "return_pct": 0.8},
            {"time": pd.Timestamp("2025-05-30 10:05:00"), "direction": "PUT",
             "close": 201.3, "rsi": 41.0, "ema9": 201.0, "ema20": 201.4,
             "volume": 90000, "score": 3, "conditions_met": 3, "return_pct": -0.3},
            {"time": pd.Timestamp("2025-05-30 11:00:00"), "direction": "CALL",
             "close": 202.0, "rsi": 60.0, "ema9": 201.8, "ema20": 201.2,
             "volume": 150000, "score": 5, "conditions_met": 5, "return_pct": 1.4},
        ])
        self._patch_query(monkeypatch, count_df, rows_df)

        r = client.get("/api/signals/IWM?limit=5")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 3
        assert data["source"] == "cloud_sql"
        assert len(data["signals"]) == 3
        assert len(data["signals"]) <= 5
        # `time` is stringified by the router
        assert data["signals"][0]["time"] == "2025-05-30 09:35:00"
        assert data["signals"][0]["ticker"] == "IWM"

    def test_signals_with_direction_filter(self, client, monkeypatch):
        # The SQL filters direction server-side; the mock returns only CALLs.
        count_df = pd.DataFrame([{"n": 2}])
        rows_df = pd.DataFrame([
            {"time": pd.Timestamp("2025-05-30 09:35:00"), "direction": "CALL",
             "close": 200.1, "rsi": 56.0, "ema9": 199.8, "ema20": 199.5,
             "volume": 120000, "score": 4, "conditions_met": 4, "return_pct": 0.8},
            {"time": pd.Timestamp("2025-05-30 11:00:00"), "direction": "CALL",
             "close": 202.0, "rsi": 60.0, "ema9": 201.8, "ema20": 201.2,
             "volume": 150000, "score": 5, "conditions_met": 5, "return_pct": 1.4},
        ])
        self._patch_query(monkeypatch, count_df, rows_df)

        r = client.get("/api/signals/IWM?limit=5&direction=CALL")
        assert r.status_code == 200
        data = r.json()
        assert len(data["signals"]) == 2
        for s in data["signals"]:
            assert s["direction"] == "CALL"

    def test_signals_end_date_filter(self, client, monkeypatch):
        # The endpoint pushes the end_date cutoff into the SQL WHERE; the
        # mock returns rows already at/before the cutoff.
        count_df = pd.DataFrame([{"n": 1}])
        rows_df = pd.DataFrame([
            {"time": pd.Timestamp("2025-06-01 15:55:00"), "direction": "CALL",
             "close": 205.0, "rsi": 55.0, "ema9": 204.8, "ema20": 204.5,
             "volume": 110000, "score": 4, "conditions_met": 4, "return_pct": 0.5},
        ])
        self._patch_query(monkeypatch, count_df, rows_df)

        r = client.get("/api/signals/IWM?limit=5&end_date=2025-06-01")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        for s in data["signals"]:
            assert s["time"] <= "2025-06-01 23:59:59", f"Signal {s['time']} is after cutoff"

    def test_signals_end_date_and_time_filter(self, client, monkeypatch):
        count_df = pd.DataFrame([{"n": 1}])
        rows_df = pd.DataFrame([
            {"time": pd.Timestamp("2025-06-02 09:45:00"), "direction": "PUT",
             "close": 199.0, "rsi": 42.0, "ema9": 199.3, "ema20": 199.6,
             "volume": 80000, "score": 3, "conditions_met": 3, "return_pct": -0.2},
        ])
        self._patch_query(monkeypatch, count_df, rows_df)

        r = client.get("/api/signals/IWM?limit=5&end_date=2025-06-02&end_time=10:00")
        assert r.status_code == 200
        data = r.json()
        for s in data["signals"]:
            assert s["time"] <= "2025-06-02 10:00:00", f"Signal {s['time']} is after cutoff"

    def test_signals_empty_for_old_date(self, client, monkeypatch):
        """When the COUNT(*) query returns 0, the router short-circuits with
        an empty `signals: []` / `count: 0` envelope and never runs the
        rows query."""
        calls = self._patch_query(
            monkeypatch, pd.DataFrame([{"n": 0}]), pd.DataFrame()
        )

        r = client.get("/api/signals/IWM?limit=5&end_date=2014-01-01")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 0
        assert data["signals"] == []
        # Only the COUNT query ran — rows query is skipped on a 0 count.
        assert calls["n"] == 1


# ── Similar Signals API (analog matcher) ────────────────────────────────────

# NOTE: deliberately NOT decorated with @requires_data_backend. Every test
# in this class is hermetic — FastAPI Query-validation cases, the explicit
# _CLOUD_SQL=False 503 case, and the happy-path cases that mock
# query_to_dataframe AND patch _CLOUD_SQL=True via _patch_query. None of
# them touch a real Cloud SQL backend, so they must run in the no-DB CI
# `Run Tests` job — that's the whole point of mocking the query. Gating
# them behind @requires_data_backend silently skipped real /similar
# endpoint coverage in CI (Codex review, PR #501).
class TestSimilarSignalsAPI:
    """`GET /api/signals/{ticker}/similar` — historical analog matcher.

    Tests use monkeypatched `query_to_dataframe` so they don't depend on
    Cloud SQL state (any specific ticker's row count drifts as the
    historical_signals table grows).
    """

    def _patch_query(self, monkeypatch, stats_df, matches_df):
        """Install a fake `query_to_dataframe` that returns stats then
        matches in call order. Mirrors how the router invokes it.

        Also forces `signals._CLOUD_SQL = True`. The /similar endpoint
        503s up-front when `_CLOUD_SQL` is False (its no-DB guard), and
        `_CLOUD_SQL` is evaluated at import time from the Cloud SQL env
        vars — which are absent in the CI `Run Tests` job. Without this
        patch the guard short-circuits before the mocked query is ever
        reached, so the test would exercise the 503 path instead of the
        behavior under test."""
        from gcp import database
        from api.routers import signals as signals_module

        monkeypatch.setattr(signals_module, "_CLOUD_SQL", True)

        calls = {"n": 0}

        def fake_query(sql, params=None):
            calls["n"] += 1
            # Stats query is always called first; matches second
            return stats_df.copy() if calls["n"] == 1 else matches_df.copy()

        monkeypatch.setattr(database, "query_to_dataframe", fake_query)
        return calls

    def test_similar_invalid_direction_returns_400(self, client, monkeypatch):
        # Force _CLOUD_SQL=True so the endpoint reaches its direction
        # validation instead of 503-ing on the no-DB guard (CI's
        # Run Tests job has no Cloud SQL env vars).
        from api.routers import signals as signals_module
        monkeypatch.setattr(signals_module, "_CLOUD_SQL", True)

        r = client.get("/api/signals/IWM/similar?direction=BUY&rsi=55&score=4")
        assert r.status_code == 400
        assert "CALL or PUT" in r.json()["detail"]

    def test_similar_validates_score_range(self, client):
        # FastAPI Query(ge=3, le=5) — 6 is out of range
        r = client.get("/api/signals/IWM/similar?direction=CALL&rsi=55&score=6")
        assert r.status_code == 422
        # And below the minimum
        r = client.get("/api/signals/IWM/similar?direction=CALL&rsi=55&score=2")
        assert r.status_code == 422

    def test_similar_validates_rsi_band(self, client):
        # rsi_band must be in [0.5, 20.0]
        r = client.get(
            "/api/signals/IWM/similar?direction=CALL&rsi=55&score=4&rsi_band=25"
        )
        assert r.status_code == 422

    def test_similar_no_matches_returns_zero_count_shape(self, client, monkeypatch):
        """When the SQL returns 0 rows, the router short-circuits with
        a `stats: {count: 0}, matches: []` envelope."""
        empty_stats = pd.DataFrame([{
            "count": 0,
            "avg_mfe_pct": None, "median_mfe_pct": None,
            "p25_mfe_pct": None, "p75_mfe_pct": None,
            "avg_return_5min": None, "avg_return_20min": None,
            "pct_profitable": None,
            "earliest": None, "latest": None,
        }])
        self._patch_query(monkeypatch, empty_stats, pd.DataFrame())

        r = client.get(
            "/api/signals/IWM/similar?direction=CALL&rsi=55&score=4"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ticker"] == "IWM"
        assert data["direction"] == "CALL"
        assert data["stats"] == {"count": 0}
        assert data["matches"] == []

    def test_similar_returns_full_stats_and_matches(self, client, monkeypatch):
        """Happy path: populated stats payload + ordered match list.
        Verifies that pandas/numpy scalars become plain JSON-able floats."""
        stats = pd.DataFrame([{
            "count": 12,
            "avg_mfe_pct": 1.234,
            "median_mfe_pct": 1.0,
            "p25_mfe_pct": 0.5,
            "p75_mfe_pct": 1.8,
            "avg_return_5min": 0.42,
            "avg_return_20min": 0.71,
            "pct_profitable": 0.667,
            "earliest": pd.Timestamp("2023-01-04 14:30:00"),
            "latest": pd.Timestamp("2026-04-25 10:15:00"),
        }])
        matches = pd.DataFrame([
            {
                "time": pd.Timestamp("2026-04-25 10:15:00"),
                "direction": "CALL", "price": 222.5, "score": 4,
                "rsi": 56.2, "return_pct": 1.7,
                "return_5min": 0.4, "return_20min": 1.2,
            },
            {
                "time": pd.Timestamp("2026-04-22 11:00:00"),
                "direction": "CALL", "price": 219.1, "score": 4,
                "rsi": 54.0, "return_pct": -0.3,
                "return_5min": -0.1, "return_20min": -0.2,
            },
        ])
        self._patch_query(monkeypatch, stats, matches)

        r = client.get(
            "/api/signals/IWM/similar?direction=call&rsi=55&score=4&limit=5"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["direction"] == "CALL"  # uppercased
        assert data["stats"]["count"] == 12
        assert data["stats"]["pct_profitable"] == pytest.approx(0.667)
        assert data["stats"]["earliest"] == "2023-01-04 14:30:00"
        assert len(data["matches"]) == 2
        # `time` is stringified in the router
        assert data["matches"][0]["time"] == "2026-04-25 10:15:00"
        # Most-recent first
        assert data["matches"][0]["time"] > data["matches"][1]["time"]

    def test_similar_respects_503_when_cloud_sql_unconfigured(self, client, monkeypatch):
        """When `CLOUD_SQL_CONNECTION_NAME` is missing, the router
        returns 503 — never fakes data, never crashes."""
        from api.routers import signals as signals_module
        monkeypatch.setattr(signals_module, "_CLOUD_SQL", False)

        r = client.get(
            "/api/signals/IWM/similar?direction=CALL&rsi=55&score=4"
        )
        assert r.status_code == 503
        assert "Cloud SQL" in r.json()["detail"]


# ── Journal CRUD ────────────────────────────────────────────────────────────

class TestJournalCRUD:
    """`/api/journal/trades` — Cloud SQL CRUD with local fallback.

    The router has two code paths (`_HAS_CLOUD_SQL` ON/OFF). We test
    both: Cloud SQL with monkeypatched `execute_sql`/`query_to_dataframe`
    capturing the SQL+params, and local fallback with `tmp_path`.
    """

    def _patch_cloud_sql(self, monkeypatch, query_returns=None):
        """Force the journal router into Cloud SQL mode and capture every
        execute_sql + query_to_dataframe call."""
        from api.routers import journal as journal_module

        captured = {"execute": [], "query": []}

        def fake_execute(sql, params=None):
            captured["execute"].append((sql, dict(params or {})))

        def fake_query(sql, params=None):
            captured["query"].append((sql, dict(params or {})))
            if query_returns is None:
                return pd.DataFrame()
            return query_returns

        monkeypatch.setattr(journal_module, "_HAS_CLOUD_SQL", True)
        monkeypatch.setattr(journal_module, "execute_sql", fake_execute)
        monkeypatch.setattr(journal_module, "query_to_dataframe", fake_query)
        return captured

    def test_post_call_trade_round_trip_cloud_sql(self, client, monkeypatch):
        """POST a CALL trade → return_pct = (exit - entry) / entry × 100."""
        captured = self._patch_cloud_sql(
            monkeypatch,
            query_returns=pd.DataFrame([{"id": "abc-123"}]),
        )
        body = {
            "ticker": "iwm",
            "direction": "call",
            "entry_date": "2026-04-25",
            "entry_time": "10:00",
            "entry_price": 200.0,
            "exit_date": "2026-04-25",
            "exit_time": "10:30",
            "exit_price": 202.0,
            "notes": "test",
        }
        r = client.post("/api/journal/trades", json=body)
        assert r.status_code == 200
        data = r.json()
        assert data["source"] == "cloud_sql"
        assert data["id"] == "abc-123"
        # CALL: (202-200)/200*100 = +1.0
        assert data["return_pct"] == 1.0

        # Verify the SQL params
        ins_sql, ins_params = captured["execute"][0]
        assert "INSERT INTO journal_entries" in ins_sql
        assert ins_params["ticker"] == "IWM"  # uppercased
        assert ins_params["direction"] == "CALL"
        assert ins_params["entry_ts"] == "2026-04-25T10:00:00"
        assert ins_params["exit_ts"] == "2026-04-25T10:30:00"
        assert ins_params["return_pct"] == 1.0

    def test_post_put_trade_inverts_return_sign(self, client, monkeypatch):
        """PUT direction: a price DROP is a profit, so return_pct flips
        sign relative to the raw price diff. This is the load-bearing
        bug surface from the audit (`pct if "CALL" else -pct`)."""
        self._patch_cloud_sql(
            monkeypatch,
            query_returns=pd.DataFrame([{"id": "xyz"}]),
        )
        body = {
            "ticker": "QQQ",
            "direction": "PUT",
            "entry_date": "2026-04-25",
            "entry_time": "10:00",
            "entry_price": 400.0,
            "exit_date": "2026-04-25",
            "exit_time": "10:30",
            "exit_price": 396.0,  # price dropped — a profit on a PUT
            "notes": "",
        }
        r = client.post("/api/journal/trades", json=body)
        data = r.json()
        # Raw pct: (396-400)/400*100 = -1.0
        # PUT inverts → +1.0 (the trader profited)
        assert data["return_pct"] == 1.0

    def test_post_zero_entry_price_returns_zero_pct(self, client, monkeypatch):
        """Defensive: never divide by zero."""
        self._patch_cloud_sql(monkeypatch, query_returns=pd.DataFrame([{"id": "z"}]))
        body = {
            "ticker": "IWM", "direction": "CALL",
            "entry_date": "2026-04-25", "entry_time": "10:00",
            "entry_price": 0.0,
            "exit_date": "2026-04-25", "exit_time": "10:30",
            "exit_price": 5.0,
        }
        r = client.post("/api/journal/trades", json=body)
        assert r.json()["return_pct"] == 0.0

    def test_delete_round_trip_cloud_sql(self, client, monkeypatch):
        """DELETE issues a single SQL DELETE keyed on id + the signed-in owner."""
        captured = self._patch_cloud_sql(monkeypatch)
        r = client.delete("/api/journal/trades/abc-123")
        assert r.status_code == 200
        assert r.json() == {"source": "cloud_sql", "deleted": "abc-123"}
        del_sql, del_params = captured["execute"][0]
        assert "DELETE FROM journal_entries" in del_sql
        # Now scoped to the owner so a user can't delete another's entry; no auth
        # in this test → the open/local-dev "local" owner.
        assert "user_email = :user_email" in del_sql
        assert del_params == {"id": "abc-123", "user_email": "local"}

    def test_post_falls_back_to_local_on_cloud_sql_failure(self, client, monkeypatch, tmp_path):
        """If Cloud SQL throws, the router writes to a local JSON file
        keyed by ticker (the gitignored `data/journal/{ticker}_journal.json`)."""
        from api.routers import journal as journal_module

        # Force Cloud SQL "ON" but make execute_sql raise
        monkeypatch.setattr(journal_module, "_HAS_CLOUD_SQL", True)
        monkeypatch.setattr(
            journal_module, "execute_sql",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("DB down")),
        )
        # Redirect the local journal dir to tmp_path so we don't pollute
        # the real data/ directory
        monkeypatch.setattr(journal_module, "LOCAL_JOURNAL_DIR", tmp_path)

        body = {
            "ticker": "IWM", "direction": "CALL",
            "entry_date": "2026-04-25", "entry_time": "10:00",
            "entry_price": 200.0,
            "exit_date": "2026-04-25", "exit_time": "10:30",
            "exit_price": 202.0,
        }
        r = client.post("/api/journal/trades", json=body)
        assert r.status_code == 200
        data = r.json()
        assert data["source"] == "local"
        assert data["return_pct"] == 1.0
        # Local file written
        local_file = tmp_path / "iwm_journal.json"
        assert local_file.exists()
        entries = json.loads(local_file.read_text())
        assert len(entries) == 1
        assert entries[0]["ticker"] == "IWM"


# ── Market Data API ─────────────────────────────────────────────────────────

# Hermetic: patches api.main._CLOUD_SQL=True and api.main.query_to_dataframe
# so the /api/market/* endpoints exercise their real Cloud SQL code path
# against synthetic intraday DataFrames — no real Cloud SQL backend.
class TestMarketDataAPI:
    """`/api/market/dates/{ticker}` and `/api/market/data/{ticker}/{date}` —
    both read `market_data_intraday` from Cloud SQL in `api.main`.

    The endpoints bind `query_to_dataframe` and `_CLOUD_SQL` at module
    import time, so tests patch them on the `api.main` module object.
    """

    def _patch_intraday(self, monkeypatch, df):
        """Force Cloud SQL ON in api.main and install a fake
        `query_to_dataframe` returning `df` for every call.

        `_load_date_data` and `get_available_dates` both run the same
        query_to_dataframe; a single canned df satisfies both because the
        intraday-bars shape (`ts, open, high, low, close, volume`) is a
        superset of the dates query (`DATE(ts)`). The dates endpoint is
        tested separately with a date-shaped df below."""
        import api.main as main_module

        monkeypatch.setattr(main_module, "_CLOUD_SQL", True)
        monkeypatch.setattr(main_module, "query_to_dataframe", lambda *a, **k: df.copy())

    def _intraday_day_df(self, date_str="2026-02-20", n_bars=120):
        """Build a synthetic 1-min intraday bar DataFrame matching the
        `market_data_intraday` SELECT shape (ts/open/high/low/close/volume/
        data_source). RTH starting 09:30 ET."""
        ts = pd.date_range(f"{date_str} 09:30:00", periods=n_bars, freq="1min")
        return pd.DataFrame({
            "ts": ts,
            "open": [200.0 + i * 0.01 for i in range(n_bars)],
            "high": [200.2 + i * 0.01 for i in range(n_bars)],
            "low": [199.8 + i * 0.01 for i in range(n_bars)],
            "close": [200.1 + i * 0.01 for i in range(n_bars)],
            "volume": [50000 + i * 10 for i in range(n_bars)],
            "data_source": ["alphavantage"] * n_bars,
        })

    def test_market_dates(self, client, monkeypatch):
        import api.main as main_module
        monkeypatch.setattr(main_module, "_CLOUD_SQL", True)
        # DISTINCT DATE(ts) AS trade_date — one row per trading day
        dates_df = pd.DataFrame({
            "trade_date": [
                pd.Timestamp("2026-02-20").date(),
                pd.Timestamp("2026-02-19").date(),
                pd.Timestamp("2026-01-15").date(),
            ],
        })
        monkeypatch.setattr(main_module, "query_to_dataframe", lambda *a, **k: dates_df.copy())

        r = client.get("/api/market/dates/IWM")
        assert r.status_code == 200
        data = r.json()
        assert data["source"] == "cloud_sql"
        assert data["dates"] == ["20260220", "20260219", "20260115"]
        # months derived from the dates, descending
        assert data["months"] == ["202602", "202601"]

    def test_market_data_full_day(self, client, monkeypatch):
        """Fetch a full day of 1-min bars."""
        self._patch_intraday(monkeypatch, self._intraday_day_df(n_bars=120))

        r = client.get("/api/market/data/IWM/20260220?timeframe=1")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 120
        assert len(data["candlestick"]) == data["count"]
        assert len(data["volume"]) == data["count"]

    def test_market_data_end_time_filter(self, client, monkeypatch):
        """Fetch bars sliced to a specific time — should return fewer bars."""
        self._patch_intraday(monkeypatch, self._intraday_day_df(n_bars=120))
        full = client.get("/api/market/data/IWM/20260220?timeframe=1")
        assert full.status_code == 200

        # 120 bars from 09:30 → 11:29; cutoff 10:30 keeps 09:30..10:30 (61 bars)
        sliced = client.get("/api/market/data/IWM/20260220?timeframe=1&end_time=10:30")
        assert sliced.status_code == 200
        full_count = full.json()["count"]
        sliced_count = sliced.json()["count"]
        assert sliced_count < full_count, f"Sliced ({sliced_count}) should be < full ({full_count})"
        assert sliced_count > 0
        assert sliced_count == 61

    def test_market_data_end_time_invalid_format(self, client, monkeypatch):
        self._patch_intraday(monkeypatch, self._intraday_day_df(n_bars=30))
        r = client.get("/api/market/data/IWM/20260220?timeframe=1&end_time=invalid")
        assert r.status_code == 400

    def test_market_data_404_when_no_rows(self, client, monkeypatch):
        """An empty intraday df with no GCS fallback → 404 (no data for
        that date). `_load_date_data` falls through to GCS when Cloud SQL
        returns 0 rows, so `blob_exists` is stubbed False to keep the test
        hermetic — the FileNotFoundError it raises becomes a 404."""
        self._patch_intraday(monkeypatch, pd.DataFrame(
            columns=["ts", "open", "high", "low", "close", "volume", "data_source"]
        ))
        from api import gcs_reader
        monkeypatch.setattr(gcs_reader, "blob_exists", lambda *a, **k: False)
        r = client.get("/api/market/data/IWM/20260220?timeframe=1")
        assert r.status_code == 404


# ── Dashboard Brief API ─────────────────────────────────────────────────────

# Hermetic: patches dashboard._CLOUD_SQL=True + dashboard._query_fn so the
# /api/dashboard/brief endpoint runs its real Cloud SQL aggregation against
# synthetic premarket_analysis / market_data_daily DataFrames. Also covers
# the explicit source='unavailable' no-DB path.
class TestDashboardBriefAPI:
    """`GET /api/dashboard/brief/{ticker}` — daily bias card from Cloud SQL.

    The router calls `_query_fn` (bound at import) once for
    `premarket_analysis` and once for `market_data_daily`. Tests install a
    fake `_query_fn` that returns those two DataFrames in call order.
    """

    def _patch_query(self, monkeypatch, premarket_df, daily_df):
        """Force Cloud SQL ON and feed premarket then daily DataFrames."""
        from api.routers import dashboard as dash_module

        monkeypatch.setattr(dash_module, "_CLOUD_SQL", True)

        calls = {"n": 0}

        def fake_query(sql, params=None):
            calls["n"] += 1
            return premarket_df.copy() if calls["n"] == 1 else daily_df.copy()

        monkeypatch.setattr(dash_module, "_query_fn", fake_query)
        return calls

    def test_brief_live(self, client, monkeypatch):
        premarket = pd.DataFrame([{
            "analysis_date": "2026-05-15", "price": 205.0, "rsi": 58.3,
            "rsi_direction": "up", "consecutive_up": 2, "consecutive_down": 0,
            "signal_status": "watch", "strat_candle": "2U", "strat_combo": None,
            "strat_setup": True, "ftfc_score": 0.75, "ftfc_direction": "bullish",
        }])
        daily = pd.DataFrame([{
            "date": "2026-05-15", "close": 205.0, "rsi_14": 58.3, "ema_9": 204.0,
            "ema_20": 203.0, "sma_200": 195.0, "macd": 0.12, "bb_upper": 210.0,
            "bb_lower": 200.0, "atr_14": 1.8, "rvol": 1.1, "strat_candle": "2U",
            "strat_combo": None, "strat_setup": True, "ftfc_score": 0.75,
            "ftfc_direction": "bullish", "consecutive_up": 2, "consecutive_down": 0,
            "price_vs_ema9": 0.5, "price_vs_ema20": 1.0,
        }])
        self._patch_query(monkeypatch, premarket, daily)

        r = client.get("/api/dashboard/brief/IWM?date=2026-05-15")
        assert r.status_code == 200
        data = r.json()
        assert data["ticker"] == "IWM"
        assert data["source"] == "cloud_sql"
        assert data["bias"] == "bullish"  # ftfc_direction=bullish
        assert data["has_premarket"] is True

    def test_brief_with_historical_date(self, client, monkeypatch):
        # daily df dated on/before the requested date
        daily = pd.DataFrame([{
            "date": "2020-03-13", "close": 120.0, "rsi_14": 30.0, "ema_9": 125.0,
            "ema_20": 130.0, "sma_200": 150.0, "macd": -1.2, "bb_upper": 160.0,
            "bb_lower": 110.0, "atr_14": 5.0, "rvol": 2.5, "strat_candle": "2D",
            "strat_combo": None, "strat_setup": False, "ftfc_score": -0.8,
            "ftfc_direction": "bearish", "consecutive_up": 0, "consecutive_down": 3,
            "price_vs_ema9": -4.0, "price_vs_ema20": -7.7,
        }])
        self._patch_query(monkeypatch, pd.DataFrame(), daily)

        r = client.get("/api/dashboard/brief/IWM?date=2020-03-16")
        assert r.status_code == 200
        data = r.json()
        assert data["source"] == "cloud_sql"
        di = data["daily_indicators"]
        assert di["date"] is not None
        # Should return data on or before the requested date
        assert di["date"] <= "2020-03-16"

    def test_brief_stale_days_present(self, client, monkeypatch):
        """When Cloud SQL is available, daily_indicators includes stale_days."""
        daily = pd.DataFrame([{
            "date": "2026-05-15", "close": 205.0, "rsi_14": 58.3, "ema_9": 204.0,
            "ema_20": 203.0, "sma_200": 195.0, "macd": 0.12, "bb_upper": 210.0,
            "bb_lower": 200.0, "atr_14": 1.8, "rvol": 1.1, "strat_candle": "2U",
            "strat_combo": None, "strat_setup": True, "ftfc_score": 0.75,
            "ftfc_direction": "bullish", "consecutive_up": 2, "consecutive_down": 0,
            "price_vs_ema9": 0.5, "price_vs_ema20": 1.0,
        }])
        self._patch_query(monkeypatch, pd.DataFrame(), daily)

        r = client.get("/api/dashboard/brief/IWM?date=2026-05-15")
        assert r.status_code == 200
        data = r.json()
        assert data["source"] == "cloud_sql"
        assert "stale_days" in data["daily_indicators"]

    def test_brief_unavailable_source(self, client, monkeypatch):
        """When Cloud SQL is OFF the router returns source='unavailable'
        with an explicit reason — no silent fallback."""
        from api.routers import dashboard as dash_module
        monkeypatch.setattr(dash_module, "_CLOUD_SQL", False)
        monkeypatch.setattr(dash_module, "_query_fn", None)

        r = client.get("/api/dashboard/brief/IWM")
        assert r.status_code == 200
        data = r.json()
        assert data["source"] == "unavailable"
        assert "reason" in data


# ── Reference Levels API ────────────────────────────────────────────────────

# Hermetic: patches api.main._fetch_av_daily_reference, api.main._CLOUD_SQL
# and api.main.query_to_dataframe so /api/market/reference exercises both the
# AlphaVantage-recent and Cloud-SQL-historical source-routing branches with
# synthetic data — no real AV HTTP call, no Cloud SQL.
class TestReferenceAPI:
    """`GET /api/market/reference/{ticker}/{date}` — previous-day OHLC.

    Source routing: AV for dates within ~30 days, Cloud SQL
    `market_data_daily` for older dates. Tests mock each source.
    """

    def test_reference_recent_uses_alphavantage(self, client, monkeypatch):
        """Recent dates (< 30 days ago) prefer AlphaVantage."""
        import api.main as main_module
        from datetime import date, timedelta

        # A date 2 days ago is "recent" → endpoint hits the AV branch.
        recent = (date.today() - timedelta(days=2)).strftime("%Y%m%d")

        monkeypatch.setattr(main_module, "_fetch_av_daily_reference", lambda t, d: {
            "date": "20260512", "open": 204.0, "high": 206.5,
            "low": 203.0, "close": 205.8,
        })
        # Week range goes through Cloud SQL — keep it OFF so week is None.
        monkeypatch.setattr(main_module, "_CLOUD_SQL", False)

        r = client.get(f"/api/market/reference/IWM/{recent}")
        assert r.status_code == 200
        data = r.json()
        assert data["source"] == "alphavantage"
        assert data["date"] == "20260512"
        assert data["high"] == 206.5
        assert data["low"] == 203.0
        assert data["close"] == 205.8

    def test_reference_historical_uses_cloud_sql(self, client, monkeypatch):
        """Old dates (> 30 days ago) use Cloud SQL `market_data_daily`."""
        import api.main as main_module

        monkeypatch.setattr(main_module, "_CLOUD_SQL", True)
        # First query: prev-day row (ORDER BY date DESC LIMIT 1).
        # Second query (_fetch_week_range): 5-row window — give it < 2 rows
        # so it returns None and we don't have to model the week shape.
        prev_day = pd.DataFrame([{
            "date": pd.Timestamp("2020-03-13").date(),
            "open": 121.0, "high": 125.0, "low": 118.0, "close": 120.5,
        }])
        calls = {"n": 0}

        def fake_query(sql, params=None):
            calls["n"] += 1
            return prev_day.copy() if calls["n"] == 1 else pd.DataFrame()

        monkeypatch.setattr(main_module, "query_to_dataframe", fake_query)

        r = client.get("/api/market/reference/IWM/20200316")
        assert r.status_code == 200
        data = r.json()
        assert data["source"] == "cloud_sql"
        assert data["date"] == "20200313"
        assert data["date"] < "20200316"  # prev day before Mar 16
        assert data["close"] == 120.5

    def test_reference_returns_prev_day(self, client, monkeypatch):
        """Should return the day BEFORE the requested date, not the date itself."""
        import api.main as main_module
        monkeypatch.setattr(main_module, "_CLOUD_SQL", True)
        prev_day = pd.DataFrame([{
            "date": pd.Timestamp("2020-03-13").date(),
            "open": 121.0, "high": 125.0, "low": 118.0, "close": 120.5,
        }])
        calls = {"n": 0}

        def fake_query(sql, params=None):
            calls["n"] += 1
            return prev_day.copy() if calls["n"] == 1 else pd.DataFrame()

        monkeypatch.setattr(main_module, "query_to_dataframe", fake_query)

        r = client.get("/api/market/reference/IWM/20200316")
        assert r.status_code == 200
        data = r.json()
        assert data["date"] != "20200316", "Should return previous day, not same day"


# ── Backtest API ────────────────────────────────────────────────────────────

# Hermetic: patches api.routers.backtest.gcs_reader (list_matching_blobs +
# download_csv) so the /api/backtest/* endpoints parse synthetic backtest /
# equity CSVs — no real GCS download. Module-level TTL caches are cleared
# before each test so a prior case can't leak a cached response.
class TestBacktestAPI:
    """`/api/backtest/{results,equity,all}/{ticker}` — read backtest CSVs
    from GCS via `api.gcs_reader`. Tests mock the GCS reader."""

    def _clear_caches(self):
        from api.routers import backtest as bt_module
        bt_module._RESULTS_CACHE.clear()
        bt_module._EQUITY_CACHE.clear()
        bt_module._ALL_RUNS_CACHE.clear()

    def test_backtest_results(self, client, monkeypatch):
        from api.routers import backtest as bt_module
        self._clear_caches()

        # 4 trades — 3 wins, 1 loss → win_rate 0.75
        trades_df = pd.DataFrame([
            {"entry_time": "2015-01-02 09:30:00", "exit_time": "2015-01-02 10:00:00",
             "direction": "CALL", "entry_price": 120.0, "exit_price": 121.0,
             "return_pct": 0.83},
            {"entry_time": "2015-01-05 09:45:00", "exit_time": "2015-01-05 10:30:00",
             "direction": "PUT", "entry_price": 119.0, "exit_price": 118.0,
             "return_pct": 0.84},
            {"entry_time": "2015-01-06 11:00:00", "exit_time": "2015-01-06 11:30:00",
             "direction": "CALL", "entry_price": 121.5, "exit_price": 120.0,
             "return_pct": -1.23},
            {"entry_time": "2015-01-07 14:00:00", "exit_time": "2015-01-07 15:00:00",
             "direction": "CALL", "entry_price": 122.0, "exit_price": 123.0,
             "return_pct": 0.82},
        ])
        monkeypatch.setattr(
            bt_module.gcs_reader, "list_matching_blobs",
            lambda prefix, pattern: ["raw/data/backtest_results/backtest_IWM_20260221_161724.csv"],
        )
        monkeypatch.setattr(
            bt_module.gcs_reader, "download_csv", lambda blob: trades_df.copy()
        )

        r = client.get("/api/backtest/results/IWM")
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data
        assert "trades" in data
        s = data["summary"]
        assert s["total_trades"] == 4
        assert 0 <= s["win_rate"] <= 1
        assert s["win_rate"] == 0.75

    def test_backtest_equity(self, client, monkeypatch):
        from api.routers import backtest as bt_module
        self._clear_caches()

        # Equity CSV: "Unnamed: 0" date col + "0" value col.
        # Peak 10250 at index 1; trough 9840 afterwards → drawdown the
        # endpoint measures is from the global peak FORWARD.
        equity_df = pd.DataFrame({
            "Unnamed: 0": ["2015-01-02", "2015-01-05", "2015-01-06", "2015-01-07"],
            "0": [10000.0, 10250.0, 9840.0, 10100.0],
        })
        monkeypatch.setattr(
            bt_module.gcs_reader, "list_matching_blobs",
            lambda prefix, pattern: ["raw/data/backtest_results/equity_IWM_20260221_161724.csv"],
        )
        monkeypatch.setattr(
            bt_module.gcs_reader, "download_csv", lambda blob: equity_df.copy()
        )

        r = client.get("/api/backtest/equity/IWM")
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data
        assert "dates" in data
        assert "values" in data
        assert "max_drawdown_pct" in data["summary"]
        assert data["values"] == [10000.0, 10250.0, 9840.0, 10100.0]
        # peak 10250 → trough 9840 after peak → drawdown = (9840-10250)/10250
        assert data["summary"]["max_drawdown_pct"] == pytest.approx(-4.0, abs=1e-3)

    def test_backtest_all_runs(self, client, monkeypatch):
        from api.routers import backtest as bt_module
        self._clear_caches()

        trades_df = pd.DataFrame([
            {"return_pct": 1.0}, {"return_pct": -0.5}, {"return_pct": 0.8},
        ])

        def fake_list(prefix, pattern):
            # backtest pattern vs equity pattern — return the matching set
            if "equity" in pattern:
                return []
            return ["raw/data/backtest_results/backtest_IWM_20260221_161724.csv"]

        monkeypatch.setattr(bt_module.gcs_reader, "list_matching_blobs", fake_list)
        monkeypatch.setattr(
            bt_module.gcs_reader, "download_csv", lambda blob: trades_df.copy()
        )

        r = client.get("/api/backtest/all/IWM")
        assert r.status_code == 200
        data = r.json()
        assert "runs" in data
        assert data["total_runs"] == 1
        assert data["runs"][0]["trade_count"] == 3

    def test_backtest_results_404_when_no_blobs(self, client, monkeypatch):
        """No backtest CSV in GCS → 404."""
        from api.routers import backtest as bt_module
        self._clear_caches()
        monkeypatch.setattr(
            bt_module.gcs_reader, "list_matching_blobs", lambda prefix, pattern: []
        )
        r = client.get("/api/backtest/results/NOPE")
        assert r.status_code == 404

    def test_backtest_trade_entry_time_format(self, client, monkeypatch):
        """Verify entry_time is a string in YYYY-MM-DD HH:MM:SS format for frontend filtering."""
        from api.routers import backtest as bt_module
        self._clear_caches()
        trades_df = pd.DataFrame([
            {"entry_time": "2015-01-02 09:30:00", "direction": "CALL",
             "entry_price": 120.0, "exit_price": 121.0, "return_pct": 0.83},
        ])
        monkeypatch.setattr(
            bt_module.gcs_reader, "list_matching_blobs",
            lambda prefix, pattern: ["raw/data/backtest_results/backtest_IWM_20260221_161724.csv"],
        )
        monkeypatch.setattr(
            bt_module.gcs_reader, "download_csv", lambda blob: trades_df.copy()
        )

        r = client.get("/api/backtest/results/IWM")
        assert r.status_code == 200
        assert r.json()["trades"]
        t = r.json()["trades"][0]
        assert "entry_time" in t
        # Format: "2015-01-02 09:30:00"
        assert len(t["entry_time"]) >= 19, f"Unexpected entry_time format: {t['entry_time']}"
        assert t["entry_time"][4] == "-" and t["entry_time"][10] == " "


# ── Playbook API ────────────────────────────────────────────────────────────

# Hermetic: patches api.routers.playbook.gcs_reader (download_text +
# list_matching_blobs) so /api/playbook and /api/reports/list parse a
# synthetic markdown playbook / blob list — no real GCS. Module caches
# are cleared per test.
class TestPlaybookAPI:
    """`/api/playbook/{ticker}` (parses a phase6 markdown file) and
    `/api/reports/list/{ticker}` (lists phase report blobs). Both read GCS
    via `api.gcs_reader`."""

    def _clear_caches(self):
        from api.routers import playbook as pb_module
        pb_module._PLAYBOOK_CACHE.clear()
        pb_module._LIST_CACHE.clear()
        pb_module._REPORT_TEXT_CACHE.clear()

    def test_playbook(self, client, monkeypatch):
        from api.routers import playbook as pb_module
        self._clear_caches()

        # Minimal phase6 playbook markdown with one card the parser
        # recognises: a ### heading + "-> CALL ENTRY" + a win rate.
        markdown = (
            "# Phase 6 Playbook IWM\n\n"
            "### Morning Trend Continuation\n\n"
            "**WHAT YOU SEE ON THE CHART:**\n"
            "  * Price riding above EMA9\n"
            "  * Higher highs since the open\n\n"
            "**WHAT TO CHECK:**\n"
            "- [ ] Price above VWAP\n"
            "- [ ] RSI between 50-70\n\n"
            "**IF ALL CONFIRMED -> CALL ENTRY**\n\n"
            "Historical win rate: 62.5%\n"
            "Avg return: 8.0 bps\n"
        )
        monkeypatch.setattr(
            pb_module.gcs_reader, "download_text", lambda blob: markdown
        )

        r = client.get("/api/playbook/IWM")
        assert r.status_code == 200
        data = r.json()
        assert data["ticker"] == "IWM"
        assert "cards" in data
        assert len(data["cards"]) == 1
        card = data["cards"][0]
        assert card["name"] == "Morning Trend Continuation"
        assert card["direction"] == "CALL"
        assert card["direction"] in ("CALL", "PUT", "NEUTRAL")
        assert card["win_rate"] == 62.5

    def test_reports_list(self, client, monkeypatch):
        from api.routers import playbook as pb_module
        self._clear_caches()

        # list_matching_blobs is called twice: ticker-specific, then all-phases.
        def fake_list(prefix, pattern):
            if "iwm" in pattern:  # ticker-specific match
                return ["raw/reports/phase4_summary_iwm.md"]
            return ["raw/reports/phase4_summary_iwm.md", "raw/reports/phase1_overview.md"]

        monkeypatch.setattr(pb_module.gcs_reader, "list_matching_blobs", fake_list)

        r = client.get("/api/reports/list/IWM")
        assert r.status_code == 200
        data = r.json()
        assert data["ticker"] == "IWM"
        assert "reports" in data
        filenames = {rep["filename"] for rep in data["reports"]}
        assert "phase4_summary_iwm.md" in filenames

    def test_reports_list_404_when_empty(self, client, monkeypatch):
        """No report blobs in GCS → 404."""
        from api.routers import playbook as pb_module
        self._clear_caches()
        monkeypatch.setattr(
            pb_module.gcs_reader, "list_matching_blobs", lambda prefix, pattern: []
        )
        r = client.get("/api/reports/list/ZZZ")
        assert r.status_code == 404


# ── /api/health/freshness ───────────────────────────────────────────────────

# Hermetic: every test monkeypatches `audit_data_freshness.audit_all` with a
# fake report (or an exception), so the endpoint never touches Cloud SQL.
# Runs in the no-DB CI `Run Tests` job.
class TestHealthFreshnessAPI:
    """`GET /api/health/freshness` — wraps `scripts/audit_data_freshness.py`.

    The endpoint has a module-level 5-minute TTL cache. Tests must reset
    `_cache_value` between cases or stale results leak across.
    """

    def _reset_cache(self):
        from api.routers import health as health_module
        health_module._cache_value = None
        health_module._cache_expires_at = 0.0

    def test_freshness_returns_audit_dict(self, client, monkeypatch):
        from api.routers import health as health_module
        self._reset_cache()

        # Build a fake report via the real dataclass so the to_dict()
        # call inside the route matches production shape.
        import audit_data_freshness as audit_mod

        rows = [audit_mod.FreshnessRow(
            table="market_data_daily", ticker="IWM",
            last_row_at="2026-04-13", expected_latest="2026-04-13",
            lag_hours=2.5, expected_max_hours=24,
            status="ok", row_count_recent=1,
        )]
        rep = audit_mod.FreshnessReport(
            checked_at="2026-04-14T03:30:00.000Z",
            expected_market_close="2026-04-13",
            rows=rows,
        )
        monkeypatch.setattr(audit_mod, "audit_all", lambda: rep)

        r = client.get("/api/health/freshness")
        assert r.status_code == 200
        data = r.json()
        assert data["overall_status"] == "ok"
        assert data["expected_market_close"] == "2026-04-13"
        assert len(data["tables"]) == 1
        assert data["tables"][0]["table"] == "market_data_daily"

    def test_freshness_caches_for_ttl(self, client, monkeypatch):
        """Second call within TTL doesn't re-run the audit (the audit
        touches Cloud SQL — caching avoids a hit per dashboard render)."""
        from api.routers import health as health_module
        self._reset_cache()

        import audit_data_freshness as audit_mod

        call_count = {"n": 0}

        def fake_audit():
            call_count["n"] += 1
            return audit_mod.FreshnessReport(
                checked_at="x", expected_market_close="y", rows=[],
            )

        monkeypatch.setattr(audit_mod, "audit_all", fake_audit)

        r1 = client.get("/api/health/freshness")
        r2 = client.get("/api/health/freshness")
        assert r1.status_code == 200 and r2.status_code == 200
        assert call_count["n"] == 1, "second call must hit the TTL cache"

    def test_freshness_500_on_audit_exception(self, client, monkeypatch):
        """If `audit_all` raises, the route surfaces a 500 with detail —
        not a silent 200 with stale data."""
        from api.routers import health as health_module
        self._reset_cache()

        import audit_data_freshness as audit_mod
        monkeypatch.setattr(
            audit_mod, "audit_all",
            lambda: (_ for _ in ()).throw(RuntimeError("DB down")),
        )

        r = client.get("/api/health/freshness")
        assert r.status_code == 500
        assert "DB down" in r.json()["detail"]

    def test_freshness_cache_does_not_persist_500(self, client, monkeypatch):
        """An exception from `audit_all` must NOT poison the cache —
        the next request after recovery should re-run the audit."""
        from api.routers import health as health_module
        self._reset_cache()

        import audit_data_freshness as audit_mod
        rep = audit_mod.FreshnessReport(
            checked_at="x", expected_market_close="y", rows=[],
        )

        # First call raises
        monkeypatch.setattr(
            audit_mod, "audit_all",
            lambda: (_ for _ in ()).throw(RuntimeError("transient")),
        )
        r1 = client.get("/api/health/freshness")
        assert r1.status_code == 500

        # Second call succeeds — cache must not have stored the failure
        monkeypatch.setattr(audit_mod, "audit_all", lambda: rep)
        r2 = client.get("/api/health/freshness")
        assert r2.status_code == 200


# ── Phase-report markdown fetch ─────────────────────────────────────────────

# Hermetic: every test monkeypatches `gcs_reader.list_matching_blobs` /
# `download_text`, so the endpoint never touches real GCS. Runs in no-DB CI.
class TestReportMarkdownAPI:
    """`GET /api/reports/{ticker}/{phase}` — raw markdown text from GCS.

    Mocks `gcs_reader.list_matching_blobs` + `download_text` so tests
    don't depend on which phase reports happen to be stored in GCS.
    """

    def test_returns_404_when_no_matching_phase(self, client, monkeypatch):
        from api.routers import playbook as pb_module

        # Both lookups return nothing → 404
        monkeypatch.setattr(
            pb_module.gcs_reader, "list_matching_blobs",
            lambda prefix, pattern: [],
        )
        # Also clear the route cache so a previous test doesn't poison this one
        pb_module._REPORT_TEXT_CACHE.clear()
        r = client.get("/api/reports/IWM/phase99_summary")
        assert r.status_code == 404

    def test_returns_plaintext_markdown_when_blob_exists(self, client, monkeypatch):
        from api.routers import playbook as pb_module

        markdown = "# Backtest Results\n\nStrategy Parameters\n..."
        monkeypatch.setattr(
            pb_module.gcs_reader, "list_matching_blobs",
            lambda prefix, pattern: ["raw/data/reports/phase4_summary_iwm.md"],
        )
        # `download_text` is the GCS read used by this endpoint
        monkeypatch.setattr(
            pb_module.gcs_reader, "download_text",
            lambda blob_name: markdown,
        )
        pb_module._REPORT_TEXT_CACHE.clear()

        r = client.get("/api/reports/IWM/phase4_summary")
        assert r.status_code == 200
        # PlainTextResponse → not JSON
        assert r.headers["content-type"].startswith("text/plain")
        assert "# Backtest Results" in r.text


# ── Insights watchlist (catalyst ranker output) ─────────────────────────────

# Hermetic: every test monkeypatches `lib.agents.ranker.rank_tickers`, so the
# endpoint's deterministic SQL+Python ranker is never actually invoked against
# Cloud SQL. Runs in the no-DB CI `Run Tests` job.
class TestInsightsWatchlistAPI:
    """`GET /api/insights/watchlist` — wraps `lib.agents.ranker.rank_tickers`.

    No LLM, just SQL+Python. Tests patch `rank_tickers` directly so
    we don't depend on Cloud SQL state.
    """

    def test_watchlist_returns_ranked_tickers(self, client, monkeypatch):
        from api.routers import insights as insights_module

        called_with = {}

        def fake_rank(**kwargs):
            called_with.update(kwargs)
            return {
                "as_of": "2026-04-25",
                "count": 2,
                "tickers": [
                    {"ticker": "AAPL", "score": 0.81, "breakdown": {}},
                    {"ticker": "MSFT", "score": 0.74, "breakdown": {}},
                ],
            }

        # Patch the late-imported reference in the route
        monkeypatch.setattr(
            "lib.agents.ranker.rank_tickers", fake_rank
        )

        r = client.get("/api/insights/watchlist?limit=2")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 2
        assert [t["ticker"] for t in data["tickers"]] == ["AAPL", "MSFT"]
        # The route clamps limit into [1, 50]
        assert called_with["limit"] == 2

    def test_watchlist_clamps_limit_to_50(self, client, monkeypatch):
        called_with = {}

        def fake_rank(**kwargs):
            called_with.update(kwargs)
            return {"as_of": "2026-04-25", "count": 0, "tickers": []}

        monkeypatch.setattr("lib.agents.ranker.rank_tickers", fake_rank)
        r = client.get("/api/insights/watchlist?limit=999")
        assert r.status_code == 200
        assert called_with["limit"] == 50

    def test_watchlist_parses_catalyst_filter_csv(self, client, monkeypatch):
        called_with = {}

        def fake_rank(**kwargs):
            called_with.update(kwargs)
            return {"as_of": "x", "count": 0, "tickers": []}

        monkeypatch.setattr("lib.agents.ranker.rank_tickers", fake_rank)
        r = client.get(
            "/api/insights/watchlist?catalyst=earnings,sec_8k,top_mover"
        )
        assert r.status_code == 200
        assert called_with["catalyst_filter"] == {
            "earnings", "sec_8k", "top_mover"
        }

    def test_watchlist_extras_uppercased_and_split(self, client, monkeypatch):
        called_with = {}

        def fake_rank(**kwargs):
            called_with.update(kwargs)
            return {"as_of": "x", "count": 0, "tickers": []}

        monkeypatch.setattr("lib.agents.ranker.rank_tickers", fake_rank)
        r = client.get("/api/insights/watchlist?extras=avgo,nvda,tsla")
        assert r.status_code == 200
        assert called_with["extras"] == ["AVGO", "NVDA", "TSLA"]

    def test_watchlist_expand_universe_default_false(self, client, monkeypatch):
        """The watchlist gate is the default — `expand=False` in the
        route signature mirrors the ranker default. Critical: an
        accidental flip to True would balloon the candidate pool to
        ~1871 tickers and time out the morning brief."""
        called_with = {}

        def fake_rank(**kwargs):
            called_with.update(kwargs)
            return {"as_of": "x", "count": 0, "tickers": []}

        monkeypatch.setattr("lib.agents.ranker.rank_tickers", fake_rank)
        client.get("/api/insights/watchlist")
        assert called_with["expand_universe"] is False


# ── Journal API ─────────────────────────────────────────────────────────────

class TestJournalAPI:
    def test_journal_list(self, client):
        r = client.get("/api/journal/trades/IWM")
        assert r.status_code == 200
        data = r.json()
        assert "trades" in data
        assert "source" in data


# ── Live Market API ─────────────────────────────────────────────────────────

# Hermetic: stubs api.routers.live.AV_API_KEY and replaces
# httpx.AsyncClient with a fake async-context-manager so the endpoint's
# real parsing logic runs against a canned AlphaVantage JSON payload —
# no real AV HTTP call. Also covers the 503-when-no-key path.
class TestLiveMarketAPI:
    """`/api/live/quote/{ticker}` and `/api/live/history/{ticker}` — both
    fetch from AlphaVantage over httpx. Tests mock the HTTP client."""

    def _fake_async_client(self, json_payload):
        """Return a class usable as `httpx.AsyncClient` whose `.get()`
        yields a response with `.json()` → `json_payload`."""

        class _FakeResp:
            def json(self):
                return json_payload

            def raise_for_status(self):
                return None

        class _FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, *a, **k):
                return _FakeResp()

        return _FakeClient

    def test_live_quote(self, client, monkeypatch):
        from api.routers import live as live_module

        monkeypatch.setattr(live_module, "AV_API_KEY", "TESTKEY")
        payload = {
            "Global Quote": {
                "01. symbol": "IWM",
                "02. open": "204.00",
                "03. high": "206.50",
                "04. low": "203.10",
                "05. price": "205.80",
                "06. volume": "31000000",
                "07. latest trading day": "2026-05-15",
                "08. previous close": "204.20",
                "09. change": "1.60",
                "10. change percent": "0.7835%",
            }
        }
        monkeypatch.setattr(
            live_module.httpx, "AsyncClient", self._fake_async_client(payload)
        )

        r = client.get("/api/live/quote/IWM")
        assert r.status_code == 200
        data = r.json()
        assert data["ticker"] == "IWM"
        assert data["price"] == pytest.approx(205.80)
        assert data["change"] == pytest.approx(1.60)
        assert data["change_pct"] == pytest.approx(0.7835)
        assert data["volume"] == 31000000

    def test_live_quote_503_without_api_key(self, client, monkeypatch):
        """No AV key configured → 503 (never fakes a quote)."""
        from api.routers import live as live_module
        monkeypatch.setattr(live_module, "AV_API_KEY", "")
        r = client.get("/api/live/quote/IWM")
        assert r.status_code == 503

    def test_live_history(self, client, monkeypatch):
        from api.routers import live as live_module

        monkeypatch.setattr(live_module, "AV_API_KEY", "TESTKEY")
        payload = {
            "Time Series (1min)": {
                "2026-05-15 15:58:00": {
                    "1. open": "205.50", "2. high": "205.70",
                    "3. low": "205.40", "4. close": "205.60", "5. volume": "12000",
                },
                "2026-05-15 15:59:00": {
                    "1. open": "205.60", "2. high": "205.90",
                    "3. low": "205.55", "4. close": "205.80", "5. volume": "15000",
                },
            }
        }
        monkeypatch.setattr(
            live_module.httpx, "AsyncClient", self._fake_async_client(payload)
        )

        r = client.get("/api/live/history/IWM")
        assert r.status_code == 200
        data = r.json()
        assert "bars" in data
        assert data["count"] == 2
        # sorted ascending by timestamp
        assert data["bars"][0]["time"] == "2026-05-15 15:58:00"
        assert data["bars"][1]["close"] == pytest.approx(205.80)


# ── Review Mode Integration ─────────────────────────────────────────────────

# Hermetic: every data backend the review-mode pages touch (Cloud SQL via
# signals/dashboard/main, GCS via backtest/playbook, AV via reference,
# audit_all via health) is monkeypatched with synthetic fixtures, so the
# whole review-mode page contract runs in the no-DB CI `Run Tests` job.
class TestReviewModeIntegration:
    """End-to-end tests simulating a full review-mode session at a specific point in time."""

    REVIEW_DATE = "2025-06-02"
    REVIEW_TIME = "10:30"
    REVIEW_DATE_COMPACT = "20250602"

    def _patch_all_backends(self, monkeypatch):
        """Wire every data backend used by the review-mode pages to
        synthetic fixtures. Returns nothing — purely side-effecting."""
        import api.main as main_module
        from gcp import database
        from api.routers import signals as signals_module
        from api.routers import dashboard as dash_module
        from api.routers import backtest as bt_module
        from api.routers import playbook as pb_module

        # ── Signals (Cloud SQL) ──────────────────────────────────────────
        signal_rows = pd.DataFrame([
            {"time": pd.Timestamp("2025-06-02 09:45:00"), "direction": "CALL",
             "close": 205.0, "rsi": 55.0, "ema9": 204.8, "ema20": 204.5,
             "volume": 110000, "score": 4, "conditions_met": 4, "return_pct": 0.5},
        ])
        signal_count = pd.DataFrame([{"n": 1}])
        monkeypatch.setattr(signals_module, "_CLOUD_SQL", True)

        sig_calls = {"n": 0}

        def fake_signal_query(sql, params=None):
            sig_calls["n"] += 1
            return signal_count.copy() if sig_calls["n"] % 2 == 1 else signal_rows.copy()

        monkeypatch.setattr(database, "query_to_dataframe", fake_signal_query)

        # ── Dashboard brief (Cloud SQL) ──────────────────────────────────
        daily = pd.DataFrame([{
            "date": "2025-05-30", "close": 204.0, "rsi_14": 54.0, "ema_9": 203.5,
            "ema_20": 203.0, "sma_200": 195.0, "macd": 0.05, "bb_upper": 210.0,
            "bb_lower": 200.0, "atr_14": 1.5, "rvol": 1.0, "strat_candle": "2U",
            "strat_combo": None, "strat_setup": True, "ftfc_score": 0.4,
            "ftfc_direction": "bullish", "consecutive_up": 1, "consecutive_down": 0,
            "price_vs_ema9": 0.2, "price_vs_ema20": 0.5,
        }])
        monkeypatch.setattr(dash_module, "_CLOUD_SQL", True)

        dash_calls = {"n": 0}

        def fake_dash_query(sql, params=None):
            dash_calls["n"] += 1
            # premarket first (empty), then daily
            return pd.DataFrame() if dash_calls["n"] % 2 == 1 else daily.copy()

        monkeypatch.setattr(dash_module, "_query_fn", fake_dash_query)

        # ── Backtest (GCS) ───────────────────────────────────────────────
        bt_module._RESULTS_CACHE.clear()
        bt_module._EQUITY_CACHE.clear()
        bt_module._ALL_RUNS_CACHE.clear()
        trades_df = pd.DataFrame([
            {"entry_time": "2015-01-02 09:30:00", "direction": "CALL",
             "entry_price": 120.0, "exit_price": 121.0, "return_pct": 0.83},
        ])
        equity_df = pd.DataFrame({
            "Unnamed: 0": ["2015-01-02", "2015-01-05"],
            "0": [10000.0, 10100.0],
        })

        def fake_bt_list(prefix, pattern):
            if "equity" in pattern:
                return ["raw/data/backtest_results/equity_IWM_20260221_161724.csv"]
            return ["raw/data/backtest_results/backtest_IWM_20260221_161724.csv"]

        def fake_bt_csv(blob):
            return equity_df.copy() if "equity" in blob else trades_df.copy()

        monkeypatch.setattr(bt_module.gcs_reader, "list_matching_blobs", fake_bt_list)
        monkeypatch.setattr(bt_module.gcs_reader, "download_csv", fake_bt_csv)

        # ── Playbook (GCS) ───────────────────────────────────────────────
        pb_module._PLAYBOOK_CACHE.clear()
        pb_module._LIST_CACHE.clear()
        pb_module._REPORT_TEXT_CACHE.clear()
        playbook_md = (
            "# Phase 6 Playbook IWM\n\n"
            "### Morning Trend Continuation\n\n"
            "**IF ALL CONFIRMED -> CALL ENTRY**\n\n"
            "Historical win rate: 60.0%\n"
        )
        monkeypatch.setattr(
            pb_module.gcs_reader, "download_text", lambda blob: playbook_md
        )

        # ── Reference (Cloud SQL — older than 30d so AV branch skipped) ──
        prev_day = pd.DataFrame([{
            "date": pd.Timestamp("2025-05-30").date(),
            "open": 203.0, "high": 205.0, "low": 202.0, "close": 204.0,
        }])
        monkeypatch.setattr(main_module, "_CLOUD_SQL", True)

        main_calls = {"n": 0}

        def fake_main_query(sql, params=None):
            main_calls["n"] += 1
            # reference: prev-day row first, week-range second (give <2 rows)
            return prev_day.copy() if main_calls["n"] % 2 == 1 else pd.DataFrame()

        monkeypatch.setattr(main_module, "query_to_dataframe", fake_main_query)

    def test_all_dashboard_endpoints_return_200(self, client, monkeypatch):
        """Every endpoint the DashboardPage calls in review mode should return 200."""
        self._patch_all_backends(monkeypatch)
        endpoints = [
            "/api/health",
            "/api/live/status",
            f"/api/dashboard/brief/IWM?date={self.REVIEW_DATE}",
            "/api/backtest/results/IWM",
            "/api/backtest/equity/IWM",
            f"/api/signals/IWM?limit=20&end_date={self.REVIEW_DATE}&end_time={self.REVIEW_TIME}",
            "/api/playbook/IWM",
        ]
        for url in endpoints:
            r = client.get(url)
            assert r.status_code == 200, f"FAIL: {url} returned {r.status_code}"

    def test_signals_review_all_before_cutoff(self, client, monkeypatch):
        self._patch_all_backends(monkeypatch)
        r = client.get(f"/api/signals/IWM?limit=100&end_date={self.REVIEW_DATE}&end_time={self.REVIEW_TIME}")
        assert r.status_code == 200
        data = r.json()
        cutoff = f"{self.REVIEW_DATE} {self.REVIEW_TIME}:00"
        for s in data["signals"]:
            assert s["time"] <= cutoff, f"Signal {s['time']} exceeds cutoff {cutoff}"

    def test_review_brief_returns_correct_date(self, client, monkeypatch):
        self._patch_all_backends(monkeypatch)
        r = client.get(f"/api/dashboard/brief/IWM?date={self.REVIEW_DATE}")
        assert r.status_code == 200
        data = r.json()
        assert data["source"] == "cloud_sql"
        di = data["daily_indicators"]
        assert di.get("date", "9999-99-99") <= self.REVIEW_DATE

    def test_reference_for_review_date(self, client, monkeypatch):
        self._patch_all_backends(monkeypatch)
        r = client.get(f"/api/market/reference/IWM/{self.REVIEW_DATE_COMPACT}")
        assert r.status_code == 200
        data = r.json()
        # Should return the day BEFORE the review date
        assert data["date"] < self.REVIEW_DATE_COMPACT
