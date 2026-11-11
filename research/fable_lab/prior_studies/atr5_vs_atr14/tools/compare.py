"""Paired ATR5 minus ATR14 comparison of two replay sets, scored exactly as
scratchpad hist/hscore.py does (brief triggers both sides with the brief's
stop and T1; every persona plan at its entry-zone midpoint, stop and first
target; R = move / |fill - stop|, on bars_raw 09:30-15:59), with a 90%
bootstrap range by day (2000 resamples of session days, seed 7, as paired.py).
Usage: compare.py <dirA> <prefixA> <dirB> <prefixB> <window label> <out_dir>
Writes <out_dir>/sessions_<label>.csv and summary_<label>.json; A = ATR14."""
import sys, json, random, statistics as st
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from hscore_local import score
da, pa, db, pb, label, out = sys.argv[1:7]
out = Path(out); out.mkdir(parents=True, exist_ok=True)
A = {(r['day'], r['t']): r for r in score(da, pa)}
B = {(r['day'], r['t']): r for r in score(db, pb)}
keys = sorted(set(A) & set(B))
def raw(d, p, day):
    return json.load(open(f'{d}/{p}_{day}.json'))
FIELDS = ('calls_trigger_price', 'puts_trigger_price', 'calls_stop_price', 'puts_stop_price', 'calls_t1_price', 'puts_t1_price')
rows = []
cache = {}
for day, t in keys:
    if day not in cache:
        cache[day] = (raw(da, pa, day), raw(db, pb, day))
    ea, eb = cache[day][0]['tickers'][t], cache[day][1]['tickers'][t]
    ra, rb = A[(day, t)], B[(day, t)]
    trig = lambda r: sum(v for v in r['trig'].values() if v is not None)
    pl = lambda r: sum(x[2] for x in r['plans'])
    row = dict(day=day, ticker=t, atr14=(ea.get('level_basis') or {}).get('atr'), atr5=(eb.get('level_basis') or {}).get('atr'),
               basis_a=(ea.get('level_basis') or {}).get('atr_basis'), basis_b=(eb.get('level_basis') or {}).get('atr_basis'),
               trig_R_atr14=round(trig(ra), 2), trig_R_atr5=round(trig(rb), 2), trig_fills_atr14=sum(v is not None for v in ra['trig'].values()),
               trig_fills_atr5=sum(v is not None for v in rb['trig'].values()),
               plan_R_atr14=round(pl(ra), 2), plan_R_atr5=round(pl(rb), 2), plan_fills_atr14=len(ra['plans']), plan_fills_atr5=len(rb['plans']))
    row['trig_R_diff'] = round(row['trig_R_atr5'] - row['trig_R_atr14'], 2)
    row['plan_R_diff'] = round(row['plan_R_atr5'] - row['plan_R_atr14'], 2)
    for f in FIELDS:
        x, y = ea.get(f), eb.get(f)
        row[f'{f}_atr14'], row[f'{f}_atr5'] = x, y
        row[f'{f}_absdiff'] = abs(y - x) if x is not None and y is not None else None
    # plan entry midpoints, stops and first targets, per side and persona
    ent, stp, tg1, nplans = [], [], [], [0, 0]
    pa_, pb_ = ea.get('_plans') or {}, eb.get('_plans') or {}
    for side in ('long', 'short'):
        la = {p['persona']: p for p in (pa_.get(side) if isinstance(pa_.get(side), list) else []) if p.get('entry')}
        lb = {p['persona']: p for p in (pb_.get(side) if isinstance(pb_.get(side), list) else []) if p.get('entry')}
        nplans[0] += len(la); nplans[1] += len(lb)
        for k in set(la) & set(lb):
            ent.append(abs(sum(lb[k]['entry']) / 2 - sum(la[k]['entry']) / 2))
            stp.append(abs(lb[k]['stop'] - la[k]['stop']))
            if la[k]['targets'] and lb[k]['targets'] and la[k]['targets'][0] is not None and lb[k]['targets'][0] is not None:
                tg1.append(abs(lb[k]['targets'][0] - la[k]['targets'][0]))
    row.update(plans_published_atr14=nplans[0], plans_published_atr5=nplans[1],
               plan_entry_mid_absdiff_med=float(np.median(ent)) if ent else None,
               plan_stop_absdiff_med=float(np.median(stp)) if stp else None,
               plan_t1_absdiff_med=float(np.median(tg1)) if tg1 else None)
    pma = ((ea.get('level_basis') or {}).get('premarket') or {}); pmb = ((eb.get('level_basis') or {}).get('premarket') or {})
    row['pm_high_low_changed'] = (pma.get('pre_high'), pma.get('pre_low')) != (pmb.get('pre_high'), pmb.get('pre_low'))
    rows.append(row)
df = pd.DataFrame(rows)
df.to_csv(out / f'sessions_{label}.csv', index=False)
def boot(per_day):
    diffs = list(per_day); random.seed(7)
    b = sorted(sum(random.choice(diffs) for _ in diffs) for _ in range(2000)) if diffs else [0]
    return [round(float(b[100]), 2), round(float(b[1900]), 2)]
summ = {'window': label, 'sessions': int(df.day.nunique()), 'by': {}}
ratio = df.atr5 / df.atr14
SETS = [('SPY', df.ticker == 'SPY'), ('QQQ', df.ticker == 'QQQ'), ('IWM', df.ticker == 'IWM'), ('total', df.ticker.notna()),
        # where the two bases disagree most (the case the hypothesis is about)
        ('vol rising (ATR5/ATR14 > 1.15)', ratio > 1.15), ('vol falling (ATR5/ATR14 < 0.85)', ratio < 0.85),
        ('vol steady (0.85 to 1.15)', (ratio >= 0.85) & (ratio <= 1.15))]
for name, sel in SETS:
    x = df[sel]; o = {}
    for what in ('trig', 'plan'):
        per = x.groupby('day')[f'{what}_R_diff'].sum()
        o[what] = dict(atr14_R=round(float(x[f'{what}_R_atr14'].sum()), 2), atr5_R=round(float(x[f'{what}_R_atr5'].sum()), 2),
                       diff_R=round(float(per.sum()), 2), ci90=boot(per.values),
                       fills_atr14=int(x[f'{what}_fills_atr14'].sum()), fills_atr5=int(x[f'{what}_fills_atr5'].sum()),
                       avg_atr14=round(float(x[f'{what}_R_atr14'].sum() / max(1, x[f'{what}_fills_atr14'].sum())), 3),
                       avg_atr5=round(float(x[f'{what}_R_atr5'].sum() / max(1, x[f'{what}_fills_atr5'].sum())), 3))
    lv = {}
    for f in FIELDS:
        c = x[f'{f}_absdiff'].dropna()
        lv[f] = dict(n=int(len(c)), changed=int((c > 0.005).sum()), median_abs_pts=round(float(c.median()), 3) if len(c) else None,
                     median_abs_pts_when_changed=round(float(c[c > 0.005].median()), 3) if (c > 0.005).any() else None)
    for f in ('plan_entry_mid_absdiff_med', 'plan_stop_absdiff_med', 'plan_t1_absdiff_med'):
        c = x[f].dropna(); lv[f] = round(float(c.median()), 3) if len(c) else None
    lv['atr5_over_atr14_median'] = round(float((x.atr5 / x.atr14).median()), 3)
    lv['atr5_over_atr14_p10_p90'] = [round(float((x.atr5 / x.atr14).quantile(q)), 3) for q in (.1, .9)]
    lv['premarket_high_low_changed_sessions'] = int(x.pm_high_low_changed.sum())
    o['levels'] = lv
    o['ticker_sessions'] = int(len(x))
    summ['by'][name] = o
(out / f'summary_{label}.json').write_text(json.dumps(summ, indent=1))
for k, v in summ['by'].items():
    print(label, k, 'trig', v['trig']['diff_R'], v['trig']['ci90'], 'plan', v['plan']['diff_R'], v['plan']['ci90'])
