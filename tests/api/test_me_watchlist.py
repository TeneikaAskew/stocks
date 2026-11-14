"""Per-user watchlist API: GET/POST/DELETE /api/me/watchlist.

This module covers the response and request models first (Task 3), then the
three routes as they land: listing the signed-in user's watchlist, adding a
ticker, and removing one. Hermetic: no database, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "platform"))


def test_me_watchlist_models_round_trip():
    from api.schemas import (
        MeWatchlistAddRequest,
        MeWatchlistRemoveResponse,
        MeWatchlistResponse,
        MeWatchlistRow,
    )

    row = MeWatchlistRow(ticker="AAPL", added_at="2026-11-14T12:00:00+00:00")
    assert row.source is None
    assert row.name is None
    assert row.exchange is None
    assert row.asset_type is None
    assert row.last_daily_bar is None

    resp = MeWatchlistResponse(
        owner_email="a@b.com", as_of="2026-11-14T12:00:00+00:00", tickers=[row]
    )
    assert resp.tickers[0].ticker == "AAPL"

    removed = MeWatchlistRemoveResponse(**resp.model_dump(), removed=True)
    assert removed.removed is True
    with pytest.raises(ValidationError):
        MeWatchlistRemoveResponse(**resp.model_dump(), removed=False)

    assert MeWatchlistAddRequest(ticker="AAPL", source="ui").source == "ui"
    with pytest.raises(ValidationError):
        MeWatchlistAddRequest(ticker="AAPL", source="cli")
