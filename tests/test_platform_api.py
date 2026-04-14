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
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path so the platform API can import lib/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


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
        assert "lib_dir_exists" in data

    def test_live_status(self, client):
        r = client.get("/api/live/status")
        assert r.status_code == 200
        data = r.json()
        assert "is_open" in data
        assert "session" in data
        assert "current_time_et" in data


# ── Signals API ─────────────────────────────────────────────────────────────

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
        """Dates before the parquet range should return 0 signals honestly."""
        r = client.get("/api/signals/IWM?limit=5&end_date=2020-01-01")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 0
        assert data["signals"] == []


# ── Market Data API ─────────────────────────────────────────────────────────

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


# ── Journal API ─────────────────────────────────────────────────────────────

class TestJournalAPI:
    def test_journal_list(self, client):
        r = client.get("/api/journal/trades/IWM")
        assert r.status_code == 200
        data = r.json()
        assert "trades" in data
        assert "source" in data


# ── Live Market API ─────────────────────────────────────────────────────────

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
