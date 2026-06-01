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


def calculate_rsi_thrust(rsi: pd.Series, lookback: int = 3) -> pd.Series:
    """Signed RSI delta over `lookback` bars (current - lookback bars ago).

    Phase 0.7.x — used by the directional `rsi_thrust` momentum condition.
    Positive values = RSI accelerating up (bullish thrust); negative =
    accelerating down (bearish thrust). Complements the existing band
    check (`rsi_bullish_recovery`) which is a level test, not a velocity
    test — a bar with RSI=70 (out of recovery band) but delta=+10 has
    thrust without recovery.
    """
    return rsi - rsi.shift(lookback)


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
# Current-period running levels (today / WTD / MTD / QTD / YTD)
# ---------------------------------------------------------------------------

def calculate_current_period_levels(
    times: pd.Series,
    high: pd.Series,
    low: pd.Series,
    open_: pd.Series,
    close: pd.Series,
) -> pd.DataFrame:
    """Running HLO for current day / week / month / quarter / year, accumulating
    up to (and including) each bar. Close is NOT emitted here because the
    current bar's close is already in the OHLC source.

    For each period (Day/Week/Month/Quarter/Year), emits per-bar:
      Cur_<Period>_Open : first bar's open of the current period
      Cur_<Period>_High : running max of high up to and including this bar
      Cur_<Period>_Low  : running min of low up to and including this bar
      Cur_<Period>_HL_Mid: (Cur_High + Cur_Low) / 2
      Cur_<Period>_OC_Mid: (Cur_Open + close) / 2

    Plus normalized features per period:
      Cur_<Period>_Range_Pct  : (Cur_High - Cur_Low) / Cur_Open * 100
      Pos_in_Cur_<Period>     : (close - Cur_Low) / (Cur_High - Cur_Low)  in [0, 1]
      Pct_From_Cur_<Period>_Open : (close - Cur_Open) / Cur_Open * 100

    Returns: DataFrame indexed like input with ~40 columns.

    NO LOOKAHEAD: every value is computed using only bars at or before
    the current index within the same period bucket.
    """
    df = pd.DataFrame({
        'Time': times, 'High': high.values, 'Low': low.values,
        'Open': open_.values, 'Close': close.values,
    })
    ts = pd.to_datetime(df['Time'])
    df['Date'] = ts.dt.date
    df['Week'] = ts.dt.to_period('W')
    df['Month'] = ts.dt.to_period('M')
    df['Quarter'] = ts.dt.to_period('Q')
    df['Year'] = ts.dt.to_period('Y')

    result = pd.DataFrame(index=df.index)
    for period_col, label in [
        ('Date', 'Day'), ('Week', 'Week'), ('Month', 'Month'),
        ('Quarter', 'Quarter'), ('Year', 'Year'),
    ]:
        prefix = f'Cur_{label}'
        grp = df.groupby(period_col, sort=False)
        # running min/max (cummax/cummin, NOT period-final)
        result[f'{prefix}_High'] = grp['High'].cummax().values
        result[f'{prefix}_Low'] = grp['Low'].cummin().values
        # first open per period (broadcast — period's first bar's open)
        first_open = grp['Open'].transform('first')
        result[f'{prefix}_Open'] = first_open.values
        # midpoints
        result[f'{prefix}_HL_Mid'] = (
            (result[f'{prefix}_High'] + result[f'{prefix}_Low']) / 2.0
        )
        result[f'{prefix}_OC_Mid'] = (
            (result[f'{prefix}_Open'] + close.values) / 2.0
        )
        # normalized features
        rng = result[f'{prefix}_High'] - result[f'{prefix}_Low']
        result[f'{prefix}_Range_Pct'] = (
            rng / result[f'{prefix}_Open'].replace(0, np.nan) * 100.0
        )
        # position-in-range: 0 = at low, 1 = at high. NaN if range is 0.
        result[f'Pos_in_{prefix}'] = np.where(
            rng > 0, (close.values - result[f'{prefix}_Low']) / rng, np.nan,
        )
        result[f'Pct_From_{prefix}_Open'] = (
            (close.values - result[f'{prefix}_Open'])
            / result[f'{prefix}_Open'].replace(0, np.nan) * 100.0
        )

    return result


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

# ---------------------------------------------------------------------------
# Indicator block helpers (idempotent — each mutates & returns `out`)
# ---------------------------------------------------------------------------
# add_all_indicators (and the leaner capability tiers below) are composed from
# these blocks. Each block takes (out, ind, close_col) where:
#   out       : the working DataFrame (already a copy of the caller's input)
#   ind       : an IndicatorConfig
#   close_col : the close column name ('Close' or 'Last')
# The blocks were extracted VERBATIM from the historical inline body of
# add_all_indicators — the arithmetic is byte-identical. Each block documents
# the upstream columns it reads so the leaner tiers can order their calls so
# every dependency exists before it's consumed. The 'Time' guards for
# VWAP / ORB / Mins_Since_Open are preserved exactly.


def _add_atr(out, ind, close_col):
    """ATR + short/long ATR-expansion ratio. Deps: High, Low, close_col."""
    c = out[close_col]
    h = out['High']
    l = out['Low']
    out[ind.atr_col] = calculate_atr(h, l, c, ind.atr_period)
    # Additional ATR windows (e.g. ATR20 for research / longer-horizon
    # vol gauges). Skip the primary period to avoid recomputing it.
    for p in ind.atr_extra_periods:
        if p != ind.atr_period:
            out[f'ATR{p}'] = calculate_atr(h, l, c, p)
    # Phase 0.7.x — short/long ATR ratio for the `atr_expansion` gate.
    # Values > 1 = recent volatility above baseline (regime expansion).
    out['ATR_Expansion'] = calculate_atr_expansion(h, l, c, short=5, long=20)
    return out


def _add_rsi(out, ind, close_col):
    """RSI (slow + fast) and 3-bar RSI thrust. Deps: close_col."""
    c = out[close_col]
    out[ind.rsi_col] = calculate_rsi(c, ind.rsi_period)
    out[ind.rsi_fast_col] = calculate_rsi(c, ind.rsi_fast_period)
    # Additional RSI windows (e.g. RSI30). Skip any period that matches
    # the primary or fast period — already computed above.
    for p in ind.rsi_extra_periods:
        if p not in (ind.rsi_period, ind.rsi_fast_period):
            out[f'RSI{p}'] = calculate_rsi(c, p)
    # Phase 0.7.x — signed 3-bar RSI delta for the directional
    # `rsi_thrust` momentum gate.
    out['RSI_Thrust_3'] = calculate_rsi_thrust(out[ind.rsi_col], lookback=3)
    return out


def _add_emas(out, ind, close_col):
    """Exponential moving averages. Deps: close_col."""
    c = out[close_col]
    for p in ind.ema_periods:
        out[f'EMA{p}'] = calculate_ema(c, p)
    return out


def _add_smas(out, ind, close_col):
    """Simple moving averages. Deps: close_col."""
    c = out[close_col]
    for p in ind.sma_periods:
        out[f'SMA{p}'] = calculate_sma(c, p)
    return out


def _add_vwap(out, ind, close_col):
    """Session-resetting VWAP. Deps: High, Low, close_col, Volume, Time.

    Time-gated: produces no VWAP column when 'Time' is absent."""
    if 'Time' in out.columns:
        c = out[close_col]
        h = out['High']
        l = out['Low']
        v = out['Volume']
        dates = pd.to_datetime(out['Time']).dt.date
        out['VWAP'] = calculate_vwap(h, l, c, v, dates)
    return out


def _add_rvol(out, ind, close_col):
    """Mean- and median-based relative volume. Deps: Volume."""
    v = out['Volume']
    out['RVOL'] = calculate_rvol(v, ind.rvol_period)
    # Phase 0.7.x — median-based RVOL for the `rvol_above_recent` gate
    # (robust to outlier-volume bars vs. the mean-based RVOL above).
    out['RVol_Recent_20'] = calculate_rvol_recent(v, ind.rvol_period)
    return out


def _add_obv(out, ind, close_col):
    """On-balance volume. Deps: close_col, Volume."""
    c = out[close_col]
    v = out['Volume']
    out['OBV'] = calculate_obv(c, v)
    return out


def _add_stochrsi(out, ind, close_col):
    """Stochastic RSI %K / %D. Deps: ind.rsi_col (run _add_rsi first)."""
    out['StochRSI_K'], out['StochRSI_D'] = calculate_stoch_rsi(
        out[ind.rsi_col], ind.stoch_rsi_period, ind.stoch_rsi_k_period, ind.stoch_rsi_d_period,
    )
    return out


def _add_bollinger(out, ind, close_col):
    """Bollinger bands + width + %B. Deps: close_col."""
    c = out[close_col]
    out['BB_Upper'], out['BB_Middle'], out['BB_Lower'] = calculate_bollinger_bands(
        c, ind.bb_period, ind.bb_std_mult,
    )
    out['BB_Width'] = out['BB_Upper'] - out['BB_Lower']
    bb_range = out['BB_Upper'] - out['BB_Lower']
    out['BB_Pct'] = (c - out['BB_Lower']) / bb_range.where(bb_range > 0, np.nan)
    return out


def _add_macd(out, ind, close_col):
    """MACD line / signal / histogram. Deps: close_col."""
    c = out[close_col]
    out['MACD'], out['MACD_Signal'], out['MACD_Histogram'] = calculate_macd(
        c, ind.macd_fast, ind.macd_slow, ind.macd_signal,
    )
    return out


def _add_consecutive(out, ind, close_col):
    """Price-change % + consecutive up/down move counts. Deps: close_col."""
    c = out[close_col]
    price_change = c.pct_change() * 100.0
    out['Price_Change'] = price_change
    out['Consecutive_Up'], out['Consecutive_Down'] = calculate_consecutive_moves(
        price_change, ind.consecutive_periods,
    )
    out['Consecutive_Up_5'], out['Consecutive_Down_5'] = calculate_consecutive_moves(
        price_change, ind.consecutive_relaxed_window,
    )
    return out


def _add_price_levels(out, ind, close_col):
    """Price-vs-EMA/VWAP %-distances + daily-range metrics.

    Deps: close_col, High, Low, EMA{fast}/EMA{mid} (run _add_emas first),
    VWAP (run _add_vwap first; VWAP-distance is Time-gated via VWAP presence).
    """
    c = out[close_col]
    h = out['High']
    l = out['Low']
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
    # Same values under the canonical snake_case names the SQL writer
    # maps to `market_data_daily.high_low_spread{,_pct}`. Pre-2026-05-27,
    # only Daily_Range[_Pct] existed in indicator output and the snake_case
    # schema columns shipped all-NaN.
    out['high_low_spread'] = out['Daily_Range']
    out['high_low_spread_pct'] = out['Daily_Range_Pct']

    # Annualised historical volatility (single source of truth — pre-fix
    # each writer recomputed `volatility_20d` separately, and the 5-day
    # variant was simply missing). The snake_case key matches the SQL
    # column so the standard writer loop persists it without renaming.
    returns = c.pct_change()
    for p in ind.volatility_periods:
        out[f'volatility_{p}d'] = returns.rolling(p).std() * np.sqrt(252)
    return out


def _add_orb(out, ind, close_col):
    """Opening Range Breakout columns (~39). Deps: High, Low, close_col, Time.

    Time-gated: produces no ORB columns when 'Time' is absent."""
    if 'Time' in out.columns:
        c = out[close_col]
        h = out['High']
        l = out['Low']
        orb_result = calculate_all_orb(
            pd.to_datetime(out['Time']), h, l, c,
            orb_windows=ind.orb_windows,
        )
        out = pd.concat([out, orb_result], axis=1)
    return out


def _add_promoted_regime(out, ind, close_col):
    """Volatility-regime / momentum-velocity features.

    Promoted 2026-05-31 from the combo-mining measure-first study: each was a
    top permutation-importance driver of the forward regime (BIG move) and/or
    the next Strat candle, out-of-sample, across IWM/SPY/QQQ. All are
    stationary (slopes / ATR-normalised distances / ratios) and derive only
    from columns already computed by earlier blocks, so live (signal_monitor)
    and research (strat_data_builder) share one definition.

    Deps: close_col, ind.atr_col (_add_atr), EMA{fast}/EMA{mid} (_add_emas),
    VWAP (_add_vwap, Time-gated), BB_Width (_add_bollinger), RSI9+RSI14
    (_add_rsi). Time-gated for Mins_Since_Open.
    """
    c = out[close_col]
    ema_fast_p = ind.ema_fast_period
    ema_mid_p = ind.ema_mid_period
    atr_col = ind.atr_col
    atr = out[atr_col] if atr_col in out.columns else None

    def _norm(num, den):
        return num / den.where(den.abs() > 0, np.nan)

    # Realized short-horizon volatility — rolling std of 1-bar log returns.
    logret = np.log(c).diff()
    out['Realized_Vol_Short'] = logret.rolling(
        ind.realized_vol_window, min_periods=ind.realized_vol_window).std()

    # Minutes since the 09:30 open (intraday clock; NaN-safe without Time).
    if 'Time' in out.columns:
        _ts = pd.to_datetime(out['Time'])
        out['Mins_Since_Open'] = (
            _ts.dt.hour * 60 + _ts.dt.minute - (9 * 60 + 30)).astype(float)

    if atr is not None:
        # ATR-normalised distances (stationary twins of the %-based Price_vs_*).
        if f'EMA{ema_fast_p}' in out.columns:
            out['Price_vs_EMA9_ATR'] = _norm(c - out[f'EMA{ema_fast_p}'], atr)
        if f'EMA{ema_mid_p}' in out.columns:
            out['Price_vs_EMA20_ATR'] = _norm(c - out[f'EMA{ema_mid_p}'], atr)
        if 'VWAP' in out.columns:
            out['Price_vs_VWAP_ATR'] = _norm(c - out['VWAP'], atr)
        # Trend separation, vol-normalised.
        if f'EMA{ema_fast_p}' in out.columns and f'EMA{ema_mid_p}' in out.columns:
            out['EMA_Spread_ATR'] = _norm(
                out[f'EMA{ema_fast_p}'] - out[f'EMA{ema_mid_p}'], atr)
        # Momentum velocity — n-bar change in EMA9, ATR-normalised.
        if f'EMA{ema_fast_p}' in out.columns:
            out['EMA9_Slope'] = _norm(
                out[f'EMA{ema_fast_p}'].diff(ind.ema_slope_lookback), atr)

    # Bollinger compression — BB_Width vs its own rolling median.
    if 'BB_Width' in out.columns:
        bw = out['BB_Width']
        out['BB_Squeeze'] = _norm(
            bw, bw.rolling(ind.bb_squeeze_window,
                           min_periods=ind.bb_squeeze_window).median())

    # RSI fast-vs-slow divergence.
    if 'RSI9' in out.columns and 'RSI14' in out.columns:
        out['RSI_Divergence'] = out['RSI9'] - out['RSI14']

    return out


def _add_magnitude(out, ind, close_col):
    """Magnitude-engine volatility-expansion features (migrated 2026-06-01).

    These were hand-rolled inline in gcp/research/magnitude_engine/mag_dataset.py
    (``_add_phase1_features``), duplicating math the engine then could not share.
    Folded into the single indicator spine so the magnitude engine consumes the
    SAME definitions as regime/strat (CLAUDE.md "one source of truth for math").

    Session-aware: every rolling window is grouped by the intraday session date
    so it never crosses the overnight gap. Requires a 'Time' column to derive
    the session key; without 'Time' the block is skipped (these features are
    intraday-only and meaningless on daily bars). Deps: High, Low, close_col,
    BB_Upper/BB_Lower (_add_bollinger). All Rule-3.7 NaN-safe — no fabricated 0.

    Note: the inline ``atr5_atr20_ratio`` is intentionally NOT reproduced here.
    It was ATR5/ATR20 with mixed smoothing built atop the removed
    ``_compute_atr20`` workaround; the canonical ``ATR_Expansion`` (ATR5/ATR20,
    Wilder, from _add_atr/_add_promoted_regime) is the single-source equivalent
    and the magnitude engine reads that instead.
    """
    if 'Time' not in out.columns:
        return out

    h = out['High']
    l = out['Low']
    c = out[close_col]
    sess = pd.to_datetime(out['Time']).dt.date
    prev_c = c.groupby(sess).shift(1)

    def _safe_div(num, den):
        return num / den.where(den.abs() > 0, np.nan)

    # BB20 bandwidth: (upper - lower) / close. Uses the spine's Bollinger bands.
    if 'BB_Upper' in out.columns and 'BB_Lower' in out.columns:
        out['BB20_Bandwidth'] = _safe_div(out['BB_Upper'] - out['BB_Lower'], c)

    # 15-bar realized-vol z-score: rv15 = std of log returns over 15 bars;
    # z = (rv15 - rolling_mean_60(rv15)) / rolling_std_60(rv15). Session-grouped.
    logret = np.log(_safe_div(c, prev_c))
    rv15 = logret.groupby(sess).rolling(ind.mag_rv_window).std().reset_index(level=0, drop=True)
    rv_mu = rv15.groupby(sess).rolling(ind.mag_rv_z_window).mean().reset_index(level=0, drop=True)
    rv_sd = rv15.groupby(sess).rolling(ind.mag_rv_z_window).std().reset_index(level=0, drop=True)
    out['Realized_Vol_Z'] = _safe_div(rv15 - rv_mu, rv_sd)

    # Range expansion: current bar range / mean of prior-N bar ranges (session).
    rng = h - l
    avg_prior = (rng.groupby(sess).shift(1)
                    .groupby(sess).rolling(ind.mag_range_expansion_window).mean()
                    .reset_index(level=0, drop=True))
    out['Range_Expansion_Ratio'] = _safe_div(rng, avg_prior)

    # Cumulative intraday range so far / prior session's full range. cummax/
    # cummin are within-session (groupby preserves the original index); the
    # prior session's full range is mapped back per row via the session key.
    cum_hi = h.groupby(sess).cummax()
    cum_lo = l.groupby(sess).cummin()
    cumrange = cum_hi - cum_lo
    daily_range = h.groupby(sess).max() - l.groupby(sess).min()   # indexed by session
    prev_daily = daily_range.shift(1)                              # prior session's range
    prev_daily_aligned = pd.Series(sess.map(prev_daily).to_numpy(), index=out.index)
    out['Intraday_Range_vs_PrevDay'] = _safe_div(cumrange, prev_daily_aligned)

    return out


def _resolve_config(indicator_config):
    if indicator_config is None:
        from lib.config import IndicatorConfig
        return IndicatorConfig()
    return indicator_config


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

    This is a thin composition over the ``_add_*`` block helpers, called in
    dependency order. The 89-column output is byte-identical to the historical
    inline implementation (~25 callers + an in-flight backfill depend on it).

    Parameters
    ----------
    indicator_config : IndicatorConfig, optional
        All indicator periods and parameters. Uses defaults if None.
    """
    ind = _resolve_config(indicator_config)
    out = df.copy()
    out = _add_atr(out, ind, close_col)
    out = _add_rsi(out, ind, close_col)
    out = _add_emas(out, ind, close_col)
    out = _add_smas(out, ind, close_col)
    out = _add_vwap(out, ind, close_col)
    out = _add_rvol(out, ind, close_col)
    out = _add_obv(out, ind, close_col)
    out = _add_stochrsi(out, ind, close_col)
    out = _add_bollinger(out, ind, close_col)
    out = _add_macd(out, ind, close_col)
    out = _add_consecutive(out, ind, close_col)
    out = _add_price_levels(out, ind, close_col)
    out = _add_orb(out, ind, close_col)
    out = _add_promoted_regime(out, ind, close_col)
    out = _add_magnitude(out, ind, close_col)
    return out


# ---------------------------------------------------------------------------
# Capability tiers — lean indicator subsets for latency-sensitive consumers
# ---------------------------------------------------------------------------
# The live signal monitor and the premarket brief each read only ~12-20 of the
# 89 add_all_indicators columns, yet historically paid for the full suite
# (incl. the ~39 ORB columns + the promoted-regime block). The functions below
# run ONLY the blocks each capability needs, with byte-identical per-block
# arithmetic — verified 0.0 max-abs-diff vs add_all_indicators on the shared
# columns in tests/test_indicators.py. Research / nightly paths keep calling
# add_all_indicators unchanged.
#
# FEATURE_GROUPS is the authoritative output-column list per capability. It is
# the contract the parity test pins; if a consumer starts reading a new column,
# add the producing block to the tier AND the column here.


def _signal_columns(ind) -> List[str]:
    ema_fast_p, ema_mid_p = ind.ema_fast_period, ind.ema_mid_period
    return [
        ind.atr_col, 'ATR_Expansion',
        ind.rsi_col, ind.rsi_fast_col, 'RSI_Thrust_3',
        *[f'EMA{p}' for p in ind.ema_periods],
        'VWAP',
        'RVOL', 'RVol_Recent_20',
        'OBV',
        'StochRSI_K', 'StochRSI_D',
        'MACD', 'MACD_Signal', 'MACD_Histogram',
        'Price_Change', 'Consecutive_Up', 'Consecutive_Down',
        'Consecutive_Up_5', 'Consecutive_Down_5',
        f'Price_vs_EMA{ema_fast_p}', f'Price_vs_EMA{ema_mid_p}', 'Price_vs_VWAP',
        'Daily_Range', 'Daily_Range_Pct', 'Close_vs_Range',
    ]


def _brief_columns(ind) -> List[str]:
    ema_fast_p, ema_mid_p = ind.ema_fast_period, ind.ema_mid_period
    return [
        ind.atr_col, 'ATR_Expansion',
        ind.rsi_col, ind.rsi_fast_col, 'RSI_Thrust_3',
        *[f'EMA{p}' for p in ind.ema_periods],
        *[f'SMA{p}' for p in ind.sma_periods],
        'VWAP',
        'StochRSI_K', 'StochRSI_D',
        'BB_Upper', 'BB_Middle', 'BB_Lower', 'BB_Width', 'BB_Pct',
        'MACD', 'MACD_Signal', 'MACD_Histogram',
        'Price_Change', 'Consecutive_Up', 'Consecutive_Down',
        'Consecutive_Up_5', 'Consecutive_Down_5',
        # Price levels — the brief's check_call/put_conditions score on
        # Price_vs_VWAP, so the VWAP + price-levels blocks must run to stay
        # byte-identical to add_all_indicators (incl. the daily-bar VWAP
        # recompute-overwrite on Cloud-SQL daily frames). See test_brief_*.
        f'Price_vs_EMA{ema_fast_p}', f'Price_vs_EMA{ema_mid_p}', 'Price_vs_VWAP',
        'Daily_Range', 'Daily_Range_Pct', 'Close_vs_Range',
    ]


# Magnitude-engine volatility-expansion features (intraday-only, Time-gated).
# Migrated from mag_dataset._add_phase1_features 2026-06-01. The magnitude
# engine reads these from the spine plus the shared ATR_Expansion / volatility
# columns rather than recomputing them inline.
_MAGNITUDE_EXACT = [
    'BB20_Bandwidth', 'Realized_Vol_Z',
    'Range_Expansion_Ratio', 'Intraday_Range_vs_PrevDay',
]


# Stationary leak-safe feature set for the research regime model. Mirrors
# lib.combo_mining._STATIONARY_EXACT (minus MACD_Hist_Slope, which is a
# combo_mining candidate feature not produced by add_all_indicators).
_REGIME_EXACT = [
    'RSI14', 'RSI9', 'RSI_Thrust_3', 'StochRSI_K', 'StochRSI_D', 'MACD_Histogram',
    'ATR_Expansion', 'BB_Pct', 'BB_Width',
    'RVOL', 'RVol_Recent_20',
    'Price_Change', 'Close_vs_Range', 'Daily_Range_Pct',
    'Consecutive_Up', 'Consecutive_Down', 'Consecutive_Up_5', 'Consecutive_Down_5',
    'Price_vs_VWAP', 'Price_vs_EMA9', 'Price_vs_EMA20',
    'EMA9_Slope', 'Mins_Since_Open', 'Price_vs_EMA9_ATR', 'Price_vs_EMA20_ATR',
    'Price_vs_VWAP_ATR', 'EMA_Spread_ATR', 'BB_Squeeze', 'Realized_Vol_Short',
    'RSI_Divergence',
]


def _all_indicator_columns(ind) -> List[str]:
    """Every column add_all_indicators emits beyond the OHLCV/Time source set."""
    cols = (_signal_columns(ind) + _brief_columns(ind) + [
        'RSI_Divergence', 'Realized_Vol_Short', 'Mins_Since_Open',
        'Price_vs_EMA9_ATR', 'Price_vs_EMA20_ATR', 'Price_vs_VWAP_ATR',
        'EMA_Spread_ATR', 'EMA9_Slope', 'BB_Squeeze',
    ] + list(_MAGNITUDE_EXACT))
    # ORB columns for every configured window.
    for w in ind.orb_windows:
        lab = w['label']
        for ref in ['High', 'Low', 'Range', 'Mid']:
            cols.append(f'ORB_{lab}_{ref}')
        for ref in ['High', 'Low', 'Mid']:
            cols.append(f'ORB_{lab}_{ref}_Pct')
        for ref in ['Broke_High', 'Broke_Low', 'Within_Range', 'Trend', 'Distance']:
            cols.append(f'ORB_{lab}_{ref}')
    # de-dup preserving order
    seen, ordered = set(), []
    for c in cols:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def _feature_groups() -> Dict[str, List[str]]:
    """Build FEATURE_GROUPS from the default IndicatorConfig.

    Computed at import with the default config; periods rarely change and the
    membership is the authoritative contract pinned by the parity test.
    """
    from lib.config import IndicatorConfig
    ind = IndicatorConfig()
    return {
        'signal': _signal_columns(ind),
        'brief': _brief_columns(ind),
        'regime': list(_REGIME_EXACT),
        'strat': list(_REGIME_EXACT),
        # Magnitude = the stationary regime/strat set + the migrated
        # volatility-expansion features. ATR_Expansion is already in the
        # regime set and is the single-source replacement for the old inline
        # atr5_atr20_ratio.
        'magnitude': list(_REGIME_EXACT) + list(_MAGNITUDE_EXACT),
    }


FEATURE_GROUPS: Dict[str, List[str]] = _feature_groups()


def add_signal_indicators(
    df: pd.DataFrame,
    close_col: str = 'Close',
    indicator_config=None,
) -> pd.DataFrame:
    """Lean indicator set for the live signal monitor.

    Runs ONLY the blocks the live strategies (+ Discord embed) read: ATR, RSI,
    EMAs, VWAP, RVOL, OBV, StochRSI, MACD, consecutive moves, and price levels.
    Skips the heavy SMA / Bollinger / ORB (~39 cols) / promoted-regime blocks.

    Per-block arithmetic is byte-identical to add_all_indicators on the shared
    columns (FEATURE_GROUPS['signal']). Time guards for VWAP are preserved.
    """
    ind = _resolve_config(indicator_config)
    out = df.copy()
    out = _add_atr(out, ind, close_col)
    out = _add_rsi(out, ind, close_col)
    out = _add_emas(out, ind, close_col)
    out = _add_vwap(out, ind, close_col)
    out = _add_rvol(out, ind, close_col)
    out = _add_obv(out, ind, close_col)
    out = _add_stochrsi(out, ind, close_col)
    out = _add_macd(out, ind, close_col)
    out = _add_consecutive(out, ind, close_col)
    out = _add_price_levels(out, ind, close_col)
    return out


def add_brief_indicators(
    df: pd.DataFrame,
    close_col: str = 'Close',
    indicator_config=None,
) -> pd.DataFrame:
    """Lean indicator set for the premarket brief.

    Runs the blocks the brief reads: ATR, RSI, EMAs, SMAs, VWAP, StochRSI,
    Bollinger, MACD, consecutive moves, and price levels. The price-levels block
    is required because the brief's check_call/put_conditions score on
    ``Price_vs_VWAP``; VWAP must run first so that distance is computed (and, on
    Cloud-SQL daily frames carrying a pre-existing ``price_vs_vwap`` column, the
    daily-bar VWAP recompute overwrites it exactly as add_all_indicators did).
    Skips only RVOL / OBV / ORB (~39 cols) / promoted-regime — none are read by
    the brief. Per-block arithmetic is byte-identical to add_all_indicators on
    the shared columns (FEATURE_GROUPS['brief']).
    """
    ind = _resolve_config(indicator_config)
    out = df.copy()
    out = _add_atr(out, ind, close_col)
    out = _add_rsi(out, ind, close_col)
    out = _add_emas(out, ind, close_col)
    out = _add_smas(out, ind, close_col)
    out = _add_vwap(out, ind, close_col)
    out = _add_stochrsi(out, ind, close_col)
    out = _add_bollinger(out, ind, close_col)
    out = _add_macd(out, ind, close_col)
    out = _add_consecutive(out, ind, close_col)
    out = _add_price_levels(out, ind, close_col)
    return out


def add_regime_indicators(
    df: pd.DataFrame,
    close_col: str = 'Close',
    indicator_config=None,
) -> pd.DataFrame:
    """Indicator set for the research regime model (near-full).

    Provided for API symmetry. The regime model consumes the stationary
    feature set (FEATURE_GROUPS['regime']), which spans the promoted-regime
    block; producing it requires nearly every block, so this delegates to
    add_all_indicators (research path — latency is not the constraint).
    """
    return add_all_indicators(df, close_col=close_col, indicator_config=indicator_config)


def add_strat_indicators(
    df: pd.DataFrame,
    close_col: str = 'Close',
    indicator_config=None,
) -> pd.DataFrame:
    """Indicator set for the strat next-bar model (near-full).

    Provided for API symmetry; see add_regime_indicators. Research path.
    """
    return add_all_indicators(df, close_col=close_col, indicator_config=indicator_config)


def add_magnitude_indicators(
    df: pd.DataFrame,
    close_col: str = 'Close',
    indicator_config=None,
) -> pd.DataFrame:
    """Indicator set for the research magnitude engine (near-full).

    Produces the stationary regime/strat features PLUS the migrated
    volatility-expansion block (FEATURE_GROUPS['magnitude']). The magnitude
    engine previously hand-rolled these inline (mag_dataset._add_phase1_features
    + a local atr_20 workaround); it now consumes them from this single spine.
    Delegates to add_all_indicators (research path — latency is not a
    constraint and the magnitude block is Time-gated/intraday-only).
    """
    return add_all_indicators(df, close_col=close_col, indicator_config=indicator_config)


def select_features(df: pd.DataFrame, capability: str) -> pd.DataFrame:
    """Return the subset of `df` columns that belong to `capability`.

    Tolerant of Time-gated absences (e.g. VWAP/ORB when there is no Time
    column) — only columns actually present are returned, never KeyError.
    """
    if capability not in FEATURE_GROUPS:
        raise KeyError(
            f"unknown capability {capability!r}; "
            f"known: {sorted(FEATURE_GROUPS)}"
        )
    cols = [c for c in FEATURE_GROUPS[capability] if c in df.columns]
    return df[cols]
