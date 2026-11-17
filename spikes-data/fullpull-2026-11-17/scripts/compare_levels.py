"""Published triggers and stops (T's pick: the latest scheduled or live
premarket_analysis_history row written before 09:30 ET) beside what the
replayed premarket makes the PMK_H / PMK_L levels. No level is picked here."""
import sys
from datetime import date
import pandas as pd
FP = '/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/fullpull'
pm = pd.read_csv(f'{FP}/out_premarket.csv')
hist = pd.read_csv(f'{FP}/stored/ref_result_002.csv')
hist['written_at'] = pd.to_datetime(hist['written_at'], utc=True, format='ISO8601')
rows = []
for _, p in pm.iterrows():
    d = date.fromisoformat(p.session)
    open_utc = pd.Timestamp(f'{p.session} 09:30', tz='America/New_York').tz_convert('UTC')
    h = hist[(hist.ticker == p.ticker) & (hist.analysis_date == p.session)
             & hist.run_kind.isin(['scheduled', 'live']) & (hist.written_at < open_utc)].sort_values('written_at').iloc[-1]
    for side in ('calls', 'puts'):
        for role in ('trigger', 'stop'):
            name, price = h[f'{side}_{role}_name'], h[f'{side}_{role}_price']
            if name == 'PMK_H':
                v5, flt = p['fresh_cut.pre_high'], p['fresh_cut.raw_high']
            elif name == 'PMK_L':
                v5, flt = p['fresh_cut.pre_low'], p['fresh_cut.raw_low']
            else:
                v5 = flt = None
            rows.append({'ticker': p.ticker, 'session': p.session, 'written_et': h.written_at.tz_convert('America/New_York').strftime('%H:%M'),
                         'leg': f'{side} {role}', 'name': name, 'published': price,
                         'same_rule_revised_bars': flt, 'v5_revised_bars': v5,
                         'verdict': ('not a premarket level' if v5 is None else
                                     ('v5 equal' if abs(v5 - price) < 1e-9 else
                                      ('data revision only' if abs(flt - price) >= 1e-9 and abs(flt - v5) < 1e-9 else
                                       ('rule change only' if abs(flt - price) < 1e-9 else 'rule change and revision'))))})
out = pd.DataFrame(rows)
out.to_csv(f'{FP}/out_levels.csv', index=False)
pd.set_option('display.width', 250)
print(out.to_string(index=False))
print(out[out.name.isin(['PMK_H', 'PMK_L'])].verdict.value_counts())
