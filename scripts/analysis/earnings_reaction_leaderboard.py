"""
Per-ticker leaderboard from the walk-forward results.

Reads the per-event detail CSV produced by earnings_reaction_walkforward.py
and ranks tickers by:
  1. EPS-conditional directional gap P&L
  2. Long-straddle profitability (volatility play)
  3. PRIME (>=2x ATR) frequency
  4. Predictable intraday continuation/fade
"""
from __future__ import annotations
import argparse
import sys

import pandas as pd
import numpy as np


MIN_EVENTS = 8
MIN_EPS_PREDICTIONS = 4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--detail-csv', required=True,
                        help='Per-event detail CSV from earnings_reaction_walkforward.py')
    parser.add_argument('--top-n', type=int, default=15)
    args = parser.parse_args()

    df = pd.read_csv(args.detail_csv)
    df['reported_date'] = pd.to_datetime(df['reported_date'])

    print(f'\nLoaded {len(df)} events across {df.ticker.nunique()} tickers')
    print(f'Filtering to tickers with >= {MIN_EVENTS} events\n')

    # Per-ticker aggregates
    rows = []
    for ticker, grp in df.groupby('ticker'):
        if len(grp) < MIN_EVENTS:
            continue
        n_events = len(grp)
        # Long straddle (universal volatility play)
        s = grp['pnl_0dte_long_straddle'].dropna()
        straddle_mean = s.mean() if len(s) else None
        straddle_winrate = (s > 0).mean() if len(s) else None
        straddle_sharpe = s.mean() / s.std() if len(s) > 1 and s.std() > 0 else None

        # EPS-conditional directional gap
        eps_grp = grp[grp['pred_direction_eps'].notna()]
        n_eps = len(eps_grp)
        eps = eps_grp['pnl_eps_directional_gap'].dropna()
        eps_mean = eps.mean() if len(eps) >= MIN_EPS_PREDICTIONS else None
        eps_winrate = (eps > 0).mean() if len(eps) >= MIN_EPS_PREDICTIONS else None
        eps_sharpe = eps.mean() / eps.std() if len(eps) >= MIN_EPS_PREDICTIONS and eps.std() > 0 else None
        eps_swing = eps_grp['pnl_eps_swing_5d'].dropna()
        eps_swing_mean = eps_swing.mean() if len(eps_swing) >= MIN_EPS_PREDICTIONS else None
        eps_swing_winrate = (eps_swing > 0).mean() if len(eps_swing) >= MIN_EPS_PREDICTIONS else None

        # PRIME rate (mean prior intraday range >= 4%)
        prime_avg_drift = grp['mean_2hr_drift'].mean() if grp['mean_2hr_drift'].notna().any() else None
        prime_p1x_atr = grp['p_above_1x_atr'].mean() if grp['p_above_1x_atr'].notna().any() else None

        # Intraday continuation patterns
        cont_rate = grp['p_intraday_continuation'].mean() if grp['p_intraday_continuation'].notna().any() else None

        # Smart intraday (continuation/fade adaptive)
        smart = grp['pnl_smart_intraday'].dropna()
        smart_mean = smart.mean() if len(smart) else None
        smart_winrate = (smart > 0).mean() if len(smart) else None

        rows.append({
            'ticker': ticker,
            'n_events': n_events,
            'n_eps_trades': n_eps,
            'straddle_mean': straddle_mean,
            'straddle_winrate': straddle_winrate,
            'straddle_sharpe': straddle_sharpe,
            'eps_dir_mean': eps_mean,
            'eps_dir_winrate': eps_winrate,
            'eps_dir_sharpe': eps_sharpe,
            'eps_swing_mean': eps_swing_mean,
            'eps_swing_winrate': eps_swing_winrate,
            'prime_avg_2hr_drift': prime_avg_drift,
            'prime_p_above_1x_atr': prime_p1x_atr,
            'intraday_continuation_rate': cont_rate,
            'smart_intraday_mean': smart_mean,
            'smart_intraday_winrate': smart_winrate,
        })

    lb = pd.DataFrame(rows).set_index('ticker')

    # === LEADERBOARD 1: EPS-conditional directional (the new winner) ===
    cand = lb[lb['eps_dir_sharpe'].notna() & (lb['n_eps_trades'] >= 6)]
    print('=== EPS-CONDITIONAL DIRECTIONAL — TOP TICKERS ===')
    print('(predict direction from beat/miss historical pattern)\n')
    cols = ['n_events', 'n_eps_trades', 'eps_dir_mean', 'eps_dir_winrate', 'eps_dir_sharpe', 'eps_swing_mean']
    top = cand.sort_values('eps_dir_sharpe', ascending=False).head(args.top_n)[cols]
    print(top.to_string(float_format=lambda x: f'{x:.3f}'))
    print()
    bot = cand.sort_values('eps_dir_sharpe', ascending=True).head(8)[cols]
    print('--- Worst (where the predictor systematically loses — useful as anti-signal) ---')
    print(bot.to_string(float_format=lambda x: f'{x:.3f}'))
    print()

    # === LEADERBOARD 2: Volatility (long straddle every print) ===
    cand2 = lb[lb['straddle_sharpe'].notna()]
    print('\n=== LONG STRADDLE — TOP TICKERS ===')
    print('(buy ATM straddle into every earnings, sized by realized |gap|)\n')
    cols2 = ['n_events', 'straddle_mean', 'straddle_winrate', 'straddle_sharpe']
    print(cand2.sort_values('straddle_sharpe', ascending=False).head(args.top_n)[cols2]
          .to_string(float_format=lambda x: f'{x:.3f}'))

    # === LEADERBOARD 3: PRIME (high-reaction frequency) ===
    cand3 = lb[lb['prime_avg_2hr_drift'].notna()]
    print('\n\n=== PRIME — HIGHEST 2hr DRIFT (proxied) ===')
    print('(tickers that consistently produce big moves on the day)\n')
    cols3 = ['n_events', 'prime_avg_2hr_drift', 'prime_p_above_1x_atr', 'straddle_mean']
    print(cand3.sort_values('prime_avg_2hr_drift', ascending=False).head(args.top_n)[cols3]
          .to_string(float_format=lambda x: f'{x:.3f}'))

    # === LEADERBOARD 4: Intraday pattern (fade vs continue) ===
    cand4 = lb[lb['smart_intraday_winrate'].notna() & (lb['n_events'] >= 12)]
    print('\n\n=== INTRADAY SMART — best CONT/FADE adaptive predictor ===')
    cols4 = ['n_events', 'intraday_continuation_rate', 'smart_intraday_mean', 'smart_intraday_winrate']
    print(cand4.sort_values('smart_intraday_mean', ascending=False).head(args.top_n)[cols4]
          .to_string(float_format=lambda x: f'{x:.3f}'))

    print('\n\n=== Cross-sectional summary ===')
    print(f'Tickers analyzed       : {len(lb)}')
    print(f'Tickers w/ EPS-dir sig : {(lb["eps_dir_sharpe"].notna() & (lb["n_eps_trades"] >= 6)).sum()}')
    print(f'EPS-dir mean (cross)   : {lb["eps_dir_mean"].mean():.3f}')
    print(f'EPS-dir winrate (cross): {lb["eps_dir_winrate"].mean():.3f}')
    print(f'Straddle mean (cross)  : {lb["straddle_mean"].mean():.3f}')
    print(f'Straddle winrate (cross): {lb["straddle_winrate"].mean():.3f}')


if __name__ == '__main__':
    main()
