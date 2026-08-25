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


class TestPickBackfillOutputsize:
    """Staleness-decision regression guards (issue #751 follow-up).

    The `<= 1` skip made the nightly chained backfill refresh each
    ticker only every OTHER evening: at 19:15 ET a ticker whose latest
    bar was yesterday counted as current, even though today's bar
    already existed upstream. Result: the tail's daily bar arrived up
    to 25h late and the 06:30 UTC enrich job saw alternating 2,400- vs
    ~850-ticker mornings (verified against 2026-08 run durations).
    """

    TODAY = pd.Timestamp('2026-08-24').date()

    def _pick(self, bar_count, max_date):
        from gcp.fetchers.fetch_market_data import _pick_backfill_outputsize
        return _pick_backfill_outputsize(bar_count, max_date, self.TODAY)

    def test_no_bars_bootstraps_full(self):
        assert self._pick(0, None) == 'full'

    def test_current_through_today_skips(self):
        assert self._pick(2000, self.TODAY) is None

    def test_stale_by_one_day_refreshes_compact(self):
        """THE regression guard: post-close, yesterday-fresh is stale —
        today's bar exists upstream and must be pulled tonight, not
        tomorrow night."""
        yesterday = self.TODAY - pd.Timedelta(days=1).to_pytimedelta()
        assert self._pick(2000, yesterday) == 'compact'

    def test_stale_90d_still_compact(self):
        d = self.TODAY - pd.Timedelta(days=90).to_pytimedelta()
        assert self._pick(2000, d) == 'compact'

    def test_stale_beyond_90d_full(self):
        d = self.TODAY - pd.Timedelta(days=91).to_pytimedelta()
        assert self._pick(2000, d) == 'full'

    def test_shallow_history_bootstraps_full_even_if_fresh(self):
        assert self._pick(100, self.TODAY) == 'full'


class TestBackfillDataSourceTag:
    def test_upserted_frame_carries_data_source(self):
        """The universe writer's rows must be attributable — they were
        the unattributable ~2,400 empty-data_source bars/night that
        made the issue #751 investigation need insert-hour forensics."""
        from gcp.fetchers import fetch_market_data as fmd
        bars = pd.DataFrame({
            'ticker': ['AAA'] * 3,
            'date': pd.to_datetime(['2026-08-20', '2026-08-21',
                                    '2026-08-24']).date,
            'open': [1.0, 1.1, 1.2], 'high': [1.1, 1.2, 1.3],
            'low': [0.9, 1.0, 1.1], 'close': [1.05, 1.15, 1.25],
            'volume': [1000, 1100, 1200],
        })
        with patch.object(fmd, '_backfill_targets',
                          return_value=[('AAA', 2000,
                                         pd.Timestamp('2026-05-01').date())]), \
             patch.object(fmd, '_av_get_full_daily_series',
                          return_value=bars), \
             patch('gcp.database.upsert_dataframe') as ups, \
             patch.object(fmd, 'is_cloud_sql_configured', return_value=True):
            os.environ['AV_BACKFILL_SLEEP_SECS'] = '0'
            try:
                fmd._run_backfill()
            finally:
                os.environ.pop('AV_BACKFILL_SLEEP_SECS', None)
        assert ups.called
        df_written = ups.call_args[0][0]
        assert 'data_source' in df_written.columns
        assert (df_written['data_source'] == 'av_daily_backfill').all()
