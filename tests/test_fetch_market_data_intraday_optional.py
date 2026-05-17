"""Tests for the intraday-optional daily-row path in fetch_market_data.

Before this fix, `process_ticker` did `if minute_df.empty: return` — so
any ticker AlphaVantage had no 1-min intraday coverage for got NO daily
OHLCV row and NO indicators that day. AV intraday is reliable for liquid
ETFs/large-caps but spotty for the long tail of earnings names, so the
short-circuit silently dropped most of them.

The fix:
  - `build_daily_row` builds from `av_ohlcv` alone when intraday is
    absent (skipping the VWAP fields, which genuinely need 1-min bars).
  - `fetch_daily_from_av` gains `allow_fallback`: the no-intraday caller
    passes False so a holiday doesn't get a row stamped with the prior
    session's prices.

These tests cover the pure functions without mocking the AV/DB pipeline.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from gcp.fetchers.fetch_market_data import build_daily_row, fetch_daily_from_av


def _minute_df():
    """A minimal 3-bar intraday frame with a datetime index."""
    idx = pd.to_datetime([
        '2026-05-15 09:30', '2026-05-15 09:31', '2026-05-15 09:32',
    ])
    return pd.DataFrame({
        'Open':   [100.0, 100.5, 101.0],
        'High':   [100.6, 101.1, 101.4],
        'Low':    [ 99.8, 100.2, 100.7],
        'Close':  [100.5, 101.0, 101.2],
        'Volume': [10_000, 12_000, 11_000],
    }, index=idx)


_AV_OHLCV = {
    'open': 100.0, 'high': 102.0, 'low': 99.0,
    'close': 101.5, 'adjusted_close': 101.5, 'volume': 5_000_000,
}


class TestBuildDailyRow:
    def test_empty_minute_and_no_av_returns_empty(self):
        """Genuinely nothing to write → {} (the only remaining short-circuit)."""
        assert build_daily_row('XYZ', pd.DataFrame(), '2026-05-15', None) == {}

    def test_av_only_builds_row_without_intraday(self):
        """The fix: empty intraday + av_ohlcv present → a valid daily row,
        sourced from AV daily, with the VWAP fields simply absent."""
        row = build_daily_row('XYZ', pd.DataFrame(), '2026-05-15', _AV_OHLCV)
        assert row, "row must not be empty when av_ohlcv is present"
        assert row['ticker'] == 'XYZ'
        assert str(row['date']) == '2026-05-15'
        assert row['close'] == 101.5
        assert row['data_source'] == 'alphavantage_daily'
        # VWAP needs 1-min bars — correctly absent on the AV-daily-only path
        assert 'vwap' not in row
        assert 'price_vs_vwap' not in row

    def test_intraday_present_still_computes_vwap(self):
        """Regression guard: the normal intraday path is unchanged —
        VWAP is still computed when 1-min bars exist."""
        row = build_daily_row('XYZ', _minute_df(), '2026-05-15', _AV_OHLCV)
        assert row['data_source'] == 'alphavantage_daily'
        assert 'vwap' in row and row['vwap'] > 0

    def test_intraday_only_aggregates_when_no_av(self):
        """Intraday present, no AV daily → aggregate OHLCV from 1-min bars."""
        row = build_daily_row('XYZ', _minute_df(), '2026-05-15', None)
        assert row['data_source'] == 'alphavantage_1min'
        assert row['open'] == 100.0          # first bar open
        assert row['close'] == 101.2         # last bar close
        assert row['volume'] == 33_000       # summed


def _av_response(time_series: dict):
    """Build a fake requests.Response for TIME_SERIES_DAILY_ADJUSTED."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {'Time Series (Daily)': time_series}
    return resp


def _av_bar():
    return {
        '1. open': '100.0', '2. high': '102.0', '3. low': '99.0',
        '4. close': '101.5', '5. adjusted close': '101.5', '6. volume': '5000000',
    }


class TestFetchDailyFromAvFallback:
    def test_exact_match_returns_data_regardless_of_flag(self):
        """When AV has the exact fetch_date, both flag settings return it."""
        ts = {'2026-05-15': _av_bar()}
        for allow in (True, False):
            with patch('gcp.fetchers.fetch_market_data.requests.get',
                       return_value=_av_response(ts)):
                out = fetch_daily_from_av('XYZ', '2026-05-15', 'key',
                                          allow_fallback=allow)
            assert out['close'] == 101.5, f"allow_fallback={allow}"

    def test_fallback_true_uses_prior_day(self):
        """No entry for fetch_date, allow_fallback=True → prior trading day."""
        ts = {'2026-05-14': _av_bar()}  # fetch_date 05-15 absent
        with patch('gcp.fetchers.fetch_market_data.requests.get',
                   return_value=_av_response(ts)):
            out = fetch_daily_from_av('XYZ', '2026-05-15', 'key',
                                      allow_fallback=True)
        assert out['close'] == 101.5

    def test_fallback_false_refuses_prior_day(self):
        """The guard: no entry for fetch_date, allow_fallback=False →
        return {} rather than a row stamped with prior-session prices.
        This is what stops a holiday from getting a bogus daily bar."""
        ts = {'2026-05-14': _av_bar()}  # only prior day available
        with patch('gcp.fetchers.fetch_market_data.requests.get',
                   return_value=_av_response(ts)):
            out = fetch_daily_from_av('XYZ', '2026-05-15', 'key',
                                      allow_fallback=False)
        assert out == {}
