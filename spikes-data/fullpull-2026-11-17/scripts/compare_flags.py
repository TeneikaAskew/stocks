"""The isolated-print rule (lib.bar_prints via intraday_bar_flags.judge_month,
pure) on the fresh bars, beside the stored intraday_bar_flags rows."""
import sys
import pandas as pd
MAIN = '/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/fp-main'
FP = '/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/fullpull'
sys.path.insert(0, MAIN)
from lib.eastern_time import eastern_index_to_utc, market_date
from gcp.fetchers.intraday_bar_flags import judge_month
from datetime import date
END = pd.Timestamp('2026-11-17 05:00:00+00:00')
LO = pd.Timestamp('2026-11-09 09:00:00+00:00')
stored_flags = pd.read_csv(f'{FP}/stored/ref_result_004.csv')
stored_flags['ts'] = pd.to_datetime(stored_flags['ts'], utc=True, format='ISO8601')
rows = []
for t in ('SPY', 'QQQ', 'IWM'):
    f = pd.read_csv(f'{FP}/fresh/{t}_2026-11.csv')
    f['ts'] = eastern_index_to_utc(pd.DatetimeIndex(pd.to_datetime(f['ts'])))
    f = f[f.ts < END].sort_values('ts').reset_index(drop=True)
    kept, counts = judge_month(f[['ts', 'open', 'high', 'low', 'close', 'volume']], (2026, 11))
    a = set((x, s) for x, s in zip(kept.ts, kept.side) if LO <= x < END)
    sf = stored_flags[(stored_flags.ticker == t) & (stored_flags.ts >= LO) & (stored_flags.ts < END)]
    b = set((x, s) for x, s in zip(sf.ts, sf.side))
    for d in (9, 10, 11, 12, 13, 16):
        day = date(2026, 11, d)
        aa = {k for k in a if market_date(k[0]) == day}; bb = {k for k in b if market_date(k[0]) == day}
        rows.append({'ticker': t, 'session': day.isoformat(), 'flags_fresh': len(aa), 'flags_stored': len(bb),
                     'only_fresh': len(aa - bb), 'only_stored': len(bb - aa)})
out = pd.DataFrame(rows)
print(out.to_string(index=False)); print(out[['flags_fresh', 'flags_stored', 'only_fresh', 'only_stored']].sum().to_dict())
