"""Fresh AV pull vs stored market_data_intraday, per ticker and session, through
production functions only (premarket_as_read.compare_bars,
eastern_time.stored_intraday_to_eastern). Reads local files, writes local files."""
import json, sys
from datetime import date
import numpy as np
import pandas as pd

MAIN = '/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/fp-main'
FP = '/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/fullpull'
sys.path.insert(0, MAIN)
from lib.eastern_time import (eastern_index_to_utc, market_date, stored_intraday_to_eastern,
                              utc_to_eastern_naive, eastern_bounds_utc)
from gcp.fetchers.premarket_as_read import compare_bars
from datetime import time as dt_time

SESSIONS = [date(2026, 11, d) for d in (9, 10, 11, 12, 13, 16)]
STORED = {'SPY': 'bars_result_001.csv', 'QQQ': 'bars_result_002.csv', 'IWM': 'bars_result_003.csv'}
END_UTC = pd.Timestamp('2026-11-17 05:00:00+00:00')


def load_stored(t):
    s = pd.read_csv(f'{FP}/stored/{STORED[t]}')
    s['ts'] = pd.to_datetime(s['ts'], utc=True, format='ISO8601')
    return s


def load_fresh(t):
    f = pd.read_csv(f'{FP}/fresh/{t}_2026-11.csv')
    f['ts'] = pd.to_datetime(f['ts'])  # naive Eastern, as the vendor keyed it
    return f


out_rows, detail = [], []
conv = {}
for t in ('SPY', 'QQQ', 'IWM'):
    st = load_stored(t)
    fr = load_fresh(t)
    # Is every stored row a true UTC instant (CLAUDE.md 3.9)? The reader's own test.
    inst = pd.DatetimeIndex(st['ts'])
    idx, keep = stored_intraday_to_eastern(inst, st['volume'])
    conv[t] = {'rows': int(len(st)), 'read_as_label': int((idx != utc_to_eastern_naive(inst)).sum()),
               'dropped': int((~keep).sum())}
    fr_utc = fr.copy()
    fr_utc['ts'] = eastern_index_to_utc(pd.DatetimeIndex(fr['ts']))
    fr_utc = fr_utc[fr_utc['ts'] < END_UTC]
    for d in SESSIONS:
        day_fr = fr[[market_date(x) == d for x in fr_utc.reindex(fr.index)['ts'].fillna(END_UTC)]]
        day_fr = fr.loc[fr_utc.index[[market_date(x) == d for x in fr_utc['ts']]]]
        res = compare_bars(day_fr, st, d)
        # Own detail at the 0.0001 tolerance T asked for, on the same instants.
        a = day_fr.copy(); a['ts'] = eastern_index_to_utc(pd.DatetimeIndex(a['ts'])); a = a.set_index('ts')
        b = st[[market_date(x) == d for x in st['ts']]].set_index('ts')
        both = a.index.intersection(b.index)
        n_gt = 0
        for ts in both:
            diffs = {}
            for c in ('open', 'high', 'low', 'close'):
                if abs(float(a.at[ts, c]) - float(b.at[ts, c])) > 0.0001:
                    diffs[c] = (float(b.at[ts, c]), float(a.at[ts, c]))
            if int(a.at[ts, 'volume']) != int(b.at[ts, 'volume']):
                diffs['volume'] = (int(b.at[ts, 'volume']), int(a.at[ts, 'volume']))
            if diffs:
                n_gt += 1
                detail.append({'ticker': t, 'session': d.isoformat(), 'ts_et': str(utc_to_eastern_naive(pd.DatetimeIndex([ts]))[0]),
                               'kind': 'differs', **{k: f'{v[0]} -> {v[1]}' for k, v in diffs.items()}})
        for ts in a.index.difference(b.index):
            detail.append({'ticker': t, 'session': d.isoformat(), 'ts_et': str(utc_to_eastern_naive(pd.DatetimeIndex([ts]))[0]),
                           'kind': 'only_fresh', 'volume': int(a.at[ts, 'volume'])})
        for ts in b.index.difference(a.index):
            detail.append({'ticker': t, 'session': d.isoformat(), 'ts_et': str(utc_to_eastern_naive(pd.DatetimeIndex([ts]))[0]),
                           'kind': 'only_stored', 'volume': int(b.at[ts, 'volume'])})
        pm = res['premarket']
        out_rows.append({'ticker': t, 'session': d.isoformat(), 'fresh': res['as_read_bars'], 'stored': res['stored_bars'],
                         'matched': res['matched'], 'only_fresh': res['only_as_read'], 'only_stored': res['only_stored'],
                         'differing': res['differing'], 'diff_gt_0.0001_or_vol': n_gt,
                         'd_open': res['differ_open'], 'd_high': res['differ_high'], 'd_low': res['differ_low'],
                         'd_close': res['differ_close'], 'd_vol': res['differ_volume'],
                         'pm_fresh': pm['as_read_bars'], 'pm_stored': pm['stored_bars'], 'pm_differing': pm['differing'],
                         'pm_only_fresh': pm['only_as_read'], 'pm_only_stored': pm['only_stored']})

tab = pd.DataFrame(out_rows)
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 40)
print('convention check (stored_intraday_to_eastern):', json.dumps(conv))
print(tab.to_string(index=False))
tab.to_csv(f'{FP}/out_bars_summary.csv', index=False)
pd.DataFrame(detail).to_csv(f'{FP}/out_bars_detail.csv', index=False)
print('detail rows:', len(detail))
