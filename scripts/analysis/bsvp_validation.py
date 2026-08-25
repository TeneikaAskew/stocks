"""
BSVP + scalping-lanes validation against the full intraday history.

Validates every signal family of tradingview-pine-scripts/iwm-bsvp (via the
lib/indicators.calculate_bsvp port) and the composite lane-count entry rule of
tradingview-pine-scripts/iwm-scalping, per (ticker x timeframe), with:

  * event study — direction-adjusted forward returns at multiple horizons vs
    an all-bars baseline on the same timeframe (edge in bps + hit-rate lift)
  * trade-rule simulation — the iwm-bsvp.md rules verbatim: entry at signal
    close, stop at the 10-bar swing low/high, 2:1 R:R target, EOD time-stop
  * splits — full history vs recent 3 years, plus per-year edge for the
    headline families
  * threshold sensitivity sweeps (--sweep)

Design spec: docs/superpowers/specs/2026-07-13-bsvp-validation-design.md

Usage:
    python -m scripts.analysis.bsvp_validation                # full run
    python -m scripts.analysis.bsvp_validation --tickers IWM  --timeframes 30m
    python -m scripts.analysis.bsvp_validation --sweep        # + sensitivity
"""

import argparse
import os
import sys
from datetime import date, time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# This analysis runs off the local parquet cache (data/{t}/intraday/) pulled
# once from market_data_intraday. Force the parquet path so a configured
# shell doesn't silently re-pull 2M rows per ticker over the wire.
os.environ.pop('CLOUD_SQL_CONNECTION_NAME', None)

from scripts.analysis.shared_utils import (  # noqa: E402
    load_ticker_1m, resample_to_timeframe, REPORTS_DIR,
)
from lib.indicators import (  # noqa: E402
    calculate_bsvp, calculate_rsi, calculate_atr,
)

TICKERS = ['IWM', 'SPY', 'QQQ']
TIMEFRAMES = ['5m', '15m', '30m']

# Forward-return horizons per timeframe, expressed in bars
HORIZON_BARS = {
    '5m':  {'15m': 3, '30m': 6, '60m': 12},
    '15m': {'30m': 2, '60m': 4},
    '30m': {'30m': 1, '60m': 2},
}

RECENT_YEARS = 3
LOW_CONFIDENCE_N = 100

# BSVP signal families: column -> trade direction (+1 long / -1 short).
# Exhaustion signals are FADES per iwm-bsvp.md ("Exhaustion Fade" pattern).
BSVP_FAMILIES = {
    'bsvp_buy': 1, 'bsvp_sell': -1,
    'bsvp_strong_buy': 1, 'bsvp_strong_sell': -1,
    'bsvp_bull_cross': 1, 'bsvp_bear_cross': -1,
    'bsvp_bullish_div_conf': 1, 'bsvp_bearish_div_conf': -1,
    'bsvp_bull_accel': 1, 'bsvp_sell_accel': -1,
    'bsvp_bull_exhaustion': -1, 'bsvp_sell_exhaustion': 1,
    'bsvp_prime_buy': 1, 'bsvp_prime_sell': -1,
}


# ---------------------------------------------------------------------------
# Forward returns / event study
# ---------------------------------------------------------------------------

def session_forward_returns(df: pd.DataFrame, bars: int) -> pd.Series:
    """Forward pct return `bars` ahead, confined to the same session (NaN
    where the horizon would cross into the next day — no overnight leakage)."""
    day = pd.Series(df.index.date, index=df.index)
    fwd_close = df.groupby(day.values)['Close'].shift(-bars)
    return fwd_close / df['Close'] - 1.0


def eod_return(df: pd.DataFrame) -> pd.Series:
    """Return from each bar's close to the last close of the same session."""
    day = pd.Series(df.index.date, index=df.index)
    last = df.groupby(day.values)['Close'].transform('last')
    return last / df['Close'] - 1.0


def rising_edge(mask: pd.Series) -> pd.Series:
    """True only on the first bar of each run of Trues (Pine's `sig and not
    sig[1]` label logic) so overlapping bars don't multiply-count one setup."""
    m = mask.fillna(False).astype(bool)
    return m & ~m.shift(1, fill_value=False)


def event_study(events: pd.Series, fwd: pd.Series, direction: int) -> dict:
    """Direction-adjusted forward-return stats for event bars vs all bars."""
    adj = direction * fwd
    sig = adj[events & adj.notna()]
    base = adj[adj.notna()]
    if len(sig) == 0:
        return {'n': 0}
    edge = sig.mean() - base.mean()
    # one-sample t of signal returns against the baseline mean
    t = (sig.mean() - base.mean()) / (sig.std(ddof=1) / np.sqrt(len(sig))) if len(sig) > 2 and sig.std() > 0 else np.nan
    return {
        'n': int(len(sig)),
        'mean_bps': sig.mean() * 1e4,
        'hit': (sig > 0).mean(),
        'base_bps': base.mean() * 1e4,
        'base_hit': (base > 0).mean(),
        'edge_bps': edge * 1e4,
        't': t,
    }


# ---------------------------------------------------------------------------
# Trade-rule simulation (iwm-bsvp.md entry criteria, verbatim)
# ---------------------------------------------------------------------------

def trade_sim(df: pd.DataFrame, events: pd.Series, direction: int,
              stop_lookback: int = 10, rr: float = 2.0) -> dict:
    """Simulate the readme's rules per event: entry at signal close, stop at
    the `stop_lookback`-bar swing low (long) / high (short), target at
    `rr`:1, EOD close time-stop. Both-hit-same-bar counts as a loss
    (conservative). Returns win rate / avg R / expectancy."""
    close = df['Close'].to_numpy()
    high = df['High'].to_numpy()
    low = df['Low'].to_numpy()
    days = np.asarray(df.index.date)

    if direction > 0:
        swing = df['Low'].rolling(stop_lookback).min().to_numpy()
    else:
        swing = df['High'].rolling(stop_lookback).max().to_numpy()

    rs = []
    for i in np.flatnonzero(events.to_numpy()):
        entry = close[i]
        stop = swing[i]
        risk = (entry - stop) if direction > 0 else (stop - entry)
        if not np.isfinite(risk) or risk <= 0:
            continue
        target = entry + direction * rr * risk
        r = None
        j = i + 1
        while j < len(close) and days[j] == days[i]:
            if direction > 0:
                if low[j] <= stop:
                    r = -1.0
                    break
                if high[j] >= target:
                    r = rr
                    break
            else:
                if high[j] >= stop:
                    r = -1.0
                    break
                if low[j] <= target:
                    r = rr
                    break
            j += 1
        if r is None:  # EOD time-stop at the day's final close
            k = j - 1
            r = direction * (close[k] - entry) / risk
        rs.append(r)

    if not rs:
        return {'n_trades': 0}
    rs = np.array(rs)
    return {
        'n_trades': int(len(rs)),
        'win_rate': float((rs > 0).mean()),
        'avg_r': float(rs.mean()),
        'avg_win_r': float(rs[rs > 0].mean()) if (rs > 0).any() else np.nan,
        'avg_loss_r': float(rs[rs <= 0].mean()) if (rs <= 0).any() else np.nan,
    }


# ---------------------------------------------------------------------------
# Scalping lanes (port of tradingview-pine-scripts/iwm-scalping conditions)
# ---------------------------------------------------------------------------

def _session_vwap(df: pd.DataFrame) -> pd.Series:
    """Session-anchored VWAP on hlc3, matching Pine ta.vwap on an RTH chart."""
    day = np.asarray(df.index.date)
    hlc3 = (df['High'] + df['Low'] + df['Close']) / 3.0
    pv = (hlc3 * df['Volume']).groupby(day).cumsum()
    v = df['Volume'].groupby(day).cumsum()
    return pv / v.replace(0, np.nan)


def _stoch_raw(rsi: pd.Series, period: int = 14) -> pd.Series:
    """Pine `ta.stoch(rsi, rsi, rsi, 14)` — raw unsmoothed %K of RSI.
    (Deliberately NOT lib's smoothed StochRSI: the scalping script uses raw.)"""
    lo = rsi.rolling(period).min()
    hi = rsi.rolling(period).max()
    rng = (hi - lo).replace(0, np.nan)
    return 100.0 * (rsi - lo) / rng


def _asof_align(target_index: pd.DatetimeIndex, source: pd.DataFrame,
                source_tf_minutes: int, tf_minutes: int) -> pd.DataFrame:
    """Align a lower-timeframe frame to target bars: for each target bar END
    time, take the last source bar whose END time <= it (request.security
    semantics at bar close, no lookahead)."""
    src = source.copy()
    src.index = src.index + pd.Timedelta(minutes=source_tf_minutes)
    tgt_end = target_index + pd.Timedelta(minutes=tf_minutes)
    aligned = src.reindex(src.index.union(tgt_end)).ffill().loc[tgt_end]
    aligned.index = target_index
    return aligned


TF_MINUTES = {'5m': 5, '15m': 15, '30m': 30}


def scalping_lanes(df_tf: pd.DataFrame, df_1m: pd.DataFrame,
                   df_5m: pd.DataFrame, timeframe: str,
                   atr_min: float = 0.15, rvol_len: int = 50,
                   rvol_min: float = 1.5) -> pd.DataFrame:
    """All 21 directional lanes + universal gates of iwm-scalping, computed
    on the chart timeframe with 1m/5m sub-signals asof-aligned to bar close."""
    tf_min = TF_MINUTES[timeframe]
    c = df_tf['Close']
    ema9 = c.ewm(span=9, adjust=False).mean()
    ema20 = c.ewm(span=20, adjust=False).mean()
    ema50 = c.ewm(span=50, adjust=False).mean()
    vwap = _session_vwap(df_tf)
    rsi = calculate_rsi(c, 14)
    stoch = _stoch_raw(rsi, 14)
    atr = calculate_atr(df_tf['High'], df_tf['Low'], c, 14)
    rvol = df_tf['Volume'] / df_tf['Volume'].rolling(rvol_len).mean()

    # 5m sub-signals: last completed 5m bar at/before this bar's close
    f5 = pd.DataFrame({'c5': df_5m['Close'], 'h5_prev': df_5m['High'].shift(1),
                       'l5_prev': df_5m['Low'].shift(1)})
    a5 = _asof_align(df_tf.index, f5, 5, tf_min)
    break_up5 = a5['c5'] > a5['h5_prev']
    break_dn5 = a5['c5'] < a5['l5_prev']

    # 1m sub-signals at the bar's closing minute
    ema9_1 = df_1m['Close'].ewm(span=9, adjust=False).mean()
    vwap_1 = _session_vwap(df_1m)
    f1 = pd.DataFrame({'c1': df_1m['Close'], 'h1': df_1m['High'],
                       'l1': df_1m['Low'], 'ema9_1': ema9_1, 'vwap_1': vwap_1})
    a1 = _asof_align(df_tf.index, f1, 1, tf_min)
    lo_ref = np.minimum(a1['ema9_1'], a1['vwap_1'])
    hi_ref = np.maximum(a1['ema9_1'], a1['vwap_1'])
    reject_up1 = (a1['l1'] < lo_ref) & (a1['c1'] > hi_ref)
    reject_dn1 = (a1['h1'] > hi_ref) & (a1['c1'] < lo_ref)

    lanes = pd.DataFrame(index=df_tf.index)
    # 11 CALL lanes
    lanes['c_above_ema9'] = c > ema9
    lanes['c_above_ema20'] = c > ema20
    lanes['c_above_vwap'] = c > vwap
    lanes['c_rsi_gt50'] = rsi > 50
    lanes['c_rsi_gt60'] = rsi > 60
    lanes['c_stoch_gt70'] = stoch > 70
    lanes['c_ema9_gt_ema20'] = ema9 > ema20
    lanes['c_ema20_gt_ema50'] = ema20 > ema50
    lanes['c_atr_high'] = atr >= atr_min
    lanes['c_break_up5'] = break_up5
    lanes['c_reject_up1'] = reject_up1
    # 10 PUT lanes
    lanes['p_below_ema9'] = c < ema9
    lanes['p_below_ema20'] = c < ema20
    lanes['p_below_vwap'] = c < vwap
    lanes['p_rsi_lt50'] = rsi < 50
    lanes['p_rsi_lt40'] = rsi < 40
    lanes['p_stoch_lt30'] = stoch < 30
    lanes['p_ema9_lt_ema20'] = ema9 < ema20
    lanes['p_ema20_lt_ema50'] = ema20 < ema50
    lanes['p_break_dn5'] = break_dn5
    lanes['p_reject_dn1'] = reject_dn1
    # Universal gates
    lanes['u_rvol_high'] = rvol >= rvol_min
    bar_t = pd.Series(df_tf.index.time, index=df_tf.index)
    lanes['u_in_window'] = (bar_t >= time(9, 35)) & (bar_t < time(14, 30))

    call_cols = [col for col in lanes if col.startswith('c_')]
    put_cols = [col for col in lanes if col.startswith('p_')]
    lanes['call_score'] = lanes[call_cols].sum(axis=1)
    lanes['put_score'] = lanes[put_cols].sum(axis=1)
    lanes['atr_pct_high'] = (atr / c) >= 0.0008   # scale-invariant alternative
    lanes['atr_rel_high'] = atr >= atr.rolling(50).mean()
    return lanes


# ---------------------------------------------------------------------------
# Result collection
# ---------------------------------------------------------------------------

def evaluate_family(df, events, direction, horizons, label, ticker, tf, period, rows):
    for hname, fwd in horizons.items():
        st = event_study(events, fwd, direction)
        if st['n'] == 0:
            continue
        rows.append({'ticker': ticker, 'tf': tf, 'period': period,
                     'family': label, 'direction': direction,
                     'horizon': hname, **st})
    sim = trade_sim(df, events, direction)
    if sim['n_trades'] > 0:
        rows.append({'ticker': ticker, 'tf': tf, 'period': period,
                     'family': label, 'direction': direction,
                     'horizon': 'trade_2R', **sim})


def build_horizons(df: pd.DataFrame, tf: str) -> dict:
    horizons = {name: session_forward_returns(df, bars)
                for name, bars in HORIZON_BARS[tf].items()}
    horizons['eod'] = eod_return(df)
    return horizons


def analyze_ticker_tf(ticker: str, tf: str, df_1m: pd.DataFrame,
                      sweep: bool, rows: list, sweep_rows: list,
                      year_rows: list):
    df = resample_to_timeframe(df_1m, tf)
    df_5m = resample_to_timeframe(df_1m, '5m')
    print(f"  {ticker} {tf}: {len(df):,} bars "
          f"({df.index.min():%Y-%m-%d} .. {df.index.max():%Y-%m-%d})")

    bsvp = calculate_bsvp(df)
    horizons = build_horizons(df, tf)
    cutoff = df.index.max() - pd.DateOffset(years=RECENT_YEARS)
    recent = df.index >= cutoff

    # ---- BSVP families: full + recent-3y
    for fam, direction in BSVP_FAMILIES.items():
        events = rising_edge(bsvp[fam])
        evaluate_family(df, events, direction, horizons, fam, ticker, tf, 'full', rows)
        ev_recent = events & recent
        h_recent = {k: v.where(recent) for k, v in horizons.items()}
        evaluate_family(df, ev_recent, direction, h_recent, fam, ticker, tf,
                        f'recent{RECENT_YEARS}y', rows)

    # ---- Per-year edge for the headline families (buy/sell), 30m horizon key
    key_h = 'eod' if tf == '30m' else '30m'
    for fam, direction in (('bsvp_buy', 1), ('bsvp_sell', -1)):
        events = rising_edge(bsvp[fam])
        years = pd.Series(df.index.year, index=df.index)
        for yr in sorted(years.unique()):
            in_yr = years == yr
            st = event_study(events & in_yr, horizons[key_h].where(in_yr), direction)
            if st.get('n', 0) > 0:
                year_rows.append({'ticker': ticker, 'tf': tf, 'family': fam,
                                  'year': int(yr), 'horizon': key_h, **st})

    # ---- Entry-quality buckets among buy/sell signal bars
    eq = bsvp['bsvp_entry_quality']
    for fam, direction in (('bsvp_buy', 1), ('bsvp_sell', -1)):
        events = rising_edge(bsvp[fam])
        for lo, hi, blabel in ((70, 999, 'eq_70plus'), (50, 70, 'eq_50_70'),
                               (30, 50, 'eq_30_50'), (0, 30, 'eq_lt30')):
            bucket = events & (eq >= lo) & (eq < hi)
            evaluate_family(df, bucket, direction, horizons,
                            f'{fam}|{blabel}', ticker, tf, 'full', rows)

    # ---- Time-of-day buckets for buy/sell
    bar_t = pd.Series(df.index.time, index=df.index)
    tod = {'morning_0930_1030': (time(9, 30), time(10, 30)),
           'midday_1030_1400': (time(10, 30), time(14, 0)),
           'late_1400_1600': (time(14, 0), time(16, 0))}
    for fam, direction in (('bsvp_buy', 1), ('bsvp_sell', -1)):
        events = rising_edge(bsvp[fam])
        for tlabel, (t0, t1) in tod.items():
            bucket = events & (bar_t >= t0) & (bar_t < t1)
            evaluate_family(df, bucket, direction, horizons,
                            f'{fam}|{tlabel}', ticker, tf, 'full', rows)

    # ---- Scalping composite + per-lane lift
    lanes = scalping_lanes(df, df_1m, df_5m, tf)
    key_fwd = horizons[key_h]
    for col in [c for c in lanes.columns if c.startswith(('c_', 'p_'))]:
        direction = 1 if col.startswith('c_') else -1
        st = event_study(lanes[col].fillna(False).astype(bool), key_fwd, direction)
        if st.get('n', 0) > 0:
            rows.append({'ticker': ticker, 'tf': tf, 'period': 'full',
                         'family': f'lane|{col}', 'direction': direction,
                         'horizon': key_h, **st})

    for thresh in (5, 6, 7, 8, 9):
        for gates_label, gate in (
                ('nogate', pd.Series(True, index=df.index)),
                ('window', lanes['u_in_window']),
                ('window+rvol', lanes['u_in_window'] & lanes['u_rvol_high'])):
            call_ev = rising_edge((lanes['call_score'] >= thresh) & gate)
            put_ev = rising_edge((lanes['put_score'] >= thresh) & gate)
            evaluate_family(df, call_ev, 1, horizons,
                            f'scalp_call>={thresh}|{gates_label}', ticker, tf, 'full', rows)
            evaluate_family(df, put_ev, -1, horizons,
                            f'scalp_put>={thresh}|{gates_label}', ticker, tf, 'full', rows)

    # ---- Sweeps
    if sweep:
        run_sweeps(ticker, tf, df, df_1m, df_5m, bsvp, horizons, key_h, sweep_rows, lanes)


def run_sweeps(ticker, tf, df, df_1m, df_5m, bsvp, horizons, key_h, sweep_rows, lanes):
    key_fwd = horizons[key_h]

    # Acceleration threshold sweep (recomputed from returned smoothed columns)
    bpacon, spacon, vpo1 = bsvp['bsvp_bpv_avg'], bsvp['bsvp_spv_avg'], bsvp['bsvp_vpo1']
    roc = lambda s, n: 100.0 * (s - s.shift(n)) / s.shift(n)
    b_roc, s_roc, v_roc = roc(bpacon, 3), roc(spacon, 3), roc(vpo1, 3)
    for th in (10, 15, 20, 25, 30, 40):
        bull = rising_edge((bpacon > spacon) & (b_roc > th) & (v_roc > 0))
        bear = rising_edge((spacon > bpacon) & (s_roc > th) & (v_roc < 0))
        for lbl, ev, d in (('bull_accel', bull, 1), ('sell_accel', bear, -1)):
            st = event_study(ev, key_fwd, d)
            if st.get('n', 0) > 0:
                sweep_rows.append({'ticker': ticker, 'tf': tf,
                                   'sweep': f'accel_thresh={th}', 'family': lbl,
                                   'horizon': key_h, **st})

    # Divergence lookback sweep (recompute calculate_bsvp)
    for dl in (7, 14, 21, 28):
        b2 = calculate_bsvp(df, divergence_lookback=dl)
        for fam, d in (('bsvp_bullish_div_conf', 1), ('bsvp_bearish_div_conf', -1)):
            st = event_study(rising_edge(b2[fam]), key_fwd, d)
            if st.get('n', 0) > 0:
                sweep_rows.append({'ticker': ticker, 'tf': tf,
                                   'sweep': f'div_lookback={dl}', 'family': fam,
                                   'horizon': key_h, **st})

    # Conv/div lookback sweep
    for lb in (14, 27, 40):
        b2 = calculate_bsvp(df, lookback=lb)
        for fam, d in (('bsvp_buy', 1), ('bsvp_sell', -1)):
            st = event_study(rising_edge(b2[fam]), key_fwd, d)
            if st.get('n', 0) > 0:
                sweep_rows.append({'ticker': ticker, 'tf': tf,
                                   'sweep': f'lookback={lb}', 'family': fam,
                                   'horizon': key_h, **st})

    # Scalping ATR-gate alternatives on the best composite (call>=7 windowed)
    for gate_lbl, gate_col in (('atr_abs_0.15', 'c_atr_high'),
                               ('atr_pct', 'atr_pct_high'),
                               ('atr_rel_sma50', 'atr_rel_high')):
        base = (lanes['call_score'] - lanes['c_atr_high'].astype(int)) >= 6
        ev = rising_edge(base & lanes[gate_col].fillna(False).astype(bool)
                         & lanes['u_in_window'])
        st = event_study(ev, key_fwd, 1)
        if st.get('n', 0) > 0:
            sweep_rows.append({'ticker': ticker, 'tf': tf,
                               'sweep': f'scalp_atr_gate={gate_lbl}',
                               'family': 'scalp_call_6+gate', 'horizon': key_h, **st})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tickers', nargs='+', default=TICKERS)
    ap.add_argument('--timeframes', nargs='+', default=TIMEFRAMES)
    ap.add_argument('--sweep', action='store_true', help='run threshold sweeps')
    ap.add_argument('--out-prefix', default=None,
                    help='output file prefix (default bsvp_validation_<today>)')
    args = ap.parse_args()

    prefix = args.out_prefix or f"bsvp_validation_{date.today():%Y-%m-%d}"
    REPORTS_DIR.mkdir(exist_ok=True)

    rows, sweep_rows, year_rows = [], [], []
    for ticker in args.tickers:
        print(f"Loading {ticker} 1m...")
        df_1m = load_ticker_1m(ticker)
        if df_1m.empty:
            raise RuntimeError(
                f"No 1m data for {ticker} — run the intraday cache pull first")
        for tf in args.timeframes:
            analyze_ticker_tf(ticker, tf, df_1m, args.sweep,
                              rows, sweep_rows, year_rows)

    res = pd.DataFrame(rows)
    res.to_csv(REPORTS_DIR / f"{prefix}_results.csv", index=False)
    pd.DataFrame(year_rows).to_csv(REPORTS_DIR / f"{prefix}_by_year.csv", index=False)
    if sweep_rows:
        pd.DataFrame(sweep_rows).to_csv(REPORTS_DIR / f"{prefix}_sweeps.csv", index=False)

    print(f"\nWrote {len(res)} result rows -> {REPORTS_DIR / (prefix + '_results.csv')}")
    print(f"Per-year rows: {len(year_rows)}; sweep rows: {len(sweep_rows)}")


if __name__ == '__main__':
    main()
