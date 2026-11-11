"""Score the insight direction from the 09:30 open with official daily bars (market_data_daily).
Inputs (scratchpad CSVs from needs_gcp.sql): out_Q02.csv (reports), out_Q10.csv (daily), out_Q08.csv (brief vs insight).
No database access here. Bootstrap: resample session dates, 2000 draws, seed 7, 90% range."""
import sys, numpy as np, pandas as pd
S = sys.argv[1]
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 40)
q2 = pd.read_csv(f'{S}/out_Q02.csv'); q10 = pd.read_csv(f'{S}/out_Q10.csv'); q8 = pd.read_csv(f'{S}/out_Q08.csv')
q2['session_et'] = pd.to_datetime(q2['session_et']).dt.date
q10['date'] = pd.to_datetime(q10['date']).dt.date
q10 = q10.sort_values(['ticker', 'date'])
# prior-session ATR14 and the day's open/close
q10['atr_prev'] = q10.groupby('ticker')['atr_14'].shift(1)
q10['close_prev'] = q10.groupby('ticker')['close'].shift(1)
daily = q10[['ticker', 'date', 'open', 'close', 'high', 'low', 'atr_prev', 'close_prev', 'pre_high', 'pre_low']].rename(columns={'date': 'session_et'})
daily = daily[daily['open'].notna() & daily['close'].notna()]

def canonical(df):
    """One report per ticker-day: the latest run before 09:30 ET; days whose runs are all after the open are dropped."""
    pre = df[df['run_time_et'] < '09:30'].sort_values('as_of')
    return pre.groupby(['ticker', 'session_et']).tail(1)

def boot(frame, fn, n=2000, seed=7):
    """90% range of fn(frame) when session dates are resampled with replacement."""
    rng = np.random.default_rng(seed)
    dates = frame['session_et'].unique()
    groups = {d: g for d, g in frame.groupby('session_et')}
    vals = []
    for _ in range(n):
        pick = rng.choice(dates, size=len(dates), replace=True)
        vals.append(fn(pd.concat([groups[d] for d in pick])))
    return np.nanpercentile(vals, 5), np.nanpercentile(vals, 95)

def score(frame, label):
    f = frame.merge(daily, on=['ticker', 'session_et'], how='inner')
    f = f[f['direction'].isin(['long', 'short'])].copy()
    f['sign'] = np.where(f['direction'] == 'long', 1, -1)
    f['move_atr'] = (f['close'] - f['open']) / f['atr_prev']          # open -> close in prior-day ATR
    f['model_atr'] = f['sign'] * f['move_atr']                          # signed in the model's direction
    f['right'] = (f['model_atr'] > 0).astype(int)
    f['flatday'] = (f['move_atr'] == 0).astype(int)
    f['gap_atr'] = (f['open'] - f['close_prev']) / f['atr_prev']
    f['right_vs_prev_close'] = ((f['sign'] * (f['close'] - f['close_prev'])) > 0).astype(int)
    n = len(f)
    hit = f['right'].mean(); lo, hi = boot(f, lambda g: g['right'].mean())
    mean_atr = f['model_atr'].mean(); alo, ahi = boot(f, lambda g: g['model_atr'].mean())
    tot = f['model_atr'].sum(); tlo, thi = boot(f, lambda g: g['model_atr'].sum())
    print(f'\n[{label}] ticker-days={n} sessions={f.session_et.nunique()} long={int((f.sign>0).sum())} short={int((f.sign<0).sum())}')
    print(f'  right from the open: {f.right.sum()}/{n} = {100*hit:.1f}%  (90% range {100*lo:.1f}% to {100*hi:.1f}%); flat open=close days: {int(f.flatday.sum())}')
    print(f'  mean open->close move in the called direction: {mean_atr:+.3f} ATR per day (range {alo:+.3f} to {ahi:+.3f}); total {tot:+.1f} ATR (range {tlo:+.1f} to {thi:+.1f})')
    print(f'  opposite side is the mirror: {100*(1-hit):.1f}% right, {-mean_atr:+.3f} ATR per day; model minus opposite = {2*mean_atr:+.3f} ATR per day (range {2*alo:+.3f} to {2*ahi:+.3f})')
    print(f'  for reference, right vs the PRIOR CLOSE (gap counted): {f.right_vs_prev_close.sum()}/{n} = {100*f.right_vs_prev_close.mean():.1f}%; mean gap in the called direction {(f.sign*f.gap_atr).mean():+.3f} ATR')
    by = f.groupby('ticker').agg(n=('right', 'size'), right=('right', 'sum'), hit=('right', 'mean'), mean_atr=('model_atr', 'mean')).round(3)
    print(by.to_string())
    return f

live = canonical(q2[q2['run_kind'] == 'live'])
dropped = q2[(q2['run_kind'] == 'live')].groupby(['ticker', 'session_et']).size().shape[0] - live.groupby(['ticker','session_et']).size().shape[0]
print('live ticker-days with a pre-09:30 run:', len(live), ' live ticker-days with runs only after 09:30 (dropped):', dropped)
f_live = score(live, 'LIVE, latest pre-09:30 run per ticker-day')
score(live[live['conviction'] == 'medium'], 'LIVE, medium conviction only')
score(live[live['conviction'] == 'low'], 'LIVE, low conviction only')
score(live[live['session_et'] >= pd.Timestamp('2026-05-01').date()], 'LIVE, primary window 2026-05-01 onward')
score(live[live['session_et'] < pd.Timestamp('2026-05-01').date()], 'LIVE, before 2026-05-01 (Apr 15-30)')
f_live.to_csv(f'{S}/scored_live_daily.csv', index=False)
for lab, d in [('ALWAYS LONG on the same ticker-days', 'long'), ('ALWAYS SHORT on the same ticker-days', 'short')]:
    b = live.copy(); b['direction'] = d; score(b, lab)
# by month
fm = f_live.copy(); fm['month'] = pd.to_datetime(fm['session_et']).dt.to_period('M')
print('\nby month (live): n, right %, mean move in called direction (ATR)')
print(fm.groupby('month').agg(n=('right','size'), right_pct=('right', lambda s: round(100*s.mean(),1)), mean_atr=('model_atr', lambda s: round(s.mean(),3)), long_share=('sign', lambda s: round((s>0).mean(),2))).to_string())
# time horizon split
for th in ['swing','intraday']:
    score(live[live['time_horizon']==th], f'LIVE, time_horizon={th}')
# the brief's call on the same days (Q08), and agreement
q8['analysis_date'] = pd.to_datetime(q8['analysis_date']).dt.date
q8 = q8.rename(columns={'analysis_date': 'session_et'})
q8['brief_dir'] = np.where(q8['brief_status'].str.startswith('CALL', na=False), 'long', np.where(q8['brief_status'].str.startswith('PUT', na=False), 'short', 'none'))
q8['brief_setup'] = q8['brief_status'].str.contains('setup', na=False)
print('\n=== Q08: brief call vs insight direction (live premarket insight), since 2026-05-01 ===')
print('brief rows', len(q8), ' with an insight direction', q8['insight_direction'].notna().sum())
print('brief status kinds:', q8['brief_status'].str.replace(r' \(\d/5\)', '', regex=True).value_counts().to_dict())
both = q8[q8['insight_direction'].isin(['long', 'short']) & q8['brief_dir'].isin(['long', 'short'])].copy()
both['agree'] = (both['brief_dir'] == both['insight_direction'])
print(f"days both had a call: {len(both)}; agree: {int(both.agree.sum())} ({100*both.agree.mean():.1f}%)")
bs = both[both['brief_setup']]
print(f"  of which brief 'setup' (not 'building'): {len(bs)}; agree: {int(bs.agree.sum())} ({100*bs.agree.mean() if len(bs) else float('nan'):.1f}%)")
print(pd.crosstab(both['brief_dir'], both['insight_direction']))
m = both.merge(daily, on=['ticker', 'session_et'], how='inner')
for who, col in [('brief', 'brief_dir'), ('insight', 'insight_direction')]:
    s = np.where(m[col] == 'long', 1, -1); mv = s * (m['close'] - m['open']) / m['atr_prev']
    m[f'{who}_right'] = (mv > 0).astype(int); m[f'{who}_atr'] = mv
for who in ['brief', 'insight']:
    lo, hi = boot(m, lambda g, w=who: g[f'{w}_right'].mean()); alo, ahi = boot(m, lambda g, w=who: g[f'{w}_atr'].mean())
    print(f"  {who}: right from the open {int(m[f'{who}_right'].sum())}/{len(m)} = {100*m[f'{who}_right'].mean():.1f}% (range {100*lo:.1f}-{100*hi:.1f}%), mean move {m[f'{who}_atr'].mean():+.3f} ATR (range {alo:+.3f} to {ahi:+.3f})")
d = m['insight_atr'] - m['brief_atr']; dlo, dhi = boot(m, lambda g: (g['insight_atr'] - g['brief_atr']).mean())
print(f"  insight minus brief: {d.mean():+.3f} ATR per day (range {dlo:+.3f} to {dhi:+.3f}); disagreement days: {int((~m.agree).sum())}, insight right on {int(m.loc[~m.agree,'insight_right'].sum())} of them")
# brief alone on every brief day since May (any insight or not)
mb = q8[q8['brief_dir'].isin(['long','short'])].merge(daily, on=['ticker','session_et'])
s = np.where(mb['brief_dir']=='long',1,-1); mb['r']=((s*(mb['close']-mb['open']))>0).astype(int); mb['a']=s*(mb['close']-mb['open'])/mb['atr_prev']
print(f"  brief on all its call days since May: right {int(mb.r.sum())}/{len(mb)} = {100*mb.r.mean():.1f}%, mean move {mb.a.mean():+.3f} ATR")
m.to_csv(f'{S}/scored_brief_vs_insight.csv', index=False)
