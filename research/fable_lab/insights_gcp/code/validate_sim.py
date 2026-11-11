"""Validate the day-rule simulator against the local lane's E0 baseline (neutral plan on the 08:20 premarket high/low,
both sides, 2026-05-01..2026-11-10, SPY/QQQ/IWM). Local lane: 474 fills, win 47.9%, T1/stop/close 32/36/406, +7.6R."""
import sys, numpy as np, pandas as pd
S = sys.argv[1]
def sim(g, sign, e_lo, e_hi, stop, t1):
    """Earlier study's day rule on one session's RTH bars. Returns (fill_ts, fill, exit, outcome, R) or None."""
    o, h, l, c = g['open'].to_numpy(), g['high'].to_numpy(), g['low'].to_numpy(), g['close'].to_numpy()
    touch = np.where((l <= e_hi) & (h >= e_lo))[0]
    if len(touch) == 0:
        return None
    i0 = touch[0]
    fill = min(max(o[i0], e_lo), e_hi)
    risk = abs(fill - stop)
    if risk <= 0:
        return None
    for i in range(i0, len(g)):
        if sign > 0:
            if l[i] <= stop:
                ex = o[i] if o[i] < stop else stop; return (g['et'].iloc[i0], fill, ex, 'stop', (ex - fill) / risk)
            if t1 is not None and h[i] >= t1:
                ex = o[i] if o[i] > t1 else t1; return (g['et'].iloc[i0], fill, ex, 't1', (ex - fill) / risk)
        else:
            if h[i] >= stop:
                ex = o[i] if o[i] > stop else stop; return (g['et'].iloc[i0], fill, ex, 'stop', (fill - ex) / risk)
            if t1 is not None and l[i] <= t1:
                ex = o[i] if o[i] < t1 else t1; return (g['et'].iloc[i0], fill, ex, 't1', (fill - ex) / risk)
    ex = c[-1]
    return (g['et'].iloc[i0], fill, ex, 'close', sign * (ex - fill) / risk)

def side_plan(sign, trigger, buf_hi, stop_dist, t1_dist):
    """A neutral-style plan on a trigger: zone from the trigger to buf_hi past it, stop and T1 at the stored distances from the midpoint."""
    e_lo, e_hi = (trigger, trigger + buf_hi) if sign > 0 else (trigger - buf_hi, trigger)
    mid = (e_lo + e_hi) / 2
    return e_lo, e_hi, mid - sign * stop_dist, mid + sign * t1_dist


q10 = pd.read_csv(f'{S}/out_Q10.csv'); q10['session'] = pd.to_datetime(q10['date']).dt.date
q10 = q10.sort_values(['ticker', 'session']); q10['atr_prev'] = q10.groupby('ticker')['atr_14'].shift(1)
start, end = pd.Timestamp('2026-05-01').date(), pd.Timestamp('2026-11-10').date()
res = []
for t in ['SPY', 'QQQ', 'IWM']:
    b = pd.read_csv(f'{S}/bars/bars_{t}.csv.gz', parse_dates=['et']); b['session'] = pd.to_datetime(b['session']).dt.date
    b = b[(b.session >= start) & (b.session <= end)]
    tm = b['et'].dt.time
    pm = b[(tm >= pd.Timestamp('04:00').time()) & (tm < pd.Timestamp('08:20').time())].groupby('session').agg(pmh=('high', 'max'), pml=('low', 'min'))
    rth = b[(tm >= pd.Timestamp('09:30').time()) & (tm < pd.Timestamp('16:00').time())]
    atr = q10[q10.ticker == t].set_index('session')['atr_prev']
    for s, g in rth.groupby('session'):
        if s not in pm.index or s not in atr.index or not atr[s] > 0:
            continue
        a = atr[s]
        for sign, trig in [(1, pm.loc[s, 'pmh']), (-1, pm.loc[s, 'pml'])]:
            e_lo, e_hi, stop, t1 = side_plan(sign, trig, 0.25 * a, 1.0 * a, 1.0 * a)
            out = sim(g, sign, e_lo, e_hi, stop, t1)
            res.append(dict(ticker=t, session=s, sign=sign, trig=trig, open=g['open'].iloc[0], trig_vs_open_atr=sign * (trig - g['open'].iloc[0]) / a,
                            fill=out is not None, outcome=out[3] if out else None, R=out[4] if out else np.nan, fill_et=out[0] if out else None))
r = pd.DataFrame(res); f = r[r.fill]
print('ticker-sessions', r.groupby(['ticker', 'session']).ngroups, 'sides', len(r), 'fills', len(f), f'({100*len(f)/len(r):.0f}%)')
print('win %.1f%%' % (100 * (f.R > 0).mean()), 'T1/stop/close', f.outcome.value_counts().to_dict(), 'total R %+.1f' % f.R.sum(), 'per fill %+.3f' % f.R.mean())
print('fills in first 5 minutes: %.0f%%' % (100 * (pd.to_datetime(f.fill_et).dt.time <= pd.Timestamp('09:34').time()).mean()))
print('trigger vs open at 08:20 snapshot (ATR, trade direction): quantiles', r.trig_vs_open_atr.quantile([.05, .25, .5, .75, .95]).round(2).tolist(), ' share trigger already passed at the open: %.2f' % (r.trig_vs_open_atr < 0).mean())
print(f.groupby('ticker').agg(fills=('R', 'size'), win=('R', lambda s: round(100 * (s > 0).mean(), 1)), total_R=('R', 'sum')).round(2))
# the same with the daily table's pre_high/pre_low instead of the bars' extremes
q10i = q10.set_index(['ticker', 'session'])
res2 = []
for t in ['SPY', 'QQQ', 'IWM']:
    b = pd.read_csv(f'{S}/bars/bars_{t}.csv.gz', parse_dates=['et']); b['session'] = pd.to_datetime(b['session']).dt.date
    b = b[(b.session >= start) & (b.session <= end)]; tm = b['et'].dt.time
    rth = b[(tm >= pd.Timestamp('09:30').time()) & (tm < pd.Timestamp('16:00').time())]
    for s, g in rth.groupby('session'):
        if (t, s) not in q10i.index: continue
        row = q10i.loc[(t, s)]; a = row['atr_prev']
        if not (a > 0) or pd.isna(row['pre_high']) or pd.isna(row['pre_low']): continue
        for sign, trig in [(1, row['pre_high']), (-1, row['pre_low'])]:
            e_lo, e_hi, stop, t1 = side_plan(sign, trig, 0.25 * a, 1.0 * a, 1.0 * a)
            out = sim(g, sign, e_lo, e_hi, stop, t1)
            res2.append(dict(ticker=t, session=s, sign=sign, fill=out is not None, outcome=out[3] if out else None, R=out[4] if out else np.nan))
r2 = pd.DataFrame(res2); f2 = r2[r2.fill]
print('\nsame plan on the daily table pre_high/pre_low: sides', len(r2), 'fills', len(f2), 'win %.1f%%' % (100 * (f2.R > 0).mean()), 'T1/stop/close', f2.outcome.value_counts().to_dict(), 'total R %+.1f' % f2.R.sum())
