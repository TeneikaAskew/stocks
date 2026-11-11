"""Summary tables and equity curves from weekly_results.csv.

  python -I code/summarize2.py
Writes summary_by_ticker.csv, summary.md, charts/equity_{T}.png
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates
from common2 import TICKERS, ROOT

SIX = pd.Timestamp('2026-05-11').date()
R = pd.read_csv(f'{ROOT}/weekly_results.csv', parse_dates=['week'])
R['week'] = R['week'].dt.date


def stab(g):
    t = g.sort_values('week')['top1'].tolist()
    same = np.mean([a == b for a, b in zip(t[1:], t[:-1])]) if len(t) > 1 else np.nan
    if 'top3' in g and g['top3'].notna().any():
        s3 = [set(str(x).split(' ; ')) for x in g.sort_values('week')['top3']]
        jac = np.mean([len(a & b) / len(a | b) for a, b in zip(s3[1:], s3[:-1])])
    else:
        jac = np.nan
    return same, jac, g['top1'].nunique()


rows = []
for (T, ex, m, N), g in R.groupby(['ticker', 'exit', 'method', 'N']):
    for per, gg in [('all', g), ('last26', g[g['week'] >= SIX])]:
        n = gg['real_n'].sum()
        ws = gg['real_sum_net'].values
        t = ws.mean() / (ws.std(ddof=1) / np.sqrt(len(ws))) if len(ws) > 2 and ws.std() > 0 else np.nan
        same, jac, uniq = stab(gg)
        rows.append(dict(ticker=T, exit=ex, method=m, N=N, period=per, weeks=len(gg), weeks_traded=int((gg['real_n'] > 0).sum()),
                         trades=int(n), claimed_win=gg['claimed_win'].mean(), real_win=(gg['real_win'] * gg['real_n']).sum() / n if n else np.nan,
                         claimed_avg=gg['claimed_avg'].mean(), real_avg_gross=gg['real_sum'].sum() / n if n else np.nan,
                         real_total_net=ws.sum(), pct_weeks_positive=float((ws > 0).sum() / max(1, (gg['real_n'] > 0).sum())),
                         t_weekly=t, top1_same_as_prev_week=same, top3_jaccard_prev_week=jac, distinct_top1=uniq))
S = pd.DataFrame(rows)
S.to_csv(f'{ROOT}/summary_by_ticker.csv', index=False)

# ---- equity curves ----
SERIES = [('ORIGINAL', 4, 'Original top pick (4 wk fit)', '#2a78d6', '-'),
          ('FIXED', 4, 'Fixed top pick (4 wk fit)', '#eb6834', '-'),
          ('VOTER', 0, 'Voter as written', '#1baf7a', '--'),
          ('PERSIST', 12, 'Improvement 1: persistence', '#eda100', '-.'),
          ('REGIME', 12, 'Improvement 2: regime split', '#e87ba4', ':'),
          ('BASELINE', 0, 'Long every bar (benchmark)', '#008300', (0, (1, 3)))]
plt.rcParams.update({'font.size': 10, 'axes.edgecolor': '#52514e', 'axes.labelcolor': '#0b0b0b',
                     'xtick.color': '#52514e', 'ytick.color': '#52514e'})
for T in TICKERS:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.2), facecolor='#fcfcfb')
    for ax, ex, unit in [(axes[0], 'A', 'cumulative bps (sum of trades, net of 1 cent)'),
                         (axes[1], 'B', 'cumulative R (sum of trades, net of 1 cent)')]:
        ax.set_facecolor('#fcfcfb')
        for m, N, lab, col, ls in SERIES:
            g = R[(R.ticker == T) & (R.exit == ex) & (R.method == m) & (R.N == N)].sort_values('week')
            y = g['real_sum_net'].cumsum().values
            ax.plot(pd.to_datetime(g['week']), y, color=col, ls=ls, lw=2, label=lab)
            ax.annotate(f'{y[-1]:.0f}' if ex == 'A' else f'{y[-1]:.1f}', (pd.to_datetime(g['week']).iloc[-1], y[-1]),
                        xytext=(4, 0), textcoords='offset points', fontsize=8, color='#52514e', va='center')
        ax.axhline(0, color='#c3c2b7', lw=1)
        ax.axvline(pd.Timestamp(SIX), color='#c3c2b7', lw=1, ls='--')
        ax.text(pd.Timestamp(SIX), ax.get_ylim()[1], ' last 26 weeks', fontsize=8, color='#52514e', va='top')
        ax.grid(axis='y', color='#ecebe8', lw=0.8)
        for s in ['top', 'right']:
            ax.spines[s].set_visible(False)
        ax.set_ylabel(unit)
        ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%b %y'))
        ax.set_title(f'{T}, exit {ex}: ' + ('hold 20 minutes' if ex == 'A' else 'stop 0.5 ATR, target 1 ATR, flat 15:55'),
                     fontsize=11, color='#0b0b0b', loc='left')
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc='lower center', ncol=6, fontsize=9, frameon=False)
    fig.suptitle(f'{T} realized out of sample results, one week at a time (Jun 2025 to Nov 2026)',
                 fontsize=12, color='#0b0b0b', x=0.01, ha='left')
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(f'{ROOT}/charts/equity_{T}.png', dpi=110, facecolor='#fcfcfb')
    plt.close(fig)

# ---- compact markdown for the README ----
def fmt(x, p=2):
    return '' if pd.isna(x) else f'{x:.{p}f}'

keep = [('VOTER', 0), ('BASELINE', 0), ('ORIGINAL', 1), ('ORIGINAL', 4), ('ORIGINAL', 12), ('FIXED', 1), ('FIXED', 4),
        ('FIXED', 12), ('PERSIST', 12), ('REGIME', 12)]
md = []
for ex, unit in [('A', 'bps'), ('B', 'R')]:
    for per in ['last26', 'all']:
        md.append(f'\n### Exit {ex}, {"last 26 weeks (2026-05-11 to 2026-11-09)" if per == "last26" else "all 77 eval weeks (2025-05-26 to 2026-11-09)"}\n')
        md.append(f'| ticker | method | fit wks | trades | claimed win | realized win | realized avg {unit} gross | total {unit} net | t (weekly) | top pick same as last week |')
        md.append('|---|---|---|---|---|---|---|---|---|---|')
        for T in TICKERS:
            for m, N in keep:
                r = S[(S.ticker == T) & (S.exit == ex) & (S.method == m) & (S.N == N) & (S.period == per)]
                if not len(r):
                    continue
                r = r.iloc[0]
                md.append(f'| {T} | {m} | {N or ""} | {r.trades} | {fmt(r.claimed_win * 100, 0)}% | {fmt(r.real_win * 100, 0)}% | '
                          f'{fmt(r.real_avg_gross)} | {fmt(r.real_total_net, 1)} | {fmt(r.t_weekly)} | '
                          f'{"" if pd.isna(r.top1_same_as_prev_week) or m in ("VOTER", "BASELINE") else fmt(r.top1_same_as_prev_week * 100, 0) + "%"} |')
open(f'{ROOT}/summary.md', 'w').write('\n'.join(md))
print('\n'.join(md))
