"""lib.api_client.request_failure_reason names a failed request without it.

The text of a requests HTTPError, and of most transport errors, holds the full
request URL, and an AlphaVantage URL holds the API key (#2085). The fetcher
sites that log this reason are covered in
tests/gcp/test_av_request_failure_reasons.py.
"""
import pytest
import requests

from lib.api_client import request_failure_reason

SENTINEL = "SENTINELKEY0123456789"
URL = f"https://www.alphavantage.co/query?function=X&symbol=SPY&apikey={SENTINEL}&datatype=json"


def _http_503():
    resp = requests.Response()
    resp.status_code = 503
    resp.reason = "Service Unavailable"
    resp.url = URL
    return resp


def _connection_error():
    return requests.ConnectionError(
        f"HTTPSConnectionPool(host='www.alphavantage.co', port=443): Max retries "
        f"exceeded with url: /query?function=X&apikey={SENTINEL} (Caused by reset)")


def test_reason_for_an_http_error_is_its_status():
    with pytest.raises(requests.HTTPError) as info:
        _http_503().raise_for_status()
    assert SENTINEL in str(info.value)  # the leak this guards against is real
    assert request_failure_reason(info.value) == "request_failed: HTTP 503"


@pytest.mark.parametrize("exc, expected", [
    (_connection_error(), "request_failed: ConnectionError"),
    (requests.Timeout(f"Read timed out. url: {URL}"), "request_failed: Timeout"),
    (requests.exceptions.JSONDecodeError("Expecting value", f"<html>{URL}</html>", 0),
     "request_failed: JSONDecodeError"),
])
def test_reason_for_a_request_error_is_its_class(exc, expected):
    reason = request_failure_reason(exc)
    assert reason == expected and SENTINEL not in reason


def test_reason_for_a_parse_error_keeps_its_message_truncated():
    assert request_failure_reason(KeyError("1. open")) == "KeyError: '1. open'"
    assert len(request_failure_reason(ValueError("x" * 500))) == 160


def test_splits_reason_delegates_with_unchanged_output():
    from gcp.fetchers import compute_earnings_reactions as cer
    with pytest.raises(requests.HTTPError) as info:
        _http_503().raise_for_status()
    assert cer._request_failure(info.value) == "request_failed: HTTP 503"
    assert cer._request_failure(_connection_error()) == "request_failed: ConnectionError"
