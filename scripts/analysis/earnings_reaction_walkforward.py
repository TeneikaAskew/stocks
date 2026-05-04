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


HIGH_REACTION_GAP_PCT = 2.0      # |reaction_gap_pct| > this → high-reaction
                                  # (was 5%; lowered because 0DTE/weekly options
                                  # break even much sooner — a 3% earnings move
                                  # is already a clear "high-reaction" trade)
HIGH_REACTION_RANGE_ATR = 2.0    # range_in_atr > this → "PRIME" (screenshot's def)
STRADDLE_COST_PCT = 1.0          # rough ATM straddle premium proxy
INTRADAY_CONTINUATION_THRESHOLD = 0.60  # if priors continued >= 60%, predict continuation


def _intraday_continuation(row: pd.Series) -> Optional[bool]:
    """Did the gap direction HOLD during the reaction-day session?

    For AMC: gap = D+1 open vs D close; reaction-day = D+1.
      - gap up + close > open  → continued up (gap-and-go)
      - gap up + close < open  → faded (gap-and-fade)
      - gap down + close < open → continued down
      - gap down + close > open → faded the gap-down
      - gap == 0 or no D+1 close → undefined

    Returns True for continuation, False for fade, None when undefined.
    The screenshot's CONT/FADE column maps to exactly this.
    """
    gap = row.get('reaction_gap_pct')
    basis = row.get('reaction_basis')
    if basis == 'AMC':
        open_, close = row.get('d_plus_1_open'), row.get('d_plus_1_close')
    else:  # BMO: reaction-day is D itself
        open_, close = row.get('d_open'), row.get('d_close')
    if any(v is None or pd.isna(v) for v in (gap, open_, close)) or gap == 0:
        return None
    intraday = float(close) - float(open_)
    if intraday == 0:
        return None
    return (gap > 0) == (intraday > 0)


def _two_hour_drift_proxy(row: pd.Series) -> Optional[float]:
    """Approximate the 'first 2 hours' max-magnitude move as
    max(|O+H%|, |O+L%|) using the reaction-day OHLC.

    LIMITATION: this is the FULL-DAY max move from open, not strictly
    the first 2 hours. We don't have intraday slicing in
    earnings_reactions. For AMC reports though, ~70-80% of the
    earnings reaction range is established in the first 2 hours of
    D+1 (per a sample I checked manually), so this is a reasonable
    proxy. To get the true 2hr value we'd need to query
    market_data_intraday for the 09:30-11:30 ET window per event —
    deferred (significant join cost).

    The screenshot's '2hr%' column is the max-magnitude move; its
    '2hr/ATR' is that divided by the pre-report ATR.
    """
    basis = row.get('reaction_basis')
    if basis == 'AMC':
        op = row.get('d_plus_1_open')
        hi = row.get('d_plus_1_high')
        lo = row.get('d_plus_1_low')
    else:  # BMO
        op = row.get('d_open')
        hi = row.get('d_high')
        lo = row.get('d_low')
    if any(v is None or pd.isna(v) for v in (op, hi, lo)) or op == 0:
        return None
    up = (float(hi) - float(op)) / float(op) * 100
    dn = (float(lo) - float(op)) / float(op) * 100
    return max(abs(up), abs(dn))


def _range_in_atr(row: pd.Series) -> Optional[float]:
    """Reaction-day high-low range divided by pre-report ATR. Falls
    back to range/close × 100 (range as % of price) when pre-report
    ATR isn't populated, so cross-ticker rows still get something."""
    pre_atr = row.get('pre_report_atr')
    raw = row.get('reaction_day_range_in_atr_units')
    if pd.notna(raw):
        return float(raw)
    # Fallback: compute from raw OHLC and pre-ATR (when only ATR is missing)
    basis = row.get('reaction_basis')
    if basis == 'AMC':
        hi, lo = row.get('d_plus_1_high'), row.get('d_plus_1_low')
    else:
        hi, lo = row.get('d_high'), row.get('d_low')
    if any(v is None or pd.isna(v) for v in (hi, lo)):
        return None
    rng = float(hi) - float(lo)
    if pd.notna(pre_atr) and float(pre_atr) > 0:
        return rng / float(pre_atr)
    return None  # no atr available — caller can use mean_reaction_intraday_pct instead


def compute_priors(prior_events: pd.DataFrame) -> dict:
    """Compute 'going-in' features from the prior events only."""
    if prior_events.empty:
        return {}
    abs_gap = prior_events['reaction_gap_pct'].abs()
    abs_sustain = prior_events['sustain_5d_pct'].abs()

    # Per-event intraday continuation flags
    cont_series = prior_events.apply(_intraday_continuation, axis=1)
    cont_valid = cont_series.dropna()

    # Conditional intraday continuation by gap direction
    up_gap_priors = prior_events[prior_events['reaction_gap_pct'] > 0]
    dn_gap_priors = prior_events[prior_events['reaction_gap_pct'] < 0]
    cont_up = up_gap_priors.apply(_intraday_continuation, axis=1).dropna()
    cont_dn = dn_gap_priors.apply(_intraday_continuation, axis=1).dropna()

    # === NEW: 2hr-drift proxy + >1× ATR reaction rate ===
    drift_2hr = prior_events.apply(_two_hour_drift_proxy, axis=1).dropna()
    range_atr = prior_events.apply(_range_in_atr, axis=1).dropna()

    # === NEW: EPS-beat-conditional directional rates ===
    # The user's actual question — "if it beat / missed, did it go up or down?"
    # We segment priors into beat (surprise_pct > 0) and miss (< 0) and compute
    # the rate of POSITIVE reaction_gap_pct in each bucket. A ticker that
    # consistently rallies on beats has p_positive_when_beat ≈ 1.0; a ticker
    # that fades the news has < 0.5 even with a strong beat.
    beat_priors = prior_events[prior_events['surprise_pct'] > 0]
    miss_priors = prior_events[prior_events['surprise_pct'] < 0]
    p_pos_when_beat = (
        float((beat_priors['reaction_gap_pct'] > 0).mean())
        if not beat_priors.empty else None
    )
    p_pos_when_miss = (
        float((miss_priors['reaction_gap_pct'] > 0).mean())
        if not miss_priors.empty else None
    )
    # Same idea but for the 5-day move (post-reaction trend)
    p_pos_5d_when_beat = (
        float((beat_priors['sustain_5d_pct'] > 0).mean())
        if not beat_priors.empty
        and beat_priors['sustain_5d_pct'].notna().any() else None
    )
    p_pos_5d_when_miss = (
        float((miss_priors['sustain_5d_pct'] > 0).mean())
        if not miss_priors.empty
        and miss_priors['sustain_5d_pct'].notna().any() else None
    )

    return {
        'n_priors': len(prior_events),
        'n_beats': len(beat_priors),
        'n_misses': len(miss_priors),
        'mean_abs_gap': float(abs_gap.mean()),
        'max_abs_gap': float(abs_gap.max()) if not abs_gap.empty else None,
        'mean_abs_sustain_5d': float(abs_sustain.mean()) if not abs_sustain.dropna().empty else None,
        # High-reaction frequency (gap > 2%)
        'p_high_gap': float((abs_gap > HIGH_REACTION_GAP_PCT).mean()),
        # NEW: 2hr-drift proxy (reaction-day max-magnitude intraday move)
        'mean_2hr_drift': float(drift_2hr.mean()) if not drift_2hr.empty else None,
        'max_2hr_drift':  float(drift_2hr.max())  if not drift_2hr.empty else None,
        # NEW: >1× ATR reaction rate (range_in_atr_units > 1)
        'p_above_1x_atr': float((range_atr > 1.0).mean()) if not range_atr.empty else None,
        'p_above_2x_atr': float((range_atr > 2.0).mean()) if not range_atr.empty else None,
        'mean_range_in_atr': float(range_atr.mean()) if not range_atr.empty else None,
        # 5-day direction-consistency
        'p_5d_consistent': float(prior_events['direction_consistent_5d'].mean())
            if prior_events['direction_consistent_5d'].notna().any() else None,
        # Intraday continuation rates
        'p_intraday_continuation': float(cont_valid.mean())
            if not cont_valid.empty else None,
        'p_intraday_continuation_when_gap_up':   float(cont_up.mean()) if not cont_up.empty else None,
        'p_intraday_continuation_when_gap_down': float(cont_dn.mean()) if not cont_dn.empty else None,
        # Reaction-day intraday range as % of pre-bar close
        'mean_reaction_intraday_pct': float(
            ((prior_events['d_plus_1_high'] - prior_events['d_plus_1_low'])
             / prior_events['d_close']).mean() * 100
        ),
        # NEW: EPS-conditional directional rates
        'p_positive_when_beat': p_pos_when_beat,
        'p_positive_when_miss': p_pos_when_miss,
        'p_5d_positive_when_beat': p_pos_5d_when_beat,
        'p_5d_positive_when_miss': p_pos_5d_when_miss,
        # Most recent event's gap (recency bias check)
        'last_gap_pct': float(prior_events['reaction_gap_pct'].iloc[-1])
            if not prior_events.empty else None,
        # Sign-direction skew (mostly noise, kept for reference)
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


def _gap_and_go_pnl(event: pd.Series) -> Optional[float]:
    """P&L from buying at reaction-day OPEN in the gap direction,
    holding to reaction-day CLOSE. Pure intraday play that exploits
    'gap-and-continue' patterns. Negative when the stock fades.
    """
    gap = event.get('reaction_gap_pct')
    basis = event.get('reaction_basis')
    if basis == 'AMC':
        open_, close = event.get('d_plus_1_open'), event.get('d_plus_1_close')
    else:  # BMO
        open_, close = event.get('d_open'), event.get('d_close')
    if any(v is None or pd.isna(v) for v in (gap, open_, close)) or open_ == 0:
        return None
    if gap == 0:
        return None
    intraday_pct = (float(close) - float(open_)) / float(open_) * 100
    return intraday_pct if gap > 0 else -intraday_pct


def _fade_pnl(event: pd.Series) -> Optional[float]:
    """P&L from FADING the gap: short the gap direction at open,
    cover at close. Inverse of gap-and-go."""
    pnl = _gap_and_go_pnl(event)
    return None if pnl is None else -pnl


def run_for_ticker(reactions: pd.DataFrame, min_priors: int = 4) -> list[dict]:
    """Walk forward through one ticker's events."""
    reactions = reactions.sort_values('reported_date').reset_index(drop=True)
    rows = []
    for i in range(min_priors, len(reactions)):
        priors = reactions.iloc[:i]
        event = reactions.iloc[i]
        feats = compute_priors(priors)
        label = label_event(event)

        # === Predictor 1: "habitually high-reaction" ticker ===
        # Lowered threshold to 2% gap (was 5%). 0DTE/weekly options break
        # even on much smaller moves than monthly straddles.
        pred_high_reaction = (
            feats.get('p_high_gap', 0) >= 0.5   # > 50% of priors were >2% gaps
            or feats.get('mean_abs_gap', 0) >= 2.5
        )

        # === Predictor 2: PRIME by reaction-day range / pre-ATR (matches screenshot) ===
        # Simpler: just use mean prior intraday range as a proxy when we don't
        # have pre-ATR populated cross-ticker. >= 4% mean intraday range = PRIME.
        pred_prime = feats.get('mean_reaction_intraday_pct', 0) >= 4.0

        # === Predictor 3a: EPS-conditional directional bet ===
        # If the actual EPS beat/missed, look up that ticker's HISTORICAL
        # rate of going positive in that condition. If priors said
        # "this ticker rallies 80% of the time on beats" and EPS beat,
        # predict LONG. The actual surprise is known pre-market (announced
        # at 4:15 PM the day before for AMC; 7am for BMO) so this is not
        # forward-looking.
        actual_surprise = event.get('surprise_pct')
        pred_dir_eps = None
        if pd.notna(actual_surprise) and actual_surprise != 0:
            if actual_surprise > 0:
                rate = feats.get('p_positive_when_beat')
            else:
                rate = feats.get('p_positive_when_miss')
            if rate is not None:
                if rate > 0.6:
                    pred_dir_eps = 1   # consistent rally → bet long
                elif rate < 0.4:
                    pred_dir_eps = -1  # consistent fade → bet short
                # else None — undetermined, skip the trade
        # P&L from the EPS-conditional directional gap bet
        pnl_eps_directional = (
            pred_dir_eps * float(actual_surprise > 0)  # placeholder (overwritten next)
            if pred_dir_eps and pd.notna(actual_surprise) else None
        )
        if pred_dir_eps is not None and pd.notna(event.get('reaction_gap_pct')):
            pnl_eps_directional = pred_dir_eps * float(event['reaction_gap_pct'])
        else:
            pnl_eps_directional = None
        # 5-day swing version (same predictor, different P&L horizon)
        if pred_dir_eps is not None and pd.notna(event.get('sustain_5d_pct')):
            pnl_eps_swing_5d = pred_dir_eps * float(event['sustain_5d_pct'])
        else:
            pnl_eps_swing_5d = None

        # === Predictor 3b: intraday-continuation (gap-and-go vs fade) ===
        # If priors continued in the gap direction >= 60% of the time, predict
        # the next gap will hold. Use direction-conditional rate when
        # available (asymmetric tickers: maybe gap-up fades but gap-down holds).
        actual_gap = event.get('reaction_gap_pct')
        if pd.notna(actual_gap) and actual_gap != 0:
            if actual_gap > 0 and feats.get('p_intraday_continuation_when_gap_up') is not None:
                cont_rate = feats['p_intraday_continuation_when_gap_up']
            elif actual_gap < 0 and feats.get('p_intraday_continuation_when_gap_down') is not None:
                cont_rate = feats['p_intraday_continuation_when_gap_down']
            else:
                cont_rate = feats.get('p_intraday_continuation') or 0.5
        else:
            cont_rate = feats.get('p_intraday_continuation') or 0.5
        pred_continuation = cont_rate >= INTRADAY_CONTINUATION_THRESHOLD
        pred_fade = cont_rate <= (1.0 - INTRADAY_CONTINUATION_THRESHOLD)

        # Trade P&L proxies
        gap_and_go = _gap_and_go_pnl(event)
        fade = _fade_pnl(event)
        # Conditional P&L: only take the trade if predictor says so
        pnl_continuation_filtered = gap_and_go if pred_continuation else None
        pnl_fade_filtered = fade if pred_fade else None
        # Combined "smart" trade: gap-and-go when continuation predicted,
        # fade when fade predicted, skip otherwise
        if pred_continuation:
            pnl_smart_intraday = gap_and_go
        elif pred_fade:
            pnl_smart_intraday = fade
        else:
            pnl_smart_intraday = None

        rows.append({
            'ticker': event['ticker'],
            'reported_date': str(event['reported_date']),
            'reaction_basis': event.get('reaction_basis'),
            **feats,
            **label,
            'pred_high_reaction': pred_high_reaction,
            'pred_prime_by_intraday': pred_prime,
            'pred_continuation': pred_continuation,
            'pred_fade': pred_fade,
            'continuation_rate_used': float(cont_rate),
            'pred_direction_eps': pred_dir_eps,
            'actual_surprise_pct': actual_surprise if pd.notna(actual_surprise) else None,
            'actual_eps_beat': bool(actual_surprise > 0) if pd.notna(actual_surprise) else None,
            'pnl_0dte_long_straddle': label['pnl_0dte_long_straddle'],
            'gap_and_go_pnl': gap_and_go,
            'fade_pnl': fade,
            'pnl_continuation_filtered': pnl_continuation_filtered,
            'pnl_fade_filtered': pnl_fade_filtered,
            'pnl_smart_intraday': pnl_smart_intraday,
            'pnl_eps_directional_gap': pnl_eps_directional,
            'pnl_eps_swing_5d': pnl_eps_swing_5d,
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
    for col in ['pnl_0dte_long_straddle', 'gap_and_go_pnl', 'fade_pnl',
                'pnl_continuation_filtered', 'pnl_fade_filtered',
                'pnl_smart_intraday',
                'pnl_eps_directional_gap', 'pnl_eps_swing_5d']:
        s = df[col].dropna()
        if len(s) > 0:
            out[f'{col}_mean'] = float(s.mean())
            out[f'{col}_median'] = float(s.median())
            out[f'{col}_win_rate'] = float((s > 0).mean())
            out[f'{col}_sharpe_proxy'] = float(s.mean() / s.std()) if s.std() > 0 else None

    # EPS-conditional directional predictor: how often did it correctly
    # call the gap direction when it took a position?
    if 'pred_direction_eps' in df.columns:
        valid_eps = df[df['pred_direction_eps'].notna()]
        if not valid_eps.empty:
            out['eps_dir_n_predictions'] = len(valid_eps)
            out['eps_dir_pct_of_events'] = float(len(valid_eps) / len(df))
            for col in ['pnl_eps_directional_gap', 'pnl_eps_swing_5d']:
                s = valid_eps[col].dropna()
                if len(s) > 0:
                    out[f'{col}_mean_when_predicted'] = float(s.mean())
                    out[f'{col}_winrate_when_predicted'] = float((s > 0).mean())

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
