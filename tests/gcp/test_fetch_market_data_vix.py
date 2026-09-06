"""Tests for the ^VIX daily fetch in fetch_market_data.

AlphaVantage does not serve the VIX index via TIME_SERIES_DAILY, so the daily
^VIX close (consumed by strat_data_builder for the vix_close / vix_tercile
features) is fetched from Yahoo's chart API and upserted to market_data_daily.
Without it ^VIX froze on 2026-05-22 and silently NULLed ~4 weeks of vix_close.

These tests cover fetch_and_upsert_vix: response parsing, None-close skipping
(no fabricated 0 — rule 3.7), the upsert shape, and fail-loud on HTTP error.
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock

import pytest

from gcp.fetchers import fetch_market_data as mod


def _epoch(datestr: str) -> int:
    return int(dt.datetime.strptime(datestr, "%Y-%m-%d")
               .replace(tzinfo=dt.timezone.utc).timestamp())


def _yahoo_payload(rows):
    """rows = list of (datestr, open, high, low, close)."""
    return {"chart": {"result": [{
        "timestamp": [_epoch(r[0]) for r in rows],
        "indicators": {"quote": [{
            "open":  [r[1] for r in rows],
            "high":  [r[2] for r in rows],
            "low":   [r[3] for r in rows],
            "close": [r[4] for r in rows],
        }]},
    }]}}


def _resp(payload):
    r = MagicMock()
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


def test_fetch_vix_parses_and_upserts(monkeypatch):
    payload = _yahoo_payload([
        ("2026-06-17", 18.0, 18.5, 17.8, 18.2),
        ("2026-06-18", 18.2, 19.0, 18.1, 18.7),
    ])
    captured = {}
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _resp(payload))
    monkeypatch.setattr(mod, "upsert_dataframe",
                        lambda df, table, keys: captured.update(df=df, table=table, keys=keys))

    n = mod.fetch_and_upsert_vix(lookback_days=7)

    assert n == 2
    assert captured["table"] == "market_data_daily"
    assert captured["keys"] == ["ticker", "date"]
    df = captured["df"]
    assert list(df["ticker"].unique()) == ["^VIX"]
    assert set(df["date"]) == {"2026-06-17", "2026-06-18"}
    assert df.iloc[-1]["close"] == 18.7
    # index has no splits/dividends → adjusted_close == close (legitimate, not a fabricated fill)
    assert (df["adjusted_close"] == df["close"]).all()
    assert (df["data_source"] == "yahoo").all()


def test_fetch_vix_skips_none_close_no_fabrication(monkeypatch):
    """A forming/holiday bar has close=None — it must be SKIPPED, never written
    as a fabricated 0 (rule 3.7)."""
    payload = _yahoo_payload([
        ("2026-06-18", 18.2, 19.0, 18.1, 18.7),
        ("2026-06-19", None, None, None, None),  # forming bar, not settled
    ])
    captured = {}
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _resp(payload))
    monkeypatch.setattr(mod, "upsert_dataframe",
                        lambda df, table, keys: captured.update(df=df))

    n = mod.fetch_and_upsert_vix()

    assert n == 1
    assert set(captured["df"]["date"]) == {"2026-06-18"}
    assert 0 not in list(captured["df"]["close"].values)


def test_fetch_vix_empty_returns_zero_no_upsert(monkeypatch):
    """All-None window → 0 rows, no upsert (don't write an empty/fabricated row)."""
    payload = _yahoo_payload([("2026-06-19", None, None, None, None)])
    calls = []
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _resp(payload))
    monkeypatch.setattr(mod, "upsert_dataframe", lambda *a, **k: calls.append(1))

    assert mod.fetch_and_upsert_vix() == 0
    assert calls == []


def test_fetch_vix_raises_on_http_error(monkeypatch):
    """A hard fetch failure must propagate so the run reports red
    (rule 3.7: surface the outage, don't fabricate a value)."""
    r = MagicMock()
    r.raise_for_status.side_effect = RuntimeError("503 Service Unavailable")
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: r)

    with pytest.raises(RuntimeError):
        mod.fetch_and_upsert_vix()
