#!/usr/bin/env python3
"""
Options P&L Translation for Top Timeframe Combo Setups.

Translates underlying-price-move backtest results into estimated options P&L
for 0DTE (or near-term) options. Answers the core question:

  "The 1m+30m combo has Sharpe 11 on underlying moves — does that survive
   after bid-ask spread and theta decay in actual options?"

Data used:
  - Per-trade data from the 1m+30m and 5m+15m combo backtests
  - Daily options chain parquets: data/{ticker}/options/{ticker}_av_options_{date}.parquet
    Schema: contractID, symbol, expiration, strike, type, last, mark, bid, ask,
            bid_size, ask_size, volume, open_interest, date, implied_volatility,
            delta, gamma, theta, vega, rho, fetch_timestamp, snapshot_date

Estimation method (Greeks approximation):
  For each trade (entry_time, direction, entry_price, underlying_return, hold_min):
  1. Load options chain for the trade date
  2. Find the ATM option: strike closest to entry_price, expiring same day (0DTE)
     or nearest expiry if 0DTE not available
  3. At entry, mark price M = (bid + ask) / 2
  4. Estimated option P&L:
       delta_pnl   = delta × (entry_price × underlying_return)      [$ gain from underlying move]
       theta_cost  = |theta| × (390/1440) × [g(exit) − g(entry)]    [time decay, intraday-shaped]
       net_pnl_$   = delta_pnl − theta_cost
       net_pnl_pct = net_pnl_$ / M                                  [return on premium paid]
  5. Transaction cost: half-spread at entry = (ask − bid) / (2 × M) subtracted

Theta time-distribution (intraday shape) — calibrated 2026-06:
  - The decay over a hold is |theta| × (390/1440) × [g(exit_tod) − g(entry_tod)],
    where g(t) is the empirically-measured cumulative 0DTE time-value decay
    (lib.options_intraday.cumulative_theta_decay). This replaces the prior naive
    linear hold_min/1440 assumption and preserves the full-day magnitude while
    redistributing it realistically: morning decays faster than linear (open IV
    crush), a midday LULL (g below linear ~12:00–15:00), then a terminal expiry
    CLIFF in the last minutes. NB: this corrects the earlier belief that theta
    "accelerates exponentially through the day / is understated in the afternoon"
    — the data shows the afternoon (pre-cliff) is actually a lull.

Limitations (IMPORTANT — read before interpreting results):
  - MAGNITUDE residual: the |theta| anchor is still an EOD Greek, not the option's
    intraday-repriced value, so the absolute theta budget can be off even though the
    intraday SHAPE is now calibrated. A fully correct magnitude requires repricing the
    option at entry/exit (lib.options_intraday.reprice_intraday_option) rather than
    scaling an EOD Greek — tracked as the recommended follow-up.
  - Results should be interpreted as an UPPER BOUND on options profitability.
  - When entry/exit time-of-day is unavailable the code falls back to the prior
    linear hold_min/1440 distribution.

Coverage:
  - IWM options: 2016-02-22 to 2026-02-20
  - SPY options: 2018-05-23 to 2026-02-20
  - QQQ options: 2022-02-14 to 2022-09-09 (partial coverage)

Usage:
    python scripts/analysis/options_pnl_translation.py
    python scripts/analysis/options_pnl_translation.py --tickers IWM SPY
    python scripts/analysis/options_pnl_translation.py --combo 1m+30m --tickers IWM
"""

import sys
import os
import argparse
import warnings
from copy import deepcopy
from pathlib import Path

import pandas as pd
import numpy as np

warnings.filterwarnings('ignore', category=FutureWarning)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.analysis.shared_utils import (
    TICKERS, REPORTS_DIR, DATA_DIR,
    load_ticker_1m, resample_to_timeframe,
    md_header, md_table, fmt_pct, fmt_num, save_report,
    timestamp_str, progress,
)
from lib.config import load_config
from lib.indicators import add_all_indicators
from lib.backtest import BacktestEngine
from lib.options_intraday import (
    minutes_from_rth_open, intraday_theta_decay_fraction,
)

BAR_MINUTES = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60}

COMBOS_TO_TEST = {
    '1m+30m': ('1m',  '30m'),
    '5m+15m': ('5m',  '15m'),
    '1m+15m': ('1m',  '15m'),
}


# ---------------------------------------------------------------------------
# Re-use the combo runner from walk_forward_tf_combos
# ---------------------------------------------------------------------------

def run_combo_trades(df_1m: pd.DataFrame, entry_tf: str, filter_tf: str,
                     cfg) -> pd.DataFrame:
    """Run combo backtest; return per-trade DataFrame with entry details."""
    close_col = 'Close' if 'Close' in df_1m.columns else 'Last'
    bar_min = BAR_MINUTES[entry_tf]

    exit_cfg = deepcopy(cfg.exit)
    exit_cfg.call_time_stop = max(1, int(cfg.exit.call_time_stop / bar_min))
    exit_cfg.put_time_stop  = max(1, int(cfg.exit.put_time_stop  / bar_min))

    sig_cfg = deepcopy(cfg.signal)
    if bar_min >= 30:
        sig_cfg.call_entry_end = '11:00'
    if bar_min >= 60:
        sig_cfg.call_entry_end = '12:00'
        sig_cfg.put_entry_end  = '15:30'

    df_entry = df_1m.copy() if entry_tf == '1m' else resample_to_timeframe(df_1m, entry_tf)
    if 'Time' not in df_entry.columns:
        df_entry['Time'] = df_entry.index

    df_filter  = resample_to_timeframe(df_1m, filter_tf)
    f_close    = df_filter['Close']
    f_ema20    = f_close.ewm(span=20, adjust=False).mean()
    htf_trend  = pd.Series(0, index=df_filter.index)
    htf_trend[f_close > f_ema20 * 1.0005] =  1
    htf_trend[f_close < f_ema20 * 0.9995] = -1
    htf_trend = htf_trend.reindex(df_entry.index, method='ffill').fillna(0).astype(int)

    df_work = add_all_indicators(df_entry.copy(), close_col=close_col)

    engine = BacktestEngine(
        risk_config=cfg.risk,
        exit_config=exit_cfg,
        signal_config=sig_cfg,
        strat_config=cfg.strat,
        backtest_config=cfg.backtest,
        indicator_config=cfg.indicator,
    )
    orig = engine._check_entry

    def filtered_check_entry(row, bar_time, use_strat_flag, strat_df, ftfc_series, bar_idx, day_df):
        trade = orig(row, bar_time, use_strat_flag, strat_df, ftfc_series, bar_idx, day_df)
        if trade is None:
            return None
        trend = htf_trend.get(day_df.index[bar_idx], 0)
        if trade.direction == 'CALL' and trend == -1:
            return None
        if trade.direction == 'PUT'  and trend ==  1:
            return None
        return trade

    engine._check_entry = filtered_check_entry
    result = engine.run(df_work, use_strat=False, close_col=close_col)

    if not result.trades:
        return pd.DataFrame()

    rows = []
    for t in result.trades:
        if t.return_pct is None or t.entry_time is None or t.exit_time is None:
            continue
        hold_min = (t.exit_time - t.entry_time).total_seconds() / 60.0
        rows.append({
            'entry_time':   t.entry_time,
            'exit_time':    t.exit_time,
            'direction':    t.direction,
            'entry_price':  t.entry_price,
            'return_pct':   t.return_pct,
            'hold_min':     hold_min,
            'trade_date':   pd.Timestamp(t.entry_time).date(),
        })

    df = pd.DataFrame(rows)
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    df['hhmm'] = df['entry_time'].dt.hour * 100 + df['entry_time'].dt.minute
    return df


# ---------------------------------------------------------------------------
# Options chain loader
# ---------------------------------------------------------------------------

def options_path(ticker: str, date) -> Path:
    """Return the path to the options parquet for a given date."""
    d = pd.Timestamp(date)
    fname = f'{ticker.lower()}_av_options_{d.strftime("%Y%m%d")}.parquet'
    return DATA_DIR / ticker.lower() / 'options' / fname


def load_options_chain(ticker: str, date) -> pd.DataFrame:
    """Load the AV EOD options chain for a ticker/date.

    Tries Cloud SQL first (WHERE data_source='alphavantage'), falls back to
    local parquet.  Returns empty DataFrame if neither source has data.
    """
    import os
    d = pd.Timestamp(date).date()

    # Try Cloud SQL first (data_source='alphavantage' → EOD, real Greeks)
    if os.environ.get('CLOUD_SQL_CONNECTION_NAME'):
        try:
            from gcp.database import query_to_dataframe
            sql = """
                SELECT contract_symbol AS "contractID",
                       ticker AS symbol,
                       expiration, strike,
                       option_type AS type,
                       last_price AS last,
                       mark, bid, ask, volume, open_interest,
                       snapshot_date AS date,
                       implied_volatility, delta, gamma, theta, vega, rho
                FROM etf_options_snapshots
                WHERE ticker = :ticker
                  AND snapshot_date = :snap_date
                  AND data_source = 'alphavantage'
                ORDER BY expiration, strike, option_type
            """
            df = query_to_dataframe(sql, {'ticker': ticker.upper(), 'snap_date': str(d)})
            if not df.empty:
                # Normalise option_type back to AV parquet convention (calls→call, puts→put)
                df['type'] = df['type'].map({'calls': 'call', 'puts': 'put'}).fillna(df['type'])
                return df
        except Exception:
            pass

    # Fallback: local parquet
    p = options_path(ticker, date)
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()


def find_atm_option(chain: pd.DataFrame, entry_price: float,
                    trade_date, direction: str) -> pd.Series:
    """Find the ATM option closest to entry_price on trade_date.

    Preference:
      1. 0DTE: expiration == trade_date
      2. Nearest future expiration (fallback)
    Option type: 'call' for CALL direction, 'put' for PUT direction.
    """
    if chain.empty:
        return pd.Series(dtype=float)

    opt_type = 'call' if direction == 'CALL' else 'put'
    td = pd.Timestamp(trade_date)

    # Filter by option type
    sub = chain[chain['type'].str.lower() == opt_type].copy()
    if sub.empty:
        return pd.Series(dtype=float)

    # Prefer 0DTE
    zero_dte = sub[pd.to_datetime(sub['expiration']).dt.date == td.date()]
    if zero_dte.empty:
        # Fallback: nearest future expiry
        fut = sub[pd.to_datetime(sub['expiration']) >= td]
        if fut.empty:
            return pd.Series(dtype=float)
        nearest_exp = pd.to_datetime(fut['expiration']).min()
        zero_dte = fut[pd.to_datetime(fut['expiration']) == nearest_exp]

    if zero_dte.empty:
        return pd.Series(dtype=float)

    # Find closest strike
    zero_dte = zero_dte.copy()
    zero_dte['strike_dist'] = (zero_dte['strike'] - entry_price).abs()
    return zero_dte.loc[zero_dte['strike_dist'].idxmin()]


# ---------------------------------------------------------------------------
# Swing-trade option selection (overnight hold)
# ---------------------------------------------------------------------------

def find_swing_option(chain: pd.DataFrame, entry_price: float,
                      entry_date, exit_date, direction: str) -> pd.Series:
    """Find ATM option for an overnight swing trade.

    Priority:
      1. Expiration == exit_date (0DTE on exit day — max leverage)
      2. Nearest expiration after exit_date (fallback — more conservative)
    Never selects options expiring on or before entry_date.
    """
    if chain.empty:
        return pd.Series(dtype=float)

    opt_type = 'call' if direction == 'CALL' else 'put'
    entry_d = pd.Timestamp(entry_date).normalize()
    exit_d = pd.Timestamp(exit_date).normalize()

    sub = chain[chain['type'].str.lower() == opt_type].copy()
    if sub.empty:
        return pd.Series(dtype=float)

    sub['exp_dt'] = pd.to_datetime(sub['expiration']).dt.normalize()

    # Exclude options expiring on or before entry date (would expire before exit)
    sub = sub[sub['exp_dt'] > entry_d]
    if sub.empty:
        return pd.Series(dtype=float)

    # Priority 1: expiring on exit date
    exact = sub[sub['exp_dt'] == exit_d]
    if not exact.empty:
        exact = exact.copy()
        exact['strike_dist'] = (exact['strike'] - entry_price).abs()
        return exact.loc[exact['strike_dist'].idxmin()]

    # Priority 2: nearest expiration after exit date
    future = sub[sub['exp_dt'] > exit_d]
    if future.empty:
        # Fallback: anything after entry date (already filtered above)
        sub = sub.copy()
        sub['strike_dist'] = (sub['strike'] - entry_price).abs()
        nearest_exp = sub['exp_dt'].min()
        nearest = sub[sub['exp_dt'] == nearest_exp]
        return nearest.loc[nearest['strike_dist'].idxmin()]

    nearest_exp = future['exp_dt'].min()
    nearest = future[future['exp_dt'] == nearest_exp].copy()
    nearest['strike_dist'] = (nearest['strike'] - entry_price).abs()
    return nearest.loc[nearest['strike_dist'].idxmin()]


def estimate_swing_options_pnl(entry_price: float, direction: str,
                                atm_opt: pd.Series, entry_date, exit_date,
                                underlying_returns: dict) -> dict:
    """Estimate options P&L for multiple exit scenarios of a swing trade.

    Args:
        entry_price: Underlying price at entry.
        direction: 'CALL' or 'PUT'.
        atm_opt: Selected option row from find_swing_option.
        entry_date: Entry date.
        exit_date: Exit date (next trading day).
        underlying_returns: Dict with keys like 'Noon', 'BestEOD', 'EOD',
            values are return percentages (e.g. 0.5 means 0.5%).

    Returns dict with option info and P&L for each scenario, or None.
    """
    if atm_opt.empty:
        return None

    mark = float(atm_opt.get('mark', np.nan))
    bid = float(atm_opt.get('bid', np.nan))
    ask = float(atm_opt.get('ask', np.nan))
    delta = float(atm_opt.get('delta', np.nan))
    gamma = float(atm_opt.get('gamma', np.nan))
    theta = float(atm_opt.get('theta', np.nan))
    iv = float(atm_opt.get('implied_volatility', np.nan))

    if any(pd.isna(v) for v in [mark, delta, theta]) or mark <= 0:
        return None

    eff_delta = abs(delta)
    eff_gamma = abs(gamma) if not pd.isna(gamma) else 0.0

    # Calendar days for theta
    cal_days = max(1, (pd.Timestamp(exit_date) - pd.Timestamp(entry_date)).days)
    theta_cost = abs(theta) * cal_days

    # Spread cost (half-spread at entry)
    if not pd.isna(bid) and not pd.isna(ask) and ask > bid:
        spread_cost = (ask - bid) / 2.0
    else:
        spread_cost = mark * 0.02

    result = {
        'Opt_Strike': float(atm_opt['strike']),
        'Opt_Expiration': pd.Timestamp(atm_opt['expiration']).date()
            if not pd.isna(atm_opt.get('expiration')) else np.nan,
        'Opt_DTE': int((pd.Timestamp(atm_opt['expiration'])
                        - pd.Timestamp(entry_date)).days),
        'Opt_Mark': round(mark, 3),
        'Opt_Delta': round(delta, 4),
        'Opt_Gamma': round(eff_gamma, 5),
        'Opt_Theta': round(theta, 4),
        'Opt_IV': round(iv, 4) if not pd.isna(iv) else np.nan,
        'Opt_Theta_Days': cal_days,
        'Opt_Spread_Cost': round(spread_cost, 3),
    }

    for scenario, ret_pct in underlying_returns.items():
        prefix = f'Opt_{scenario}'
        if pd.isna(ret_pct):
            result[f'{prefix}_PnL'] = np.nan
            result[f'{prefix}_PnL_Pct'] = np.nan
            result[f'{prefix}_Win'] = np.nan
            continue

        # Underlying dollar move
        und_move = entry_price * ret_pct / 100.0

        # First-order: delta P&L
        delta_pnl = eff_delta * abs(und_move)

        # Second-order: gamma adjustment
        gamma_adj = 0.5 * eff_gamma * (und_move ** 2)

        # Sign: ret_pct is already direction-adjusted (positive = favorable)
        if ret_pct >= 0:
            total_pnl = delta_pnl + gamma_adj - theta_cost - spread_cost
        else:
            total_pnl = -delta_pnl + gamma_adj - theta_cost - spread_cost

        pnl_pct = total_pnl / mark * 100

        result[f'{prefix}_PnL'] = round(total_pnl, 3)
        result[f'{prefix}_PnL_Pct'] = round(pnl_pct, 2)
        result[f'{prefix}_Win'] = int(total_pnl > 0)

    return result


# ---------------------------------------------------------------------------
# Options P&L estimation — intraday 0DTE (Greeks approximation)
# ---------------------------------------------------------------------------

def estimate_options_pnl(trade: pd.Series, atm_opt: pd.Series) -> dict:
    """Estimate options P&L using first-order Greeks approximation.

    Returns dict with estimated metrics or None if data insufficient.
    """
    if atm_opt.empty:
        return None

    mark  = float(atm_opt.get('mark', np.nan))
    bid   = float(atm_opt.get('bid',  np.nan))
    ask   = float(atm_opt.get('ask',  np.nan))
    delta = float(atm_opt.get('delta', np.nan))
    theta = float(atm_opt.get('theta', np.nan))  # $/day (usually negative)

    if any(pd.isna(v) for v in [mark, delta, theta]) or mark <= 0:
        return None

    underlying_chg = trade['entry_price'] * trade['return_pct']  # $ move in underlying

    # Adjust delta sign: PUT has negative delta, we want to align with direction
    eff_delta = abs(delta)  # for PUTs, underlying drop → option gain

    # First-order delta P&L (in $)
    delta_pnl = eff_delta * abs(underlying_chg)
    # Adjust sign: if direction and underlying move disagree, it's a loss
    if trade['direction'] == 'CALL' and underlying_chg < 0:
        delta_pnl = -delta_pnl
    elif trade['direction'] == 'PUT' and underlying_chg > 0:
        delta_pnl = -delta_pnl

    # Theta cost for the hold. theta is $/calendar-day; a full RTH session is
    # 390/1440 of a calendar day. The intraday DISTRIBUTION of that decay is not
    # linear — empirical g(t) (lib.options_intraday) is morning-heavy with a
    # midday lull and a terminal expiry cliff. Keep the prior full-day magnitude
    # (390/1440 of daily theta) and redistribute it across the session via
    # g(exit) − g(entry). Fall back to the linear model when time-of-day is
    # unavailable.
    theta_daily = abs(theta)
    # THETA_MODEL=linear forces the legacy hold_min/1440 distribution — kept so
    # the empirical recalibration can be diffed against the old behaviour (run
    # the report once each way). Default 'empirical' uses the calibrated curve.
    if os.environ.get('THETA_MODEL', 'empirical').strip().lower() == 'linear':
        theta_cost = theta_daily * (trade['hold_min'] / 1440.0)
    else:
        entry_mfo = minutes_from_rth_open(trade.get('entry_time'))
        exit_mfo  = minutes_from_rth_open(trade.get('exit_time'))
        if entry_mfo is not None and exit_mfo is not None and exit_mfo > entry_mfo:
            decay_frac = intraday_theta_decay_fraction(entry_mfo, exit_mfo)
            theta_cost = theta_daily * (390.0 / 1440.0) * decay_frac  # 390 = RTH min
        else:
            theta_cost = theta_daily * (trade['hold_min'] / 1440.0)   # linear fallback

    # Transaction cost (half-spread at entry)
    spread_cost_dollar = (ask - bid) / 2.0 if not pd.isna(bid) and not pd.isna(ask) else mark * 0.02

    net_pnl_dollar = delta_pnl - theta_cost - spread_cost_dollar
    net_pnl_pct    = net_pnl_dollar / mark  # return on premium

    # Win = made money on the option
    option_win = int(net_pnl_dollar > 0)

    return {
        'mark':              mark,
        'delta':             delta,
        'theta':             theta,
        'delta_pnl':         delta_pnl,
        'theta_cost':        theta_cost,
        'spread_cost':       spread_cost_dollar,
        'net_pnl_dollar':    net_pnl_dollar,
        'net_pnl_pct':       net_pnl_pct,
        'option_win':        option_win,
        'underlying_win':    int(trade['return_pct'] > 0),
    }


# ---------------------------------------------------------------------------
# Core analysis runner
# ---------------------------------------------------------------------------

def analyse_combo(ticker: str, combo_label: str, entry_tf: str, filter_tf: str,
                  df_1m: pd.DataFrame, cfg) -> str:
    """Run the combo backtest and translate to options P&L. Returns report section."""
    progress(f'Running {combo_label} backtest...', ticker)
    trades = run_combo_trades(df_1m, entry_tf, filter_tf, cfg)

    if trades.empty:
        return f'\n### {combo_label}\nNo trades generated.\n\n'

    progress(f'  {len(trades):,} trades found. Loading options chains...', ticker)

    results = []
    missing_dates = 0
    no_atm_dates  = 0

    for _, trade in trades.iterrows():
        chain = load_options_chain(ticker, trade['trade_date'])
        if chain.empty:
            missing_dates += 1
            continue

        atm = find_atm_option(chain, trade['entry_price'], trade['trade_date'],
                               trade['direction'])
        if atm.empty:
            no_atm_dates += 1
            continue

        est = estimate_options_pnl(trade, atm)
        if est is None:
            continue

        est['trade_date']     = trade['trade_date']
        est['direction']      = trade['direction']
        est['underlying_ret'] = trade['return_pct']
        est['hold_min']       = trade['hold_min']
        est['hhmm']           = int(trade.get('hhmm', 0))
        results.append(est)

    progress(f'  Options match: {len(results):,}/{len(trades):,} trades '
             f'({missing_dates} missing dates, {no_atm_dates} no ATM found)', ticker)

    if not results:
        return f'\n### {combo_label}\nNo options data matched.\n\n'

    df = pd.DataFrame(results)

    # --- Underlying vs Options comparison ---
    n             = len(df)
    und_wr        = df['underlying_win'].mean()
    opt_wr        = df['option_win'].mean()
    und_exp       = df['underlying_ret'].mean()
    opt_exp       = df['net_pnl_pct'].mean()
    avg_mark      = df['mark'].mean()
    avg_theta_c   = df['theta_cost'].mean()
    avg_spread_c  = df['spread_cost'].mean()
    avg_delta_pnl = df['delta_pnl'].mean()

    # Sharpe on options returns
    daily_opt = df.groupby('trade_date')['net_pnl_pct'].sum()
    opt_sharpe = (
        daily_opt.mean() / daily_opt.std() * np.sqrt(252)
        if len(daily_opt) > 5 and daily_opt.std() > 0 else 0.0
    )

    # By direction breakdown
    call_df = df[df['direction'] == 'CALL']
    put_df  = df[df['direction'] == 'PUT']

    out = f'\n### {combo_label}\n\n'
    out += f'> ⚠️ **Estimation caveat**: Results use EOD Greeks applied to intraday trades.\n'
    out += f'> Theta is underestimated for 0DTE; actual options P&L is likely *worse* than shown.\n'
    out += f'> Treat as an **upper bound** on profitability, not a precise forecast.\n\n'

    out += md_table(['Metric', 'Underlying', 'Options (estimated)'], [
        ['Trades analysed',   fmt_num(n),              fmt_num(n)],
        ['**Win Rate**',      f'**{fmt_pct(und_wr * 100)}**',
                              f'**{fmt_pct(opt_wr * 100)}**'],
        ['**Expectancy**',    fmt_pct(und_exp * 100),  fmt_pct(opt_exp * 100)],
        ['Sharpe (daily)',    '—',                      f'{opt_sharpe:.2f}'],
        ['Avg mark price',    '—',                      f'${avg_mark:.2f}'],
        ['Avg delta P&L',     '—',                      f'${avg_delta_pnl:+.3f}'],
        ['Avg theta cost',    '—',                      f'−${avg_theta_c:.3f}'],
        ['Avg spread cost',   '—',                      f'−${avg_spread_c:.3f}'],
    ]) + '\n'

    if opt_wr >= 0.55:
        verdict = '✅ SURVIVES — Edge holds in options after estimated costs.'
    elif opt_wr >= 0.50:
        verdict = '⚠️ MARGINAL — Barely positive. Real theta costs could flip this.'
    else:
        verdict = '❌ DOES NOT SURVIVE — Theta + spread wipes the underlying edge.'

    out += f'\n**Options verdict: {verdict}**\n\n'

    # By direction
    out += '**By Direction:**\n\n'
    dir_rows = []
    for label_, sub in [('CALL', call_df), ('PUT', put_df)]:
        if sub.empty:
            dir_rows.append([label_, '0', 'N/A', 'N/A'])
            continue
        dir_rows.append([
            label_,
            fmt_num(len(sub)),
            fmt_pct(sub['option_win'].mean() * 100),
            fmt_pct(sub['net_pnl_pct'].mean() * 100),
        ])
    out += md_table(['Direction', 'Trades', 'Options WR', 'Options Expectancy'], dir_rows) + '\n'

    # By time of day
    out += '\n**By Time of Day:**\n\n'
    tod_buckets = [
        ('Morning (9:30–10:59)',    df['hhmm'] < 1100),
        ('Midday (11:00–13:59)',    (df['hhmm'] >= 1100) & (df['hhmm'] < 1400)),
        ('Afternoon (14:00–16:00)', df['hhmm'] >= 1400),
    ]
    tod_rows = []
    for bucket_name, mask in tod_buckets:
        sub = df[mask]
        if sub.empty:
            tod_rows.append([bucket_name, '0', 'N/A', 'N/A', 'N/A', 'N/A'])
            continue
        tod_rows.append([
            bucket_name,
            fmt_num(len(sub)),
            fmt_pct(sub['option_win'].mean() * 100),
            fmt_pct(sub['underlying_win'].mean() * 100),
            f'${sub["theta_cost"].mean():.3f}',
            fmt_pct(sub['net_pnl_pct'].mean() * 100),
        ])
    out += md_table(
        ['Period', 'Trades', 'Options WR', 'Underlying WR', 'Avg Theta Cost', 'Expectancy'],
        tod_rows,
    ) + '\n'
    out += ('_Note: theta cost uses the empirical intraday 0DTE decay curve '
            '(lib.options_intraday) — morning-heavy, midday lull, terminal expiry '
            'cliff. Absolute magnitude still scales an EOD theta Greek; see module '
            'docstring._\n\n')

    # Underlying WR vs options WR mismatch analysis
    same_dir   = (df['underlying_win'] == df['option_win']).mean()
    out += f'\n**Underlying→Options win agreement: {same_dir:.1%}** '
    out += f'(trades that win on underlying and also win as options)\n\n'

    # Save raw results
    csv_dir = REPORTS_DIR / 'data'
    csv_dir.mkdir(exist_ok=True)
    df.to_csv(
        csv_dir / f'options_pnl_{ticker.lower()}_{combo_label.replace("+", "_")}.csv',
        index=False,
    )

    return out


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(tickers=None, combos=None):
    tickers = tickers or ['IWM', 'SPY']  # QQQ has very limited options coverage
    combos  = combos  or list(COMBOS_TO_TEST.keys())

    for ticker in tickers:
        progress('Starting options P&L translation', ticker)

        df_1m = load_ticker_1m(ticker)
        if df_1m.empty:
            progress('No 1m data, skipping.', ticker)
            continue

        cfg = load_config(ticker=ticker)

        report = md_header(f'Options P&L Translation — {ticker}', 1)
        report += f'\nGenerated: {timestamp_str()}\n\n'
        report += (
            '**Purpose**: Estimate whether the underlying-price-move edge survives\n'
            'after 0DTE options bid-ask spread and theta decay.\n\n'
            '**Data**: EOD options chain parquets (daily snapshot). '
            'See per-section caveats.\n\n'
        )
        report += md_header('Results by Combo', 2)

        for combo_label in combos:
            if combo_label not in COMBOS_TO_TEST:
                progress(f'Unknown combo {combo_label}, skipping.', ticker)
                continue
            entry_tf, filter_tf = COMBOS_TO_TEST[combo_label]
            try:
                section = analyse_combo(ticker, combo_label, entry_tf, filter_tf, df_1m, cfg)
                report += section
            except Exception as exc:
                progress(f'ERROR on {combo_label}: {exc}', ticker)
                report += f'\n### {combo_label}\nError: {exc}\n\n'

        fn = f'options_pnl_{ticker.lower()}.md'
        save_report(report, fn)
        progress(f'Report saved: reports/{fn}', ticker)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Options P&L translation for top TF combo strategies',
    )
    parser.add_argument('--tickers', nargs='+', default=['IWM', 'SPY'],
                        choices=['IWM', 'SPY', 'QQQ'])
    parser.add_argument('--combo', nargs='+', default=list(COMBOS_TO_TEST.keys()),
                        choices=list(COMBOS_TO_TEST.keys()),
                        dest='combos')
    args = parser.parse_args()
    run(tickers=args.tickers, combos=args.combos)


if __name__ == '__main__':
    main()
