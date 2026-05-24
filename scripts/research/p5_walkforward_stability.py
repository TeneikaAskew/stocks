#!/usr/bin/env python3
"""Phase 5 — walk-forward stability of the P2 + P3 findings.

For each pre-registered finding from P2 (gamma alerts) and P3
(strat combos), recompute the same metric in rolling 2-year windows
and report:

  - mean lift across windows
  - std across windows
  - best / worst window
  - % of windows that confirm the original sign of the lift
  - "fragility" score: how concentrated is the signal in specific
    sub-periods

Inputs (all local from prior phases):
  - docs/research/2026-05-23/data/gamma_events.parquet (P2)
  - docs/research/2026-05-23/data/p3_strat_cells.csv (P3 aggregated)
  - For P3 we need raw row-level data to do rolling windows — pull
    via existing /tmp/p45 CSVs (222k rows × 100 tickers × 10yr).

Output:
  - docs/research/2026-05-23/data/p5_rolling_window_stability.csv
  - docs/research/2026-05-23/P5_walkforward_stability.md  (report)
"""
from __future__ import annotations
import glob
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path('docs/research/2026-05-23/data')


def load_p3_raw() -> pd.DataFrame:
    """Reload the 100-ticker × 10yr data already pulled for P4.5."""
    parts = []
    for f in sorted(glob.glob('/tmp/p45/result_*.csv')):
        df = pd.read_csv(f, parse_dates=['date'])
        parts.append(df)
    full = pd.concat(parts, ignore_index=True)
    full = full.sort_values(['ticker', 'date']).reset_index(drop=True)

    # Compute forward-return columns
    g = full.groupby('ticker', sort=False)
    for h in [1, 5, 20]:
        full[f'fwd_close_{h}d'] = g['close'].shift(-h)
        full[f'y_{h}d_bps'] = (full[f'fwd_close_{h}d'] - full['close']) / full['close'] * 10000
        full[f'y_{h}d_up'] = (full[f'y_{h}d_bps'] > 0).astype(int)
    return full


# ────── Rolling-window stability for P3 combos ──────

def p3_combo_stability(df: pd.DataFrame, combo_name: str, vix_condition: str | None,
                       horizon_col: str, window_years: int = 2, step_months: int = 6) -> pd.DataFrame:
    """For a (combo, optional VIX condition, horizon), compute lift-over-baseline
    in rolling 2yr windows stepped 6 months apart.

    Baseline = unconditional hit-rate over the SAME window (so we're measuring
    cell lift, not absolute drift).
    """
    out_rows: list[dict] = []
    df = df.copy().dropna(subset=[horizon_col]).sort_values('date')
    df['date'] = pd.to_datetime(df['date'])

    if vix_condition:
        df['vix_bucket'] = pd.cut(df['vix_close'],
                                   bins=[-np.inf, 14.65, 19.40, np.inf],
                                   labels=['LOW','MID','HIGH'])
        df = df[df['vix_bucket'].astype(str) == vix_condition]

    if df.empty:
        return pd.DataFrame()

    start = df['date'].min()
    end = df['date'].max()
    win = pd.DateOffset(years=window_years)
    step = pd.DateOffset(months=step_months)

    win_start = start
    while win_start + win <= end:
        win_end = win_start + win
        in_window = df[(df['date'] >= win_start) & (df['date'] < win_end)]
        if in_window.empty:
            win_start = win_start + step
            continue

        # Baseline (unconditional in this window, all combos)
        base_v = in_window[horizon_col]
        base_hit = 100.0 * (base_v > 0).mean()

        # Combo subset
        sub = in_window[in_window['strat_combo'] == combo_name]
        if len(sub) < 5:
            win_start = win_start + step
            continue
        v = sub[horizon_col]
        hit = 100.0 * (v > 0).mean()
        lift = hit - base_hit

        out_rows.append({
            'window_start': win_start.date(),
            'window_end': win_end.date(),
            'n': len(sub),
            'hit_pct': round(hit, 2),
            'baseline_hit_pct': round(base_hit, 2),
            'lift_pp': round(lift, 2),
            'mean_bps': round(v.mean(), 2),
        })
        win_start = win_start + step

    return pd.DataFrame(out_rows)


# ────── Rolling-window stability for P2 gamma alerts ──────

def p2_gamma_stability(events: pd.DataFrame, alert_kind: str, direction: str,
                       horizon_col: str, ftfc_filter: str | None = None,
                       vix_condition: str | None = None,
                       window_years: int = 2, step_months: int = 6) -> pd.DataFrame:
    """Same logic for gamma alerts. Baseline here is direction-adjusted:
    for CALL, baseline_hit = % of unconditional bars where fwd > 0 in window
    for PUT, baseline_hit = % where fwd > 0 (= 100 - % where fwd < 0).

    But since fwd_ret_X_bps is signed in alert direction already, we just
    compute % > 0 and compare to the unconditional fwd-return-positive rate
    pooled across all directions in the window (using whatever directional
    convention is consistent).
    """
    events = events.copy()
    events['alert_date'] = pd.to_datetime(events['alert_date'])

    out_rows: list[dict] = []
    start = events['alert_date'].min()
    end = events['alert_date'].max()
    win = pd.DateOffset(years=window_years)
    step = pd.DateOffset(months=step_months)

    win_start = start
    while win_start + win <= end:
        win_end = win_start + win
        in_window = events[(events['alert_date'] >= win_start) & (events['alert_date'] < win_end)]
        sub = in_window[(in_window['alert_kind'] == alert_kind) &
                         (in_window['alert_direction'] == direction)]
        if ftfc_filter:
            sub = sub[sub['ftfc_prev_day_dir'] == ftfc_filter]
        if vix_condition:
            sub = sub[sub['vix_tercile'] == vix_condition]

        if len(sub) < 5:
            win_start = win_start + step
            continue

        v = sub[horizon_col].dropna()
        if len(v) < 5:
            win_start = win_start + step
            continue
        hit = 100.0 * (v > 0).mean()
        # Baseline = same window's general "fwd > 0" rate across all alerts in this direction
        base_v = in_window[in_window['alert_direction'] == direction][horizon_col].dropna()
        base_hit = 100.0 * (base_v > 0).mean() if len(base_v) > 5 else np.nan
        lift = hit - base_hit if not np.isnan(base_hit) else np.nan

        out_rows.append({
            'window_start': win_start.date(),
            'window_end': win_end.date(),
            'n': len(v),
            'hit_pct': round(hit, 2),
            'baseline_dir_hit_pct': round(base_hit, 2) if not np.isnan(base_hit) else None,
            'lift_pp': round(lift, 2) if not np.isnan(lift) else None,
            'mean_bps': round(v.mean(), 2),
        })
        win_start = win_start + step
    return pd.DataFrame(out_rows)


def summarize_stability(name: str, df_windows: pd.DataFrame) -> dict:
    if df_windows.empty:
        return {'finding': name, 'n_windows': 0}
    return {
        'finding': name,
        'n_windows': len(df_windows),
        'mean_lift_pp': round(df_windows['lift_pp'].mean(), 2),
        'std_lift_pp': round(df_windows['lift_pp'].std(), 2),
        'best_window': f"{df_windows.loc[df_windows['lift_pp'].idxmax(),'window_start']} (+{df_windows['lift_pp'].max():.1f}pp)",
        'worst_window': f"{df_windows.loc[df_windows['lift_pp'].idxmin(),'window_start']} ({df_windows['lift_pp'].min():+.1f}pp)",
        'pct_windows_positive': round(100 * (df_windows['lift_pp'] > 0).mean(), 1),
        'pct_windows_significant': round(100 * (df_windows['lift_pp'].abs() > 2).mean(), 1),
    }


def main():
    print("=== Loading data ===")
    df = load_p3_raw()
    print(f"P3 raw: {len(df):,} rows")
    df = df[df['ticker'] != 'NBIS']  # P3 quarantine
    events = pd.read_parquet(ROOT / 'gamma_events.parquet')
    print(f"P2 events: {len(events):,}")

    print("\n=== P3 combo stability (rolling 2-yr windows, 6-month step) ===")
    p3_findings = [
        ('212_bear_continuation @ HIGH-VIX, 5d', '212_bear_continuation', 'HIGH', 'y_5d_bps'),
        ('clean_2d_bear @ HIGH-VIX, 5d',        'clean_2d_bear',        'HIGH', 'y_5d_bps'),
        ('322_bull_continuation, 5d (anti-pred)','322_bull_continuation',None,  'y_5d_bps'),
        ('212_bear_continuation, 5d',            '212_bear_continuation',None,  'y_5d_bps'),
        ('f2d_bull_reversal, 1d',                'f2d_bull_reversal',    None,  'y_1d_bps'),
        ('22_bull_continuation, 5d (largest N)', '22_bull_continuation', None,  'y_5d_bps'),
    ]
    p3_summaries = []
    p3_detail = []
    for name, combo, vix, hcol in p3_findings:
        w = p3_combo_stability(df, combo, vix, hcol, window_years=2, step_months=6)
        p3_summaries.append(summarize_stability(name, w))
        w['finding'] = name
        p3_detail.append(w)
    p3_df = pd.DataFrame(p3_summaries)
    p3_det = pd.concat(p3_detail, ignore_index=True)
    print(p3_df.to_string(index=False))

    print("\n=== P2 gamma alert stability (rolling 2-yr, 6-month step) ===")
    p2_findings = [
        ('gate_break CALL, 1d (bull-drift)',  'gamma_gate_break',   'CALL', 'fwd_ret_1d_bps', None,   None),
        ('gate_break PUT, 1d (anti-pred)',    'gamma_gate_break',   'PUT',  'fwd_ret_1d_bps', None,   None),
        ('king_approach CALL, 15m',           'gamma_king_approach','CALL', 'fwd_ret_15m_bps', None,  None),
        ('king_approach PUT, 15m',            'gamma_king_approach','PUT',  'fwd_ret_15m_bps', None,  None),
        ('flip_cross PUT × FTFC-DOWN, 15m',   'gamma_flip_cross',   'PUT',  'fwd_ret_15m_bps','DOWN', None),
        ('gate_break PUT × LOW-VIX, 1d',      'gamma_gate_break',   'PUT',  'fwd_ret_1d_bps', None,   'LOW'),
    ]
    p2_summaries = []
    p2_detail = []
    for name, kind, dir_, hcol, ftfc, vix in p2_findings:
        w = p2_gamma_stability(events, kind, dir_, hcol, ftfc_filter=ftfc,
                                vix_condition=vix, window_years=2, step_months=6)
        p2_summaries.append(summarize_stability(name, w))
        w['finding'] = name
        p2_detail.append(w)
    p2_df = pd.DataFrame(p2_summaries)
    p2_det = pd.concat(p2_detail, ignore_index=True)
    print(p2_df.to_string(index=False))

    # Save
    p3_det.to_csv(ROOT / 'p5_p3_combo_stability.csv', index=False)
    p2_det.to_csv(ROOT / 'p5_p2_gamma_stability.csv', index=False)
    pd.concat([p3_df.assign(source='P3'), p2_df.assign(source='P2')]).to_csv(
        ROOT / 'p5_stability_summary.csv', index=False)
    print(f"\nSaved p5_*.csv")


if __name__ == '__main__':
    main()
