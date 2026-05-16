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


# Many endpoints below read from Cloud SQL or GCS. CI runs without
# either by default, so the data-backed routes return 404/502/503.
# Use the shared marker from conftest so we don't fork the env-var
# detection logic.
from tests.conftest import requires_data_backend  # noqa: E402


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

@requires_data_backend
class TestSignalsAPI:
    def test_signals_live(self, client):
        r = client.get("/api/signals/IWM?limit=5")
        assert r.status_code == 200
        data = r.json()
        assert "count" in data
        assert "signals" in data
        assert len(data["signals"]) <= 5

    def test_signals_with_direction_filter(self, client):
        r = client.get("/api/signals/IWM?limit=5&direction=CALL")
        assert r.status_code == 200
        data = r.json()
        for s in data["signals"]:
            assert s["direction"] == "CALL"

    def test_signals_end_date_filter(self, client):
        r = client.get("/api/signals/IWM?limit=5&end_date=2025-06-01")
        assert r.status_code == 200
        data = r.json()
        for s in data["signals"]:
            assert s["time"] <= "2025-06-01 23:59:59", f"Signal {s['time']} is after cutoff"

    def test_signals_end_date_and_time_filter(self, client):
        r = client.get("/api/signals/IWM?limit=5&end_date=2025-06-02&end_time=10:00")
        assert r.status_code == 200
        data = r.json()
        for s in data["signals"]:
            assert s["time"] <= "2025-06-02 10:00:00", f"Signal {s['time']} is after cutoff"

    def test_signals_empty_for_old_date(self, client):
        """Dates before the Cloud SQL `historical_signals` range should return
        0 signals honestly (router queries Cloud SQL via lib/data_loader,
        falling back to GCS parquet if Cloud SQL is unreachable).

        IWM signals start 2015-01-02 in `historical_signals`; pick a date
        comfortably before that to assert the empty-result contract.
        """
        r = client.get("/api/signals/IWM?limit=5&end_date=2014-01-01")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 0
        assert data["signals"] == []


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
        """DELETE issues a single SQL DELETE keyed on id."""
        captured = self._patch_cloud_sql(monkeypatch)
        r = client.delete("/api/journal/trades/abc-123")
        assert r.status_code == 200
        assert r.json() == {"source": "cloud_sql", "deleted": "abc-123"}
        del_sql, del_params = captured["execute"][0]
        assert "DELETE FROM journal_entries" in del_sql
        assert del_params == {"id": "abc-123"}

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

@requires_data_backend
class TestMarketDataAPI:
    def test_market_dates(self, client):
        r = client.get("/api/market/dates/IWM")
        assert r.status_code == 200
        data = r.json()
        assert "dates" in data
        assert len(data["dates"]) > 0

    def test_market_data_full_day(self, client):
        """Fetch a full day of 1-min bars."""
        r = client.get("/api/market/data/IWM/20260220?timeframe=1")
        if r.status_code == 404:
            pytest.skip("No local data for 20260220")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] > 100  # full day has hundreds of bars
        assert len(data["candlestick"]) == data["count"]
        assert len(data["volume"]) == data["count"]

    def test_market_data_end_time_filter(self, client):
        """Fetch bars sliced to a specific time — should return fewer bars."""
        full = client.get("/api/market/data/IWM/20260220?timeframe=1")
        if full.status_code == 404:
            pytest.skip("No local data for 20260220")
        sliced = client.get("/api/market/data/IWM/20260220?timeframe=1&end_time=10:30")
        assert sliced.status_code == 200
        full_count = full.json()["count"]
        sliced_count = sliced.json()["count"]
        assert sliced_count < full_count, f"Sliced ({sliced_count}) should be < full ({full_count})"
        assert sliced_count > 0

    def test_market_data_end_time_invalid_format(self, client):
        r = client.get("/api/market/data/IWM/20260220?timeframe=1&end_time=invalid")
        assert r.status_code == 400


# ── Dashboard Brief API ─────────────────────────────────────────────────────

@requires_data_backend
class TestDashboardBriefAPI:
    def test_brief_live(self, client):
        r = client.get("/api/dashboard/brief/IWM")
        assert r.status_code == 200
        data = r.json()
        assert data["ticker"] == "IWM"
        assert data["source"] in ("cloud_sql", "unavailable")
        assert "bias" in data or data["source"] == "unavailable"

    def test_brief_with_historical_date(self, client):
        r = client.get("/api/dashboard/brief/IWM?date=2020-03-16")
        assert r.status_code == 200
        data = r.json()
        if data["source"] == "cloud_sql":
            di = data.get("daily_indicators", {})
            assert di.get("date") is not None
            # Should return data on or before the requested date
            assert di["date"] <= "2020-03-16"

    def test_brief_stale_days_present(self, client):
        """When Cloud SQL is available, daily_indicators should include stale_days."""
        r = client.get("/api/dashboard/brief/IWM")
        assert r.status_code == 200
        data = r.json()
        if data["source"] == "cloud_sql":
            di = data.get("daily_indicators", {})
            assert "stale_days" in di

    def test_brief_unavailable_source(self, client):
        """Without Cloud SQL, should return source='unavailable' with reason."""
        r = client.get("/api/dashboard/brief/IWM")
        data = r.json()
        if data["source"] == "unavailable":
            assert "reason" in data


# ── Reference Levels API ────────────────────────────────────────────────────

@requires_data_backend
class TestReferenceAPI:
    def test_reference_recent_uses_alphavantage(self, client):
        """Recent dates should prefer AlphaVantage over Cloud SQL."""
        from datetime import date
        today = date.today().strftime("%Y%m%d")
        r = client.get(f"/api/market/reference/IWM/{today}")
        # Could be 200 or 404 (no prev day data yet)
        if r.status_code == 200:
            data = r.json()
            assert "source" in data
            assert "date" in data
            assert "high" in data
            assert "low" in data
            assert "close" in data

    def test_reference_historical_uses_cloud_sql(self, client):
        """Old dates should use Cloud SQL."""
        r = client.get("/api/market/reference/IWM/20200316")
        if r.status_code == 200:
            data = r.json()
            assert data.get("source") == "cloud_sql"
            assert data["date"] < "20200316"  # prev day before Mar 16

    def test_reference_returns_prev_day(self, client):
        """Should return the day BEFORE the requested date, not the date itself."""
        r = client.get("/api/market/reference/IWM/20200316")
        if r.status_code == 200:
            data = r.json()
            assert data["date"] != "20200316", "Should return previous day, not same day"


# ── Backtest API ────────────────────────────────────────────────────────────

@requires_data_backend
class TestBacktestAPI:
    def test_backtest_results(self, client):
        r = client.get("/api/backtest/results/IWM")
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data
        assert "trades" in data
        s = data["summary"]
        assert "total_trades" in s
        assert "win_rate" in s
        assert 0 <= s["win_rate"] <= 1

    def test_backtest_equity(self, client):
        r = client.get("/api/backtest/equity/IWM")
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data
        assert "dates" in data
        assert "values" in data
        assert "max_drawdown_pct" in data["summary"]

    def test_backtest_all_runs(self, client):
        r = client.get("/api/backtest/all/IWM")
        assert r.status_code == 200
        data = r.json()
        assert "runs" in data
        assert data["total_runs"] >= 0

    def test_backtest_trade_entry_time_format(self, client):
        """Verify entry_time is a string in YYYY-MM-DD HH:MM:SS format for frontend filtering."""
        r = client.get("/api/backtest/results/IWM")
        if r.status_code == 200 and r.json()["trades"]:
            t = r.json()["trades"][0]
            assert "entry_time" in t
            # Format: "2015-01-02 09:30:00"
            assert len(t["entry_time"]) >= 19, f"Unexpected entry_time format: {t['entry_time']}"
            assert t["entry_time"][4] == "-" and t["entry_time"][10] == " "


# ── Playbook API ────────────────────────────────────────────────────────────

@requires_data_backend
class TestPlaybookAPI:
    def test_playbook(self, client):
        r = client.get("/api/playbook/IWM")
        assert r.status_code == 200
        data = r.json()
        assert "cards" in data
        if data["cards"]:
            card = data["cards"][0]
            assert "name" in card
            assert "direction" in card
            assert card["direction"] in ("CALL", "PUT", "NEUTRAL")

    def test_reports_list(self, client):
        r = client.get("/api/reports/list/IWM")
        assert r.status_code == 200
        data = r.json()
        assert "reports" in data


# ── /api/health/freshness ───────────────────────────────────────────────────

@requires_data_backend
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

@requires_data_backend
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

@requires_data_backend
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

@requires_data_backend
class TestLiveMarketAPI:
    def test_live_quote(self, client):
        r = client.get("/api/live/quote/IWM")
        # 200 if AV key is set, otherwise may fail
        if r.status_code == 200:
            data = r.json()
            assert "price" in data
            assert "change" in data
            assert "change_pct" in data
            assert "volume" in data

    def test_live_history(self, client):
        r = client.get("/api/live/history/IWM")
        if r.status_code == 200:
            data = r.json()
            assert "bars" in data


# ── Review Mode Integration ─────────────────────────────────────────────────

@requires_data_backend
class TestReviewModeIntegration:
    """End-to-end tests simulating a full review-mode session at a specific point in time."""

    REVIEW_DATE = "2025-06-02"
    REVIEW_TIME = "10:30"
    REVIEW_DATE_COMPACT = "20250602"

    def test_all_dashboard_endpoints_return_200(self, client):
        """Every endpoint the DashboardPage calls in review mode should return 200."""
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

    def test_signals_review_all_before_cutoff(self, client):
        r = client.get(f"/api/signals/IWM?limit=100&end_date={self.REVIEW_DATE}&end_time={self.REVIEW_TIME}")
        assert r.status_code == 200
        data = r.json()
        cutoff = f"{self.REVIEW_DATE} {self.REVIEW_TIME}:00"
        for s in data["signals"]:
            assert s["time"] <= cutoff, f"Signal {s['time']} exceeds cutoff {cutoff}"

    def test_review_brief_returns_correct_date(self, client):
        r = client.get(f"/api/dashboard/brief/IWM?date={self.REVIEW_DATE}")
        assert r.status_code == 200
        data = r.json()
        if data["source"] == "cloud_sql":
            di = data.get("daily_indicators", {})
            assert di.get("date", "9999-99-99") <= self.REVIEW_DATE

    def test_reference_for_review_date(self, client):
        r = client.get(f"/api/market/reference/IWM/{self.REVIEW_DATE_COMPACT}")
        if r.status_code == 200:
            data = r.json()
            # Should return the day BEFORE the review date
            assert data["date"] < self.REVIEW_DATE_COMPACT
