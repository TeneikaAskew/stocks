"""Premarket high and low: stored values vs the current main code (v5 rules)
run on the fresh AV bars and on the stored bars, at the brief's cutoff and at
09:30 ET, through gcp.fetchers.fetch_market_data.premarket_snapshot (the one
function the nightly, the recompute and the brief dry run call) with the
filter the session recorded (gcp.premarket_brief._recorded_premarket_filter,
the dry run's own reader). Local files only."""
import json, sys
from datetime import date, time as dt_time
import pandas as pd

MAIN = '/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/fp-main'
FP = '/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/fullpull'
sys.path.insert(0, MAIN)
from lib.eastern_time import eastern_index_to_utc, eastern_bounds_utc, as_eastern_time
from gcp.fetchers.fetch_market_data import premarket_snapshot
from gcp.premarket_brief import _recorded_premarket_filter

SESSIONS = [date(2026, 11, d) for d in (9, 10, 11, 12, 13, 16)]
STORED = {'SPY': 'bars_result_001.csv', 'QQQ': 'bars_result_002.csv', 'IWM': 'bars_result_003.csv'}

daily = pd.read_csv(f'{FP}/stored/ref_result_001.csv')
hist = pd.read_csv(f'{FP}/stored/ref_result_002.csv')
hist['written_at'] = pd.to_datetime(hist['written_at'], utc=True, format='ISO8601')


def picked_row(t, d):
    """T's scoring pick: the latest scheduled or live history row written before 09:30 ET."""
    _, open_utc = eastern_bounds_utc(d, dt_time(4, 0), dt_time(9, 30))
    h = hist[(hist.ticker == t) & (hist.analysis_date == d.isoformat())
             & hist.run_kind.isin(['scheduled', 'live']) & (hist.written_at < open_utc)]
    return None if h.empty else h.sort_values('written_at').iloc[-1]


def bars(t, which):
    if which == 'fresh':
        f = pd.read_csv(f'{FP}/fresh/{t}_2026-11.csv')
        f['ts'] = eastern_index_to_utc(pd.DatetimeIndex(pd.to_datetime(f['ts'])))
    else:
        f = pd.read_csv(f'{FP}/stored/{STORED[t]}')
        f['ts'] = pd.to_datetime(f['ts'], utc=True, format='ISO8601')
    return f[['ts', 'open', 'high', 'low', 'close', 'volume']].sort_values('ts').reset_index(drop=True)


def snap(frame, t, d, prior, recorded, end):
    start, _ = eastern_bounds_utc(d, dt_time(4, 0), dt_time(9, 30))
    w = frame[(frame.ts >= start) & (frame.ts < end)].reset_index(drop=True)
    s = premarket_snapshot(t, d, w, prior, None, end, recorded_filter=recorded)
    if s is None:
        return {'bars': len(w)}
    c = s['pre_filter_params'].get('confirmed') or {}
    pcp = c.get('prior_close_prints') or {}
    scr = c.get('stale_close_reports') or {}
    return {'bars': len(w), 'pre_high': s['pre_high'], 'pre_low': s['pre_low'],
            'raw_high': c.get('raw_high'), 'raw_low': c.get('raw_low'),
            'stale_prints': s['pre_excluded_stale_prints'], 'spikes': s['pre_excluded_spikes'],
            'stale_close_h': scr.get('high'), 'stale_close_l': scr.get('low'),
            'prior_close_bars': pcp.get('bars'), 'thin_bars': (s['pre_filter_params'].get('thin') or {}).get('bars_excluded'),
            'reason': c.get('reason'), 'status': s['pre_filter_status']}


rows = []
for t in ('SPY', 'QQQ', 'IWM'):
    fb, sb = bars(t, 'fresh'), bars(t, 'stored')
    dt = daily[daily.ticker == t].sort_values('date').reset_index(drop=True)
    for d in SESSIONS:
        row = dt[dt.date == d.isoformat()].iloc[0]
        prev = dt[(dt.date < d.isoformat()) & dt.close.notna()].iloc[-1]
        prior = {'close': float(prev.close), 'open': float(prev.open),
                 'atr_14': float(prev.atr_14), 'atr_5': float(prev.atr_5)}
        recorded = _recorded_premarket_filter(row.pre_filter_params)
        h = picked_row(t, d)
        basis = json.loads(h.level_basis) if h is not None and isinstance(h.level_basis, str) else {}
        bpm = basis.get('premarket') or {}
        _, open_utc = eastern_bounds_utc(d, dt_time(4, 0), dt_time(9, 30))
        if bpm.get('fetched_at'):
            cut = pd.Timestamp(bpm['fetched_at']).tz_convert('UTC'); cut_src = 'basis.fetched_at'
        else:
            cut = eastern_bounds_utc(d, dt_time(4, 0), dt_time(8, 20))[1]; cut_src = 'nominal 08:20 ET'
        cut = min(cut, open_utc)
        r = {'ticker': t, 'session': d.isoformat(), 'prior_close': prior['close'],
             'filter_atr': recorded['atr'] if recorded else None,
             'cutoff_et': as_eastern_time(cut).strftime('%H:%M:%S'), 'cutoff_src': cut_src,
             'brief_read_high': bpm.get('pre_high'), 'brief_read_low': bpm.get('pre_low'),
             'stored_high': row.pre_high, 'stored_low': row.pre_low,
             'stored_run': row.pre_recompute_run if isinstance(row.pre_recompute_run, str) else 'nightly'}
        for label, frame, end in (('fresh_cut', fb, cut), ('stored_cut', sb, cut),
                                  ('fresh_0930', fb, open_utc), ('stored_0930', sb, open_utc)):
            for k, v in snap(frame, t, d, prior, recorded, end).items():
                r[f'{label}.{k}'] = v
        rows.append(r)

out = pd.DataFrame(rows)
out.to_csv(f'{FP}/out_premarket.csv', index=False)
pd.set_option('display.width', 300); pd.set_option('display.max_columns', 80)
cols = ['ticker', 'session', 'cutoff_et', 'cutoff_src', 'brief_read_high', 'fresh_cut.pre_high', 'stored_cut.pre_high', 'fresh_cut.raw_high',
        'brief_read_low', 'fresh_cut.pre_low', 'stored_cut.pre_low', 'fresh_cut.raw_low']
print(out[cols].to_string(index=False))
cols = ['ticker', 'session', 'stored_run', 'stored_high', 'fresh_0930.pre_high', 'stored_0930.pre_high', 'fresh_0930.raw_high',
        'stored_low', 'fresh_0930.pre_low', 'stored_0930.pre_low', 'fresh_0930.raw_low']
print(out[cols].to_string(index=False))
cols = ['ticker', 'session', 'prior_close', 'filter_atr'] + [f'fresh_cut.{k}' for k in ('bars', 'stale_prints', 'spikes', 'stale_close_h', 'stale_close_l', 'prior_close_bars', 'thin_bars', 'reason')] + [f'fresh_0930.{k}' for k in ('bars', 'stale_prints', 'prior_close_bars', 'thin_bars')]
print(out[cols].to_string(index=False))
