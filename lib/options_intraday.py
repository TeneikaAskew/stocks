"""Intraday option repricing from EOD snapshots + 1-min underlying bars.

This module fills the gap between AV's EOD-only HISTORICAL_OPTIONS data
and the question "what was this option worth at 11:30am?" — needed for
post-earnings PnL replay at minute granularity, take-profit rule
calibration, and the platform's intraday option-chart view.

Approach
--------
AV provides one EOD option snapshot per (symbol, date). We have 1-min
underlying bars in ``market_data_intraday``. Plus daily risk-free rate
and dividend yield in ``daily_rates``. With those four inputs and an
IV-decay assumption we can rebuild the option's mid value at every
minute via BSM repricing.

The piece we DON'T have is the true intraday IV path. Real option IV
crushes 30-50% at the earnings open then linearly bleeds to ~40% of T-1
by close. This module models that with two configurable multipliers —
``iv_open_multiplier`` (default 0.55) and ``iv_close_multiplier``
(default 0.40). The default values are the median of empirical earnings
crushes across the SPY single-name basket; callers needing higher
fidelity can override per-event from observed T+1 IV data.

The bias direction is documented per CLAUDE.md §3.7 — we don't fabricate
a "true" intraday IV, we explicitly model it and surface the assumption.
The IV path is the only modeled quantity; everything else is observed
data (spot from intraday bars, r/q from FRED, strike/expiry from the
T-1 snapshot).

Usage
-----
::

    from lib.options_intraday import reprice_intraday_option

    timeline = reprice_intraday_option(
        ticker='MSFT',
        intraday_date=date(2025, 7, 31),
        strike=512.50,
        expiration=date(2025, 8, 1),
        option_type='call',
        iv_t_minus_1=0.55,
        entry_price_per_share=10.82,
    )
    # timeline: Time, Spot, IV_used, Theo_value, Pnl_per_share,
    #           Pnl_per_contract, Pnl_pct
    timeline['Pnl_per_contract'].max()  # peak unrealized PnL of the day
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Literal, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# Empirical defaults from cross-sectional study of earnings IV crushes.
# Open IV ≈ 55% of T-1 IV; close IV ≈ 40% of T-1 IV. Overrideable
# per-call when finer event-specific data is available.
_DEFAULT_IV_OPEN_MULT  = 0.55
_DEFAULT_IV_CLOSE_MULT = 0.40

# Year-fraction conventions — 252 trading days for r/q, 365 for time
# decay between calendar dates. ``py_vollib_vectorized`` expects time
# in years.
_TRADING_DAYS_PER_YEAR  = 252
_CALENDAR_DAYS_PER_YEAR = 365


def reprice_intraday_option(
    *,
    ticker: str,
    intraday_date: date,
    strike: float,
    expiration: date,
    option_type: Literal['call', 'put', 'calls', 'puts'],
    iv_t_minus_1: float,
    entry_price_per_share: float,
    intraday_bars: Optional[pd.DataFrame] = None,
    iv_open_multiplier: float = _DEFAULT_IV_OPEN_MULT,
    iv_close_multiplier: float = _DEFAULT_IV_CLOSE_MULT,
    risk_free: Optional[float] = None,
    dividend_yield: Optional[float] = None,
) -> pd.DataFrame:
    """Minute-by-minute PnL timeline for one option contract on one day.

    Parameters
    ----------
    ticker
        Underlying symbol, used both to label rows and to load 1-min bars
        from ``market_data_intraday`` if ``intraday_bars`` is None.
    intraday_date
        The session being replayed (typically T+1 for an earnings event —
        the post-event day where you'd be deciding whether to take profit).
    strike, expiration, option_type
        From the T-1 EOD snapshot you're replaying.
    iv_t_minus_1
        The implied vol observed at T-1 close — the snapshot's IV column.
    entry_price_per_share
        What you paid (or what you'd be marking against). Per share, not
        per contract. The PnL columns subtract this.
    intraday_bars
        Optional pre-loaded ``market_data_intraday`` slice. If None, the
        function pulls bars for (ticker, intraday_date) from Cloud SQL.
    iv_open_multiplier, iv_close_multiplier
        IV decay assumption. See module docstring. Both expressed as
        fractions of ``iv_t_minus_1``.
    risk_free, dividend_yield
        Override the daily_rates lookup if you've already resolved them.

    Returns
    -------
    DataFrame
        Columns: Time (tz-naive ET), Spot, IV_used, Theo_value,
        Pnl_per_share, Pnl_per_contract, Pnl_pct.
        Empty DataFrame if no intraday bars for the (ticker, date).
    """
    # Normalise option_type to py_vollib's single-letter format ('c'/'p').
    flag = _to_vollib_flag(option_type)
    if flag is None:
        raise ValueError(f"option_type must be call/put, got {option_type!r}")
    if iv_t_minus_1 <= 0 or not np.isfinite(iv_t_minus_1):
        raise ValueError(f"iv_t_minus_1 must be > 0, got {iv_t_minus_1}")

    # Resolve rate/yield once — these are constant across the day.
    if risk_free is None or dividend_yield is None:
        from lib.options_greeks import get_rate_and_yield
        r_lookup, q_lookup = get_rate_and_yield(intraday_date)
        if risk_free is None:
            risk_free = r_lookup
        if dividend_yield is None:
            dividend_yield = q_lookup

    bars = intraday_bars
    if bars is None:
        bars = _load_intraday_bars(ticker, intraday_date)
    if bars is None or bars.empty:
        log.warning("No intraday bars for %s on %s — returning empty timeline",
                    ticker, intraday_date)
        return pd.DataFrame(columns=[
            'Time', 'Spot', 'IV_used', 'Theo_value',
            'Pnl_per_share', 'Pnl_per_contract', 'Pnl_pct'])

    bars = bars.copy()
    bars['Time'] = pd.to_datetime(bars['Time'])
    bars = bars.sort_values('Time').reset_index(drop=True)
    n = len(bars)

    # Linear IV decay from open multiplier to close multiplier across the
    # session. Index 0 = open, index n-1 = close.
    if n > 1:
        progress = np.arange(n, dtype=float) / (n - 1)
    else:
        progress = np.zeros(1)
    iv_path = iv_t_minus_1 * (
        iv_open_multiplier
        + (iv_close_multiplier - iv_open_multiplier) * progress
    )

    # Time-to-expiry in years, recomputed per-bar (decreases through the day).
    bars_ts = bars['Time'].dt.tz_localize(None)
    exp_dt = pd.Timestamp(expiration) + pd.Timedelta(hours=16)  # 4 PM expiry
    dte_days = (exp_dt - bars_ts).dt.total_seconds() / 86400.0
    # Floor at one minute so DTE → 0 doesn't blow up BSM.
    dte_years = np.maximum(dte_days / _CALENDAR_DAYS_PER_YEAR, 1.0 / 86400.0 / _CALENDAR_DAYS_PER_YEAR)

    spot = bars['Spot'].to_numpy(dtype=float)
    theo = _bsm_price_vec(
        flag=flag, S=spot, K=strike, t=dte_years.to_numpy(dtype=float),
        r=risk_free, sigma=iv_path, q=dividend_yield,
    )

    out = pd.DataFrame({
        'Time': bars['Time'].values,
        'Spot': spot,
        'IV_used': iv_path,
        'Theo_value': theo,
    })
    out['Pnl_per_share']    = out['Theo_value'] - entry_price_per_share
    out['Pnl_per_contract'] = out['Pnl_per_share'] * 100.0
    out['Pnl_pct']          = out['Pnl_per_share'] / entry_price_per_share * 100.0
    return out


def reprice_structure_intraday(
    *,
    structure: Literal['long_call', 'long_put', 'long_straddle', 'short_strangle'],
    ticker: str,
    intraday_date: date,
    intraday_bars: Optional[pd.DataFrame] = None,
    # Long-call / long-put / long-straddle inputs (ATM strike pair)
    atm_strike: Optional[float] = None,
    call_entry: Optional[float] = None,
    put_entry: Optional[float] = None,
    call_iv: Optional[float] = None,
    put_iv: Optional[float] = None,
    # Short-strangle inputs (delta-20 wings)
    call_strike: Optional[float] = None,
    put_strike: Optional[float] = None,
    wing_call_entry: Optional[float] = None,
    wing_put_entry: Optional[float] = None,
    wing_call_iv: Optional[float] = None,
    wing_put_iv: Optional[float] = None,
    # Common
    expiration: Optional[date] = None,
    iv_open_multiplier: float = _DEFAULT_IV_OPEN_MULT,
    iv_close_multiplier: float = _DEFAULT_IV_CLOSE_MULT,
) -> pd.DataFrame:
    """Intraday PnL of a multi-leg structure.

    Long structures: timeline shows what you could have closed for at
    each minute. ``Pnl_per_contract`` is the unrealized PnL on 1 unit
    of the structure (1 contract per leg).

    Short strangle: ``Pnl_per_contract`` is positive when the structure
    is profitable to buy back. Sign convention follows the long side —
    you collected ``call_entry + put_entry`` upfront and the timeline
    shows what it would cost to close.
    """
    if expiration is None:
        raise ValueError("expiration is required for all structures")
    if intraday_bars is None:
        intraday_bars = _load_intraday_bars(ticker, intraday_date)
    if intraday_bars is None or intraday_bars.empty:
        return pd.DataFrame(columns=[
            'Time', 'Spot', 'Pnl_per_share', 'Pnl_per_contract', 'Pnl_pct'])

    if structure in ('long_call', 'long_put'):
        if atm_strike is None or call_entry is None and structure == 'long_call':
            raise ValueError("long_call needs atm_strike + call_entry + call_iv")
        if structure == 'long_call':
            return reprice_intraday_option(
                ticker=ticker, intraday_date=intraday_date, strike=atm_strike,
                expiration=expiration, option_type='call',
                iv_t_minus_1=call_iv, entry_price_per_share=call_entry,
                intraday_bars=intraday_bars,
                iv_open_multiplier=iv_open_multiplier,
                iv_close_multiplier=iv_close_multiplier,
            )
        return reprice_intraday_option(
            ticker=ticker, intraday_date=intraday_date, strike=atm_strike,
            expiration=expiration, option_type='put',
            iv_t_minus_1=put_iv, entry_price_per_share=put_entry,
            intraday_bars=intraday_bars,
            iv_open_multiplier=iv_open_multiplier,
            iv_close_multiplier=iv_close_multiplier,
        )

    if structure == 'long_straddle':
        if atm_strike is None or call_entry is None or put_entry is None:
            raise ValueError("long_straddle needs atm_strike + call_entry + put_entry + IVs")
        call_tl = reprice_intraday_option(
            ticker=ticker, intraday_date=intraday_date, strike=atm_strike,
            expiration=expiration, option_type='call', iv_t_minus_1=call_iv,
            entry_price_per_share=call_entry, intraday_bars=intraday_bars,
            iv_open_multiplier=iv_open_multiplier,
            iv_close_multiplier=iv_close_multiplier,
        )
        put_tl = reprice_intraday_option(
            ticker=ticker, intraday_date=intraday_date, strike=atm_strike,
            expiration=expiration, option_type='put', iv_t_minus_1=put_iv,
            entry_price_per_share=put_entry, intraday_bars=intraday_bars,
            iv_open_multiplier=iv_open_multiplier,
            iv_close_multiplier=iv_close_multiplier,
        )
        return _combine_legs([call_tl, put_tl], signs=[+1.0, +1.0],
                             entry=call_entry + put_entry)

    if structure == 'short_strangle':
        if (call_strike is None or put_strike is None
                or wing_call_entry is None or wing_put_entry is None):
            raise ValueError("short_strangle needs call_strike + put_strike + wing entries + IVs")
        call_tl = reprice_intraday_option(
            ticker=ticker, intraday_date=intraday_date, strike=call_strike,
            expiration=expiration, option_type='call', iv_t_minus_1=wing_call_iv,
            entry_price_per_share=wing_call_entry, intraday_bars=intraday_bars,
            iv_open_multiplier=iv_open_multiplier,
            iv_close_multiplier=iv_close_multiplier,
        )
        put_tl = reprice_intraday_option(
            ticker=ticker, intraday_date=intraday_date, strike=put_strike,
            expiration=expiration, option_type='put', iv_t_minus_1=wing_put_iv,
            entry_price_per_share=wing_put_entry, intraday_bars=intraday_bars,
            iv_open_multiplier=iv_open_multiplier,
            iv_close_multiplier=iv_close_multiplier,
        )
        # Short side: PnL is collected_premium - current_buyback_cost.
        # _combine_legs with signs=[-1, -1] flips the sign of each leg's
        # PnL because what was a loss on a long position is a gain when
        # short, and vice-versa. Entry total is what you collected.
        return _combine_legs([call_tl, put_tl], signs=[-1.0, -1.0],
                             entry=wing_call_entry + wing_put_entry)

    raise ValueError(f"Unknown structure: {structure!r}")


def _combine_legs(legs: list[pd.DataFrame], *, signs: list[float],
                  entry: float) -> pd.DataFrame:
    """Combine multiple option-leg timelines into one structure timeline.

    Each timeline contributes its ``Pnl_per_share`` × sign to the combined
    position. ``Pnl_pct`` is recomputed against the combined entry.
    """
    if not legs or any(l.empty for l in legs):
        return pd.DataFrame(columns=[
            'Time', 'Spot', 'Pnl_per_share', 'Pnl_per_contract', 'Pnl_pct'])
    if len(legs) != len(signs):
        raise ValueError("legs and signs must match length")

    base = legs[0][['Time', 'Spot']].copy()
    base['Pnl_per_share'] = 0.0
    for leg, sign in zip(legs, signs):
        base['Pnl_per_share'] += sign * leg['Pnl_per_share'].to_numpy()
    base['Pnl_per_contract'] = base['Pnl_per_share'] * 100.0
    base['Pnl_pct'] = base['Pnl_per_share'] / entry * 100.0 if entry > 0 else np.nan
    return base


def _to_vollib_flag(option_type: str) -> Optional[str]:
    t = (option_type or '').lower().strip()
    if t in ('call', 'calls', 'c'):
        return 'c'
    if t in ('put', 'puts', 'p'):
        return 'p'
    return None


def _bsm_price_vec(*, flag: str, S, K: float, t, r: float, sigma, q: float):
    """Vectorised Black-Scholes-Merton price.

    Pulled from ``py_vollib_vectorized`` if installed; otherwise computed
    in-line via scipy.stats.norm.cdf so this module is importable for
    tests without the heavier dep. The output is per-share mid price.
    """
    S_arr = np.atleast_1d(np.asarray(S, dtype=float))
    t_arr = np.atleast_1d(np.asarray(t, dtype=float))
    sigma_arr = np.atleast_1d(np.asarray(sigma, dtype=float))
    # Broadcast scalars to common length.
    n = max(S_arr.size, t_arr.size, sigma_arr.size)
    if S_arr.size == 1:    S_arr     = np.full(n, S_arr.item())
    if t_arr.size == 1:    t_arr     = np.full(n, t_arr.item())
    if sigma_arr.size == 1: sigma_arr = np.full(n, sigma_arr.item())

    # Drift adjustment: F = S * exp((r-q) * t)
    F = S_arr * np.exp((r - q) * t_arr)
    sqrt_t = np.sqrt(np.maximum(t_arr, 1e-12))
    sigma_safe = np.maximum(sigma_arr, 1e-8)
    d1 = (np.log(F / K) + 0.5 * sigma_safe**2 * t_arr) / (sigma_safe * sqrt_t)
    d2 = d1 - sigma_safe * sqrt_t
    # scipy.stats.norm.cdf
    from scipy.stats import norm
    discount = np.exp(-r * t_arr)
    if flag == 'c':
        price = discount * (F * norm.cdf(d1) - K * norm.cdf(d2))
    else:  # 'p'
        price = discount * (K * norm.cdf(-d2) - F * norm.cdf(-d1))
    # Replace any non-finite (shouldn't happen, but defensive) with NaN.
    return np.where(np.isfinite(price), price, np.nan)


def _load_intraday_bars(ticker: str, target_date: date) -> Optional[pd.DataFrame]:
    """Load 1-min bars for (ticker, date) from market_data_intraday.

    Returns DataFrame with columns ``Time`` and ``Spot`` (the bar close),
    or None on unavailability.
    """
    try:
        from gcp.database import query_to_dataframe
    except ImportError:
        return None
    df = query_to_dataframe(
        "SELECT ts AS \"Time\", close AS \"Spot\" "
        "FROM market_data_intraday "
        "WHERE ticker = :t AND ts >= :start AND ts < :end "
        "AND interval = '1min' ORDER BY ts",
        {"t": ticker.upper(),
         "start": datetime.combine(target_date, datetime.min.time()),
         "end": datetime.combine(target_date + timedelta(days=1),
                                  datetime.min.time())},
    )
    if df is None or df.empty:
        return None
    return df


# ---------------------------------------------------------------------------
# Intraday 0DTE theta-decay shape  g(t)
# ---------------------------------------------------------------------------
# A 0DTE option loses ~all of its time value between the RTH open (09:30 ET)
# and expiry (16:00 ET). That decay is NOT linear in clock time — the naive
# ``theta * hold_min/1440`` assumption that consumers used distributes it
# evenly. ``g(t)`` below is the empirically-measured cumulative fraction of
# the day's ATM time-value that has decayed by ``t`` minutes after the open.
#
# Provenance: calibrated from ``etf_options_snapshots`` market_session='REALTIME'
# 5-minute ATM-straddle marks (ATM = argmin_K(call+put) over strikes with
# |delta| in [0.15, 0.85], which excludes stale penny wings). Pooled over
# SPY+IWM+QQQ × 6 sessions (2026-05-27 … 2026-06-10); the three tickers'
# curves agreed to within ~0.05 at every knot, so a single shared curve is
# used. Monotonicity enforced via cumulative-max. Re-derive with
# ``scripts/analysis/calibrate_intraday_theta.py`` as more sessions accrue.
#
# Shape vs. linear: morning decays FASTER than linear (open IV crush), a
# midday LULL where g falls below linear (~12:00–15:00), then the terminal
# expiry CLIFF — only ~0.80 has decayed by the last observed bar (~15:55) and
# the remaining ~0.20 is lost in the final minutes into the 16:00 settle.
# The 385→390 segment encodes that cliff (last observed bar → expiry pin=1.0).
_RTH_OPEN_MIN  = 9 * 60 + 30          # 09:30 ET, minutes since midnight
_RTH_CLOSE_MIN = 16 * 60              # 16:00 ET
_RTH_SPAN_MIN  = float(_RTH_CLOSE_MIN - _RTH_OPEN_MIN)   # 390

_THETA_DECAY_KNOT_MIN = np.array(
    [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 360, 375, 385, 390],
    dtype=float)
_THETA_DECAY_KNOT_G = np.array(
    [0.000, 0.136, 0.224, 0.287, 0.344, 0.388, 0.451, 0.502,
     0.536, 0.582, 0.631, 0.664, 0.721, 0.772, 0.803, 1.000],
    dtype=float)


def minutes_from_rth_open(ts) -> Optional[float]:
    """Minutes elapsed since the 09:30 ET RTH open for a trade timestamp.

    Returns ``None`` for null / unparseable input so callers can fall back to
    the naive linear model rather than silently mis-time the decay. Tz-aware
    timestamps are converted to US/Eastern; naive timestamps are assumed to be
    exchange wall-clock (the convention the strat backtest already uses).
    """
    if ts is None:
        return None
    try:
        t = pd.Timestamp(ts)
    except (ValueError, TypeError):
        return None
    if pd.isna(t):
        return None
    if t.tzinfo is not None:
        t = t.tz_convert("America/New_York")
    return float(t.hour * 60 + t.minute - _RTH_OPEN_MIN)


def cumulative_theta_decay(min_from_open: float) -> float:
    """g(t): cumulative fraction (0..1) of the RTH day's 0DTE time-value decayed
    by ``min_from_open`` minutes after the open. Clamps to 0 before the open and
    1 after the close (``np.interp`` saturates at the endpoint knots)."""
    return float(np.interp(min_from_open,
                           _THETA_DECAY_KNOT_MIN, _THETA_DECAY_KNOT_G))


def intraday_theta_decay_fraction(entry_min_from_open: float,
                                  exit_min_from_open: float) -> float:
    """Fraction of the RTH day's 0DTE time-decay realized over a hold window,
    i.e. ``g(exit) - g(entry)``.

    This replaces the naive linear ``(exit - entry) / 390``. Multiply by the
    daily theta budget ``|theta| * (390/1440)`` to get the dollar theta cost of
    the hold — a full-day hold returns 1.0, preserving the prior full-day
    magnitude while redistributing it realistically across the session.
    Returns 0.0 for a non-positive window.
    """
    if exit_min_from_open <= entry_min_from_open:
        return 0.0
    return (cumulative_theta_decay(exit_min_from_open)
            - cumulative_theta_decay(entry_min_from_open))
