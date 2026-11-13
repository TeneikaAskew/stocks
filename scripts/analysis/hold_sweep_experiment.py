#!/usr/bin/env python3
"""Hold sweep for the similar-setups realized score. Read only.

Question (owner, 2026-11-13): the realized score from FEAT-SIGNAL-001
(rule next-open-20m-1c-v1) holds every signal for exactly 20 bars on every
ticker. Would another hold do better per ticker?

For each stored signal in ``historical_signals`` this rescores the trade
with the production helper ``lib.trading_analysis.realized_outcome`` at
each hold in --holds (default 5, 10, 15, 20, 30, 45, 60 bars), same entry
(the open of the bar after the signal bar), same 09:30 to 15:34 ET signal
window, same session-close rule and the same 0.01 cost. Bars come from
``gcp.historical_signals.load_intraday_bars`` and are turned into naive
Eastern time exactly as scripts/run_historical_signals.py does, so hold=20
reproduces the stored realized_return_pct.

Two signal sets per hold:
  own     every signal scoreable at that hold (longer holds lose late signals)
  common  only signals scoreable at every hold, so holds are compared on the
          same trades
Two counting rules:
  all         every stored signal (back-to-back bars overlap heavily)
  one-at-a-time  a signal is taken only once the previous trade has exited,
                 which is what a single position could have done; its t value
                 is the honest test of whether the average differs from zero
Periods: before / after --split (default 2026-05-01, the FEAT-SIGNAL-001
holdout/primary boundary), so a hold chosen on 'before' can be checked on
'after'.

It only SELECTs (historical_signals, market_data_intraday) inside READ ONLY
transactions and writes one CSV. Usage, from the repo root with Cloud SQL
configured as for the other jobs:

    python3 scripts/analysis/hold_sweep_experiment.py --out /tmp/hold_sweep.csv
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from lib.eastern_time import utc_to_eastern_naive  # noqa: E402
from lib.trading_analysis import realized_outcome  # noqa: E402

DEFAULT_HOLDS = (5, 10, 15, 20, 30, 45, 60)
SMALL_DAYS = 40        # fewer distinct signal days than this is a small sample
SMALL_TRADES = 100     # fewer one-at-a-time trades than this is a small sample


# ── scoring (pure, tested locally) ─────────────────────────────────────────

def score_signals(bars: pd.DataFrame, signals: pd.DataFrame, holds, cost: float) -> pd.DataFrame:
    """One row per signal found in ``bars``, with ``pos`` (row of the signal
    bar), ``direction`` and ``r{h}`` (realized percent, NaN if not scoreable).

    ``bars`` is load_intraday_bars' frame (Time tz-aware UTC); ``signals``
    has ``entry_time`` (tz-aware UTC instant) and ``trade_type``.
    """
    frame = bars.assign(Time=utc_to_eastern_naive(pd.DatetimeIndex(pd.to_datetime(bars['Time'], utc=True))))
    frame = frame.reset_index(drop=True)
    pos_index = pd.Index(frame['Time'])
    sig_et = utc_to_eastern_naive(pd.DatetimeIndex(pd.to_datetime(signals['entry_time'], utc=True)))
    pos = pos_index.get_indexer(sig_et)
    found = pos >= 0
    out = pd.DataFrame({
        'entry_time': pd.to_datetime(signals['entry_time'], utc=True).to_numpy()[found],
        'et': sig_et[found],
        'pos': pos[found],
        'direction': np.where(signals['trade_type'].astype(str).str.lower().to_numpy()[found] == 'call', 1, -1),
    })
    for h in holds:
        out[f'r{h}'] = realized_outcome(frame, out['pos'].to_numpy(), out['direction'].to_numpy(), hold=h, cost=cost)
    out.attrs['unmatched'] = int((~found).sum())
    return out


def one_at_a_time(pos: np.ndarray, hold: int) -> np.ndarray:
    """Mask of signals a single position could take: the next signal is
    taken only once the previous trade has exited (its signal bar is at or
    after the previous exit bar, signal + 1 + hold). ``pos`` must be sorted."""
    keep = np.zeros(len(pos), dtype=bool)
    free_at = -1
    for i, p in enumerate(pos):
        if p >= free_at:
            keep[i] = True
            free_at = p + 1 + hold
    return keep


def _stats(r: pd.Series, days: pd.Series) -> dict:
    n = int(r.notna().sum())
    if n == 0:
        return {'n': 0, 'days': 0, 'win_share': np.nan, 'avg_pct': np.nan, 'median_pct': np.nan,
                'std_pct': np.nan, 't': np.nan}
    v = r.dropna()
    std = float(v.std(ddof=1)) if n > 1 else np.nan
    t = float(v.mean() / (std / np.sqrt(n))) if n > 1 and std > 0 else np.nan
    return {'n': n, 'days': int(days[r.notna()].nunique()), 'win_share': float((v > 0).mean()),
            'avg_pct': float(v.mean()), 'median_pct': float(v.median()), 'std_pct': std, 't': t}


def summarise(scored: pd.DataFrame, holds, split: pd.Timestamp, ticker: str, strategy: str) -> pd.DataFrame:
    """Rows of (ticker, strategy, set, count, hold, period) statistics."""
    scored = scored.sort_values('pos', kind='mergesort').reset_index(drop=True)
    day = scored['et'].dt.normalize()
    period = np.where(scored['et'] < split, 'before', 'after')
    cols = [f'r{h}' for h in holds]
    common = scored[cols].notna().all(axis=1)
    rows = []
    for set_name, set_mask in (('own', pd.Series(True, index=scored.index)), ('common', common)):
        for h in holds:
            r = scored[f'r{h}'].where(set_mask)
            ok = r.notna().to_numpy()
            single = np.zeros(len(r), dtype=bool)
            single[ok] = one_at_a_time(scored['pos'].to_numpy()[ok], h)
            for count_name, cmask in (('all', np.ones(len(r), dtype=bool)), ('one_at_a_time', single)):
                rr = r.where(cmask)
                for per in ('all', 'before', 'after'):
                    pm = np.ones(len(r), dtype=bool) if per == 'all' else (period == per)
                    st = _stats(rr.where(pm), day)
                    rows.append({'ticker': ticker, 'strategy': strategy, 'set': set_name,
                                 'count': count_name, 'hold': h, 'period': per, **st})
    return pd.DataFrame(rows)


def recommend(summary: pd.DataFrame) -> pd.DataFrame:
    """Per ticker and strategy: the hold with the best one-at-a-time average
    on the common set BEFORE the split, and how that hold did AFTER it."""
    s = summary[(summary['set'] == 'common') & (summary['count'] == 'one_at_a_time')]
    out = []
    for (tk, strat), g in s.groupby(['ticker', 'strategy']):
        before = g[g['period'] == 'before'].dropna(subset=['avg_pct'])
        after = g[g['period'] == 'after'].set_index('hold')
        if before.empty:
            continue
        best = before.loc[before['avg_pct'].idxmax()]
        h = int(best['hold'])
        a = after.loc[h] if h in after.index else None
        a20 = after.loc[20] if 20 in after.index else None
        small = bool(best['n'] < SMALL_TRADES or best['days'] < SMALL_DAYS
                     or a is None or a['n'] < SMALL_TRADES or a['days'] < SMALL_DAYS)
        out.append({
            'ticker': tk, 'strategy': strat, 'chosen_hold': h,
            'before_n': int(best['n']), 'before_avg_pct': best['avg_pct'], 'before_t': best['t'],
            'after_n': None if a is None else int(a['n']),
            'after_avg_pct': None if a is None else a['avg_pct'],
            'after_win_share': None if a is None else a['win_share'],
            'after_avg_pct_hold20': None if a20 is None else a20['avg_pct'],
            'small_sample': small,
            'distinguishable_from_zero_before': bool(abs(best['t']) >= 2) if pd.notna(best['t']) else False,
        })
    return pd.DataFrame(out)


# ── Cloud SQL (read only) ──────────────────────────────────────────────────

def _read(engine, sql: str, params: dict) -> pd.DataFrame:
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        df = pd.read_sql(text(sql), conn, params=params)
        conn.rollback()
    return df


def _month_chunks(lo: pd.Timestamp, hi: pd.Timestamp):
    """[a, b) UTC windows cut at 06:00 UTC on the 1st (01:00 to 02:00 ET),
    so no session (04:00 to 20:00 ET) is split and holds stay inside one."""
    a = lo.normalize() - timedelta(days=1)
    while a < hi:
        b = (a + pd.offsets.MonthBegin(1)).normalize() + timedelta(hours=6)
        if b <= a:
            b = a + timedelta(days=32)
        yield a, min(b, hi + timedelta(days=1))
        a = b


def run(args) -> int:
    from gcp.database import get_engine
    from gcp.historical_signals import load_intraday_bars

    holds = tuple(int(h) for h in args.holds.split(','))
    split = pd.Timestamp(args.split)
    engine = get_engine()

    where, params = '1=1', {}
    if args.start:
        where += ' AND entry_time >= :start'
        params['start'] = pd.Timestamp(args.start, tz='UTC')
    if args.end:
        where += ' AND entry_time < :end'
        params['end'] = pd.Timestamp(args.end, tz='UTC')
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',') if t.strip()]
    else:
        tickers = _read(engine, f'SELECT DISTINCT ticker FROM historical_signals WHERE {where} ORDER BY 1',
                        params)['ticker'].tolist()

    summaries, unmatched = [], {}
    for tk in tickers:
        sig = _read(engine, f"""
            SELECT entry_time, trade_type, strategy
            FROM historical_signals
            WHERE ticker = :t AND {where}
            ORDER BY entry_time""", {**params, 't': tk})
        if sig.empty:
            continue
        sig['entry_time'] = pd.to_datetime(sig['entry_time'], utc=True)
        print(f'{tk}: {len(sig)} signals {sig.entry_time.min()} to {sig.entry_time.max()}', flush=True)
        parts = []
        for a, b in _month_chunks(sig['entry_time'].min(), sig['entry_time'].max()):
            s = sig[(sig['entry_time'] >= a) & (sig['entry_time'] < b)]
            if s.empty:
                continue
            bars = load_intraday_bars(tk, a.to_pydatetime(), b.to_pydatetime())
            if bars.empty:
                unmatched[tk] = unmatched.get(tk, 0) + len(s)
                continue
            for strat, ss in s.groupby('strategy'):
                sc = score_signals(bars, ss, holds, args.cost)
                sc['strategy'] = strat
                unmatched[tk] = unmatched.get(tk, 0) + sc.attrs['unmatched']
                # positions are per chunk; offset so one-at-a-time never links chunks
                sc['pos'] = sc['pos'] + len(parts) * 10_000_000
                parts.append(sc)
        if not parts:
            continue
        allsc = pd.concat(parts, ignore_index=True)
        for strat, g in allsc.groupby('strategy'):
            summaries.append(summarise(g, holds, split, tk, strat))

    if not summaries:
        print('no signals scored')
        return 1
    summary = pd.concat(summaries, ignore_index=True)
    summary.to_csv(args.out, index=False)
    rec = recommend(summary)
    rec_path = os.path.splitext(args.out)[0] + '_recommend.csv'
    rec.to_csv(rec_path, index=False)

    pd.set_option('display.width', 200)
    pd.set_option('display.max_rows', 2000)
    view = summary[(summary['set'] == 'own') & (summary['period'] == 'all')]
    view = view.pivot_table(index=['ticker', 'strategy', 'hold'], columns='count',
                            values=['n', 'win_share', 'avg_pct', 't'])
    print('\n== own set, whole period ==')
    print(view.round(4).to_string())
    print('\n== chosen on before, checked on after (common set, one at a time) ==')
    print(rec.round(4).to_string(index=False))
    print('\nunmatched signals (no bar at entry_time):', unmatched)
    print(f'\nwrote {args.out} and {rec_path}')
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--tickers', help='comma list; default every ticker in historical_signals')
    p.add_argument('--start', help='YYYY-MM-DD, entry_time from (UTC)')
    p.add_argument('--end', help='YYYY-MM-DD, entry_time before (UTC)')
    p.add_argument('--holds', default=','.join(str(h) for h in DEFAULT_HOLDS))
    p.add_argument('--cost', type=float, default=0.01)
    p.add_argument('--split', default='2026-05-01', help='Eastern date dividing before/after')
    p.add_argument('--out', default='/tmp/hold_sweep.csv')
    return run(p.parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())
