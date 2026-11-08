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

from lib.eastern_time import (ET_NAME, eastern_index_to_utc, stored_intraday_to_eastern,
                              session_schedule, eastern_now)


def _eastern_bound(value) -> Optional[pd.Timestamp]:
    """A caller's bound as naive Eastern wall clock (None passes through).
    An aware value is an instant and is converted, never relabelled."""
    if value is None or value == '':
        return None
    t = pd.Timestamp(value)
    if t.tzinfo is not None:
        t = t.tz_convert(ET_NAME).tz_localize(None)  # tz-ok: converted to Eastern first
    return t
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
    '1y':  'YE',
}


def _apply_contract_defaults(attrs, defaults):
    """Loader compatibility defaults for a wholly unannotated source contract.

    A partially declared contract keeps each missing field ``unknown`` with an
    explicit reason, on single-file loads exactly as `_concat_source_frames`
    does for multi-file ones; nothing is invented (Rule 3.7).
    """
    if not any(key in attrs for key in defaults):
        attrs.update(defaults)
        return
    missing = [key for key in defaults if key not in attrs]
    for key in missing:
        attrs[key] = 'unknown'
    if missing:
        attrs['source_contract_reasons'] = list(dict.fromkeys(
            list(attrs.get('source_contract_reasons', [])) + ['incomplete_source_contract']))


def _concat_source_frames(frames):
    """Reconcile partition declarations before pandas can discard unequal attrs.

    Only wholly unannotated contracts qualify for loader compatibility defaults.
    A missing/conflicting field in any annotated set stays unknown. Acquisition
    time describes the whole result only when every component declares the same
    value; otherwise its missingness is explicit, never a latest-file timestamp.
    Other arbitrary per-file attrs are not a contract for the combined source.
    """
    contract_keys = ('source_resolution', 'session_policy', 'timestamp_semantics')
    declarations = [frame.attrs for frame in frames]
    attrs = {}
    reasons = [reason for declaration in declarations
               for reason in declaration.get('source_contract_reasons', [])]
    if any(key in declaration for declaration in declarations for key in contract_keys):
        for key in contract_keys:
            values = [declaration[key] for declaration in declarations if key in declaration]
            missing = len(values) != len(declarations)
            conflicting = any(value != values[0] for value in values[1:])
            attrs[key] = 'unknown' if missing or conflicting else values[0]
            if missing:
                reasons.append('incomplete_source_contract')
            if conflicting:
                reasons.append('conflicting_source_contract')
    if reasons:
        attrs['source_contract_reasons'] = list(dict.fromkeys(reasons))

    acquisitions = [declaration.get('source_acquired_at') for declaration in declarations]
    present = [value for value in acquisitions if value not in (None, '', 'unknown')]
    if not present:
        acquisition_status = 'unknown'
    elif len(present) != len(acquisitions):
        acquisition_status = 'incomplete'
    elif any(value != present[0] for value in present[1:]):
        acquisition_status = 'mixed'
    else:
        acquisition_status = 'uniform'
    attrs['source_acquired_at'] = present[0] if acquisition_status == 'uniform' else None
    attrs['source_acquisition_status'] = acquisition_status
    adjustments = [declaration.get('price_adjustment', 'unknown') for declaration in declarations]
    attrs['price_adjustment'] = (adjustments[0] if all(value == adjustments[0]
                                for value in adjustments) else 'unknown')

    # Clear attrs on shallow copies so concat never compares unrelated metadata
    # (nor retains whichever input happened to sort first).
    parts = [frame.copy(deep=False) for frame in frames]
    for part in parts:
        part.attrs = {}
    result = pd.concat(parts)
    result.attrs = attrs
    return result


def _cloud_sql_active() -> bool:
    """Return True when all Cloud SQL env vars are present."""
    return bool(os.environ.get('CLOUD_SQL_CONNECTION_NAME'))


# None until a daily query shows whether market_data_daily has the
# premarket provenance columns; see DataLoader._load_daily_from_sql.
_PREMARKET_PROVENANCE_PRESENT: Optional[bool] = None
_PROVENANCE_SELECT = (",\n                   pre_fetched_at, pre_excluded_stale_prints, "
                      "pre_excluded_spikes")


def _query_cloud_sql(sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    """Run a SELECT against Cloud SQL; log then return an empty DataFrame on error.

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
        # The STRICT helper, so a real failure raises HERE and the log below
        # sees the traceback, rather than `query_to_dataframe` swallowing it to
        # an empty frame one layer down. The result is still logged-then-empty
        # on EVERY error, an outage included: this wrapper backs
        # `load_intraday`, `load_daily`, `get_close_price`, `load_trades` and
        # the options-chain read, each of which answers empty / None / a local
        # Parquet fallback for an unreachable Cloud SQL, and re-raising an
        # outage here broke every one of those contracts for the jobs and API
        # consumers that never needed to distinguish it (Codex P2 on #999). A
        # caller that DOES need to tell an outage from a gap -- the
        # movement/prediction path -- reads `query_to_dataframe_strict`
        # directly (see `lib/movement_statement._strict_query`), so nothing
        # depends on this shared wrapper raising.
        from gcp.database import query_to_dataframe_strict
        return query_to_dataframe_strict(sql, params)
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

        The index (and ``Time`` column) is naive Eastern wall clock from every
        source. A caller that needs instants converts with
        ``lib.eastern_time.eastern_index_to_utc``.

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
                    df = _concat_source_frames(frames).sort_index()
                    df = self.normalize_columns(df)
                    df = self._strip_timezone(df)
                    df_out = self._filter_dates(df, start_date, end_date)
                else:
                    # Priority 3: daily minute parquets (e.g. data/spx/minute/spx_minute_YYYYMMDD.parquet)
                    minute_dir = self.data_dir / ticker_lower / 'minute'
                    daily_files = sorted(minute_dir.glob(f'{ticker_lower}_minute_*.parquet'))
                    if daily_files:
                        frames = [pd.read_parquet(f) for f in daily_files]
                        df = _concat_source_frames(frames).sort_index()
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
        _apply_contract_defaults(df_out.attrs, {'source_resolution': '1min',
                                                'timestamp_semantics': 'bar_start',
                                                'session_policy': 'unknown'})
        return df_out

    def _load_intraday_from_sql(
        self,
        ticker: str,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> pd.DataFrame:
        """Query market_data_intraday from Cloud SQL and normalize to local format.

        ``start_date`` / ``end_date`` are Eastern wall-clock bounds (a bare date
        is its Eastern midnight), inclusive, like the index this returns. A bar
        at Eastern time t is stored at raw t (legacy label) or at t's UTC
        instant (true UTC), which is never earlier; so the raw window runs from
        ``start`` read as a label to ``end`` converted as an instant, and the
        converted index is cut back to the bounds. Binding the Eastern strings
        straight to TIMESTAMPTZ read them as UTC: an EST request for D pulled in
        D-1's 19:00-20:00 ET spill and lost D's own (Codex P2 on #1185).
        """
        params: dict = {'ticker': ticker.upper(), 'interval': '1min'}
        where = "WHERE ticker = :ticker AND interval = :interval"
        lo = _eastern_bound(start_date)
        hi = _eastern_bound(end_date)
        if lo is not None:
            where += " AND ts >= :start"
            params['start'] = lo.tz_localize('UTC')  # the raw label reading, the earlier one
        if hi is not None:
            where += " AND ts <= :end"
            params['end'] = eastern_index_to_utc(pd.DatetimeIndex([hi]))[0]

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

        # Naive Eastern wall clock, the same contract as the parquet paths
        # below and what every consumer's RTH / session grouping assumes
        # (indicator_correlation_job, regime_combo_job, add_all_indicators'
        # VWAP/ORB). Each row is read by its own stored convention, so this is
        # right both before and after the re-framing migration. Stripping the
        # zone instead handed true-UTC rows out as naive UTC: a 09:30 ET bar
        # read as 13:30 and 'RTH' became 05:30-12:00 ET (Codex P1 on #1185).
        idx, keep = stored_intraday_to_eastern(df['ts'], df['Volume'])
        if lo is not None:
            keep &= (idx >= lo)
        if hi is not None:
            keep &= (idx <= hi)
        df = df.loc[keep].drop(columns='ts')
        df.index = idx[keep]
        df = df.sort_index()
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
                    df = _concat_source_frames(frames).sort_index()
                    df_out = self.normalize_columns(df)

        # Skip staleness when caller asked for a specific year (historical query).
        if year is None:
            # value_col='Close' filters out NULL-close placeholders
            # (Track A G.P0.3 / G.P1.17 — fetch-premarket-refresh
            # writes pre_* fields with no close on today's row).
            _check_staleness(df_out, ticker,
                             max_age_days=max_age_days, on_stale=on_stale,
                             value_col='Close')
        _apply_contract_defaults(df_out.attrs, {'source_resolution': '1d',
                                                'session_policy': 'NYSE_regular',
                                                'timestamp_semantics': 'session_label'})
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
                   atr_14, atr_5, atr_20,
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
                   gap_pct, pre_range_atr{{provenance}}
            FROM market_data_daily
            {where}
            ORDER BY date
        """
        # The premarket provenance columns (FEAT-STRAT-001: fetch time and
        # excluded-print counts) are read when the table has them. A query
        # that fails or comes back empty with them is retried without them,
        # and once that retry finds rows they are not asked for again.
        global _PREMARKET_PROVENANCE_PRESENT
        df = pd.DataFrame()
        if _PREMARKET_PROVENANCE_PRESENT is not False:
            df = _query_cloud_sql(sql.format(provenance=_PROVENANCE_SELECT), params)
            if not df.empty:
                _PREMARKET_PROVENANCE_PRESENT = True
        if df.empty and _PREMARKET_PROVENANCE_PRESENT is not True:
            df = _query_cloud_sql(sql.format(provenance=''), params)
            if not df.empty:
                _PREMARKET_PROVENANCE_PRESENT = False
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
            'atr_14': 'ATR14', 'atr_5': 'ATR5', 'atr_20': 'ATR20',
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
        *,
        observation_ts=None,
        source_resolution: Optional[str] = None,
        session_policy: Optional[str] = None,
        aggregation_policy: str = 'legacy_v1',
    ) -> pd.DataFrame:
        """Aggregate under an explicit, inspectable compatibility policy.

        ``legacy_v1`` (default) retains historical pandas bins, raw OHLC
        aggregation and no observation-clock filtering for existing numerical
        consumers. Source attrs never opt these consumers into a new policy.
        Its output declares only the legacy version, not strict coverage.
        ``observed_v2`` opts into the exchange/source contract below. Clock or
        source override keywords require that explicit policy.

        ``observation_ts`` is an instant (naive means declared Eastern wall time).
        Daily indexes are session labels, including UTC-midnight vendor labels.
        Intraday indexes are bar-start instants; naive indexes mean Eastern.
        Only completed source bars are admitted at the observation clock. The
        resulting higher-period bar may still be partial.

        attrs['coverage'] describes the period containing the observation clock;
        attrs['period_coverage'] maps canonical UTC instant keys (intraday) or
        session-label keys (D/W/M/Q/Y) to each historical period record.
        ``partial`` describes time, while
        ``coverage_complete`` describes expected observations through the clock.
        ``open`` is available only when the actual period opening observation is
        valid. ``source_cutoff`` is the last source bar's availability instant,
        never the (possibly future) resample label or an acquisition timestamp.
        Unknown acquisition time and price adjustment remain explicitly unknown.
        attrs['gap_before_by_timestamp'] supplies session-aware adjacency to Strat.
        """
        rule = RESAMPLE_RULES.get(timeframe)
        if rule is None:
            raise ValueError(f"Unknown timeframe: {timeframe}. Use one of {list(RESAMPLE_RULES.keys())}")
        if aggregation_policy == 'legacy_v1':
            if any(value is not None for value in (observation_ts, source_resolution, session_policy)):
                raise ValueError('clock/source overrides require aggregation_policy=observed_v2')
            close_col = 'Close' if 'Close' in df.columns else 'Last'
            result = df.resample(rule).agg({
                'Open': 'first', 'High': 'max', 'Low': 'min',
                close_col: 'last', 'Volume': 'sum',
            }).dropna()
            if close_col != 'Close':
                result = result.rename(columns={close_col: 'Close'})
            # Source cadence/coverage cannot describe a different output grid.
            result.attrs = {'aggregation_policy': 'legacy_v1'}
            return result
        if aggregation_policy != 'observed_v2':
            raise ValueError(f'Unknown aggregation_policy: {aggregation_policy}')
        return _aggregate_observed_frame(df, timeframe, observation_ts,
                                         source_resolution, session_policy)

    def build_multi_timeframe(
        self,
        df: pd.DataFrame,
        timeframes: list = None,
        *,
        observation_ts=None,
        source_resolution: Optional[str] = None,
        session_policy: Optional[str] = None,
        aggregation_policy: str = 'legacy_v1',
    ) -> Dict[str, pd.DataFrame]:
        """Build frames under one explicit policy (one clock for observed_v2)."""
        if timeframes is None:
            timeframes = ['5m', '15m', '1h', '4h', '12h', '1d', '1w']
        # Resolve once, so live frames cannot straddle different decisions.
        clock = (_observation_clock(observation_ts)
                 if aggregation_policy == 'observed_v2' else observation_ts)
        return {tf: self.aggregate_to_timeframe(
            df, tf, observation_ts=clock, source_resolution=source_resolution,
            session_policy=session_policy, aggregation_policy=aggregation_policy) for tf in timeframes}

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
        run_kind: Optional[str] = 'live',
    ) -> pd.DataFrame:
        """Load logged trades from Cloud SQL trades table.

        ``run_kind`` defaults to ``'live'`` so analysis never counts replay
        or backfill rows as production trades (trades.run_kind, #820: 412
        simulated rows from a deleted backfill script sat unmarked in the
        table). Pass ``None`` to read every kind.
        """
        # AUDIT-2026-05-13: silent fallback — with no Cloud SQL configured
        # (local dev) this returns an empty frame the caller cannot tell from
        # "no trades"; the trades table has no other source, so there is no
        # cross-source fallback here (§3.7.1), only the unconfigured case.
        if not _cloud_sql_active():
            return pd.DataFrame()

        params: dict = {}
        conditions = []
        if run_kind is not None:
            conditions.append("run_kind = :run_kind")
            params['run_kind'] = run_kind
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


_PERIOD_FREQ = {'1d': 'D', '1w': 'W-FRI', '1mo': 'M', '1q': 'Q', '1y': 'Y'}


def _observation_clock(value=None):
    """Resolve an instant, with naive timestamps explicitly interpreted as Eastern."""
    clock = pd.Timestamp(eastern_now() if value is None else value)
    if clock.tzinfo is None:
        clock = clock.tz_localize(ET_NAME, ambiguous='raise', nonexistent='raise')
    return clock.tz_convert(ET_NAME)


def _session_labels(index):
    """Daily indexes are labels: remove zone without converting their date."""
    index = pd.DatetimeIndex(index)
    if index.tz is not None:
        index = index.tz_localize(None)  # tz-ok: session labels, not instants
    return index.normalize()


def _period_schedule(stamp, timeframe):
    day = pd.Timestamp(stamp)
    if day.tzinfo is not None:
        day = day.tz_convert(ET_NAME).tz_localize(None)  # tz-ok: converted to Eastern first; a session label
    period = day.to_period(_PERIOD_FREQ.get(timeframe, 'D'))
    return session_schedule(period.start_time.date(), period.end_time.date())


def _intraday_grid(schedule, interval):
    pieces = [pd.date_range(row.market_open, row.market_close, freq=interval,
                            inclusive='left').tz_convert(ET_NAME)
              for row in schedule.itertuples()]
    if not pieces:
        return pd.DatetimeIndex([], tz=ET_NAME)
    result = pieces[0]
    for piece in pieces[1:]:
        result = result.append(piece)
    return result


def _aggregate_observed_frame(df, timeframe, observation_ts, source_resolution, session_policy):
    from lib.strat import validate_ohlc_rows

    clock = _observation_clock(observation_ts)
    data = df.copy()
    if not isinstance(data.index, pd.DatetimeIndex):
        if data.empty:
            data.index = pd.DatetimeIndex([])
        else:
            raise ValueError('timeframe aggregation requires a DatetimeIndex')
    naive_source = data.index.tz is None
    data = data.sort_index()
    if data.index.has_duplicates:
        raise ValueError('duplicate observation timestamps')
    resolution = source_resolution if source_resolution is not None else data.attrs.get('source_resolution')
    daily = resolution in ('1d', '1D', 'daily')
    policy = session_policy if session_policy is not None else data.attrs.get('session_policy', 'unknown')
    target_interval = None if timeframe in _PERIOD_FREQ else pd.Timedelta(RESAMPLE_RULES[timeframe])
    base_reasons = list(data.attrs.get('source_contract_reasons', []))
    source_interval = None
    if resolution in (None, '', 'unknown'):
        base_reasons.append('unknown_source_resolution')
    elif not daily:
        try:
            source_interval = pd.Timedelta(resolution)
        except (ValueError, TypeError):
            base_reasons.append('unsupported_source_resolution')
        if source_interval is not None and (pd.isna(source_interval) or
                source_interval <= pd.Timedelta(0) or source_interval >= pd.Timedelta(days=1)):
            source_interval = None
            base_reasons.append('unsupported_source_resolution')
    if policy != 'NYSE_regular':
        base_reasons.append('unknown_session_policy')
    semantics = data.attrs.get('timestamp_semantics', 'unknown')
    if semantics != ('session_label' if daily else 'bar_start'):
        base_reasons.append('unsupported_timestamp_semantics')
    if ((daily and target_interval is not None) or
            (target_interval is not None and source_interval is not None and
             (source_interval > target_interval or target_interval % source_interval != pd.Timedelta(0)))):
        base_reasons.append('source_resolution_too_coarse')
    known_intraday = not daily and source_interval is not None and not base_reasons
    # Every declaration this function reads is read above (acquisition fields
    # come from ``df``). Dropping the working copy's attrs keeps pandas from
    # deep-copying them on each per-period slice below; the result's attrs are
    # rebuilt explicitly at the end.
    data.attrs = {}
    # Unknown duration/policy is not permission to treat a bar start as a
    # completed observation. No OHLC or completion timestamp can be admitted.
    if base_reasons:
        data = data.iloc[:0]

    if daily:
        data.index = _session_labels(data.index)
        schedule = (session_schedule(data.index.min().date(), data.index.max().date())
                    if len(data) else _period_schedule(clock, timeframe))
        cutoff_by_index = schedule['market_close'].reindex(data.index)
        eligible = cutoff_by_index.notna() & (cutoff_by_index <= clock)
        data = data.loc[eligible.to_numpy()]
        cutoffs = cutoff_by_index.loc[eligible].dt.tz_convert(ET_NAME)
    else:
        data.index = (data.index.tz_localize(ET_NAME, ambiguous='raise', nonexistent='raise')
                      if data.index.tz is None else data.index.tz_convert(ET_NAME))
        cutoffs = (pd.Series(data.index + source_interval, index=data.index)
                   if source_interval is not None else
                   pd.Series(pd.DatetimeIndex([], tz=ET_NAME), index=data.index))
        if known_intraday and len(data):
            schedule = session_schedule(data.index.min().date(), data.index.max().date())
            grid = _intraday_grid(schedule, source_interval)
            data = data.loc[data.index.isin(grid)]
            cutoffs = cutoffs.reindex(data.index)
            session_closes = {stamp.date(): close.tz_convert(ET_NAME)
                              for stamp, close in schedule['market_close'].items()}
            cutoffs = pd.Series([min(cutoff, session_closes[stamp.date()])
                                 for stamp, cutoff in cutoffs.items()], index=data.index)
        data = data.loc[(cutoffs <= clock).to_numpy()]
        cutoffs = cutoffs.reindex(data.index)

    if 'Close' not in data and 'Last' in data:
        data = data.rename(columns={'Last': 'Close'})
    for column in ['Open', 'High', 'Low', 'Close']:
        if column not in data and data.empty:
            data[column] = pd.Series(dtype=float)
    valid = validate_ohlc_rows(data)
    prices = data[['Open', 'High', 'Low', 'Close']].apply(pd.to_numeric, errors='coerce')
    if 'Volume' in data:
        prices['Volume'] = pd.to_numeric(data['Volume'], errors='coerce')
    else:
        prices['Volume'] = np.nan

    session_open_cache = {}

    def label_for(stamp):
        if timeframe in _PERIOD_FREQ:
            wall = pd.Timestamp(stamp)
            if wall.tzinfo:
                wall = wall.tz_localize(None)  # tz-ok: already Eastern, period label
            return wall.to_period(_PERIOD_FREQ[timeframe]).end_time.normalize()
        if known_intraday:
            day = pd.Timestamp(stamp).date()
            if day not in session_open_cache:
                schedule = _period_schedule(stamp, '1d')
                session_open_cache[day] = (schedule.iloc[0]['market_open'].tz_convert(ET_NAME)
                                           if len(schedule) else None)
            opening = session_open_cache[day]
            if opening is None:
                return pd.Timestamp(stamp).floor(RESAMPLE_RULES[timeframe])
            return opening + ((stamp - opening) // target_interval) * target_interval
        return pd.Timestamp(stamp).floor(RESAMPLE_RULES[timeframe])

    def labels_for(index):
        """``label_for`` over a whole index, vectorized; same values, same order."""
        index = pd.DatetimeIndex(index)
        if not len(index):
            return pd.DatetimeIndex([label_for(stamp) for stamp in index])
        if timeframe in _PERIOD_FREQ:
            wall = index.tz_localize(None) if index.tz is not None else index  # tz-ok: already Eastern, period labels
            return wall.to_period(_PERIOD_FREQ[timeframe]).end_time.normalize()
        if known_intraday:
            days = pd.DatetimeIndex(index.date)
            opens = session_schedule(days.min().date(), days.max().date())['market_open']
            opens = opens.dt.tz_convert(ET_NAME)
            missing_days = ~days.isin(opens.index)
            if missing_days.any():
                return pd.DatetimeIndex([label_for(stamp) for stamp in index])
            opening = pd.DatetimeIndex(opens.reindex(days))
            return opening + ((index - opening) // target_interval) * target_interval
        return pd.DatetimeIndex([label_for(stamp) for stamp in index])

    def period_dates(stamps):
        """First and last calendar day of each stamp's period, as int64 day labels."""
        stamps = pd.DatetimeIndex(stamps)
        if stamps.tz is not None:
            stamps = stamps.tz_convert(ET_NAME).tz_localize(None)  # tz-ok: converted to Eastern first; session labels
        periods = stamps.to_period(_PERIOD_FREQ.get(timeframe, 'D'))
        return (periods.start_time.normalize().as_unit('ns').asi8,
                periods.end_time.normalize().as_unit('ns').asi8)

    # Group source positions without pandas first/last skipping null observations.
    row_labels = labels_for(data.index)
    groups = {}
    for position, label in enumerate(row_labels):
        groups.setdefault(label, []).append(position)
    current_label = label_for(clock)

    # One schedule covering every period this call inspects, read as integer
    # nanoseconds: the same rows ``_period_schedule`` returns for each period,
    # without a calendar copy and a pandas slice per period.
    keys = list(groups) + [clock]
    walls = [key.tz_convert(ET_NAME).tz_localize(None) if key.tzinfo is not None else key  # tz-ok: converted to Eastern first; session labels
             for key in keys]
    starts, ends = period_dates(walls)
    bounds = {key: (int(start), int(end)) for key, start, end in zip(keys, starts, ends)}
    full_schedule = session_schedule(pd.Timestamp(int(starts.min())).date(),
                                     pd.Timestamp(int(ends.max())).date())
    day_ns = pd.DatetimeIndex(full_schedule.index).as_unit('ns').asi8
    open_ns = pd.DatetimeIndex(full_schedule['market_open']).as_unit('ns').asi8
    close_ns = pd.DatetimeIndex(full_schedule['market_close']).as_unit('ns').asi8
    clock_ns = clock.value
    data_index = data.index
    data_ns = pd.DatetimeIndex(data_index).as_unit('ns').asi8
    cutoff_ns = pd.DatetimeIndex(cutoffs).as_unit('ns').asi8 if len(cutoffs) else np.array([], dtype='int64')
    valid_values = valid.to_numpy(dtype=bool)
    open_values = prices['Open'].to_numpy()
    position_of = {value: position for position, value in enumerate(data_ns.tolist())}
    grid_cache = {}

    def utc_instant(value):
        return pd.Timestamp(int(value), tz='UTC').tz_convert(ET_NAME)

    def session_grid(lo, hi):
        if (lo, hi) not in grid_cache:
            day_schedule = full_schedule.iloc[lo:hi]
            grid_cache[(lo, hi)] = (_intraday_grid(day_schedule, source_interval),
                                    {stamp.date(): close.tz_convert(ET_NAME)
                                     for stamp, close in day_schedule['market_close'].items()})
        return grid_cache[(lo, hi)]

    def coverage(key, positions):
        start_day, end_day = bounds[key]
        lo = int(np.searchsorted(day_ns, start_day, side='left'))
        hi = max(lo, int(np.searchsorted(day_ns, end_day, side='right')))
        stamp = key
        reasons = list(base_reasons)
        start = end = None
        if hi > lo:
            first_open = utc_instant(open_ns[lo])
            start = first_open
            end = utc_instant(close_ns[hi - 1])
            if target_interval is not None:
                start = label_for(stamp)
                if start < first_open or start >= end:
                    start = end = None
                    reasons.append('outside_regular_session')
                else:
                    end = min(start + target_interval, end)
        else:
            reasons.append('non_trading_period')
        observed_ns = data_ns[positions]
        observed_valid = valid_values[positions]
        expected_ns = np.array([], dtype='int64')
        opening_ns = None
        if daily and hi > lo:
            expected_ns = day_ns[lo:hi][close_ns[lo:hi] <= clock_ns]
            opening_ns = int(day_ns[lo])
        elif known_intraday and hi > lo and start is not None:
            grid, session_closes = session_grid(lo, hi)
            expected = grid[(grid >= start) & (grid < end)]
            expected = expected[[min(value + source_interval, session_closes[value.date()]) <= clock
                                 for value in expected]]
            expected_ns = expected.as_unit('ns').asi8
            opening_ns = start.as_unit('ns').value
        missing_ns = np.setdiff1d(expected_ns, observed_ns)
        if len(missing_ns):
            reasons.append('missing_observations')
        opening_position = position_of.get(opening_ns) if opening_ns is not None else None
        open_observed = (opening_position is not None and opening_position in set(positions)
                         and bool(valid_values[opening_position]))
        if not open_observed:
            reasons.append('missing_period_open')
        if not len(positions):
            reasons.append('no_observations')
        if not observed_valid.all():
            reasons.append('invalid_ohlc')
        cutoff = None
        if len(positions):
            observed_cutoffs = cutoff_ns[positions]
            observed_cutoffs = observed_cutoffs[observed_cutoffs != pd.NaT.value]
            if len(observed_cutoffs):
                cutoff = utc_instant(observed_cutoffs.max())
        if daily:
            missing_days = pd.DatetimeIndex(missing_ns)
        else:
            missing_days = pd.DatetimeIndex(missing_ns, tz='UTC').tz_convert(ET_NAME)
        complete = bool(end is not None and clock >= end)
        return {
            'timeframe': timeframe, 'aggregation_policy': 'observed_v2',
            'period_start': start.isoformat() if start is not None else None,
            'period_end': end.isoformat() if end is not None else None,
            'period_open_observed': bool(open_observed),
            'open': float(open_values[opening_position]) if open_observed else None,
            'completed': complete, 'partial': bool(end is not None and not complete),
            'coverage_complete': bool(not base_reasons and len(expected_ns) and not len(missing_ns) and observed_valid.all()),
            'available': bool(not base_reasons and len(positions) and observed_valid.all()),
            'observed_count': len(positions), 'expected_count': len(expected_ns),
            'missing_count': len(missing_ns),
            'missing_sessions': sorted({str(value.date()) for value in missing_days}),
            'source_resolution': resolution or 'unknown', 'session_policy': policy,
            'timestamp_semantics': semantics,
            'source_cutoff': cutoff.isoformat() if cutoff is not None else None,
            'source_age_seconds': (clock - cutoff).total_seconds() if cutoff is not None else None,
            'source_acquired_at': df.attrs.get('source_acquired_at'),
            'source_acquisition_status': df.attrs.get('source_acquisition_status', 'unknown'),
            'price_adjustment': df.attrs.get('price_adjustment', 'unknown'),
            'reasons': reasons,
        }

    columns = {name: prices[name].to_numpy() for name in ('Open', 'High', 'Low', 'Close', 'Volume')}
    records, period_coverage = [], {}
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)  # all-NaN slices are NaN, as pandas gives
        for label, positions in groups.items():
            take = np.asarray(positions)
            highs, lows, volumes = (columns['High'][take], columns['Low'][take],
                                    columns['Volume'][take])
            record = {'Open': columns['Open'][take[0]],
                      'High': np.nan if np.isnan(highs).all() else np.nanmax(highs),
                      'Low': np.nan if np.isnan(lows).all() else np.nanmin(lows),
                      'Close': columns['Close'][take[-1]],
                      'Volume': np.nan if np.isnan(volumes).all() else np.nansum(volumes)}
            if not valid_values[take].all():
                # Any malformed constituent makes aggregate OHLC unavailable. Keep
                # the position so the next bar cannot bridge an invalid observation.
                record.update({key: np.nan for key in ('Open', 'High', 'Low', 'Close')})
            records.append(record)
            period_coverage[label.isoformat()] = coverage(label, positions)
    result = pd.DataFrame(records, index=pd.DatetimeIndex(list(groups)),
                          columns=['Open', 'High', 'Low', 'Close', 'Volume'])
    current_coverage = coverage(clock, groups.get(current_label, []))
    gaps = {label.isoformat(): False for label in result.index}
    if len(result) > 1:
        if timeframe in _PERIOD_FREQ:
            schedule = session_schedule(result.index[0].date() - timedelta(days=7), result.index[-1].date())
            labels = pd.DatetimeIndex(sorted(set(labels_for(schedule.index))))
        elif known_intraday:
            schedule = session_schedule(result.index[0].date(), result.index[-1].date())
            labels = pd.DatetimeIndex(sorted(set(labels_for(_intraday_grid(schedule, source_interval)))))
        else:
            labels = pd.DatetimeIndex([])
        label_positions = labels.get_indexer(result.index) if len(labels) else None
        for number, (previous, current) in enumerate(zip(result.index[:-1], result.index[1:])):
            gaps[current.isoformat()] = bool(base_reasons or not len(labels) or
                label_positions[number + 1] - label_positions[number] != 1)
            if daily or known_intraday:
                # An incomplete constituent range cannot classify either side
                # of a comparison, even when both target labels exist.
                gaps[current.isoformat()] |= any(
                    not period_coverage[stamp.isoformat()]['coverage_complete']
                    for stamp in (previous, current))
    key_semantics = 'session_label' if timeframe in _PERIOD_FREQ else 'utc_instant'
    if target_interval is not None and result.index.tz is not None:
        # Intraday identities are instants, independent of index display zone.
        # A naive Eastern -> UTC adapter therefore needs no metadata mutation.
        period_coverage = {stamp.tz_convert('UTC').isoformat(): period_coverage[stamp.isoformat()]
                           for stamp in result.index}
        gaps = {stamp.tz_convert('UTC').isoformat(): gaps[stamp.isoformat()]
                for stamp in result.index}
        if naive_source:
            result.index = result.index.tz_localize(None)  # tz-ok: preserve naive Eastern API
    result.attrs = {
        'aggregation_policy': 'observed_v2',
        'source_resolution': timeframe, 'session_policy': policy,
        'timestamp_semantics': 'session_label' if timeframe in _PERIOD_FREQ else 'bar_start',
        'observation_ts': clock.isoformat(), 'coverage': current_coverage,
        'period_coverage': period_coverage, 'gap_before_by_timestamp': gaps,
        'period_key_semantics': key_semantics, 'gap_key_semantics': key_semantics,
        'naive_index_timezone': ET_NAME,
    }
    return result
