"""Which bar cutoffs, if any, reproduce what the 08:20 brief read (level_basis.premarket)
from today's (revised) bars, under the filter-only extremes (the rule the brief ran then)."""
import json, sys
from datetime import date, time as dt_time
import pandas as pd
MAIN = '/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/fp-main'
FP = '/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/fullpull'
sys.path.insert(0, MAIN)
sys.argv = ['x']
exec(open(f'{FP}/scripts/compare_premarket.py').read().split('rows = []')[0])
res = []
for t in ('SPY', 'QQQ', 'IWM'):
    fb = bars(t, 'fresh')
    dt = daily[daily.ticker == t].sort_values('date').reset_index(drop=True)
    for d in SESSIONS[2:]:
        row = dt[dt.date == d.isoformat()].iloc[0]
        prev = dt[(dt.date < d.isoformat()) & dt.close.notna()].iloc[-1]
        prior = {'close': float(prev.close), 'open': float(prev.open), 'atr_14': float(prev.atr_14), 'atr_5': float(prev.atr_5)}
        h = picked_row(t, d); bpm = json.loads(h.level_basis)['premarket']
        rec = _recorded_premarket_filter(json.dumps(bpm['pre_filter_params']) if bpm.get('pre_filter_params') else row.pre_filter_params)
        hit = []
        for mm in range(0, 31):
            end = eastern_bounds_utc(d, dt_time(4, 0), dt_time(7, 50))[1] + pd.Timedelta(minutes=mm)
            s = snap(fb, t, d, prior, rec, end)
            if s.get('raw_high') == bpm['pre_high'] and s.get('raw_low') == bpm['pre_low']:
                hit.append(as_eastern_time(end).strftime('%H:%M'))
        s0 = snap(fb, t, d, prior, rec, pd.Timestamp(bpm['fetched_at']).tz_convert('UTC'))
        res.append({'ticker': t, 'session': d.isoformat(), 'brief_read': f"{bpm['pre_high']} / {bpm['pre_low']}",
                    'revised_at_fetched_at': f"{s0['raw_high']} / {s0['raw_low']}",
                    'cutoffs_07:50-08:20_reproducing': ','.join(hit) or 'none'})
print(pd.DataFrame(res).to_string(index=False))
