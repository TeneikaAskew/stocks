"""No AlphaVantage request failure writes the API key to the logs (#2085).

The text of a requests HTTPError, and of most transport errors, holds the
full request URL, and an AlphaVantage URL holds `apikey`. Each site below
used to log the exception object, which put the key in Cloud Logging
(fetch-earnings-history, 2026-11-24 and 2026-11-26, fetch_market_data.py:261).

Every case drives the real function with a real requests exception whose text
carries a sentinel key, then inspects every captured LogRecord: the formatted
message, `msg`, `args`, `exc_info`, `exc_text` and `stack_info`. It also pins
what each function returns, and the request it sent, to their base behaviour.
"""
import logging
import socket
import sys
from unittest.mock import patch

import pandas as pd
import pytest
import requests

from gcp.fetchers import fetch_av_earnings_options_backfill as backfill
from gcp.fetchers import fetch_av_historical_options as hist_opts
from gcp.fetchers import fetch_earnings_history as earnings
from gcp.fetchers import fetch_insider_transactions as insider
from gcp.fetchers import fetch_market_data as fmd
from gcp.fetchers import fetch_top_movers as movers
from lib.api_client import request_failure_reason

SENTINEL = "SENTINELKEY0123456789"
URL = f"https://www.alphavantage.co/query?function=X&symbol=SPY&apikey={SENTINEL}&datatype=json"


@pytest.fixture(autouse=True)
def _no_network():
    def refuse(*_a, **_k):
        raise AssertionError("network access attempted")
    with patch.object(socket.socket, "connect", refuse):
        yield


class _Records(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def records():
    handler = _Records()
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield handler.records
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)


def _http_503():
    """A real Response whose raise_for_status raises the real HTTPError."""
    resp = requests.Response()
    resp.status_code = 503
    resp.reason = "Service Unavailable"
    resp.url = URL
    return resp


def _connection_error():
    return requests.ConnectionError(
        f"HTTPSConnectionPool(host='www.alphavantage.co', port=443): Max retries "
        f"exceeded with url: /query?function=X&apikey={SENTINEL} (Caused by reset)")


def _timeout():
    return requests.Timeout(
        f"HTTPSConnectionPool(host='www.alphavantage.co', port=443): Read timed out. "
        f"(read timeout=30) url: {URL}")




def _stub(kind):
    """requests.get stand-in for one failure kind, recording each call."""
    calls = []

    def get(url, params=None, timeout=None, **kw):
        calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        if kind == "http_503":
            return _http_503()
        if kind == "connection_error":
            raise _connection_error()
        raise _timeout()
    return get, calls


def _assert_clean(records):
    assert records, "the failure logged nothing"
    for r in records:
        blob = " ".join([
            r.getMessage(), str(r.msg), repr(r.args),
            repr(r.exc_info), str(r.exc_text), str(r.stack_info),
        ])
        assert SENTINEL not in blob, f"key in log record: {r.getMessage()!r}"
        assert "apikey" not in blob, f"request URL in log record: {r.getMessage()!r}"
        assert r.exc_info is None


def _messages(records):
    return [r.getMessage() for r in records]


KINDS = ["http_503", "connection_error", "timeout"]
EXPECTED = {
    "http_503": "request_failed: HTTP 503",
    "connection_error": "request_failed: ConnectionError",
    "timeout": "request_failed: Timeout",
}


# --- one case per site --------------------------------------------------------

@pytest.mark.parametrize("kind", KINDS)
def test_fetch_minute_bars(kind, records):
    get, calls = _stub(kind)
    with patch.object(fmd.requests, "get", get):
        bars, reason = fmd.fetch_minute_bars("SPY", "2026-11-25", SENTINEL)
    assert bars.empty and reason == fmd.FETCH_REQUEST_ERROR
    assert len(calls) == 1 and calls[0]["params"]["apikey"] == SENTINEL
    assert calls[0]["timeout"] == 60
    _assert_clean(records)
    assert any(EXPECTED[kind] in m for m in _messages(records))


@pytest.mark.parametrize("kind", KINDS)
def test_fetch_daily_from_av(kind, records):
    get, calls = _stub(kind)
    with patch.object(fmd.requests, "get", get):
        got = fmd.fetch_daily_from_av("GLAS", "2026-11-25", SENTINEL)
    assert got == {}
    assert len(calls) == 1 and calls[0]["params"]["apikey"] == SENTINEL
    assert calls[0]["params"]["function"] == "TIME_SERIES_DAILY"
    assert calls[0]["timeout"] == 30
    _assert_clean(records)
    assert any(EXPECTED[kind] in m for m in _messages(records))


@pytest.mark.parametrize("kind", KINDS)
def test_av_get_full_daily_series(kind, records):
    get, calls = _stub(kind)
    with patch.object(fmd.requests, "get", get):
        got = fmd._av_get_full_daily_series("GBTG", SENTINEL, "full")
    assert isinstance(got, pd.DataFrame) and got.empty
    assert len(calls) == 1 and calls[0]["params"]["apikey"] == SENTINEL
    assert calls[0]["params"]["outputsize"] == "full" and calls[0]["timeout"] == 60
    _assert_clean(records)
    assert any(EXPECTED[kind] in m for m in _messages(records))


@pytest.mark.parametrize("kind", KINDS)
def test_fetch_history_for_ticker(kind, records):
    get, calls = _stub(kind)
    with patch.object(earnings.requests, "get", get):
        got = earnings.fetch_history_for_ticker("FSM", SENTINEL, enrich_with_yahoo=False)
    assert isinstance(got, pd.DataFrame) and got.empty
    assert len(calls) == 1 and calls[0]["params"] == {
        "function": "EARNINGS", "symbol": "FSM", "apikey": SENTINEL}
    assert calls[0]["timeout"] == 30
    _assert_clean(records)
    assert any(EXPECTED[kind] in m for m in _messages(records))


@pytest.mark.parametrize("kind", KINDS)
def test_insider_fetch_for_ticker(kind, records):
    get, calls = _stub(kind)
    with patch.object(insider.requests, "get", get):
        got = insider.fetch_for_ticker("SPY", SENTINEL)
    assert isinstance(got, pd.DataFrame) and got.empty
    assert len(calls) == 1 and calls[0]["params"] == {
        "function": "INSIDER_TRANSACTIONS", "symbol": "SPY", "apikey": SENTINEL}
    assert calls[0]["timeout"] == 30
    _assert_clean(records)
    assert any(EXPECTED[kind] in m for m in _messages(records))


@pytest.mark.parametrize("kind", KINDS)
def test_historical_options_fetch(kind, records):
    get, calls = _stub(kind)
    with patch.object(hist_opts.requests, "get", get):
        got = hist_opts.fetch_av_options("SPY", "2026-11-25", SENTINEL)
    assert isinstance(got, pd.DataFrame) and got.empty
    assert len(calls) == 1 and calls[0]["params"]["apikey"] == SENTINEL
    assert calls[0]["params"]["function"] == "HISTORICAL_OPTIONS" and calls[0]["timeout"] == 60
    _assert_clean(records)
    assert any(EXPECTED[kind] in m for m in _messages(records))


@pytest.mark.parametrize("kind", KINDS)
def test_top_movers_fetch(kind, records):
    get, calls = _stub(kind)
    with patch.object(movers.requests, "get", get):
        got = movers.fetch_top_movers(SENTINEL)
    assert isinstance(got, pd.DataFrame) and got.empty
    assert len(calls) == 1 and calls[0]["params"] == {
        "function": "TOP_GAINERS_LOSERS", "apikey": SENTINEL}
    assert calls[0]["timeout"] == 30
    _assert_clean(records)
    assert any(EXPECTED[kind] in m for m in _messages(records))


@pytest.mark.parametrize("kind, attempts", [
    ("http_503", 2),          # the HTTPError branch retries once, then logs both
    ("connection_error", 1),  # every other failure is logged and skipped
    ("timeout", 1),
])
def test_earnings_options_backfill_driver(kind, attempts, records, monkeypatch):
    get, calls = _stub(kind)
    events = pd.DataFrame([{"ticker": "SPY", "reported_date": "2026-11-25"}])
    monkeypatch.setenv("AV_API_KEY", SENTINEL)
    monkeypatch.setattr(sys, "argv", ["backfill", "--no-skip-existing"])

    def no_write(*_a, **_k):
        raise AssertionError("a failed fetch must not write")

    with patch.object(backfill.requests, "get", get), \
         patch.object(backfill, "is_cloud_sql_configured", return_value=True), \
         patch.object(backfill, "_load_event_list", return_value=events), \
         patch.object(backfill, "upsert_dataframe", no_write), \
         patch.object(backfill.time, "sleep"):
        with pytest.raises(SystemExit) as exit_info:
            backfill.main()
    assert exit_info.value.code == 2
    assert len(calls) == attempts
    assert all(c["params"]["apikey"] == SENTINEL and c["timeout"] == 60 for c in calls)
    _assert_clean(records)
    assert any(EXPECTED[kind] in m for m in _messages(records))


# --- the helper ---------------------------------------------------------------

def test_reason_for_an_http_error_is_its_status():
    try:
        _http_503().raise_for_status()
    except requests.HTTPError as exc:
        assert SENTINEL in str(exc)  # the leak this guards against is real
        assert request_failure_reason(exc) == "request_failed: HTTP 503"


@pytest.mark.parametrize("exc, expected", [
    (_connection_error(), "request_failed: ConnectionError"),
    (_timeout(), "request_failed: Timeout"),
    (requests.exceptions.JSONDecodeError("Expecting value", f"<html>{URL}</html>", 0),
     "request_failed: JSONDecodeError"),
])
def test_reason_for_a_request_error_is_its_class(exc, expected):
    assert request_failure_reason(exc) == expected


def test_reason_for_a_parse_error_keeps_its_message_truncated():
    assert request_failure_reason(KeyError("1. open")) == "KeyError: '1. open'"
    assert len(request_failure_reason(ValueError("x" * 500))) == 160


def test_splits_reason_is_unchanged():
    from gcp.fetchers import compute_earnings_reactions as cer
    try:
        _http_503().raise_for_status()
    except requests.HTTPError as exc:
        assert cer._request_failure(exc) == "request_failed: HTTP 503"
    assert cer._request_failure(_connection_error()) == "request_failed: ConnectionError"
