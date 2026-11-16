"""Read-only measurement of prior-close prints in premarket one-minute bars.

usage: measure.py <worktree> <bars_root> <daily_csv> <out_dir> <TICKER>

Writes <out_dir>/sessions_<T>.pkl (one record per premarket session).
Nothing here writes to the repo, a database or a bucket.
"""
import sys, json, pickle
from datetime import time
import numpy as np, pandas as pd

WT, BARS, DAILY, OUT, T = sys.argv[1:6]
sys.path.insert(0, WT)
import lib.indicators as ind                                    # noqa: E402
from lib.indicators import calculate_premarket_context as cpc   # noqa: E402
from lib.indicators import premarket_print_filter               # noqa: E402
from lib.strat_levels import price_cents                        # noqa: E402
from lib.eastern_time import utc_to_eastern_naive, previous_session  # noqa: E402
from gcp.fetchers.export_intraday_bars import read_bars         # noqa: E402

MINV = ind.PM_MIN_EXTREME_VOLUME
assert MINV == 100
D_FRAC = 0.0025
TOLS = (0, 1, 2, 5, 10)
XS = (0.001, 0.0025, 0.005)


def cents_arr(a):
    return np.array([price_cents(x) if x == x else -10**9 for x in a], dtype=np.int64)


def engine(raw, cand, v, pc, pc_c, *, min_vol=MINV, stale=True, drop=None, body_ok=None):
    """The three shipped extreme rules on numpy arrays, with hooks.

    raw: dict o,h,l,c of raw premarket prices (body_there reads raw open/close).
    cand: dict o,h,l,c the candidates start from (raw, or the print filter's output).
    drop: optional dict of bool arrays, extra values that are not candidates.
    body_ok: optional dict o,c of bool arrays; False = that open/close is not a body term.
    Returns (pre_high, pre_low, high_setter, low_setter); setter = (bar index, kind).
    """
    o, h, l, c = (cand[k].astype(float).copy() for k in 'ohlc')
    if stale and pc is not None and pc == pc and pc > 0:
        at = {k: cents_arr(x) == pc_c for k, x in (('o', raw['o']), ('c', raw['c']), ('h', h), ('l', l))}
        body_there = at['o'] | at['c']
        h[at['h'] & ~body_there] = np.nan
        l[at['l'] & ~body_there] = np.nan
    if drop is not None:
        for k, a in (('o', o), ('h', h), ('l', l), ('c', c)):
            a[drop[k]] = np.nan
    thin = v < min_vol          # NaN volume compares False and stays
    for a in (o, h, l, c):
        a[thin] = np.nan
    bo, bc = o.copy(), c.copy()
    if body_ok is not None:
        bo[~body_ok['o']] = np.nan
        bc[~body_ok['c']] = np.nan
    bodies = np.concatenate([bo, bc]); bodies = bodies[~np.isnan(bodies)]
    hi_idx = np.where(~np.isnan(h))[0]; lo_idx = np.where(~np.isnan(l))[0]
    hs = hi_idx[np.argsort(-h[hi_idx], kind='stable')]
    ls = lo_idx[np.argsort(l[lo_idx], kind='stable')]
    ht = ([float(h[hs[1]])] if len(hs) >= 2 else []) + ([float(bodies.max())] if len(bodies) else [])
    lt = ([float(l[ls[1]])] if len(ls) >= 2 else []) + ([float(bodies.min())] if len(bodies) else [])
    ph = max(ht) if ht else None
    pl = min(lt) if lt else None

    def setter(val, second_idx, second_val):
        if val is None:
            return None
        for k, a in (('open', bo), ('close', bc)):
            w = np.where(a == val)[0]
            if len(w):
                return (int(w[0]), k)
        return (int(second_idx), 'second_wick') if second_val == val else None
    hset = setter(ph, hs[1] if len(hs) >= 2 else -1, float(h[hs[1]]) if len(hs) >= 2 else None)
    lset = setter(pl, ls[1] if len(ls) >= 2 else -1, float(l[ls[1]]) if len(ls) >= 2 else None)
    return ph, pl, hset, lset


def pc_drop(raw, cents, pc, pc_c, tol, d_frac=D_FRAC):
    """P1 (tol 0) and P2 (tol 5): a price within tol cents of the prior close is not a
    candidate when every remaining price of its bar is more than d_frac x prior close away."""
    D = d_frac * pc
    at = {k: np.abs(cents[k] - pc_c) <= tol for k in 'ohlc'}
    near_rest = np.zeros(len(raw['o']), bool); any_at = near_rest.copy(); any_rest = near_rest.copy()
    for k in 'ohlc':
        valid = ~np.isnan(raw[k])
        any_at |= at[k] & valid
        any_rest |= ~at[k] & valid
        near_rest |= ~at[k] & valid & (np.abs(raw[k] - pc) <= D)
    bar = any_at & any_rest & ~near_rest
    return {k: at[k] & bar for k in 'ohlc'}, bar


def pc_drop_ctx(raw, cents, v, pc, pc_c, tol, d_frac=D_FRAC, win=5):
    """P4: a price within tol cents of the prior close is not a candidate when the
    trading around it is elsewhere: the median of the prices NOT within tol cents of
    the prior close, over the non-thin bars from win before to win after (the bar
    itself included), is more than d_frac x prior close away. A bar wholly at the
    prior close is judged by its neighbours. No such price in the window: kept."""
    D = d_frac * pc
    n = len(v)
    at = {k: np.abs(cents[k] - pc_c) <= tol for k in 'ohlc'}
    ok_bar = ~(v < MINV)
    stack = np.vstack([np.where(~at[k] & ok_bar, raw[k], np.nan) for k in 'ohlc'])   # 4 x n
    bar = np.zeros(n, bool)
    has_at = at['o'] | at['h'] | at['l'] | at['c']
    for i in np.where(has_at)[0]:
        w = stack[:, max(0, i - win): i + win + 1]
        w = w[~np.isnan(w)]
        if len(w) and abs(float(np.median(w)) - pc) > D:
            bar[i] = True
    return {k: at[k] & bar for k in 'ohlc'}, bar


def median_drop(raw, v, d_frac, win=5):
    """P5 (no prior close needed): a price is not a candidate when it is more than
    d_frac away from the median of all four prices of the non-thin bars from win
    before to win after its bar (the bar itself included)."""
    n = len(v)
    ok_bar = ~(v < MINV)
    stack = np.vstack([np.where(ok_bar, raw[k], np.nan) for k in 'ohlc'])
    ref = np.full(n, np.nan)
    for i in range(n):
        w = stack[:, max(0, i - win): i + win + 1]
        w = w[~np.isnan(w)]
        if len(w):
            ref[i] = np.median(w)
    with np.errstate(invalid='ignore'):
        return {k: np.abs(raw[k] - ref) > d_frac * ref for k in 'ohlc'}


def isolated_bodies(raw, v, d_frac):
    """P3: an open or close is a body term only if another non-thin bar within the
    next or previous 2 bars has any price within d_frac x that price of it."""
    n = len(v)
    okbar = ~(v < MINV)
    res = {}
    for k in 'oc':
        a = raw[k]; good = np.zeros(n, bool)
        for s in (-2, -1, 1, 2):
            j = np.arange(n) + s
            valid = (j >= 0) & (j < n)
            jj = np.clip(j, 0, n - 1)
            near = np.zeros(n, bool)
            for kk in 'ohlc':
                near |= np.abs(raw[kk][jj] - a) <= d_frac * a
            good |= valid & okbar[jj] & near
        res[k] = good
    return res


def longest_run(mask):
    best = cur = 0
    for m in mask:
        cur = cur + 1 if m else 0
        best = max(best, cur)
    return best


def run_near(raw, v, value, frac=0.001):
    """Longest run of consecutive non-thin bars with all four prices within frac of value."""
    if value is None:
        return 0
    m = ~(v < MINV)
    for k in 'ohlc':
        m &= np.abs(raw[k] - value) <= frac * value
    return longest_run(m)


def main():
    daily = pd.read_csv(DAILY, usecols=['ticker', 'date', 'close', 'pfp_text'], low_memory=False)
    daily = daily[daily.ticker == T].set_index('date')
    man = json.load(open(f'{BARS}/{T}/manifest.json'))
    keys = sorted(man['months'])
    bars, months = read_bars(BARS, T, keys[0], keys[-1])
    et = utc_to_eastern_naive(bars['ts'])
    bars['et'] = et
    tod = et.dt.time
    pre = bars[(tod >= ind.PREMARKET_START) & (tod < ind.REGULAR_SESSION_OPEN)].copy()
    pre['day'] = pre['et'].dt.date
    meta = {'ticker': T, 'months': [keys[0], keys[-1], len(keys)], 'bars': len(bars),
            'first_ts': str(bars.ts.iloc[0]), 'last_ts': str(bars.ts.iloc[-1]),
            'inferred_rows': int(sum(m.get('inferred_rows') or 0 for m in months)),
            'basis_states': pd.Series([m['basis']['state'] for m in months]).value_counts().to_dict(),
            'premarket_sessions_in_bars': int(pre.day.nunique()), 'skipped_no_prior_close': [],
            'parity_mismatch': [], 'parity_checked': 0}
    recs = []
    for day, g in pre.groupby('day', sort=True):
        prev = previous_session(day).isoformat()
        if prev not in daily.index or not pd.notna(daily.at[prev, 'close']):
            meta['skipped_no_prior_close'].append(day.isoformat()); continue
        pc = float(daily.at[prev, 'close']); pc_c = price_cents(pc)
        g = g.reset_index(drop=True)
        raw = {k: g[n].to_numpy(dtype=float) for k, n in (('o', 'open'), ('h', 'high'), ('l', 'low'), ('c', 'close'))}
        v = g['volume'].astype('float64').to_numpy(dtype=float, na_value=np.nan)
        cents = {k: cents_arr(raw[k]) for k in 'ohlc'}
        kw = dict(times=g['ts'], open_=g['open'], high=g['high'], low=g['low'], close=g['close'], volume=g['volume'])
        none = dict(atr=None, stale_print_atr=None, spike_atr=None)
        ship = cpc(**kw, prev_close=pc, **none)
        ind.PM_MIN_EXTREME_VOLUME = 0
        try:
            ship0 = cpc(**kw, prev_close=pc, **none)
        finally:
            ind.PM_MIN_EXTREME_VOLUME = MINV
        r = {'ticker': T, 'date': day.isoformat(), 'pc': pc, 'n_bars': len(g), 'n_thin': int((v < MINV).sum()),
             'ship_high': ship['pre_high'], 'ship_low': ship['pre_low'],
             'ship_reason': ship['confirmed']['reason'],
             'ship_stale_reports': ship['confirmed']['stale_close_reports'],
             'vol0_high': ship0['pre_high'], 'vol0_low': ship0['pre_low']}
        base = engine(raw, raw, v, pc, pc_c)
        meta['parity_checked'] += 1
        if (base[0], base[1]) != (ship['pre_high'], ship['pre_low']):
            meta['parity_mismatch'].append((day.isoformat(), base[:2], ship['pre_high'], ship['pre_low']))
        base0 = engine(raw, raw, v, pc, pc_c, min_vol=0)
        if (base0[0], base0[1]) != (ship0['pre_high'], ship0['pre_low']):
            meta['parity_mismatch'].append((day.isoformat() + ' vol0', base0[:2], ship0['pre_high'], ship0['pre_low']))

        def bar_desc(s):
            if s is None:
                return None
            i, kind = s
            return {'time': g['et'].iloc[i].strftime('%H:%M'), 'kind': kind, 'open': raw['o'][i], 'high': raw['h'][i],
                    'low': raw['l'][i], 'close': raw['c'][i], 'volume': None if v[i] != v[i] else int(v[i])}
        r['ship_high_bar'] = bar_desc(base[2]); r['ship_low_bar'] = bar_desc(base[3])
        s0 = base0
        r['vol0_high_bar'] = bar_desc(s0[2]); r['vol0_low_bar'] = bar_desc(s0[3])

        cands = {}
        d1, b1 = pc_drop(raw, cents, pc, pc_c, 0)
        d2, b2 = pc_drop(raw, cents, pc, pc_c, 5)
        d2b, _ = pc_drop(raw, cents, pc, pc_c, 5, 0.001)
        d2c, _ = pc_drop(raw, cents, pc, pc_c, 2)
        d2d, _ = pc_drop(raw, cents, pc, pc_c, 10)
        d4, b4 = pc_drop_ctx(raw, cents, v, pc, pc_c, 5)
        cands['P1'] = engine(raw, raw, v, pc, pc_c, drop=d1)
        cands['P2'] = engine(raw, raw, v, pc, pc_c, drop=d2)
        cands['P2_D0.10'] = engine(raw, raw, v, pc, pc_c, drop=d2b)
        cands['P2_tol2'] = engine(raw, raw, v, pc, pc_c, drop=d2c)
        cands['P2_tol10'] = engine(raw, raw, v, pc, pc_c, drop=d2d)
        cands['P3'] = engine(raw, raw, v, pc, pc_c, stale=False, body_ok=isolated_bodies(raw, v, D_FRAC))
        cands['P3_D0.05'] = engine(raw, raw, v, pc, pc_c, stale=False, body_ok=isolated_bodies(raw, v, 0.0005))
        cands['P4'] = engine(raw, raw, v, pc, pc_c, drop=d4)
        d24 = {k: d2[k] | d4[k] for k in 'ohlc'}
        cands['P2+P4'] = engine(raw, raw, v, pc, pc_c, drop=d24)
        cands['P5_D0.25'] = engine(raw, raw, v, pc, pc_c, drop=median_drop(raw, v, 0.0025))
        cands['P5_D0.50'] = engine(raw, raw, v, pc, pc_c, drop=median_drop(raw, v, 0.005))
        d25 = median_drop(raw, v, 0.005)
        cands['P2+P5_D0.50'] = engine(raw, raw, v, pc, pc_c, drop={k: d2[k] | d25[k] for k in 'ohlc'})
        for name, c in cands.items():
            r[f'{name}_high'], r[f'{name}_low'] = c[0], c[1]

        # continuity support for a dropped print: the bar before closed, or the bar
        # after opened, within 0.1% of the prior close (either bar non-thin).
        nb = np.zeros(len(v), bool)
        okb = ~(v < MINV)
        near_c = okb & (np.abs(raw['c'] - pc) <= 0.001 * pc)
        near_o = okb & (np.abs(raw['o'] - pc) <= 0.001 * pc)
        nb[1:] |= near_c[:-1]; nb[:-1] |= near_o[1:]
        for name, bm in (('P1', b1), ('P2', b2), ('P4', b4)):
            live = bm & okb
            r[f'{name}_bars_dropped'] = int(live.sum())
            r[f'{name}_bars_dropped_supported'] = int((live & nb).sum())

        # runs of genuine trading at the prior close / at the shipped extremes
        r['run_pc'] = run_near(raw, v, pc)
        r['run_ship_high'] = run_near(raw, v, ship['pre_high'])
        r['run_ship_low'] = run_near(raw, v, ship['pre_low'])
        r['ship_high_at_pc'] = ship['pre_high'] is not None and price_cents(ship['pre_high']) == pc_c
        r['ship_low_at_pc'] = ship['pre_low'] is not None and price_cents(ship['pre_low']) == pc_c
        r['ship_high_pc_dist_c'] = None if ship['pre_high'] is None else abs(price_cents(ship['pre_high']) - pc_c)
        r['ship_low_pc_dist_c'] = None if ship['pre_low'] is None else abs(price_cents(ship['pre_low']) - pc_c)

        # item 1 counts
        live = v >= MINV
        for tol in TOLS:
            at_o = np.abs(cents['o'] - pc_c) <= tol; at_c = np.abs(cents['c'] - pc_c) <= tol
            for X in XS:
                far_o = np.abs(raw['o'] - pc) > X * pc; far_c = np.abs(raw['c'] - pc) > X * pc
                far_w = (np.abs(raw['l'] - pc) > X * pc) | (np.abs(raw['h'] - pc) > X * pc)
                r[f'i1_t{tol}_x{X}'] = int((live & ((at_o & far_c) | (at_c & far_o))).sum())
                r[f'i1both_t{tol}_x{X}'] = int((live & at_o & at_c & far_w).sum())

        # 2026 sessions with a recorded calibrated filter: the same candidates on top of it
        pf = daily.at[day.isoformat(), 'pfp_text'] if day.isoformat() in daily.index else None
        if isinstance(pf, str):
            p = json.loads(pf)
            if p.get('pm_stale_print_atr', {}).get('status') == 'ok' and p.get('pm_spike_atr', {}).get('status') == 'ok' and p.get('atr'):
                fk = dict(atr=p['atr'], stale_print_atr=p['pm_stale_print_atr']['value'], spike_atr=p['pm_spike_atr']['value'])
                shipf = cpc(**kw, prev_close=pc, **fk)
                f = premarket_print_filter(*(pd.Series(raw[k]) for k in 'ohlc'), prev_close=pc, **fk)
                fc = {'o': f['open'].to_numpy(), 'h': f['high'].to_numpy(), 'l': f['low'].to_numpy(), 'c': f['close'].to_numpy()}
                bf = engine(raw, fc, v, pc, pc_c)
                if (bf[0], bf[1]) != (shipf['pre_high'], shipf['pre_low']):
                    meta['parity_mismatch'].append((day.isoformat() + ' filtered', bf[:2], shipf['pre_high'], shipf['pre_low']))
                r['F_ship_high'], r['F_ship_low'] = shipf['pre_high'], shipf['pre_low']
                r['F_ship_high_bar'] = bar_desc(bf[2]); r['F_ship_low_bar'] = bar_desc(bf[3])
                r['F_excl_stale'] = shipf['excluded_prior_close_prints']; r['F_excl_spike'] = shipf['excluded_spike_prints']
                for name, dd in (('P1', d1), ('P2', d2), ('P4', d4), ('P2+P4', d24)):
                    e = engine(raw, fc, v, pc, pc_c, drop=dd)
                    r[f'F_{name}_high'], r[f'F_{name}_low'] = e[0], e[1]
                e = engine(raw, fc, v, pc, pc_c, stale=False, body_ok=isolated_bodies(raw, v, D_FRAC))
                r['F_P3_high'], r['F_P3_low'] = e[0], e[1]
                r['F_run_ship_high'] = run_near(raw, v, shipf['pre_high']); r['F_run_ship_low'] = run_near(raw, v, shipf['pre_low'])
        recs.append(r)
    pickle.dump({'meta': meta, 'recs': recs}, open(f'{OUT}/sessions_{T}.pkl', 'wb'))
    print(json.dumps({k: (v if k not in ('skipped_no_prior_close',) else [len(v), v[:2], v[-2:]]) for k, v in meta.items()}, default=str))


if __name__ == '__main__':
    main()
