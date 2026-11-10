"""FEAT-STRAT-001 per-ticker params, done_when 7: one-minute bars for every
calibrated ticker.

gcp/fetchers/fetch_alphavantage_intraday.py resolves --symbol=ALL at run time
to the brief tickers (lib.config MarketConfig.tickers), the insight default
tickers (gcp.insight_pipeline_job.DEFAULT_TICKERS) and the watchlist,
deduplicated, instead of its SYMBOLS constant; the nightly path
(av-intraday-nightly: --symbol=ALL --force) still requests extended hours.
On origin/main and the #1753 head --symbol=ALL is SPY, IWM and QQQ.
"""
from __future__ import annotations

import sys

import pandas as pd
import pytest

from gcp.fetchers import fetch_alphavantage_intraday as av


@pytest.fixture
def stub_watchlist(monkeypatch):
    """The shared watchlist, answered on the strict reader the universe
    reads it through (a failed read raises; Codex P2 on e4bb463e)."""
    import gcp.database as database
    from gcp.calibrate_level_params import WATCHLIST_SQL

    def query(sql, params=None):
        assert sql == WATCHLIST_SQL and params == {"user_id": "default"}
        return pd.DataFrame({"ticker": ["AAPL", "nvda", "SPY", "MSFT"]})
    monkeypatch.setattr(database, "query_to_dataframe_strict", query)


def _expected():
    from gcp.insight_pipeline_job import DEFAULT_TICKERS
    from lib.config import MarketConfig
    out = []
    for t in list(MarketConfig().tickers) + list(DEFAULT_TICKERS) + ["AAPL", "NVDA", "SPY", "MSFT"]:
        if t.upper() not in out:
            out.append(t.upper())
    return out


def test_all_resolves_to_brief_insight_and_watchlist(stub_watchlist):
    got = av.resolve_all_symbols()
    assert got == _expected()
    assert {"SPY", "IWM", "QQQ", "AAPL", "NVDA", "MSFT"} == set(got)
    assert len(got) == len(set(got))
    assert not hasattr(av, "SYMBOLS")


def test_a_failed_watchlist_read_fails_all(monkeypatch):
    import gcp.database as database

    def broken(sql, params=None):
        raise RuntimeError("connection reset")
    monkeypatch.setattr(database, "query_to_dataframe_strict", broken)
    with pytest.raises(RuntimeError, match="connection reset"):
        av.resolve_all_symbols()


def test_nightly_path_fetches_every_resolved_ticker_with_extended_hours(stub_watchlist, monkeypatch):
    """main with the av-intraday-nightly arguments hands every resolved
    ticker to process_symbol, and each month request asks for extended
    hours."""
    seen, requests_made = [], []

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"Error Message": "stub"}

    def fake_get(url, params=None, timeout=None):
        requests_made.append(params)
        return Resp()

    def fake_process(symbol, start, end, keys, force):
        seen.append((symbol, force))
        av.fetch_month(symbol, 2026, 11, keys[0])
        return av.OUTCOME_OK

    monkeypatch.setattr(av, "get_api_keys", lambda: ["k"])
    monkeypatch.setattr(av, "process_symbol", fake_process)
    monkeypatch.setattr(av.requests, "get", fake_get)
    monkeypatch.setattr(sys, "argv", ["fetch_alphavantage_intraday", "--symbol=ALL", "--force"])
    monkeypatch.delenv("CLOUD_RUN_TASK_COUNT", raising=False)
    av.main()
    assert [s for s, _ in seen] == _expected()
    assert all(force for _, force in seen)
    assert len(requests_made) == len(seen)
    assert all(p["extended_hours"] == "true" and p["interval"] == "1min" for p in requests_made)


def test_named_symbols_are_unchanged(monkeypatch):
    seen = []
    monkeypatch.setattr(av, "get_api_keys", lambda: ["k"])
    monkeypatch.setattr(av, "process_symbol", lambda s, *a: seen.append(s) or av.OUTCOME_OK)
    monkeypatch.setattr(av, "resolve_all_symbols", lambda: pytest.fail("ALL not requested"))
    monkeypatch.setattr(sys, "argv", ["x", "--symbol", "AMD,NVDA"])
    monkeypatch.delenv("CLOUD_RUN_TASK_COUNT", raising=False)
    av.main()
    assert seen == ["AMD", "NVDA"]
