"""
Unified data loading with column normalization and multi-source priority.

Handles AlphaVantage parquet, Yahoo Finance daily parquet, and on-demand
Yahoo Finance fetching. Provides timeframe aggregation for Strat FTFC.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Dict
import warnings
warnings.filterwarnings('ignore')


# Canonical column mapping: normalize any source to these names
COLUMN_MAP = {
    'Last': 'Close',
    'last': 'Close',
    'Adj Close': 'Close',
    'adj_close': 'Close',
    'open': 'Open',
    'high': 'High',
    'low': 'Low',
    'close': 'Close',
    'volume': 'Volume',
    'timestamp': 'Time',
}

REQUIRED_COLUMNS = ['Open', 'High', 'Low', 'Close', 'Volume']

# Resampling rules for pandas
RESAMPLE_RULES = {
    '1m': '1min',
    '5m': '5min',
    '15m': '15min',
    '30m': '30min',
    '1h': '1h',
    'D': '1D',
    'W': 'W-FRI',
    'M': 'ME',
}


class DataLoader:
    """Load market data from multiple sources with consistent column naming."""

    def __init__(self, data_dir: str = 'data'):
        self.data_dir = Path(data_dir)

    def normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rename columns to canonical names and ensure required columns exist."""
        df = df.copy()

        # Handle MultiIndex columns (yfinance sometimes returns these)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(-1)

        # Apply column mapping
        rename = {}
        for col in df.columns:
            if col in COLUMN_MAP:
                rename[col] = COLUMN_MAP[col]
        if rename:
            df = df.rename(columns=rename)

        # Ensure Time column exists
        if 'Time' not in df.columns and isinstance(df.index, pd.DatetimeIndex):
            df['Time'] = df.index

        # Ensure datetime index
        if 'Time' in df.columns and not isinstance(df.index, pd.DatetimeIndex):
            df['Time'] = pd.to_datetime(df['Time'])
            df = df.set_index('Time', drop=False)

        return df

    def load_intraday(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Load intraday (1-minute) data for a ticker.

        Priority order:
        1. AlphaVantage combined parquet in intraday/
        2. Monthly AlphaVantage parquets in intraday/
        3. Daily minute parquets in minute/ (e.g. SPX format)
        4. Empty DataFrame if nothing found
        """
        ticker_lower = ticker.lower()
        intraday_dir = self.data_dir / ticker_lower / 'intraday'

        # Priority 1: combined parquet
        combined = intraday_dir / f'{ticker_lower}_av_1min_combined.parquet'
        if combined.exists():
            df = pd.read_parquet(combined)
            df = self.normalize_columns(df)
            df = self._strip_timezone(df)
            df = self._filter_dates(df, start_date, end_date)
            return df.sort_index()

        # Priority 2: monthly parquets
        monthly_files = sorted(intraday_dir.glob(f'{ticker_lower}_av_1min_*.parquet'))
        if monthly_files:
            frames = [pd.read_parquet(f) for f in monthly_files]
            df = pd.concat(frames).sort_index()
            df = self.normalize_columns(df)
            df = self._strip_timezone(df)
            df = self._filter_dates(df, start_date, end_date)
            return df

        # Priority 3: daily minute parquets (e.g. data/spx/minute/spx_minute_YYYYMMDD.parquet)
        minute_dir = self.data_dir / ticker_lower / 'minute'
        daily_files = sorted(minute_dir.glob(f'{ticker_lower}_minute_*.parquet'))
        if daily_files:
            frames = [pd.read_parquet(f) for f in daily_files]
            df = pd.concat(frames).sort_index()
            df = self.normalize_columns(df)
            df = self._strip_timezone(df)
            df = self._filter_dates(df, start_date, end_date)
            return df

        return pd.DataFrame()

    def load_daily(
        self,
        ticker: str,
        year: Optional[int] = None,
    ) -> pd.DataFrame:
        """Load daily data for a ticker from yearly parquet files."""
        ticker_lower = ticker.lower()
        ticker_dir = self.data_dir / ticker_lower

        if year:
            parquet_file = ticker_dir / f'{ticker_lower}_{year}.parquet'
            if parquet_file.exists():
                df = pd.read_parquet(parquet_file)
                return self.normalize_columns(df).sort_index()
            return pd.DataFrame()

        # Load all years
        files = sorted(ticker_dir.glob(f'{ticker_lower}_*.parquet'))
        if not files:
            return pd.DataFrame()

        frames = [pd.read_parquet(f) for f in files]
        df = pd.concat(frames).sort_index()
        return self.normalize_columns(df)

    def load_summary(self, ticker: str) -> dict:
        """Load the latest summary JSON for a ticker."""
        import json
        ticker_lower = ticker.lower()
        summary_path = self.data_dir / ticker_lower / f'{ticker_lower}_summary.json'
        if summary_path.exists():
            with open(summary_path) as f:
                return json.load(f)
        return {}

    def load_best_available(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        prefer_intraday: bool = True,
    ) -> pd.DataFrame:
        """Load the best available data for a ticker.

        Tries intraday first (if preferred), then daily.
        """
        if prefer_intraday:
            df = self.load_intraday(ticker, start_date, end_date)
            if not df.empty:
                return df

        df = self.load_daily(ticker)
        if not df.empty:
            df = self._filter_dates(df, start_date, end_date)
            return df

        return pd.DataFrame()

    def aggregate_to_timeframe(
        self,
        df: pd.DataFrame,
        timeframe: str,
    ) -> pd.DataFrame:
        """Resample OHLCV data to a higher timeframe.

        Parameters
        ----------
        timeframe : one of '5m', '15m', '30m', '1h', 'D', 'W', 'M'
        """
        rule = RESAMPLE_RULES.get(timeframe)
        if rule is None:
            raise ValueError(f"Unknown timeframe: {timeframe}. Use one of {list(RESAMPLE_RULES.keys())}")

        close_col = 'Close' if 'Close' in df.columns else 'Last'

        resampled = df.resample(rule).agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            close_col: 'last',
            'Volume': 'sum',
        }).dropna()

        # Normalize close column name
        if close_col != 'Close':
            resampled = resampled.rename(columns={close_col: 'Close'})

        return resampled

    def build_multi_timeframe(
        self,
        df: pd.DataFrame,
        timeframes: list = None,
    ) -> Dict[str, pd.DataFrame]:
        """Build a dict of DataFrames at multiple timeframes from minute data.

        Used for Strat FTFC calculation.
        """
        if timeframes is None:
            timeframes = ['5m', '15m', '1h', 'D', 'W']

        result = {}
        for tf in timeframes:
            try:
                result[tf] = self.aggregate_to_timeframe(df, tf)
            except Exception:
                continue
        return result

    def _strip_timezone(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove timezone info from index for consistent handling across sources."""
        if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
            df = df.copy()
            df.index = df.index.tz_localize(None)
            if 'Time' in df.columns:
                df['Time'] = df['Time'].dt.tz_localize(None)
        return df

    def _filter_dates(
        self,
        df: pd.DataFrame,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> pd.DataFrame:
        """Filter DataFrame by date range."""
        if start_date:
            start = pd.to_datetime(start_date)
            df = df[df.index >= start]
        if end_date:
            end = pd.to_datetime(end_date)
            df = df[df.index <= end]
        return df
