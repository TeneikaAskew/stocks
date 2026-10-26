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
import json
import logging
import math
import time

import pandas as pd
import pytest


class _FakeResponse:
    def __init__(self, json_data, ok=True, status_code=200, headers=None):
        from requests.structures import CaseInsensitiveDict
        self._json = json_data
        self.ok = ok
        self.status_code = status_code
        self.headers = CaseInsensitiveDict(headers or {})

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("http error")

    def json(self):
        return self._json

    @property
    def raw(self):
        import io
        from urllib3.response import HTTPResponse
        if not hasattr(self, '_raw'):
            self._raw = HTTPResponse(body=io.BytesIO(json.dumps(self._json).encode()), preload_content=False)
        return self._raw

    def close(self):
        if hasattr(self, '_raw'):
            self._raw.close()


_NOW = datetime(2026, 5, 22, 18, 7, 32, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _hermetic_source_boundaries(monkeypatch):
    """No test in this module may escape its explicit HTTP/SQL mocks."""
    import socket
    import subprocess
    import requests
    from gcp import database
    from gcp.fetchers import fetch_av_realtime_options as mod

    def forbidden(*args, **kwargs):
        raise AssertionError("unmocked external boundary")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(database, "get_engine", forbidden)
    monkeypatch.setattr(mod, "upsert_dataframe", forbidden)
    # Source/telemetry tests run with persistence admitted. Missing persistence
    # has separate quota-before-preflight regressions in the admission suite.
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return _NOW  # Actual NYSE regular session, independent of run time.
    monkeypatch.setattr(mod, "datetime", FrozenDatetime)


def _attempt_events(caplog):
    events = []
    for record in caplog.records:
        message = record.getMessage()
        if message.startswith('{"event":"av_realtime_options_attempt"'):
            assert len(message.encode("utf-8")) <= 2048
            event = json.loads(message)
            assert set(event) == {
                "event", "attempt", "function", "require_greeks", "datatype",
                "ticker", "http_status", "elapsed_s", "error_class",
                "request_ids", "retry_after", "response_schema",
            }
            assert type(event["elapsed_s"]) in (int, float)
            assert math.isfinite(event["elapsed_s"]) and event["elapsed_s"] >= 0
            events.append(event)
    return events


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
        ) or len(df),
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


# ── Transient-empty retry (issue #770) ──────────────────────────────────────
#
# AV intermittently returns a well-formed success with zero contracts for a
# single ticker on one 5-minute fire while sibling tickers succeed on the
# same key seconds apart; a re-probe minutes later returns the full chain
# (verified live 2026-08-26: the failing IWM fire at 14:31 UTC vs a manual
# 5,372-contract probe shortly after). process_ticker retries THAT shape
# only; every other Unavailable cause must propagate un-retried.


def _empty_payload():
    return {"endpoint": "Realtime Options", "message": "success", "data": []}


def _good_payload(contract="IWM260918C00200000"):
    return {
        "endpoint": "Realtime Options",
        "message": "success",
        "data": [{"contractID": contract, "type": "call",
                  "expiration": "2026-09-18", "strike": "200", "last": "1.0"}],
    }


def _no_sleep(monkeypatch):
    import time as _time
    sleeps = []
    monkeypatch.setattr(_time, "sleep", lambda s: sleeps.append(s))
    return sleeps


def test_process_ticker_retries_transient_empty_then_succeeds(monkeypatch):
    from gcp.fetchers import fetch_av_realtime_options as mod

    responses = [_FakeResponse(_empty_payload()), _FakeResponse(_good_payload())]
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: responses.pop(0))
    monkeypatch.setattr(mod, "upsert_dataframe", lambda df, *a: len(df))
    sleeps = _no_sleep(monkeypatch)

    rows = mod.process_ticker("IWM", "fake-key", _NOW)
    assert rows == 1, "second attempt's chain must be used"
    assert len(sleeps) == 1, "one pacing delay between the two attempts"


def test_process_ticker_fails_loud_when_empty_on_every_attempt(monkeypatch):
    """Persistently empty is a real outage / off-hours fire — the Rule 3.7
    hard-fail survives the retry layer, and the job still exits non-zero."""
    import pytest
    from gcp.fetchers import fetch_av_realtime_options as mod

    calls = []
    monkeypatch.setattr(
        mod.requests, "get",
        lambda *a, **k: calls.append(1) or _FakeResponse(_empty_payload()))
    _no_sleep(monkeypatch)

    with pytest.raises(mod.RealtimeOptionsEmpty, match="attempts"):
        mod.process_ticker("IWM", "fake-key", _NOW)
    assert len(calls) == mod.EMPTY_RETRY_ATTEMPTS + 1


def test_rate_limit_and_sample_payload_are_never_retried(monkeypatch):
    """Retrying a rate-limited or unentitled endpoint burns quota for a
    response that cannot change — exactly one API call each."""
    import pytest
    from gcp.fetchers import fetch_av_realtime_options as mod

    for payload in (
        {"Information": "rate limit reached for your key"},
        {"endpoint": "Realtime Options", "message": "sample disclaimer",
         "data": [{"contractID": "XXYYZZ999999C00020000"}]},
    ):
        calls = []
        monkeypatch.setattr(
            mod.requests, "get",
            lambda *a, _p=payload, **k: calls.append(1) or _FakeResponse(_p))
        _no_sleep(monkeypatch)
        with pytest.raises(mod.RealtimeOptionsUnavailable):
            mod.process_ticker("SPY", "fake-key", _NOW)
        assert len(calls) == 1, f"non-empty cause was retried: {payload}"


def test_empty_is_subclass_so_main_error_handling_is_unchanged():
    from gcp.fetchers import fetch_av_realtime_options as mod
    assert issubclass(mod.RealtimeOptionsEmpty, mod.RealtimeOptionsUnavailable)


def test_transport_contract_and_separate_safe_attempt_projection(monkeypatch, caplog):
    from gcp.fetchers import fetch_av_realtime_options as mod

    calls = []
    ticks = iter([100.0, 100.125])
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(mod.requests, "get", lambda *a, **kw: (
        calls.append((a, kw)) or _FakeResponse(_good_payload())))
    caplog.set_level(logging.INFO, logger=mod.__name__)

    assert len(mod.fetch_av_realtime_options("spy", "FAKE-transport-key", _NOW)) == 1
    assert calls == [(("https://www.alphavantage.co/query",), {
        "params": {"function": "REALTIME_OPTIONS", "symbol": "spy",
                   "require_greeks": "true", "apikey": "FAKE-transport-key",
                   "datatype": "json"}, "timeout": 60,
    })]
    assert _attempt_events(caplog) == [{
        "event": "av_realtime_options_attempt", "attempt": 1,
        "function": "REALTIME_OPTIONS", "require_greeks": "true",
        "datatype": "json", "ticker": "SPY", "http_status": 200,
        "elapsed_s": 0.125, "error_class": None, "request_ids": {},
        "retry_after": None,
        "response_schema": {"body": "object", "present": ["data", "endpoint", "message"],
                            "endpoint": "expected", "message": "expected", "records": "array_nonempty"},
    }]
    assert "FAKE-transport-key" not in caplog.text
    assert "apikey" not in caplog.text and "len=" not in caplog.text


_INCIDENT_ERROR = (
    "Invalid API call. Please retry or visit the documentation at "
    "https://www.alphavantage.co/documentation/#realtime-options"
)


def test_incident_provider_error_is_safe_and_never_empty_retried(monkeypatch, caplog):
    from gcp.fetchers import fetch_av_realtime_options as mod

    calls, writes = [], []
    monkeypatch.setattr(mod.requests, "get", lambda *a, **kw: (
        calls.append(1) or _FakeResponse({"Error Message": _INCIDENT_ERROR})))
    monkeypatch.setattr(mod, "upsert_dataframe", lambda *a, **kw: writes.append(1))
    sleeps = _no_sleep(monkeypatch)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    with pytest.raises(mod.RealtimeOptionsUnavailable) as caught:
        mod.process_ticker("IWM", "FAKE-key", _NOW)
    assert not isinstance(caught.value, mod.RealtimeOptionsEmpty)
    assert str(caught.value) == "AV REALTIME_OPTIONS provider error"
    assert calls == [1] and writes == [] and sleeps == []
    event, = _attempt_events(caplog)
    assert event["attempt"] == 1 and event["http_status"] == 200
    assert event["error_class"] == "provider_error"
    assert _INCIDENT_ERROR not in caplog.text


@pytest.mark.parametrize("empty_count, succeeds", [(1, True), (3, False)])
def test_retry_attempt_telemetry_and_write_order(monkeypatch, caplog, empty_count, succeeds):
    from gcp.fetchers import fetch_av_realtime_options as mod

    calls, writes = [], []
    def request(*args, **kwargs):
        assert writes == [], "empty attempts cannot write"
        calls.append(1)
        payload = _empty_payload() if len(calls) <= empty_count else _good_payload()
        return _FakeResponse(payload)

    monkeypatch.setattr(mod.requests, "get", request)
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(mod, "upsert_dataframe", lambda *a, **kw: writes.append(len(a[0])) or len(a[0]))
    sleeps = _no_sleep(monkeypatch)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    if succeeds:
        assert mod.process_ticker("IWM", "FAKE-key", _NOW) == 1
        assert writes == [1]
        expected_classes = ["empty", None]
    else:
        with pytest.raises(mod.RealtimeOptionsEmpty, match="attempts"):
            mod.process_ticker("IWM", "FAKE-key", _NOW)
        assert writes == []
        expected_classes = ["empty", "empty", "empty"]
    events = _attempt_events(caplog)
    assert [e["error_class"] for e in events] == expected_classes
    assert [e["attempt"] for e in events] == list(range(1, len(expected_classes) + 1))
    assert [e["http_status"] for e in events] == [200] * len(expected_classes)
    assert len(calls) == len(expected_classes)
    assert sleeps == [mod._av_cfg.delay_between_calls] * (len(calls) - 1)


@pytest.mark.parametrize("retry_after", ["0", "120", "Wed, 21 Oct 2015 07:28:00 GMT"])
def test_supported_header_values_are_narrowly_projected(monkeypatch, caplog, retry_after):
    from gcp.fetchers import fetch_av_realtime_options as mod

    request_id = "123e4567-e89b-12d3-a456-426614174000"
    response = _FakeResponse(_good_payload(), headers={
        "X-Request-ID": request_id, "Request-ID": request_id,
        "Retry-After": retry_after, "Untrusted-Header": "DO-NOT-COPY",
    })
    monkeypatch.setattr(mod.requests, "get", lambda *a, **kw: response)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    assert len(mod.fetch_av_realtime_options("SPY", "FAKE-key", _NOW)) == 1
    event, = _attempt_events(caplog)
    assert event["request_ids"] == {"x-request-id": request_id, "request-id": request_id}
    assert event["retry_after"] == (int(retry_after) if retry_after.isdecimal() else retry_after)
    assert "DO-NOT-COPY" not in caplog.text and "Untrusted-Header" not in caplog.text


@pytest.mark.parametrize("unsafe", [
    "FAKE-SECRET-1547", "https://evil.invalid/?apikey=FAKE-SECRET-1547",
    "123e4567-e89b-12d3-a456-426614174000\r\nINJECTED",
    "120 FAKE-SECRET-1547", "Wed, 21 Oct 2015 07:28:00 GMT trailing",
    pytest.param("FAKE-SECRET-1547" * 10000, id="oversized"), "86401", "-1", "1.5", "0001", True, None,
])
def test_untrusted_allowlisted_header_values_are_omitted(monkeypatch, caplog, unsafe):
    from gcp.fetchers import fetch_av_realtime_options as mod

    response = _FakeResponse(_good_payload(), headers={
        "X-Request-ID": unsafe, "Request-ID": unsafe, "Retry-After": unsafe,
    })
    monkeypatch.setattr(mod.requests, "get", lambda *a, **kw: response)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    assert len(mod.fetch_av_realtime_options("SPY", "FAKE-key", _NOW)) == 1
    event, = _attempt_events(caplog)
    assert event["request_ids"] == {} and event["retry_after"] is None
    assert "FAKE-SECRET-1547" not in caplog.text and "INJECTED" not in caplog.text


@pytest.mark.parametrize("failure, classification, status", [
    ("http", "http_error", 503), ("transport", "transport_error", None),
    ("json", "json_error", 200), ("parser", "parse_error", 200),
])
def test_failures_emit_once_and_preserve_http_transport_exception(monkeypatch, caplog,
                                                                failure, classification, status):
    from gcp.fetchers import fetch_av_realtime_options as mod

    unsafe = "FAKE-SECRET-1547 https://evil.invalid/?apikey=FAKE-SECRET-1547\r\nINJECTED"
    error = mod.requests.HTTPError(unsafe) if failure == "http" else ConnectionError(unsafe)
    response = _FakeResponse(_good_payload(), status_code=status, headers={"Retry-After": "0"})
    if failure == "http":
        monkeypatch.setattr(response, "raise_for_status", lambda: (_ for _ in ()).throw(error))
    elif failure == "json":
        monkeypatch.setattr(response, "json", lambda: (_ for _ in ()).throw(ValueError(unsafe)))
    elif failure == "parser":
        monkeypatch.setattr(mod, "_normalize_av_response", lambda *a: (_ for _ in ()).throw(ValueError(unsafe)))
    calls = []
    def request(*args, **kwargs):
        calls.append(1)
        if failure == "transport":
            raise error
        return response
    monkeypatch.setattr(mod.requests, "get", request)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    with pytest.raises(Exception) as caught:
        mod.process_ticker("SPY", "FAKE-key", _NOW)
    if failure in ("http", "transport"):
        assert caught.value is error
    else:
        assert unsafe not in str(caught.value)
    event, = _attempt_events(caplog)
    assert event["error_class"] == classification and event["http_status"] == status
    assert event["retry_after"] == (None if failure == "transport" else 0)
    assert calls == [1]
    assert "FAKE-SECRET-1547" not in caplog.text and "INJECTED" not in caplog.text


@pytest.mark.parametrize("payload, classification", [
    ({"Information": "UNSAFE"}, "provider_info"),
    ({"Error Message": "UNSAFE"}, "provider_error"),
    ({"endpoint": "UNSAFE", "message": "UNSAFE", "data": [{}]}, "unexpected_response"),
    ({"endpoint": "Realtime Options", "message": "UNSAFE",
      "data": [{"contractID": "XXYYZZUNSAFE"}]}, "sample"),
])
def test_main_errors_never_reflect_provider_or_symbol_text(monkeypatch, caplog, payload, classification):
    from gcp.fetchers import fetch_av_realtime_options as mod

    unsafe = "FAKE-SECRET-1547 https://evil.invalid/?apikey=FAKE-SECRET-1547\r\nINJECTED"
    payload = json.loads(json.dumps(payload).replace("UNSAFE", unsafe.replace("\r\n", "\\r\\n")))
    monkeypatch.setenv("AV_API_KEY", "FAKE-SECRET-1547")
    monkeypatch.setattr(mod.sys, "argv", ["fetch", "--tickers", "SPY " + unsafe])
    monkeypatch.setattr(mod.requests, "get", lambda *a, **kw: _FakeResponse(payload))
    _no_sleep(monkeypatch)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    with pytest.raises(SystemExit) as caught:
        mod.main()
    assert caught.value.code == 1
    events = _attempt_events(caplog)
    assert events and {e["error_class"] for e in events} == {classification}
    assert events[0]["ticker"] == "SPY" and events[1]["ticker"] == "unavailable"
    assert "FAKE-SECRET-1547" not in caplog.text.upper()
    assert "EVIL.INVALID" not in caplog.text.upper() and "INJECTED" not in caplog.text
    assert "len=" not in caplog.text


def test_main_transport_error_list_is_safe_and_continues_canonical_tickers(monkeypatch, caplog):
    from gcp.fetchers import fetch_av_realtime_options as mod

    monkeypatch.setenv("AV_API_KEY", "FAKE-SECRET-1547")
    monkeypatch.setattr(mod.sys, "argv", ["fetch", "--tickers", "spy iwm"])
    calls = []
    def request(*args, **kwargs):
        calls.append(kwargs["params"]["symbol"])
        raise mod.requests.ConnectionError("FAKE-SECRET-1547 https://evil.invalid/?apikey=FAKE-SECRET-1547\r\nINJECTED")
    monkeypatch.setattr(mod.requests, "get", request)
    sleeps = _no_sleep(monkeypatch)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    with pytest.raises(SystemExit) as caught:
        mod.main()
    assert caught.value.code == 1 and calls == ["SPY", "IWM"]
    assert sleeps == [mod._av_cfg.delay_between_calls]
    assert len(_attempt_events(caplog)) == 2
    assert "FAKE-SECRET-1547" not in caplog.text and "evil.invalid" not in caplog.text
    assert "INJECTED" not in caplog.text and "len=" not in caplog.text
    assert "Failed (2): ['SPY: failed', 'IWM: failed']" in caplog.text


@pytest.mark.parametrize("status", [True, float("nan"), float("inf"), "200", 99, 600])
def test_invalid_observation_status_is_not_serialized(monkeypatch, caplog, status):
    from gcp.fetchers import fetch_av_realtime_options as mod
    monkeypatch.setattr(mod.requests, "get", lambda *a, **kw: _FakeResponse(_good_payload(), status_code=status))
    caplog.set_level(logging.INFO, logger=mod.__name__)
    assert len(mod.fetch_av_realtime_options("SPY", "FAKE-key", _NOW)) == 1
    event, = _attempt_events(caplog)
    assert event["http_status"] is None


@pytest.mark.parametrize("bad_clock", [float("nan"), float("inf"), True, -100.0])
def test_invalid_clock_never_breaks_source_or_emits_nonfinite_duration(monkeypatch, caplog, bad_clock):
    from gcp.fetchers import fetch_av_realtime_options as mod
    ticks = iter([100.0, bad_clock])
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(mod.requests, "get", lambda *a, **kw: _FakeResponse(_good_payload()))
    caplog.set_level(logging.INFO, logger=mod.__name__)
    assert len(mod.fetch_av_realtime_options("SPY", "FAKE-key", _NOW)) == 1
    event, = _attempt_events(caplog)
    assert event["elapsed_s"] == 0.0


@pytest.mark.parametrize("failing_http", [False, True])
def test_broken_header_metadata_cannot_change_source_outcome(monkeypatch, caplog, failing_http):
    from gcp.fetchers import fetch_av_realtime_options as mod
    class BrokenHeaders:
        def get(self, name):
            raise ValueError("FAKE-SECRET-1547")
    response = _FakeResponse(_good_payload(), ok=not failing_http)
    response.headers = BrokenHeaders()
    monkeypatch.setattr(mod.requests, "get", lambda *a, **kw: response)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    if failing_http:
        with pytest.raises(RuntimeError, match="http error"):
            mod.fetch_av_realtime_options("SPY", "FAKE-key", _NOW)
    else:
        assert len(mod.fetch_av_realtime_options("SPY", "FAKE-key", _NOW)) == 1
    event, = _attempt_events(caplog)
    assert event["error_class"] == ("http_error" if failing_http else None)
    assert event["request_ids"] == {} and event["retry_after"] is None
    assert "FAKE-SECRET-1547" not in caplog.text


@pytest.mark.parametrize("failing_http", [False, True])
def test_telemetry_sink_failure_cannot_replace_source_outcome(monkeypatch, caplog, failing_http):
    from gcp.fetchers import fetch_av_realtime_options as mod

    response = _FakeResponse(_good_payload(), ok=not failing_http)
    monkeypatch.setattr(mod.requests, "get", lambda *a, **kw: response)
    def broken_sink(*args, **kwargs):
        raise RuntimeError("FAKE-SECRET-1547")
    monkeypatch.setattr(mod.log, "info", broken_sink)
    if failing_http:
        with pytest.raises(RuntimeError, match="^http error$"):
            mod.fetch_av_realtime_options("SPY", "FAKE-key", _NOW)
    else:
        assert len(mod.fetch_av_realtime_options("SPY", "FAKE-key", _NOW)) == 1
    assert "FAKE-SECRET-1547" not in caplog.text


def test_unsafe_nondefault_symbol_is_projected_without_transport_restriction(monkeypatch, caplog):
    from gcp.fetchers import fetch_av_realtime_options as mod

    symbol = "FAKE-SECRET-1547\r\nINJECTED"
    symbols = []
    monkeypatch.setattr(mod.requests, "get", lambda *a, **kw: (
        symbols.append(kw["params"]["symbol"]) or _FakeResponse(_good_payload())))
    monkeypatch.setattr(mod, "upsert_dataframe", lambda df, *a: len(df))
    caplog.set_level(logging.INFO, logger=mod.__name__)
    assert mod.process_ticker(symbol, "FAKE-key", _NOW) == 1
    assert symbols == [symbol]
    event, = _attempt_events(caplog)
    assert event["ticker"] == "unavailable"
    assert "FAKE-SECRET-1547" not in caplog.text and "INJECTED" not in caplog.text


@pytest.mark.parametrize("failure", ["status", "headers", "clock"])
def test_observation_access_errors_are_safe_and_do_not_break_success(monkeypatch, caplog, failure):
    from gcp.fetchers import fetch_av_realtime_options as mod
    response = _FakeResponse(_good_payload())
    def broken(*args):
        raise ValueError("FAKE-SECRET-1547")
    if failure == "clock":
        monkeypatch.setattr(time, "monotonic", broken)
    else:
        class BrokenResponse(_FakeResponse):
            pass
        response.__class__ = BrokenResponse
        monkeypatch.setattr(BrokenResponse, failure if failure == "headers" else "status_code",
                            property(broken), raising=False)
    monkeypatch.setattr(mod.requests, "get", lambda *a, **kw: response)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    assert len(mod.fetch_av_realtime_options("SPY", "FAKE-key", _NOW)) == 1
    event, = _attempt_events(caplog)
    assert event["error_class"] is None
    if failure == "status":
        assert event["http_status"] is None
    if failure == "clock":
        assert event["elapsed_s"] == 0.0
    assert "FAKE-SECRET-1547" not in caplog.text


def test_main_untrusted_ticker_batch_logs_are_bounded_without_skipping_attempts(monkeypatch, caplog):
    from gcp.fetchers import fetch_av_realtime_options as mod

    monkeypatch.setenv("AV_API_KEY", "FAKE-key")
    monkeypatch.setattr(mod.sys, "argv", ["fetch", "--tickers", " ".join(["UNSAFE"] * 300)])
    calls = []
    monkeypatch.setattr(mod.requests, "get", lambda *a, **kw: (
        calls.append(1) or _FakeResponse({"Error Message": "FAKE-SECRET-1547"})))
    sleeps = _no_sleep(monkeypatch)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    with pytest.raises(SystemExit) as caught:
        mod.main()
    assert caught.value.code == 1 and len(calls) == 300 and len(sleeps) == 299
    assert len(_attempt_events(caplog)) == 300
    assert all(len(record.getMessage().encode("utf-8")) <= 2048 for record in caplog.records)
    assert "Failed (300):" in caplog.text
    assert "UNSAFE" not in caplog.text and "FAKE-SECRET-1547" not in caplog.text
