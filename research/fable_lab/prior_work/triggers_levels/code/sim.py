"""Trigger / target experiments on 1-min bars. Reads work/sessions.pkl (build_sessions.py).
Usage: python3 -I sim.py            -> results.csv, by_month.csv, work/trades.parquet, work/meta.json
Cost: 1 cent per share each side (2 cents round trip) on every trade. R = net profit / |entry - first stop|.
"""
import json, os, pickle, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); LANE = os.path.dirname(HERE)
COST = 0.01
PRIMARY = ('2026-05-01', '2026-11-10'); HOLDOUT = ('2025-03-03', '2026-04-30')
NBOOT, SEED = 2000, 7

STRUCT = ('PDH', 'PDL', 'PDC', 'PWH', 'PWL', 'PWC', 'PMH', 'PML', 'PMC', 'PQH', 'PQL', 'PQC', 'PYH', 'PYL', 'PYC',
          'parent_bar_high', 'parent_bar_low')
EXTRA = ('PDO', 'PWO', 'PMO', 'CWO', 'CMO', '12N_H', '12N_L', '12N_50', '2D_H', '2D_L', '2D_50',
         'ATR0.5_U', 'ATR0.5_D', 'ATR1.0_U', 'ATR1.0_D')
FAMILIES = {
    'PD': ('PDH', 'PDL'), 'PW': ('PWH', 'PWL'), '12HR_HL': ('12N_H', '12N_L'), '12HR_50': ('12N_50',),
    '2D_HL': ('2D_H', '2D_L'), '2D_50': ('2D_50',), 'ATR0.5': ('ATR0.5_U', 'ATR0.5_D'), 'ATR1.0': ('ATR1.0_U', 'ATR1.0_D'),
}


# ───────────────────────── engine ─────────────────────────
def find_entry(s, side, level, start=0, end=None, at_open_fill=False):
    """First bar from `start` that trades through `level`. Returns (bar index, fill price) or None.
    If the first bar already opens beyond the level: fill at that open (brief rule) or no trade (cross rule)."""
    if level is None or not np.isfinite(level):
        return None
    o, h, l = s['o'], s['h'], s['l']
    end = len(o) if end is None else end
    if start >= end:
        return None
    if (side > 0 and o[start] >= level) or (side < 0 and o[start] <= level):
        return (start, float(o[start])) if at_open_fill else None
    m = (h[start:end] >= level) if side > 0 else (l[start:end] <= level)
    if not m.any():
        return None
    i = start + int(np.argmax(m))
    return i, float(max(level, o[i]) if side > 0 else min(level, o[i]))


def run_trade(s, side, i0, px, stop, targets, mgmt='fixed'):
    """targets: [(price, fraction)], nearest first. Stop wins a same-bar tie. Rest closes at the last bar's close.
    mgmt: fixed | be (stop to entry after TP1) | trail (after TP1 stop to entry, after TP2 stop to TP1, ...)."""
    o, h, l, c = s['o'], s['h'], s['l'], s['c']
    n = len(o); risk = abs(px - stop)
    if risk <= 0:
        return None
    targets = [(p, f) for p, f in targets if (p - px) * side > 0]
    pos, pnl, cur, k, i_s, i_t = 1.0, 0.0, stop, 0, i0, i0
    how, xi = 'close', n - 1
    while pos > 1e-9:
        js = jt = None
        if i_s < n:
            m = (l[i_s:] <= cur) if side > 0 else (h[i_s:] >= cur)
            if m.any():
                js = i_s + int(np.argmax(m))
        if k < len(targets):
            tp = targets[k][0]
            m = (h[i_t:] >= tp) if side > 0 else (l[i_t:] <= tp)
            if m.any():
                jt = i_t + int(np.argmax(m))
        if js is None and jt is None:
            pnl += pos * side * (c[-1] - px); how = 'close' if k == 0 else f'tp{k}+close'; break
        if jt is None or (js is not None and js <= jt):
            ex = cur if js == i0 else (min(cur, o[js]) if side > 0 else max(cur, o[js]))
            pnl += pos * side * (ex - px); how = 'stop' if k == 0 else f'tp{k}+stop'; xi = js; pos = 0.0; break
        f = min(targets[k][1], pos)
        pnl += f * side * (tp - px); pos -= f; k += 1; i_t = jt; i_s = jt + 1; xi = jt
        if mgmt == 'be':
            cur = max(cur, px) if side > 0 else min(cur, px)
        elif mgmt == 'trail':
            new = px if k == 1 else targets[k - 2][0]
            cur = max(cur, new) if side > 0 else min(cur, new)
        if pos <= 1e-9:
            how = f'tp{k}'
    return dict(R=(pnl - 2 * COST) / risk, Rg=pnl / risk, how=how, xi=xi, risk=risk)


def brief_trade(s, side, entry, stop, t1):
    """Exact port of week_summary.trade (the earlier scoring): fill at trigger or the bar open if through, exit at
    stop, T1 (abs distance) or the close. Returns gross and net R."""
    if entry is None or stop is None:
        return None
    o, h, l, c = s['o'], s['h'], s['l'], s['c']
    up = side > 0
    m = (h >= entry) if up else (l <= entry)
    if not m.any():
        return None
    i0 = int(np.argmax(m)); px = max(entry, o[i0]) if up else min(entry, o[i0])
    risk = abs(px - stop)
    if risk <= 0:
        return None
    for i in range(i0, len(o)):
        if (up and l[i] <= stop) or (not up and h[i] >= stop):
            ex = min(stop, o[i]) if up else max(stop, o[i])
            g = ((ex - px) if up else (px - ex)); how = 'stop'; break
        if t1 is not None and ((up and h[i] >= t1) or (not up and l[i] <= t1)):
            g = abs(t1 - px); how = 'T1'; break
    else:
        g = (c[-1] - px) if up else (px - c[-1]); how = 'close'; i = len(o) - 1
    return dict(i0=i0, px=px, R=(g - 2 * COST) / risk, Rg=g / risk, how=how, xi=i, risk=risk)


# ───────────────────────── levels ─────────────────────────
def ladder_prices(s, names=None, with_pmk=True):
    lv = s['levels']; pm = s['pm']['08:30']
    out = [lv[n] for n in (names or (STRUCT + EXTRA)) if n in lv]
    if with_pmk and pm:
        out += [pm['main_h'], pm['main_l']]
    return np.array(sorted(set(round(float(x), 4) for x in out if x == x)))


def nearest(prices, ref, side, min_gap=0.0):
    """Nearest price beyond ref (+gap) in direction side."""
    if side > 0:
        x = prices[prices > ref + min_gap]
        return float(x[0]) if len(x) else None
    x = prices[prices < ref - min_gap]
    return float(x[-1]) if len(x) else None


def rungs(prices, level, side, gap, k=3):
    out = []; cur = level
    for _ in range(k):
        nx = nearest(prices, cur, side, gap - 1e-9 if gap > 0 else 0.0)
        if nx is None:
            break
        out.append(nx); cur = nx
    return out


# ───────────────────────── trigger definitions ─────────────────────────
def trig_family(names):
    def f(s, side, ref):
        p = np.array(sorted(s['levels'][n] for n in names if n in s['levels']))
        return nearest(p, ref, side)
    return f


def trig_pm(cut='08:30', key='main', rule=None):
    """Premarket extreme at a cutoff, optionally replaced by a rule."""
    def f(s, side, ref):
        pm = s['pm'].get(cut)
        if not pm:
            return None
        sd = 'h' if side > 0 else 'l'
        lvl = pm[f'{key}_{sd}']
        if rule is None:
            return lvl
        full = ladder_prices(s, with_pmk=False)
        def nxt(beyond):
            return nearest(full, beyond, side)
        if rule.startswith('thinA'):
            if not pm[f'thinA_{sd}']:
                return lvl
            red = pm[f'thinA_drop_{sd}']
            return {'thinA_drop': red, 'thinA_next': nxt(red), 'thinA_skip': None}[rule]
        if rule.startswith('thinB'):
            if not pm.get(f'thinB_{sd}'):
                return lvl
            return {'thinB_next': nxt(lvl), 'thinB_skip': None}[rule]
        # isolated-extreme rules. Unflagged -> the brief's filtered extreme, unchanged.
        iso, vol_ok, rth_ok = pm[f'iso_{sd}'], pm[f'iso_volok_{sd}'], pm[f'iso_rthok_{sd}']
        raw = pm[f'raw_{sd}']; red = pm[f'iso_drop_{sd}']
        red = min(red, lvl) if side > 0 else max(red, lvl)
        if not iso:
            return lvl
        if rule == 'iso_drop':
            return red
        if rule == 'iso_vol':
            return raw if vol_ok else red
        if rule == 'iso_rth':
            return raw if rth_ok else red
        if rule == 'iso_next':
            return nxt(red)
        if rule == 'iso_vol_next':
            return raw if vol_ok else nxt(red)
        if rule == 'both_next':   # isolated AND cut by the brief's ATR spike filter AND no heavy volume -> next ladder level
            if vol_ok:
                return raw
            return nxt(red) if pm[f'main_cut_{sd}'] else red
        raise ValueError(rule)
    return f


def trig_nearest(names=None, with_pmk=True):
    def f(s, side, ref):
        return nearest(ladder_prices(s, names, with_pmk), ref, side)
    return f


def trig_control(k):
    return lambda s, side, ref: ref + side * k * s['atr']


def trig_orb(s, side, ref):
    return s['orh'] if side > 0 else s['orl']


def trig_brief(s, side, ref):
    return s['brief'].get('calls_trigger_price' if side > 0 else 'puts_trigger_price')


# ───────────────────────── exits ─────────────────────────
def make_exit(target, stop, mgmt='fixed'):
    """Returns f(s, side, level, px) -> (stop price, targets, mgmt) or None."""
    def f(s, side, level, px):
        atr = s['atr']; full = ladder_prices(s)
        if stop == 'brief':
            st = s['brief'].get('calls_stop_price' if side > 0 else 'puts_stop_price')
            if st is None or (px - st) * side <= 0:
                return None
        elif stop.startswith('prior'):
            st = nearest(full, level, -side, float(stop[5:]) * atr - 1e-9)
            if st is None:
                st = level - side * 0.5 * atr
            if (px - st) * side <= 0:
                return None
        else:
            st = px - side * float(stop[3:]) * atr
        if target == 'brief_t1':
            t = s['brief'].get('calls_t1_price' if side > 0 else 'puts_t1_price')
            tg = [(t, 1.0)] if t is not None else []
        elif target == 'brief_t123':
            ts = [s['brief'].get(f"{'calls' if side > 0 else 'puts'}_t{i}_price") for i in (1, 2, 3)]
            ts = [t for t in ts if t is not None]
            tg = [(t, 1 / 3) for t in ts]
        elif target.startswith('lad'):
            gap, k = target[3:].split('_'); r = rungs(full, level, side, float(gap) * atr, int(k))
            tg = [(p, 1.0 / int(k)) for p in r] if int(k) > 1 else [(p, 1.0) for p in r]
        elif target == 'atr3':
            tg = [(px + side * m * atr, 1 / 3) for m in (0.5, 1.0, 1.5)]
        elif target.startswith('atr1_'):
            tg = [(px + side * float(target[5:]) * atr, 1.0)]
        elif target == 'close':
            tg = []
        else:
            raise ValueError(target)
        return st, tg, mgmt
    return f


X_ATR = make_exit('atr1_0.5', 'atr0.25')
X_LVL = make_exit('lad0.1_1', 'prior0.1')


# ───────────────────────── runner ─────────────────────────
def side_of(status):
    u = status.upper()
    return 1 if u.startswith('CALL') else -1 if u.startswith('PUT') else 0


def run_variant(S, trig, exit_f, dirmode, b10, start_bar=0, at_open_fill=False, reentry=None, exact_brief=False):
    rows = []
    for s in S:
        end = int(np.searchsorted(s['tmin'], 600)) if b10 else len(s['o'])
        sides = [side_of(s['status'])] if dirmode == 'brief' else [1, -1]
        if sides == [0]:
            continue
        if start_bar >= len(s['o']):
            continue
        ref = float(s['o'][start_bar])
        cands = []
        for side in sides:
            lvl = trig(s, side, ref)
            if exact_brief:
                bs = s['brief']; k = 'calls' if side > 0 else 'puts'
                x = brief_trade(s, side, bs.get(f'{k}_trigger_price'), bs.get(f'{k}_stop_price'), bs.get(f'{k}_t1_price'))
                if x and x['i0'] < end:
                    cands.append((x['i0'], side, lvl, x['px'], x))
                continue
            e = find_entry(s, side, lvl, start_bar, end, at_open_fill)
            if e:
                cands.append((e[0], side, lvl, e[1], None))
        if not cands:
            continue
        cands.sort(key=lambda x: x[0])
        if len(cands) == 2 and cands[0][0] == cands[1][0]:
            continue  # both sides in the same minute: no trade
        i0, side, lvl, px, pre = cands[0]
        if pre is not None:
            rows.append((s['day'], s['ticker'], side, int(s['tmin'][i0]), lvl, px, pre['how'], pre['R'], pre['Rg'], pre['risk'], 1))
            continue
        ex = exit_f(s, side, lvl, px)
        if ex is None:
            continue
        st, tg, mgmt = ex
        r = run_trade(s, side, i0, px, st, tg, mgmt)
        if r is None:
            continue
        rows.append((s['day'], s['ticker'], side, int(s['tmin'][i0]), lvl, px, r['how'], r['R'], r['Rg'], r['risk'], 1))
        if reentry and r['how'] == 'tp1' and tg:
            # push through: after TP1 (all out), a 5-minute close beyond that level starts the next trade to the level after it
            full = ladder_prices(s); atr = s['atr']; prev_lvl, cur_lvl, xi = lvl, tg[0][0], r['xi']
            for nth in range(2, reentry['max'] + 1):
                c, tm = s['c'], s['tmin']
                ok = ((c > cur_lvl) if side > 0 else (c < cur_lvl)) & (tm % 5 == 4) & (np.arange(len(c)) > xi) & (np.arange(len(c)) < min(end, len(c)) - 1)
                if reentry.get('vwap'):
                    ok &= ((c > s['vwap']) if side > 0 else (c < s['vwap']))
                if not ok.any():
                    break
                j = int(np.argmax(ok)) + 1; px2 = float(s['o'][j])
                nx = rungs(full, cur_lvl, side, reentry['gap'] * atr, 1)
                if not nx or (nx[0] - px2) * side <= 0:
                    break
                st2 = prev_lvl if reentry['stop'] == 'prior' else px2 - side * float(reentry['stop']) * atr
                if (px2 - st2) * side <= 0:
                    break
                r2 = run_trade(s, side, j, px2, st2, [(nx[0], 1.0)])
                if r2 is None:
                    break
                rows.append((s['day'], s['ticker'], side, int(tm[j]), cur_lvl, px2, r2['how'], r2['R'], r2['Rg'], r2['risk'], nth))
                if r2['how'] != 'tp1':
                    break
                prev_lvl, cur_lvl, xi = cur_lvl, nx[0], r2['xi']
    return rows


def variants():
    """(group, name, kwargs, baseline name)"""
    V = []
    # A: trigger source, two common exits
    for xn, xf in (('X_ATR', X_ATR), ('X_LVL', X_LVL)):
        base = f'A.PMK|{xn}'
        V.append(('A', f'A.BRIEF_TRIGGER(fill at open if through)|{xn}', dict(trig=trig_brief, exit_f=xf, at_open_fill=True), base))
        V.append(('A', base, dict(trig=trig_pm(), exit_f=xf), f'A.CONTROL_open+-0.25ATR|{xn}'))
        for fam, names in FAMILIES.items():
            V.append(('A', f'A.{fam}|{xn}', dict(trig=trig_family(names), exit_f=xf), base))
        V.append(('A', f'A.ORB15|{xn}', dict(trig=trig_orb, exit_f=xf, start_bar=15), base))
        V.append(('A', f'A.NEAREST_BRIEF_CANDIDATES|{xn}', dict(trig=trig_nearest(STRUCT), exit_f=xf), base))
        V.append(('A', f'A.NEAREST_FULL|{xn}', dict(trig=trig_nearest(), exit_f=xf), base))
        V.append(('A', f'A.NEAREST_FULL_NO_PMK|{xn}', dict(trig=trig_nearest(with_pmk=False), exit_f=xf), base))
        V.append(('A', f'A.CONTROL_open+-0.25ATR|{xn}', dict(trig=trig_control(0.25), exit_f=xf), base))
        V.append(('A', f'A.CONTROL_open+-0.1ATR|{xn}', dict(trig=trig_control(0.1), exit_f=xf), base))
        # B, C: premarket level rules at two cutoffs
        for cut in ('08:30', '09:25'):
            b = f'BC.PMK_main@{cut}|{xn}'
            V.append(('BC', b, dict(trig=trig_pm(cut), exit_f=xf), f'A.PMK|{xn}'))
            V.append(('BC', f'BC.PMK_raw@{cut}|{xn}', dict(trig=trig_pm(cut, 'raw'), exit_f=xf), b))
            for rule in ('thinA_drop', 'thinA_next', 'thinA_skip', 'thinB_next', 'thinB_skip'):
                V.append(('B', f'B.{rule}@{cut}|{xn}', dict(trig=trig_pm(cut, 'main', rule), exit_f=xf), b))
            for rule in ('iso_drop', 'iso_vol', 'iso_rth', 'iso_next', 'iso_vol_next', 'both_next'):
                V.append(('C', f'C.{rule}@{cut}|{xn}', dict(trig=trig_pm(cut, 'main', rule), exit_f=xf), b))
    # D: targets / stops
    D0 = 'D.BRIEF|brief exact (stop=brief, T1=brief)'
    V.append(('D', D0, dict(trig=trig_brief, exit_f=None, exact_brief=True), D0))
    for tn, tf, aof in (('BRIEF', trig_brief, True), ('FULL', trig_nearest(), False)):
        stops = (['brief'] if tn == 'BRIEF' else []) + ['prior0.1', 'prior0.25', 'atr0.15', 'atr0.25', 'atr0.5']
        tgts = (['brief_t1', 'brief_t123'] if tn == 'BRIEF' else ['lad0_1']) + ['lad0.1_1', 'lad0.25_1', 'lad0.1_3', 'lad0.25_3', 'atr1_0.5', 'atr1_1.0', 'atr3', 'close']
        for st in stops:
            for tg in tgts:
                multi = tg in ('brief_t123', 'lad0.1_3', 'lad0.25_3', 'atr3')
                for mg in (('fixed', 'be', 'trail') if multi else ('fixed',)):
                    V.append(('D', f'D.{tn}|tgt={tg}|stop={st}|{mg}', dict(trig=tf, exit_f=make_exit(tg, st, mg), at_open_fill=aof), D0))
        for st in ('prior', '0.25'):
            for vw in (False, True):
                for gap in (0.1, 0.25):
                    ex = make_exit(f'lad{gap}_1', 'prior0.1' if st == 'prior' else 'atr0.25')
                    b = f'D.{tn}|tgt=lad{gap}_1|stop={"prior0.1" if st == "prior" else "atr0.25"}|fixed'
                    V.append(('D', f'D.{tn}|REENTRY gap={gap} stop={st}{" vwap" if vw else ""}',
                              dict(trig=tf, exit_f=ex, at_open_fill=aof, reentry=dict(max=3, gap=gap, stop=st, vwap=vw)), b))
    return V


def max_dd(r):
    if len(r) == 0:
        return 0.0
    c = np.cumsum(r); return float(np.max(np.maximum.accumulate(np.maximum(c, 0)) - c))


def main():
    S = pickle.load(open(f'{LANE}/work/sessions.pkl', 'rb'))
    only = sys.argv[1] if len(sys.argv) > 1 else None
    V = variants()
    all_rows = []; cols = ['day', 'ticker', 'side', 'entry_min', 'level', 'entry', 'how', 'R', 'R_gross', 'risk', 'nth']
    for group, name, kw, base in V:
        if only and only not in name:
            continue
        for dirmode in ('brief', 'both'):
            for b10 in (False, True):
                rows = run_variant(S, dirmode=dirmode, b10=b10, **kw)
                df = pd.DataFrame(rows, columns=cols)
                df['group'] = group; df['variant'] = name; df['dir'] = dirmode; df['time'] = 'before10' if b10 else 'allday'; df['base'] = base
                all_rows.append(df)
    T = pd.concat(all_rows, ignore_index=True)
    T['window'] = np.where(T.day >= PRIMARY[0], 'primary', 'holdout')
    T['month'] = T.day.str[:7]
    T.to_parquet(f'{LANE}/work/trades.parquet')

    days = {'primary': sorted({s['day'] for s in S if s['day'] >= PRIMARY[0]}), 'holdout': sorted({s['day'] for s in S if s['day'] < PRIMARY[0]})}
    rng = np.random.default_rng(SEED)
    W = {w: rng.multinomial(len(d), np.ones(len(d)) / len(d), size=NBOOT).astype(float) for w, d in days.items()}
    didx = {w: {d: i for i, d in enumerate(ds)} for w, ds in days.items()}

    def dayvec(g, w):
        v = np.zeros(len(days[w]))
        if len(g):
            x = g.groupby('day').R.sum()
            v[[didx[w][d] for d in x.index]] = x.values
        return v

    key = ['variant', 'dir', 'time']
    vecs = {}; res = []
    for (name, dm, tm), g in T.groupby(key, sort=False):
        for w in ('primary', 'holdout'):
            gw = g[g.window == w]
            for t in ('ALL', 'SPY', 'QQQ', 'IWM'):
                x = gw if t == 'ALL' else gw[gw.ticker == t]
                vecs[(name, dm, tm, w, t)] = dayvec(x, w)
    meta = T.groupby(key, sort=False).agg(group=('group', 'first'), base=('base', 'first')).reset_index()
    for _, m in meta.iterrows():
        g = T[(T.variant == m.variant) & (T.dir == m.dir) & (T.time == m.time)]
        for w in ('primary', 'holdout'):
            gw = g[g.window == w].sort_values(['day', 'entry_min'])
            for t in ('ALL', 'SPY', 'QQQ', 'IWM'):
                x = gw if t == 'ALL' else gw[gw.ticker == t]
                v = vecs[(m.variant, m.dir, m.time, w, t)]
                bt = W[w] @ v
                r = x.R.values
                row = dict(group=m.group, variant=m.variant, dir=m.dir, time=m.time, window=w, ticker=t, days=len(days[w]),
                           trades=len(x), win_pct=round(100 * (r > 0).mean(), 1) if len(r) else None,
                           total_R=round(r.sum(), 2), R_lo=round(np.percentile(bt, 5), 2), R_hi=round(np.percentile(bt, 95), 2),
                           avg_R=round(r.mean(), 3) if len(r) else None,
                           avg_win=round(r[r > 0].mean(), 3) if (r > 0).any() else None,
                           avg_loss=round(r[r <= 0].mean(), 3) if (r <= 0).any() else None,
                           max_dd_R=round(max_dd(r), 2), median_risk_atr=None, base=m.base)
                bv = vecs.get((m.base, m.dir, m.time, w, t))
                if bv is not None and m.base != m.variant:
                    d = v - bv; bd = W[w] @ d
                    row.update(diff_R=round(d.sum(), 2), diff_lo=round(np.percentile(bd, 5), 2), diff_hi=round(np.percentile(bd, 95), 2),
                               diff_days=int((np.abs(d) > 1e-9).sum()))
                if m.time == 'before10':
                    av = vecs.get((m.variant, m.dir, 'allday', w, t))
                    if av is not None:
                        d = v - av; bd = W[w] @ d
                        row.update(b10_minus_allday_R=round(d.sum(), 2), b10_lo=round(np.percentile(bd, 5), 2), b10_hi=round(np.percentile(bd, 95), 2))
                res.append(row)
    R = pd.DataFrame(res)
    R.to_csv(f'{LANE}/results.csv', index=False)
    bm = T.groupby(['variant', 'dir', 'time', 'month']).agg(trades=('R', 'size'), total_R=('R', 'sum'), win_pct=('R', lambda r: 100 * (r > 0).mean())).round(2).reset_index()
    bmt = T.groupby(['variant', 'dir', 'time', 'month', 'ticker']).agg(trades=('R', 'size'), total_R=('R', 'sum'), win_pct=('R', lambda r: 100 * (r > 0).mean())).round(2).reset_index()
    bm['ticker'] = 'ALL'
    pd.concat([bm, bmt]).sort_values(['variant', 'dir', 'time', 'ticker', 'month']).to_csv(f'{LANE}/by_month.csv', index=False)
    json.dump(dict(sessions=len(S), days={k: len(v) for k, v in days.items()}, variants=len(V), trade_rows=len(T), cost_per_share_per_side=COST,
                   nboot=NBOOT, seed=SEED), open(f'{LANE}/work/meta.json', 'w'))
    print(len(V), 'variants', len(T), 'trade rows', len(R), 'result rows')


if __name__ == '__main__':
    main()
