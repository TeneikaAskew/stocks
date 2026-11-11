"""Score stored insight directions and plans on 1-minute bars (day rule, earlier study's fill/stop/target rule).
import warnings; warnings.simplefilter("ignore")
Inputs in the scratchpad: out_Q02.csv (reports), out_Q10.csv (daily: open/close, prior ATR14, premarket high/low),
out_Q14.csv (high-importance events), bars/bars_{SPY,QQQ,IWM}.csv.gz (Eastern-time bars from prep_bars.py).
Bootstrap: resample session dates with replacement, 2000 draws, seed 7, 90% range. No database access here."""
import sys, json, numpy as np, pandas as pd
S = sys.argv[1]
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 40)
N_BOOT, SEED = 2000, 7

q2 = pd.read_csv(f'{S}/out_Q02.csv')
q2['as_of'] = pd.to_datetime(q2['as_of'], utc=True, format='ISO8601')
q2['session_et'] = pd.to_datetime(q2['session_et']).dt.date
# A backfill row's as_of is the date at midnight UTC (gcp/insight_pipeline_job + scripts/generate_historical_report.py),
# so its session is the UTC date, not the Eastern date (which lands on the evening before).
q2['session'] = np.where(q2['run_kind'] == 'backfill', q2['as_of'].dt.tz_convert('UTC').dt.date, q2['session_et'])
q2['t1'] = q2['targets'].apply(lambda s: (json.loads(s) or [None])[0] if isinstance(s, str) else None)

q10 = pd.read_csv(f'{S}/out_Q10.csv'); q10['date'] = pd.to_datetime(q10['date']).dt.date
q10 = q10.sort_values(['ticker', 'date']); q10['atr_prev'] = q10.groupby('ticker')['atr_14'].shift(1)
q10['close_prev'] = q10.groupby('ticker')['close'].shift(1); q10['close_fwd4'] = q10.groupby('ticker')['close'].shift(-4)
daily = q10.rename(columns={'date': 'session'})[['ticker', 'session', 'open', 'close', 'atr_prev', 'close_prev', 'close_fwd4', 'pre_high', 'pre_low']]

q14 = pd.read_csv(f'{S}/out_Q14.csv'); q14['event_date'] = pd.to_datetime(q14['event_date']).dt.date
event_days = set(q14[q14['event_name'].str.upper().str.contains('CPI|NFP|FOMC|EMPLOYMENT SITUATION|CONSUMER PRICE', regex=True)]['event_date'])

bars = {t: pd.read_csv(f'{S}/bars/bars_{t}.csv.gz', parse_dates=['et']) for t in ['SPY', 'QQQ', 'IWM']}
for t in bars:
    b = bars[t]; b['session'] = pd.to_datetime(b['session']).dt.date
    tm = b['et'].dt.time
    bars[t] = b[(tm >= pd.Timestamp('09:30').time()) & (tm < pd.Timestamp('16:00').time())].sort_values('et')
rth = {t: {s: g for s, g in bars[t].groupby('session')} for t in bars}
# premarket high and low from the bars themselves, 04:00 to 08:20 ET (the time the premarket refresh writes). The daily
# table's pre_high/pre_low sit 0.1 to 0.25% above the as-traded premarket extremes on about half the sessions (adjusted
# series or another feed), which breaks a symmetric construction, so they are not used for triggers.
pm = {}
for t in ['SPY', 'QQQ', 'IWM']:
    b = pd.read_csv(f'{S}/bars/bars_{t}.csv.gz', parse_dates=['et']); b['session'] = pd.to_datetime(b['session']).dt.date
    tm = b['et'].dt.time
    pm[t] = b[(tm >= pd.Timestamp('04:00').time()) & (tm < pd.Timestamp('08:20').time())].groupby('session').agg(pm_high=('high', 'max'), pm_low=('low', 'min'))

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

rows = []
for _, r in q2.iterrows():
    t, s = r['ticker'], r['session']
    if r['direction'] not in ('long', 'short') or s not in rth[t]:
        continue
    g = rth[t][s]
    if len(g) < 300:
        continue
    d = daily[(daily.ticker == t) & (daily.session == s)]
    d = d.iloc[0] if len(d) else None
    sign = 1 if r['direction'] == 'long' else -1
    rec = dict(id=r['id'], ticker=t, session=s, run_kind=r['run_kind'], run_time_et=r['run_time_et'], direction=r['direction'], sign=sign,
               conviction=r['conviction'], time_horizon=r['time_horizon'], regime=r['regime'], event_day=s in event_days,
               bar_open=g['open'].iloc[0], bar_close=g['close'].iloc[-1], bars=len(g),
               daily_open=d['open'] if d is not None else np.nan, daily_close=d['close'] if d is not None else np.nan,
               atr_prev=d['atr_prev'] if d is not None else np.nan, close_prev=d['close_prev'] if d is not None else np.nan,
               close_fwd4=d['close_fwd4'] if d is not None else np.nan,
               pre_high=pm[t].loc[s, 'pm_high'] if s in pm[t].index else np.nan, pre_low=pm[t].loc[s, 'pm_low'] if s in pm[t].index else np.nan)
    rec['move_atr'] = (rec['bar_close'] - rec['bar_open']) / rec['atr_prev']
    rec['model_atr'] = sign * rec['move_atr']; rec['right'] = int(rec['model_atr'] > 0)
    rec['right_5s'] = int(sign * (rec['close_fwd4'] - rec['bar_open']) > 0) if not np.isnan(rec['close_fwd4']) else np.nan
    # stored headline (neutral) plan
    e_lo, e_hi, stop, t1 = r['entry_low'], r['entry_high'], r['stop'], r['t1']
    has_plan = all(pd.notna(x) for x in (e_lo, e_hi, stop)) and e_hi >= e_lo and abs(((e_lo + e_hi) / 2) - stop) > 0 and r['regime'] != 'orb_only'
    rec['has_plan'] = has_plan
    if has_plan:
        trig = e_lo if sign > 0 else e_hi
        mid = (e_lo + e_hi) / 2
        rec.update(trigger=trig, buf_hi=e_hi - e_lo, stop_dist=abs(mid - stop), t1_dist=abs(t1 - mid) if pd.notna(t1) else np.nan,
                   trig_is_pm=(abs(trig - (rec['pre_high'] if sign > 0 else rec['pre_low'])) / trig < 0.0005) if pd.notna(rec['pre_high']) else np.nan,
                   trig_dist_atr=abs(trig - rec['bar_open']) / rec['atr_prev'])
        out = sim(g, sign, e_lo, e_hi, stop, t1 if pd.notna(t1) else None)
        rec['stored_fill'] = out is not None
        if out: rec.update(stored_fill_et=out[0], stored_outcome=out[3], stored_R=out[4])
        # symmetric construction on the premarket high and low with the stored distances
        if pd.notna(rec['pre_high']) and pd.notna(rec['pre_low']) and pd.notna(rec['t1_dist']):
            L = side_plan(1, rec['pre_high'], rec['buf_hi'], rec['stop_dist'], rec['t1_dist'])
            Sd = side_plan(-1, rec['pre_low'], rec['buf_hi'], rec['stop_dist'], rec['t1_dist'])
            oL, oS = sim(g, 1, *L), sim(g, -1, *Sd)
            rec.update(long_fill=oL is not None, short_fill=oS is not None, long_R=oL[4] if oL else np.nan, short_R=oS[4] if oS else np.nan,
                       long_out=oL[3] if oL else None, short_out=oS[3] if oS else None)
            rec['model_R'] = rec['long_R'] if sign > 0 else rec['short_R']; rec['model_out'] = rec['long_out'] if sign > 0 else rec['short_out']
            rec['opp_R'] = rec['short_R'] if sign > 0 else rec['long_R']; rec['opp_out'] = rec['short_out'] if sign > 0 else rec['long_out']
            tL, tS = (oL[0] if oL else None), (oS[0] if oS else None)
            if tL is not None and (tS is None or tL < tS): first = 1
            elif tS is not None and (tL is None or tS < tL): first = -1
            else: first = 0
            rec['first_side'] = first
            rec['first_R'] = rec['long_R'] if first > 0 else (rec['short_R'] if first < 0 else np.nan)
            rec['first_out'] = rec['long_out'] if first > 0 else (rec['short_out'] if first < 0 else None)
            rec['first_right'] = int(first * rec['move_atr'] > 0) if first else np.nan
            rec['first_atr'] = first * rec['move_atr'] if first else np.nan
    rows.append(rec)
df = pd.DataFrame(rows)
df.to_csv(f'{S}/scored_bars_all.csv', index=False)

def boot(frame, num_col, den_col=None, n=N_BOOT, seed=SEED):
    """90% range of sum(num)/sum(den) (den=None: plain sum) when session dates are resampled."""
    per = frame.groupby('session').agg(num=(num_col, 'sum'), den=(den_col, 'sum') if den_col else (num_col, 'size'))
    rng = np.random.default_rng(seed); idx = rng.integers(0, len(per), size=(n, len(per)))
    num = per['num'].to_numpy()[idx].sum(axis=1)
    if den_col is None:
        return np.percentile(num, 5), np.percentile(num, 95)
    den = per['den'].to_numpy()[idx].sum(axis=1); v = num / np.where(den == 0, np.nan, den)
    return np.nanpercentile(v, 5), np.nanpercentile(v, 95)

def trade_line(frame, rcol, ocol, label):
    f = frame[frame[rcol].notna()].copy(); f['one'] = 1; f['win'] = (f[rcol] > 0).astype(int)
    if not len(f):
        print(f'  {label}: no fills'); return
    tot, lo, hi = f[rcol].sum(), *boot(f, rcol)
    per, plo, phi = f[rcol].mean(), *boot(f, rcol, 'one')
    oc = f[ocol].value_counts().to_dict()
    print(f"  {label}: fills {len(f)} ({100*len(f)/len(frame):.0f}% of {len(frame)}), win {100*f.win.mean():.1f}%, T1/stop/close {oc.get('t1',0)}/{oc.get('stop',0)}/{oc.get('close',0)}, total {tot:+.1f}R (range {lo:+.1f} to {hi:+.1f}), per fill {per:+.3f}R (range {plo:+.3f} to {phi:+.3f})")

def diff_line(frame, a, b, label):
    f = frame.copy(); f['d'] = f[a].fillna(0) - f[b].fillna(0)
    lo, hi = boot(f, 'd'); print(f"  {label}: {f.d.sum():+.1f}R (range {lo:+.1f} to {hi:+.1f})")

def dir_line(frame, rcol, acol, label):
    f = frame[frame[acol].notna()].copy(); f['one'] = 1
    if not len(f): print(f'  {label}: n=0'); return
    hit, lo, hi = f[rcol].mean(), *boot(f, rcol, 'one'); m, mlo, mhi = f[acol].mean(), *boot(f, acol, 'one')
    print(f"  {label}: n={len(f)} right from the open {int(f[rcol].sum())}/{len(f)} = {100*hit:.1f}% (range {100*lo:.1f}-{100*hi:.1f}%), mean move {m:+.3f} ATR/day (range {mlo:+.3f} to {mhi:+.3f})")

def report(frame, title):
    print(f'\n===== {title}: {len(frame)} ticker-days, {frame.session.nunique()} sessions, long {int((frame.sign>0).sum())} short {int((frame.sign<0).sum())} =====')
    print('  direction from the 09:30 open (1-minute bars):')
    dir_line(frame, 'right', 'model_atr', '  model')
    f2 = frame.assign(opp_right=1 - frame['right'], opp_atr=-frame['model_atr']); dir_line(f2, 'opp_right', 'opp_atr', '  opposite')
    dir_line(frame, 'first_right', 'first_atr', '  first side to trigger (premarket high vs low)')
    f3 = frame.assign(al=(frame['move_atr'] > 0).astype(int)); dir_line(f3, 'al', 'move_atr', '  always long')
    r5 = frame[frame['right_5s'].notna()]
    if len(r5): print(f"    5-session hold from the open (daily closes): right {int(r5.right_5s.sum())}/{len(r5)} = {100*r5.right_5s.mean():.1f}%")
    print('  neutral plan, day rule, stored plan as published:'); trade_line(frame[frame.has_plan], 'stored_R', 'stored_outcome', 'stored plan (model side)')
    print('  neutral plan, day rule, both sides built on the premarket high/low with the stored distances:')
    fs = frame[frame['long_R'].notna() | frame['short_R'].notna() | frame['long_fill'].notna()]
    trade_line(fs, 'model_R', 'model_out', "model's side"); trade_line(fs, 'opp_R', 'opp_out', 'opposite side'); trade_line(fs, 'first_R', 'first_out', 'first side to trigger')
    both = pd.concat([fs.assign(R=fs['long_R'], O=fs['long_out']), fs.assign(R=fs['short_R'], O=fs['short_out'])]); trade_line(both, 'R', 'O', 'both sides every day')
    diff_line(fs, 'model_R', 'opp_R', 'model minus opposite'); diff_line(fs, 'model_R', 'first_R', 'model minus first-to-trigger')
    print(f"    ties (both sides fill in the same bar): {int((fs.first_side==0).sum())}; stored trigger equals the premarket high/low: {int(frame.trig_is_pm.eq(True).sum())} of {int(frame.has_plan.sum())} plans")

live = df[(df.run_kind == 'live') & (df.run_time_et < '09:30')].sort_values('run_time_et').groupby(['ticker', 'session']).tail(1)
print('bars vs daily cross-check (live): max |open diff| %.3f%%, max |close diff| %.3f%%, sessions with >0.1%% open diff: %d, close: %d' % (
    (100 * (live.bar_open - live.daily_open).abs() / live.daily_open).max(), (100 * (live.bar_close - live.daily_close).abs() / live.daily_close).max(),
    int(((live.bar_open - live.daily_open).abs() / live.daily_open > 0.001).sum()), int(((live.bar_close - live.daily_close).abs() / live.daily_close > 0.001).sum())))
report(live, 'LIVE canonical (latest pre-09:30 run)')
report(live[live.session >= pd.Timestamp('2026-05-01').date()], 'LIVE, 2026-05-01 onward (primary window)')
for t in ['SPY', 'QQQ', 'IWM']: report(live[live.ticker == t], f'LIVE {t}')
report(live[live.conviction == 'medium'], 'LIVE medium conviction'); report(live[live.conviction == 'low'], 'LIVE low conviction')
report(live[live.event_day], 'LIVE on CPI/jobs/FOMC days'); report(live[~live.event_day], 'LIVE on other days')
bf = df[df.run_kind == 'backfill']; report(bf, 'BACKFILL rows (written after the fact; session = UTC date of as_of)')
live.to_csv(f'{S}/scored_bars_live.csv', index=False)
lm = live.copy(); lm['month'] = pd.to_datetime(lm['session']).dt.to_period('M')
print('\n===== LIVE by month: ticker-days, direction right %, mean move (ATR), stored-plan fills and total R, constructed model side / opposite / first-to-trigger total R =====')
print(lm.groupby('month').agg(n=('right', 'size'), right_pct=('right', lambda s: round(100 * s.mean(), 1)), move_atr=('model_atr', lambda s: round(s.mean(), 3)),
      stored_fills=('stored_R', 'count'), stored_R=('stored_R', 'sum'), model_R=('model_R', 'sum'), opp_R=('opp_R', 'sum'), first_R=('first_R', 'sum')).round(1).to_string())
print('\nstored plan: trigger already passed at the open (price beyond it at 09:30): %d of %d plans; median trigger distance from the open %.2f ATR' % (
    int((live.trig_dist_atr.notna() & ((live.sign * (live.trigger - live.bar_open)) < 0)).sum()), int(live.has_plan.sum()), live.trig_dist_atr.median()))
