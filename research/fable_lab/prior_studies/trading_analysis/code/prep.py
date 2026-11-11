"""Per ticker: run the ORIGINAL script steps on the full 1-min history and build the
inputs for the weekly walk-forward.

  python -I code/prep.py SPY      (then QQQ, IWM)

Writes work/{T}_orig_signals.parquet   generate_technical_signals output, unchanged
       work/{T}_orig_condweek.parquet  original-method score per condition per week
                                        (all bars incl. extended hours, 20-row MFE)
       work/{T}_trades.parquet         non-overlapping trades with REAL exits for every
                                        condition, flags from the original frame (src=orig)
                                        and from the regular-hours frame (src=fixed)
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from common2 import (load_bars, build_rth, build_ext, conditions, outcomes_hold, outcomes_bracket,
                     non_overlap, quiet, MarketAnalyzer, WORK, RTH_OPEN, RTH_CLOSE)

T = sys.argv[1]
t0 = time.time()
bars = load_bars(T)
d = build_rth(bars, T)
e = build_ext(bars)
print(T, 'frames', len(d), len(e), round(time.time() - t0), 's', flush=True)

# ---- 1. the original script's own signal step, unchanged (slow row loop) ----
ma = MarketAnalyzer()
sig = quiet(ma.generate_technical_signals, e)
sig = sig.drop(columns=['score_explanation'], errors='ignore')
sig['week'] = pd.to_datetime(sig['entry_time']).dt.to_period('W-SUN').dt.start_time
sig.to_parquet(f'{WORK}/{T}_orig_signals.parquet', index=False)
print(T, 'orig signals', len(sig), round(time.time() - t0), 's', flush=True)

# ---- 2. original-method score per condition per week (MFE over next 20 ROWS) ----
L = e['Last']
fmax = L[::-1].rolling(20, min_periods=20).max()[::-1].shift(-1)
fmin = L[::-1].rolling(20, min_periods=20).min()[::-1].shift(-1)
mfe = {1: ((fmax - L) / L * 100).values, -1: ((L - fmin) / L * 100).values}
Ce = conditions(e, cand_from=d)
voter = Ce['VOTER call (as written)'][0] | Ce['VOTER put (as written)'][0]
loop = np.zeros(len(e), bool); loop[3:len(e) - 20] = True
parity = dict(vectorized_voter=int((voter & loop).sum()), script_signals=len(sig))
print(T, 'parity', parity, flush=True)
rows = []
wk = e['Week'].values
for name, (s, dr) in Ce.items():
    ok = s & np.isfinite(mfe[dr])
    if not ok.any():
        continue
    g = pd.DataFrame({'week': wk[ok], 'm': mfe[dr][ok]}).groupby('week')['m']
    a = pd.DataFrame({'n': g.size(), 'sum_mfe': g.sum(), 'wins': g.apply(lambda x: (x > 0).sum())})
    a['cond'] = name; a['dir'] = dr
    rows.append(a.reset_index())
pd.concat(rows, ignore_index=True).to_parquet(f'{WORK}/{T}_orig_condweek.parquet', index=False)

# ---- 3. real-exit trades for every condition ----
Al, As, Ax, _ = outcomes_hold(d)
Bl, Bs, Bxl, Bxs = outcomes_bracket(d)
EX = {'A': {1: (Al, Ax), -1: (As, Ax)}, 'B': {1: (Bl, Bxl), -1: (Bs, Bxs)}}
cost = {'A': (0.01 / d['Open'].values) * 1e4,                              # 1 cent round trip, bps
        'B': 0.01 / (0.5 * d['ATR_D'].values)}                              # 1 cent round trip, R
Cd = conditions(d)
# original-frame flags at regular-hours timestamps, mapped onto d rows
pos = pd.Series(np.arange(len(d)), index=d['Time'].values)
emod = e['mod'].values
erth = (emod >= RTH_OPEN) & (emod < RTH_CLOSE)
Cmap = {}
for name, (s, dr) in Ce.items():
    f = np.zeros(len(d), bool)
    f[pos.reindex(e['Time'].values[s & erth]).dropna().astype(int).values] = True
    Cmap[name] = (f, dr)
out = []
for src, CC in [('fixed', Cd), ('orig', Cmap)]:
    for name, (s, dr) in CC.items():
        for ex in ['A', 'B']:
            R, X = EX[ex][dr]
            fire = np.where(s & np.isfinite(R))[0]
            if not len(fire):
                continue
            tk = non_overlap(fire, X)
            out.append(pd.DataFrame({'src': src, 'exit': ex, 'cond': name, 'dir': dr,
                                     'time': d['Time'].values[tk], 'date': d['Date'].values[tk],
                                     'week': d['Week'].values[tk], 'regime': d['REGIME'].values[tk],
                                     'ret': R[tk], 'cost': cost[ex][tk]}))
TR = pd.concat(out, ignore_index=True)
TR['src'] = TR['src'].astype('category'); TR['exit'] = TR['exit'].astype('category'); TR['cond'] = TR['cond'].astype('category')
TR.to_parquet(f'{WORK}/{T}_trades.parquet', index=False)
json.dump(dict(ticker=T, rth_rows=len(d), ext_rows=len(e), parity=parity, trades=len(TR),
               first=str(d['Time'].min()), last=str(d['Time'].max()), secs=round(time.time() - t0)),
          open(f'{WORK}/{T}_prep_meta.json', 'w'), indent=1)
print(T, 'done', len(TR), 'trades', round(time.time() - t0), 's', flush=True)
