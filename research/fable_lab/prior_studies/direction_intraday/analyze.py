"""Intraday path of the 08:30 brief's direction calls (CALL/PUT), Mar 3 2025 to Nov 10 2026.

For every ticker-session: from the 09:30 open, max favorable / adverse excursion in ATR units (both
directions), first time each 0.25/0.5/1.0 ATR distance is reached up and down, close vs prior close and
vs open, and the brief's own trigger level touches and trigger-trade outcome (same trade rule as hscore).
Writes session_stats.csv and summary.json next to this file.
Usage: python analyze.py
"""
import glob, json, os, random, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = '/tmp/claude-0/-home-user/e21e199c-cf90-5c22-8afa-93bf6f11a73f/scratchpad/hist'
B = '/mnt/project-files/stocks-scorecard/inputs/bars_raw'
D = '/mnt/project-files/strat-verify/ftfc-replay/raw'
sys.path.insert(0, '/mnt/project-files/stocks-scorecard')
from week_summary import trade  # same fill/stop/T1 rule hscore uses

T = ('SPY', 'QQQ', 'IWM')
KS = (0.25, 0.5, 1.0)
HOLDOUT_END = '2026-04-30'

_bars = {}
def bars(t):
    if t not in _bars:
        _bars[t] = (pd.concat([pd.read_csv(f, parse_dates=['timestamp']) for f in sorted(glob.glob(f'{B}/{t}_1min_*.csv'))])
                    .drop_duplicates('timestamp').set_index('timestamp').sort_index())
    return _bars[t]

def rth(t, day):
    return bars(t).loc[f'{day} 09:30':f'{day} 15:59']

def prev_rth_close(t, day):
    b = bars(t); b = b[b.index < pd.Timestamp(day)]
    b = b[(b.index.time >= pd.Timestamp('09:30').time()) & (b.index.time <= pd.Timestamp('15:59').time())]
    return float(b.close.iloc[-1])

_atr = {}
def daily_atr14(t, day):
    if t not in _atr:
        d = pd.read_csv(f'{D}/{t}_daily_adjusted.csv', parse_dates=['timestamp']).sort_values('timestamp').set_index('timestamp')
        pc = d.close.shift(1)
        tr = pd.concat([d.high - d.low, (d.high - pc).abs(), (d.low - pc).abs()], axis=1).max(axis=1)
        _atr[t] = tr.rolling(14).mean().shift(1)  # ATR known before the session
    s = _atr[t]
    s = s[s.index <= pd.Timestamp(day)]
    return float(s.iloc[-1])

def direction(status):
    s = (status or '').upper()
    return 'up' if s.startswith('CALL') else 'down' if s.startswith('PUT') else None

def path_stats(b, o, atr):
    """Per direction: MFE (ATR), time of MFE, first hit time per k. Returns dict keyed 'up'/'down'."""
    hi = b.high.values; lo = b.low.values; ts = b.index
    up_ex = (np.maximum.accumulate(hi) - o) / atr
    dn_ex = (o - np.minimum.accumulate(lo)) / atr
    out = {}
    for side, ex in (('up', up_ex), ('down', dn_ex)):
        r = {'mfe': float(max(ex[-1], 0)), 'mfe_t': ts[int(np.argmax(ex))].strftime('%H:%M')}
        for k in KS:
            idx = np.argmax(ex >= k) if (ex >= k).any() else None
            r[f'hit{k}'] = idx
            r[f'hit{k}_t'] = ts[idx].strftime('%H:%M') if idx is not None else ''
        out[side] = r
    return out

def load_rows():
    files = sorted(glob.glob(f'{HIST}/oos/main0830_20*.json') + glob.glob(f'{HIST}/out/main0830_20*.json'))
    rows = []
    for f in files:
        day = f.rsplit('_', 1)[1][:10]
        d = json.load(open(f))
        for t in T:
            e = d['tickers'].get(t)
            b = rth(t, day)
            if e is None or len(b) < 300:  # same half-day rule as hscore
                continue
            lb = e.get('level_basis') or {}
            atr = lb.get('atr') or e.get('atr14')
            atr_src = 'row'
            if not atr:
                atr = daily_atr14(t, day); atr_src = 'daily_csv'
            o = float(b.open.iloc[0]); c = float(b.close.iloc[-1])
            pc = e.get('prev_day_close') or prev_rth_close(t, day)
            ps = path_stats(b, o, atr)
            r = dict(day=day, ticker=t, window='holdout' if day <= HOLDOUT_END else 'in_sample',
                     status=e.get('signal_status') or 'No row', call=direction(e.get('signal_status')),
                     atr=round(atr, 4), atr_src=atr_src, prev_close=pc, open=o, close=c,
                     close_vs_prior='up' if c > pc else 'down', close_vs_open='up' if c > o else 'down',
                     move_close_atr=round((c - pc) / atr, 4), move_oc_atr=round((c - o) / atr, 4),
                     gap_atr=round((o - pc) / atr, 4))
            for side in ('up', 'down'):
                s = ps[side]
                r[f'{side}_mfe'] = round(s['mfe'], 4); r[f'{side}_mfe_t'] = s['mfe_t']
                for k in KS:
                    r[f'{side}_hit{k}'] = s[f'hit{k}'] is not None
                    r[f'{side}_hit{k}_t'] = s[f'hit{k}_t']
                    r[f'_{side}_i{k}'] = s[f'hit{k}']
            # brief's own triggers
            for side, k in (('up', 'calls'), ('down', 'puts')):
                tp = e.get(f'{k}_trigger_price')
                r[f'{side}_trig'] = tp
                r[f'{side}_stop'] = e.get(f'{k}_stop_price'); r[f'{side}_t1'] = e.get(f'{k}_t1_price')
                if tp is None:
                    r[f'{side}_trig_touch'] = None; r[f'{side}_trig_thru_open'] = None
                    r[f'{side}_trig_t'] = ''; r[f'{side}_trig_R'] = None; r[f'{side}_trig_how'] = ''
                    continue
                touched = (b.high >= tp) if side == 'up' else (b.low <= tp)
                r[f'{side}_trig_touch'] = bool(touched.any())
                r[f'{side}_trig_thru_open'] = bool(o >= tp) if side == 'up' else bool(o <= tp)
                r[f'{side}_trig_t'] = b.index[int(np.argmax(touched.values))].strftime('%H:%M') if touched.any() else ''
                x = trade(b.reset_index(drop=True), 'long' if side == 'up' else 'short', tp, r[f'{side}_stop'], r[f'{side}_t1'])
                r[f'{side}_trig_R'] = x['R'] if x and x.get('fill') else None
                r[f'{side}_trig_how'] = x.get('how', '') if x and x.get('fill') else ''
            rows.append(r)
    return pd.DataFrame(rows)

def shock_proxy(df):
    """No econ-calendar field in the rows. Proxy: SPY 08:30-08:44 range / 07:00-08:29 range; top third = 'shock'."""
    spy = bars('SPY'); out = {}
    for d in sorted(df.day.unique()):
        w = spy.loc[f'{d} 08:30':f'{d} 08:44']; pre = spy.loc[f'{d} 07:00':f'{d} 08:29']
        out[d] = (w.high.max() - w.low.min()) / max(1e-9, pre.high.max() - pre.low.min()) if len(w) and len(pre) else 0
    cut = sorted(out.values())[int(len(out) * 2 / 3)]
    return {d: v >= cut for d, v in out.items()}

def side_view(df, side_of):
    """Return per-row stats for a chosen direction. side_of(row) -> 'up'|'down'."""
    recs = []
    for _, r in df.iterrows():
        s = side_of(r); a = 'down' if s == 'up' else 'up'
        x = dict(day=r.day, ticker=r.ticker, mfe=r[f'{s}_mfe'], mae=r[f'{a}_mfe'],
                 close_right=(r.close_vs_prior == s), oc_right=(r.close_vs_open == s),
                 signed_close=(r.move_close_atr if s == 'up' else -r.move_close_atr),
                 signed_oc=(r.move_oc_atr if s == 'up' else -r.move_oc_atr))
        for k in KS:
            fi = r[f'_{s}_i{k}']; ai = r[f'_{a}_i{k}']
            fi = None if pd.isna(fi) else int(fi); ai = None if pd.isna(ai) else int(ai)
            x[f'fav{k}'] = fi is not None
            x[f'adv{k}'] = ai is not None
            x[f'first{k}'] = fi is not None and (ai is None or fi < ai)
            x[f'tie{k}'] = fi is not None and ai is not None and fi == ai
        recs.append(x)
    return pd.DataFrame(recs)

def summarize(v):
    if len(v) == 0:
        return {'n': 0}
    o = {'n': int(len(v)), 'close_right_pct': round(100 * v.close_right.mean(), 1),
         'close_right_n': int(v.close_right.sum()), 'oc_right_pct': round(100 * v.oc_right.mean(), 1),
         'mean_close_atr': round(v.signed_close.mean(), 3), 'mean_oc_atr': round(v.signed_oc.mean(), 3),
         'median_mfe': round(v.mfe.median(), 3), 'median_mae': round(v.mae.median(), 3),
         'mean_mfe': round(v.mfe.mean(), 3), 'mean_mae': round(v.mae.mean(), 3)}
    for k in KS:
        o[f'fav{k}_pct'] = round(100 * v[f'fav{k}'].mean(), 1)
        o[f'adv{k}_pct'] = round(100 * v[f'adv{k}'].mean(), 1)
        o[f'first{k}_pct'] = round(100 * v[f'first{k}'].mean(), 1)
        o[f'tie{k}_n'] = int(v[f'tie{k}'].sum())
    return o

def boot_diff(a, b, col, days, n=2000):
    """Day-clustered bootstrap 90% CI of mean(a[col]) - mean(b[col]); a and b row-aligned."""
    d = (a[col].astype(float).values - b[col].astype(float).values)
    by = pd.Series(d).groupby(days.values).agg(['sum', 'count'])
    s, c = by['sum'].values, by['count'].values
    random.seed(11); m = len(s); res = []
    for _ in range(n):
        idx = [random.randrange(m) for _ in range(m)]
        res.append(s[idx].sum() / c[idx].sum())
    res.sort()
    return round(100 * d.mean(), 1), round(100 * res[int(0.05 * n)], 1), round(100 * res[int(0.95 * n)], 1)

def main():
    df = load_rows()
    shock = shock_proxy(df)
    df['shock_proxy'] = df.day.map(shock)
    df['month'] = df.day.str[:7]
    calls = df[df.call.notna()].reset_index(drop=True)
    res = {'sessions': int(df.day.nunique()), 'ticker_sessions': int(len(df)), 'calls': int(len(calls))}

    brief = side_view(calls, lambda r: r.call)
    opp = side_view(calls, lambda r: 'down' if r.call == 'up' else 'up')
    allup = side_view(calls, lambda r: 'up')
    alldown = side_view(calls, lambda r: 'down')
    coin = pd.concat([allup, alldown])  # expected value of a fair coin on the same sessions
    all_up_all = side_view(df, lambda r: 'up'); all_dn_all = side_view(df, lambda r: 'down')

    res['overall'] = {'brief': summarize(brief), 'opposite_of_brief': summarize(opp),
                      'coin_flip_same_sessions': summarize(coin), 'always_call_same_sessions': summarize(allup),
                      'always_put_same_sessions': summarize(alldown),
                      'coin_flip_all_sessions': summarize(pd.concat([all_up_all, all_dn_all])),
                      'always_call_all_sessions': summarize(all_up_all)}
    res['brief_minus_opposite_90ci'] = {c: boot_diff(brief, opp, c, calls.day) for c in
                                        ['fav0.25', 'fav0.5', 'fav1.0', 'first0.25', 'first0.5', 'first1.0', 'close_right']}
    res['brief_minus_always_call_90ci'] = {c: boot_diff(brief, allup, c, calls.day) for c in
                                           ['fav0.5', 'first0.5', 'close_right']}

    def split(key, values):
        out = {}
        for v in values:
            m = (calls[key] == v).values
            out[str(v)] = {'brief': summarize(brief[m]), 'opposite': summarize(opp[m]), 'always_call': summarize(allup[m])}
        return out
    res['by_ticker'] = split('ticker', T)
    res['by_window'] = split('window', ['holdout', 'in_sample'])
    res['by_month'] = split('month', sorted(calls.month.unique()))
    res['by_shock_proxy'] = split('shock_proxy', [True, False])
    calls['strength'] = calls.status.str.extract(r'\((\d)/5\)')[0]
    res['by_strength'] = split('strength', ['2', '3', '4'])
    calls['call_side'] = calls.call
    res['by_side'] = split('call_side', ['up', 'down'])

    # trigger touches in the call direction, and the trigger trade outcome
    def trig(sub, side_of):
        tt, thru, R, touch_n = [], 0, [], 0
        n = 0
        for _, r in sub.iterrows():
            s = side_of(r)
            if r[f'{s}_trig'] is None or pd.isna(r[f'{s}_trig']):
                continue
            n += 1
            if r[f'{s}_trig_touch']:
                touch_n += 1
                thru += bool(r[f'{s}_trig_thru_open'])
            if r[f'{s}_trig_R'] is not None and not pd.isna(r[f'{s}_trig_R']):
                R.append(float(r[f'{s}_trig_R']))
        R = np.array(R)
        return {'with_trigger': n, 'touched': touch_n, 'touch_pct': round(100 * touch_n / n, 1) if n else None,
                'through_at_open': thru, 'trades': int(len(R)), 'wins': int((R > 0).sum()),
                'win_pct': round(100 * (R > 0).mean(), 1) if len(R) else None,
                'total_R': round(float(R.sum()), 2), 'avg_R': round(float(R.mean()), 3) if len(R) else None}
    res['trigger'] = {'call_side': trig(calls, lambda r: r.call),
                      'opposite_side': trig(calls, lambda r: 'down' if r.call == 'up' else 'up'),
                      'no_signal_up': trig(df[df.call.isna()], lambda r: 'up'),
                      'no_signal_down': trig(df[df.call.isna()], lambda r: 'down')}
    res['trigger_by_ticker'] = {t: {'call_side': trig(calls[calls.ticker == t], lambda r: r.call),
                                    'opposite_side': trig(calls[calls.ticker == t], lambda r: 'down' if r.call == 'up' else 'up')}
                                for t in T}
    res['trigger_by_window'] = {w: {'call_side': trig(calls[calls.window == w], lambda r: r.call),
                                    'opposite_side': trig(calls[calls.window == w], lambda r: 'down' if r.call == 'up' else 'up')}
                                for w in ('holdout', 'in_sample')}

    # per-session CSV (calls joined with their call-direction view)
    keep = [c for c in df.columns if not c.startswith('_')]
    out = calls[keep].copy()
    for c in ['mfe', 'mae'] + [f'{p}{k}' for p in ('fav', 'adv', 'first', 'tie') for k in KS]:
        out[f'call_{c}'] = brief[c].values
    out['call_close_right'] = brief.close_right.values
    out.to_csv(f'{HERE}/session_stats.csv', index=False)
    df[keep].to_pickle(f'{HIST}/../direction_intraday_all.pkl')
    json.dump(res, open(f'{HERE}/summary.json', 'w'), indent=1, default=str)
    print(json.dumps({k: res[k] for k in ('sessions', 'ticker_sessions', 'calls')}))

if __name__ == '__main__':
    main()
