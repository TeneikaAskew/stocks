"""Copy the fields this lane needs from the STRAT thread's 08:30 brief replays (main code) into inputs/brief_rows.json.
Usage: python3 -I extract_brief_rows.py <hist dir with oos/ and out/>   (default: the session scratchpad hist dir)"""
import glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
HIST = sys.argv[1] if len(sys.argv) > 1 else '/tmp/claude-0/-home-user/e21e199c-cf90-5c22-8afa-93bf6f11a73f/scratchpad/hist'
files = sorted(glob.glob(f'{HIST}/oos/main0830_20*.json') + glob.glob(f'{HIST}/out/main0830_20*.json'))
rows = []
for f in files:
    day = f.rsplit('_', 1)[1][:10]
    d = json.load(open(f))
    for t in ('SPY', 'QQQ', 'IWM'):
        e = d['tickers'].get(t)
        if e is None:
            continue
        lb = e.get('level_basis') or {}
        r = dict(day=day, ticker=t, status=e.get('signal_status'), atr=lb.get('atr') or e.get('atr14'),
                 prior_close=lb.get('prior_close') or e.get('prev_day_close'), prev_open=e.get('prev_day_open'),
                 reference=lb.get('reference'), premarket=lb.get('premarket'),
                 levels=[[x['name'], x['price']] for x in lb.get('levels', [])],
                 orb_window=e.get('recommended_orb_window'))
        for k in ('calls', 'puts'):
            for s in ('trigger_price', 'trigger_name', 'stop_price', 't1_price', 't2_price', 't3_price'):
                r[f'{k}_{s}'] = e.get(f'{k}_{s}')
        rows.append(r)
out = os.path.join(HERE, '..', 'inputs', 'brief_rows.json')
json.dump(rows, open(out, 'w'))
print(len(files), 'sessions', len(rows), 'rows ->', os.path.abspath(out), os.path.getsize(out), 'bytes')
