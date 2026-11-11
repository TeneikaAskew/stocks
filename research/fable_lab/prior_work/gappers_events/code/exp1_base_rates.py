"""Experiment 1: gap base rates (H0, H1a to H1g). Reads days.csv + brief_rows.json. Writes results_exp1.csv
and prints the tables. Usage: python3 exp1_base_rates.py"""
import numpy as np, pandas as pd
from common import *
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 500)
d = pd.read_csv(f'{LANE}/days.csv', keep_default_na=False, na_values=['', 'nan'])
rows = brief_rows(); R = []
def emit(hyp, variant, win, tick, metric, vals, days, pct=True):
    vals = np.asarray(vals, float); ok = ~np.isnan(vals); vals = vals[ok]; days = np.asarray(days)[ok]
    if len(vals) == 0: return
    lo, hi = boot(vals, days); k = 100 if pct else 1
    R.append(dict(experiment='1', hypothesis=hyp, variant=variant, window=win, ticker=tick, metric=metric, n=len(vals),
                  value=round(k * vals.mean(), 2), lo=round(k * lo, 2), hi=round(k * hi, 2)))
def slices(df):
    for win in ('primary', 'holdout'):
        w = df[df.window == win]
        yield win, 'ALL', w
        for t in T: yield win, t, w[w.ticker == t]
def call_dir(s):
    s = (s or '').upper(); return 1 if s.startswith('CALL') else -1 if s.startswith('PUT') else 0
d['call'] = [call_dir(rows[(a, b, '08:30')]['status']) for a, b in zip(d.day, d.ticker)]
d['absgap'] = d.gap_atr.abs()
BINS = [0, 0.1, 0.25, 0.5, 1.0, 99]; LAB = ['<0.10', '0.10-0.25', '0.25-0.50', '0.50-1.00', '>=1.00']
d['size'] = pd.cut(d.absgap, BINS, labels=LAB, right=False)
d['size_pct'] = pd.cut(d.gap_pct.abs(), [0, 0.1, 0.25, 0.5, 1.0, 99], labels=['<0.10%', '0.10-0.25%', '0.25-0.50%', '0.50-1.00%', '>=1.00%'], right=False)
g = d[d.gap_dir != 0].copy()
for k in ('15', '30', '60'): g[f'go{k}'] = (g[f'ret{k}_atr'] * g.gap_dir > 0).astype(float); g[f'r{k}'] = g[f'ret{k}_atr'] * g.gap_dir
g['oc_go'] = (g.oc_atr * g.gap_dir > 0).astype(float); g['oc_r'] = g.oc_atr * g.gap_dir

# ---- H0: is "gap agrees with call" just the head start?
c = d[(d.call != 0) & (d.gap_dir != 0)].copy()
c['agree'] = np.where(c.call == c.gap_dir, 'gap_with_call', 'gap_against_call')
c['right_prior'] = ((c.close - c.prior_close) * c.call > 0).astype(float)
c['right_open'] = (c.oc_atr * c.call > 0).astype(float); c['oc_call'] = c.oc_atr * c.call
for win, tk, w in slices(c):
    for a, s in w.groupby('agree'):
        emit('H0', a, win, tk, 'call right at close vs PRIOR close %', s.right_prior, s.day)
        emit('H0', a, win, tk, 'call right at close vs OPEN %', s.right_open, s.day)
        emit('H0', a, win, tk, 'open-to-close move in call direction (ATR)', s.oc_call, s.day, pct=False)
# ---- H1a/c/d by size bucket (ATR and %)
MET = [('fill', 'gap filled same day %'), ('fill15', 'filled in first 15 min %'), ('fill30', 'filled in first 30 min %'), ('fill60', 'filled in first 60 min %'),
       ('halffill', 'half the gap filled %'), ('go15', 'first 15 min went WITH gap %'), ('go30', 'first 30 min went WITH gap %'), ('go60', 'first 60 min went WITH gap %'),
       ('oc_go', 'close beyond open WITH gap %'), ('go0.25_first', '0.25 ATR with gap before 0.25 against %'), ('go0.5_first', '0.5 ATR with gap before 0.5 against %'),
       ('fade0.5_first', '0.5 ATR against gap before 0.5 with %'),
       ('next_lvl_hit', 'next ladder level reached %'), ('next_lvl_before_fill', 'next ladder level before fill %')]
for col, hyp in (('size', 'H1a'), ('size_pct', 'H1a_pct')):
    for win, tk, w in slices(g):
        for b, s in w.groupby(col, observed=True):
            for m, lab in MET: emit(hyp, f'|gap| {b}' + (' ATR' if col == 'size' else ''), win, tk, lab, s[m], s.day)
            emit(hyp, f'|gap| {b}' + (' ATR' if col == 'size' else ''), win, tk, 'open-to-close move with gap (ATR)', s.oc_r, s.day, pct=False)
            emit(hyp, f'|gap| {b}' + (' ATR' if col == 'size' else ''), win, tk, 'first 30 min move with gap (ATR)', s.r30, s.day, pct=False)
            R.append(dict(experiment='1', hypothesis=hyp, variant=f'|gap| {b}' + (' ATR' if col == 'size' else ''), window=win, ticker=tk, metric='median minutes to fill (filled only)', n=int(s.fill.sum()), value=s.fill_min.median(), lo=np.nan, hi=np.nan))
    for win, tk, w in slices(g):
        for dr, s in w.groupby(np.where(w.gap_dir > 0, 'gap UP', 'gap DOWN')):
            for b, s2 in s.groupby('size', observed=True):
                for m, lab in (('fill', 'gap filled same day %'), ('oc_go', 'close beyond open WITH gap %')): emit('H1a_dir', f'{dr} {b} ATR', win, tk, lab, s2[m], s2.day)
# ---- H1b location, among gaps >= 0.25 ATR, and all
big = g[g.absgap >= 0.25].copy(); big['out'] = np.where(big.gap_loc == 'inside', 'opens inside prior range', 'opens outside prior range')
for win, tk, w in slices(big):
    for a, s in w.groupby('out'):
        for m, lab in MET[:1] + MET[8:11] + MET[12:]: emit('H1b', a + ' (|gap|>=0.25 ATR)', win, tk, lab, s[m], s.day)
        emit('H1b', a + ' (|gap|>=0.25 ATR)', win, tk, 'open-to-close move with gap (ATR)', s.oc_r, s.day, pct=False)
# ---- H1e premarket volume, H1f premarket trend (gaps >= 0.25 ATR)
big['pmvol'] = np.where(big.pm_vol_rel >= 1.5, 'premarket volume >= 1.5x own median', 'premarket volume < 1.5x')
big['pmtr'] = np.where(big.pm_trend_atr * big.gap_dir > 0.05, '08:30-09:29 drift WITH gap', np.where(big.pm_trend_atr * big.gap_dir < -0.05, '08:30-09:29 drift AGAINST gap', 'flat'))
for hyp, col in (('H1e', 'pmvol'), ('H1f', 'pmtr')):
    for win, tk, w in slices(big):
        for a, s in w.groupby(col):
            for m, lab in MET[:1] + MET[8:11]: emit(hyp, a + ' (|gap|>=0.25 ATR)', win, tk, lab, s[m], s.day)
            emit(hyp, a + ' (|gap|>=0.25 ATR)', win, tk, 'open-to-close move with gap (ATR)', s.oc_r, s.day, pct=False)
# ---- H1g: does the gap seen at 08:29 / 09:19 survive to the open?
for lab, col in (('08:29', 'ind_gap_0829_atr'), ('09:19', 'ind_gap_0919_atr')):
    for thr in (0.1, 0.25, 0.5):
        k = d[d[col].abs() >= thr]
        for win, tk, w in slices(k):
            emit('H1g', f'indicated gap at {lab} >= {thr} ATR', win, tk, 'same sign as 09:30 gap %', (np.sign(w[col]) == np.sign(w.gap_atr)).astype(float), w.day)
            emit('H1g', f'indicated gap at {lab} >= {thr} ATR', win, tk, 'open gap also >= same size, same sign %', ((np.sign(w[col]) == np.sign(w.gap_atr)) & (w.absgap >= thr)).astype(float), w.day)
res = pd.DataFrame(R); res.to_csv(f'{LANE}/results_exp1.csv', index=False)
def show(hyp, metrics=None, tick='ALL'):
    r = res[(res.hypothesis == hyp) & (res.ticker == tick)]
    if metrics: r = r[r.metric.isin(metrics)]
    r = r.assign(cell=r.value.astype(str) + ' [' + r.lo.astype(str) + ', ' + r.hi.astype(str) + '] n=' + r.n.astype(str))
    print(f'\n=== {hyp} ({tick})'); print(r.pivot_table(index=['metric', 'variant'], columns='window', values='cell', aggfunc='first', sort=False)[['primary', 'holdout']].to_string())
if __name__ == '__main__':
    print('gap days', len(g), g.groupby(['window', 'size'], observed=True).size().unstack().to_string())
    show('H0'); show('H1a'); show('H1a_dir'); show('H1b'); show('H1e'); show('H1f'); show('H1g')
    for t in T: show('H1a', ['gap filled same day %', 'close beyond open WITH gap %', '0.5 ATR with gap before 0.5 against %'], t)
