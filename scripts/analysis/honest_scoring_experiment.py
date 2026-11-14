#!/usr/bin/env python3
"""The Experiment of FEAT-SIGNAL-001's honest outcome scoring spec, as one script.

docs/superpowers/specs/2026-11-11-feat-signal-001-honest-outcome-scoring.md
ports the research lab's ``scoring_spec/verify_pct.py``,
``indicators/code/voter_run.py``, ``indicators/code/pct_profitable.py`` and
``scoring_spec/resolver_exp.py`` here, so the two Experiment tables can be
rebuilt from a checkout. It reads research data from the project files (read
only, never in the repo) and writes only to ``--out-dir``.

Table A, ``pct_profitable`` on the production voter's own signals::

    # optional: rebuild a ticker's voter signals with this checkout's
    # unchanged generate_technical_signals (4 to 10 minutes per ticker)
    python3 -I scripts/analysis/honest_scoring_experiment.py voter SPY --out-dir /tmp/hse
    # the table (about 3 minutes), from the lab's voter parquet by default
    python3 -I scripts/analysis/honest_scoring_experiment.py table-a [--signals-dir /tmp/hse] \
        [--out-dir /tmp/hse]

Table B, the brief's playbook legs scored three ways::

    python3 -I scripts/analysis/honest_scoring_experiment.py table-b \
        --base-checkout /tmp/wt-scoring [--sessions .../sessions.pkl] [--legs-out /tmp/legs.csv]

``--base-checkout`` is a clean origin/main checkout from before this change:
its ``resolve_leg`` is imported unchanged for the origin/main rows. The
"this spec" rows come from this checkout's implemented ``resolve_leg`` (rule
cross-fill-t1-v1). The ``week_summary.trade`` rows and the information-only
"held for T3" and "a third at each target" variants are the lab's own rules,
ported unchanged.

Table A's real exit is the lab's ``realized_outcomes`` ('time' rule), ported
unchanged: it counts an exit bar up to 15:55 by minute of day and does not
consult the NYSE calendar. The production rule (lib.trading_analysis
.realized_outcome) also requires the session's own close, so on a half day it
scores fewer signals; Table A is the lab's measurement and is reproduced as
the spec states it.

Python 3 with pandas 2.3, numpy and pyarrow. No network, no database.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import math
import os
import pickle
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

LAB = '/mnt/project-files/stocks-scorecard/research/fable_lab'
BARS_DIR = '/mnt/project-files/stocks-scorecard/inputs/bars_raw'
DAILY_DIR = '/mnt/project-files/strat-verify/ftfc-replay/raw'
SIGNALS_DIR = f'{LAB}/indicators/work'
SESSIONS = f'{LAB}/triggers_levels/work/sessions.pkl'
TICKERS = ['SPY', 'QQQ', 'IWM']
PRIMARY = ('2026-05-01', '2026-11-10')
HOLDOUT = ('2025-03-03', '2026-04-30')
LONG = ('2016-03-01', '2025-02-28')


# ── Table A: the lab's loaders and realized_outcomes, ported unchanged ─────

def window_of(dates):
    d = pd.to_datetime(pd.Series(dates)).dt.strftime('%Y-%m-%d').values
    return np.where((d >= PRIMARY[0]) & (d <= PRIMARY[1]), 'primary',
                    np.where((d >= HOLDOUT[0]) & (d <= HOLDOUT[1]), 'holdout',
                             np.where((d >= LONG[0]) & (d <= LONG[1]), 'long', 'other')))


def load_bars(ticker, bars_dir=BARS_DIR):
    fs = sorted(os.path.join(bars_dir, f) for f in os.listdir(bars_dir)
                if f.startswith(f'{ticker}_1min_') and f.endswith('.csv'))
    df = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    df['Time'] = pd.to_datetime(df['timestamp'])
    df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Last', 'volume': 'Volume'})
    df = df[['Time', 'Open', 'High', 'Low', 'Last', 'Volume']]
    return df.drop_duplicates('Time').sort_values('Time').reset_index(drop=True), len(fs)


def wilder(x, n):
    return x.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def daily_bars(ticker, bars, daily_dir=DAILY_DIR):
    """Daily OHLC: the AV daily file where it has bars, regular-hours 1-min aggregates after."""
    D0 = pd.read_csv(f'{daily_dir}/{ticker}_daily_adjusted.csv', parse_dates=['timestamp']).sort_values('timestamp')
    D0 = D0.rename(columns={'timestamp': 'Date', 'open': 'O', 'high': 'H', 'low': 'L', 'close': 'C'})
    mod = bars['Time'].dt.hour * 60 + bars['Time'].dt.minute
    r = bars[(mod >= 570) & (mod < 960)]
    g = r.groupby(r['Time'].dt.normalize())
    D1 = pd.DataFrame({'O': g['Open'].first(), 'H': g['High'].max(), 'L': g['Low'].min(),
                       'C': g['Last'].last(), 'n': g.size()})
    D1 = D1[D1['n'] >= 200].drop(columns='n')
    D1.index.name = 'Date'
    D0 = D0.set_index('Date')[['O', 'H', 'L', 'C']]
    D1 = D1[D1.index > D0.index.max()]
    return pd.concat([D0, D1]).sort_index()


RTH_OPEN, LAST_SIGNAL_MIN, HOLD = 570, 934, 20
BRACKET_ATR = 0.15
COST = 0.01


def realized_outcomes(mod, day_id, O, H, L, C, atr_d, sig_idx, direction, exit_rule='time',
                      rth_only=True, next_bar_entry=True, hold=HOLD, bracket_atr=BRACKET_ATR, cost=COST):
    """The lab's research rule (indicators/code/proposed_pct_profitable.py), unchanged.
    Returns (ok, ret_pct, r_mult)."""
    sig_idx = np.asarray(sig_idx)
    direction = np.asarray(direction, float)
    n = len(C)
    ent = sig_idx + (1 if next_bar_entry else 0)
    ext = ent + hold
    ok = ext < n
    e = np.where(ok, ent, 0)
    x = np.where(ok, ext, 0)
    if rth_only:
        ok &= (mod[sig_idx] >= RTH_OPEN) & (mod[sig_idx] <= LAST_SIGNAL_MIN) & (day_id[x] == day_id[sig_idx]) & (mod[x] <= 955)
    px_in = O[e] if next_bar_entry else C[sig_idx]
    px_out = O[x] if next_bar_entry else C[x]
    pnl = (px_out - px_in) * direction
    if exit_rule == 'bracket':
        dist = bracket_atr * atr_d[sig_idx]
        done = np.zeros(len(sig_idx), bool)
        for j in range(hold):
            b = np.minimum(e + j, n - 1)
            adverse = np.where(direction > 0, px_in - L[b], H[b] - px_in)
            favor = np.where(direction > 0, H[b] - px_in, px_in - L[b])
            gap = (O[b] - px_in) * direction
            stop = (~done) & (adverse >= dist)
            pnl = np.where(stop, np.minimum(-dist, gap), pnl)
            done |= stop
            tgt = (~done) & (favor >= dist)
            pnl = np.where(tgt, np.where(j > 0, np.maximum(dist, gap), dist), pnl)
            done |= tgt
        r = (pnl - cost) / dist
    else:
        r = np.full(len(sig_idx), np.nan)
    ret = (pnl - cost) / px_in * 100
    return ok, ret, r


def cmd_voter(args):
    """Port of indicators/code/voter_run.py with this checkout's MarketAnalyzer."""
    from lib.trading_analysis import MarketAnalyzer
    bars, nfiles = load_bars(args.ticker, args.bars_dir)
    ma = MarketAnalyzer()
    with contextlib.redirect_stdout(io.StringIO()):
        enriched = ma.add_technical_indicators(bars.copy())
        sig = ma.generate_technical_signals(enriched)
    keep = ['entry_time', 'trade_type', 'entry_price', 'duration_minutes', 'return_pct', 'best_return',
            'signal_strength', 'exit_time', 'exit_price', 'entry_rsi', 'exit_rsi'] + [
        c for c in sig.columns if c.startswith('return_') and c.endswith('min')]
    sig = sig[[c for c in keep if c in sig.columns]]
    os.makedirs(args.out_dir, exist_ok=True)
    out = os.path.join(args.out_dir, f'{args.ticker}_voter_signals.parquet')
    sig.to_parquet(out, index=False)
    print(args.ticker, 'files', nfiles, 'bars', len(bars), 'signals', len(sig), '->', out, flush=True)


def table_a_frames(ticker, args):
    """Port of indicators/code/pct_profitable.py for one ticker: (per-signal frame, scoreable count)."""
    bars, _ = load_bars(ticker, args.bars_dir)
    D = daily_bars(ticker, bars, args.daily_dir)
    tr = pd.concat([D['H'] - D['L'], (D['H'] - D['C'].shift()).abs(), (D['L'] - D['C'].shift()).abs()],
                   axis=1).max(axis=1)
    atr_prev = wilder(tr, 14).shift(1)
    t = bars['Time']
    mod = (t.dt.hour * 60 + t.dt.minute).values
    dnorm = t.dt.normalize()
    day_id = dnorm.factorize()[0]
    atr_d = dnorm.map(atr_prev).ffill().values
    O, H, L, C = (bars[c].values for c in ['Open', 'High', 'Low', 'Last'])
    sig = pd.read_parquet(os.path.join(args.signals_dir, f'{ticker}_voter_signals.parquet'))
    pos = pd.Series(np.arange(len(bars)), index=t.values)
    si = pos.reindex(pd.to_datetime(sig['entry_time']).values).values.astype(int)
    dr = np.where(sig['trade_type'] == 'call', 1, -1)
    week = pd.to_datetime(sig['entry_time']).dt.to_period('W-SUN').dt.start_time.dt.date.values
    df = pd.DataFrame({'ticker': ticker, 'week': week, 'old': (sig['return_pct'].values > 0).astype(float)})
    rth = (mod[si] >= 570) & (mod[si] <= 934)
    df['rth'] = rth
    df['f1_rth_only_best_of_20'] = np.where(rth, df['old'], np.nan)
    ok, ret, _ = realized_outcomes(mod, day_id, O, H, L, C, atr_d, si, dr, 'time', rth_only=True,
                                   next_bar_entry=False, cost=0)
    df['f2_rth_close_after_20'] = np.where(ok, ret > 0, np.nan)
    ok, ret, _ = realized_outcomes(mod, day_id, O, H, L, C, atr_d, si, dr, 'time')
    scoreable = int(ok.sum())
    df['fixedA_time_exit'] = np.where(ok, ret > 0, np.nan)
    df['fixedA_ret_bps'] = np.where(ok, ret * 100, np.nan)
    ok, ret, r = realized_outcomes(mod, day_id, O, H, L, C, atr_d, si, dr, 'bracket')
    df['fixedB_bracket'] = np.where(ok, r > 0, np.nan)
    df['fixedB_R'] = np.where(ok, r, np.nan)
    ok, ret, _ = realized_outcomes(mod, day_id, O, H, L, C, atr_d, si, dr, 'time', rth_only=False)
    df['allhours_time_exit'] = np.where(ok, ret > 0, np.nan)
    okA = df['fixedA_time_exit'].notna().values
    keep = np.zeros(len(df), bool)
    nxt = -1
    for j in np.where(okA)[0]:
        if si[j] >= nxt:
            keep[j] = True
            nxt = si[j] + 21
    df['fixedA_one_at_a_time'] = np.where(keep, df['fixedA_time_exit'], np.nan)
    df['window'] = window_of(pd.to_datetime(sig['entry_time']).dt.normalize())
    return df, scoreable


def _summary(ticker, df):
    rows = []
    for wn, gg in [('all', df)] + [(k, v) for k, v in df.groupby('window') if k != 'other']:
        rows.append(dict(
            ticker=ticker, window=wn, signals_all_hours=len(gg), share_outside_regular_hours=1 - gg['rth'].mean(),
            old_pct_profitable=gg['old'].mean(), step1_regular_hours_only=gg['f1_rth_only_best_of_20'].mean(),
            step2_close_after_20min=gg['f2_rth_close_after_20'].mean(),
            new_A_time_exit=gg['fixedA_time_exit'].mean(), avg_net_bps_A=gg['fixedA_ret_bps'].mean(),
            new_B_bracket=gg['fixedB_bracket'].mean(), avg_net_R_B=gg['fixedB_R'].mean(),
            new_A_one_at_a_time=gg['fixedA_one_at_a_time'].mean(),
            trades_one_at_a_time=int(gg['fixedA_one_at_a_time'].count()),
            all_hours_time_exit=gg['allhours_time_exit'].mean(), weeks=gg['week'].nunique(),
            weekly_new_A_min=gg.groupby('week')['fixedA_time_exit'].mean().min(),
            weekly_new_A_max=gg.groupby('week')['fixedA_time_exit'].mean().max(),
            weekly_old_min=gg.groupby('week')['old'].mean().min(),
            weekly_old_max=gg.groupby('week')['old'].mean().max()))
    return rows


def _pct_bare(x):
    """A share as the summary CSV stores it (4 dp), in percent to 1 dp, half up."""
    d = Decimal(f'{float(x):.4f}') * 100
    return str(d.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def _pct(x):
    return _pct_bare(x) + '%'


def cmd_table_a(args):
    summaries, scoreable = [], {}
    for T in TICKERS:
        df, scoreable[T] = table_a_frames(T, args)
        summaries.extend(_summary(T, df))
        print(T, 'signals', len(df), 'old', round(df['old'].mean(), 4),
              'A', round(df['fixedA_time_exit'].mean(), 4), scoreable[T],
              'B', round(df['fixedB_bracket'].mean(), 4), file=sys.stderr, flush=True)
    S = pd.DataFrame(summaries)
    if args.out_dir:
        os.makedirs(args.out_dir, exist_ok=True)
        out = S.copy()
        num = out.select_dtypes(float).columns
        out[num] = out[num].round(4)
        out.to_csv(os.path.join(args.out_dir, 'pct_profitable_summary.csv'), index=False)
    a = {T: S[(S.ticker == T) & (S.window == 'all')].iloc[0] for T in TICKERS}
    h = {T: S[(S.ticker == T) & (S.window == 'holdout')].iloc[0] for T in TICKERS}
    p = {T: S[(S.ticker == T) & (S.window == 'primary')].iloc[0] for T in TICKERS}

    def row(label, cells):
        return f'| {label} | ' + ' | '.join(cells) + ' |'

    weeks = int(a[TICKERS[0]]['weeks'])
    lines = [
        '### Table A: `pct_profitable`, the voter\'s own signals, 2025-03-03 to 2026-11-10',
        '',
        '| Measure | ' + ' | '.join(TICKERS) + ' |',
        '|---|---|---|---|',
        row('Signals, all hours', [f"{int(a[T]['signals_all_hours']):,}" for T in TICKERS]),
        row('Old `pct_profitable` (served today)', [_pct(a[T]['old_pct_profitable']) for T in TICKERS]),
        row('Regular hours only, still best of 20 closes', [_pct(a[T]['step1_regular_hours_only']) for T in TICKERS]),
        row('+ the close 20 minutes later instead of the best close',
            [_pct(a[T]['step2_close_after_20min']) for T in TICKERS]),
        row('**Real exit (this spec): next-bar open, open 20 bars later, 1 cent**',
            [f"**{_pct(a[T]['new_A_time_exit'])}**" for T in TICKERS]),
        row('Signals scoreable under the real exit', [f'{scoreable[T]:,}' for T in TICKERS]),
        row('Same, one position at a time (' + ' / '.join(f"{int(a[T]['trades_one_at_a_time']):,}" for T in TICKERS)
            + ' trades)', [_pct(a[T]['new_A_one_at_a_time']) for T in TICKERS]),
        row('Average net result, real exit (bps per signal)',
            [f"{round(float(a[T]['avg_net_bps_A']), 4):+.2f}" for T in TICKERS]),
        row('Bracket of 0.15 x prior-day ATR14, information only', [_pct(a[T]['new_B_bracket']) for T in TICKERS]),
        row(f'Weekly range, old ({weeks} weeks)',
            [f"{_pct_bare(a[T]['weekly_old_min'])} to {_pct(a[T]['weekly_old_max'])}" for T in TICKERS]),
        row('Weekly range, real exit',
            [f"{_pct_bare(a[T]['weekly_new_A_min'])} to {_pct(a[T]['weekly_new_A_max'])}" for T in TICKERS]),
        row('Holdout: old / real exit',
            [f"{_pct(h[T]['old_pct_profitable'])} / {_pct(h[T]['new_A_time_exit'])}" for T in TICKERS]),
        row('Primary: old / real exit',
            [f"{_pct(p[T]['old_pct_profitable'])} / {_pct(p[T]['new_A_time_exit'])}" for T in TICKERS]),
    ]
    print('\n'.join(lines))


# ── Table B: three rules on the brief's playbook legs ──────────────────────

def ok(x):
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x) and x > 0


def _load_base_resolve_leg(checkout):
    path = Path(checkout) / 'gcp' / 'premarket_playbook_resolver.py'
    spec = importlib.util.spec_from_file_location('origin_main_premarket_playbook_resolver', path)
    mod = importlib.util.module_from_spec(spec)
    # Registered before running so its dataclasses resolve; its own imports
    # (lib.eastern_time) are unchanged by this spec.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.resolve_leg


def main_rule(resolve, side, trig, stop, tg, bars):
    out = resolve('call' if side > 0 else 'put', trig, stop, tg, bars)
    if out.trigger_hit_ts is None or out.eod_pnl_pct is None:
        return None
    pnl = out.eod_pnl_pct / 100 * trig * 1.0
    stop_between = False
    ts = [out.t1_hit_ts, out.t2_hit_ts, out.t3_hit_ts]
    hit = [t for t in ts if t is not None]
    if hit and out.stop_hit_ts is not None and out.t1_hit_ts is not None and out.stop_hit_ts > out.t1_hit_ts:
        last = max(i for i, t in enumerate(ts) if t is not None)
        if last > 0 and ts[last] > out.stop_hit_ts:
            stop_between = True
    return dict(pnl=pnl, risk=abs(trig - stop) if ok(stop) else np.nan, stop_between=stop_between)


def weekly_rule(s, side, trig, stop, t1):
    """stocks-scorecard/week_summary.trade as the lab ported it."""
    o, h, l, c = s['o'], s['h'], s['l'], s['c']
    up = side > 0
    if not ok(stop):
        return None
    m = (h >= trig) if up else (l <= trig)
    if not m.any():
        return None
    i0 = int(np.argmax(m))
    px = max(trig, o[i0]) if up else min(trig, o[i0])
    risk = abs(px - stop)
    if risk <= 0:
        return None
    behind = ok(t1) and ((up and o[i0] >= t1) or (not up and o[i0] <= t1))
    for i in range(i0, len(o)):
        if (up and l[i] <= stop) or (not up and h[i] >= stop):
            ex = min(stop, o[i]) if up else max(stop, o[i])
            g = (ex - px) if up else (px - ex)
            how = 'stop'
            break
        if ok(t1) and ((up and h[i] >= t1) or (not up and l[i] <= t1)):
            g = abs(t1 - px)
            how = 'T1'
            break
    else:
        g = (c[-1] - px) if up else (px - c[-1])
        how = 'close'
    return dict(pnl=g, risk=risk, R=g / risk, how=how, open_past_t1=bool(behind and how == 'T1'))


def spec_rule_lab(s, side, trig, stop, tg, last=False):
    """The lab's statement of this spec's rule; used here only for the
    information-only variant held for the farthest target (last=True)."""
    o, h, l, c = s['o'], s['h'], s['l'], s['c']
    up = side > 0
    n = len(o)
    if (up and o[0] >= trig) or (not up and o[0] <= trig):
        return dict(status='gap_through')
    m = (h >= trig) if up else (l <= trig)
    if not m.any():
        return dict(status='not_triggered')
    i0 = int(np.argmax(m))
    px = trig if i0 == 0 else (max(trig, o[i0]) if up else min(trig, o[i0]))
    if not ok(stop) or (up and stop >= px) or (not up and stop <= px):
        return dict(status='invalid_stop')
    risk = abs(px - stop)
    tgts = [t for t in tg if ok(t) and ((up and t > px) or (not up and t < px))]
    t1 = (tgts[-1] if last else tgts[0]) if tgts else None
    for i in range(i0, n):
        if (up and l[i] <= stop) or (not up and h[i] >= stop):
            ex = stop if i == i0 else (min(stop, o[i]) if up else max(stop, o[i]))
            g = (ex - px) if up else (px - ex)
            return dict(status='filled', pnl=g, risk=risk, R=g / risk, how='stop')
        if i > i0 and t1 is not None and ((up and h[i] >= t1) or (not up and l[i] <= t1)):
            g = abs(t1 - px)
            return dict(status='filled', pnl=g, risk=risk, R=g / risk, how='T1')
    g = (c[-1] - px) if up else (px - c[-1])
    return dict(status='filled', pnl=g, risk=risk, R=g / risk, how='close')


def thirds_rule(s, side, trig, stop, tg):
    """Information only: same entry and ordering, a third out at each target beyond the fill."""
    o, h, l, c = s['o'], s['h'], s['l'], s['c']
    up = side > 0
    n = len(o)
    base = spec_rule_lab(s, side, trig, stop, tg)
    if base['status'] != 'filled':
        return base
    m = (h >= trig) if up else (l <= trig)
    i0 = int(np.argmax(m))
    px = trig if i0 == 0 else (max(trig, o[i0]) if up else min(trig, o[i0]))
    risk = abs(px - stop)
    tgts = [t for t in tg if ok(t) and ((up and t > px) or (not up and t < px))]
    if not tgts:
        return base
    frac = 1.0 / len(tgts)
    pos = 1.0
    g = 0.0
    k = 0
    for i in range(i0, n):
        if (up and l[i] <= stop) or (not up and h[i] >= stop):
            ex = stop if i == i0 else (min(stop, o[i]) if up else max(stop, o[i]))
            g += pos * ((ex - px) if up else (px - ex))
            pos = 0.0
            break
        while i > i0 and k < len(tgts) and ((up and h[i] >= tgts[k]) or (not up and l[i] <= tgts[k])):
            g += frac * abs(tgts[k] - px)
            pos -= frac
            k += 1
        if pos <= 1e-9:
            break
    if pos > 1e-9:
        g += pos * ((c[-1] - px) if up else (px - c[-1]))
    return dict(status='filled', R=g / risk)


def implemented_rule(side, trig, stop, tg, bars):
    """This checkout's resolve_leg (rule cross-fill-t1-v1); R over |fill - stop|."""
    from gcp.premarket_playbook_resolver import resolve_leg
    out = resolve_leg('call' if side > 0 else 'put', trig, stop if ok(stop) else None,
                      [t if ok(t) else None for t in tg], bars)
    if out.entry_status != 'filled':
        return dict(status=out.entry_status)
    pnl = out.eod_pnl_pct / 100 * out.fill_price
    return dict(status='filled', R=pnl / abs(out.fill_price - stop), how=out.exit_reason, fill=out.fill_price)


def table_b_legs(args):
    from lib.eastern_time import ET_NAME
    base_resolve = _load_base_resolve_leg(args.base_checkout)
    with open(args.sessions, 'rb') as fh:
        sessions = pickle.load(fh)
    rows = []
    for s in sessions:
        b = s['brief']
        w = 'primary' if s['day'] >= PRIMARY[0] else 'holdout'
        t0 = pd.Timestamp(s['day'] + ' 09:30', tz=ET_NAME)
        bars = pd.DataFrame({'time': [t0 + pd.Timedelta(minutes=int(k)) for k in range(len(s['o']))],
                             'open': s['o'], 'high': s['h'], 'low': s['l'], 'close': s['c']})
        for side, k in ((1, 'calls'), (-1, 'puts')):
            trig, stop = b.get(f'{k}_trigger_price'), b.get(f'{k}_stop_price')
            tg = [b.get(f'{k}_t{j}_price') for j in (1, 2, 3)]
            if not ok(trig):
                continue
            gap = (side > 0 and s['o'][0] >= trig) or (side < 0 and s['o'][0] <= trig)
            mr = main_rule(base_resolve, side, trig, stop, tg, bars)
            wr = weekly_rule(s, side, trig, stop, tg[0])
            sr = implemented_rule(side, trig, stop, tg, bars)
            s3 = spec_rule_lab(s, side, trig, stop, tg, last=True)
            st = thirds_rule(s, side, trig, stop, tg)
            rows.append(dict(
                window=w, day=s['day'], ticker=s['ticker'], side=k, gap=gap,
                m_fill=mr is not None, m_pnl=mr['pnl'] if mr else np.nan,
                m_R=(mr['pnl'] / mr['risk']) if mr and mr['risk'] == mr['risk'] and mr['risk'] > 0 else np.nan,
                m_stop_between=mr['stop_between'] if mr else False,
                w_fill=wr is not None, w_R=wr['R'] if wr else np.nan,
                w_open_past_t1=wr['open_past_t1'] if wr else False,
                s_status=sr['status'], s_R=sr.get('R', np.nan), s_how=sr.get('how'),
                s3_R=s3.get('R', np.nan), sth_R=st.get('R', np.nan)))
    return pd.DataFrame(rows)


def cmd_table_b(args):
    D = table_b_legs(args)
    if args.legs_out:
        D.to_csv(args.legs_out, index=False)
    groups = {w: g for w, g in D.groupby('window')}
    groups['both'] = D
    order = ('holdout', 'primary', 'both')

    def main_stats(g):
        mf = g[g.m_fill]
        return mf, len(mf), (mf.m_pnl > 0).mean(), mf.m_R.sum()

    def week_stats(g):
        wf = g[g.w_fill]
        return wf, len(wf), (wf.w_R > 0).mean(), wf.w_R.sum()

    def spec_stats(g):
        sf = g[g.s_status == 'filled']
        return sf, len(sf), int((g.s_status == 'gap_through').sum()), (sf.s_R > 0).mean(), sf.s_R.sum()

    lines = ['### Table B: the brief\'s playbook legs scored three ways, '
             f'{D[["day", "ticker"]].drop_duplicates().shape[0]:,} ticker-days, both sides', '',
             'R = price result over |entry - stop|, no cost (the resolver books none).', '',
             '| Rule | Window | Fills | Wins | Total R |', '|---|---|---|---|---|']
    for w in order:
        _, n, win, R = main_stats(groups[w])
        lines.append(f'| origin/main `resolve_leg` | {w} | {n:,} | {win:.1%} | {R:+.2f} |')
    mf, *_ = main_stats(D)
    lines.append(f'| of which the session opened past the trigger | both | {int(mf.gap.sum()):,} | | '
                 f'{mf[mf.gap].m_R.sum():+.2f} |')
    lines.append(f'| of which a later target was booked after the stop | both | {int(mf.m_stop_between.sum()):,} | | '
                 f'{mf[mf.m_stop_between].m_R.sum():+.2f} |')
    for w in order:
        _, n, win, R = week_stats(groups[w])
        lines.append(f'| `week_summary.trade` | {w} | {n:,} | {win:.1%} | {R:+.2f} |')
    past = [week_stats(groups[w])[0] for w in order]
    lines.append('| of which T1 booked with the open already past T1 | holdout / primary / both | '
                 + ' / '.join(str(int(wf.w_open_past_t1.sum())) for wf in past) + ' | | '
                 + ' / '.join(f'{wf[wf.w_open_past_t1].w_R.sum():+.2f}' for wf in past) + ' |')
    for w in order:
        _, n, gap, win, R = spec_stats(groups[w])
        lines.append(f'| **this spec** | {w} | {n:,} ({gap} gap_through) | {win:.1%} | {R:+.2f} |')
    sf, *_ = spec_stats(D)
    how = sf.s_how.value_counts()
    ng = mf[~mf.gap]
    wf_all = week_stats(D)[0]
    wng = wf_all[~wf_all.gap]
    lines += ['',
              f"This spec's exits over both windows: T1 {int(how.get('t1', 0))}, stop {int(how.get('stop', 0))}, "
              f"close {int(how.get('close', 0))}. On the {len(ng):,} legs that did not open past the trigger, "
              f"origin/main's resolver books {ng.m_R.sum():+.2f} R where `week_summary.trade` books "
              f"{wng.w_R.sum():+.2f} R. For information, the same entry and ordering held for T3 gives "
              f"{sf.s3_R.sum():+.2f} R ({(sf.s3_R > 0).mean():.1%} wins), and a third at each of T1, T2 and T3 "
              f"gives {sf.sth_R.sum():+.2f} R ({(sf.sth_R > 0).mean():.1%} wins)."]
    print('\n'.join(lines))


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    v = sub.add_parser('voter', help="rebuild one ticker's voter signals with this checkout")
    v.add_argument('ticker')
    v.add_argument('--out-dir', required=True)
    v.add_argument('--bars-dir', default=BARS_DIR)
    v.set_defaults(func=cmd_voter)
    a = sub.add_parser('table-a', help='pct_profitable: old, real exit, bracket, per window')
    a.add_argument('--signals-dir', default=SIGNALS_DIR)
    a.add_argument('--bars-dir', default=BARS_DIR)
    a.add_argument('--daily-dir', default=DAILY_DIR)
    a.add_argument('--out-dir', default=None, help='write pct_profitable_summary.csv here')
    a.set_defaults(func=cmd_table_a)
    b = sub.add_parser('table-b', help='the playbook legs under origin/main, week_summary and this spec')
    b.add_argument('--base-checkout', required=True, help='a clean origin/main checkout from before this change')
    b.add_argument('--sessions', default=SESSIONS)
    b.add_argument('--legs-out', default=None, help='write one row per leg here')
    b.set_defaults(func=cmd_table_b)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == '__main__':
    sys.exit(main())
