"""Tables with 90% day-bootstrap ranges from sides.csv and taps.csv. Writes tables.md and summary.json.
Usage: python3 -I summarize.py"""
import json, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.dirname(HERE)
S = pd.read_csv(f'{OUT}/sides.csv', low_memory=False); TP = pd.read_csv(f'{OUT}/taps.csv', low_memory=False)
S['report'] = S.report.fillna(''); TP['report'] = TP.report.fillna('')
RNG = np.random.default_rng(11); NB = 2000
ALLDAYS = np.array(sorted(set(S.day))); DIX = {d: i for i, d in enumerate(ALLDAYS)}
DRAW = RNG.integers(0, len(ALLDAYS), size=(NB, len(ALLDAYS)))
out_md = []; summ = {}

def _agg(df, col):
    """per-day sum and count of a column (NaN dropped) on the global day index."""
    x = df[['day', col]].dropna()
    v = x[col].astype(float).values; i = x.day.map(DIX).values
    s = np.bincount(i, weights=v, minlength=len(ALLDAYS)); n = np.bincount(i, minlength=len(ALLDAYS))
    return s, n

def _boot(s, n):
    w = np.zeros((NB, len(ALLDAYS)))
    for b in range(NB):
        w[b] = np.bincount(DRAW[b], minlength=len(ALLDAYS))
    num = w @ s; den = w @ n
    return np.where(den > 0, num / np.maximum(den, 1), np.nan)
_W = None
def boot(s, n):
    global _W
    if _W is None:
        _W = np.stack([np.bincount(DRAW[b], minlength=len(ALLDAYS)) for b in range(NB)]).astype(float)
    num = _W @ s; den = _W @ n
    return np.where(den > 0, num / np.maximum(den, 1), np.nan)

def rate(df, col, pct=True):
    s, n = _agg(df, col); N = int(n.sum())
    if N == 0:
        return dict(n=0, v=None, lo=None, hi=None)
    bs = boot(s, n); m = 100 if pct else 1
    return dict(n=N, v=round(m * s.sum() / N, 1 if pct else 3), lo=round(m * np.nanpercentile(bs, 5), 1 if pct else 3),
                hi=round(m * np.nanpercentile(bs, 95), 1 if pct else 3))

def diff(dfa, dfb, col, pct=True):
    sa, na = _agg(dfa, col); sb, nb = _agg(dfb, col)
    if na.sum() == 0 or nb.sum() == 0:
        return dict(v=None, lo=None, hi=None)
    bs = boot(sa, na) - boot(sb, nb); m = 100 if pct else 1
    return dict(v=round(m * (sa.sum() / na.sum() - sb.sum() / nb.sum()), 1 if pct else 3),
                lo=round(m * np.nanpercentile(bs, 5), 1 if pct else 3), hi=round(m * np.nanpercentile(bs, 95), 1 if pct else 3))

def f(r, pct=True):
    if r.get('v') is None:
        return 'n/a'
    u = '%' if pct else ''
    s = f"{r['v']}{u} [{r['lo']}, {r['hi']}]"
    return s + (f" n={r['n']}" if 'n' in r else '')

def fd(r, pct=True):
    if r.get('v') is None:
        return 'n/a'
    star = '' if (r['lo'] <= 0 <= r['hi']) else ' *'
    return f"{r['v']:+}{' pts' if pct else ''} [{r['lo']:+}, {r['hi']:+}]{star}"

def table(title, header, rows, key=None):
    out_md.append(f'\n### {title}\n'); out_md.append('| ' + ' | '.join(header) + ' |'); out_md.append('|' + '---|' * len(header))
    for r in rows:
        out_md.append('| ' + ' | '.join(str(x) for x in r) + ' |')
    if key:
        summ[key] = dict(header=header, rows=rows)

WIN = [('holdout', 'Holdout (Mar 2025 to Apr 2026)'), ('primary', 'Primary (May to Nov 10 2026)'), ('all', 'All')]
def win(df, w):
    return df if w == 'all' else df[df.window == w]

S = S[S.has_trigger == True].copy()
for c in ['touch', 'hold1', 'hold5', 'hold15', 'hold30', 'strict5', 'close_beyond_trigger']:
    S[c] = S[c].astype(float)
# unconditional "delivered" measures per ticker day side (0 when no hold)
def uncond(name):
    hit = S[f'{name}_before_stop'].astype('float')
    return np.where(S[f't1'].notna() if name.startswith('t') and name == 't1' else True, (S.hold5 == 1) & (hit == 1), np.nan).astype(float)
for name in ['t1', 't2', 't3', 'a0.25', 'a0.5', 'a1.0']:
    exists = S[name].notna() if name in ('t1', 't2', 't3') else pd.Series(True, index=S.index)
    S[f'deliv_{name}'] = np.where(exists, ((S.hold5 == 1) & (S[f'{name}_before_stop'] == True)).astype(float), np.nan)
    S[f'reach_{name}'] = np.where(exists, ((S.hold5 == 1) & (S[f'{name}_hit'] == True)).astype(float), np.nan)
    for k in ('hit', 'before_stop', 'in_hold'):
        S[f'{name}_{k}'] = S[f'{name}_{k}'].map({True: 1.0, False: 0.0, 'True': 1.0, 'False': 0.0})
S['stop_after_hold'] = S.stop_after_hold.map({True: 1.0, False: 0.0, 'True': 1.0, 'False': 0.0})
S['pre10'] = S.hold5_pre10.map({True: 1.0, False: 0.0, 'True': 1.0, 'False': 0.0})
S['aligned'] = S.ftfc_aligned.map({True: 1.0, False: 0.0, 'True': 1.0, 'False': 0.0})
S['is_report'] = (S.report != '').astype(int)
S['rep0830'] = ((S.report != '') & (S.report_time == '08:30')).astype(int)

S['start_ok'] = (S.hold5_t.fillna('99:99') <= '13:55')
for nm, cap in (('a0.5', 120), ('a0.25', 60)):
    S[f'{nm}_within{cap}'] = np.where(S.start_ok & (S.hold5 == 1), ((S[f'{nm}_hit'] == 1) & (S[f'{nm}_mins'] <= cap)).astype(float), np.nan)
S['fake'] = np.where(S.touch == 1, 1 - S.hold5, np.nan)          # touched the trigger but never held 5 minutes
CALLED = S[S.role == 'called']; OPP = S[S.role == 'opposite']; NOC = S[S.role == 'no_call']

# ---- A: trigger cross and hold ----
def tabA(tk=None, key='A'):
    rows = []
    for w, wl in WIN:
        a = win(CALLED, w); b = win(OPP, w)
        if tk: a = a[a.ticker == tk]; b = b[b.ticker == tk]
        for col, lab in [('touch', 'Touched the trigger'), ('hold1', 'Closed 1 minute beyond'), ('hold5', 'Held 5 minutes'),
                         ('hold15', 'Held 15 minutes'), ('hold30', 'Held 30 minutes'), ('close_beyond_trigger', 'Day closed beyond trigger'),
                         ('fake', 'Of touches: never held 5 minutes (fakeout)')]:
            rows.append([wl, lab, f(rate(a, col)), f(rate(b, col)), fd(diff(a, b, col))])
    table(f"A. Crossed the trigger and held ({tk or 'SPY+QQQ+IWM'}): share of call days",
          ['Window', 'Measure', 'Called side', 'Opposite side', 'Called minus opposite'], rows, key + (tk or ''))
tabA()
for tk in ('SPY', 'QQQ', 'IWM'):
    tabA(tk)

# no call days
rows = []
for w, wl in WIN:
    x = win(NOC, w)
    for col, lab in [('touch', 'Touched'), ('hold5', 'Held 5 minutes'), ('hold30', 'Held 30 minutes')]:
        rows.append([wl, lab, f(rate(x[x.side == 'calls'], col)), f(rate(x[x.side == 'puts'], col))])
table('A2. Days with no call: the same triggers', ['Window', 'Measure', 'Calls trigger', 'Puts trigger'], rows, 'A2')

# ---- B: targets after the 5 minute hold ----
def tabB(tk=None):
    rows = []
    for w, wl in WIN:
        a = win(CALLED, w); b = win(OPP, w)
        if tk: a = a[a.ticker == tk]; b = b[b.ticker == tk]
        ah = a[a.hold5 == 1].copy(); bh = b[b.hold5 == 1].copy()
        for name, lab in [('t1', 'T1'), ('t2', 'T2'), ('t3', 'T3'), ('t4', 'next rung after T3'), ('a0.25', 'trigger + 0.25 ATR'),
                          ('a0.5', 'trigger + 0.5 ATR'), ('a1.0', 'trigger + 1.0 ATR')]:
            med = ah.loc[ah[f'{name}_hit'] == 1, f'{name}_mins'].median()
            rows.append([wl, lab, f(rate(ah, f'{name}_hit')), f(rate(ah, f'{name}_before_stop')),
                         f(rate(ah[ah[f'{name}_hit'] == 1], f'{name}_in_hold')), '' if pd.isna(med) else int(med),
                         f(rate(bh, f'{name}_hit')), f(rate(bh, f'{name}_before_stop')),
                         fd(diff(ah, bh, f'{name}_before_stop'))])
        rows.append([wl, 'stop touched after the hold', f(rate(ah, 'stop_after_hold')), '', '', '', f(rate(bh, 'stop_after_hold')), '', fd(diff(ah, bh, 'stop_after_hold'))])
    table(f"B. After a 5 minute hold: targets reached ({tk or 'SPY+QQQ+IWM'}); base = sides that held 5 minutes",
          ['Window', 'Target', 'Called: reached', 'Called: reached before stop', 'Of those reached: already inside the 5 min hold',
           'Median minutes from hold start', 'Opposite: reached', 'Opposite: before stop', 'Before stop, called minus opposite'], rows, 'B' + (tk or ''))
tabB()

# ---- C: unconditional: share of all call days where the side held 5 min AND reached target before stop ----
def tabC(tk=None):
    rows = []
    for w, wl in WIN:
        a = win(CALLED, w); b = win(OPP, w)
        if tk: a = a[a.ticker == tk]; b = b[b.ticker == tk]
        for name, lab in [('t1', 'T1'), ('t2', 'T2'), ('t3', 'T3'), ('a0.25', 'trigger + 0.25 ATR'), ('a0.5', 'trigger + 0.5 ATR'), ('a1.0', 'trigger + 1.0 ATR')]:
            rows.append([wl, lab, f(rate(a, f'deliv_{name}')), f(rate(b, f'deliv_{name}')), fd(diff(a, b, f'deliv_{name}'))])
    table(f"C. Share of call days where the side held 5 minutes and then reached the target before its stop ({tk or 'SPY+QQQ+IWM'})",
          ['Window', 'Target', 'Called side', 'Opposite side', 'Called minus opposite'], rows, 'C' + (tk or ''))
tabC()
for tk in ('SPY', 'QQQ', 'IWM'):
    tabC(tk)

# which side delivered, per call day (0.5 ATR yardstick and T1)
rows = []
m = CALLED.merge(OPP, on=['day', 'ticker'], suffixes=('_c', '_o'))
for w, wl in WIN:
    x = win(m.rename(columns={'window_c': 'window'}), w)
    for name in ('t1', 'a0.5'):
        y = x.dropna(subset=[f'deliv_{name}_c', f'deliv_{name}_o'])
        c_ = y[f'deliv_{name}_c'] == 1; o_ = y[f'deliv_{name}_o'] == 1
        n = len(y)
        rows.append([wl, name, n, f'{100*(c_ & ~o_).mean():.1f}%', f'{100*(~c_ & o_).mean():.1f}%', f'{100*(c_ & o_).mean():.1f}%', f'{100*(~c_ & ~o_).mean():.1f}%'])
table('C2. Which side delivered (held 5 min, then target before stop), per call day', ['Window', 'Target', 'n', 'Only the called side', 'Only the opposite side', 'Both', 'Neither'], rows, 'C2')

# ---- D: trades in R ----
def rrow(df, col):
    x = df[col].dropna()
    r = rate(df, col, pct=False)
    return [len(x), f'{100*(x > 0).mean():.0f}%' if len(x) else '', round(x.sum(), 2) if len(x) else '', f(r, pct=False).split(' n=')[0]]
rows = []
for w, wl in WIN:
    for role, df in (('called', CALLED), ('opposite', OPP)):
        x = win(df, w)
        for col, lab in [('R_touch_t1', 'Enter on first touch, exit T1 (old rule)'), ('R_hold_t1', 'Enter after 5 min hold, exit T1'),
                         ('R_hold_t2', 'Enter after 5 min hold, exit T2'), ('R_hold_t3', 'Enter after 5 min hold, exit T3'),
                         ('R_hold_to_close', 'Enter after 5 min hold, no target, exit stop or close'),
                         ('R_hold_atr', 'Enter after 5 min hold, stop 0.25 ATR back through trigger, target trigger + 0.5 ATR')]:
            rows.append([wl, role, lab] + rrow(x, col))
table('D. Trade view (R = profit in units of the risk from entry to stop)', ['Window', 'Side', 'Rule', 'Trades', 'Win %', 'Total R', 'Avg R [90% range]'], rows, 'D')

# ---- E: before / after 10:00 ----
rows = []
for w, wl in WIN:
    for role, df in (('called', CALLED), ('opposite', OPP), ('both sides, all days', S)):
        x = win(df, w); x = x[x.hold5 == 1]
        a = x[x.pre10 == 1]; b = x[x.pre10 == 0]
        for col, lab, pct in [('t1_before_stop', 'T1 before stop', True), ('a0.5_before_stop', 'trigger + 0.5 ATR before stop', True),
                              ('a0.5_hit', 'trigger + 0.5 ATR reached', True), ('a0.5_within120', 'trigger + 0.5 ATR within 2 hours of the hold (holds starting by 13:55)', True),
                              ('a0.25_within60', 'trigger + 0.25 ATR within 1 hour of the hold (holds starting by 13:55)', True), ('stop_after_hold', 'stop touched', True),
                              ('R_hold_t2', 'avg R, exit T2', False), ('R_hold_to_close', 'avg R, hold to close', False), ('R_hold_atr', 'avg R, ATR sized', False)]:
            rows.append([wl, role, lab, f(rate(a, col, pct), pct), f(rate(b, col, pct), pct), fd(diff(a, b, col, pct), pct)])
table('E. 5 minute holds that started before 10:00 vs at or after 10:00', ['Window', 'Side', 'Measure', 'Before 10:00', '10:00 or later', 'Before minus after'], rows, 'E')
# time distribution
x = CALLED[CALLED.hold5 == 1]
tt = pd.to_datetime(x.hold5_t, format='%H:%M')
bins = [('09:30 (open already through)', (x.hold5_t == '09:30')), ('09:31 to 09:59', (x.hold5_t > '09:30') & (x.hold5_t < '10:00')),
        ('10:00 to 10:59', (x.hold5_t >= '10:00') & (x.hold5_t < '11:00')), ('11:00 to 12:59', (x.hold5_t >= '11:00') & (x.hold5_t < '13:00')),
        ('13:00 to 15:55', (x.hold5_t >= '13:00'))]
table('E2. When the called side 5 minute hold started', ['Start', 'Holds', 'Share'], [[l, int(mk.sum()), f'{100*mk.mean():.0f}%'] for l, mk in bins], 'E2')

rows = []
for w, wl in WIN:
    x = win(S, w); x = x[x.hold5 == 1]
    for lab, mk in [('09:30 to 09:59', x.hold5_t < '10:00'), ('10:00 to 10:59', (x.hold5_t >= '10:00') & (x.hold5_t < '11:00')),
                    ('11:00 to 12:59', (x.hold5_t >= '11:00') & (x.hold5_t < '13:00')), ('13:00 to 13:55', (x.hold5_t >= '13:00') & (x.hold5_t <= '13:55'))]:
        y = x[mk]
        rows.append([wl, lab, len(y), f(rate(y, 'a0.25_within60')).split(' n=')[0], f(rate(y, 'a0.5_within120')).split(' n=')[0],
                     f(rate(y, 'stop_after_hold')).split(' n=')[0], f(rate(y, 'R_hold_atr', False), False).split(' n=')[0],
                     f(rate(y, 'R_hold_to_close', False), False).split(' n=')[0]])
table('E3. By the hour the 5 minute hold started (both sides, all days, same time allowance for each)',
      ['Window', 'Hold started', 'Holds', '+0.25 ATR within 1 hour', '+0.5 ATR within 2 hours', 'Stop touched later', 'Avg R, ATR sized', 'Avg R, hold to close'], rows, 'E3')

# ---- F: continuity at the hold ----
rows = []
for w, wl in WIN:
    for role, df in (('called', CALLED), ('opposite', OPP), ('both sides, all days', S)):
        x = win(df, w); x = x[x.hold5 == 1]
        a = x[x.aligned == 1]; b = x[x.aligned == 0]
        for col, lab, pct in [('t1_before_stop', 'T1 before stop', True), ('a0.5_before_stop', 'trigger + 0.5 ATR before stop', True),
                              ('stop_after_hold', 'stop touched', True), ('R_hold_to_close', 'avg R, hold to close', False), ('R_hold_atr', 'avg R, ATR sized', False)]:
            rows.append([wl, role, lab, f(rate(a, col, pct), pct), f(rate(b, col, pct), pct), fd(diff(a, b, col, pct), pct)])
table('F. Timeframe continuity when the 5 minute hold confirmed (price vs day, week, month, quarter opens all agreeing with the side)',
      ['Window', 'Side', 'Measure', 'All four agree', 'Not all agree', 'Agree minus not'], rows, 'F')

# ---- G: Strat level taps ----
TP['tapped'] = (TP.state == 'tapped').astype(float); TP['open_beyond'] = (TP.state == 'open_beyond').astype(float)
T2 = TP[TP.state == 'tapped'].copy()
for k in ('0.25', '0.5'):
    T2[f'follow{k}'] = (T2[f'res{k}'] == 'follow').astype(float); T2[f'fail{k}'] = (T2[f'res{k}'] == 'fail').astype(float)
for k in ('0.25', '0.5'):
    T2[f'decided{k}'] = np.where(T2[f'res{k}'] == 'neither', np.nan, (T2[f'res{k}'] == 'follow').astype(float))
for c in ('held5_within10', 'close_beyond', 'pre10', 'ftfc_aligned', 'ftfc_DW'):
    T2[c] = T2[c].map({True: 1.0, False: 0.0, 'True': 1.0, 'False': 0.0})
LEV = [('PDH', 'Prior day high'), ('PDL', 'Prior day low'), ('PWH', 'Prior week high'), ('PWL', 'Prior week low'),
       ('E12H', '12HR overnight candle high'), ('E12L', '12HR overnight candle low'), ('E12M', '12HR overnight candle 50%'),
       ('D12H', '12HR prior day candle high'), ('D12L', '12HR prior day candle low'), ('D12M', '12HR prior day candle 50%')]
for w, wl in WIN:
    rows = []
    for lv, lab in LEV + [('ALL', 'All levels')]:
        a = win(TP, w); b = win(T2, w)
        if lv != 'ALL': a = a[a.level == lv]; b = b[b.level == lv]
        rows.append([lab, len(a), f(rate(a, 'open_beyond')).split(' n=')[0], f(rate(a, 'tapped')).split(' n=')[0],
                     f(rate(b, 'held5_within10')).split(' n=')[0], f(rate(b, 'follow0.25')).split(' n=')[0], f(rate(b, 'fail0.25')).split(' n=')[0],
                     f(rate(b, 'follow0.5')).split(' n=')[0], f(rate(b, 'fail0.5')).split(' n=')[0], f(rate(b, 'close_beyond')).split(' n=')[0],
                     f(rate(b, 'ftfc_aligned')).split(' n=')[0], f(rate(b, 'pre10')).split(' n=')[0]])
    table(f'G. Strat level taps in the regular session, {wl}',
          ['Level', 'Ticker days', 'Open already beyond', 'Tapped in session', 'Of taps: held 5 min beyond (starting within 10 min)',
           'Ran 0.25 ATR beyond before 0.25 back', 'Came back 0.25 first', 'Ran 0.5 ATR before 0.5 back', 'Came back 0.5 first', 'Day closed beyond', 'Continuity agreed at the tap', 'Tap was before 10:00'], rows, 'G_' + w)

def split_tab(title, col, la, lb, key):
    rows = []
    for w, wl in WIN:
        for grp, levs in [('All levels', None), ('Prior day high/low', ['PDH', 'PDL']), ('Prior week high/low', ['PWH', 'PWL']),
                          ('12HR overnight high/low', ['E12H', 'E12L']), ('12HR overnight 50%', ['E12M']), ('12HR prior day high/low', ['D12H', 'D12L']),
                          ('12HR prior day 50%', ['D12M'])]:
            x = win(T2, w)
            if levs: x = x[x.level.isin(levs)]
            a = x[x[col] == 1]; b = x[x[col] == 0]
            for m, ml in [('follow0.25', 'ran 0.25 ATR first'), ('fail0.25', 'came back 0.25 ATR first'), ('decided0.25', 'ran first, of those that went 0.25 ATR either way'),
                          ('decided0.5', 'ran first, of those that went 0.5 ATR either way'), ('held5_within10', 'held 5 min'), ('close_beyond', 'closed beyond')]:
                rows.append([wl, grp, ml, f(rate(a, m)), f(rate(b, m)), fd(diff(a, b, m))])
    table(title, ['Window', 'Levels', 'Outcome', la, lb, f'{la} minus {lb}'], rows, key)
split_tab('G2. Taps with full timeframe continuity (day, week, month, quarter opens all on the tap side) vs not', 'ftfc_aligned', 'Continuity agrees', 'Does not', 'G2')
split_tab('G3. Taps before 10:00 vs at or after 10:00', 'pre10', 'Before 10:00', '10:00 or later', 'G3')
# post-10 taps, split by continuity
rows = []
for w, wl in WIN:
    x = win(T2, w)
    for lab, mk in [('Before 10:00, continuity agrees', (x.pre10 == 1) & (x.ftfc_aligned == 1)), ('Before 10:00, not', (x.pre10 == 1) & (x.ftfc_aligned == 0)),
                    ('10:00 or later, continuity agrees', (x.pre10 == 0) & (x.ftfc_aligned == 1)), ('10:00 or later, not', (x.pre10 == 0) & (x.ftfc_aligned == 0))]:
        y = x[mk]
        rows.append([wl, lab, f(rate(y, 'follow0.25')), f(rate(y, 'decided0.25')), f(rate(y, 'decided0.5')), f(rate(y, 'close_beyond'))])
table('G4. Taps by time and continuity together (all levels)', ['Window', 'Group', 'Ran 0.25 ATR first', 'Ran first of decided (0.25)', 'Ran first of decided (0.5)', 'Closed beyond'], rows, 'G4')

# ---- H: report days ----
rows = []
for w, wl in WIN:
    for role, df in (('called', CALLED), ('opposite', OPP)):
        x = win(df, w)
        for lab, a in [('08:30 release days (CPI, jobs, PCE)', x[x.rep0830 == 1]), ('FOMC and 10:00 release days', x[(x.is_report == 1) & (x.rep0830 == 0)]),
                       ('Other days', x[x.is_report == 0])]:
            rows.append([wl, role, lab, a.day.nunique(), f(rate(a, 'touch')), f(rate(a, 'hold5')), f(rate(a, 'deliv_t1')), f(rate(a, 'deliv_a0.5')),
                         f(rate(a, 'R_hold_to_close', False), False), f(rate(a, 'R_touch_t1', False), False)])
table('H. Report days vs other days', ['Window', 'Side', 'Days', 'Sessions', 'Touched trigger', 'Held 5 min', 'Held + T1 before stop',
                                       'Held + 0.5 ATR before stop', 'Avg R hold to close', 'Avg R touch to T1'], rows, 'H')
rows = []
for w, wl in WIN:
    x = win(CALLED, w); o = win(OPP, w)
    for lab, mk, mo in [('08:30 release days', x.rep0830 == 1, o.rep0830 == 1), ('Other days', x.is_report == 0, o.is_report == 0)]:
        for m, ml in [('hold5', 'Held 5 min'), ('deliv_t1', 'Held + T1 before stop'), ('deliv_a0.5', 'Held + 0.5 ATR before stop')]:
            rows.append([wl, lab, ml, fd(diff(x[mk], o[mo], m))])
    for m, ml in [('hold5', 'Held 5 min'), ('deliv_a0.5', 'Held + 0.5 ATR before stop')]:
        rows.append([wl, 'called side: release days minus other days', ml, fd(diff(x[x.rep0830 == 1], x[x.is_report == 0], m))])
table('H2. Report days: called minus opposite', ['Window', 'Days', 'Measure', 'Difference'], rows, 'H2')
# taps on report days
rows = []
T2['rep0830'] = ((T2.report != '') & (T2.report_time == '08:30')).astype(int)
for w, wl in WIN:
    x = win(T2, w)
    a = x[x.rep0830 == 1]; b = x[x.report == '']
    for m, ml in [('follow0.25', 'ran 0.25 ATR first'), ('follow0.5', 'ran 0.5 ATR first'), ('close_beyond', 'closed beyond')]:
        rows.append([wl, ml, f(rate(a, m)), f(rate(b, m)), fd(diff(a, b, m))])
table('H3. Strat level taps on 08:30 release days vs other days', ['Window', 'Outcome', 'Release days', 'Other days', 'Difference'], rows, 'H3')

# ---- I: trigger geometry ----
rows = []
for role, df in (('called', CALLED), ('opposite', OPP)):
    for col, lab in [('trig_dist_atr', 'Open to trigger (ATR)'), ('risk_atr', 'Trigger to stop (ATR)'), ('t1_dist_atr', 'Trigger to T1 (ATR)'),
                     ('t2_dist_atr', 'Trigger to T2 (ATR)'), ('t3_dist_atr', 'Trigger to T3 (ATR)')]:
        q = df[col].dropna().quantile([.25, .5, .75]).round(2).tolist()
        rows.append([role, lab, int(df[col].notna().sum()), q[1], f'{q[0]} to {q[2]}'])
    rows.append([role, 'Has no T1 / no T2 / no T3', len(df), f"{100*df.t1.isna().mean():.0f}% / {100*df.t2.isna().mean():.0f}% / {100*df.t3.isna().mean():.0f}%", ''])
    rows.append([role, 'T1 closer than 0.1 ATR to the trigger', int(df.t1_dist_atr.notna().sum()), f"{100*(df.t1_dist_atr.dropna() < 0.1).mean():.0f}%", ''])
table('I. Where the brief puts its levels', ['Side', 'Distance', 'n', 'Median', 'Middle half'], rows, 'I')

open(f'{OUT}/tables.md', 'w').write('\n'.join(out_md) + '\n')
json.dump(summ, open(f'{OUT}/summary.json', 'w'), indent=1)
print('\n'.join(out_md))
