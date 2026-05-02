"""Tests for SignalMonitor._resolve_watchlist — DB-backed watchlist source.

The live monitor reads its watchlist from the centralized
`gcp.fetchers._watchlist.load_watchlist(surface='signals')` helper —
single source of truth, the watchlists Cloud SQL table where
`signals = TRUE AND removed_at IS NULL`. There is NO fallback to
the legacy alert_config.json watchlist key (removed in the refactor
that introduced the signals surface).

Coverage:
  1. Helper returns rows → use the list
  2. Helper returns empty → __init__ raises RuntimeError (fail loud)
  3. self.tickers is set on __init__ from the resolved list
  4. All per-ticker dicts (windows, daily_trades, ...) seed from self.tickers
  5. run_orb_snapshot iterates self.tickers (regression guard)

Hermetic: no Cloud SQL, no live network. The load_watchlist helper
is patched at the boundary.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _make_monitor():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    return monitor


# ── 1) Helper happy path ──────────────────────────────────────────────

def test_resolve_watchlist_uses_load_watchlist_with_signals_surface():
    """The production happy path: load_watchlist(surface='signals') returns
    the live monitor universe."""
    captured: dict = {}

    def _capture_load(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return ["IWM", "QQQ", "SPY"]

    with patch("gcp.fetchers._watchlist.load_watchlist", side_effect=_capture_load):
        monitor = _make_monitor()

    assert monitor.tickers == ["IWM", "QQQ", "SPY"]
    # Crucial: signal_monitor MUST pass surface='signals' so it gets the
    # filtered live-monitor universe, not the broader research watchlist.
    assert captured["kwargs"].get("surface") == "signals"


def test_resolve_watchlist_uses_arbitrary_subset_returned_by_helper():
    """User can flip signals=TRUE for any subset; monitor uses whatever
    the helper returns — no client-side filtering."""
    with patch("gcp.fetchers._watchlist.load_watchlist",
                return_value=["SPX", "AVGO"]):
        monitor = _make_monitor()
    assert monitor.tickers == ["SPX", "AVGO"]


# ── 2) Helper returns empty → fail loudly ─────────────────────────────

def test_resolve_watchlist_raises_when_helper_returns_empty():
    """No fallback. If the watchlists table has zero rows with
    signals=TRUE AND INSIGHT_TICKERS env var is unset, the helper
    returns []. The monitor must raise RuntimeError so Cloud Run
    surfaces the failure (failure-notifier sink → GitHub issue)
    rather than silently watching no tickers."""
    from gcp.signal_monitor import SignalMonitor

    with patch("gcp.fetchers._watchlist.load_watchlist", return_value=[]):
        with pytest.raises(RuntimeError, match="watchlist is empty"):
            SignalMonitor()


def test_resolve_watchlist_error_message_tells_operator_how_to_fix():
    """The error message must point the user at the remediation:
    UPDATE watchlists SET signals = TRUE WHERE ticker IN (...)."""
    from gcp.signal_monitor import SignalMonitor

    with patch("gcp.fetchers._watchlist.load_watchlist", return_value=[]):
        try:
            SignalMonitor()
        except RuntimeError as e:
            msg = str(e)
            assert "signals = TRUE" in msg
            assert "watchlists" in msg


# ── 3) self.tickers populated; downstream dicts use it ────────────────

def test_init_sets_self_tickers_and_seeds_per_ticker_dicts():
    """All per-ticker dicts (windows, daily_trades, ...) must be keyed
    on the resolved watchlist."""
    with patch("gcp.fetchers._watchlist.load_watchlist",
                return_value=["IWM", "QQQ", "SPY"]):
        monitor = _make_monitor()

    assert set(monitor.windows.keys()) == {"IWM", "QQQ", "SPY"}
    assert set(monitor.daily_trades.keys()) == {"IWM", "QQQ", "SPY"}
    assert set(monitor.daily_pnl.keys()) == {"IWM", "QQQ", "SPY"}
    assert set(monitor.active_positions.keys()) == {"IWM", "QQQ", "SPY"}
    assert set(monitor.orb_levels.keys()) == {"IWM", "QQQ", "SPY"}
    assert set(monitor.level_maps.keys()) == {"IWM", "QQQ", "SPY"}
    assert set(monitor.last_prices.keys()) == {"IWM", "QQQ", "SPY"}


# ── 4) ORB snapshot uses self.tickers ─────────────────────────────────

def test_run_orb_snapshot_iterates_self_tickers_not_market_cfg():
    """If signals=TRUE was set for SPY only, orb-snapshot must only
    fetch SPY — not the larger MarketConfig.tickers default. Catches
    a regression where someone reverts to monitor.market_cfg.tickers."""
    from gcp.signal_monitor import run_orb_snapshot

    fetch_calls: list[str] = []

    def _fake_fetch_latest_bar(self, ticker):
        fetch_calls.append(ticker)
        import pandas as pd
        return pd.DataFrame()

    with patch("gcp.fetchers._watchlist.load_watchlist",
                return_value=["SPY"]), \
         patch("gcp.signal_monitor.SignalMonitor.fetch_latest_bar",
                _fake_fetch_latest_bar):
        rc = run_orb_snapshot("15m")

    assert rc == 0
    assert fetch_calls == ["SPY"], (
        f"ORB snapshot must iterate self.tickers, got {fetch_calls}"
    )
