"""
Unified data loading with column normalization and multi-source priority.

Handles AlphaVantage parquet, Yahoo Finance daily parquet, and on-demand
Yahoo Finance fetching. Provides timeframe aggregation for Strat FTFC.

Cloud SQL mode
--------------
When CLOUD_SQL_CONNECTION_NAME is set (along with DB_USER, DB_PASS, DB_NAME),
load_intraday() and load_daily() query Cloud SQL first and fall back to local
Parquet files if the query returns no rows.  All call-site code is unchanged.
"""

import logging
import os
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Dict
import warnings
warnings.filterwarnings('ignore')

log = logging.getLogger(__name__)


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

# Resampling rules for pandas. Keys mirror methodology doc §4.
RESAMPLE_RULES = {
    '1m':  '1min',
    '5m':  '5min',
    '15m': '15min',
    '30m': '30min',
    '1h':  '1h',
    '4h':  '4h',
    '12h': '12h',
    '1d':  '1D',
    '1w':  'W-FRI',
    '1mo': 'ME',
    '1q':  'QE',
}


def _cloud_sql_active() -> bool:
    """Return True when all Cloud SQL env vars are present."""
    return bool(os.environ.get('CLOUD_SQL_CONNECTION_NAME'))


def _query_cloud_sql(sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    """Run a SELECT against Cloud SQL; returns empty DataFrame on any error.

    Track D / G.P1.1: log the full traceback before swallowing the
    exception so production silent failures (e.g. Cloud SQL Connector
    auth, transient connection issue, schema mismatch) surface in
    Cloud Logging. Pre-fix the bare `except Exception: return empty`
    silently returned no data, causing downstream callers like
    `SignalMonitor.refresh_level_map` to see `df.empty` and set
    `level_maps[ticker] = None`, which made `check_level_breaks`
    return [] on every bar — `signal_alerts.level_broken` was 0%
    populated for the entire 2026-05-04 → 2026-05-08 window despite
    fresh strat_levels data being available.
    """
    try:
        from gcp.database import query_to_dataframe
        return query_to_dataframe(sql, params)
    except Exception:
        log.exception(
            "_query_cloud_sql: query failed; returning empty DataFrame "
            "(callers must treat empty as a signal that the underlying "
            "DB query errored, not as a legitimate zero-row result)"
        )
        return pd.DataFrame()


def _check_staleness(df: pd.DataFrame, ticker: str, *,
                     max_age_days: int, on_stale: str,
                     date_col: Optional[str] = None,
                     value_col: Optional[str] = None,
                     today: Optional[date] = None) -> None:
    """Compare the most recent row's date against today; warn or raise
    if the gap exceeds `max_age_days`.

    `on_stale` values:
      'silent' — return without checking (back-compat default for legacy callers)
      'warn'   — log a WARNING with the gap; do not raise
      'error'  — raise RuntimeError

    `date_col`: when provided, use that column. When None, use the
    DataFrame's index (assumed to be a DatetimeIndex). Empty df is a
    no-op (an empty result is a different failure mode than a stale
    result; the caller decides how to handle empty).

    `value_col`: when provided, filter out rows where this column is
    NaN BEFORE computing the max date. This is what makes the staleness
    check honest in the presence of `fetch-premarket-refresh`'s
    pre-market placeholder rows (today's row has `pre_*` fields but
    `close` is NaN) — without the filter, MAX(date) returns today even
    when the latest USABLE OHLC bar is days old. Track A G.P0.3's
    freshness watchdog applies the same `close IS NOT NULL` filter at
    the SQL layer; this check applies it at the DataFrame layer.
    """
    if on_stale == 'silent':
        return
    if df is None or df.empty:
        return
    if today is None:
        today = date.today()

    # Filter out placeholder rows where the value column is NaN. The
    # check should reflect the most recent USABLE bar, not the most
    # recent row of any kind.
    if value_col is not None and value_col in df.columns:
        df = df[df[value_col].notna()]
        if df.empty:
            # Every row is a placeholder. Treat as stale at infinity
            # under 'error', as a "no usable rows" warning under 'warn'.
            msg = (f"data_loader: {ticker} has no rows with non-null "
                   f"{value_col} — every row is a placeholder.")
            if on_stale == 'error':
                raise RuntimeError(msg)
            log.warning(msg)
            return

    if date_col is not None and date_col in df.columns:
        last = df[date_col].max()
    else:
        try:
            last = df.index.max()
        except Exception:
            return

    if hasattr(last, 'date'):
        last_d = last.date()
    elif isinstance(last, date):
        last_d = last
    else:
        try:
            last_d = pd.to_datetime(last).date()
        except Exception:
            return

    gap_days = (today - last_d).days
    if gap_days <= max_age_days:
        return

    msg = (f"data_loader: {ticker} most recent row {last_d} is "
           f"{gap_days} days old (threshold: {max_age_days})")
    if on_stale == 'error':
        raise RuntimeError(msg)
    log.warning(msg)


class DataLoader:
    """Load market data from multiple sources with consistent column naming.

    When CLOUD_SQL_CONNECTION_NAME is set, queries Cloud SQL (PostgreSQL)
    for market_data_daily / market_data_intraday before falling back to
    local Parquet files.  New methods load_options() and load_trades()
    query the options/trades tables exclusively from Cloud SQL.
    """

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
        *,
        max_age_days: int = 2,
        on_stale: str = 'silent',
    ) -> pd.DataFrame:
        """Load intraday (1-minute) data for a ticker.

        Priority order:
        0. Cloud SQL market_data_intraday  (when CLOUD_SQL_CONNECTION_NAME is set)
        1. AlphaVantage combined parquet in intraday/
        2. Monthly AlphaVantage parquets in intraday/
        3. Daily minute parquets in minute/ (e.g. SPX format)
        4. Empty DataFrame if nothing found

        Staleness (Track A G.P1.17): if the most recent bar is older
        than `max_age_days` calendar days, `on_stale` controls behavior:
          'silent' — default, no check (legacy callers).
          'warn'   — log WARNING with the gap.
          'error'  — raise RuntimeError; caller refuses to proceed.
        Always called LAST so all paths (Cloud SQL + parquet) are
        covered by one check.
        """
        df_out: pd.DataFrame = pd.DataFrame()

        # Priority 0: Cloud SQL
        if _cloud_sql_active():
            df = self._load_intraday_from_sql(ticker, start_date, end_date)
            if not df.empty:
                df_out = df

        if df_out.empty:
            ticker_lower = ticker.lower()
            intraday_dir = self.data_dir / ticker_lower / 'intraday'

            # Priority 1: combined parquet
            combined = intraday_dir / f'{ticker_lower}_av_1min_combined.parquet'
            if combined.exists():
                df = pd.read_parquet(combined)
                df = self.normalize_columns(df)
                df = self._strip_timezone(df)
                df = self._filter_dates(df, start_date, end_date)
                df_out = df.sort_index()
            else:
                # Priority 2: monthly parquets
                monthly_files = sorted(intraday_dir.glob(f'{ticker_lower}_av_1min_*.parquet'))
                if monthly_files:
                    frames = [pd.read_parquet(f) for f in monthly_files]
                    df = pd.concat(frames).sort_index()
                    df = self.normalize_columns(df)
                    df = self._strip_timezone(df)
                    df_out = self._filter_dates(df, start_date, end_date)
                else:
                    # Priority 3: daily minute parquets (e.g. data/spx/minute/spx_minute_YYYYMMDD.parquet)
                    minute_dir = self.data_dir / ticker_lower / 'minute'
                    daily_files = sorted(minute_dir.glob(f'{ticker_lower}_minute_*.parquet'))
                    if daily_files:
                        frames = [pd.read_parquet(f) for f in daily_files]
                        df = pd.concat(frames).sort_index()
                        df = self.normalize_columns(df)
                        df = self._strip_timezone(df)
                        df_out = self._filter_dates(df, start_date, end_date)

        # value_col='Close' filters out NULL-close placeholder rows
        # (e.g. fetch-premarket-refresh writes today's row with pre_*
        # fields but no close). Without this, the staleness check
        # silently passes when the latest USABLE bar is days old.
        _check_staleness(df_out, ticker,
                         max_age_days=max_age_days, on_stale=on_stale,
                         value_col='Close')
        return df_out

    def _load_intraday_from_sql(
        self,
        ticker: str,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> pd.DataFrame:
        """Query market_data_intraday from Cloud SQL and normalize to local format."""
        params: dict = {'ticker': ticker.upper(), 'interval': '1min'}
        where = "WHERE ticker = :ticker AND interval = :interval"
        if start_date:
            where += " AND ts >= :start"
            params['start'] = start_date
        if end_date:
            where += " AND ts <= :end"
            params['end'] = end_date

        sql = f"""
            SELECT ts, open AS "Open", high AS "High", low AS "Low",
                   close AS "Close", volume AS "Volume"
            FROM market_data_intraday
            {where}
            ORDER BY ts
        """
        df = _query_cloud_sql(sql, params)
        if df.empty:
            return df

        df['ts'] = pd.to_datetime(df['ts'], utc=True).dt.tz_localize(None)
        df = df.set_index('ts')
        df.index.name = 'Time'
        df['Time'] = df.index
        return df

    def load_daily(
        self,
        ticker: str,
        year: Optional[int] = None,
        *,
        max_age_days: int = 2,
        on_stale: str = 'silent',
    ) -> pd.DataFrame:
        """Load daily OHLCV + indicators for a ticker.

        Tries Cloud SQL first (when configured), then local yearly Parquet files.

        Staleness (Track A G.P1.17): if the most recent row is older
        than `max_age_days` calendar days, `on_stale` controls behavior:
          'silent' — default, no check (legacy callers).
          'warn'   — log WARNING with the gap.
          'error'  — raise RuntimeError; caller refuses to proceed.

        Year-scoped queries (year != None) skip the staleness check
        because the caller is intentionally requesting historical data.
        """
        df_out: pd.DataFrame = pd.DataFrame()

        # Cloud SQL path
        if _cloud_sql_active():
            df = self._load_daily_from_sql(ticker, year)
            if not df.empty:
                df_out = df

        if df_out.empty:
            ticker_lower = ticker.lower()
            ticker_dir = self.data_dir / ticker_lower

            if year:
                parquet_file = ticker_dir / f'{ticker_lower}_{year}.parquet'
                if parquet_file.exists():
                    df = pd.read_parquet(parquet_file)
                    df_out = self.normalize_columns(df).sort_index()
            else:
                # Load all years
                files = sorted(ticker_dir.glob(f'{ticker_lower}_*.parquet'))
                if files:
                    frames = [pd.read_parquet(f) for f in files]
                    df = pd.concat(frames).sort_index()
                    df_out = self.normalize_columns(df)

        # Skip staleness when caller asked for a specific year (historical query).
        if year is None:
            # value_col='Close' filters out NULL-close placeholders
            # (Track A G.P0.3 / G.P1.17 — fetch-premarket-refresh
            # writes pre_* fields with no close on today's row).
            _check_staleness(df_out, ticker,
                             max_age_days=max_age_days, on_stale=on_stale,
                             value_col='Close')
        return df_out

    def _load_daily_from_sql(
        self,
        ticker: str,
        year: Optional[int],
    ) -> pd.DataFrame:
        """Query market_data_daily from Cloud SQL."""
        params: dict = {'ticker': ticker.upper()}
        where = "WHERE ticker = :ticker"
        if year:
            where += " AND EXTRACT(year FROM date) = :year"
            params['year'] = year

        sql = f"""
            SELECT date, open AS "Open", high AS "High", low AS "Low",
                   close AS "Close", adjusted_close, volume AS "Volume",
                   rsi_14, rsi_9,
                   ema_9, ema_20, ema_50,
                   ma_5, ma_10, ma_20, ma_50, sma_200,
                   atr_14, atr_20,
                   macd, macd_signal, macd_histogram,
                   bb_upper, bb_lower, bb_width, bb_pct,
                   stoch_rsi_k AS "StochRSI_K", stoch_rsi_d AS "StochRSI_D",
                   obv, rvol, volatility_20d,
                   consecutive_up AS "Consecutive_Up",
                   consecutive_down AS "Consecutive_Down",
                   vwap, price_vs_vwap AS "Price_vs_VWAP",
                   price_vs_ema9, price_vs_ema20,
                   strat_candle, strat_combo, strat_setup,
                   ftfc_score, ftfc_direction,
                   pre_high, pre_low, pre_vwap, pre_volume,
                   gap_pct, pre_range_atr
            FROM market_data_daily
            {where}
            ORDER BY date
        """
        df = _query_cloud_sql(sql, params)
        if df.empty:
            return df

        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        df.index.name = 'Time'
        df['Time'] = df.index

        # Map lowercase SQL cols back to the canonical names callers expect
        rename = {
            'rsi_14': 'RSI14', 'rsi_9': 'RSI9',
            'ema_9': 'EMA9', 'ema_20': 'EMA20', 'ema_50': 'EMA50',
            'ma_5': 'SMA5', 'ma_10': 'SMA10', 'ma_20': 'SMA20',
            'ma_50': 'SMA50', 'sma_200': 'SMA200',
            'atr_14': 'ATR14', 'atr_20': 'ATR20',
            'macd': 'MACD', 'macd_signal': 'MACD_Signal',
            'macd_histogram': 'MACD_Histogram',
            'bb_upper': 'BB_Upper', 'bb_lower': 'BB_Lower',
            'bb_width': 'BB_Width', 'bb_pct': 'BB_Pct',
            'obv': 'OBV', 'rvol': 'RVOL', 'vwap': 'VWAP',
            'price_vs_ema9': 'Price_vs_EMA9',
            'price_vs_ema20': 'Price_vs_EMA20',
        }
        return df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

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
        timeframe : one of '5m', '15m', '30m', '1h', '4h', '12h', '1d', '1w', '1mo'
                    (legacy 'D' / 'W' / 'M' keys removed in PR #126)
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
            timeframes = ['5m', '15m', '1h', '4h', '12h', '1d', '1w']

        result = {}
        for tf in timeframes:
            try:
                result[tf] = self.aggregate_to_timeframe(df, tf)
            except Exception:
                continue
        return result

    def load_options(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        option_type: Optional[str] = None,
        source: str = 'etf',
        data_source: Optional[str] = None,
    ) -> pd.DataFrame:
        """Load options snapshots from Cloud SQL.

        Parameters
        ----------
        source : 'etf' (etf_options_snapshots) or 'earnings' (earnings_options_snapshots)
        option_type : 'calls', 'puts', or None for both
        data_source : 'alphavantage' (EOD, real Greeks), 'yahooquery' (intraday, B-S Greeks),
                      or None for all sources
        """
        if not _cloud_sql_active():
            return pd.DataFrame()

        table = 'etf_options_snapshots' if source == 'etf' else 'earnings_options_snapshots'
        ticker_col = 'ticker' if source == 'etf' else 'symbol'

        params: dict = {'ticker': ticker.upper()}
        where = f"WHERE {ticker_col} = :ticker"
        if start_date:
            where += " AND snapshot_date >= :start"
            params['start'] = start_date
        if end_date:
            where += " AND snapshot_date <= :end"
            params['end'] = end_date
        if option_type:
            where += " AND option_type = :opt"
            params['opt'] = option_type
        if data_source:
            where += " AND data_source = :data_source"
            params['data_source'] = data_source

        sql = f"SELECT * FROM {table} {where} ORDER BY snapshot_ts, expiration, strike"
        return _query_cloud_sql(sql, params)

    def get_close_price(
        self,
        ticker: str,
        target_date,
    ) -> Optional[float]:
        """Return the close price for ``ticker`` on ``target_date`` from Cloud SQL.

        Single-row lookup against ``market_data_daily`` (uses the
        ``(ticker, date)`` unique index, so it's O(1)). Returns ``None`` if
        no row exists or Cloud SQL is unavailable. The caller decides whether
        to fall back to put-call parity / proxy spot.

        ``target_date`` may be a ``datetime.date``, ``datetime.datetime``, or
        ``YYYY-MM-DD`` string.
        """
        if not _cloud_sql_active():
            return None
        if hasattr(target_date, "strftime"):
            d_str = target_date.strftime("%Y-%m-%d")
        else:
            d_str = str(target_date)
        df = _query_cloud_sql(
            "SELECT close FROM market_data_daily "
            "WHERE ticker = :t AND date = :d LIMIT 1",
            {"t": ticker.upper(), "d": d_str},
        )
        if df.empty:
            return None
        val = df.iloc[0]["close"]
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        return float(val)

    def load_trades(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        ticker: Optional[str] = None,
    ) -> pd.DataFrame:
        """Load logged trades from Cloud SQL trades table."""
        if not _cloud_sql_active():
            return pd.DataFrame()

        params: dict = {}
        conditions = []
        if ticker:
            conditions.append("ticker = :ticker")
            params['ticker'] = ticker.upper()
        if start_date:
            conditions.append("trade_date >= :start")
            params['start'] = start_date
        if end_date:
            conditions.append("trade_date <= :end")
            params['end'] = end_date

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"SELECT * FROM trades {where} ORDER BY entry_time"
        return _query_cloud_sql(sql, params)

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


# Module-level convenience wrapper. Single shared DataLoader instance so
# repeated calls don't recreate the data_dir Path. Used by lib.options_greeks.
_DEFAULT_LOADER: Optional[DataLoader] = None


def get_close_price(ticker: str, target_date) -> Optional[float]:
    """Module-level shortcut for ``DataLoader().get_close_price(ticker, date)``.

    Returns ``None`` when Cloud SQL is unreachable or the row doesn't exist.
    """
    global _DEFAULT_LOADER
    if _DEFAULT_LOADER is None:
        _DEFAULT_LOADER = DataLoader()
    return _DEFAULT_LOADER.get_close_price(ticker, target_date)
