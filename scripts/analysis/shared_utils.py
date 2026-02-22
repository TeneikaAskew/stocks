"""
Shared utilities for the per-ticker analysis pipeline.

Provides data loading, Strat classification, indicator enrichment,
timeframe resampling, and markdown report generation used across
all analysis phases.
"""

import pandas as pd
import numpy as np
import json
import sys
import os
from pathlib import Path
from datetime import datetime, time, timedelta
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.data_loader import DataLoader, RESAMPLE_RULES
from lib.strat import StratClassifier
from lib.indicators import (
    add_all_indicators, calculate_rsi, calculate_ema, calculate_atr,
    calculate_vwap, calculate_rvol, calculate_obv, calculate_stoch_rsi,
    calculate_order_blocks, calculate_all_orb, calculate_historical_levels,
)
from lib.config import (
    IndicatorConfig, StratConfig, SignalConfig, ExitConfig,
    RiskConfig, BacktestConfig, load_config,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TICKERS = ['IWM', 'SPY', 'QQQ']
REFERENCE_TICKERS = ['SPX']
ALL_TICKERS = TICKERS + REFERENCE_TICKERS

STRAT_TYPES = ['1', '2U', '2D', '3']

TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', 'D']

MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

# RTH filter: only regular trading hours
RTH_START = time(9, 30)
RTH_END = time(16, 0)

REPORTS_DIR = PROJECT_ROOT / 'reports'
DATA_DIR = PROJECT_ROOT / 'data'


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_ticker_1m(ticker: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """Load 1-minute data for a ticker, filtered to RTH and sorted."""
    loader = DataLoader(str(DATA_DIR))
    df = loader.load_intraday(ticker, start_date=start_date, end_date=end_date)
    if df.empty:
        print(f"  WARNING: No data for {ticker}")
        return df

    # Ensure Time column
    if 'Time' not in df.columns:
        df['Time'] = df.index

    # Filter to regular trading hours only
    df = filter_rth(df)

    # Remove duplicates
    df = df[~df.index.duplicated(keep='first')]

    return df.sort_index()


def filter_rth(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to regular trading hours (9:30 - 16:00)."""
    if df.empty:
        return df
    times = pd.to_datetime(df.index).time if isinstance(df.index, pd.DatetimeIndex) else pd.to_datetime(df['Time']).dt.time
    mask = pd.Series(times, index=df.index).apply(lambda t: RTH_START <= t <= RTH_END)
    return df[mask]


def get_trading_dates(df: pd.DataFrame) -> pd.Series:
    """Extract trading dates from a DataFrame."""
    if 'Time' in df.columns:
        return pd.to_datetime(df['Time']).dt.date
    return df.index.date


def split_by_period(df: pd.DataFrame, recent_years: int = 3) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Split data into full period and recent period."""
    if df.empty:
        return df, df
    last_date = df.index.max()
    cutoff = last_date - pd.DateOffset(years=recent_years)
    recent = df[df.index >= cutoff]
    return df, recent


# ---------------------------------------------------------------------------
# Timeframe resampling
# ---------------------------------------------------------------------------

def resample_to_timeframe(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Resample 1m data to a higher timeframe."""
    if timeframe == '1m':
        return df.copy()

    rule = RESAMPLE_RULES.get(timeframe)
    if rule is None:
        raise ValueError(f"Unknown timeframe: {timeframe}")

    close_col = 'Close' if 'Close' in df.columns else 'Last'

    resampled = df.resample(rule).agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        close_col: 'last',
        'Volume': 'sum',
    }).dropna()

    if close_col != 'Close':
        resampled = resampled.rename(columns={close_col: 'Close'})

    return resampled


def build_multi_timeframe_dict(df_1m: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Build dict of DataFrames at all analysis timeframes from 1m data."""
    result = {'1m': df_1m}
    for tf in TIMEFRAMES:
        if tf == '1m':
            continue
        try:
            result[tf] = resample_to_timeframe(df_1m, tf)
        except Exception as e:
            print(f"  Warning: failed to resample to {tf}: {e}")
    return result


# ---------------------------------------------------------------------------
# Strat classification at any timeframe
# ---------------------------------------------------------------------------

def classify_strat_series(df: pd.DataFrame) -> pd.Series:
    """Classify Strat types for a DataFrame."""
    classifier = StratClassifier()
    return classifier.classify_series(df)


def add_strat_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add Strat classification and combo columns to a DataFrame."""
    classifier = StratClassifier()
    return classifier.add_strat_columns(df)


# ---------------------------------------------------------------------------
# Indicator enrichment
# ---------------------------------------------------------------------------

def enrich_with_indicators(df: pd.DataFrame, indicator_config: IndicatorConfig = None,
                           skip_levels: bool = False) -> pd.DataFrame:
    """Add all technical indicators + Strat + historical levels + order blocks.

    Args:
        df: Input OHLCV DataFrame.
        indicator_config: Optional indicator configuration.
        skip_levels: If True, skip calculate_historical_levels and calculate_order_blocks
                     to reduce peak memory usage (~1.5GB savings on 1M bar datasets).
                     Columns guarded by 'if col in df.columns' checks will simply be absent.
    """
    if indicator_config is None:
        indicator_config = IndicatorConfig()

    close_col = 'Close' if 'Close' in df.columns else 'Last'

    # Core indicators (RSI, EMA, VWAP, ATR, BB, MACD, ORB, etc.)
    df = add_all_indicators(df, close_col=close_col, indicator_config=indicator_config)

    if not skip_levels:
        # Historical levels (prev day/week/month/year highs/lows)
        if 'Time' in df.columns:
            try:
                levels = calculate_historical_levels(
                    pd.to_datetime(df['Time']),
                    df['High'], df['Low'], df['Open'], df[close_col],
                )
                df = pd.concat([df, levels], axis=1)
            except Exception:
                pass

        # Order blocks
        try:
            atr_col = indicator_config.atr_col
            atr = df[atr_col] if atr_col in df.columns else None
            ob = calculate_order_blocks(
                df['High'], df['Low'], df[close_col], atr=atr,
                lookback=indicator_config.order_block_lookback,
                consol_window=indicator_config.order_block_consol_window,
                consol_threshold=indicator_config.order_block_consol_threshold,
                vol_ratio=indicator_config.order_block_vol_ratio,
                ffill_limit=indicator_config.order_block_ffill_limit,
                level_tolerance=indicator_config.order_block_level_tolerance,
            )
            df = pd.concat([df, ob], axis=1)
        except Exception:
            pass

    # Strat classification
    df = add_strat_columns(df)

    # OBV slope (rising/falling)
    if 'OBV' in df.columns:
        df['OBV_Slope'] = df['OBV'].diff(5)

    # EMA cross
    ema_fast = indicator_config.ema_fast_period
    ema_mid = indicator_config.ema_mid_period
    if f'EMA{ema_fast}' in df.columns and f'EMA{ema_mid}' in df.columns:
        df['EMA_Cross'] = (df[f'EMA{ema_fast}'] > df[f'EMA{ema_mid}']).astype(int)

    return df


# ---------------------------------------------------------------------------
# Return calculation helpers
# ---------------------------------------------------------------------------

def calculate_forward_returns(df: pd.DataFrame, periods: List[int] = None, close_col: str = 'Close') -> pd.DataFrame:
    """Calculate forward returns (in bps) over multiple periods."""
    if periods is None:
        periods = [1, 5, 10, 15, 30]

    result = pd.DataFrame(index=df.index)
    close = df[close_col] if close_col in df.columns else df['Close']

    for p in periods:
        result[f'fwd_ret_{p}'] = close.pct_change(p).shift(-p) * 10000  # bps

    return result


def calculate_mfe_mae(df: pd.DataFrame, bar_idx: int, direction: str,
                      max_bars: int = 60, close_col: str = 'Close') -> Tuple[float, float]:
    """Calculate Max Favorable Excursion and Max Adverse Excursion from a bar."""
    close = df[close_col] if close_col in df.columns else df['Close']
    entry_price = close.iloc[bar_idx]

    end_idx = min(bar_idx + max_bars, len(df))
    future = close.iloc[bar_idx:end_idx]

    if len(future) <= 1:
        return 0.0, 0.0

    if direction == 'CALL':
        returns = (future - entry_price) / entry_price * 10000  # bps
    else:
        returns = (entry_price - future) / entry_price * 10000  # bps

    mfe = returns.max()
    mae = returns.min()
    return float(mfe), float(mae)


# ---------------------------------------------------------------------------
# Markdown report generation
# ---------------------------------------------------------------------------

def md_header(title: str, level: int = 1) -> str:
    return f"{'#' * level} {title}\n"


def md_table(headers: List[str], rows: List[List], align: List[str] = None) -> str:
    """Generate a markdown table."""
    if not rows:
        return ""

    if align is None:
        align = ['left'] * len(headers)

    # Header
    header_line = '| ' + ' | '.join(headers) + ' |'
    sep_map = {'left': ':---', 'right': '---:', 'center': ':---:'}
    sep_line = '| ' + ' | '.join(sep_map.get(a, '---') for a in align) + ' |'

    # Rows
    row_lines = []
    for row in rows:
        cells = [str(c) for c in row]
        row_lines.append('| ' + ' | '.join(cells) + ' |')

    return '\n'.join([header_line, sep_line] + row_lines) + '\n'


def fmt_pct(val: float, decimals: int = 1) -> str:
    """Format as percentage string."""
    if pd.isna(val):
        return 'N/A'
    return f"{val:.{decimals}f}%"


def fmt_bps(val: float, decimals: int = 1) -> str:
    """Format as basis points string."""
    if pd.isna(val):
        return 'N/A'
    return f"{val:+.{decimals}f} bps"


def fmt_num(val, decimals: int = 0) -> str:
    """Format a number with commas."""
    if pd.isna(val):
        return 'N/A'
    if decimals == 0:
        return f"{int(val):,}"
    return f"{val:,.{decimals}f}"


def save_report(content: str, filename: str):
    """Save a markdown report to the reports directory."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / filename
    with open(path, 'w') as f:
        f.write(content)
    print(f"  Report saved: {path}")


def timestamp_str() -> str:
    """Current timestamp for report headers."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def confidence_interval_95(successes: int, total: int) -> Tuple[float, float]:
    """Wilson score interval for binomial proportion (95% CI)."""
    if total == 0:
        return (0.0, 0.0)
    z = 1.96
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * np.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return (max(0, center - spread), min(1, center + spread))


def sample_size_label(n: int) -> str:
    """Confidence label based on sample size."""
    if n < 30:
        return 'Low'
    elif n < 100:
        return 'Moderate'
    elif n < 500:
        return 'Good'
    else:
        return 'High'


# ---------------------------------------------------------------------------
# Progress reporting
# ---------------------------------------------------------------------------

def progress(msg: str, ticker: str = None):
    """Print progress message."""
    prefix = f"[{ticker}] " if ticker else ""
    print(f"  {prefix}{msg}")
