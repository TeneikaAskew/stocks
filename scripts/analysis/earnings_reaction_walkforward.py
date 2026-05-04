"""
Walk-forward predictive analysis: do prior earnings reactions predict the next?

Usage:
    python3 scripts/analysis/earnings_reaction_walkforward.py [--ticker MCK] [--min-priors 4]

Test: as of T (one earnings event), use ONLY data from prior events to compute
"going-in" features. Then evaluate:
  1. Did our features correctly flag T as a high-reaction event?
  2. Was a directional 0DTE / 5-day swing actually profitable based on the
     features' sign + magnitude?

Two profitability proxies:
  - 0DTE proxy: realized |reaction_gap_pct| as the move you'd capture
    on a long-straddle bought at D-close (BMO) or D+1-open (AMC). No
    actual option premium yet — uses |gap| - 1.0% as cost approximation
    (representative ATM straddle premium for liquid names; refine when
    we add expected_move from earnings_calendar).
  - Swing proxy: sustain_5d_pct directional bet sized at 1 unit.

Outputs:
  - Per-event row: prior features, prediction, actual, P&L
  - Aggregate: hit rate, precision/recall on high-reaction prediction,
    avg P&L conditional on prediction, sharpe-equivalent.
"""
from __future__ import annotations

import argparse
import csv
import sys
from typing import Optional

import pandas as pd
import numpy as np


HIGH_REACTION_GAP_PCT = 5.0      # |reaction_gap_pct| > this → high-reaction
HIGH_REACTION_RANGE_ATR = 2.0    # range_in_atr > this → high-reaction (alt def)
STRADDLE_COST_PCT = 1.0          # rough ATM straddle premium proxy


def compute_priors(prior_events: pd.DataFrame) -> dict:
    """Compute 'going-in' features from the prior events only."""
    if prior_events.empty:
        return {}
    abs_gap = prior_events['reaction_gap_pct'].abs()
    abs_sustain = prior_events['sustain_5d_pct'].abs()
    return {
        'n_priors': len(prior_events),
        # Magnitude / volatility regime
        'mean_abs_gap': float(abs_gap.mean()),
        'max_abs_gap': float(abs_gap.max()) if not abs_gap.empty else None,
        'mean_abs_sustain_5d': float(abs_sustain.mean()) if not abs_sustain.dropna().empty else None,
        # High-reaction frequency (the screenshot's ">1× ATR Rate" analog)
        'p_high_gap': float((abs_gap > HIGH_REACTION_GAP_PCT).mean()),
        # Direction-consistency (the screenshot's "Continuation %" analog)
        'p_continuation': float(prior_events['direction_consistent_5d'].mean())
            if prior_events['direction_consistent_5d'].notna().any() else None,
        # Reaction-day intraday range as % of pre-bar close
        'mean_reaction_intraday_pct': float(
            ((prior_events['d_plus_1_high'] - prior_events['d_plus_1_low'])
             / prior_events['d_close']).mean() * 100
        ),
        # Most recent event's gap (recency bias check)
        'last_gap_pct': float(prior_events['reaction_gap_pct'].iloc[-1])
            if not prior_events.empty else None,
        # Sign-direction skew of past reactions
        'p_positive_gap': float((prior_events['reaction_gap_pct'] > 0).mean()),
    }


def label_event(row: pd.Series) -> dict:
    """Compute outcome labels + P&L proxies for one event."""
    gap = row['reaction_gap_pct']
    sustain = row.get('sustain_5d_pct')
    return {
        # Binary high-reaction labels
        'actual_high_reaction_gap': bool(abs(gap) > HIGH_REACTION_GAP_PCT) if pd.notna(gap) else None,
        # 0DTE P&L proxy: capture |gap| minus straddle cost. Asymmetric — buyer
        # of straddle is long volatility, profits on big moves regardless of sign.
        'pnl_0dte_long_straddle': (
            abs(gap) - STRADDLE_COST_PCT if pd.notna(gap) else None
        ),
        # Directional 0DTE proxy: predict direction = sign of last gap, bet 1 unit
        # P&L = sign_prediction × actual_gap. Negative when prediction wrong.
        # (computed in main loop where we have access to the prediction sign)
        # 5-day swing P&L: bet sign of avg-prior-gap, hold for 5d
        'pnl_swing_5d': sustain if pd.notna(sustain) else None,
    }


def run_for_ticker(reactions: pd.DataFrame, min_priors: int = 4) -> list[dict]:
    """Walk forward through one ticker's events."""
    reactions = reactions.sort_values('reported_date').reset_index(drop=True)
    rows = []
    for i in range(min_priors, len(reactions)):
        priors = reactions.iloc[:i]
        event = reactions.iloc[i]
        feats = compute_priors(priors)
        label = label_event(event)

        # Predictor rule: predict high-reaction if priors show it's a habit
        pred_high_reaction = (
            feats.get('p_high_gap', 0) >= 0.4   # > 40% of priors were >5% gaps
            or feats.get('mean_abs_gap', 0) >= 5.0
        )
        # Directional prediction: sign of mean prior gap (a momentum-ish signal)
        # If priors trend positive on average, predict positive
        pred_dir = 1 if feats.get('p_positive_gap', 0.5) >= 0.5 else -1

        # Directional 0DTE P&L
        pnl_0dte_dir = pred_dir * event['reaction_gap_pct'] if pd.notna(event['reaction_gap_pct']) else None
        # Directional swing P&L
        pnl_swing_dir = pred_dir * event['sustain_5d_pct'] if pd.notna(event.get('sustain_5d_pct')) else None

        rows.append({
            'ticker': event['ticker'],
            'reported_date': str(event['reported_date']),
            'reaction_basis': event.get('reaction_basis'),
            **feats,
            **label,
            'pred_high_reaction': pred_high_reaction,
            'pred_direction': pred_dir,
            'pnl_0dte_long_straddle': label['pnl_0dte_long_straddle'],
            'pnl_0dte_directional': pnl_0dte_dir,
            'pnl_swing_5d_directional': pnl_swing_dir,
        })
    return rows


def aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    out = {'n_events': len(df)}

    # Confusion-matrix metrics for high-reaction prediction
    actual = df['actual_high_reaction_gap']
    pred = df['pred_high_reaction']
    valid = actual.notna() & pred.notna()
    df_v = df[valid]
    if not df_v.empty:
        tp = ((df_v['pred_high_reaction']) & (df_v['actual_high_reaction_gap'])).sum()
        fp = ((df_v['pred_high_reaction']) & (~df_v['actual_high_reaction_gap'])).sum()
        fn = ((~df_v['pred_high_reaction']) & (df_v['actual_high_reaction_gap'])).sum()
        tn = ((~df_v['pred_high_reaction']) & (~df_v['actual_high_reaction_gap'])).sum()
        out['high_reaction_precision'] = float(tp / (tp + fp)) if (tp + fp) > 0 else None
        out['high_reaction_recall']    = float(tp / (tp + fn)) if (tp + fn) > 0 else None
        out['high_reaction_accuracy']  = float((tp + tn) / len(df_v))
        out['base_rate_high_reaction'] = float(df_v['actual_high_reaction_gap'].mean())

    # P&L stats
    for col in ['pnl_0dte_long_straddle', 'pnl_0dte_directional', 'pnl_swing_5d_directional']:
        s = df[col].dropna()
        if len(s) > 0:
            out[f'{col}_mean'] = float(s.mean())
            out[f'{col}_median'] = float(s.median())
            out[f'{col}_win_rate'] = float((s > 0).mean())
            out[f'{col}_sharpe_proxy'] = float(s.mean() / s.std()) if s.std() > 0 else None

    # P&L conditional on prediction (does the predictor add lift?)
    for col in ['pnl_0dte_directional', 'pnl_swing_5d_directional']:
        s_long  = df[df['pred_direction'] ==  1][col].dropna()
        s_short = df[df['pred_direction'] == -1][col].dropna()
        if len(s_long) > 0:
            out[f'{col}_when_pred_long_mean']  = float(s_long.mean())
        if len(s_short) > 0:
            out[f'{col}_when_pred_short_mean'] = float(s_short.mean())

    # Lift on the high-reaction predictor
    s_pred_high  = df[df['pred_high_reaction']]['pnl_0dte_long_straddle'].dropna()
    s_pred_norm  = df[~df['pred_high_reaction']]['pnl_0dte_long_straddle'].dropna()
    if len(s_pred_high) > 0 and len(s_pred_norm) > 0:
        out['straddle_pnl_when_predicted_high'] = float(s_pred_high.mean())
        out['straddle_pnl_when_predicted_normal'] = float(s_pred_norm.mean())
        out['lift'] = float(s_pred_high.mean() - s_pred_norm.mean())

    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', required=True,
                        help='Path to earnings_reactions CSV (from db-query workflow)')
    parser.add_argument('--ticker', default=None,
                        help='Single ticker to analyze (default: all)')
    parser.add_argument('--min-priors', type=int, default=4,
                        help='Minimum prior events required before predicting (default: 4)')
    parser.add_argument('--out-detail', default=None,
                        help='Write per-event detail CSV here')
    args = parser.parse_args()

    df = pd.read_csv(args.csv, parse_dates=['reported_date'])
    df = df.sort_values(['ticker', 'reported_date'])
    if args.ticker:
        df = df[df['ticker'] == args.ticker.upper()]
        if df.empty:
            print(f'No reactions for {args.ticker}', file=sys.stderr)
            sys.exit(1)

    all_rows = []
    for ticker, grp in df.groupby('ticker'):
        if len(grp) < args.min_priors + 1:
            continue
        all_rows.extend(run_for_ticker(grp, min_priors=args.min_priors))

    if not all_rows:
        print('No events with enough priors to evaluate', file=sys.stderr)
        sys.exit(1)

    detail_df = pd.DataFrame(all_rows)
    if args.out_detail:
        detail_df.to_csv(args.out_detail, index=False)
        print(f'Wrote {len(detail_df)} per-event rows to {args.out_detail}',
              file=sys.stderr)

    # Per-ticker summary
    print('\n=== Per-ticker summary ===')
    if args.ticker:
        print(pd.DataFrame([aggregate(all_rows)]).T)
    else:
        per_ticker = {}
        for ticker, grp in detail_df.groupby('ticker'):
            per_ticker[ticker] = aggregate(grp.to_dict('records'))
        per_t_df = pd.DataFrame(per_ticker).T
        # Sort by lift if available, else by hit rate
        if 'lift' in per_t_df.columns:
            per_t_df = per_t_df.sort_values('lift', ascending=False)
        print(per_t_df.to_string(max_rows=20))

    # Cross-sectional aggregate
    print('\n=== Cross-sectional aggregate (all events, all tickers) ===')
    agg = aggregate(all_rows)
    for k, v in agg.items():
        if v is not None and isinstance(v, float):
            print(f'  {k:<45s} {v:>10.4f}')
        else:
            print(f'  {k:<45s} {v}')


if __name__ == '__main__':
    main()
