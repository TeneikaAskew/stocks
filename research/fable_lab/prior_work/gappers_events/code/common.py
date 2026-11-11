"""Shared helpers for the gappers_events lane."""
import glob, json, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LANE = os.path.normpath(os.path.join(HERE, '..'))
BARS = '/mnt/project-files/stocks-scorecard/inputs/bars_raw'
DAILY = '/mnt/project-files/strat-verify/ftfc-replay/raw'
T = ('SPY', 'QQQ', 'IWM')
PRIMARY = ('2026-05-01', '2026-11-10')
HOLDOUT = ('2025-03-03', '2026-04-30')

def window(day):
    return 'primary' if day >= PRIMARY[0] else 'holdout'

_bars = {}
def bars(t):
    if t not in _bars:
        b = pd.concat([pd.read_csv(f, parse_dates=['timestamp']) for f in sorted(glob.glob(f'{BARS}/{t}_1min_*.csv'))])
        _bars[t] = b.drop_duplicates('timestamp').set_index('timestamp').sort_index()
    return _bars[t]

def brief_rows():
    rows = json.load(open(f'{LANE}/brief_rows.json'))
    return {(r['day'], r['ticker'], r['cutoff']): r for r in rows}

def calendar():
    c = pd.read_csv(f'{LANE}/calendar/report_days.csv')
    return c

def _daysums(values, days, u=None):
    values = np.asarray(values, float); days = np.asarray(days)
    if u is None: u = np.unique(days)
    idx = np.searchsorted(u, days)
    return u, np.bincount(idx, weights=values, minlength=len(u)), np.bincount(idx, minlength=len(u)).astype(float)

def boot(values, days, stat='mean', n=2000, seed=7, all_days=None):
    """90% interval, resampling whole days (the three tickers on one day stay together).
    stat 'mean' (average per row) or 'sum' (total, e.g. total R)."""
    if len(values) == 0:
        return (np.nan, np.nan)
    u, s, c = _daysums(values, days, None if all_days is None else np.unique(np.asarray(all_days)))
    pick = np.random.default_rng(seed).integers(0, len(u), (n, len(u)))
    out = s[pick].sum(1) / (c[pick].sum(1) if stat == 'mean' else 1.0)
    return (float(np.percentile(out, 5)), float(np.percentile(out, 95)))

def boot_diff(a, da, b, db, stat='mean', n=2000, seed=7, all_days=None):
    """90% interval for stat(a) - stat(b), resampling the same days for both (paired by day).
    all_days: the full list of days in the window (needed for 'sum' so empty days count as zero)."""
    u = np.unique(np.concatenate([np.asarray(da), np.asarray(db)] + ([np.asarray(all_days)] if all_days is not None else [])))
    if len(u) == 0: return (np.nan, np.nan)
    _, sa, ca = _daysums(a, da, u); _, sb, cb = _daysums(b, db, u)
    pick = np.random.default_rng(seed).integers(0, len(u), (n, len(u)))
    if stat == 'mean':
        with np.errstate(invalid='ignore', divide='ignore'):
            out = sa[pick].sum(1) / ca[pick].sum(1) - sb[pick].sum(1) / cb[pick].sum(1)
        out = out[np.isfinite(out)]
    else:
        out = sa[pick].sum(1) - sb[pick].sum(1)
    return (float(np.percentile(out, 5)), float(np.percentile(out, 95))) if len(out) else (np.nan, np.nan)

def sim(h, l, o, c, side, entry, stop, target, start=0, last_entry=None, market=False):
    """Same trade rule as stocks-scorecard/week_summary.trade, on numpy arrays of one regular session.
    side 'long'/'short'. Stop-entry at `entry` from bar `start` (fill at entry, or the bar's open if already
    through); market=True fills at the open of bar `start`. No fill after bar index `last_entry`.
    Exit at stop (stop wins a same-bar tie, gaps through the stop fill at the open), target, or the last close.
    Returns dict(fill, i, px, R, how, exit_i) ; R in units of |fill - stop|."""
    up = side == 'long'; n = len(h)
    if stop is None or start >= n or (not market and (entry is None or (isinstance(entry, float) and np.isnan(entry)))):
        return None
    if market:
        i0, px = start, o[start]
    else:
        hit = (h[start:] >= entry) if up else (l[start:] <= entry)
        if not hit.any():
            return {'fill': False}
        i0 = start + int(np.argmax(hit))
        if last_entry is not None and i0 > last_entry:
            return {'fill': False}
        px = max(entry, o[i0]) if up else min(entry, o[i0])
    risk = abs(px - stop)
    if risk <= 0 or (up and stop >= px) or ((not up) and stop <= px):
        return {'fill': True, 'R': None, 'how': 'no risk', 'i': i0, 'px': px}
    for i in range(i0, n):
        s_hit = l[i] <= stop if up else h[i] >= stop
        if s_hit:
            ex = min(stop, o[i]) if up else max(stop, o[i])
            if i == i0:
                ex = stop
            return {'fill': True, 'i': i0, 'px': px, 'R': ((ex - px) if up else (px - ex)) / risk, 'how': 'stop', 'exit_i': i}
        if target is not None and (h[i] >= target if up else l[i] <= target):
            return {'fill': True, 'i': i0, 'px': px, 'R': abs(target - px) / risk, 'how': 'target', 'exit_i': i}
    return {'fill': True, 'i': i0, 'px': px, 'R': ((c[-1] - px) if up else (px - c[-1])) / risk, 'how': 'close', 'exit_i': n - 1}
