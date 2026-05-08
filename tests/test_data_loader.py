"""Tests for lib/data_loader.py — Data loading and normalization."""

import logging
from datetime import date, datetime

import pandas as pd
import numpy as np
import pytest
from pathlib import Path

from lib.data_loader import DataLoader, COLUMN_MAP, RESAMPLE_RULES, _check_staleness


@pytest.fixture
def loader(tmp_path, monkeypatch):
    """DataLoader pointing to a temp directory.

    Tests in this file exercise the file-system fallback code paths.
    With Cloud SQL credentials in env (`CLOUD_SQL_CONNECTION_NAME`
    set, e.g. when running locally with `.env` sourced) DataLoader
    queries Cloud SQL first and bypasses `data_dir` entirely, which
    breaks "empty when no local data" assertions. Clear the env var
    so the loader takes the parquet/CSV path the tests expect.
    """
    monkeypatch.delenv("CLOUD_SQL_CONNECTION_NAME", raising=False)
    return DataLoader(data_dir=str(tmp_path))


@pytest.fixture
def minute_data():
    """1-day of 1-minute OHLCV data (390 bars)."""
    np.random.seed(42)
    n = 390
    base = 200.0
    returns = np.random.normal(0, 0.001, n)
    close = base * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(np.random.normal(0, 0.001, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.001, n)))
    open_ = np.roll(close, 1)
    open_[0] = base
    volume = np.random.randint(10000, 100000, n).astype(float)

    times = pd.date_range('2024-01-02 09:30', periods=n, freq='1min')

    return pd.DataFrame({
        'Open': open_,
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': volume,
    }, index=times)


class TestNormalizeColumns:
    def test_renames_last_to_close(self, loader):
        df = pd.DataFrame({
            'Open': [100], 'High': [101], 'Low': [99],
            'Last': [100.5], 'Volume': [1000],
        }, index=pd.date_range('2024-01-01', periods=1))
        result = loader.normalize_columns(df)
        assert 'Close' in result.columns
        assert 'Last' not in result.columns

    def test_renames_lowercase(self, loader):
        df = pd.DataFrame({
            'open': [100], 'high': [101], 'low': [99],
            'close': [100.5], 'volume': [1000],
        }, index=pd.date_range('2024-01-01', periods=1))
        result = loader.normalize_columns(df)
        assert 'Close' in result.columns
        assert 'Open' in result.columns
        assert 'Volume' in result.columns

    def test_adds_time_from_index(self, loader):
        df = pd.DataFrame({
            'Open': [100], 'High': [101], 'Low': [99],
            'Close': [100.5], 'Volume': [1000],
        }, index=pd.date_range('2024-01-01', periods=1))
        result = loader.normalize_columns(df)
        assert 'Time' in result.columns

    def test_preserves_existing_columns(self, loader):
        df = pd.DataFrame({
            'Open': [100], 'High': [101], 'Low': [99],
            'Close': [100.5], 'Volume': [1000], 'Extra': [42],
        }, index=pd.date_range('2024-01-01', periods=1))
        result = loader.normalize_columns(df)
        assert 'Extra' in result.columns


class TestAggregateToTimeframe:
    def test_5min(self, loader, minute_data):
        result = loader.aggregate_to_timeframe(minute_data, '5m')
        assert len(result) < len(minute_data)
        # 390 bars / 5 = ~78 bars
        assert len(result) <= 80

    def test_15min(self, loader, minute_data):
        result = loader.aggregate_to_timeframe(minute_data, '15m')
        assert len(result) <= 30

    def test_1h(self, loader, minute_data):
        result = loader.aggregate_to_timeframe(minute_data, '1h')
        assert len(result) <= 10

    def test_daily(self, loader, minute_data):
        result = loader.aggregate_to_timeframe(minute_data, '1d')
        assert len(result) == 1  # Single day of data

    def test_has_ohlcv(self, loader, minute_data):
        result = loader.aggregate_to_timeframe(minute_data, '15m')
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            assert col in result.columns

    def test_high_is_max(self, loader, minute_data):
        result = loader.aggregate_to_timeframe(minute_data, '1h')
        # The aggregated High should be the max of the component bars
        for idx in result.index:
            mask = (minute_data.index >= idx) & (minute_data.index < idx + pd.Timedelta(hours=1))
            if mask.sum() > 0:
                assert result.loc[idx, 'High'] >= minute_data.loc[mask, 'High'].max() - 1e-10

    def test_invalid_timeframe(self, loader, minute_data):
        with pytest.raises(ValueError):
            loader.aggregate_to_timeframe(minute_data, '3m')


class TestBuildMultiTimeframe:
    def test_default_timeframes(self, loader, minute_data):
        result = loader.build_multi_timeframe(minute_data)
        assert isinstance(result, dict)
        # With only 1 day of data, daily and weekly should work
        assert '5m' in result
        assert '15m' in result

    def test_custom_timeframes(self, loader, minute_data):
        result = loader.build_multi_timeframe(minute_data, timeframes=['5m', '15m'])
        assert '5m' in result
        assert '15m' in result
        assert '1h' not in result


class TestLoadIntraday:
    def test_returns_empty_when_no_data(self, loader):
        result = loader.load_intraday('IWM')
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_loads_combined_parquet(self, loader, minute_data, tmp_path):
        # Create the expected directory structure
        ticker_dir = tmp_path / 'iwm' / 'intraday'
        ticker_dir.mkdir(parents=True)
        parquet_path = ticker_dir / 'iwm_av_1min_combined.parquet'
        minute_data.to_parquet(parquet_path)

        result = loader.load_intraday('IWM')
        assert not result.empty
        assert len(result) == len(minute_data)


class TestLoadDaily:
    def test_returns_empty_when_no_data(self, loader):
        result = loader.load_daily('IWM')
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_loads_yearly_parquet(self, loader, tmp_path):
        ticker_dir = tmp_path / 'iwm'
        ticker_dir.mkdir(parents=True)

        # Create a yearly parquet
        dates = pd.bdate_range('2024-01-02', periods=50)
        df = pd.DataFrame({
            'Open': np.random.uniform(195, 205, 50),
            'High': np.random.uniform(200, 210, 50),
            'Low': np.random.uniform(190, 200, 50),
            'Close': np.random.uniform(195, 205, 50),
            'Volume': np.random.randint(100000, 500000, 50),
        }, index=dates)
        df.to_parquet(ticker_dir / 'iwm_2024.parquet')

        result = loader.load_daily('IWM', year=2024)
        assert not result.empty
        assert len(result) == 50


class TestFilterDates:
    def test_filter_start(self, loader, minute_data):
        result = loader._filter_dates(minute_data, '2024-01-02 10:00', None)
        assert result.index.min() >= pd.Timestamp('2024-01-02 10:00')

    def test_filter_end(self, loader, minute_data):
        result = loader._filter_dates(minute_data, None, '2024-01-02 12:00')
        assert result.index.max() <= pd.Timestamp('2024-01-02 12:00')

    def test_filter_both(self, loader, minute_data):
        result = loader._filter_dates(minute_data, '2024-01-02 10:00', '2024-01-02 12:00')
        assert result.index.min() >= pd.Timestamp('2024-01-02 10:00')
        assert result.index.max() <= pd.Timestamp('2024-01-02 12:00')


# ---------------------------------------------------------------------------
# New test classes for newly-added functionality
# ---------------------------------------------------------------------------


class TestStripTimezone:
    """Tests for the _strip_timezone() helper method."""

    def test_strips_utc_timezone(self, loader):
        """Create a DataFrame with UTC timezone and verify it is removed."""
        times = pd.date_range('2024-01-02 09:30', periods=5, freq='1min', tz='UTC')
        df = pd.DataFrame({
            'Open': [100, 101, 102, 103, 104],
            'High': [105, 106, 107, 108, 109],
            'Low': [95, 96, 97, 98, 99],
            'Close': [102, 103, 104, 105, 106],
            'Volume': [1000, 1100, 1200, 1300, 1400],
        }, index=times)

        result = loader._strip_timezone(df)

        assert result.index.tz is None
        # Values should be preserved
        assert len(result) == 5
        assert result.iloc[0]['Close'] == 102

    def test_no_op_on_naive(self, loader):
        """Create a DataFrame without timezone and verify it is unchanged."""
        times = pd.date_range('2024-01-02 09:30', periods=5, freq='1min')
        df = pd.DataFrame({
            'Open': [100, 101, 102, 103, 104],
            'High': [105, 106, 107, 108, 109],
            'Low': [95, 96, 97, 98, 99],
            'Close': [102, 103, 104, 105, 106],
            'Volume': [1000, 1100, 1200, 1300, 1400],
        }, index=times)

        result = loader._strip_timezone(df)

        assert result.index.tz is None
        # Data should be identical (same object since no copy needed)
        pd.testing.assert_frame_equal(result, df)

    def test_strips_time_column_too(self, loader):
        """Verify the 'Time' column also gets timezone stripped."""
        times = pd.date_range('2024-01-02 09:30', periods=5, freq='1min', tz='UTC')
        df = pd.DataFrame({
            'Open': [100, 101, 102, 103, 104],
            'High': [105, 106, 107, 108, 109],
            'Low': [95, 96, 97, 98, 99],
            'Close': [102, 103, 104, 105, 106],
            'Volume': [1000, 1100, 1200, 1300, 1400],
            'Time': times,
        }, index=times)

        result = loader._strip_timezone(df)

        # Index should be tz-naive
        assert result.index.tz is None
        # Time column should also be tz-naive
        assert result['Time'].dt.tz is None
        # Timestamps should match after stripping
        expected_times = times.tz_localize(None)
        pd.testing.assert_index_equal(result.index, expected_times)
        pd.testing.assert_index_equal(
            pd.DatetimeIndex(result['Time']),
            expected_times,
            check_names=False,
        )


class TestLoadMinuteDir:
    """Tests for loading from the minute/ subdirectory (SPX format)."""

    def test_loads_daily_minute_parquets(self, loader, tmp_path):
        """Create a daily minute parquet in the minute/ dir and verify load_intraday finds it."""
        minute_dir = tmp_path / 'spx' / 'minute'
        minute_dir.mkdir(parents=True)

        # Create a small 1-minute parquet for one day
        times = pd.date_range('2025-10-01 09:30', periods=10, freq='1min')
        df = pd.DataFrame({
            'Open': np.arange(100, 110, dtype=float),
            'High': np.arange(101, 111, dtype=float),
            'Low': np.arange(99, 109, dtype=float),
            'Close': np.arange(100.5, 110.5, dtype=float),
            'Volume': np.full(10, 5000, dtype=float),
        }, index=times)
        df.to_parquet(minute_dir / 'spx_minute_20251001.parquet')

        result = loader.load_intraday('SPX')
        assert not result.empty
        assert len(result) == 10
        assert 'Close' in result.columns

    def test_intraday_dir_takes_priority(self, loader, tmp_path):
        """If both intraday/ and minute/ exist, intraday/ wins."""
        # Create intraday/ combined parquet (Priority 1)
        intraday_dir = tmp_path / 'spx' / 'intraday'
        intraday_dir.mkdir(parents=True)
        times_intraday = pd.date_range('2025-10-01 09:30', periods=5, freq='1min')
        df_intraday = pd.DataFrame({
            'Open': np.arange(200, 205, dtype=float),
            'High': np.arange(201, 206, dtype=float),
            'Low': np.arange(199, 204, dtype=float),
            'Close': np.arange(200.5, 205.5, dtype=float),
            'Volume': np.full(5, 8000, dtype=float),
        }, index=times_intraday)
        df_intraday.to_parquet(intraday_dir / 'spx_av_1min_combined.parquet')

        # Create minute/ parquet (Priority 3)
        minute_dir = tmp_path / 'spx' / 'minute'
        minute_dir.mkdir(parents=True)
        times_minute = pd.date_range('2025-10-01 09:30', periods=10, freq='1min')
        df_minute = pd.DataFrame({
            'Open': np.arange(100, 110, dtype=float),
            'High': np.arange(101, 111, dtype=float),
            'Low': np.arange(99, 109, dtype=float),
            'Close': np.arange(100.5, 110.5, dtype=float),
            'Volume': np.full(10, 5000, dtype=float),
        }, index=times_minute)
        df_minute.to_parquet(minute_dir / 'spx_minute_20251001.parquet')

        result = loader.load_intraday('SPX')
        # intraday/ has 5 bars, minute/ has 10 — we should get 5 (intraday wins)
        assert len(result) == 5

    def test_minute_dir_timezone_stripped(self, loader, tmp_path):
        """Create parquet with UTC timezone, verify timezone is stripped in output."""
        minute_dir = tmp_path / 'spx' / 'minute'
        minute_dir.mkdir(parents=True)

        times = pd.date_range('2025-10-01 09:30', periods=10, freq='1min', tz='UTC')
        df = pd.DataFrame({
            'Open': np.arange(100, 110, dtype=float),
            'High': np.arange(101, 111, dtype=float),
            'Low': np.arange(99, 109, dtype=float),
            'Close': np.arange(100.5, 110.5, dtype=float),
            'Volume': np.full(10, 5000, dtype=float),
        }, index=times)
        df.to_parquet(minute_dir / 'spx_minute_20251001.parquet')

        result = loader.load_intraday('SPX')
        assert not result.empty
        assert result.index.tz is None


class TestLoadBestAvailable:
    """Tests for the load_best_available() multi-source fallback method."""

    def test_prefers_intraday(self, loader, tmp_path):
        """Create data in both intraday/ and yearly parquet, verify intraday returned."""
        # Create intraday data
        intraday_dir = tmp_path / 'iwm' / 'intraday'
        intraday_dir.mkdir(parents=True)
        times = pd.date_range('2024-01-02 09:30', periods=20, freq='1min')
        df_intraday = pd.DataFrame({
            'Open': np.arange(200, 220, dtype=float),
            'High': np.arange(201, 221, dtype=float),
            'Low': np.arange(199, 219, dtype=float),
            'Close': np.arange(200.5, 220.5, dtype=float),
            'Volume': np.full(20, 9000, dtype=float),
        }, index=times)
        df_intraday.to_parquet(intraday_dir / 'iwm_av_1min_combined.parquet')

        # Create daily data
        ticker_dir = tmp_path / 'iwm'
        dates = pd.bdate_range('2024-01-02', periods=50)
        df_daily = pd.DataFrame({
            'Open': np.random.uniform(195, 205, 50),
            'High': np.random.uniform(200, 210, 50),
            'Low': np.random.uniform(190, 200, 50),
            'Close': np.random.uniform(195, 205, 50),
            'Volume': np.random.randint(100000, 500000, 50),
        }, index=dates)
        df_daily.to_parquet(ticker_dir / 'iwm_2024.parquet')

        result = loader.load_best_available('IWM')
        # Should return intraday (20 bars), not daily (50 bars)
        assert len(result) == 20

    def test_falls_back_to_daily(self, loader, tmp_path):
        """Create only yearly parquet, verify load_best_available returns it."""
        ticker_dir = tmp_path / 'iwm'
        ticker_dir.mkdir(parents=True)

        dates = pd.bdate_range('2024-01-02', periods=50)
        df_daily = pd.DataFrame({
            'Open': np.random.uniform(195, 205, 50),
            'High': np.random.uniform(200, 210, 50),
            'Low': np.random.uniform(190, 200, 50),
            'Close': np.random.uniform(195, 205, 50),
            'Volume': np.random.randint(100000, 500000, 50),
        }, index=dates)
        df_daily.to_parquet(ticker_dir / 'iwm_2024.parquet')

        result = loader.load_best_available('IWM')
        assert not result.empty
        assert len(result) == 50

    def test_empty_when_no_data(self, loader):
        """Verify empty DataFrame returned when no data exists for ticker."""
        result = loader.load_best_available('NONEXISTENT')
        assert isinstance(result, pd.DataFrame)
        assert result.empty


# ──────────────────────────────────────────────────────────────────────
# Staleness check (Track A G.P1.17)
# ──────────────────────────────────────────────────────────────────────


def _df_with_last_date(d: date) -> pd.DataFrame:
    return pd.DataFrame(
        {'Close': [100.0, 101.0]},
        index=pd.DatetimeIndex([d - pd.Timedelta(days=1), d]),
    )


class TestCheckStaleness:
    def test_silent_returns_without_check(self):
        df = _df_with_last_date(date(2026, 1, 1))
        # Even though df is months old, silent never warns or raises
        _check_staleness(df, 'SPY', max_age_days=2, on_stale='silent',
                         today=date(2026, 5, 8))

    def test_within_threshold_passes(self):
        today = date(2026, 5, 8)
        df = _df_with_last_date(today)
        _check_staleness(df, 'SPY', max_age_days=2, on_stale='warn',
                         today=today)
        # 1-day-old df is within threshold of 2 days
        df2 = _df_with_last_date(date(2026, 5, 7))
        _check_staleness(df2, 'SPY', max_age_days=2, on_stale='warn',
                         today=today)

    def test_warn_logs_warning(self, caplog):
        today = date(2026, 5, 8)
        df = _df_with_last_date(date(2026, 4, 27))  # 11 days old
        with caplog.at_level(logging.WARNING, logger='lib.data_loader'):
            _check_staleness(df, 'SPY', max_age_days=2, on_stale='warn',
                             today=today)
        assert any('SPY' in r.message and '11 days old' in r.message
                   for r in caplog.records)

    def test_error_raises(self):
        today = date(2026, 5, 8)
        df = _df_with_last_date(date(2026, 4, 27))
        with pytest.raises(RuntimeError) as exc:
            _check_staleness(df, 'SPY', max_age_days=2, on_stale='error',
                             today=today)
        assert 'SPY' in str(exc.value)
        assert '11 days' in str(exc.value)

    def test_empty_df_is_noop(self):
        # Empty df: caller decides; staleness check skips.
        _check_staleness(pd.DataFrame(), 'SPY', max_age_days=2,
                         on_stale='error', today=date(2026, 5, 8))

    def test_uses_date_col_when_provided(self, caplog):
        df = pd.DataFrame({
            'date': [date(2026, 4, 27), date(2026, 4, 28)],
            'close': [100.0, 101.0],
        })
        with caplog.at_level(logging.WARNING, logger='lib.data_loader'):
            _check_staleness(df, 'SPY', max_age_days=2, on_stale='warn',
                             date_col='date', today=date(2026, 5, 8))
        assert any('10 days old' in r.message for r in caplog.records)


class TestLoadDailyStaleness:
    """End-to-end check that load_daily wires `on_stale` through."""

    def test_load_daily_warn_on_stale_parquet(self, loader, caplog):
        # Plant a stale daily parquet
        ticker_dir = loader.data_dir / 'spy'
        ticker_dir.mkdir(parents=True)
        df = pd.DataFrame(
            {'Open': [100.0], 'High': [102.0], 'Low': [99.0],
             'Close': [101.0], 'Volume': [1_000_000]},
            index=pd.DatetimeIndex([pd.Timestamp('2025-01-01')]),
        )
        df.to_parquet(ticker_dir / 'spy_2025.parquet')

        # year=None triggers staleness check
        with caplog.at_level(logging.WARNING, logger='lib.data_loader'):
            out = loader.load_daily('SPY', on_stale='warn')

        assert not out.empty
        # Should have logged a warning (>2 days stale)
        assert any('SPY' in r.message and 'days old' in r.message
                   for r in caplog.records)

    def test_load_daily_year_scoped_skips_check(self, loader, caplog):
        """year != None means caller wants historical data on purpose."""
        ticker_dir = loader.data_dir / 'spy'
        ticker_dir.mkdir(parents=True)
        df = pd.DataFrame(
            {'Open': [100.0], 'High': [102.0], 'Low': [99.0],
             'Close': [101.0], 'Volume': [1_000_000]},
            index=pd.DatetimeIndex([pd.Timestamp('2025-01-01')]),
        )
        df.to_parquet(ticker_dir / 'spy_2025.parquet')

        with caplog.at_level(logging.WARNING, logger='lib.data_loader'):
            out = loader.load_daily('SPY', year=2025, on_stale='error')
        # Even with on_stale='error', year-scoped query doesn't raise
        assert not out.empty
        assert not any('days old' in r.message for r in caplog.records)
