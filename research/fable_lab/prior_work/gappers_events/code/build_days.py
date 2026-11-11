"""One row per ticker session, 2025-03-03 to 2026-11-10: gap features, premarket features, outcomes.
Inputs: 1-min bars (bars_raw), brief_rows.json (08:30 rows for ATR and the level ladder), calendar/report_days.csv.
Outputs: days.csv and cache/sessions.pkl (regular-session arrays for the strategy scripts).
Usage: python3 build_days.py"""
import os, pickle
import numpy as np
import pandas as pd
from common import *

rows = brief_rows(); cal = calendar()
ev = cal.groupby('date').apply(lambda g: '+'.join(sorted(set(g.event)))).to_dict()
tier = cal.groupby('date').tier.min().to_dict()
ev830 = cal[cal.time_et == '08:30'].groupby('date').apply(lambda g: '+'.join(sorted(set(g.event)))).to_dict()
t1_830 = set(cal[(cal.time_et == '08:30') & (cal.tier == 1)].date)
out = []; cache = {}
for t in T:
    b = bars(t); b = b[b.index >= '2025-02-01']
    days = sorted({d.strftime('%Y-%m-%d') for d in b.index.normalize().unique()})
    tod = b.index.hour * 60 + b.index.minute
    prev = None; pmv_hist = []; pmv830_hist = []; own_tr = []
    for day in days:
        m = b.index.normalize() == pd.Timestamp(day)
        d = b[m]; td = tod[m]
        r = d[(td >= 570) & (td <= 959)]
        if len(r) < 300:      # same half-day / missing-day rule as the earlier scoring (hscore.py)
            continue
        pre = d[(td >= 240) & (td < 570)]
        h, l, o, c, v = (r[k].values.astype(float) for k in ('high', 'low', 'open', 'close', 'volume'))
        ti = (r.index.hour * 60 + r.index.minute).values
        cur = dict(day=day, hi=h.max(), lo=l.min(), close=c[-1], open=o[0])
        pmv = float(pre.volume.sum()); pmv830 = float(pre[(pre.index.hour * 60 + pre.index.minute) < 510].volume.sum())
        br0 = rows.get((day, t, '08:30'))
        if prev is None and br0 and day >= HOLDOUT[0]:   # first session of the history: prior day from the brief row
            prev = dict(day=None, hi=br0['pdh'], lo=br0['pdl'], close=br0['prior_close'], open=None)
            pmv_hist.append(pmv); pmv830_hist.append(pmv830)
        if prev is None or day < HOLDOUT[0]:
            if prev is not None:
                own_tr.append(max(cur['hi'] - cur['lo'], abs(cur['hi'] - prev['close']), abs(cur['lo'] - prev['close'])))
            prev = cur; pmv_hist.append(pmv); pmv830_hist.append(pmv830); continue
        br = rows.get((day, t, '08:30'))
        pc = prev['close']; pdh, pdl = prev['hi'], prev['lo']
        atr = (br or {}).get('atr') or float(np.mean(own_tr[-14:]))
        O = o[0]; gap = O - pc; sgn = 1 if gap > 0 else -1 if gap < 0 else 0
        pt = (pre.index.hour * 60 + pre.index.minute).values; pcl = pre.close.values.astype(float)
        def last_before(mins):
            k = pcl[pt < mins]; return float(k[-1]) if len(k) else np.nan
        p829, p919, p929 = last_before(510), last_before(560), last_before(570)
        def rng(a, z):
            k = pcl[(pt >= a) & (pt < z)]; return (float(k.max()), float(k.min())) if len(k) else (np.nan, np.nan)
        pm_hi_830, pm_lo_830 = rng(240, 510)       # premarket closes 04:00-08:29 (what an 08:30 run can see)
        pm_hi_920, pm_lo_920 = rng(240, 560)       # 04:00-09:19
        pm_hi_all, pm_lo_all = rng(240, 570)       # 04:00-09:29
        post_hi, post_lo = rng(510, 570)           # 08:30-09:29 only (post-release range)
        v830 = float(pre.volume.values[pt == 510].sum()); vprev = pre.volume.values[(pt >= 480) & (pt < 510)]
        spike830 = v830 / (np.median(vprev) if len(vprev) and np.median(vprev) > 0 else np.nan)
        x = dict(day=day, ticker=t, window=window(day), atr=atr, prior_close=pc, pdh=pdh, pdl=pdl, open=O, close=c[-1],
                 gap=gap, gap_atr=gap / atr, gap_pct=100 * gap / pc, gap_dir=sgn,
                 gap_loc='above_pdh' if O > pdh else 'below_pdl' if O < pdl else 'inside',
                 ind_gap_0829_atr=(p829 - pc) / atr, ind_gap_0919_atr=(p919 - pc) / atr,
                 pm_vol=pmv, pm_vol_rel=pmv / np.median(pmv_hist[-20:]), pm_vol0830_rel=pmv830 / np.median(pmv830_hist[-20:]),
                 pm_trend_atr=(p929 - p829) / atr, react_atr=(p929 - p829) / atr,
                 pm_hi_830=pm_hi_830, pm_lo_830=pm_lo_830, pm_hi_920=pm_hi_920, pm_lo_920=pm_lo_920,
                 pm_hi_all=pm_hi_all, pm_lo_all=pm_lo_all, post_hi=post_hi, post_lo=post_lo, spike830=spike830,
                 events=ev.get(day, ''), events_0830=ev830.get(day, ''), tier=tier.get(day, 0),
                 t1_0830=int(day in t1_830), fomc=int('FOMC' in ev.get(day, '')))
        # ---- outcomes from the open
        def at(mins):   # close of the bar ending just before `mins`
            k = np.where(ti < mins)[0]; return c[k[-1]]
        for lab, mins in (('15', 585), ('30', 600), ('60', 630)):
            x[f'ret{lab}_atr'] = (at(mins) - O) / atr
        x['oc_atr'] = (c[-1] - O) / atr
        x['or5_hi'], x['or5_lo'], x['c5'] = h[ti < 575].max(), l[ti < 575].min(), at(575)
        x['or15_hi'], x['or15_lo'], x['c15'] = h[ti < 585].max(), l[ti < 585].min(), at(585)
        if sgn:
            fill = (l <= pc) if sgn > 0 else (h >= pc)
            fi = int(np.argmax(fill)) if fill.any() else None
            x['fill'] = int(fi is not None); x['fill_min'] = int(ti[fi] - 570) if fi is not None else np.nan
            for lab, mins in (('15', 585), ('30', 600), ('60', 630)):
                x[f'fill{lab}'] = int(fi is not None and ti[fi] < mins)
            fav = (np.maximum.accumulate(h) - O) if sgn > 0 else (O - np.minimum.accumulate(l))
            adv = (O - np.minimum.accumulate(l)) if sgn > 0 else (np.maximum.accumulate(h) - O)
            x['mfe_gapdir_atr'] = fav[-1] / atr; x['mae_gapdir_atr'] = adv[-1] / atr
            for k in (0.25, 0.5):
                fa = np.argmax(fav >= k * atr) if (fav >= k * atr).any() else 10**6
                ad = np.argmax(adv >= k * atr) if (adv >= k * atr).any() else 10**6
                x[f'go{k}_first'] = int(fa < ad); x[f'fade{k}_first'] = int(ad < fa)
            # half-gap fill and gap extension by the same amount
            x['halffill'] = int(adv[-1] >= abs(gap) / 2)
            # next ladder level in the gap direction, at least 0.1 ATR beyond the open
            lv = sorted(set((br or {}).get('levels', {}).values()))
            nxt = [p for p in lv if (p - O) * sgn >= 0.1 * atr]
            nl = (min(nxt) if sgn > 0 else max(nxt)) if nxt else np.nan
            x['next_lvl'] = nl; x['next_lvl_dist_atr'] = abs(nl - O) / atr if nxt else np.nan
            if nxt:
                reach = (h >= nl) if sgn > 0 else (l <= nl)
                ri = int(np.argmax(reach)) if reach.any() else None
                x['next_lvl_hit'] = int(ri is not None)
                x['next_lvl_before_fill'] = int(ri is not None and (fi is None or ri < fi))
        out.append(x)
        cache[(day, t)] = dict(h=h, l=l, o=o, c=c, v=v, ti=ti, atr=atr, pc=pc)
        own_tr.append(max(cur['hi'] - cur['lo'], abs(cur['hi'] - pc), abs(cur['lo'] - pc)))
        prev = cur; pmv_hist.append(pmv); pmv830_hist.append(pmv830)
df = pd.DataFrame(out).sort_values(['day', 'ticker'])
df.to_csv(f'{LANE}/days.csv', index=False)
os.makedirs(f'{LANE}/cache', exist_ok=True)
pickle.dump(cache, open(f'{LANE}/cache/sessions.pkl', 'wb'))
print(len(df), 'ticker sessions', df.day.nunique(), 'days', df.groupby('window').size().to_dict())
