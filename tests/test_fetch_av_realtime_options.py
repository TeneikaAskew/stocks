"""Unit tests for `gcp/fetchers/fetch_av_realtime_options.py`.

Sibling of test_fetch_av_historical_options.py. The realtime fetcher
deliberately differs from the historical one in two key ways enforced
by CLAUDE.md Rule 3.7:

  1. It RAISES on AV failure (RealtimeOptionsUnavailable / requests
     exceptions) — it does NOT return an empty DataFrame. The historical
     fetcher returns empty for backwards-compat with its backfill loop,
     but new code should fail loud.

  2. It detects the AV "sample data" response (contractID starting with
     `XXYYZZ`) that AV returns when the subscription tier doesn't include
     REALTIME_OPTIONS. Writing those rows to etf_options_snapshots would
     poison every downstream gamma / GEX computation.

Tests cover:
    - `fetch_av_realtime_options` success path (normalized df, REALTIME session)
    - `fetch_av_realtime_options` raises on rate-limit / error / sample / empty
    - `_normalize_av_response` schema coercion
    - `process_ticker` dedup before upsert
"""

from __future__ import annotations

from datetime import datetime, date, timezone

import pandas as pd
import pytest


class _FakeResponse:
    def __init__(self, json_data, ok=True):
        self._json = json_data
        self.ok = ok

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("http error")

    def json(self):
        return self._json


_NOW = datetime(2026, 5, 22, 18, 7, 32, tzinfo=timezone.utc)


# ──────────────────────────────────────────────────────────────────────
# Successful response → normalized df with REALTIME session
# ──────────────────────────────────────────────────────────────────────

def test_fetch_realtime_options_returns_normalized_df(monkeypatch):
    from gcp.fetchers import fetch_av_realtime_options as mod

    fake_payload = {
        "message": "success",
        "endpoint": "Realtime Options",
        "data": [
            {
                "contractID": "SPY260522C00500000",
                "symbol": "SPY",
                "type": "call",
                "expiration": "2026-05-22",
                "strike": "500.00",
                "last": "238.93",
                "mark": "243.05",
                "bid": "241.65",
                "ask": "244.45",
                "volume": "53",
                "open_interest": "4",
                "implied_volatility": "3.16602",
                "delta": "0.99327",
                "gamma": "0.00015",
                "theta": "-1.20745",
                "vega": "0.00732",
                "rho": "0.01355",
            },
        ],
    }
    monkeypatch.setattr(
        mod.requests, "get", lambda *a, **k: _FakeResponse(fake_payload)
    )

    df = mod.fetch_av_realtime_options("spy", "fake-key", _NOW)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["ticker"] == "SPY"
    assert row["data_source"] == "alphavantage"
    assert row["market_session"] == "REALTIME"  # NOT 'EOD'
    assert row["option_type"] == "calls"
    assert row["strike"] == 500.0
    assert row["last_price"] == 238.93
    # snapshot_ts is the live fetch time, NOT 23:00 EOD marker
    assert pd.Timestamp(row["snapshot_ts"]) == pd.Timestamp(_NOW)
    assert row["snapshot_date"] == date(2026, 5, 22)


# ──────────────────────────────────────────────────────────────────────
# AV sample/illustration data — subscription tier doesn't include realtime
# ──────────────────────────────────────────────────────────────────────

def test_fetch_realtime_options_raises_on_sample_payload(monkeypatch):
    """AV returns the literal sample contractID 'XXYYZZ999999C00020000'
    when the subscription tier doesn't include REALTIME_OPTIONS. Writing
    those rows would poison every downstream gamma computation — fetcher
    must raise, not silently write 4 fake rows."""
    from gcp.fetchers import fetch_av_realtime_options as mod

    # The exact response AV returned before the 2026-05-22 upgrade.
    fake_payload = {
        "message": "This is a premium endpoint. THE SAMPLE DATA SCHEMA BELOW IS ARTIFICIAL...",
        "endpoint": "Realtime Options",
        "data": [
            {
                "contractID": "XXYYZZ999999C00020000",
                "symbol": "XXYYZZ",
                "expiration": "2099-99-99",
                "strike": "20.00",
                "type": "call",
                "last": "100.00",
                "mark": "100.10",
                "bid": "100.05",
                "ask": "100.15",
                "volume": "100",
                "open_interest": "100",
                "date": "2049-99-99",
            },
        ],
    }
    monkeypatch.setattr(
        mod.requests, "get", lambda *a, **k: _FakeResponse(fake_payload)
    )

    with pytest.raises(mod.RealtimeOptionsUnavailable, match="sample/illustration"):
        mod.fetch_av_realtime_options("SPY", "fake-key", _NOW)


# ──────────────────────────────────────────────────────────────────────
# AV error / rate-limit shapes — raise, don't swallow
# ──────────────────────────────────────────────────────────────────────

def test_fetch_realtime_options_raises_on_rate_limit(monkeypatch):
    """{"Information": "rate limit..."} → raise UNAVAILABLE."""
    from gcp.fetchers import fetch_av_realtime_options as mod

    fake = _FakeResponse({
        "Information": "Our standard API rate limit is 600 requests per minute"
    })
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: fake)

    with pytest.raises(mod.RealtimeOptionsUnavailable, match="rate-limit"):
        mod.fetch_av_realtime_options("SPY", "fake-key", _NOW)


def test_fetch_realtime_options_raises_on_error_message(monkeypatch):
    """{"Error Message": "Invalid API call..."} → raise UNAVAILABLE."""
    from gcp.fetchers import fetch_av_realtime_options as mod

    fake = _FakeResponse({
        "Error Message": "Invalid API call. Please check the symbol parameter."
    })
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: fake)

    with pytest.raises(mod.RealtimeOptionsUnavailable, match="error"):
        mod.fetch_av_realtime_options("FAKE", "fake-key", _NOW)


def test_fetch_realtime_options_raises_on_unexpected_endpoint(monkeypatch):
    """Response shape isn't what we expect — fail loud."""
    from gcp.fetchers import fetch_av_realtime_options as mod

    fake = _FakeResponse({
        "endpoint": "Historical Options",  # wrong endpoint
        "message": "success",
        "data": [{"contractID": "SPY260522C500"}],
    })
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: fake)

    with pytest.raises(mod.RealtimeOptionsUnavailable, match="unexpected"):
        mod.fetch_av_realtime_options("SPY", "fake-key", _NOW)


def test_fetch_realtime_options_raises_on_empty_data(monkeypatch):
    """0 contracts during market hours is anomalous — raise, don't write
    nothing silently. The job's exit-non-zero path will surface this to
    Cloud Scheduler so it doesn't go unnoticed."""
    from gcp.fetchers import fetch_av_realtime_options as mod

    fake = _FakeResponse({
        "endpoint": "Realtime Options",
        "message": "success",
        "data": [],
    })
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: fake)

    with pytest.raises(mod.RealtimeOptionsUnavailable, match="0 contracts"):
        mod.fetch_av_realtime_options("SPY", "fake-key", _NOW)


def test_fetch_realtime_options_propagates_http_error(monkeypatch):
    """A network failure must bubble up — caller decides retry vs fail.
    The historical fetcher swallows this (returns empty df); the realtime
    fetcher does NOT (Rule 3.7)."""
    from gcp.fetchers import fetch_av_realtime_options as mod

    def boom(*a, **k):
        raise ConnectionError("network down")

    monkeypatch.setattr(mod.requests, "get", boom)
    with pytest.raises(ConnectionError):
        mod.fetch_av_realtime_options("SPY", "fake-key", _NOW)


# ──────────────────────────────────────────────────────────────────────
# _normalize_av_response — schema coercion & REALTIME marker
# ──────────────────────────────────────────────────────────────────────

def test_normalize_sets_realtime_session_and_live_snapshot_ts():
    from gcp.fetchers.fetch_av_realtime_options import _normalize_av_response

    raw = pd.DataFrame([
        {"type": "call", "expiration": "2026-05-29", "strike": "500.0",
         "delta": "0.5", "gamma": "0.02"},
    ])
    out = _normalize_av_response(raw, "SPY", _NOW)

    assert (out["market_session"] == "REALTIME").all()
    assert (pd.to_datetime(out["snapshot_ts"]) == pd.Timestamp(_NOW)).all()
    assert (out["snapshot_date"] == date(2026, 5, 22)).all()
    # NOT 23:00 — the EOD marker the historical fetcher uses
    assert out.iloc[0]["snapshot_ts"].hour != 23


def test_normalize_drops_rows_missing_required_keys():
    from gcp.fetchers.fetch_av_realtime_options import _normalize_av_response

    raw = pd.DataFrame([
        {"type": "call", "expiration": "2026-05-29", "strike": "500.0"},
        # Missing strike — drops
        {"type": "put", "expiration": "2026-05-29"},
    ])
    out = _normalize_av_response(raw, "SPY", _NOW)
    assert len(out) == 1
    assert out.iloc[0]["option_type"] == "calls"


def test_normalize_coerces_numeric_greeks():
    """Greeks arrive as strings from AV; must be numeric for SQL writes."""
    from gcp.fetchers.fetch_av_realtime_options import _normalize_av_response

    raw = pd.DataFrame([{
        "type": "put", "expiration": "2026-08-21", "strike": "705.00",
        "bid": "10.25", "ask": "10.30", "mark": "10.28",
        "volume": "330", "open_interest": "2244",
        "implied_volatility": "0.19048",
        "delta": "-0.23192", "gamma": "0.00430",
        "theta": "-0.10073", "vega": "1.13585", "rho": "-0.45623",
    }])
    out = _normalize_av_response(raw, "SPY", _NOW)
    for col in ("strike", "bid", "ask", "mark", "volume", "open_interest",
                "implied_volatility", "delta", "gamma", "theta", "vega", "rho"):
        assert pd.api.types.is_numeric_dtype(out[col]), f"{col} not numeric"
    assert out.iloc[0]["delta"] == pytest.approx(-0.23192)


# ──────────────────────────────────────────────────────────────────────
# process_ticker — dedup before upsert
# ──────────────────────────────────────────────────────────────────────

def test_process_ticker_dedups_before_upsert(monkeypatch):
    """AV occasionally returns duplicate rows in a single response.
    Conflict-cols (ticker, snapshot_ts, option_type, expiration, strike)
    would crash Postgres ON CONFLICT on intra-batch dups."""
    from gcp.fetchers import fetch_av_realtime_options as mod

    fake_payload = {
        "endpoint": "Realtime Options",
        "message": "success",
        "data": [
            {"contractID": "SPY1", "type": "call",
             "expiration": "2026-05-29", "strike": "500", "last": "1.0"},
            {"contractID": "SPY1-dup", "type": "call",
             "expiration": "2026-05-29", "strike": "500", "last": "1.5"},
        ],
    }
    monkeypatch.setattr(
        mod.requests, "get", lambda *a, **k: _FakeResponse(fake_payload)
    )

    upserts = []
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(
        mod, "upsert_dataframe",
        lambda df, table, conflict_cols: upserts.append(
            (len(df), table, list(conflict_cols))
        ),
    )

    rows_written = mod.process_ticker("SPY", "fake-key", _NOW)
    assert rows_written == 1, "duplicate contract was deduped pre-upsert"
    assert len(upserts) == 1
    n_rows, table, conflict_cols = upserts[0]
    assert table == "etf_options_snapshots"
    assert conflict_cols == [
        "ticker", "snapshot_ts", "option_type", "expiration", "strike",
    ]


def test_process_ticker_raises_unavailable_does_not_upsert(monkeypatch):
    """Sample-data response → process_ticker bubbles up — no upsert."""
    from gcp.fetchers import fetch_av_realtime_options as mod

    fake_payload = {
        "endpoint": "Realtime Options",
        "message": "premium endpoint sample",
        "data": [
            {"contractID": "XXYYZZ999999C00020000", "type": "call",
             "expiration": "2099-99-99", "strike": "20"},
        ],
    }
    monkeypatch.setattr(
        mod.requests, "get", lambda *a, **k: _FakeResponse(fake_payload)
    )
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)

    upserts = []
    monkeypatch.setattr(
        mod, "upsert_dataframe", lambda *a, **k: upserts.append(a),
    )

    with pytest.raises(mod.RealtimeOptionsUnavailable):
        mod.process_ticker("SPY", "fake-key", _NOW)
    assert upserts == [], "no upsert on UNAVAILABLE"
