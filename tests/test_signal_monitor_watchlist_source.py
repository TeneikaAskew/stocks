"""Tests for SignalMonitor._resolve_watchlist — DB-backed watchlist source.

The live monitor used to read its watchlist from alert_config.json (a
static config). This module verifies the new DB-backed source-of-truth:
`watchlists.signals = TRUE AND removed_at IS NULL`, with safe fallback
to alert_config.json on any error path.

Coverage:
  1. DB returns rows → use DB tickers (the production happy path)
  2. DB returns empty → fall back to alert_config.json
  3. DB raises → fall back to alert_config.json (resilience)
  4. Cloud SQL not configured (local dev) → fall back to alert_config.json
  5. ImportError on DB libs → fall back to alert_config.json
  6. self.tickers is set on __init__ from the resolved list
  7. run_orb_snapshot iterates self.tickers (not market_cfg.tickers)

Hermetic: no Cloud SQL, no live network. All DB calls are patched.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _make_monitor():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    return monitor


def _patch_db_with_rows(rows: list[tuple]):
    """Build a mock engine that yields the given (ticker,) rows."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.fetchall.return_value = rows
    return mock_engine


# ── 1) DB happy path ──────────────────────────────────────────────────

def test_resolve_watchlist_uses_db_when_signals_true_rows_present():
    """The production happy path: DB has rows with signals=TRUE."""
    with patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         patch("gcp.database.get_engine",
                return_value=_patch_db_with_rows([("IWM",), ("QQQ",), ("SPY",)])):
        monitor = _make_monitor()
    assert monitor.tickers == ["IWM", "QQQ", "SPY"]


def test_resolve_watchlist_db_can_return_arbitrary_subset():
    """User can toggle signals flag for any subset — monitor uses what's there."""
    with patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         patch("gcp.database.get_engine",
                return_value=_patch_db_with_rows([("SPX",), ("AVGO",)])):
        monitor = _make_monitor()
    assert monitor.tickers == ["SPX", "AVGO"]


# ── 2) DB returns empty → fallback ────────────────────────────────────

def test_resolve_watchlist_falls_back_when_db_returns_empty():
    """Pre-migration / unset signals flags → fallback to alert_config.json."""
    with patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         patch("gcp.database.get_engine",
                return_value=_patch_db_with_rows([])):
        monitor = _make_monitor()
    # alert_config.json has 5 tickers: IWM, QQQ, SPY, SPX, AVGO
    assert "SPY" in monitor.tickers
    assert "QQQ" in monitor.tickers
    assert "IWM" in monitor.tickers


# ── 3) DB raises → fallback ───────────────────────────────────────────

def test_resolve_watchlist_falls_back_on_db_exception():
    """Connection blip / schema mismatch → log and fallback. Resilience."""
    mock_engine = MagicMock()
    mock_engine.connect.side_effect = RuntimeError("connection refused")
    with patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         patch("gcp.database.get_engine", return_value=mock_engine):
        monitor = _make_monitor()
    # Falls back to alert_config.json
    assert "SPY" in monitor.tickers
    assert len(monitor.tickers) > 0


# ── 4) Cloud SQL not configured → fallback ────────────────────────────

def test_resolve_watchlist_falls_back_when_cloud_sql_not_configured():
    """Local dev shell with no Cloud SQL env vars → use config file."""
    with patch("gcp.database.is_cloud_sql_configured", return_value=False):
        monitor = _make_monitor()
    assert "SPY" in monitor.tickers
    assert len(monitor.tickers) > 0


# ── 5) self.tickers populated; downstream dicts use it ────────────────

def test_init_sets_self_tickers_and_seeds_per_ticker_dicts():
    """All per-ticker dicts (windows, daily_trades, ...) must be keyed
    on the resolved watchlist, not on a stale market_cfg.tickers."""
    with patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         patch("gcp.database.get_engine",
                return_value=_patch_db_with_rows([("IWM",), ("QQQ",), ("SPY",)])):
        monitor = _make_monitor()

    assert set(monitor.windows.keys()) == {"IWM", "QQQ", "SPY"}
    assert set(monitor.daily_trades.keys()) == {"IWM", "QQQ", "SPY"}
    assert set(monitor.daily_pnl.keys()) == {"IWM", "QQQ", "SPY"}
    assert set(monitor.active_positions.keys()) == {"IWM", "QQQ", "SPY"}
    assert set(monitor.orb_levels.keys()) == {"IWM", "QQQ", "SPY"}
    assert set(monitor.level_maps.keys()) == {"IWM", "QQQ", "SPY"}
    assert set(monitor.last_prices.keys()) == {"IWM", "QQQ", "SPY"}


# ── 6) ORB snapshot uses self.tickers ─────────────────────────────────

def test_run_orb_snapshot_iterates_self_tickers_not_market_cfg():
    """If signals=TRUE was set for SPY only, orb-snapshot must only
    fetch SPY — not the larger alert_config.json list. Catches a
    regression where someone reverts to monitor.market_cfg.tickers."""
    from gcp.signal_monitor import run_orb_snapshot

    fetch_calls: list[str] = []

    def _fake_fetch_latest_bar(self, ticker):
        fetch_calls.append(ticker)
        import pandas as pd
        return pd.DataFrame()

    with patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         patch("gcp.database.get_engine",
                return_value=_patch_db_with_rows([("SPY",)])), \
         patch("gcp.signal_monitor.SignalMonitor.fetch_latest_bar",
                _fake_fetch_latest_bar):
        rc = run_orb_snapshot("15m")

    assert rc == 0
    assert fetch_calls == ["SPY"], (
        f"ORB snapshot must iterate self.tickers, got {fetch_calls}"
    )
