"""Verify _run_backfill honours AV_BACKFILL_SLEEP_SECS env override.

The hardcoded 13s sleep (free-tier safe) was the binding constraint that
prevented dispatching --backfill against the full 1,600+ ticker universe
in a single Cloud Run execution. The override lets premium-tier deploys
run at 1s (75 RPM) without code changes.
"""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    for k in ('AV_BACKFILL_SLEEP_SECS', 'BACKFILL_ALL_HISTORY',
              'ALPHA_VANTAGE_API_KEY'):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv('ALPHA_VANTAGE_API_KEY', 'fake-key')
    yield


def _stub_targets():
    """Two tickers, each needing a 'compact' pull (to exercise the sleep path)."""
    return [('AAA', 2000, pd.Timestamp('2026-05-28').date()),
            ('BBB', 2000, pd.Timestamp('2026-05-28').date())]


def _stub_av_df():
    return pd.DataFrame([{
        'ticker': 'X', 'date': pd.Timestamp('2026-05-29').date(),
        'open': 1.0, 'high': 1.0, 'low': 1.0, 'close': 1.0, 'volume': 100,
        'adjusted_close': 1.0,
    }])


@patch('gcp.fetchers.fetch_market_data.is_cloud_sql_configured', return_value=True)
@patch('gcp.fetchers.fetch_market_data._backfill_targets', side_effect=_stub_targets)
@patch('gcp.fetchers.fetch_market_data._av_get_full_daily_series',
       return_value=_stub_av_df())
def test_default_sleep_is_13s(mock_av, mock_targets, mock_cfg, monkeypatch):
    from gcp.fetchers import fetch_market_data
    # Block the real DB upsert.
    with patch('gcp.database.upsert_dataframe'), \
         patch('time.sleep') as sleep_mock:
        fetch_market_data._run_backfill()
    # Two pending → exactly one sleep call between them, at the default.
    sleep_mock.assert_called_once_with(13.0)


@patch('gcp.fetchers.fetch_market_data.is_cloud_sql_configured', return_value=True)
@patch('gcp.fetchers.fetch_market_data._backfill_targets', side_effect=_stub_targets)
@patch('gcp.fetchers.fetch_market_data._av_get_full_daily_series',
       return_value=_stub_av_df())
def test_env_override_lowers_sleep(mock_av, mock_targets, mock_cfg, monkeypatch):
    monkeypatch.setenv('AV_BACKFILL_SLEEP_SECS', '1.0')
    from gcp.fetchers import fetch_market_data
    with patch('gcp.database.upsert_dataframe'), \
         patch('time.sleep') as sleep_mock:
        fetch_market_data._run_backfill()
    sleep_mock.assert_called_once_with(1.0)


@patch('gcp.fetchers.fetch_market_data.is_cloud_sql_configured', return_value=True)
@patch('gcp.fetchers.fetch_market_data._backfill_targets', side_effect=_stub_targets)
@patch('gcp.fetchers.fetch_market_data._av_get_full_daily_series',
       return_value=_stub_av_df())
def test_zero_sleep_skips_call(mock_av, mock_targets, mock_cfg, monkeypatch):
    monkeypatch.setenv('AV_BACKFILL_SLEEP_SECS', '0')
    from gcp.fetchers import fetch_market_data
    with patch('gcp.database.upsert_dataframe'), \
         patch('time.sleep') as sleep_mock:
        fetch_market_data._run_backfill()
    sleep_mock.assert_not_called()


@patch('gcp.fetchers.fetch_market_data.is_cloud_sql_configured', return_value=True)
@patch('gcp.fetchers.fetch_market_data._backfill_targets', side_effect=_stub_targets)
@patch('gcp.fetchers.fetch_market_data._av_get_full_daily_series',
       return_value=_stub_av_df())
def test_invalid_env_falls_back_to_default(mock_av, mock_targets, mock_cfg, monkeypatch):
    monkeypatch.setenv('AV_BACKFILL_SLEEP_SECS', 'not-a-number')
    from gcp.fetchers import fetch_market_data
    with patch('gcp.database.upsert_dataframe'), \
         patch('time.sleep') as sleep_mock:
        fetch_market_data._run_backfill()
    sleep_mock.assert_called_once_with(13.0)


@patch('gcp.fetchers.fetch_market_data.is_cloud_sql_configured', return_value=True)
@patch('gcp.fetchers.fetch_market_data._backfill_targets', side_effect=_stub_targets)
@patch('gcp.fetchers.fetch_market_data._av_get_full_daily_series',
       return_value=_stub_av_df())
def test_negative_env_clamped_to_zero(mock_av, mock_targets, mock_cfg, monkeypatch):
    monkeypatch.setenv('AV_BACKFILL_SLEEP_SECS', '-5')
    from gcp.fetchers import fetch_market_data
    with patch('gcp.database.upsert_dataframe'), \
         patch('time.sleep') as sleep_mock:
        fetch_market_data._run_backfill()
    sleep_mock.assert_not_called()
