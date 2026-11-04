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
    # Coherent OHLC: a gap from the previous close is still inside this
    # bar's range. Invalid constituents now intentionally invalidate aggregates.
    high = np.maximum(high, open_)
    low = np.minimum(low, open_)
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

    def test_unknown_timeframe_raises_through_build(self, loader, minute_data):
        """lib/strat.py relies on "an unknown key raises ValueError from
        build_multi_timeframe so mistakes surface loudly instead of
        producing empty FTFC"; the loop's `except Exception: continue`
        made that claim false and silently dropped the timeframe
        (internal review of #1022; CLAUDE.md 3.7)."""
        with pytest.raises(ValueError):
            loader.build_multi_timeframe(minute_data, timeframes=['5m', '3m'])


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


# ── value_col filter — placeholder rows must not look fresh ────────


class TestStalenessIgnoresNullCloseRows:
    """Track A G.P0.3 / G.P1.17 / codex review on PR #325:
    fetch-premarket-refresh writes today's market_data_daily row with
    pre_* fields and `close=NULL`. The staleness check must filter
    those rows out before computing MAX(date), or it'll silently report
    the table fresh-as-of-today while the latest USABLE OHLC bar is
    days old."""

    def test_check_staleness_filters_null_close_via_value_col(self, caplog):
        # Today is 2026-05-08. Latest real OHLC row is 2026-04-27 (11 days old).
        # Today's row exists but has NaN close (the placeholder pattern).
        df = pd.DataFrame({
            'Close': [100.0, 101.0, float('nan')],
        }, index=pd.DatetimeIndex([
            pd.Timestamp('2026-04-27'),  # last usable
            pd.Timestamp('2026-04-26'),
            pd.Timestamp('2026-05-08'),  # placeholder — will be filtered
        ]))
        with caplog.at_level(logging.WARNING, logger='lib.data_loader'):
            _check_staleness(
                df, 'SPY', max_age_days=2, on_stale='warn',
                value_col='Close', today=date(2026, 5, 8),
            )
        # Should warn — last usable bar is 11 days old, NOT today.
        assert any('11 days old' in r.message for r in caplog.records), (
            "Without value_col filtering, MAX(date)=2026-05-08 (the "
            "placeholder) and the check silently passes. With the "
            "filter, MAX(date)=2026-04-27 (the last real bar)."
        )

    def test_check_staleness_passes_when_today_has_real_close(self):
        """Sanity: when today's row has a real close, no warning fires."""
        df = pd.DataFrame({
            'Close': [100.0, 101.0],
        }, index=pd.DatetimeIndex([
            pd.Timestamp('2026-05-07'), pd.Timestamp('2026-05-08'),
        ]))
        # No exception on 'error', no warning logged
        _check_staleness(
            df, 'SPY', max_age_days=2, on_stale='error',
            value_col='Close', today=date(2026, 5, 8),
        )

    def test_check_staleness_warns_when_every_row_is_placeholder(self, caplog):
        df = pd.DataFrame({
            'Close': [float('nan'), float('nan')],
        }, index=pd.DatetimeIndex([
            pd.Timestamp('2026-05-07'), pd.Timestamp('2026-05-08'),
        ]))
        with caplog.at_level(logging.WARNING, logger='lib.data_loader'):
            _check_staleness(
                df, 'SPY', max_age_days=2, on_stale='warn',
                value_col='Close', today=date(2026, 5, 8),
            )
        assert any('no rows with non-null Close' in r.message
                   for r in caplog.records)

    def test_load_daily_warns_on_placeholder_today_row(self, loader, caplog):
        """End-to-end: load_daily reads a parquet where today's row has
        NaN Close + an older row has real Close. The staleness check
        must use the older real row's date, not today's placeholder."""
        ticker_dir = loader.data_dir / 'spy'
        ticker_dir.mkdir(parents=True)
        # Two-row dataset: real row from a year ago, placeholder for today
        df = pd.DataFrame({
            'Open': [100.0, float('nan')], 'High': [102.0, float('nan')],
            'Low': [99.0, float('nan')],
            'Close': [101.0, float('nan')],  # today's close is NaN
            'Volume': [1_000_000, 0],
        }, index=pd.DatetimeIndex([
            pd.Timestamp('2025-01-01'),
            pd.Timestamp(date.today()),  # today's placeholder
        ]))
        df.to_parquet(ticker_dir / 'spy_2025.parquet')

        with caplog.at_level(logging.WARNING, logger='lib.data_loader'):
            out = loader.load_daily('SPY', on_stale='warn')
        assert not out.empty
        # Must warn — last usable bar is 2025-01-01, far past 2-day threshold.
        # Without value_col, MAX(date)=today, no warning (the bug).
        assert any('SPY' in r.message and 'days old' in r.message
                   for r in caplog.records), (
            "load_daily must filter NaN-close placeholder rows before "
            "checking staleness."
        )


class TestLoadIntradayFromSqlClock:
    """Codex P1 on #1185: the Cloud SQL path returned the stored clock with its
    zone stripped. On a true-UTC day that is naive UTC, so a 09:30 ET bar read
    as 13:30 and every RTH filter downstream kept 05:30-12:00 ET. Both stored
    conventions must come back as the same naive-Eastern session."""

    @staticmethod
    def _stored(stored: str) -> pd.DataFrame:
        wall = pd.date_range("2026-09-24 04:00", "2026-09-24 20:00", freq="1min")
        minute = wall.hour * 60 + wall.minute
        if stored == "et_label":
            ts = wall.tz_localize("UTC")
        else:
            ts = wall.tz_localize("America/New_York").tz_convert("UTC")
        return pd.DataFrame({
            "ts": ts, "Open": 1.0, "High": 1.0, "Low": 1.0,
            "Close": np.arange(len(wall), dtype=float),
            "Volume": [5000 if 570 <= m < 600 else 100 for m in minute],
        })

    @pytest.mark.parametrize("stored", ["et_label", "utc"])
    def test_both_conventions_read_as_eastern(self, loader, monkeypatch, stored):
        import lib.data_loader as dl
        rows = self._stored(stored)
        monkeypatch.setattr(dl, "_cloud_sql_active", lambda: True)
        monkeypatch.setattr(dl, "_query_cloud_sql", lambda sql, params=None: rows.copy())
        df = loader.load_intraday("SPY", "2026-09-24", "2026-09-26")
        assert df.index.tz is None
        assert df.index[0] == pd.Timestamp("2026-09-24 04:00")
        assert df.index[-1] == pd.Timestamp("2026-09-24 20:00")
        assert (df["Time"] == df.index).all()
        # The open's volume spike sits at 09:30 ET, and the Close series
        # survives in order.
        assert df.loc[pd.Timestamp("2026-09-24 09:30"), "Volume"] == 5000
        assert df["Close"].is_monotonic_increasing
        assert "ts" not in df.columns


class TestLoadIntradayFromSqlBounds:
    """Codex P2 on #1185: the bounds are Eastern dates. Bound straight to
    TIMESTAMPTZ they read as UTC, so an EST request for D pulled in D-1's
    19:00-20:00 ET spill (raw D 00:00-01:00Z) and lost D's own."""

    @staticmethod
    def _true_utc(day: str) -> pd.DataFrame:
        wall = pd.date_range(f"{day} 04:00", f"{day} 20:00", freq="1min")
        minute = wall.hour * 60 + wall.minute
        return pd.DataFrame({
            "ts": wall.tz_localize("America/New_York").tz_convert("UTC"),
            "Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0,
            "Volume": [5000 if 570 <= m < 600 else 100 for m in minute],
        })

    def test_an_est_day_request_returns_exactly_that_session(self, loader, monkeypatch):
        import lib.data_loader as dl
        rows = pd.concat([self._true_utc("2026-01-14"), self._true_utc("2026-01-15"),
                          self._true_utc("2026-01-16")]).reset_index(drop=True)
        seen = {}

        def fake_sql(sql, params=None):
            seen.update(params)
            m = (rows["ts"] >= params["start"]) & (rows["ts"] <= params["end"])
            return rows[m].copy()

        monkeypatch.setattr(dl, "_cloud_sql_active", lambda: True)
        monkeypatch.setattr(dl, "_query_cloud_sql", fake_sql)
        df = loader.load_intraday("SPY", "2026-01-15", "2026-01-16")
        assert df.index.min() == pd.Timestamp("2026-01-15 04:00")
        assert df.index.max() == pd.Timestamp("2026-01-15 20:00")
        assert len(df) == 961
        # Raw window: D as a label, through D+1 00:00 ET as an instant.
        assert seen["start"] == pd.Timestamp("2026-01-15 00:00", tz="UTC")
        assert seen["end"] == pd.Timestamp("2026-01-16 05:00", tz="UTC")

    def test_an_aware_bound_is_converted_not_relabelled(self):
        import lib.data_loader as dl
        assert dl._eastern_bound(pd.Timestamp("2026-07-15 13:30", tz="UTC")) == \
            pd.Timestamp("2026-07-15 09:30")
        assert dl._eastern_bound("2026-07-15") == pd.Timestamp("2026-07-15")
        assert dl._eastern_bound(None) is None


class TestRecoveredObservationContract:
    """New recovery coverage; these are not the lost historical Task 2 tests."""

    @staticmethod
    def frame(index, *, daily=False):
        frame = pd.DataFrame({
            'Open': 100., 'High': 102., 'Low': 99., 'Close': 101., 'Volume': 10.,
        }, index=pd.DatetimeIndex(index))
        frame.attrs = {
            'source_resolution': '1d' if daily else '1min',
            'session_policy': 'NYSE_regular',
            'timestamp_semantics': 'session_label' if daily else 'bar_start',
        }
        return frame

    @staticmethod
    def observed(loader, frame, timeframe='5m', clock='2024-01-02 09:35-05:00'):
        return loader.aggregate_to_timeframe(
            frame, timeframe, observation_ts=clock, aggregation_policy='observed_v2')

    def test_completed_minutes_only_and_session_anchor(self, loader):
        frame = self.frame(pd.date_range('2024-01-02 09:29', periods=8, freq='min'))
        frame.loc[pd.Timestamp('2024-01-02 09:35'), 'High'] = 900.
        result = self.observed(loader, frame)
        assert list(result.index) == [pd.Timestamp('2024-01-02 09:30')]
        assert result.iloc[0].to_dict() == {
            'Open': 100., 'High': 102., 'Low': 99., 'Close': 101., 'Volume': 50.}
        coverage = result.attrs['period_coverage']['2024-01-02T14:30:00+00:00']
        assert coverage['source_cutoff'] == '2024-01-02T09:35:00-05:00'
        assert coverage['coverage_complete'] is True
        assert coverage['completed'] is True

    def test_live_build_resolves_one_clock(self, loader, monkeypatch):
        import lib.data_loader as module
        calls = []
        def now():
            calls.append(1)
            return pd.Timestamp('2024-01-02 09:34-05:00')
        monkeypatch.setattr(module, 'eastern_now', now)
        frame = self.frame(pd.date_range('2024-01-02 09:30', periods=6, freq='min'))
        live = loader.build_multi_timeframe(frame, ['5m', '1d'], aggregation_policy='observed_v2')
        assert len(calls) == 1
        for timeframe, actual in live.items():
            expected = self.observed(loader, frame, timeframe, '2024-01-02 14:34Z')
            pd.testing.assert_frame_equal(actual, expected)
            assert actual.attrs == expected.attrs
            coverage = actual.attrs['coverage']
            assert coverage['partial'] and coverage['period_open_observed']
            assert coverage['open'] == 100.
            assert coverage['observed_count'] == 4
            assert coverage['source_acquisition_status'] == 'unknown'
            assert coverage['source_acquired_at'] is None
            assert coverage['price_adjustment'] == 'unknown'

    @pytest.mark.parametrize('day,close', [
        ('2024-03-08', '21:00Z'), ('2024-03-11', '20:00Z'),
        ('2024-11-29', '18:00Z'),
    ])
    def test_daily_session_not_available_until_exchange_close(self, loader, day, close):
        frame = self.frame([pd.Timestamp(day, tz='UTC')], daily=True)
        clock = pd.Timestamp(f'{day} {close}')
        before = self.observed(loader, frame, '1d', clock-pd.Timedelta(seconds=1))
        after = self.observed(loader, frame, '1d', clock)
        assert before.empty
        assert before.attrs['coverage']['open'] is None
        assert len(after) == 1
        assert after.attrs['coverage']['completed'] is True
        assert after.attrs['coverage']['source_cutoff'] == clock.tz_convert('America/New_York').isoformat()

    def test_holiday_rows_are_not_daily_observations(self, loader):
        frame = self.frame(['2024-07-04', '2024-07-05'], daily=True)
        result = self.observed(loader, frame, '1d', '2024-07-05 16:00-04:00')
        assert list(result.index) == [pd.Timestamp('2024-07-05')]

    @pytest.mark.parametrize('timeframe,label', [
        ('1w', '2024-01-05'), ('1mo', '2024-01-31'),
        ('1q', '2024-03-31'), ('1y', '2024-12-31'),
    ])
    def test_current_period_open_requires_actual_opening_session(self, loader, timeframe, label):
        frame = self.frame(['2024-01-02', '2024-01-03'], daily=True)
        frame.iloc[1, frame.columns.get_loc('Open')] = 101.
        result = self.observed(loader, frame, timeframe, '2024-01-03 16:00-05:00')
        assert list(result.index) == [pd.Timestamp(label)]
        coverage = result.attrs['coverage']
        assert coverage['partial'] and coverage['coverage_complete']
        assert coverage['open'] == 100.
        assert coverage['source_cutoff'] == '2024-01-03T16:00:00-05:00'
        missing_open = self.observed(loader, frame.iloc[1:], timeframe, '2024-01-03 16:00-05:00')
        assert missing_open.attrs['coverage']['open'] is None
        assert 'missing_period_open' in missing_open.attrs['coverage']['reasons']

    def test_missing_interval_and_invalid_constituent_block_adjacency(self, loader):
        from lib.strat import StratClassifier
        index = pd.date_range('2024-01-02 09:30', periods=15, freq='min')
        frame = self.frame(index)
        missing = frame.drop(index[5:10])
        result = self.observed(loader, missing, clock='2024-01-02 09:45-05:00')
        assert result.attrs['gap_before_by_timestamp']['2024-01-02T14:40:00+00:00']
        assert StratClassifier().classify_series(result).iloc[-1] == 'X'
        frame.loc[index[2], 'Close'] = np.nan
        invalid = self.observed(loader, frame, clock='2024-01-02 09:45-05:00')
        assert invalid.iloc[0][['Open', 'High', 'Low', 'Close']].isna().all()
        assert invalid.attrs['gap_before_by_timestamp']['2024-01-02T14:35:00+00:00']

    @pytest.mark.parametrize('key,value,reason', [
        ('source_resolution', None, 'unknown_source_resolution'),
        ('source_resolution', '2d', 'unsupported_source_resolution'),
        ('source_resolution', '10min', 'source_resolution_too_coarse'),
        ('session_policy', 'unknown', 'unknown_session_policy'),
        ('timestamp_semantics', 'unknown', 'unsupported_timestamp_semantics'),
    ])
    def test_unsafe_source_contract_is_unavailable(self, loader, key, value, reason):
        frame = self.frame(pd.date_range('2024-01-02 09:30', periods=5, freq='min'))
        frame.attrs[key] = value
        result = self.observed(loader, frame)
        assert result.empty
        coverage = result.attrs['coverage']
        assert not coverage['available'] and not coverage['coverage_complete']
        assert coverage['open'] is None and coverage['source_cutoff'] is None
        assert reason in coverage['reasons']

    @pytest.mark.parametrize('kwargs', [
        {'observation_ts': '2024-01-02 10:00-05:00'},
        {'source_resolution': '1min'}, {'session_policy': 'NYSE_regular'},
    ])
    def test_source_overrides_require_explicit_policy(self, loader, kwargs):
        frame = self.frame(pd.date_range('2024-01-02 09:30', periods=5, freq='min'))
        with pytest.raises(ValueError, match='observed_v2'):
            loader.aggregate_to_timeframe(frame, '5m', **kwargs)
        with pytest.raises(ValueError, match='observed_v2'):
            loader.build_multi_timeframe(frame, ['5m'], **kwargs)

    def test_default_and_named_legacy_keep_literal_historical_bins(self, loader):
        frame = self.frame(['2024-01-02 09:30', '2024-01-02 09:31', '2024-01-02 10:00'])
        frame['Open'] = [100., 101., 102.]
        frame['High'] = [102., 103., 104.]
        frame['Low'] = [99., 100., 101.]
        frame['Close'] = [101., 102., 103.]
        expected = pd.DataFrame({
            'Open': [100., 102.], 'High': [103., 104.], 'Low': [99., 101.],
            'Close': [102., 103.], 'Volume': [20., 10.],
        }, index=pd.date_range('2024-01-02 09:00', periods=2, freq='h'))
        for kwargs in ({}, {'aggregation_policy': 'legacy_v1'}):
            actual = loader.aggregate_to_timeframe(frame, '1h', **kwargs)
            pd.testing.assert_frame_equal(actual, expected)
            assert actual.attrs == {'aggregation_policy': 'legacy_v1'}

    @pytest.mark.parametrize('daily', [False, True])
    @pytest.mark.parametrize('defect', ['missing', 'conflicting', 'none'])
    def test_actual_partition_loaders_reconcile_source_contracts(self, loader, tmp_path, daily, defect):
        frames = [self.frame([f'2024-01-0{day} 09:30'], daily=daily) for day in (2, 3)]
        if defect == 'missing':
            frames[1].attrs.pop('source_resolution')
        elif defect == 'conflicting':
            frames[1].attrs['source_resolution'] = '2min'
        directory = tmp_path / 'iwm' if daily else tmp_path / 'iwm' / 'intraday'
        directory.mkdir(parents=True)
        for number, frame in enumerate(frames):
            name = f'iwm_202{number}.parquet' if daily else f'iwm_av_1min_2024_0{number+1}.parquet'
            frame.to_parquet(directory/name)
        result = loader.load_daily('IWM') if daily else loader.load_intraday('IWM')
        assert len(result) == 2
        if defect == 'none':
            assert result.attrs['source_resolution'] == ('1d' if daily else '1min')
            assert 'source_contract_reasons' not in result.attrs
        else:
            assert result.attrs['source_resolution'] == 'unknown'
            reason = 'incomplete_source_contract' if defect == 'missing' else 'conflicting_source_contract'
            assert reason in result.attrs['source_contract_reasons']
            observed = self.observed(loader, result, '1d', '2024-01-03 16:00-05:00')
            assert not observed.attrs['coverage']['available']
            assert reason in observed.attrs['coverage']['reasons']

    @pytest.mark.parametrize('acquisitions,status', [
        ([None, None], 'unknown'), (['2024-01-04', None], 'incomplete'),
        (['2024-01-04', '2024-01-05'], 'mixed'),
        (['2024-01-04', '2024-01-04'], 'uniform'),
    ])
    def test_concat_preserves_acquisition_uncertainty(self, acquisitions, status):
        from lib.data_loader import _concat_source_frames
        frames = [self.frame([f'2024-01-0{day}'], daily=True) for day in (2, 3)]
        for frame, acquisition in zip(frames, acquisitions):
            frame.attrs['source_acquired_at'] = acquisition
        result = _concat_source_frames(frames)
        assert result.attrs['source_acquisition_status'] == status
        assert result.attrs['source_acquired_at'] == (acquisitions[0] if status == 'uniform' else None)
        assert frames[0].attrs['source_acquired_at'] == acquisitions[0]
