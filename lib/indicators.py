"""
Consolidated technical indicator functions.

All functions are pure — they take pandas Series/DataFrame inputs and return
outputs with no side effects. Wilder's smoothing is used where appropriate
(RSI, ATR, Stochastic RSI) to match standard implementations.

Extracted from trading_analysis.py (canonical Wilder's implementations) and
analyze_market_data_enhanced.py (Bollinger, MACD, consecutive moves).
"""

import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Core smoothing
# ---------------------------------------------------------------------------

def wilder_moving_average(values: pd.Series, period: int) -> pd.Series:
    """Wilder's Moving Average (RMA).

    Formula: RMA[i] = (RMA[i-1] * (period-1) + value[i]) / period
    Equivalent to EWM with alpha = 1/period.
    """
    alpha = 1.0 / period
    return values.ewm(alpha=alpha, adjust=False).mean()


# ---------------------------------------------------------------------------
# Momentum indicators
# ---------------------------------------------------------------------------

def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index with Wilder's smoothing."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = wilder_moving_average(gain, period)
    avg_loss = wilder_moving_average(loss, period)

    with np.errstate(divide='ignore', invalid='ignore'):
        rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # Pure uptrend (avg_loss=0) → rs=inf → RSI=100; fill any remaining NaN
    rsi = rsi.fillna(50.0)
    return rsi


def calculate_stoch_rsi(
    rsi: pd.Series,
    period: int = 14,
    k_period: int = 3,
    d_period: int = 3,
) -> Tuple[pd.Series, pd.Series]:
    """Stochastic RSI with SMA smoothing for %K and %D.

    Uses SMA (not Wilder's RMA) for %K and %D, per the original Chande &
    Kroll specification and matching TradingView, Alpha Vantage, and TA-Lib.
    Returns NaN for the raw StochRSI until `period` RSI bars are available.
    """
    rsi_min = rsi.rolling(window=period, min_periods=period).min()
    rsi_max = rsi.rolling(window=period, min_periods=period).max()
    rsi_range = rsi_max - rsi_min

    with np.errstate(divide='ignore', invalid='ignore'):
        stoch_rsi = 100.0 * (rsi - rsi_min) / rsi_range.where(rsi_range > 0, np.nan)
        stoch_rsi = pd.Series(stoch_rsi, index=rsi.index).fillna(50.0)

    stoch_rsi_k = stoch_rsi.rolling(window=k_period, min_periods=k_period).mean()
    stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean()
    return stoch_rsi_k, stoch_rsi_d


def calculate_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, and histogram.

    MACD is NaN until the slow EMA is warmed up (`slow` bars); the signal
    line is NaN for a further `signal` bars. Matches TradingView / Alpha
    Vantage behaviour.
    """
    ema_fast = close.ewm(span=fast, min_periods=slow, adjust=False).mean()
    ema_slow = close.ewm(span=slow, min_periods=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, min_periods=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ---------------------------------------------------------------------------
# Trend / moving averages
# ---------------------------------------------------------------------------

def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average (standard span-based).

    Returns NaN until `period` bars are available, matching TradingView
    and Alpha Vantage behaviour.
    """
    return prices.ewm(span=period, min_periods=period, adjust=False).mean()


def calculate_sma(prices: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average. Returns NaN until `period` bars are available."""
    return prices.rolling(window=period, min_periods=period).mean()


# ---------------------------------------------------------------------------
# Volatility indicators
# ---------------------------------------------------------------------------

def calculate_true_range(
    high: pd.Series, low: pd.Series, close_prev: pd.Series,
) -> pd.Series:
    """True Range — max of (H-L, |H-Cprev|, |L-Cprev|)."""
    hl = high - low
    hc = (high - close_prev).abs()
    lc = (low - close_prev).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1)


def calculate_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14,
) -> pd.Series:
    """Average True Range with Wilder's smoothing."""
    close_prev = close.shift(1)
    tr = calculate_true_range(high, low, close_prev)
    return wilder_moving_average(tr, period)


def calculate_atr_expansion(
    high: pd.Series, low: pd.Series, close: pd.Series,
    short: int = 5, long: int = 20,
) -> pd.Series:
    """Ratio of short-window ATR to long-window ATR.

    Phase 0.7.x — used by the `atr_expansion` momentum condition.
    Values > 1 indicate recent volatility is above its longer-window
    baseline (vol expansion regime); < 1 indicates contraction. The
    momentum strategy fires the gate when the ratio exceeds
    `ATR_EXPANSION_THRESHOLD`, indicating tradeable conditions.
    """
    atr_short = calculate_atr(high, low, close, short)
    atr_long  = calculate_atr(high, low, close, long)
    return atr_short / atr_long.where(atr_long > 0, np.nan)


def calculate_bollinger_bands(
    close: pd.Series, period: int = 20, std_mult: float = 2.0,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands — returns (upper, middle, lower).

    Uses population std (ddof=0) to match TradingView, TA-Lib, Bloomberg,
    and Alpha Vantage — per John Bollinger's original specification.
    Returns NaN for bars before the lookback period is satisfied.
    """
    middle = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + std_mult * std
    lower = middle - std_mult * std
    return upper, middle, lower


# ---------------------------------------------------------------------------
# Volume indicators
# ---------------------------------------------------------------------------

def calculate_vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    dates: pd.Series,
) -> pd.Series:
    """Volume Weighted Average Price — resets each trading day.

    Parameters
    ----------
    dates : Series of date-like values used to group bars into sessions.
    """
    typical_price = (high + low + close) / 3.0
    tpv = typical_price * volume

    df_tmp = pd.DataFrame({'tpv': tpv, 'vol': volume, 'date': dates})
    cum_tpv = df_tmp.groupby('date')['tpv'].cumsum()
    cum_vol = df_tmp.groupby('date')['vol'].cumsum()

    vwap = cum_tpv / cum_vol.where(cum_vol > 0, np.nan)
    return vwap


def calculate_rvol(volume: pd.Series, period: int = 20) -> pd.Series:
    """Relative Volume — current volume / rolling average volume."""
    rolling_avg = volume.rolling(window=period, min_periods=1).mean()
    return volume / rolling_avg.where(rolling_avg > 0, np.nan)


def calculate_rvol_recent(volume: pd.Series, period: int = 20) -> pd.Series:
    """Median-based relative volume — current / rolling MEDIAN volume.

    Phase 0.7.x — used by the `rvol_above_recent` momentum condition.
    Median is robust to outlier high-volume bars (news spikes, opening
    minute) that depress the mean-based RVOL on subsequent bars and
    cause the gate to mis-fire.
    """
    rolling_med = volume.rolling(window=period, min_periods=1).median()
    return volume / rolling_med.where(rolling_med > 0, np.nan)


def calculate_rvol_minute_of_day(
    times: pd.Series, volume: pd.Series,
) -> pd.Series:
    """RVOL adjusted by minute-of-day average.

    Parameters
    ----------
    times : Series of datetime values with intraday timestamps.
    volume : Corresponding volume values.
    """
    minute_of_day = times.dt.hour * 60 + times.dt.minute
    minute_avg = pd.Series(minute_of_day).map(
        pd.DataFrame({'mod': minute_of_day, 'vol': volume})
        .groupby('mod')['vol']
        .mean()
    )
    minute_avg = minute_avg.values
    # Avoid division by zero
    minute_avg_safe = np.where(minute_avg > 0, minute_avg, np.nan)
    return volume.values / minute_avg_safe


def calculate_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume — vectorized cumulative sum approach."""
    price_change = close.diff()
    vol_direction = pd.Series(0.0, index=close.index)
    vol_direction[price_change > 0] = volume[price_change > 0]
    vol_direction[price_change < 0] = -volume[price_change < 0]
    return vol_direction.cumsum()


# ---------------------------------------------------------------------------
# Pattern / consecutive-move detection
# ---------------------------------------------------------------------------

def calculate_consecutive_moves(
    price_change: pd.Series, periods: int = 3,
) -> Tuple[pd.Series, pd.Series]:
    """Count consecutive up and down moves (rolling window).

    Returns (consecutive_up, consecutive_down) as integer Series.
    """
    up = (price_change > 0).astype(int)
    down = (price_change < 0).astype(int)
    consecutive_up = up.rolling(periods, min_periods=1).sum()
    consecutive_down = down.rolling(periods, min_periods=1).sum()
    return consecutive_up, consecutive_down


# ---------------------------------------------------------------------------
# Historical levels (prev day/week/month/year)
# ---------------------------------------------------------------------------

def calculate_historical_levels(
    times: pd.Series,
    high: pd.Series,
    low: pd.Series,
    open_: pd.Series,
    close: pd.Series,
) -> pd.DataFrame:
    """Previous period levels (day, week, month, year) with midpoints,
    price-position percentages, at-level flags, and breakout indicators.

    Returns a DataFrame with ~80 new columns aligned to the input index.
    """
    df = pd.DataFrame({
        'Time': times, 'High': high, 'Low': low, 'Open': open_, 'Close': close,
    })
    df['Date'] = pd.to_datetime(df['Time']).dt.date
    df['Week'] = pd.to_datetime(df['Time']).dt.to_period('W')
    df['Month'] = pd.to_datetime(df['Time']).dt.to_period('M')
    df['Quarter'] = pd.to_datetime(df['Time']).dt.to_period('Q')
    df['Year'] = pd.to_datetime(df['Time']).dt.to_period('Y')

    result = pd.DataFrame(index=df.index)

    for period_col, label in [
        ('Date', 'Day'), ('Week', 'Week'), ('Month', 'Month'),
        ('Quarter', 'Quarter'), ('Year', 'Year'),
    ]:
        grp = df.groupby(period_col).agg(
            H=('High', 'max'), L=('Low', 'min'), O=('Open', 'first'), C=('Close', 'last'),
        )
        shifted = grp.shift(1)
        prefix = f'Prev_{label}'

        result[f'{prefix}_High'] = df[period_col].map(shifted['H'])
        result[f'{prefix}_Low'] = df[period_col].map(shifted['L'])
        result[f'{prefix}_Open'] = df[period_col].map(shifted['O'])
        result[f'{prefix}_Close'] = df[period_col].map(shifted['C'])
        result[f'{prefix}_HL_Mid'] = (result[f'{prefix}_High'] + result[f'{prefix}_Low']) / 2.0
        result[f'{prefix}_OC_Mid'] = (result[f'{prefix}_Open'] + result[f'{prefix}_Close']) / 2.0

        # Price position as percentage
        for lev in [f'{prefix}_High', f'{prefix}_Low', f'{prefix}_Open',
                    f'{prefix}_Close', f'{prefix}_HL_Mid', f'{prefix}_OC_Mid']:
            result[f'{lev}_Pct'] = (close.values - result[lev].values) / result[lev].values * 100.0
            result[f'At_{lev}'] = (result[f'{lev}_Pct'].abs() <= 0.1).astype(int)

        # Breakout / breakdown flags
        result[f'Broke_{prefix}_High'] = (close.values > result[f'{prefix}_High'].values).astype(int)
        result[f'Broke_{prefix}_Low'] = (close.values < result[f'{prefix}_Low'].values).astype(int)

    return result


# ---------------------------------------------------------------------------
# Pre-market context (4:00 AM - 9:30 AM ET extended-hours session)
# ---------------------------------------------------------------------------


def calculate_premarket_context(
    times: pd.Series,
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    *,
    prev_close: float = None,
    atr14: float = None,
    premarket_start: time = time(4, 0),     # 4:00 AM ET
    market_open: time = time(9, 30),        # 9:30 AM ET
) -> dict:
    """Compute pre-market H/L/VWAP/volume + gap_pct + pre_range_atr from
    extended-hours minute bars.

    Why this exists
    ---------------
    The 4/27 brief computed entry zones from Friday's H/L but Monday
    gapped up materially — every level was stale before the bell. This
    helper surfaces the pre-market range so the LLM analyst (and the
    strat_levels engine) can calibrate triggers to today's reality.

    Args:
        times, open_, high, low, close, volume: aligned 1-min bar series
        prev_close:  prior-day close, used to compute gap_pct. None → no gap_pct.
        atr14:       14-day ATR, used to normalise pre_range. None → no atr-norm.
        premarket_start: extended-hours start (default 4:00 AM ET)
        market_open: regular-session open (default 9:30 AM ET)

    Returns:
        dict with keys: pre_high, pre_low, pre_vwap, pre_volume, pre_open,
        pre_close, gap_pct, pre_range_atr, bar_count.

    Edge cases:
      - Empty pre-market bars → all numeric values None, bar_count=0
      - prev_close=None → gap_pct=None
      - atr14=None or 0 → pre_range_atr=None
      - All-NaN volume → pre_volume=None (avoid sum of NaN = 0 confusion)
    """
    out = {
        'pre_high': None, 'pre_low': None, 'pre_vwap': None,
        'pre_volume': None, 'pre_open': None, 'pre_close': None,
        'gap_pct': None, 'pre_range_atr': None, 'bar_count': 0,
    }

    if times is None or len(times) == 0:
        return out

    # Convert times to dt and filter to pre-market window
    ts = pd.to_datetime(times)
    if hasattr(ts, 'dt'):
        # If tz-aware, convert to ET; else assume already-ET
        ts_et = ts.dt.tz_convert('America/New_York') if ts.dt.tz is not None else ts
        time_of_day = ts_et.dt.time
    else:
        time_of_day = pd.Series([t.time() if hasattr(t, 'time') else t for t in ts])

    pre_mask = (time_of_day >= premarket_start) & (time_of_day < market_open)
    if not pre_mask.any():
        return out

    pre_h = high[pre_mask]
    pre_l = low[pre_mask]
    pre_c = close[pre_mask]
    pre_o = open_[pre_mask]
    pre_v = volume[pre_mask]

    out['bar_count'] = int(pre_mask.sum())
    out['pre_high'] = float(pre_h.max()) if not pre_h.empty else None
    out['pre_low']  = float(pre_l.min()) if not pre_l.empty else None
    out['pre_open'] = float(pre_o.iloc[0]) if not pre_o.empty else None
    out['pre_close'] = float(pre_c.iloc[-1]) if not pre_c.empty else None

    # VWAP — typical price weighted by volume
    typical = (pre_h + pre_l + pre_c) / 3.0
    if pre_v.notna().any() and pre_v.sum() > 0:
        out['pre_vwap'] = float((typical * pre_v).sum() / pre_v.sum())
        out['pre_volume'] = int(pre_v.fillna(0).sum())

    # Gap %: today's pre-market open vs yesterday's close
    if prev_close is not None and prev_close > 0 and out['pre_open'] is not None:
        out['gap_pct'] = round((out['pre_open'] / prev_close - 1) * 100, 4)

    # Pre-market range expansion vs ATR (regime tag)
    if atr14 is not None and atr14 > 0 and out['pre_high'] is not None and out['pre_low'] is not None:
        out['pre_range_atr'] = round((out['pre_high'] - out['pre_low']) / atr14, 4)

    return out


# ---------------------------------------------------------------------------
# Opening Range Breakout (ORB)
# ---------------------------------------------------------------------------

def calculate_orb(
    times: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    minutes: int = 5,
    label: str = '5m',
    market_open: time = None,
) -> pd.DataFrame:
    """ORB for a single timeframe window.

    Returns ~12 columns: High/Low/Range/Mid, price-position percentages,
    breakout flags, trend direction, and distance.
    """
    if market_open is None:
        market_open = time(9, 30)
    orb_end = (datetime.combine(datetime.today(), market_open) + timedelta(minutes=minutes)).time()

    df = pd.DataFrame({
        'Time': times, 'High': high, 'Low': low, 'Close': close,
    })
    df['Date'] = pd.to_datetime(df['Time']).dt.date
    df['TimeOnly'] = pd.to_datetime(df['Time']).dt.time

    in_orb = (df['TimeOnly'] >= market_open) & (df['TimeOnly'] <= orb_end)
    orb_highs = df[in_orb].groupby('Date')['High'].max()
    orb_lows = df[in_orb].groupby('Date')['Low'].min()

    result = pd.DataFrame(index=df.index)
    result[f'ORB_{label}_High'] = df['Date'].map(orb_highs)
    result[f'ORB_{label}_Low'] = df['Date'].map(orb_lows)
    result[f'ORB_{label}_Range'] = result[f'ORB_{label}_High'] - result[f'ORB_{label}_Low']
    result[f'ORB_{label}_Mid'] = (result[f'ORB_{label}_High'] + result[f'ORB_{label}_Low']) / 2.0

    # Percentage distances
    for ref in ['High', 'Low', 'Mid']:
        col = f'ORB_{label}_{ref}'
        result[f'{col}_Pct'] = (close.values - result[col].values) / result[col].values * 100.0

    # Post-ORB breakout / breakdown / trend
    post_orb = df['TimeOnly'] > orb_end
    result[f'ORB_{label}_Broke_High'] = 0
    result[f'ORB_{label}_Broke_Low'] = 0
    result[f'ORB_{label}_Within_Range'] = 0
    result[f'ORB_{label}_Trend'] = 0
    result[f'ORB_{label}_Distance'] = 0.0

    if post_orb.any():
        c = close.values
        oh = result[f'ORB_{label}_High'].values
        ol = result[f'ORB_{label}_Low'].values
        po = post_orb.values

        result.loc[po, f'ORB_{label}_Broke_High'] = (c[po] > oh[po]).astype(int)
        result.loc[po, f'ORB_{label}_Broke_Low'] = (c[po] < ol[po]).astype(int)
        result.loc[po, f'ORB_{label}_Within_Range'] = ((c[po] >= ol[po]) & (c[po] <= oh[po])).astype(int)

        above = po & (c > oh)
        below = po & (c < ol)
        result.loc[above, f'ORB_{label}_Trend'] = 1
        result.loc[below, f'ORB_{label}_Trend'] = -1
        result.loc[above, f'ORB_{label}_Distance'] = c[above] - oh[above]
        result.loc[below, f'ORB_{label}_Distance'] = c[below] - ol[below]

    return result


def calculate_all_orb(
    times: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    orb_windows: List[Dict] = None,
    market_open: time = None,
) -> pd.DataFrame:
    """Calculate ORB for configured windows (default: 5/15/30-min)."""
    if orb_windows is None:
        from lib.config import IndicatorConfig
        orb_windows = IndicatorConfig().orb_windows

    frames = []
    for window in orb_windows:
        frames.append(calculate_orb(
            times, high, low, close,
            minutes=window['minutes'],
            label=window['label'],
            market_open=market_open,
        ))
    return pd.concat(frames, axis=1)


# ---------------------------------------------------------------------------
# Order Blocks
# ---------------------------------------------------------------------------

def calculate_order_blocks(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr: pd.Series = None,
    lookback: int = 20,
    consol_window: int = 5,
    consol_threshold: int = 3,
    vol_ratio: float = 0.6,
    ffill_limit: int = 30,
    level_tolerance: float = 0.001,
) -> pd.DataFrame:
    """Detect institutional consolidation zones.

    Returns 7 columns: Zone flag, High/Low/Mid, Position, Distance, Test.
    """
    volatility = atr if atr is not None else (high - low)
    avg_vol = volatility.rolling(window=lookback, min_periods=1).mean()
    low_vol_threshold = avg_vol * vol_ratio

    zone = (volatility < low_vol_threshold).astype(int)

    consol_count = zone.rolling(window=consol_window, min_periods=consol_window).sum()
    is_ob = consol_count >= consol_threshold

    ob_high = high.rolling(window=consol_window, min_periods=consol_window).max()
    ob_low = low.rolling(window=consol_window, min_periods=consol_window).min()
    ob_high[~is_ob] = np.nan
    ob_low[~is_ob] = np.nan

    ob_mid = (ob_high + ob_low) / 2.0

    # Forward-fill for configured number of bars
    ob_high = ob_high.ffill(limit=ffill_limit)
    ob_low = ob_low.ffill(limit=ffill_limit)
    ob_mid = ob_mid.ffill(limit=ffill_limit)

    position = pd.Series(0, index=close.index)
    position[close > ob_high] = 1
    position[close < ob_low] = -1

    distance = pd.Series(0.0, index=close.index)
    above = close > ob_high
    below = close < ob_low
    distance[above] = close[above] - ob_high[above]
    distance[below] = close[below] - ob_low[below]

    at_high = ((close - ob_high) / ob_high).abs() <= level_tolerance
    at_low = ((close - ob_low) / ob_low).abs() <= level_tolerance
    test = (at_high | at_low).astype(int)

    return pd.DataFrame({
        'Order_Block_Zone': zone,
        'Order_Block_High': ob_high,
        'Order_Block_Low': ob_low,
        'Order_Block_Mid': ob_mid,
        'Order_Block_Position': position,
        'Order_Block_Distance': distance,
        'Order_Block_Test': test,
    }, index=close.index)


# ---------------------------------------------------------------------------
# Convenience: add all indicators to a DataFrame
# ---------------------------------------------------------------------------

def add_all_indicators(
    df: pd.DataFrame,
    close_col: str = 'Close',
    indicator_config=None,
) -> pd.DataFrame:
    """Add a comprehensive set of indicators to an OHLCV DataFrame.

    Expects columns: Open, High, Low, Close (or `close_col`), Volume, Time.
    Handles both 'Close' and 'Last' column naming via `close_col`.

    Parameters
    ----------
    indicator_config : IndicatorConfig, optional
        All indicator periods and parameters. Uses defaults if None.
    """
    if indicator_config is None:
        from lib.config import IndicatorConfig
        indicator_config = IndicatorConfig()

    ind = indicator_config
    out = df.copy()
    c = out[close_col]
    h = out['High']
    l = out['Low']
    v = out['Volume']

    # ATR
    out[ind.atr_col] = calculate_atr(h, l, c, ind.atr_period)
    # Phase 0.7.x — short/long ATR ratio for the `atr_expansion` gate.
    # Values > 1 = recent volatility above baseline (regime expansion).
    out['ATR_Expansion'] = calculate_atr_expansion(h, l, c, short=5, long=20)

    # RSI
    out[ind.rsi_col] = calculate_rsi(c, ind.rsi_period)
    out[ind.rsi_fast_col] = calculate_rsi(c, ind.rsi_fast_period)

    # EMAs
    for p in ind.ema_periods:
        out[f'EMA{p}'] = calculate_ema(c, p)

    # SMAs
    for p in ind.sma_periods:
        out[f'SMA{p}'] = calculate_sma(c, p)

    # VWAP
    if 'Time' in out.columns:
        dates = pd.to_datetime(out['Time']).dt.date
        out['VWAP'] = calculate_vwap(h, l, c, v, dates)

    # RVOL
    out['RVOL'] = calculate_rvol(v, ind.rvol_period)
    # Phase 0.7.x — median-based RVOL for the `rvol_above_recent` gate
    # (robust to outlier-volume bars vs. the mean-based RVOL above).
    out['RVol_Recent_20'] = calculate_rvol_recent(v, ind.rvol_period)

    # OBV
    out['OBV'] = calculate_obv(c, v)

    # Stochastic RSI
    out['StochRSI_K'], out['StochRSI_D'] = calculate_stoch_rsi(
        out[ind.rsi_col], ind.stoch_rsi_period, ind.stoch_rsi_k_period, ind.stoch_rsi_d_period,
    )

    # Bollinger Bands
    out['BB_Upper'], out['BB_Middle'], out['BB_Lower'] = calculate_bollinger_bands(
        c, ind.bb_period, ind.bb_std_mult,
    )
    out['BB_Width'] = out['BB_Upper'] - out['BB_Lower']
    bb_range = out['BB_Upper'] - out['BB_Lower']
    out['BB_Pct'] = (c - out['BB_Lower']) / bb_range.where(bb_range > 0, np.nan)

    # MACD
    out['MACD'], out['MACD_Signal'], out['MACD_Histogram'] = calculate_macd(
        c, ind.macd_fast, ind.macd_slow, ind.macd_signal,
    )

    # Consecutive moves
    price_change = c.pct_change() * 100.0
    out['Price_Change'] = price_change
    out['Consecutive_Up'], out['Consecutive_Down'] = calculate_consecutive_moves(
        price_change, ind.consecutive_periods,
    )
    out['Consecutive_Up_5'], out['Consecutive_Down_5'] = calculate_consecutive_moves(
        price_change, ind.consecutive_relaxed_window,
    )

    # Price position relative to first two EMAs
    ema_fast_p = ind.ema_fast_period
    ema_mid_p = ind.ema_mid_period
    out[f'Price_vs_EMA{ema_fast_p}'] = (c - out[f'EMA{ema_fast_p}']) / out[f'EMA{ema_fast_p}'] * 100.0
    out[f'Price_vs_EMA{ema_mid_p}'] = (c - out[f'EMA{ema_mid_p}']) / out[f'EMA{ema_mid_p}'] * 100.0
    if 'VWAP' in out.columns:
        out['Price_vs_VWAP'] = (c - out['VWAP']) / out['VWAP'] * 100.0

    # Daily range metrics
    out['Daily_Range'] = h - l
    out['Daily_Range_Pct'] = (h - l) / c * 100.0
    out['Close_vs_Range'] = (c - l) / (h - l).where((h - l) > 0, np.nan)

    # ORB (Opening Range Breakout)
    if 'Time' in out.columns:
        orb_result = calculate_all_orb(
            pd.to_datetime(out['Time']), h, l, c,
            orb_windows=ind.orb_windows,
        )
        out = pd.concat([out, orb_result], axis=1)

    return out
