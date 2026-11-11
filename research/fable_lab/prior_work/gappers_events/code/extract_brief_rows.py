"""Copy the fields this lane uses out of the brief replay JSONs into brief_rows.json (one list of rows).
Usage: python3 extract_brief_rows.py <dir with main0830_*.json> [more dirs...]
Each replay JSON was made by /mnt/project-files/stocks-scorecard/tools/replay_day.py (brief's own code)."""
import glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
rows = []
for d in sys.argv[1:]:
    for f in sorted(glob.glob(f'{d}/main0[89][0-9][0-9]_20*.json')):
        j = json.load(open(f)); day = j['session']; cut = j['cutoff']
        for t, e in j['tickers'].items():
            lb = e.get('level_basis') or {}; pm = lb.get('premarket') or {}
            r = dict(day=day, ticker=t, cutoff=cut, status=e.get('signal_status'), atr=lb.get('atr') or e.get('atr14'),
                     prior_close=lb.get('prior_close') or e.get('prev_day_close'), pdh=e.get('prev_day_high'), pdl=e.get('prev_day_low'),
                     pre_high=pm.get('pre_high'), pre_low=pm.get('pre_low'), pre_vwap=pm.get('pre_vwap'), pm_gap_pct=pm.get('gap_pct'),
                     regime=e.get('regime'), levels={x['name']: x['price'] for x in (lb.get('levels') or []) if x.get('price') is not None},
                     plans=e.get('_plans'))
            for k in ('calls', 'puts'):
                for s in ('trigger_price', 'trigger_name', 'stop_price', 'stop_name', 't1_price', 't2_price', 't3_price'):
                    r[f'{k}_{s}'] = e.get(f'{k}_{s}')
            rows.append(r)
out = os.path.join(HERE, '..', 'brief_rows.json')
json.dump(rows, open(out, 'w'))
from collections import Counter
print(len(rows), 'rows', Counter(r['cutoff'] for r in rows), '->', os.path.normpath(out))
