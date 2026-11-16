"""FEAT-STRAT-001 per-ticker params: scripts/backfill_watchlist_data.py
recomputes the last daily row's indicators and premarket snapshot through
gcp.fetchers.fetch_market_data.compute_and_upsert_daily_indicators. It must
pass the ticker's level parameters in force on that date, read the way the
nightly fetcher reads them (read_level_params_for_run), so the premarket
print filter runs with the ticker's calibrated thresholds. Without them a
good row was overwritten with pre_filter_status level_params_unavailable.
"""
from __future__ import annotations

import importlib
from datetime import date

import pytest

from tests.lib.level_params_fixtures import install_level_params

LAST = date(2026, 11, 5)


class _Resp:
    def json(self):
        return {"Time Series (Daily)": {
            "2026-11-04": {"1. open": "10", "2. high": "11", "3. low": "9", "4. close": "10.5",
                           "5. adjusted close": "10.5", "6. volume": "100"},
            LAST.isoformat(): {"1. open": "10.5", "2. high": "11.5", "3. low": "10",
                               "4. close": "11", "5. adjusted close": "11", "6. volume": "120"},
        }}


@pytest.fixture
def script(monkeypatch):
    import requests

    import gcp.database as database
    import gcp.fetchers.fetch_market_data as fmd

    mod = importlib.import_module("scripts.backfill_watchlist_data")
    calls = []
    monkeypatch.setenv("AV_API_KEY", "test")
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(database, "upsert_dataframe", lambda *a, **k: None)
    monkeypatch.setattr(fmd, "compute_and_upsert_daily_indicators",
                        lambda ticker, fetch_date, **kw: calls.append((ticker, fetch_date, kw)))
    return mod, calls


def test_backfill_daily_passes_the_tickers_level_params(monkeypatch, script):
    mod, calls = script
    pdb = install_level_params(monkeypatch, ("AVGO",))
    assert mod.backfill_daily("AVGO") is True
    assert len(calls) == 1
    ticker, fetch_date, kw = calls[0]
    assert (ticker, fetch_date) == ("AVGO", LAST.isoformat())
    lp = kw.get("level_params")
    assert lp is not None and lp.ticker == "AVGO" and lp.session_date == LAST
    assert lp.ok("pm_spike_atr") and lp.ok("pm_stale_print_atr")
    # One parameter read, through the loader's own SQL.
    assert sum("level_param_policy" in q for q in pdb.queries) == 1


def test_backfill_daily_with_unreadable_tables_says_so(monkeypatch, script, caplog):
    """The tables cannot be read: as in the nightly fetcher, the snapshot is
    written unfiltered with that reason (level_params None) and the backfill
    reports failure rather than success."""
    mod, calls = script
    pdb = install_level_params(monkeypatch, ("AVGO",))
    pdb.drop("ticker_level_params")
    assert mod.backfill_daily("AVGO") is False
    assert len(calls) == 1 and calls[0][2].get("level_params", "missing") is None
    assert "level_params_unavailable" in caplog.text
