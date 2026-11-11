"""Cross-check the calendar: is the 08:30 minute a volume spike in SPY premarket on listed 08:30 days?
spike830 = volume of the 08:30 minute / median minute volume 08:00-08:29. Usage: python3 check_calendar.py"""
import pandas as pd
from common import *
d = pd.read_csv(f'{LANE}/days.csv', keep_default_na=False, na_values=['nan']); d['spike830'] = pd.to_numeric(d.spike830, errors='coerce'); s = d[d.ticker == 'SPY'].copy()
s['grp'] = s.apply(lambda r: 'tier1 08:30' if r.t1_0830 else ('tier2 08:30' if r.events_0830 else 'none listed'), axis=1)
print(s.groupby('grp').spike830.describe(percentiles=[.1, .5, .9]).round(1))
print('\nListed 08:30 days with spike under 5x (possible wrong date):')
print(s[(s.events_0830 != '') & (s.spike830 < 5)][['day', 'events_0830', 'spike830']].round(1).to_string(index=False))
print('\nUnlisted days with spike over 20x (other 08:30 news, e.g. jobless claims Thursdays):')
u = s[(s.events_0830 == '') & (s.spike830 > 20)][['day', 'spike830']]
u['weekday'] = pd.to_datetime(u.day).dt.day_name(); print(u.round(1).to_string(index=False))
cal = calendar(); missing = sorted(set(cal.date) - set(d.day)); print('\ncalendar dates with no session row:', missing)
