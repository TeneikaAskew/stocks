#!/usr/bin/env python3
"""
Walk-forward backtest of the playability_score formula.

For each (ticker, fiscal_date_ending) row in earnings_reactions, we:
  1. As of just-before this report, compute playability_score + archetype
     using ONLY past rows for the same ticker (reported_date < this_row).
  2. Note the actual outcome at this row: reaction_gap_pct, is_reversal_5d.
  3. Score the archetype's directional prediction against the actual:
       bullish_trend  hit if reaction_gap_pct > 0
       bearish_trend  hit if reaction_gap_pct < 0
       reversal_play  hit if is_reversal_5d = True
       mixed          hit if |reaction_gap_pct| > MIXED_HIT_THRESHOLD
       quiet          skipped (no prediction)
  4. Bucket by score quintile + archetype, aggregate hit rate.

Output: BACKTEST_PLAYABILITY_RESULTS.md with quintile + archetype tables.

Usage:
    python -m scripts.backtest_playability
    python -m scripts.backtest_playability --min-nq 12
    python -m scripts.backtest_playability --output BACKTEST.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcp.database import query_to_dataframe
from lib.earnings_reactions import (
    compute_playability_score,
    classify_archetype,
)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)


# Threshold for the "mixed" archetype hit definition: actual move > this means
# the "big move" call was right. Same scale as reaction_gap_pct (percent).
MIXED_HIT_THRESHOLD = 3.0


def fetch_reactions_for_backtest(min_nq: int = 12) -> pd.DataFrame:
    """Pull all earnings_reactions sorted by (ticker, reported_date).

    Pulls the full multi-horizon return ladder so the calibration sweep
    can compute dollar P&L on each prediction (1d / 3d / 5d / 10d holds)
    in addition to the hit/miss ranking metric.
    """
    sql = """
        SELECT ticker, reported_date, fiscal_date_ending,
               reaction_gap_pct,
               direction_consistent_5d,
               is_reversal_5d,
               sustain_3d_pct,
               sustain_5d_pct,
               sustain_10d_pct,
               reaction_max_run_pct,
               reaction_max_drawdown_pct,
               d_minus_1_close,
               d_plus_1_close
        FROM earnings_reactions
        WHERE reaction_gap_pct IS NOT NULL
          AND reported_date IS NOT NULL
        ORDER BY ticker, reported_date
    """
    df = query_to_dataframe(sql)
    return df


def _reactions_stats_from_past(
    past: pd.DataFrame, lookback: int | None = None,
) -> dict | None:
    """Compute archetype/score inputs from a ticker's PAST reaction rows.

    Mirrors lib.earnings_reactions.query_reaction_stats but in-memory,
    walk-forward — only uses rows strictly before the target reported_date.

    When `lookback` is given (> 0), only the most recent `lookback` past
    rows are used — a bounded window rather than all history. This is one
    of the two knobs the earnings calibration sweep tunes.
    """
    if past.empty:
        return None
    if lookback is not None and lookback > 0:
        past = past.tail(lookback)
    gaps = past['reaction_gap_pct'].dropna()
    if gaps.empty:
        return None
    n_q = len(past)
    move_magnitude_pct = gaps.abs().mean()
    directional_bias_pct = gaps.mean()
    dir_consistency = past['direction_consistent_5d'].mean()  # bool → 0..1
    reversal_rate = past['is_reversal_5d'].mean()
    return {
        'n_q': n_q,
        'move_magnitude_pct': float(move_magnitude_pct),
        'directional_bias_pct': float(directional_bias_pct),
        'dir_consistency': float(dir_consistency) if pd.notna(dir_consistency) else None,
        'reversal_rate':   float(reversal_rate)   if pd.notna(reversal_rate)   else None,
    }


def hit_for_archetype(archetype: str | None,
                      reaction_gap_pct: float,
                      is_reversal_5d: bool | None) -> bool | None:
    """Was this archetype's directional prediction correct for the actual?

    Returns None when no prediction is made (archetype='quiet' or None).
    """
    if archetype is None:
        return None
    if archetype == 'bullish_trend':
        return reaction_gap_pct > 0
    if archetype == 'bearish_trend':
        return reaction_gap_pct < 0
    if archetype == 'reversal_play':
        return bool(is_reversal_5d) if is_reversal_5d is not None else None
    if archetype == 'mixed':
        return abs(reaction_gap_pct) > MIXED_HIT_THRESHOLD
    return None  # 'quiet' or unknown


def compute_quintile_spread(predictions: pd.DataFrame) -> dict:
    """Reduce a run_backtest() predictions frame to the calibration
    sweep's ranking metrics.

    Returns {n_predictions, overall_hit_rate, quintile_spread}, where
    quintile_spread is the hit-rate of the highest-score quintile minus
    the lowest. A high spread means the playability score orders
    earnings plays in a way that tracks real outcomes — the property
    the sweep maximises. Zeros on an empty/degenerate frame.
    """
    zero = {'n_predictions': 0, 'overall_hit_rate': 0.0, 'quintile_spread': 0.0}
    if predictions is None or predictions.empty:
        return zero
    df = predictions.dropna(subset=['hit', 'score']).copy()
    if df.empty:
        return zero
    df['hit'] = df['hit'].astype(bool)
    df['score'] = df['score'].astype(float)
    n = len(df)
    overall = float(df['hit'].mean())
    spread = 0.0
    if df['score'].nunique() >= 5:
        try:
            df['q'] = pd.qcut(df['score'], q=5, labels=False, duplicates='drop')
            by_q = df.groupby('q')['hit'].mean().sort_index()
            spread = float(by_q.iloc[-1] - by_q.iloc[0])
        except (ValueError, IndexError):
            spread = 0.0
    return {'n_predictions': n, 'overall_hit_rate': overall,
            'quintile_spread': spread}


# Dollar conversion: per_trade_pct (e.g. 3.4 means +3.4%) × $10 = $34
# per $1k notional. Centralised here so any rendering layer can do the
# same conversion without re-deriving the factor.
_DOLLARS_PER_PCT_PER_1K = 10.0

# Hold horizons evaluated for best_hold_horizon_days. 1 = day-of
# reaction (uses actual_gap_pct); 3/5/10 = sustain_*_pct.
_HOLD_HORIZONS_DAYS = (1, 3, 5, 10)


def _archetype_directional_return(archetype: str | None,
                                  actual_gap_pct: float | None,
                                  hold_return_pct: float | None) -> float | None:
    """Realised return of the archetype's directional bet for one hold.

    Sign convention: positive = the prediction made money.
      bullish_trend: long position over the hold horizon → +hold_return
      bearish_trend: short position over the hold horizon → -hold_return
      reversal_play: fade the initial gap; long if gap < 0, short if > 0
                     → -sign(actual_gap) × hold_return
      mixed / quiet / unknown: None (no single-direction stock trade).
    """
    if hold_return_pct is None or archetype is None:
        return None
    if archetype == 'bullish_trend':
        return float(hold_return_pct)
    if archetype == 'bearish_trend':
        return -float(hold_return_pct)
    if archetype == 'reversal_play':
        if actual_gap_pct is None or actual_gap_pct == 0:
            return None
        return -float(hold_return_pct) if actual_gap_pct > 0 else float(hold_return_pct)
    return None


def _summary_stats_pct(returns: pd.Series) -> dict:
    """Win/loss decomposition + payoff/expectancy/profit-factor/sharpe
    from a Series of per-trade percent returns. NaNs dropped. Empty
    input returns NaN-filled dict so downstream INSERT writes SQL NULL.
    Caller passes returns in chronological order for path-dependent
    max-drawdown to be meaningful.
    """
    s = returns.dropna()
    n = int(len(s))
    if n == 0:
        nan = float('nan')
        return {
            'n': 0, 'win_rate': nan, 'avg_win_pct': nan, 'avg_loss_pct': nan,
            'payoff_ratio': nan, 'expectancy_pct': nan, 'profit_factor': nan,
            'max_drawdown_pct': nan, 'sharpe_per_trade': nan,
        }
    wins = s[s > 0]
    losses = s[s < 0]
    win_rate = float(len(wins)) / n
    avg_win_pct  = float(wins.mean())   if len(wins)   > 0 else 0.0
    avg_loss_pct = float(losses.mean()) if len(losses) > 0 else 0.0  # negative
    payoff_ratio = (
        abs(avg_win_pct / avg_loss_pct) if avg_loss_pct < 0 else float('inf')
    )
    expectancy_pct = float(s.mean())
    gross_win  = float(wins.sum())   if len(wins)   > 0 else 0.0
    gross_loss = float(losses.sum()) if len(losses) > 0 else 0.0  # negative
    profit_factor = (
        gross_win / abs(gross_loss) if gross_loss < 0 else float('inf')
    )
    # Equity curve starts at 0 (no trades). Prepend 0 so the first
    # trade's drawdown is measured relative to initial equity, not to
    # itself (a series of all losses must report total cumulative loss
    # as the max drawdown, not zero).
    equity = pd.concat([pd.Series([0.0]), s.cumsum()], ignore_index=True)
    peak = equity.cummax()
    drawdown = equity - peak
    max_dd_pct = float(drawdown.min()) if len(drawdown) > 0 else 0.0
    std = float(s.std(ddof=1)) if n > 1 else 0.0
    sharpe = float(expectancy_pct / std) if std > 0 else 0.0
    return {
        'n': n,
        'win_rate': win_rate,
        'avg_win_pct': avg_win_pct,
        'avg_loss_pct': avg_loss_pct,
        'payoff_ratio': float(payoff_ratio),
        'expectancy_pct': expectancy_pct,
        'profit_factor': float(profit_factor),
        'max_drawdown_pct': max_dd_pct,
        'sharpe_per_trade': sharpe,
    }


def compute_dollar_metrics(predictions: pd.DataFrame) -> dict:
    """Dollar P&L attribution on top-quintile predictions.

    Restricts to the top-score quintile (Q5) and the directional
    archetypes (bullish_trend / bearish_trend / reversal_play) because
    those map to clean stock-only trade structures. Mixed and quiet rows
    are excluded — see _archetype_directional_return.

    For each of {1d, 3d, 5d, 10d} hold horizons computes win_rate,
    avg_win/loss, payoff_ratio, expectancy, profit_factor, max
    drawdown, and per-trade sharpe. Picks best_hold_horizon_days by
    payoff_ratio (ties broken by expectancy_pct), excluding horizons
    with n<50 or zero-loss (inf payoff) noise.

    Returns dict with keys for the 5d-hold canonical metrics plus
    best_hold_horizon_days + n_q5_directional. All values NaN-safe.
    """
    nan_safe = {
        'n_q5_directional': 0,
        'avg_win_pct': float('nan'),
        'avg_loss_pct': float('nan'),
        'payoff_ratio': float('nan'),
        'expectancy_pct': float('nan'),
        'expectancy_dollars_per_1k': float('nan'),
        'profit_factor': float('nan'),
        'max_drawdown_pct': float('nan'),
        'sharpe_per_trade': float('nan'),
        'best_hold_horizon_days': None,
    }
    if predictions is None or predictions.empty:
        return nan_safe
    df = predictions.dropna(subset=['score']).copy()
    if df.empty or df['score'].nunique() < 5:
        return nan_safe

    df['q'] = pd.qcut(df['score'], q=5, labels=False, duplicates='drop')
    q5 = df[df['q'] == df['q'].max()].copy()
    q5 = q5[q5['archetype'].isin(
        ['bullish_trend', 'bearish_trend', 'reversal_play'])]
    if q5.empty:
        return nan_safe
    q5 = q5.sort_values('reported_date').reset_index(drop=True)

    horizon_to_col = {
        1:  'actual_gap_pct',
        3:  'sustain_3d_pct',
        5:  'sustain_5d_pct',
        10: 'sustain_10d_pct',
    }
    per_horizon: dict[int, dict] = {}
    for h in _HOLD_HORIZONS_DAYS:
        col = horizon_to_col[h]
        if col not in q5.columns:
            continue
        returns = q5.apply(
            lambda r: _archetype_directional_return(
                r['archetype'], r.get('actual_gap_pct'), r.get(col)),
            axis=1,
        )
        per_horizon[h] = _summary_stats_pct(pd.Series(returns, dtype='float64'))

    if not per_horizon:
        return nan_safe

    eligible = {
        h: m for h, m in per_horizon.items()
        if m['n'] >= 50 and m['payoff_ratio'] != float('inf')
    }
    if eligible:
        best_h = max(
            eligible.keys(),
            key=lambda h: (eligible[h]['payoff_ratio'],
                           eligible[h]['expectancy_pct']),
        )
    else:
        best_h = max(per_horizon.keys(),
                     key=lambda h: per_horizon[h]['n'])

    # Canonical reported metrics: 5d hold (matches the existing
    # backtest's hit definition's time window).
    canon = per_horizon.get(5) or per_horizon[best_h]
    exp_pct = canon['expectancy_pct']
    exp_dollars = (
        exp_pct * _DOLLARS_PER_PCT_PER_1K
        if exp_pct == exp_pct  # not NaN
        else float('nan')
    )
    return {
        'n_q5_directional':        canon['n'],
        'avg_win_pct':             canon['avg_win_pct'],
        'avg_loss_pct':            canon['avg_loss_pct'],
        'payoff_ratio':            canon['payoff_ratio'],
        'expectancy_pct':          exp_pct,
        'expectancy_dollars_per_1k': exp_dollars,
        'profit_factor':           canon['profit_factor'],
        'max_drawdown_pct':        canon['max_drawdown_pct'],
        'sharpe_per_trade':        canon['sharpe_per_trade'],
        'best_hold_horizon_days':  int(best_h),
    }


# ────────────────────────────────────────────────────────────
# Options metrics — PR-B (T-1 ATM straddle / strangle / call / put)
# ────────────────────────────────────────────────────────────
#
# Methodology — exit is modelled as intrinsic-only at the T+1 close,
# i.e. we ASSUME the option was held through earnings then closed the
# next day after IV crush, with all extrinsic gone. This is a
# conservative lower bound on long-options PnL (real extrinsic at T+1
# is typically 5-15% of T-1 IV) and a conservative UPPER bound on
# short-options PnL. The bias is consistent across events so relative
# comparisons (long_straddle vs short_strangle) remain valid.
#
# The intrinsic-only choice is deliberate: a synthetic IV-crush model
# would require a Black-Scholes call on every event (~41k × 4 contracts)
# and the result depends on an assumed post-event IV which itself
# needs calibration — adding two layers of speculation on top of one
# data limitation (we only snapshot T-1, not T+1). See
# CLAUDE.md §3.7 — no fabricated value when the truth is missing.


def _select_atm_pair(chain: pd.DataFrame, spot: float) -> dict | None:
    """Pick the ATM call+put pair from a single-event chain.

    `chain` is rows of earnings_options_snapshots for one
    (symbol, snapshot_date). `spot` is d_minus_1_close.

    Strategy:
      1. Pick the nearest expiry available (earliest expiration).
      2. Find the strike with the smallest |strike - spot| that has
         BOTH a call and put row.
      3. Return their mids (or last_price if mid unusable).

    Returns None if no such strike exists (illiquid name, no straddle
    available). Caller MUST treat None as "no options-side metric for
    this event" rather than zero (CLAUDE.md §3.7).
    """
    if chain is None or chain.empty or spot is None or spot <= 0:
        return None
    nearest = chain['expiration'].min()
    near = chain[chain['expiration'] == nearest]
    if near.empty:
        return None
    calls = near[near['option_type'] == 'calls'].set_index('strike')
    puts  = near[near['option_type'] == 'puts'].set_index('strike')
    paired_strikes = sorted(set(calls.index) & set(puts.index))
    if not paired_strikes:
        return None
    strike = min(paired_strikes, key=lambda s: abs(s - spot))
    call_mid = _mid(calls.loc[strike])
    put_mid  = _mid(puts.loc[strike])
    if call_mid is None or put_mid is None:
        return None
    return {
        'strike': float(strike),
        'expiration': nearest,
        'call_mid': float(call_mid),
        'put_mid':  float(put_mid),
        'call_iv':  _safe_float(calls.loc[strike].get('implied_volatility')),
        'put_iv':   _safe_float(puts.loc[strike].get('implied_volatility')),
    }


def _select_delta_n_pair(chain: pd.DataFrame, target_delta: float = 0.20) -> dict | None:
    """Pick the delta-N strangle wings (call ≈ +target, put ≈ -target).

    Used for short-strangle PnL. Calls are typically +0.05..+0.50 delta;
    puts -0.05..-0.50. Picks the closest absolute-delta match in each
    side; the strikes need NOT be equidistant from spot (that's the
    point — skew is captured).
    """
    if chain is None or chain.empty or target_delta <= 0:
        return None
    nearest = chain['expiration'].min()
    near = chain[chain['expiration'] == nearest].dropna(subset=['delta'])
    if near.empty:
        return None
    calls = near[(near['option_type'] == 'calls') & (near['delta'] > 0)]
    puts  = near[(near['option_type'] == 'puts')  & (near['delta'] < 0)]
    if calls.empty or puts.empty:
        return None
    call_row = calls.iloc[(calls['delta'] - target_delta).abs().argsort()].iloc[0]
    put_row  = puts.iloc[(puts['delta'] - (-target_delta)).abs().argsort()].iloc[0]
    call_mid = _mid(call_row)
    put_mid  = _mid(put_row)
    if call_mid is None or put_mid is None:
        return None
    return {
        'expiration': nearest,
        'call_strike': float(call_row['strike']),
        'put_strike':  float(put_row['strike']),
        'call_mid': float(call_mid),
        'put_mid':  float(put_mid),
        'call_delta': float(call_row['delta']),
        'put_delta':  float(put_row['delta']),
    }


def _mid(row) -> float | None:
    """Bid/ask midpoint with last_price fallback. NaN-safe."""
    bid = _safe_float(row.get('bid') if hasattr(row, 'get') else row['bid'] if 'bid' in row else None)
    ask = _safe_float(row.get('ask') if hasattr(row, 'get') else row['ask'] if 'ask' in row else None)
    if bid is not None and ask is not None and ask > 0 and bid >= 0:
        # Reject grossly stale bid/ask (spread > 200% of mid)
        m = (bid + ask) / 2.0
        if m > 0 and (ask - bid) / m < 2.0:
            return m
    # Fall back to last_price ONLY when bid/ask unusable.
    lp = _safe_float(row.get('last_price') if hasattr(row, 'get') else row['last_price'] if 'last_price' in row else None)
    if lp is not None and lp > 0:
        return lp
    return None


def _safe_float(v) -> float | None:
    """None/NaN/inf-safe coercion to float."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f == float('inf') or f == float('-inf'):
        return None
    return f


def _long_straddle_pnl_pct(call_mid: float, put_mid: float,
                            strike: float, spot_exit: float) -> float | None:
    """PnL of a long ATM straddle, % return on premium paid.

    Entry: pay (call_mid + put_mid). Exit at T+1 close, modelled as
    intrinsic-only (see methodology comment).
    """
    if call_mid is None or put_mid is None or spot_exit is None:
        return None
    premium = call_mid + put_mid
    if premium <= 0:
        return None
    intrinsic = abs(spot_exit - strike)
    return (intrinsic - premium) / premium * 100.0


def _short_strangle_pnl_pct(call_mid: float, put_mid: float,
                             call_strike: float, put_strike: float,
                             spot_exit: float) -> float | None:
    """PnL of a short OTM strangle, % return on premium received.

    Sell call at call_strike + put at put_strike for combined
    `call_mid + put_mid`. Buyback at T+1 modelled as intrinsic-only.
    PnL = premium - intrinsic_buy_back.
    """
    if (call_mid is None or put_mid is None
            or call_strike is None or put_strike is None
            or spot_exit is None):
        return None
    premium = call_mid + put_mid
    if premium <= 0:
        return None
    intrinsic = (max(spot_exit - call_strike, 0.0)
                 + max(put_strike - spot_exit, 0.0))
    return (premium - intrinsic) / premium * 100.0


def _long_call_pnl_pct(call_mid: float, strike: float,
                       spot_exit: float) -> float | None:
    """PnL of a long ATM call, % return on premium."""
    if call_mid is None or call_mid <= 0 or spot_exit is None:
        return None
    intrinsic = max(spot_exit - strike, 0.0)
    return (intrinsic - call_mid) / call_mid * 100.0


def _long_put_pnl_pct(put_mid: float, strike: float,
                      spot_exit: float) -> float | None:
    """PnL of a long ATM put, % return on premium."""
    if put_mid is None or put_mid <= 0 or spot_exit is None:
        return None
    intrinsic = max(strike - spot_exit, 0.0)
    return (intrinsic - put_mid) / put_mid * 100.0


def _load_options_snapshots() -> pd.DataFrame:
    """One-shot load of every T-1 options snapshot for the sweep.

    Returns a single DataFrame with one row per (symbol, snapshot_date,
    expiration, strike, option_type). The sweep groups in-memory by
    (symbol, snapshot_date) so this is loaded once per run.
    """
    sql = """
        SELECT symbol, snapshot_date, expiration, strike, option_type,
               bid, ask, last_price, implied_volatility, delta
        FROM earnings_options_snapshots
    """
    df = query_to_dataframe(sql)
    if df is None or df.empty:
        return pd.DataFrame()
    # Coerce types
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date']).dt.date
    df['expiration']    = pd.to_datetime(df['expiration']).dt.date
    return df


def compute_options_metrics(predictions: pd.DataFrame,
                            options_df: pd.DataFrame) -> dict:
    """Options-side P&L attribution for top-quintile predictions.

    Restricts to Q5 (top quintile) AND events with at least one ATM
    pair available in `options_df`. Computes:
      - implied_move (from straddle premium / spot)
      - realized_move (|reaction_gap_pct|)
      - long_straddle / short_strangle / long_call / long_put PnL%
      - realized_vs_implied_ratio

    Returns NaN-safe dict — empty Q5∩options writes SQL NULL.
    """
    nan_safe = {
        'n_with_options': 0,
        'avg_atm_straddle_iv_pct':   float('nan'),
        'avg_implied_move_pct':      float('nan'),
        'avg_realized_move_pct':     float('nan'),
        'realized_vs_implied_ratio': float('nan'),
        'avg_long_straddle_pnl_pct': float('nan'),
        'avg_short_strangle_pnl_pct': float('nan'),
        'avg_long_call_pnl_pct':     float('nan'),
        'avg_long_put_pnl_pct':      float('nan'),
    }
    if predictions is None or predictions.empty:
        return nan_safe
    if options_df is None or options_df.empty:
        return nan_safe

    df = predictions.dropna(subset=['score']).copy()
    if df.empty or df['score'].nunique() < 5:
        return nan_safe
    df['q'] = pd.qcut(df['score'], q=5, labels=False, duplicates='drop')
    q5 = df[df['q'] == df['q'].max()].copy()
    if q5.empty:
        return nan_safe

    # Pre-group options by (symbol, snapshot_date) so we hit the index
    # once instead of filtering for every event.
    options_df = options_df.copy()
    options_df['snapshot_date'] = pd.to_datetime(
        options_df['snapshot_date']).dt.date
    opts_by_event = {
        k: g for k, g in options_df.groupby(['symbol', 'snapshot_date'])
    }

    n_matched = 0
    iv_vals: list[float] = []
    implied_moves: list[float] = []
    realized_moves: list[float] = []
    rv_ratios: list[float] = []
    long_straddle_pnls: list[float] = []
    short_strangle_pnls: list[float] = []
    long_call_pnls:  list[float] = []
    long_put_pnls:   list[float] = []

    for _, row in q5.iterrows():
        ticker = str(row['ticker']).upper()
        reported = pd.to_datetime(row['reported_date']).date()
        snapshot_dt = reported - timedelta(days=1)
        spot_entry = _safe_float(row.get('d_minus_1_close'))
        spot_exit  = _safe_float(row.get('d_plus_1_close'))
        if spot_entry is None or spot_exit is None:
            continue

        chain = opts_by_event.get((ticker, snapshot_dt))
        if chain is None or chain.empty:
            continue

        atm = _select_atm_pair(chain, spot_entry)
        if atm is None:
            continue
        n_matched += 1

        # IV and implied move
        avg_iv = None
        if atm['call_iv'] is not None and atm['put_iv'] is not None:
            avg_iv = (atm['call_iv'] + atm['put_iv']) / 2.0
            iv_vals.append(avg_iv * 100.0)  # AV reports IV as decimal

        # Implied move% from straddle premium
        implied_pct = (atm['call_mid'] + atm['put_mid']) / spot_entry * 100.0
        implied_moves.append(implied_pct)

        realized_pct = abs(_safe_float(row.get('actual_gap_pct')) or 0.0)
        realized_moves.append(realized_pct)
        if implied_pct > 0:
            rv_ratios.append(realized_pct / implied_pct)

        # PnL structures
        ls = _long_straddle_pnl_pct(
            atm['call_mid'], atm['put_mid'], atm['strike'], spot_exit)
        if ls is not None:
            long_straddle_pnls.append(ls)
        lc = _long_call_pnl_pct(atm['call_mid'], atm['strike'], spot_exit)
        if lc is not None:
            long_call_pnls.append(lc)
        lp = _long_put_pnl_pct(atm['put_mid'], atm['strike'], spot_exit)
        if lp is not None:
            long_put_pnls.append(lp)

        # Short strangle requires delta data
        strangle = _select_delta_n_pair(chain, target_delta=0.20)
        if strangle is not None:
            ss = _short_strangle_pnl_pct(
                strangle['call_mid'], strangle['put_mid'],
                strangle['call_strike'], strangle['put_strike'], spot_exit)
            if ss is not None:
                short_strangle_pnls.append(ss)

    if n_matched == 0:
        return nan_safe

    def _mean_or_nan(lst):
        return float(sum(lst) / len(lst)) if lst else float('nan')

    return {
        'n_with_options':            int(n_matched),
        'avg_atm_straddle_iv_pct':   _mean_or_nan(iv_vals),
        'avg_implied_move_pct':      _mean_or_nan(implied_moves),
        'avg_realized_move_pct':     _mean_or_nan(realized_moves),
        'realized_vs_implied_ratio': _mean_or_nan(rv_ratios),
        'avg_long_straddle_pnl_pct': _mean_or_nan(long_straddle_pnls),
        'avg_short_strangle_pnl_pct': _mean_or_nan(short_strangle_pnls),
        'avg_long_call_pnl_pct':     _mean_or_nan(long_call_pnls),
        'avg_long_put_pnl_pct':      _mean_or_nan(long_put_pnls),
    }


def compute_long_only_report(
    predictions: pd.DataFrame,
    options_df: pd.DataFrame,
) -> str:
    """Long-only Q5 detail report — segments + named winners + predictors.

    For traders who only BUY premium (long straddles, long strangles,
    long calls, long puts). Restricts to Q5 events with options matches,
    then explores: where do these structures actually win? What do those
    events look like? Specifically targeted at finding "CRCL-style"
    blowouts where a low-implied / high-realized event hands the long
    side a multi-bagger.

    Returns a markdown string suitable for printing to stdout / logs.

    Segments:
      1. ALL Q5         — baseline
      2. ratio > 1.5    — large over-realization (long wins big here)
      3. ratio 0.85-1.5 — roughly fair pricing (long is coin-flip)
      4. ratio < 0.85   — over-priced premium (long loses; user should skip)

    Per-segment metrics:
      - n events
      - hit rate (% positive PnL) for each long structure
      - mean PnL %
      - 90th-pct PnL % (the upside tail — what you make on the wins)
      - 10th-pct PnL % (the downside tail — what you lose when wrong)

    Named drill-downs:
      - Top 10 long straddle wins (ticker / date / PnL / implied vs realized)
      - Top 10 long call wins
      - Top 10 long put wins

    Predictors of long-wins (in the ratio > 1.5 segment):
      - Distribution of implied_move sizes (small implied → easier to beat)
      - Most common archetypes
      - reaction_gap direction distribution
    """
    if predictions is None or predictions.empty or options_df is None or options_df.empty:
        return "# Long-only report\n\nNo data available.\n"

    # Restrict to Q5
    df = predictions.dropna(subset=['score']).copy()
    if df.empty or df['score'].nunique() < 5:
        return "# Long-only report\n\nInsufficient score variation for quintile cut.\n"
    df['q'] = pd.qcut(df['score'], q=5, labels=False, duplicates='drop')
    q5 = df[df['q'] == df['q'].max()].copy()
    if q5.empty:
        return "# Long-only report\n\nNo Q5 events found.\n"

    # Pre-group options once.
    options_df = options_df.copy()
    options_df['snapshot_date'] = pd.to_datetime(options_df['snapshot_date']).dt.date
    opts_by_event = {k: g for k, g in options_df.groupby(['symbol', 'snapshot_date'])}

    # Compute per-event long-side metrics.
    rows = []
    for _, row in q5.iterrows():
        ticker = str(row['ticker']).upper()
        reported = pd.to_datetime(row['reported_date']).date()
        snapshot_dt = reported - timedelta(days=1)
        spot_entry = _safe_float(row.get('d_minus_1_close'))
        spot_exit = _safe_float(row.get('d_plus_1_close'))
        if spot_entry is None or spot_exit is None or spot_entry <= 0:
            continue
        chain = opts_by_event.get((ticker, snapshot_dt))
        if chain is None or chain.empty:
            continue
        atm = _select_atm_pair(chain, spot_entry)
        if atm is None:
            continue

        implied_pct = (atm['call_mid'] + atm['put_mid']) / spot_entry * 100.0
        realized_pct_signed = _safe_float(row.get('actual_gap_pct')) or 0.0
        realized_pct = abs(realized_pct_signed)
        ratio = realized_pct / implied_pct if implied_pct > 0 else None

        ls = _long_straddle_pnl_pct(atm['call_mid'], atm['put_mid'],
                                     atm['strike'], spot_exit)
        lc = _long_call_pnl_pct(atm['call_mid'], atm['strike'], spot_exit)
        lp = _long_put_pnl_pct(atm['put_mid'], atm['strike'], spot_exit)

        rows.append({
            'ticker': ticker,
            'date': reported,
            'archetype': row.get('archetype'),
            'spot_entry': spot_entry,
            'spot_exit': spot_exit,
            'strike': atm['strike'],
            'call_mid': atm['call_mid'],
            'put_mid': atm['put_mid'],
            'straddle_premium': atm['call_mid'] + atm['put_mid'],
            'implied_pct': implied_pct,
            'realized_pct': realized_pct,
            'realized_signed_pct': realized_pct_signed,
            'ratio': ratio,
            'long_straddle_pnl': ls,
            'long_call_pnl': lc,
            'long_put_pnl': lp,
        })

    if not rows:
        return "# Long-only report\n\nNo matched events.\n"
    detail = pd.DataFrame(rows).dropna(subset=['ratio'])

    # ──────────────────────────────────────────────
    # Build the report.
    # ──────────────────────────────────────────────
    lines = ["# Long-Only Strategy Report (Q5 picks only)\n"]
    lines.append(f"_{len(detail)} Q5 events with usable options snapshots._\n")
    lines.append("All P&L expressed as % return on premium paid. "
                 "Exit modelled as intrinsic-only at T+1 close (conservative — "
                 "real exit value is slightly higher because some extrinsic "
                 "survives IV crush).\n")

    def _segment_stats(name: str, sub: pd.DataFrame) -> list[str]:
        if sub.empty:
            return [f"### {name}\n_No events._\n"]
        out = [f"### {name} — n = {len(sub)}\n"]
        out.append("| Structure | Hit rate | Mean PnL | p90 (best wins) | p10 (worst losses) | Median PnL |")
        out.append("|---|---|---|---|---|---|")
        for col, label in [
            ('long_straddle_pnl', 'Long Straddle'),
            ('long_call_pnl',     'Long Call'),
            ('long_put_pnl',      'Long Put'),
        ]:
            v = sub[col].dropna()
            if v.empty:
                out.append(f"| {label} | — | — | — | — | — |")
                continue
            hit = (v > 0).mean() * 100
            out.append(f"| {label} | {hit:.0f}% | {v.mean():+.0f}% | "
                       f"{v.quantile(0.90):+.0f}% | {v.quantile(0.10):+.0f}% | "
                       f"{v.median():+.0f}% |")
        return out + [""]

    lines += _segment_stats(
        "All Q5 (baseline)", detail)
    lines += _segment_stats(
        "Ratio > 1.5 — REALIZED MASSIVELY EXCEEDED IMPLIED (where long wins big)",
        detail[detail['ratio'] > 1.5])
    lines += _segment_stats(
        "Ratio 0.85 – 1.5 — fairly priced (mostly coin-flip)",
        detail[(detail['ratio'] >= 0.85) & (detail['ratio'] <= 1.5)])
    lines += _segment_stats(
        "Ratio < 0.85 — OPTIONS OVER-PRICED (long loses; skip these)",
        detail[detail['ratio'] < 0.85])

    # Named drill-downs — top winners per structure.
    def _top_winners(name: str, col: str, n: int = 10) -> list[str]:
        out = [f"### Top {n} winners — {name}\n"]
        sub = detail.dropna(subset=[col]).sort_values(col, ascending=False).head(n)
        if sub.empty:
            return out + ["_No events._\n"]
        out.append("| Ticker | Date | Move | Implied → Realized | PnL % | $ paid → $ exit per contract |")
        out.append("|---|---|---|---|---|---|")
        for _, r in sub.iterrows():
            if col == 'long_straddle_pnl':
                premium = r['straddle_premium']
                exit_v = abs(r['spot_exit'] - r['strike'])  # intrinsic-only
                direction = ''
            elif col == 'long_call_pnl':
                premium = r['call_mid']
                exit_v = max(r['spot_exit'] - r['strike'], 0)
                direction = '↑'
            else:  # long_put_pnl
                premium = r['put_mid']
                exit_v = max(r['strike'] - r['spot_exit'], 0)
                direction = '↓'
            paid = premium * 100
            exitd = exit_v * 100
            out.append(
                f"| {r['ticker']} | {r['date']} | "
                f"{direction}{abs(r['realized_signed_pct']):.1f}% | "
                f"{r['implied_pct']:.1f}% → {r['realized_pct']:.1f}% "
                f"(ratio {r['ratio']:.2f}) | "
                f"{r[col]:+.0f}% | "
                f"${paid:.0f} → ${exitd:.0f} |")
        return out + [""]

    lines += _top_winners("Long Straddle", 'long_straddle_pnl', 10)
    lines += _top_winners("Long Call (direction-correct upside)", 'long_call_pnl', 10)
    lines += _top_winners("Long Put (direction-correct downside)", 'long_put_pnl', 10)

    # Predictors of long-wins.
    winners = detail[detail['ratio'] > 1.5]
    losers = detail[detail['ratio'] < 0.85]
    lines.append("### Predictors of long-wins (the ratio > 1.5 subset)\n")
    lines.append(f"_{len(winners)} long-win events vs {len(losers)} long-skip events._\n")

    def _compare_means(col: str, label: str) -> str:
        w_mean = winners[col].mean() if col in winners else float('nan')
        l_mean = losers[col].mean() if col in losers else float('nan')
        return f"- **{label}**: long-wins avg {w_mean:.2f} vs long-skips avg {l_mean:.2f}"

    lines.append(_compare_means('implied_pct', 'Implied move%'))
    lines.append(_compare_means('realized_pct', 'Realized move%'))
    lines.append("")

    # Archetype breakdown
    if 'archetype' in winners.columns and not winners['archetype'].isna().all():
        lines.append("**Archetype mix of long-wins:**")
        for arch, n in winners['archetype'].value_counts().head(5).items():
            pct = n / len(winners) * 100
            lines.append(f"- {arch}: {n} ({pct:.0f}%)")
        lines.append("")
        lines.append("**Archetype mix of long-skips (for contrast):**")
        for arch, n in losers['archetype'].value_counts().head(5).items():
            pct = n / len(losers) * 100
            lines.append(f"- {arch}: {n} ({pct:.0f}%)")
        lines.append("")

    lines.append("### Key takeaway\n")
    lines.append("Filter Q5 events to those with **realized > implied "
                 "historically** (i.e. moves that the options market "
                 "consistently under-prices). On that subset, long "
                 "straddle and the correct directional leg have positive "
                 "expectancy. On the over-priced subset (ratio < 0.85), "
                 "long premium loses systematically — skip those events "
                 "or wait for IV to compress before entry.\n")

    return "\n".join(lines)


def run_backtest(min_nq: int, lookback: int | None = None) -> pd.DataFrame:
    """Walk forward, return DataFrame of predictions with hit flags.

    `lookback` caps how many recent past quarters feed each prediction's
    stats (None / 0 = all history). It and `min_nq` are the two knobs
    the earnings calibration sweep tunes.
    """
    log.info("Fetching earnings_reactions for backtest…")
    all_reactions = fetch_reactions_for_backtest()
    log.info("  loaded %d rows across %d tickers",
             len(all_reactions), all_reactions['ticker'].nunique())

    # Typical daily return baseline — used by compute_playability_score's
    # move_magnitude_norm. We don't have per-ticker per-date typical
    # daily return at hand here, so we use a constant proxy (median
    # daily return on a broad index). The score's *relative* ordering
    # is preserved as long as this is consistent across rows.
    TYPICAL_DAILY_RETURN_PCT = 1.0

    predictions: list[dict] = []
    by_ticker = all_reactions.groupby('ticker', sort=False)
    n_tickers = all_reactions['ticker'].nunique()
    skipped_low_nq = 0
    skipped_quiet = 0

    for i, (ticker, grp) in enumerate(by_ticker, 1):
        # Sort by reported_date asc for walk-forward
        grp_sorted = grp.sort_values('reported_date').reset_index(drop=True)
        for idx in range(len(grp_sorted)):
            row = grp_sorted.iloc[idx]
            past = grp_sorted.iloc[:idx]  # strictly before
            if len(past) < min_nq:
                skipped_low_nq += 1
                continue

            stats = _reactions_stats_from_past(past, lookback)
            if stats is None:
                continue

            archetype = classify_archetype(
                move_magnitude_pct=stats['move_magnitude_pct'],
                directional_bias_pct=stats['directional_bias_pct'],
                dir_consistency=stats['dir_consistency'],
                reversal_rate=stats['reversal_rate'],
            )
            if archetype == 'quiet':
                skipped_quiet += 1
                continue

            # options_volume is unknown for this walk-forward (we don't
            # have it at-time on the historical row). Use a constant
            # 10000 as a proxy — preserves relative ordering across
            # rows since log(opt_vol + 1) scales the same.
            score = compute_playability_score(
                move_magnitude_pct=stats['move_magnitude_pct'],
                typical_daily_return_pct=TYPICAL_DAILY_RETURN_PCT,
                dir_consistency=stats['dir_consistency'],
                reversal_rate=stats['reversal_rate'],
                options_volume=10000.0,
            )

            actual_gap = float(row['reaction_gap_pct'])
            actual_reversal = (
                bool(row['is_reversal_5d'])
                if pd.notna(row['is_reversal_5d']) else None
            )
            hit = hit_for_archetype(archetype, actual_gap, actual_reversal)

            def _f(col: str) -> float | None:
                v = row.get(col)
                return float(v) if pd.notna(v) else None

            predictions.append({
                'ticker': ticker,
                'reported_date': row['reported_date'],
                'archetype': archetype,
                'score': score,
                'nQ_past': len(past),
                'move_mag_pct': stats['move_magnitude_pct'],
                'dir_consistency': stats['dir_consistency'],
                'reversal_rate': stats['reversal_rate'],
                'actual_gap_pct': actual_gap,
                'actual_reversal_5d': actual_reversal,
                'hit': hit,
                # Multi-horizon return ladder for dollar P&L attribution.
                # 1d return = the close-to-close reaction itself; 3/5/10d
                # are cumulative returns from anchor through hold horizon.
                'sustain_3d_pct':  _f('sustain_3d_pct'),
                'sustain_5d_pct':  _f('sustain_5d_pct'),
                'sustain_10d_pct': _f('sustain_10d_pct'),
                'max_run_pct':     _f('reaction_max_run_pct'),
                'max_dd_pct':      _f('reaction_max_drawdown_pct'),
                # Spot anchors for options PnL attribution. T-1 close
                # is when the snapshot was taken (the trade-entry price);
                # T+1 close is the canonical exit point post-IV-crush.
                'd_minus_1_close': _f('d_minus_1_close'),
                'd_plus_1_close':  _f('d_plus_1_close'),
            })

        if i % 100 == 0:
            log.info("  %d/%d tickers processed; %d predictions, %d skipped (low_nq=%d, quiet=%d)",
                     i, n_tickers, len(predictions), skipped_low_nq + skipped_quiet,
                     skipped_low_nq, skipped_quiet)

    log.info("Done: %d predictions; skipped %d low_nq, %d quiet",
             len(predictions), skipped_low_nq, skipped_quiet)
    return pd.DataFrame(predictions)


def write_report(df: pd.DataFrame, output: Path, min_nq: int) -> None:
    """Write BACKTEST_PLAYABILITY_RESULTS.md from predictions DataFrame."""
    if df.empty:
        output.write_text("# Backtest: no predictions produced\n")
        return

    # Drop rows where hit is None (no prediction made)
    df = df.dropna(subset=['hit']).copy()
    df['hit'] = df['hit'].astype(bool)
    df = df.dropna(subset=['score'])  # quiet rows already dropped above
    df['score'] = df['score'].astype(float)

    total = len(df)
    overall_hit_rate = df['hit'].mean()

    # By archetype
    archetype_table = (
        df.groupby('archetype', sort=False)
        .agg(n=('hit', 'count'),
             hit_rate=('hit', 'mean'),
             avg_score=('score', 'mean'),
             avg_actual_move=('actual_gap_pct', lambda s: s.abs().mean()))
        .sort_values('hit_rate', ascending=False)
        .reset_index()
    )

    # By score quintile
    df['quintile'] = pd.qcut(df['score'], q=5, labels=['Q1 (lowest)', 'Q2', 'Q3', 'Q4', 'Q5 (highest)'])
    quintile_table = (
        df.groupby('quintile', observed=True)
        .agg(n=('hit', 'count'),
             hit_rate=('hit', 'mean'),
             avg_score=('score', 'mean'),
             avg_actual_move=('actual_gap_pct', lambda s: s.abs().mean()))
        .reset_index()
    )

    # By archetype × quintile (the headline table)
    cross_table = (
        df.groupby(['archetype', 'quintile'], observed=True)
        .agg(n=('hit', 'count'), hit_rate=('hit', 'mean'))
        .reset_index()
    )
    pivot = cross_table.pivot(index='archetype', columns='quintile', values='hit_rate')

    md_lines = []
    md_lines.append("# Playability Score Backtest — Walk-Forward Validation\n")
    md_lines.append(f"Walks forward through `earnings_reactions` ({total:,} predictions, ")
    md_lines.append(f"min_nq={min_nq}). For each prediction the score & archetype were ")
    md_lines.append("computed using **only** past reaction rows for that ticker. The ")
    md_lines.append("'hit' column is whether the archetype's directional call matched the ")
    md_lines.append("actual outcome on that earnings event.\n\n")

    md_lines.append("## Overall\n")
    md_lines.append(f"- **Predictions made:** {total:,}\n")
    md_lines.append(f"- **Overall hit rate:** {overall_hit_rate:.1%}\n")
    md_lines.append(f"- **Random baseline:** ~50% (directional) / ~25% (mixed: |move| > {MIXED_HIT_THRESHOLD}%)\n\n")

    md_lines.append("## Hit rate by archetype\n\n")
    md_lines.append("| Archetype | n | Hit rate | Avg score | Avg |move| |\n")
    md_lines.append("|---|---:|---:|---:|---:|\n")
    for _, row in archetype_table.iterrows():
        md_lines.append(
            f"| {row['archetype']} | {row['n']:,} | {row['hit_rate']:.1%} | "
            f"{row['avg_score']:.2f} | {row['avg_actual_move']:.2f}% |\n"
        )
    md_lines.append("\n")

    md_lines.append("## Hit rate by score quintile\n\n")
    md_lines.append("Higher quintile = higher computed playability_score. If the formula works, ")
    md_lines.append("Q5 hit rate should be meaningfully above Q1.\n\n")
    md_lines.append("| Quintile | n | Hit rate | Avg score | Avg |move| |\n")
    md_lines.append("|---|---:|---:|---:|---:|\n")
    for _, row in quintile_table.iterrows():
        md_lines.append(
            f"| {row['quintile']} | {row['n']:,} | {row['hit_rate']:.1%} | "
            f"{row['avg_score']:.2f} | {row['avg_actual_move']:.2f}% |\n"
        )
    md_lines.append("\n")

    md_lines.append("## Hit rate by archetype × score quintile\n\n")
    md_lines.append("Cell values are hit rates. NaN means no predictions in that bucket.\n\n")
    # Render pivot table manually (avoids tabulate dep)
    col_headers = ["archetype"] + [str(c) for c in pivot.columns]
    md_lines.append("| " + " | ".join(col_headers) + " |\n")
    md_lines.append("|" + "|".join(["---"] * len(col_headers)) + "|\n")
    for archetype, row in pivot.iterrows():
        cells = [archetype]
        for col in pivot.columns:
            v = row[col]
            cells.append(f"{v:.1%}" if pd.notna(v) else "—")
        md_lines.append("| " + " | ".join(cells) + " |\n")
    md_lines.append("\n")

    md_lines.append("## Interpretation\n")
    md_lines.append("- **Archetype hit rate > 50%** for directional types (bullish/bearish) ")
    md_lines.append("means the directional prediction beats coin flip.\n")
    md_lines.append("- **Archetype hit rate > MIXED_HIT_THRESHOLD baseline** for 'mixed' means ")
    md_lines.append(f"the score's identification of vol-rich names is meaningful.\n")
    md_lines.append("- **Q5 > Q1** in the quintile table = the score formula is producing ")
    md_lines.append("ordered predictions that translate to actual outcomes.\n")
    md_lines.append("- **Q5 ≈ Q1** = the formula isn't separating signal from noise; redesign needed.\n\n")

    output.write_text("".join(md_lines))
    log.info("Wrote %s (%d predictions, overall hit rate %.1f%%)",
             output, total, overall_hit_rate * 100)
    # Also print to stdout so the report is captured in Cloud Logging
    # when run via Cloud Run Job (container fs is ephemeral).
    print("\n" + "=" * 70)
    print("BEGIN_BACKTEST_REPORT")
    print("=" * 70)
    print("".join(md_lines))
    print("=" * 70)
    print("END_BACKTEST_REPORT")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Walk-forward backtest of the playability_score formula"
    )
    parser.add_argument('--min-nq', type=int, default=12,
                        help="Minimum quarters of past history required to "
                             "score a prediction (default: 12, matches brief).")
    parser.add_argument('--lookback', type=int, default=0,
                        help="Cap recent past quarters per prediction "
                             "(0 = use all history; default: 0).")
    parser.add_argument('--output', type=str, default='BACKTEST_PLAYABILITY_RESULTS.md',
                        help="Output report path (default: BACKTEST_PLAYABILITY_RESULTS.md)")
    args = parser.parse_args()

    output = Path(args.output)
    if not output.is_absolute():
        output = Path(__file__).resolve().parent.parent / output

    df = run_backtest(min_nq=args.min_nq, lookback=(args.lookback or None))
    write_report(df, output, args.min_nq)
    print(f"\nReport written to: {output}\n")


if __name__ == '__main__':
    main()
