"""Weekly walk-forward, per ticker, original vs fixed scoring, plus two improvements.

  python -I code/walkforward.py

For each ticker, each eval week W, each lookback N in (1, 4, 12) weeks:
  ORIGINAL  rank every condition by the script's own measure (average 20-row max
            favourable move, all bars incl. extended hours) over weeks W-N..W-1, pick the top.
            Claimed win rate = share of fires whose 20-row max favourable move > 0
            (this is what the API's pct_profitable reports).
  FIXED     rank every condition by its average REAL-exit result (net of a 1 cent cost)
            over weeks W-N..W-1, regular hours, no overlapping positions, pick the top.
  Realized  trade the pick during week W with the real exit. Exit A: enter next bar open,
            exit 20 bars later or at the 15:55 open (bps). Exit B: stop 0.5 ATR, target 1 ATR,
            else the 15:55 open (R, 1R = 0.5 ATR).
Also: VOTER (the script's call/put voter as written, which is what feeds historical_signals),
BASELINE (long every bar, non-overlapping), PERSIST (improvement 1) and REGIME (improvement 2).
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from common2 import TICKERS, WORK, ROOT

NS = (1, 4, 12)
FIRST_EVAL = pd.Timestamp('2025-05-26')      # 12 full weeks after the first bar (2025-03-03)
SIX_MONTHS = pd.Timestamp('2026-05-11')      # last 26 eval weeks start here
BASE = 'CAND all bars (baseline) | long'
VOTERS = ['VOTER call (as written)', 'VOTER put (as written)']


def realized(tr):
    if len(tr) == 0:
        return dict(real_n=0, real_win=np.nan, real_avg=np.nan, real_sum=0.0, real_sum_net=0.0)
    r = tr['ret'].values; c = tr['cost'].values
    return dict(real_n=len(r), real_win=float((r > 0).mean()), real_avg=float(r.mean()),
                real_sum=float(r.sum()), real_sum_net=float((r - c).sum()))


def fit_fixed(trw, weeks, min_n):
    g = trw[trw['week'].isin(weeks)].assign(net=lambda x: x['ret'] - x['cost']).groupby('cond', observed=True)
    s = pd.DataFrame({'n': g.size(), 'avg': g['net'].mean(), 'win': g['ret'].apply(lambda x: (x > 0).mean())})
    return s[s['n'] >= min_n].sort_values('avg', ascending=False)


def main():
    rows = []
    for T in TICKERS:
        TR = pd.read_parquet(f'{WORK}/{T}_trades.parquet')
        TR['cond'] = TR['cond'].astype(str); TR['src'] = TR['src'].astype(str); TR['exit'] = TR['exit'].astype(str)
        CW = pd.read_parquet(f'{WORK}/{T}_orig_condweek.parquet')
        SG = pd.read_parquet(f'{WORK}/{T}_orig_signals.parquet')
        weeks = np.sort(TR['week'].unique())
        evalw = [w for w in weeks if w >= FIRST_EVAL]
        for ex in ['A', 'B']:
            fx = TR[(TR.src == 'fixed') & (TR.exit == ex)]
            og = TR[(TR.src == 'orig') & (TR.exit == ex)]
            fx_by_w = {w: g for w, g in fx.groupby('week')}
            og_by_w = {w: g for w, g in og.groupby('week')}
            empty = fx.iloc[:0]
            for W in evalw:
                i = int(np.searchsorted(weeks, W))
                fw = fx_by_w.get(W, empty); ow = og_by_w.get(W, empty)
                base = dict(ticker=T, week=pd.Timestamp(W).date(), exit=ex)
                # voter as written and baseline (no fitting)
                sw = SG[SG['week'] == W]
                rows.append({**base, 'N': 0, 'method': 'VOTER', 'top1': 'voter call+put',
                             'claimed_win': float((sw['return_pct'] > 0).mean()) if len(sw) else np.nan,
                             'claimed_avg': float(sw['return_pct'].mean()) if len(sw) else np.nan,
                             **realized(ow[ow['cond'].isin(VOTERS)])})
                rows.append({**base, 'N': 0, 'method': 'BASELINE', 'top1': BASE, **realized(fw[fw['cond'] == BASE])})
                for N in NS:
                    prior = weeks[max(0, i - N):i]
                    # ORIGINAL: average 20-row MFE, all bars
                    c = CW[CW['week'].isin(prior)].groupby('cond').agg(n=('n', 'sum'), s=('sum_mfe', 'sum'), w=('wins', 'sum'))
                    c = c[c['n'] >= 30 * N]; c['avg'] = c['s'] / c['n']; c['win'] = c['w'] / c['n']
                    c = c.sort_values('avg', ascending=False)
                    top = list(c.index[:3])
                    rows.append({**base, 'N': N, 'method': 'ORIGINAL', 'top1': top[0], 'top3': ' ; '.join(top),
                                 'claimed_win': c['win'].iloc[0], 'claimed_avg': c['avg'].iloc[0],
                                 **realized(ow[ow['cond'] == top[0]])})
                    # VOTER claim over the same fit window (what pct_profitable would show)
                    sp = SG[SG['week'].isin(prior)]
                    rows[-1]['voter_claimed_win_fit'] = float((sp['return_pct'] > 0).mean()) if len(sp) else np.nan
                    # FIXED: real exit, net of cost
                    f = fit_fixed(fx, prior, 3 * N)
                    top = list(f.index[:3])
                    rows.append({**base, 'N': N, 'method': 'FIXED', 'top1': top[0], 'top3': ' ; '.join(top),
                                 'claimed_win': f['win'].iloc[0], 'claimed_avg': f['avg'].iloc[0],
                                 **realized(fw[fw['cond'] == top[0]])})
                # IMPROVEMENT 1, PERSIST: positive over 12 weeks AND positive in >= 3 of the last 4 weeks
                prior12 = weeks[max(0, i - 12):i]; last4 = weeks[max(0, i - 4):i]
                f12 = fit_fixed(fx, prior12, 36)
                f12 = f12[f12['avg'] > 0]
                wk = fx[fx['week'].isin(last4) & fx['cond'].isin(f12.index)].assign(net=lambda x: x['ret'] - x['cost'])
                wm = wk.groupby(['cond', 'week'])['net'].agg(['mean', 'size'])
                pos_weeks = ((wm['mean'] > 0) & (wm['size'] >= 2)).groupby(level=0).sum()
                ok = [k for k in f12.index if pos_weeks.get(k, 0) >= 3]
                if ok:
                    k = ok[0]
                    rows.append({**base, 'N': 12, 'method': 'PERSIST', 'top1': k, 'top3': ' ; '.join(ok[:3]),
                                 'claimed_win': f12.loc[k, 'win'], 'claimed_avg': f12.loc[k, 'avg'],
                                 **realized(fw[fw['cond'] == k])})
                else:
                    rows.append({**base, 'N': 12, 'method': 'PERSIST', 'top1': '(no trade)', **realized(empty)})
                # IMPROVEMENT 2, REGIME: rank separately for days above / below the 50-day average
                picks, parts = [], []
                for rg in ['up', 'down']:
                    fr = fit_fixed(fx[fx['regime'] == rg], prior12, 18)
                    if len(fr):
                        k = fr.index[0]; picks.append(f'{rg}: {k}')
                        parts.append(fw[(fw['cond'] == k) & (fw['regime'] == rg)])
                rows.append({**base, 'N': 12, 'method': 'REGIME', 'top1': ' | '.join(picks),
                             **realized(pd.concat(parts) if parts else empty)})
        print(T, 'done', flush=True)
    R = pd.DataFrame(rows)
    R.to_csv(f'{ROOT}/weekly_results.csv', index=False)
    return R


if __name__ == '__main__':
    main()
