"""level_hits: did price cross the brief's trigger, hold 5+ minutes, and reach the targets? Did it tap Strat levels?

Inputs : replayed 08:30 briefs (run_replay.py output dir), 1 min bars, daily fixture (for week/month/quarter opens),
         report_days.csv.
Outputs: sides.csv (one row per ticker day side), results.csv (one row per ticker day), taps.csv (one row per
         level per ticker day) in the lane folder.
Usage  : python3 -I analyze.py <replay_dir> <worktree>
"""
import glob, json, os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)
REPLAY, WT = sys.argv[1], sys.argv[2]
B = '/mnt/project-files/stocks-scorecard/inputs/bars_raw'
T = ('SPY', 'QQQ', 'IWM')
HOLDOUT_END = '2026-04-30'
HOLDS = (1, 5, 15, 30)
ATR_STEPS = (0.25, 0.5, 1.0)

# ---------- data ----------
_bars = {}
def bars(t):
    if t not in _bars:
        _bars[t] = (pd.concat([pd.read_csv(f, parse_dates=['timestamp']) for f in sorted(glob.glob(f'{B}/{t}_1min_*.csv'))])
                    .drop_duplicates('timestamp').set_index('timestamp').sort_index())
    return _bars[t]

def day_slice(t, day, a, b):
    return bars(t).loc[f'{day} {a}':f'{day} {b}']

_daily = {}
def daily_opens(t):
    """Session open per day: the committed daily fixture through 2026-11-06, the 09:30 bar open after that."""
    if t not in _daily:
        raw = json.load(open(f'{WT}/tests/fixtures/strat_levels_2026-11-06_daily.json'))
        d = pd.DataFrame(raw['tickers'][t], columns=raw['columns'])
        s = pd.Series(d['open'].astype(float).values, index=pd.to_datetime(d['date']))
        b = bars(t); r = b[(b.index.time >= pd.Timestamp('09:30').time()) & (b.index.time <= pd.Timestamp('15:59').time())]
        o = r.open.groupby(r.index.normalize()).first()
        s = pd.concat([s, o[o.index > s.index.max()]]).sort_index()
        _daily[t] = s
    return _daily[t]

def period_opens(t, day, today_open):
    """Open of the current day, week, month, quarter as known during the session (today's open if today starts it)."""
    s = daily_opens(t); d = pd.Timestamp(day)
    s = s[s.index < d]
    out = {'D': today_open}
    for k, start in (('W', d - pd.Timedelta(days=d.weekday())), ('M', d.replace(day=1)),
                     ('Q', pd.Timestamp(year=d.year, month=3 * ((d.month - 1) // 3) + 1, day=1))):
        x = s[s.index >= start]
        out[k] = float(x.iloc[0]) if len(x) else today_open
    return out

def clean_ext(x, atr):
    """Extended hours bars carry late/bad prints as long wicks. Clip each bar's high/low to within 0.1 ATR of its
    own open-close body, and everything to within 0.3 ATR of the 15 minute centred median close."""
    if len(x) == 0:
        return None
    med = x.close.rolling(15, center=True, min_periods=1).median()
    top = np.minimum(np.maximum(x.open, x.close), med + 0.3 * atr)
    bot = np.maximum(np.minimum(x.open, x.close), med - 0.3 * atr)
    hi = np.minimum(x.high, top + 0.1 * atr); lo = np.maximum(x.low, bot - 0.1 * atr)
    return float(hi.max()), float(lo.min())

def first_run(mask, n, start=0):
    """Index of the first bar of the first run of n consecutive True at or after start; None if no run."""
    m = mask[start:].astype(int)
    if len(m) < n:
        return None
    c = np.convolve(m, np.ones(n, dtype=int), 'valid')
    w = np.flatnonzero(c == n)
    return int(w[0]) + start if len(w) else None

def first_true(mask, start=0):
    w = np.flatnonzero(mask[start:])
    return int(w[0]) + start if len(w) else None

def hhmm(ts, i):
    return ts[i].strftime('%H:%M') if i is not None else ''

def direction(status):
    s = (status or '').upper()
    return 'calls' if s.startswith('CALL') else 'puts' if s.startswith('PUT') else None

def trade(o, h, l, c, sgn, start, entry, stop, target):
    """From bar index start (inclusive): exit at stop, target or the last close. Stop wins a same bar tie. R units."""
    risk = sgn * (entry - stop)
    if not risk > 0:
        return None, 'no_risk'
    for j in range(start, len(c)):
        adv = l[j] if sgn > 0 else h[j]; fav = h[j] if sgn > 0 else l[j]
        if sgn * (adv - stop) <= 0:
            return -1.0, 'stop'
        if target is not None and sgn * (fav - target) >= 0:
            return sgn * (target - entry) / risk, 'target'
    return sgn * (c[-1] - entry) / risk, 'close'

# ---------- per side ----------
def side_stats(b, side, e, atr, opens):
    sgn = 1 if side == 'calls' else -1
    lb_side = ((e.get('level_basis') or {}).get('long' if side == 'calls' else 'short') or {})
    trig = e.get(f'{side}_trigger_price'); stop = e.get(f'{side}_stop_price')
    tg = [e.get(f'{side}_t{k}_price') for k in (1, 2, 3)]
    r = {'side': side, 'trigger': trig, 'trigger_name': e.get(f'{side}_trigger_name'), 'stop': stop,
         'stop_name': e.get(f'{side}_stop_name'), 't1': tg[0], 't2': tg[1], 't3': tg[2]}
    if trig is None:
        r['has_trigger'] = False
        return r
    r['has_trigger'] = True
    # next ladder rung beyond the last brief target
    last = next((x for x in reversed(tg) if x is not None), trig)
    nxt = [c_['price'] for c_ in (lb_side.get('candidates') or []) if sgn * (c_['price'] - last) > 0]
    t4 = (min(nxt) if sgn > 0 else max(nxt)) if nxt else None
    r['t4_next_rung'] = t4
    o = b.open.values; h = b.high.values; l = b.low.values; c = b.close.values; ts = b.index
    fav = h if sgn > 0 else l; adv = l if sgn > 0 else h
    r['trig_dist_atr'] = round(sgn * (trig - o[0]) / atr, 4)       # how far the trigger is from the open (negative = open already through)
    r['thru_open'] = bool(sgn * (o[0] - trig) >= 0)
    r['risk_atr'] = round(sgn * (trig - stop) / atr, 4) if stop is not None else None
    for k, x in zip((1, 2, 3), tg):
        r[f't{k}_dist_atr'] = round(sgn * (x - trig) / atr, 4) if x is not None else None
    touch = sgn * (fav - trig) >= 0
    beyond = sgn * (c - trig) > 0
    strict = sgn * (adv - trig) > 0
    ti = first_true(touch)
    r['touch'] = ti is not None; r['touch_t'] = hhmm(ts, ti)
    # longest run of consecutive closes beyond the trigger
    best = cur = 0
    for v in beyond:
        cur = cur + 1 if v else 0; best = max(best, cur)
    r['longest_hold_min'] = int(best)
    r['mins_beyond_total'] = int(beyond.sum())
    for n in HOLDS:
        i = first_run(beyond, n); r[f'hold{n}'] = i is not None; r[f'hold{n}_t'] = hhmm(ts, i)
        i2 = first_run(strict, n); r[f'strict{n}'] = i2 is not None
    i5 = first_run(beyond, 5)
    r['close_beyond_trigger'] = bool(sgn * (c[-1] - trig) > 0)
    r['mfe_from_trig_atr'] = round(float(np.max(sgn * (fav - trig))) / atr, 4)  # best excursion beyond trigger, whole session
    # stop / targets after the hold starts
    targets = {'t1': tg[0], 't2': tg[1], 't3': tg[2], 't4': t4}
    for a in ATR_STEPS:
        targets[f'a{a}'] = trig + sgn * a * atr       # yardsticks: trigger plus 0.25 / 0.5 / 1.0 of the ticker's ATR
    for name, x in targets.items():
        r[f'{name}_reached_day'] = bool((sgn * (fav - x) >= 0).any()) if x is not None else None
        r[f'{name}_thru_open'] = bool(sgn * (o[0] - x) >= 0) if x is not None else None
    if i5 is not None:
        c5 = i5 + 4                                     # bar whose close confirms the 5 minute hold
        r['hold5_confirm_t'] = hhmm(ts, c5)
        r['hold5_pre10'] = bool(ts[i5].time() < pd.Timestamp('10:00').time())
        js = first_true(sgn * (adv - stop) <= 0, i5) if stop is not None else None
        r['stop_after_hold'] = js is not None; r['stop_after_hold_t'] = hhmm(ts, js)
        r['mfe_after_hold_atr'] = round(float(np.max(sgn * (fav[i5:] - trig))) / atr, 4)
        r['mae_after_hold_atr'] = round(float(np.max(-sgn * (adv[i5:] - trig))) / atr, 4)
        for name, x in targets.items():
            if x is None:
                r[f'{name}_hit'] = None; continue
            jt = first_true(sgn * (fav - x) >= 0, i5)
            r[f'{name}_hit'] = jt is not None
            r[f'{name}_hit_t'] = hhmm(ts, jt)
            r[f'{name}_mins'] = (jt - i5) if jt is not None else None
            r[f'{name}_in_hold'] = bool(jt is not None and jt <= c5)       # reached inside the 5 minute hold itself
            r[f'{name}_before_stop'] = bool(jt is not None and (js is None or jt < js))
        # continuity at the confirming close
        px = c[c5]
        g = {k: (px > v) for k, v in opens.items()}
        r['ftfc_n'] = int(sum(g.values()) if sgn > 0 else sum(not v for v in g.values()))
        r['ftfc_aligned'] = r['ftfc_n'] == 4
        # trade after the hold: enter at the confirming close; exit stop / target / close
        entry = float(c[c5]); r['hold_entry'] = entry
        r['hold_entry_past_atr'] = round(sgn * (entry - trig) / atr, 4)
        for name in ('t1', 't2', 't3'):
            x = targets[name]
            if x is None:
                continue
            if sgn * (x - entry) <= 0:
                r[f'R_hold_{name}'] = None; r[f'R_hold_{name}_how'] = 'target_already_passed'; continue
            R, how = trade(o, h, l, c, sgn, c5 + 1, entry, stop, x) if stop is not None else (None, 'no_stop')
            r[f'R_hold_{name}'] = None if R is None else round(R, 4); r[f'R_hold_{name}_how'] = how
        if stop is not None:
            R, how = trade(o, h, l, c, sgn, c5 + 1, entry, stop, None)
            r['R_hold_to_close'] = None if R is None else round(R, 4); r['R_hold_to_close_how'] = how
            # ATR sized version: risk 0.25 ATR back through the trigger, target 0.5 ATR beyond the trigger
            R, how = trade(o, h, l, c, sgn, c5 + 1, entry, trig - sgn * 0.25 * atr, trig + sgn * 0.5 * atr) \
                if sgn * (trig + sgn * 0.5 * atr - entry) > 0 else (None, 'target_already_passed')
            r['R_hold_atr'] = None if R is None else round(R, 4); r['R_hold_atr_how'] = how
    # touch entry (earlier study's rule): fill at trigger, or the open if already through; exit stop / T1 / close
    if ti is not None and stop is not None and tg[0] is not None:
        entry = float(o[0]) if r['thru_open'] else float(trig)
        if sgn * (tg[0] - entry) > 0:
            # same bar: the fill bar can also stop or hit the target
            R, how = trade(o, h, l, c, sgn, ti, entry, stop, tg[0])
            r['R_touch_t1'] = None if R is None else round(R, 4); r['R_touch_t1_how'] = how
        else:
            r['R_touch_t1_how'] = 'target_already_passed'
    return r

# ---------- Strat level taps ----------
def strat_levels(t, day, prior, e, atr):
    lv = {}
    lv['PDH'] = ('up', e.get('prev_day_high')); lv['PDL'] = ('down', e.get('prev_day_low'))
    for x in ((e.get('level_basis') or {}).get('levels') or []):
        if x['name'] == 'PWH': lv['PWH'] = ('up', x['price'])
        if x['name'] == 'PWL': lv['PWL'] = ('down', x['price'])
    ev = clean_ext(day_slice(t, prior, '16:00', '19:59'), atr)        # overnight 12HR candle (16:00 to 04:00; data ends 20:00)
    if ev:
        lv['E12H'] = ('up', ev[0]); lv['E12L'] = ('down', ev[1]); lv['E12M'] = ('mid', (ev[0] + ev[1]) / 2)
    pm = clean_ext(day_slice(t, prior, '04:00', '09:29'), atr)        # prior day 12HR candle (04:00 to 16:00)
    rt = day_slice(t, prior, '09:30', '15:59')
    if len(rt):
        hi = max(rt.high.max(), pm[0]) if pm else rt.high.max(); lo = min(rt.low.min(), pm[1]) if pm else rt.low.min()
        lv['D12H'] = ('up', float(hi)); lv['D12L'] = ('down', float(lo)); lv['D12M'] = ('mid', float(hi + lo) / 2)
    return lv

def tap_rows(b, lv, atr, opens, base):
    o = b.open.values; h = b.high.values; l = b.low.values; c = b.close.values; ts = b.index
    rows = []
    for name, (d, price) in lv.items():
        if price is None or not np.isfinite(price):
            continue
        if d == 'mid':
            d = 'up' if o[0] < price else 'down'
        sgn = 1 if d == 'up' else -1
        fav = h if sgn > 0 else l; adv = l if sgn > 0 else h
        r = dict(base, level=name, price=round(float(price), 4), dir=d, dist_open_atr=round(sgn * (price - o[0]) / atr, 4))
        if sgn * (o[0] - price) >= 0:
            r['state'] = 'open_beyond'; rows.append(r); continue
        ti = first_true(sgn * (fav - price) >= 0)
        if ti is None:
            r['state'] = 'not_tapped'; rows.append(r); continue
        r['state'] = 'tapped'; r['tap_t'] = hhmm(ts, ti); r['pre10'] = bool(ts[ti].time() < pd.Timestamp('10:00').time())
        r['tap_min'] = int(ti)
        beyond = sgn * (c - price) > 0
        i5 = first_run(beyond, 5, ti)
        r['held5_within10'] = bool(i5 is not None and i5 <= ti + 10)
        r['held5_later'] = i5 is not None
        for k in (0.25, 0.5):
            jf = first_true(sgn * (fav - (price + sgn * k * atr)) >= 0, ti)
            ja = first_true(sgn * (adv - (price - sgn * k * atr)) <= 0, ti)
            r[f'res{k}'] = ('neither' if jf is None and ja is None else
                            'follow' if ja is None or (jf is not None and jf < ja) else 'fail')
            r[f'follow{k}_mins'] = (jf - ti) if r[f'res{k}'] == 'follow' else None
        r['mfe_after_atr'] = round(float(np.max(sgn * (fav[ti:] - price))) / atr, 4)
        r['mae_after_atr'] = round(float(np.max(-sgn * (adv[ti:] - price))) / atr, 4)
        r['close_beyond'] = bool(sgn * (c[-1] - price) > 0)
        g = {k: (price > v) for k, v in opens.items()}
        n = int(sum(g.values()) if sgn > 0 else sum(not v for v in g.values()))
        r['ftfc_n'] = n; r['ftfc_aligned'] = n == 4
        r['ftfc_DW'] = bool((g['D'] and g['W']) if sgn > 0 else (not g['D'] and not g['W']))
        rows.append(r)
    return rows

# ---------- main ----------
def main():
    rep = pd.read_csv(f'{HERE}/report_days.csv')
    rep_map = rep.groupby('date').event.apply(lambda s: '+'.join(sorted(set(s)))).to_dict()
    rep_time = rep.groupby('date').time_et.min().to_dict()
    files = sorted(glob.glob(f'{REPLAY}/main0830_20*.json'))
    days = [f.rsplit('_', 1)[1][:10] for f in files]
    sides, taps, wide = [], [], []
    for f, day in zip(files, days):
        d = json.load(open(f))
        for t in T:
            e = d['tickers'].get(t)
            b = day_slice(t, day, '09:30', '15:59')
            if e is None or len(b) < 300:
                continue
            lb = e.get('level_basis') or {}
            atr = lb.get('atr') or e.get('atr14')
            if not atr:
                continue
            prior = lb.get('last_bar_date') or str(bars(t)[bars(t).index < pd.Timestamp(day)].index[-1].date())
            call = direction(e.get('signal_status'))
            o0 = float(b.open.iloc[0]); cl = float(b.close.iloc[-1]); pc = e.get('prev_day_close')
            opens = period_opens(t, day, o0)
            base = dict(day=day, ticker=t, window='holdout' if day <= HOLDOUT_END else 'primary',
                        status=e.get('signal_status') or 'none', call=call or 'none', atr=round(atr, 4),
                        report=rep_map.get(day, ''), report_time=rep_time.get(day, ''),
                        open=o0, close=cl, prev_close=pc,
                        gap_atr=round((o0 - pc) / atr, 4) if pc else None,
                        ftfc_brief=e.get('tf_continuity'), strat_candle=e.get('strat_candle'))
            w = dict(base)
            for side in ('calls', 'puts'):
                r = side_stats(b, side, e, atr, opens)
                r = dict(base, role=('called' if side == call else 'opposite' if call else 'no_call'), **r)
                sides.append(r)
                for k, v in r.items():
                    if k not in base and k not in ('side', 'role'):
                        w[f'{side}_{k}'] = v
            lv = strat_levels(t, day, prior, e, atr)
            tr = tap_rows(b, lv, atr, opens, base)
            taps += tr
            for x in tr:
                w[f"{x['level']}"] = x['price']; w[f"{x['level']}_state"] = x['state']; w[f"{x['level']}_tap_t"] = x.get('tap_t', '')
                w[f"{x['level']}_res"] = x.get('res0.25', '')
            wide.append(w)
    S = pd.DataFrame(sides); S.to_csv(f'{OUT}/sides.csv', index=False)
    W = pd.DataFrame(wide); W.to_csv(f'{OUT}/results.csv', index=False)
    TP = pd.DataFrame(taps); TP.to_csv(f'{OUT}/taps.csv', index=False)
    print('sessions', len(set(S.day)), 'ticker days', len(W), 'side rows', len(S), 'tap rows', len(TP))
    print(W.groupby(['window', 'call']).size())

if __name__ == '__main__':
    main()
