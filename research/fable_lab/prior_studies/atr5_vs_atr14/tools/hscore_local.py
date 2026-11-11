"""Copy of scratchpad hist/hscore.py (scoring unchanged). One change: a level_basis whose premarket is None (sessions before the premarket thresholds have 40 sessions of one-minute history) records pmh/pml as None instead of raising."""
"""Score brief replays (triggers, plans, direction) on bars_raw. Usage:
hscore.py <outdir> <prefix> [--days=a,b] [--json=path]  (prefix like main0830)"""
import sys, json, glob, os
import pandas as pd
sys.path.insert(0, '/mnt/project-files/stocks-scorecard')
from week_summary import trade
B = '/mnt/project-files/stocks-scorecard/inputs/bars_raw'
T = ('SPY', 'QQQ', 'IWM')
_bars = {}
def bars(t):
    if t not in _bars:
        _bars[t] = pd.concat([pd.read_csv(f, parse_dates=['timestamp']) for f in sorted(glob.glob(f'{B}/{t}_1min_*.csv'))]).drop_duplicates('timestamp').set_index('timestamp').sort_index()
    return _bars[t]
_sess = {}
def sess(t, day):
    k = (t, day)
    if k not in _sess:
        b = bars(t).loc[f'{day} 09:30':f'{day} 15:59']
        _sess[k] = b.reset_index(drop=True)
    return _sess[k]
def prev_close(t, day):
    b = bars(t); b = b[(b.index < pd.Timestamp(day)) & (b.index.time <= pd.Timestamp('15:59').time()) & (b.index.time >= pd.Timestamp('09:30').time())]
    return float(b.close.iloc[-1])
def direction(status):
    s = (status or '').upper()
    return 'up' if s.startswith('CALL') else 'down' if s.startswith('PUT') else None
def score(outdir, prefix, days=None):
    rows = []
    for f in sorted(glob.glob(f'{outdir}/{prefix}_20*.json')):
        day = f.rsplit('_', 1)[1][:10]
        if days and day not in days: continue
        d = json.load(open(f))
        for t in T:
            e = d['tickers'].get(t); b = sess(t, day)
            if e is None or len(b) < 300: continue
            pc = e.get('prev_day_close') or prev_close(t, day); o, c = b.open.iloc[0], b.close.iloc[-1]
            r = dict(day=day, t=t, status=e.get('signal_status'), call=direction(e.get('signal_status')),
                     vs_prior='up' if c > pc else 'down', vs_open='up' if c > o else 'down',
                     pmh=((e.get("level_basis") or {}).get("premarket") or {}).get("pre_high"),
                     pml=((e.get("level_basis") or {}).get("premarket") or {}).get("pre_low"), trig={}, plans=[])
            for side, k in (('long', 'calls'), ('short', 'puts')):
                x = trade(b, side, e.get(f'{k}_trigger_price'), e.get(f'{k}_stop_price'), e.get(f'{k}_t1_price'))
                r['trig'][side] = x['R'] if x and x.get('fill') else None
            for side, pl in (e.get('_plans') or {}).items():
                if not isinstance(pl, list): continue
                for p in pl:
                    if p.get('entry') is None: continue
                    tg = [x for x in p['targets'] if x is not None]
                    x = trade(b, side, sum(p['entry']) / 2, p['stop'], tg[0] if tg else None)
                    if x and x.get('fill') and x.get('R') is not None:
                        r['plans'].append((side, p['persona'], x['R']))
            rows.append(r)
    return rows
def summary(rows):
    tr = [v for r in rows for v in r['trig'].values() if v is not None]
    tr_with = [r['trig']['long' if r['call'] == 'up' else 'short'] for r in rows if r['call'] and r['trig']['long' if r['call'] == 'up' else 'short'] is not None]
    pl = [x[2] for r in rows for x in r['plans']]
    pl_with = [x[2] for r in rows for x in r['plans'] if r['call'] and x[0] == ('long' if r['call'] == 'up' else 'short')]
    calls = [r for r in rows if r['call']]
    f = lambda xs: dict(n=len(xs), win=sum(x > 0 for x in xs), R=round(sum(xs), 2), avg=round(sum(xs) / len(xs), 3) if xs else None)
    return dict(sessions=len({r['day'] for r in rows}), calls=len(calls),
                right_vs_prior=sum(r['call'] == r['vs_prior'] for r in calls), right_vs_open=sum(r['call'] == r['vs_open'] for r in calls),
                triggers=f(tr), triggers_with_call=f(tr_with), plans=f(pl), plans_with_call=f(pl_with))
if __name__ == '__main__':
    days = next((a.split('=', 1)[1].split(',') for a in sys.argv if a.startswith('--days=')), None)
    rows = score(sys.argv[1], sys.argv[2], days)
    js = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--json=')), None)
    if js: json.dump(rows, open(js, 'w'))
    print(sys.argv[2], json.dumps(summary(rows)))
