"""Old vs fixed pct_profitable for the production voter, per ticker, week by week.
  python3 -I code/pct_profitable.py     -> pct_profitable_weekly.csv , pct_profitable_summary.csv
Needs work/{T}_voter_signals.parquet from code/voter_run.py (the production code's own signals, unchanged).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from proposed_pct_profitable import realized_outcomes

W, Sm = [], []
for T in TICKERS:
    bars, _ = load_bars(T)
    D = daily_bars(T, bars)
    tr = pd.concat([D['H'] - D['L'], (D['H'] - D['C'].shift()).abs(), (D['L'] - D['C'].shift()).abs()], axis=1).max(axis=1)
    atr_prev = wilder(tr, 14).shift(1)
    t = bars['Time']; mod = (t.dt.hour * 60 + t.dt.minute).values
    dnorm = t.dt.normalize(); day_id = dnorm.factorize()[0]
    atr_d = dnorm.map(atr_prev).ffill().values
    O, H, L, C = (bars[c].values for c in ['Open', 'High', 'Low', 'Last'])
    sig = pd.read_parquet(f'{WORK}/{T}_voter_signals.parquet')
    pos = pd.Series(np.arange(len(bars)), index=t.values)
    si = pos.reindex(pd.to_datetime(sig['entry_time']).values).values.astype(int)
    dr = np.where(sig['trade_type'] == 'call', 1, -1)
    week = pd.to_datetime(sig['entry_time']).dt.to_period('W-SUN').dt.start_time.dt.date.values
    df = pd.DataFrame({'ticker': T, 'week': week, 'old': (sig['return_pct'].values > 0).astype(float)})
    rth = (mod[si] >= 570) & (mod[si] <= 934)
    df['rth'] = rth
    # fix ladder: each step adds one fix
    df['f1_rth_only_best_of_20'] = np.where(rth, df['old'], np.nan)
    ok, ret, _ = realized_outcomes(mod, day_id, O, H, L, C, atr_d, si, dr, 'time', rth_only=True, next_bar_entry=False, cost=0)
    df['f2_rth_close_after_20'] = np.where(ok, ret > 0, np.nan)
    ok, ret, _ = realized_outcomes(mod, day_id, O, H, L, C, atr_d, si, dr, 'time')
    df['fixedA_time_exit'] = np.where(ok, ret > 0, np.nan); df['fixedA_ret_bps'] = np.where(ok, ret * 100, np.nan)
    ok, ret, r = realized_outcomes(mod, day_id, O, H, L, C, atr_d, si, dr, 'bracket')
    df['fixedB_bracket'] = np.where(ok, r > 0, np.nan); df['fixedB_R'] = np.where(ok, r, np.nan)
    # ext-hours as written but with a real exit (shows the hours effect alone)
    ok, ret, _ = realized_outcomes(mod, day_id, O, H, L, C, atr_d, si, dr, 'time', rth_only=False)
    df['allhours_time_exit'] = np.where(ok, ret > 0, np.nan)
    # one position at a time (the voter fires on back-to-back bars; overlapping signals are not separate trades)
    okA = df['fixedA_time_exit'].notna().values; keep = np.zeros(len(df), bool); nxt = -1
    for j in np.where(okA)[0]:
        if si[j] >= nxt: keep[j] = True; nxt = si[j] + 21
    df['fixedA_one_at_a_time'] = np.where(keep, df['fixedA_time_exit'], np.nan)
    df['window'] = window_of(pd.to_datetime(sig['entry_time']).dt.normalize())
    g = df.groupby(['ticker', 'week'])
    w = pd.DataFrame({
        'signals_all_hours': g.size(), 'old_pct_profitable': g['old'].mean(),
        'signals_regular_hours': g['fixedA_time_exit'].count(), 'step1_regular_hours_only': g['f1_rth_only_best_of_20'].mean(),
        'step2_close_after_20min': g['f2_rth_close_after_20'].mean(),
        'new_pct_profitable_A_time_exit': g['fixedA_time_exit'].mean(), 'avg_net_bps_A': g['fixedA_ret_bps'].mean(),
        'new_pct_profitable_B_bracket': g['fixedB_bracket'].mean(), 'avg_net_R_B': g['fixedB_R'].mean(),
        'trades_one_at_a_time': g['fixedA_one_at_a_time'].count(), 'new_A_one_at_a_time': g['fixedA_one_at_a_time'].mean(),
        'all_hours_time_exit': g['allhours_time_exit'].mean()}).reset_index()
    W.append(w)
    for wn, gg in [('all', df)] + [(k, v) for k, v in df.groupby('window') if k != 'other']:
        Sm.append(dict(ticker=T, window=wn, signals_all_hours=len(gg), share_outside_regular_hours=1 - gg['rth'].mean(),
                       old_pct_profitable=gg['old'].mean(), step1_regular_hours_only=gg['f1_rth_only_best_of_20'].mean(),
                       step2_close_after_20min=gg['f2_rth_close_after_20'].mean(),
                       new_A_time_exit=gg['fixedA_time_exit'].mean(), avg_net_bps_A=gg['fixedA_ret_bps'].mean(),
                       new_B_bracket=gg['fixedB_bracket'].mean(), avg_net_R_B=gg['fixedB_R'].mean(),
                       new_A_one_at_a_time=gg['fixedA_one_at_a_time'].mean(), trades_one_at_a_time=int(gg['fixedA_one_at_a_time'].count()),
                       all_hours_time_exit=gg['allhours_time_exit'].mean(),
                       weeks=gg['week'].nunique(),
                       weekly_new_A_min=gg.groupby('week')['fixedA_time_exit'].mean().min(), weekly_new_A_max=gg.groupby('week')['fixedA_time_exit'].mean().max(),
                       weekly_old_min=gg.groupby('week')['old'].mean().min(), weekly_old_max=gg.groupby('week')['old'].mean().max()))
    print(T, 'signals', len(df), flush=True)
Wk = pd.concat(W, ignore_index=True); num = Wk.select_dtypes(float).columns; Wk[num] = Wk[num].round(4)
Wk.to_csv(f'{ROOT}/pct_profitable_weekly.csv', index=False)
S = pd.DataFrame(Sm); num = S.select_dtypes(float).columns; S[num] = S[num].round(4); S.to_csv(f'{ROOT}/pct_profitable_summary.csv', index=False)
print(S.T.to_string())
