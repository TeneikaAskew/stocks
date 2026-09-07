"""gcp/backfill_ticker.py — the watchlist side effect is opt-out.

Codex on #1022: run() unconditionally called add_to_watchlist(), which
inserts the ticker into the shared `default` watchlist or clears
removed_at on a deliberately removed one. That is the Discord /replay
contract, but scripts/backfill_and_replay.py now routes historical-test
tickers through the same job, and every active watchlist row is consumed
by the generic fetchers. BACKFILL_ADD_TO_WATCHLIST=false keeps those
backfills out of the production universe; the default stays true.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import gcp.backfill_ticker as mod


@pytest.fixture
def stubbed_run(monkeypatch):
    """Stub every network/DB touch in run() and return the add_to_watchlist mock."""
    monkeypatch.setenv("BACKFILL_TICKER", "amd")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
    monkeypatch.setenv("BACKFILL_DATES", "2026-04-24")
    monkeypatch.setenv("BACKFILL_INCLUDE_NEWS", "false")
    daily = pd.DataFrame({
        "date": [pd.Timestamp("2026-04-23").date(), pd.Timestamp("2026-04-24").date()],
        "open": [1.0, 1.0], "high": [1.0, 1.0], "low": [1.0, 1.0],
        "close": [1.0, 1.0], "adjusted_close": [1.0, 1.0], "volume": [1, 1],
    })
    watch = MagicMock()
    with patch.object(mod, "av_daily_full", return_value=daily), \
         patch.object(mod, "av_intraday_month", return_value=pd.DataFrame()), \
         patch.object(mod, "compute_indicators_for_full_range", return_value=0), \
         patch.object(mod, "compute_indicators_for_dates"), \
         patch.object(mod, "add_to_watchlist", watch), \
         patch("gcp.database.upsert_dataframe"):
        yield watch


def test_watchlist_add_is_the_default(stubbed_run, monkeypatch):
    monkeypatch.delenv("BACKFILL_ADD_TO_WATCHLIST", raising=False)
    assert mod.run() == 0
    stubbed_run.assert_called_once_with("AMD")


def test_watchlist_add_can_be_opted_out(stubbed_run, monkeypatch):
    monkeypatch.setenv("BACKFILL_ADD_TO_WATCHLIST", "false")
    assert mod.run() == 0
    stubbed_run.assert_not_called()
