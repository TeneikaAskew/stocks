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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

    fake = _FakeResponse({
        "Information": "Our standard API rate limit is 600 requests per minute"
    })
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: fake)

    with pytest.raises(mod.RealtimeOptionsUnavailable, match="rate-limit"):
        mod.fetch_av_realtime_options("SPY", "fake-key", _NOW)


def test_fetch_realtime_options_raises_on_error_message(monkeypatch):
    """{"Error Message": "Invalid API call..."} → raise UNAVAILABLE."""
    from gcp.fetchers import _av_realtime_collector as mod

    fake = _FakeResponse({
        "Error Message": "Invalid API call. Please check the symbol parameter."
    })
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: fake)

    with pytest.raises(mod.RealtimeOptionsUnavailable, match="error"):
        mod.fetch_av_realtime_options("FAKE", "fake-key", _NOW)


def test_fetch_realtime_options_raises_on_unexpected_endpoint(monkeypatch):
    """Response shape isn't what we expect — fail loud."""
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod
    assert issubclass(mod.RealtimeOptionsEmpty, mod.RealtimeOptionsUnavailable)


def test_transport_contract_and_separate_safe_attempt_projection(monkeypatch, caplog):
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod
    monkeypatch.setattr(mod.requests, "get", lambda *a, **kw: _FakeResponse(_good_payload(), status_code=status))
    caplog.set_level(logging.INFO, logger=mod.__name__)
    assert len(mod.fetch_av_realtime_options("SPY", "FAKE-key", _NOW)) == 1
    event, = _attempt_events(caplog)
    assert event["http_status"] is None


@pytest.mark.parametrize("bad_clock", [float("nan"), float("inf"), True, -100.0])
def test_invalid_clock_never_breaks_source_or_emits_nonfinite_duration(monkeypatch, caplog, bad_clock):
    from gcp.fetchers import _av_realtime_collector as mod
    ticks = iter([100.0, bad_clock])
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(mod.requests, "get", lambda *a, **kw: _FakeResponse(_good_payload()))
    caplog.set_level(logging.INFO, logger=mod.__name__)
    assert len(mod.fetch_av_realtime_options("SPY", "FAKE-key", _NOW)) == 1
    event, = _attempt_events(caplog)
    assert event["elapsed_s"] == 0.0


@pytest.mark.parametrize("failing_http", [False, True])
def test_broken_header_metadata_cannot_change_source_outcome(monkeypatch, caplog, failing_http):
    from gcp.fetchers import _av_realtime_collector as mod
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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod

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
    from gcp.fetchers import _av_realtime_collector as mod
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
    from gcp.fetchers import _av_realtime_collector as mod

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

@pytest.mark.parametrize('value', [None, {}, '', False, 0, '[]', 'MISSING'])
def test_only_literal_empty_list_is_retryable_unknown_data_is_terminal(monkeypatch, value):
    from gcp.fetchers import _av_realtime_collector as mod
    calls = []
    payload = dict(_empty_payload(), data=value)
    if value == 'MISSING':
        payload.pop('data')
    monkeypatch.setattr(mod.requests, 'get', lambda *a, **k: calls.append(1) or _FakeResponse(payload))
    _no_sleep(monkeypatch)
    with pytest.raises(mod.RealtimeOptionsUnavailable) as error:
        mod.process_ticker('IWM', 'offline-key', _NOW)
    assert not isinstance(error.value, mod.RealtimeOptionsEmpty)
    assert len(calls) == 1


def test_literal_empty_list_still_has_exactly_three_attempts_and_no_write(monkeypatch):
    from gcp.fetchers import _av_realtime_collector as mod
    calls, writes = [], []
    monkeypatch.setattr(mod.requests, 'get', lambda *a, **k: calls.append(1) or _FakeResponse(_empty_payload()))
    monkeypatch.setattr(mod, 'upsert_dataframe', lambda *a: writes.append(a))
    _no_sleep(monkeypatch)
    with pytest.raises(mod.RealtimeOptionsEmpty):
        mod.process_ticker('IWM', 'offline-key', _NOW)
    assert len(calls) == 3
    assert writes == []


def test_body_time_accumulates_across_tickers_preserving_first_ack(monkeypatch, caplog):
    import sys
    from types import SimpleNamespace
    from gcp.fetchers import _av_realtime_collector as mod
    transport = mod._cli_transport
    clock, calls, writes = [100.0], [], []
    monkeypatch.setattr(transport, '_source_clock', lambda: clock[0])
    monkeypatch.setattr(mod, '_av_cfg', SimpleNamespace(delay_between_calls=0))
    monkeypatch.setattr(mod, '_regular_session_due', lambda stamp: True)
    monkeypatch.setenv('AV_API_KEY', 'offline-key')
    monkeypatch.setattr(sys, 'argv', ['collector', '--tickers', 'IWM QQQ'])
    class SlowBody(_FakeResponse):
        @property
        def raw(self):
            raw = super().raw
            original = raw.read
            def read(*args, **kwargs):
                clock[0] += 4.0
                return original(*args, **kwargs)
            raw.read = read
            return raw
    def request(*args, **kwargs):
        calls.append(kwargs['params']['symbol'])
        return SlowBody(_good_payload())
    monkeypatch.setattr(mod.requests, 'get', request)
    monkeypatch.setattr(mod, 'upsert_dataframe', lambda df, *a: writes.append(df['ticker'].iloc[0]) or len(df))
    caplog.set_level(logging.INFO)
    with pytest.raises(SystemExit) as result:
        mod.main()
    assert result.value.code == 1
    assert calls == ['IWM', 'QQQ']
    assert writes == ['IWM']
    assert '1 acknowledged contracts written' in caplog.text
    assert 'source_deadline' in caplog.text


@pytest.mark.parametrize('encoding', ['identity', 'gzip'])
def test_actual_urllib3_wire_and_decoded_limits(monkeypatch, encoding):
    import gzip
    import io
    from types import SimpleNamespace
    from urllib3.response import HTTPResponse
    from gcp.fetchers import _av_realtime_transport as transport
    limit = 10 * 1024 * 1024  # Approved contract, independent of implementation.
    body = json.dumps('x' * limit).encode()
    wire = gzip.compress(body) if encoding == 'gzip' else body
    if encoding == 'gzip':
        assert len(wire) < limit < len(body)
    else:
        assert len(wire) > limit
    raw = HTTPResponse(body=io.BytesIO(wire), headers={'content-encoding': encoding}, preload_content=False)
    with pytest.raises(transport.SourceBodyLimit):
        transport._source_json(SimpleNamespace(raw=raw), transport.deadline())
    raw.close()


def test_actual_requests_bad_status_fails_with_fixed_safe_reason(monkeypatch):
    import io
    import requests
    from urllib3.response import HTTPResponse
    from gcp.fetchers import _av_realtime_transport as transport
    response = requests.Response()
    response.status_code = 503
    response.reason = 'PRIVATE_PROVIDER_REASON'
    response.url = 'https://invalid.example/?apikey=PRIVATE_KEY'
    response.raw = HTTPResponse(body=io.BytesIO(b'PRIVATE_BODY'), preload_content=False)
    observed = []
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: response)
    with pytest.raises(requests.HTTPError) as error:
        transport.decoded_json({}, transport.deadline(), observed.append)
    assert str(error.value) == 'http_error'
    assert observed == [response]
    assert response.raw.closed


# ──────────────────────────────────────────────────────────────────────
# FEAT-OPTION-001 source budget (spec 2026-10-31, revision 6, rules 1-10)
#
# _SourceSim drives the original scheduled entry on a fake source clock.
# Its timer stands in for the transport's SIGALRM: the transport arms it
# through signal.setitimer, and when fake work crosses the armed instant
# the installed handler runs exactly as the real signal would. Defaults:
# connect 0.2 s, body 0.8 s, persistence 0.5 s, pace 0.4 s. No provider,
# SQL or GCP call is made.
# ──────────────────────────────────────────────────────────────────────

class _SourceSim:
    START = 1000.0

    def __init__(self, monkeypatch, *, tickers='SPY IWM QQQ', connect=0.2,
                 body=0.8, persistence=0.5, pace=0.4, empty=()):
        import signal
        import sys
        from types import SimpleNamespace
        from gcp.fetchers import _av_realtime_collector as mod
        self.mod = mod
        self.transport = mod._cli_transport
        self.true = self.START      # what a real monotonic clock would read
        self.offset = 0.0           # a scripted clock step (group d only)
        self.alarm = None
        self.connect = connect
        self.body = body if isinstance(body, dict) else {}
        self.default_body = body if not isinstance(body, dict) else 0.8
        self.persistence = persistence if isinstance(persistence, dict) else {}
        self.default_persistence = persistence if not isinstance(persistence, dict) else 0.5
        self.empty = set(empty)
        self.requests = []          # (ticker, true start)
        self.call_ends = []         # (ticker, true end) per decoded_json
        self.writes = []            # (ticker, rows)
        self.write_hook = None
        self.budgets = []
        self.normalize_hook = None

        monkeypatch.setattr(self.transport, '_source_clock', lambda: self.true + self.offset)
        monkeypatch.setattr(signal, 'setitimer', self._setitimer)
        monkeypatch.setattr(self.transport.time, 'sleep', self.advance)
        monkeypatch.setattr(mod, '_av_cfg', SimpleNamespace(delay_between_calls=pace))
        monkeypatch.setattr(mod, '_regular_session_due', lambda stamp: True)
        monkeypatch.setattr(mod, 'is_cloud_sql_configured', lambda: True)
        monkeypatch.setenv('AV_API_KEY', 'offline-key')
        monkeypatch.setattr(sys, 'argv', ['collector', '--tickers', tickers])
        monkeypatch.setattr(mod.requests, 'get', self._get)
        monkeypatch.setattr(mod, 'upsert_dataframe', self._upsert)
        real_decoded = self.transport.decoded_json

        def decoded(params, deadline, observed):
            try:
                return real_decoded(params, deadline, observed)
            finally:
                self.call_ends.append((params['symbol'], self.true))
        monkeypatch.setattr(self.transport, 'decoded_json', decoded)
        real_normalize = mod._normalize_av_response

        def normalize(*args, **kwargs):
            result = real_normalize(*args, **kwargs)
            if self.normalize_hook is not None:
                self.normalize_hook(self)
            return result
        monkeypatch.setattr(mod, '_normalize_av_response', normalize)
        budget_type = getattr(mod, '_SourceBudget', None)
        if budget_type is not None:
            original_init = budget_type.__init__

            def init(budget):
                original_init(budget)
                self.budgets.append(budget)
            monkeypatch.setattr(budget_type, '__init__', init)

    def _setitimer(self, which, seconds, interval=0.0):
        self.alarm = self.true + seconds if seconds > 0 else None
        return (0.0, 0.0)

    def advance(self, seconds):
        import signal
        target = self.true + seconds
        if self.alarm is not None and target >= self.alarm:
            self.true, self.alarm = self.alarm, None
            signal.getsignal(signal.SIGALRM)(signal.SIGALRM, None)
        self.true = target

    def rel(self, value):
        return value - self.START

    def _get(self, *args, **kwargs):
        ticker = kwargs['params']['symbol']
        self.requests.append((ticker, self.true))
        self.advance(self.connect)
        sim = self
        body = self.body.get(ticker, self.default_body)
        payload = _empty_payload() if ticker in self.empty else _good_payload()

        class Body(_FakeResponse):
            charged = False

            @property
            def raw(self):
                raw = super().raw
                original = raw.read

                def read(*a, **k):
                    if not Body.charged:
                        Body.charged = True
                        sim.advance(body)
                    return original(*a, **k)
                raw.read = read
                return raw
        return Body(payload)

    def _upsert(self, df, *args):
        ticker = df['ticker'].iloc[0]
        self.writes.append((ticker, len(df)))
        if self.write_hook is not None:
            result = self.write_hook(self, ticker, df)
            if result is not None:
                return result
        self.advance(self.persistence.get(ticker, self.default_persistence))
        return len(df)

    def run(self):
        try:
            self.mod.main()
        except SystemExit as exit_:
            return exit_.code
        return 0

    def requested(self):
        return [ticker for ticker, _ in self.requests]

    def written(self):
        return [ticker for ticker, _ in self.writes]


@pytest.mark.parametrize('slow', [13.0, 20.0])
@pytest.mark.parametrize('position', ['SPY', 'IWM', 'QQQ'], ids=['first', 'middle', 'final'])
def test_persistence_time_excluded_from_shared_source_budget(monkeypatch, caplog, position, slow):
    """#1646: slow persistence on any ticker no longer refuses a later ticker."""
    sim = _SourceSim(monkeypatch, persistence={position: slow})
    caplog.set_level(logging.INFO)
    assert sim.run() == 0
    assert sim.requested() == ['SPY', 'IWM', 'QQQ']
    assert sim.written() == ['SPY', 'IWM', 'QQQ']
    assert '3 acknowledged contracts written, 0 errors' in caplog.text
    assert 'source_deadline' not in caplog.text and 'UNAVAILABLE' not in caplog.text


def test_source_budget_is_cumulative_never_reset_or_revived(monkeypatch, caplog):
    from gcp.fetchers import _av_realtime_collector as mod
    # Provider time accumulates across ticker boundaries with no reset:
    # 6 s bodies and no persistence time leave QQQ interrupted mid-body.
    sim = _SourceSim(monkeypatch, body=6.0, persistence=0.0)
    deadlines = []
    sim.write_hook = lambda s, ticker, df: deadlines.append(s.budgets[0].deadline()) and None
    caplog.set_level(logging.INFO)
    assert sim.run() == 1
    assert sim.requested() == ['SPY', 'IWM', 'QQQ'] and sim.written() == ['SPY', 'IWM']
    assert deadlines == [pytest.approx(sim.START + 15.0)] * 2
    assert '"ticker":"QQQ"' in caplog.text and 'source_deadline' in caplog.text

    # A budget already exhausted when persistence begins stays exhausted:
    # uninterrupted CPU work runs past the deadline before the pause.
    caplog.clear()
    sim = _SourceSim(monkeypatch, body={'SPY': 14.5}, persistence={'SPY': 30.0})
    sim.normalize_hook = lambda s: s.advance(1.0) if len(s.requests) == 1 else None
    seen = []
    sim.write_hook = lambda s, ticker, df: seen.append(s.budgets[0].exhausted) and None
    assert sim.run() == 1
    assert sim.requested() == ['SPY'] and sim.written() == ['SPY']
    assert seen == [True] and sim.budgets[0].exhausted
    assert '1 acknowledged contracts written, 2 errors' in caplog.text
    assert caplog.text.count('realtime UNAVAILABLE') == 2

    # Persistence credit never restores more than the remainder held at the
    # trusted pause reading, including where q + r rounds upward.
    readings = iter([0.0, 10.25])
    monkeypatch.setattr(mod._SourceBudget, '_clock', staticmethod(lambda point: next(readings)))
    budget = mod._SourceBudget()
    budget.pause()
    held = budget._held
    assert held == 4.75
    for q in (10.25, 123.456789, 987654.321, 2.0 ** 40 + 0.1, 1e15 + 0.3):
        readings = iter([q])
        monkeypatch.setattr(mod._SourceBudget, '_clock', staticmethod(lambda point: next(readings)))
        budget._paused, budget._held = True, held
        budget.resume()
        assert not budget.exhausted
        assert 0 < budget.deadline() - q <= held
    # Later source work raises SourceDeadline with zero further requests.
    budget._exhausted = True
    with pytest.raises(mod._cli_transport.SourceDeadline):
        budget.checkpoint()
    assert math.isnan(budget.deadline())


_BAD_READINGS = {
    'raises': 'raise',
    'nan': float('nan'),
    'inf': float('inf'),
    'string': '1000.0',
    'bool': True,
    'backward': 'backward',
}


def _faulty_clock(monkeypatch, at, count, value):
    """Return value instead of the true reading at the count-th covered `at`."""
    from gcp.fetchers import _av_realtime_collector as mod
    original = mod._SourceBudget._clock
    seen = {}

    def clock(point):
        reading = original(point)
        seen[point] = seen.get(point, 0) + 1
        if point == at and seen[point] == count:
            if value == 'raise':
                raise RuntimeError('clock unavailable')
            if value == 'backward':
                return reading - 5.0
            return value
        return reading
    monkeypatch.setattr(mod._SourceBudget, '_clock', staticmethod(clock))


@pytest.mark.parametrize('fault', [k for k in _BAD_READINGS if k != 'backward'] + ['non-advancing'])
def test_untrusted_clock_readings_fail_later_source_closed_creation(monkeypatch, caplog, fault):
    """Group (a): an untrusted creation reading exits before any request or write."""
    sim = _SourceSim(monkeypatch)
    if fault == 'non-advancing':
        sim.true = 1.7e308  # c0 + 15 == c0
    else:
        _faulty_clock(monkeypatch, 'create', 1, _BAD_READINGS[fault])
    caplog.set_level(logging.INFO)
    assert sim.run() == 1
    assert sim.requests == [] and sim.writes == []
    assert 'source deadline unavailable' in caplog.text


@pytest.mark.parametrize('fault', list(_BAD_READINGS))
@pytest.mark.parametrize('where', ['first-ticker', 'later-ticker', 'empty-retry'])
def test_untrusted_clock_readings_fail_later_source_closed_before_fetch(monkeypatch, caplog, fault, where):
    """Group (b): a faulty source-admission checkpoint refuses before dispatch."""
    empty = ('IWM',) if where == 'empty-retry' else ()
    sim = _SourceSim(monkeypatch, empty=empty)
    # admit #1 is SPY's request, #2 IWM's pace, #3 IWM's first retry pace.
    count = {'first-ticker': 1, 'later-ticker': 2, 'empty-retry': 3}[where]
    _faulty_clock(monkeypatch, 'admit', count, _BAD_READINGS[fault])
    caplog.set_level(logging.INFO)
    assert sim.run() == 1
    expected = {'first-ticker': [], 'later-ticker': ['SPY'], 'empty-retry': ['SPY', 'IWM']}[where]
    assert sim.requested() == expected   # nothing refetched or replayed
    assert sim.written() == ([] if where == 'first-ticker' else ['SPY'])
    assert sim.budgets[0].exhausted
    failed = {'first-ticker': 3, 'later-ticker': 2, 'empty-retry': 2}[where]
    assert caplog.text.count('realtime UNAVAILABLE') == failed
    assert ' failed' not in caplog.text.replace('Failed (', '')


_AFTER_FETCH_FAULTS = (
    [(at, fault) for at in ('post_call', 'pause', 'resume') for fault in _BAD_READINGS]
    + [('resume', 'absorbing'), ('resume', 'clamped'),
       ('pairing', 'double-pause'), ('pairing', 'resume-without-pause')])


@pytest.mark.parametrize('at, fault', _AFTER_FETCH_FAULTS)
@pytest.mark.parametrize('outcome', ['ack', 'short-ack', 'uncertain'])
def test_untrusted_clock_readings_fail_later_source_closed_after_fetch(monkeypatch, caplog, fault, at, outcome):
    """Group (c): exhaustion after a fetch keeps the current write and outcome."""
    sim = _SourceSim(monkeypatch)
    if fault == 'absorbing':
        _faulty_clock(monkeypatch, 'resume', 1, 2.0 ** 60)   # q + r rounds to q
    elif fault == 'clamped':
        _faulty_clock(monkeypatch, 'resume', 1, 2.0 ** 56)   # q + r rounds past r
    elif fault not in ('double-pause', 'resume-without-pause'):
        _faulty_clock(monkeypatch, at, 1, _BAD_READINGS[fault])

    def write(s, ticker, df):
        if ticker == 'SPY':
            if fault == 'double-pause':
                s.budgets[0].pause()
            if fault == 'resume-without-pause':
                s.budgets[0].resume()   # the collector's own resume now has no pause
            s.advance(0.5)
            if outcome == 'short-ack':
                return len(df) + 1
            if outcome == 'uncertain':
                raise RuntimeError('connection reset after a committed chunk')
        return None
    sim.write_hook = write
    caplog.set_level(logging.INFO)
    assert sim.run() == 1
    assert sim.requested() == ['SPY'] and sim.written() == ['SPY']   # one write, no refetch
    assert sim.budgets[0].exhausted
    if outcome == 'ack':
        assert 'upserted 1 acknowledged rows' in caplog.text
        assert "'IWM: unavailable', 'QQQ: unavailable'" in caplog.text
    elif outcome == 'short-ack':
        assert "'SPY: unavailable', 'IWM: unavailable', 'QQQ: unavailable'" in caplog.text
    else:
        assert 'write outcome uncertain' in caplog.text
        assert "'SPY: failed', 'IWM: unavailable', 'QQQ: unavailable'" in caplog.text


def test_untrusted_clock_readings_fail_later_source_closed_admitted_residual(monkeypatch, caplog):
    """Group (d): admitted backward steps are bounded or shown, not detected."""
    from gcp.fetchers import _av_realtime_collector as mod
    # Step after the post-call checkpoint: SPY normalization takes 2 s of true
    # time and the clock steps back 1.5 s, so the pause reads p with L <= p.
    sim = _SourceSim(monkeypatch)
    marks = {}

    def step_after_checkpoint(s):
        if len(s.requests) == 1:
            marks['checkpoint'] = s.true
            s.advance(2.0)
            s.offset = -1.5

    def held_at_pause(s, ticker, df):
        if ticker == 'SPY':
            marks['held'] = s.budgets[0]._held
            marks['true_pause'] = s.true
        return None
    sim.normalize_hook = step_after_checkpoint
    sim.write_hook = held_at_pause
    caplog.set_level(logging.INFO)
    assert sim.run() == 0
    true_remaining = (sim.START + 15.0) - marks['true_pause']
    overstated = marks['held'] - true_remaining
    since_checkpoint = marks['true_pause'] - marks['checkpoint']
    assert overstated == pytest.approx(1.5)
    assert 0 < overstated <= since_checkpoint      # the rule 5 bound
    assert sim.requested() == sim.written() == ['SPY', 'IWM', 'QQQ']
    assert not sim.budgets[0].exhausted

    # Step during IWM's provider call that lands at or above its admission
    # reading: the post-call checkpoint admits it; the pause overstates the
    # remainder by up to the pace before the call plus its provider time.
    caplog.clear()
    sim = _SourceSim(monkeypatch)
    marks = {}
    original = mod._SourceBudget._clock

    def clock(point):
        reading = original(point)
        if point == 'admit':
            marks.setdefault('admits', []).append(reading)
        return reading
    monkeypatch.setattr(mod._SourceBudget, '_clock', staticmethod(clock))

    def step_during_call(s):
        if len(s.requests) == 2:
            s.offset = -1.3   # true call end minus 1.3 s >= IWM's admission reading
    real_get = sim._get

    def get(*args, **kwargs):
        response = real_get(*args, **kwargs)
        step_during_call(sim)
        return response
    monkeypatch.setattr(mod.requests, 'get', get)

    def held_at_iwm_pause(s, ticker, df):
        if ticker == 'IWM':
            marks['held'] = s.budgets[0]._held
            marks['true_pause'] = s.true
            marks['deadline'] = s.budgets[0]._deadline   # set before the step
        return None
    sim.write_hook = held_at_iwm_pause
    assert sim.run() == 0
    iwm_admission = marks['admits'][1]
    assert sim.call_ends[1][1] + sim.offset >= iwm_admission   # admitted, not detected
    true_remaining = marks['deadline'] - marks['true_pause']
    overstated = marks['held'] - true_remaining
    pace_and_provider = 0.4 + 0.2 + 0.8
    assert overstated == pytest.approx(1.3)
    assert overstated > 0                      # outside the rule 5 bound (0 s here)
    assert overstated <= pace_and_provider + 1e-9
    assert sim.requested() == sim.written() == ['SPY', 'IWM', 'QQQ']
    assert not sim.budgets[0].exhausted


def test_untrusted_clock_budget_arithmetic_is_terminal(monkeypatch):
    """Non-finite budget arithmetic exhausts; no later reading revives it."""
    from gcp.fetchers import _av_realtime_collector as mod
    readings = iter([0.0, 1.0, 2.0, 3.0, 4.0])
    monkeypatch.setattr(mod._SourceBudget, '_clock', staticmethod(lambda point: next(readings)))
    budget = mod._SourceBudget()
    budget.pause()
    budget._held = math.inf
    budget.resume()
    assert budget.exhausted
    with pytest.raises(mod._cli_transport.SourceDeadline):
        budget.checkpoint()
    budget.pause()
    budget.resume()
    assert budget.exhausted and math.isnan(budget.deadline())


@pytest.mark.parametrize('failure', ['raises', 'short-ack'])
def test_persistence_exception_and_short_ack_keep_outcome_and_resume_budget(monkeypatch, caplog, failure):
    sim = _SourceSim(monkeypatch, persistence={'SPY': 9.0})
    held = {}
    committed = []

    def write(s, ticker, df):
        if ticker == 'SPY':
            held['r'] = s.budgets[0]._held
            committed.append('chunk-1')
            s.advance(9.0)
            if failure == 'raises':
                raise RuntimeError('connection reset after chunk 1 committed')
            return len(df) - 1 if len(df) > 1 else 0
        if ticker == 'IWM':
            held['iwm_deadline_left'] = s.budgets[0].deadline() - (s.true + s.offset)
        return None
    sim.write_hook = write
    original_checkpoint = sim.mod._SourceBudget.checkpoint
    after = []

    def checkpoint(budget):
        deadline = original_checkpoint(budget)
        after.append(deadline - budget._last)
        return deadline
    monkeypatch.setattr(sim.mod._SourceBudget, 'checkpoint', checkpoint)
    caplog.set_level(logging.INFO)
    assert sim.run() == 1
    assert sim.requested() == ['SPY', 'IWM', 'QQQ'] and sim.written() == ['SPY', 'IWM', 'QQQ']
    # IWM's admission sees exactly the remainder held before SPY's write.
    assert after[1] == pytest.approx(held['r'])
    if failure == 'raises':
        assert 'write outcome uncertain; partial chunks may have committed' in caplog.text
        assert "Failed (1): ['SPY: failed']" in caplog.text
    else:
        assert "Failed (1): ['SPY: unavailable']" in caplog.text
    assert 'source_deadline' not in caplog.text


def test_provider_budget_exhaustion_and_retry_pacing_consume_source_budget(monkeypatch, caplog):
    # Provider time alone past 15 s refuses or interrupts the later ticker.
    sim = _SourceSim(monkeypatch, body=7.5, persistence=0.0)
    caplog.set_level(logging.INFO)
    assert sim.run() == 1
    assert sim.written() == ['SPY'] and 'IWM' in sim.requested()
    assert 'QQQ' not in sim.written()

    # S7: connect 0.2 s, SPY body 14 s, persistence 0.5 s excluded.
    caplog.clear()
    sim = _SourceSim(monkeypatch, body={'SPY': 14.0, 'IWM': 14.0, 'QQQ': 14.0})
    assert sim.run() == 1
    assert sim.requested() == ['SPY', 'IWM'] and sim.written() == ['SPY']
    (_, iwm_start), (_, iwm_end) = sim.requests[1], sim.call_ends[1]
    assert sim.rel(iwm_start) == pytest.approx(15.1)
    assert iwm_end - iwm_start == pytest.approx(0.36)
    events = [e for e in _attempt_events(caplog) if e['ticker'] == 'IWM']
    assert [e['error_class'] for e in events] == ['source_deadline']
    assert "Failed (2): ['IWM: unavailable', 'QQQ: unavailable']" in caplog.text

    # Retry refusal: IWM body 6.3 s with a literal-empty list on every attempt.
    caplog.clear()
    sim = _SourceSim(monkeypatch, body={'IWM': 6.3}, empty=('IWM',))
    paces = []
    real_pace = sim.transport.pace

    def pace(deadline, delay):
        paces.append((sim.rel(sim.true), sim.rel(deadline)))
        return real_pace(deadline, delay)
    monkeypatch.setattr(sim.transport, 'pace', pace)
    assert sim.run() == 1
    assert sim.requested() == ['SPY', 'IWM', 'IWM'] and sim.written() == ['SPY']
    assert sim.rel(sim.call_ends[2][1]) == pytest.approx(15.3)   # attempt 2 ends
    # IWM admission, retry 1, refused retry 2, refused QQQ admission.
    assert [round(at, 6) for at, _ in paces] == [1.5, 8.4, 15.3, 15.3]
    assert all(dl == pytest.approx(15.5) for _, dl in paces)
    assert 'source pacing unavailable' not in caplog.text   # fixed reason never logged
    assert "Failed (2): ['IWM: unavailable', 'QQQ: unavailable']" in caplog.text
