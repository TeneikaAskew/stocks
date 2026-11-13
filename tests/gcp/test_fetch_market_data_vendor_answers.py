"""Preserved vendor-answer contracts moved verbatim from evaluator tests.

These seven functions retain the 22 cases from #1181, #1188 and #1202.
"""
from unittest.mock import patch

import pandas as pd
import pytest

from gcp.fetchers import fetch_market_data as fmd


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _month(day: str) -> dict:
    """A TIME_SERIES_INTRADAY reply holding three bars on `day`."""
    ts = {f"{day} 09:3{i}:00": {"1. open": "10", "2. high": "11", "3. low": "9",
                                  "4. close": "10.5", "5. volume": "100"}
          for i in range(3)}
    return {"Meta Data": {}, "Time Series (1min)": ts}


@pytest.mark.parametrize("payload, reason", [
    ({"Error Message": "Invalid API call. Please retry or visit the documentation"},
     "invalid_api_call"),
    ({"Note": "Thank you for using Alpha Vantage! Please consider spreading out"},
     "rate_limit"),
    ({"Information": "Thank you for using Alpha Vantage! This is a premium endpoint"},
     "info_message"),
    ({"Meta Data": {}}, "no_timeseries"),
    ({"Meta Data": {}, "Time Series (1min)": {}}, "no_timeseries"),
    (_month("2026-06-01"), "no_bars_on_date"),
])
def test_fetch_minute_bars_names_the_vendors_answer(payload, reason):
    with patch.object(fmd.requests, "get", return_value=_Resp(payload)):
        bars, got = fmd.fetch_minute_bars("VSCO", "2026-06-02", "key")
    assert bars.empty and got == reason


def test_a_transport_failure_is_named():
    with patch.object(fmd.requests, "get", side_effect=fmd.requests.ConnectionError("reset")):
        bars, got = fmd.fetch_minute_bars("SPY", "2026-09-25", "key")
    assert bars.empty and got == "request_error"


@pytest.mark.parametrize("payload", [
    [], None, "Invalid API call", 5,
    {"Meta Data": {}, "Time Series (1min)": ["2026-09-25 09:30:00"]},
    {"Meta Data": {}, "Time Series (1min)": "unavailable"},
])
def test_a_reply_that_is_not_a_json_object_is_the_vendors_shape(payload):
    """Codex on #1202: a body that parses as JSON but is not an object, or a
    time series that is not one, raised AttributeError or TypeError out of
    this function. Before #1181 a bare `except Exception` made it an empty
    frame; it is the vendor's reply, so it is named like any other reply with
    no time series. The daily fetcher then still falls back to the daily
    endpoint, and the premarket refresh, which has no per-ticker guard, keeps
    going."""
    with patch.object(fmd.requests, "get", return_value=_Resp(payload)):
        bars, got = fmd.fetch_minute_bars("SPY", "2026-09-25", "key")
        df = fmd.fetch_minute_data("SPY", "2026-09-25", "key")
    assert bars.empty and got == "no_timeseries"
    assert isinstance(df, pd.DataFrame) and df.empty


def test_bars_on_the_date_come_back_ok():
    with patch.object(fmd.requests, "get", return_value=_Resp(_month("2026-09-25"))):
        bars, got = fmd.fetch_minute_bars("SPY", "2026-09-25", "key")
    assert got == "success" and len(bars) == 3 and set(bars["ticker"]) == {"SPY"}


@pytest.mark.parametrize("payload, n", [(_month("2026-09-25"), 3), ({"Note": "x"}, 0)])
def test_fetch_minute_data_keeps_its_contract(payload, n):
    """The daily fetcher and the premarket refresh still get one frame, empty
    on any failure. The reason is for callers that ask for it."""
    with patch.object(fmd.requests, "get", return_value=_Resp(payload)):
        df = fmd.fetch_minute_data("SPY", "2026-09-25", "key")
    assert isinstance(df, pd.DataFrame) and len(df) == n


@pytest.mark.parametrize("ticker, sent", [("BF.B", "BF-B"), ("MOG.A", "MOG-A"), ("SPY", "SPY")])
def test_av_listed_symbol(ticker, sent):
    assert fmd.av_listed_symbol(ticker) == sent


def _daily(day: str) -> dict:
    """A TIME_SERIES_DAILY_ADJUSTED reply holding one day."""
    return {"Meta Data": {}, "Time Series (Daily)": {day: {
        "1. open": "26.03", "2. high": "26.305", "3. low": "25.895", "4. close": "26.16",
        "5. adjusted close": "26.16", "6. volume": "1504871",
        "7. dividend amount": "0.0000", "8. split coefficient": "1.0"}}}


@pytest.mark.parametrize("call", ["minute", "daily", "daily_series"])
def test_every_price_call_sends_the_listed_share_class(call):
    """#1188: the daily fetcher and the premarket refresh sent BF.B and MOG.A
    dotted, which AlphaVantage refuses, so market_data_daily held no row for
    either. Every price call sends the listed form now, and what comes back
    stays keyed by the dotted ticker the rest of the system uses."""
    sent = []

    def get(url, params=None, timeout=None):
        sent.append(params["symbol"])
        return _Resp(_month("2026-09-25") if call == "minute" else _daily("2026-09-25"))

    with patch.object(fmd.requests, "get", side_effect=get):
        if call == "minute":
            bars, reason = fmd.fetch_minute_bars("BF.B", "2026-09-25", "key")
            assert reason == "success" and set(bars["ticker"]) == {"BF.B"}
        elif call == "daily":
            assert fmd.fetch_daily_from_av("BF.B", "2026-09-25", "key")["close"] == 26.16
        else:
            df = fmd._av_get_full_daily_series("BF.B", "key", "compact")
            assert set(df["ticker"]) == {"BF.B"}
    assert sent == ["BF-B"]

