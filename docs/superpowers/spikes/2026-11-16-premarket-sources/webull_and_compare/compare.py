"""Compare three sources of 2026-11-16 premarket one-minute bars for SPY, QQQ, IWM.

Read-only. Sources:
  av    = Alpha Vantage read about 15:00 ET on 2026-11-16 (in-session read), Eastern stamps
  st    = Cloud SQL market_data_intraday after the 22:27Z fetch, UTC stamps
  wb    = Webull get_stock_bars_single M1 PRE, UTC stamps
Run with: python3 compare.py  (cwd /tmp/build-brief so lib imports resolve)
"""
import csv
import json
import math
import statistics
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, '/tmp/build-brief')
from lib.indicators import calculate_premarket_context  # noqa: E402
from lib.strat_levels import price_cents  # noqa: E402

S = '/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad'
D = S + '/premarket_sources'
FX = '/tmp/build-brief/tests/fixtures/premarket_2026_11_16'
ET = ZoneInfo('America/New_York')
UTC = timezone.utc
START = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)   # 04:00 ET
OPEN = datetime(2026, 11, 16, 14, 30, tzinfo=UTC)  # 09:30 ET
PREV_CLOSE = {'QQQ': 679.89, 'SPY': 754.37, 'IWM': 277.54}

brief = json.load(open(f'{FX}/brief_rows.json'))
BRIEF = {}
for r in brief['rows']:
    row = dict(zip(brief['columns'], r))
    lb = row['level_basis']
    if isinstance(lb, str):
        lb = json.loads(lb)
    BRIEF[row['ticker']] = lb['premarket']


def load_av(t, path=None):
    out = {}
    for r in csv.DictReader(open(path or f'{S}/av1116/{t}.csv')):
        ts = datetime.strptime(r['timestamp'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=ET).astimezone(UTC)
        if START <= ts < OPEN:
            out[ts] = tuple(float(r[k]) for k in ('open', 'high', 'low', 'close')) + (float(r['volume']),)
    return out


def load_st(t):
    out = {}
    for r in csv.DictReader(open(f'{FX}/{t}_bars.csv')):
        ts = datetime.fromisoformat(r['ts']).astimezone(UTC)
        if START <= ts < OPEN:
            out[ts] = tuple(float(r[k]) for k in ('open', 'high', 'low', 'close')) + (float(r['volume']),)
    return out


def load_wb(t):
    out = {}
    if t == 'IWM':
        for r in csv.DictReader(open(f'{D}/webull_IWM_20261116.csv')):
            ts = datetime.strptime(r['time_utc'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=UTC)
            if START <= ts < OPEN:
                out[ts] = tuple(float(r[k]) for k in ('open', 'high', 'low', 'close')) + (float(r['volume']),)
    else:
        for r in json.load(open(f'{D}/webull_{t}_20261116.json')):
            ts = datetime.strptime(r['time'], '%Y-%m-%dT%H:%M:%S.000+0000').replace(tzinfo=UTC)
            if START <= ts < OPEN:
                out[ts] = tuple(float(r[k]) for k in ('open', 'high', 'low', 'close')) + (float(r['volume']),)
    return out


def et(ts):
    return ts.astimezone(ET).strftime('%H:%M')


def same_cent(a, b):
    return price_cents(a) == price_cents(b)


def alignment(a, b):
    """Share of common minutes whose close agrees to the cent, at label shifts -1, 0, +1."""
    res = {}
    for sh in (-1, 0, 1):
        n = agree = 0
        for ts, v in a.items():
            w = b.get(ts + timedelta(minutes=sh))
            if w is None:
                continue
            n += 1
            agree += same_cent(v[3], w[3])
        res[sh] = (agree, n)
    return res


def agreement(srcs, keys):
    names = ['open', 'high', 'low', 'close']
    out = {}
    pairs = [('av', 'st'), ('av', 'wb'), ('st', 'wb')]
    for p, q in pairs:
        out[f'{p}-{q}'] = {nm: sum(same_cent(srcs[p][k][i], srcs[q][k][i]) for k in keys) for i, nm in enumerate(names)}
        out[f'{p}-{q}']['all4'] = sum(all(same_cent(srcs[p][k][i], srcs[q][k][i]) for i in range(4)) for k in keys)
    out['all3'] = {nm: sum(same_cent(srcs['av'][k][i], srcs['st'][k][i]) and same_cent(srcs['av'][k][i], srcs['wb'][k][i]) for k in keys)
                   for i, nm in enumerate(names)}
    out['all3']['all4'] = sum(all(same_cent(srcs['av'][k][i], srcs['st'][k][i]) and same_cent(srcs['av'][k][i], srcs['wb'][k][i])
                                  for i in range(4)) for k in keys)
    return out


def vol_ratios(srcs, keys):
    def med(p, q):
        r = [srcs[p][k][4] / srcs[q][k][4] for k in keys if srcs[q][k][4] > 0]
        return round(statistics.median(r), 3) if r else None, len(r)
    tot = {s: int(sum(srcs[s][k][4] for k in keys)) for s in srcs}
    return {'st/av': med('st', 'av'), 'wb/av': med('wb', 'av'), 'wb/st': med('wb', 'st'), 'totals_common': tot}


def raw_hl(bars, cutoff=None):
    ks = [k for k in bars if cutoff is None or k < cutoff]
    if not ks:
        return None
    hk = max(ks, key=lambda k: bars[k][1])
    lk = min(ks, key=lambda k: bars[k][2])
    return {'high': bars[hk][1], 'high_at': et(hk), 'high_vol': int(bars[hk][4]),
            'low': bars[lk][2], 'low_at': et(lk), 'low_vol': int(bars[lk][4]), 'bars': len(ks)}


def ctx(bars, t, cutoff=None, filter_params=None):
    ks = sorted(k for k in bars if cutoff is None or k < cutoff)
    times = pd.Series(pd.to_datetime(ks))
    o = pd.Series([bars[k][0] for k in ks]); h = pd.Series([bars[k][1] for k in ks])
    l = pd.Series([bars[k][2] for k in ks]); c = pd.Series([bars[k][3] for k in ks])
    v = pd.Series([bars[k][4] for k in ks])
    kw = dict(prev_close=PREV_CLOSE[t], atr=None, stale_print_atr=None, spike_atr=None)
    if filter_params:
        kw.update(filter_params)
    r = calculate_premarket_context(times, o, h, l, c, v, **kw)
    return {'pre_high': r['pre_high'], 'pre_low': r['pre_low'], 'pre_vwap': r['pre_vwap'],
            'bar_count': r['bar_count'], 'thin_excluded': r['thin']['bars_excluded'] if r['thin'] else None,
            'stale_close_reports': r['confirmed']['stale_close_reports'] if r['confirmed'] else None,
            'excluded_prior_close_prints': r['excluded_prior_close_prints'],
            'excluded_spike_prints': r['excluded_spike_prints'], 'reason': r['confirmed']['reason'] if r['confirmed'] else None}


def prior_close_prints(bars, pc, oc_only=True):
    """Bars where open or close (or, oc_only False, any price) is within 5 cents of the prior close,
    and every price of the bar not within 5 cents is more than 0.25 percent away, with at least one such price."""
    hits = []
    for k in sorted(bars):
        o, h, l, c, v = bars[k]
        near = [abs(x - pc) <= 0.05 + 1e-9 for x in (o, h, l, c)]
        trig = (near[0] or near[3]) if oc_only else any(near)
        if not trig:
            continue
        far = [x for x, n in zip((o, h, l, c), near) if not n]
        if far and all(abs(x - pc) / pc > 0.0025 for x in far):
            hits.append(k)
    return hits


def main():
    report = {}
    for t in ('SPY', 'QQQ', 'IWM'):
        srcs = {'av': load_av(t), 'st': load_st(t), 'wb': load_wb(t)}
        sets = {s: set(b) for s, b in srcs.items()}
        common = sorted(sets['av'] & sets['st'] & sets['wb'])
        cut = datetime.fromisoformat(BRIEF[t]['fetched_at']).astimezone(UTC)
        cut_min = cut.replace(second=0, microsecond=0)  # bars stamped before this minute
        rep = {
            'bars': {s: len(b) for s, b in srcs.items()},
            'bars_to_cutoff': {s: sum(1 for k in b if k < cut_min) for s, b in srcs.items()},
            'only': {
                'av_not_st': len(sets['av'] - sets['st']), 'st_not_av': len(sets['st'] - sets['av']),
                'av_not_wb': len(sets['av'] - sets['wb']), 'wb_not_av': len(sets['wb'] - sets['av']),
                'st_not_wb': len(sets['st'] - sets['wb']), 'wb_not_st': len(sets['wb'] - sets['st']),
            },
            'only_lists': {
                'wb_not_av': [et(k) for k in sorted(sets['wb'] - sets['av'])],
                'wb_not_st': [et(k) for k in sorted(sets['wb'] - sets['st'])],
                'st_not_av': [et(k) for k in sorted(sets['st'] - sets['av'])],
                'av_not_st': [et(k) for k in sorted(sets['av'] - sets['st'])],
            },
            'common_all3': len(common),
            'alignment_close_agree(shift: agree, n)': {
                'wb_vs_st': alignment(srcs['wb'], srcs['st']), 'wb_vs_av': alignment(srcs['wb'], srcs['av'])},
            'agreement_common_all3': agreement(srcs, common),
            'volume_common_all3': vol_ratios(srcs, common),
            'cutoff_utc': cut.isoformat(), 'cutoff_bars_before': cut_min.isoformat(),
            'brief_recorded': {k: BRIEF[t][k] for k in ('pre_high', 'pre_low', 'pre_vwap', 'excluded_stale_prints', 'excluded_spikes')},
        }
        rep['hl'] = {}
        fp = BRIEF[t]['pre_filter_params']
        filt = dict(atr=fp['atr'], stale_print_atr=fp['pm_stale_print_atr']['value'], spike_atr=fp['pm_spike_atr']['value'])
        for s, b in srcs.items():
            rep['hl'][s] = {
                'raw_full': raw_hl(b), 'raw_cutoff': raw_hl(b, cut_min),
                'rules_full': ctx(b, t), 'rules_cutoff': ctx(b, t, cut_min),
                'rules_plus_filter_cutoff': ctx(b, t, cut_min, filt),
                'rules_plus_filter_full': ctx(b, t, None, filt),
            }
        # cutoff check: does the in-session AV read reproduce the brief's recorded VWAP with the brief's filter?
        rep['cutoff_check'] = {}
        for label, cm in (('before_cut_minute', cut_min), ('through_cut_minute', cut_min + timedelta(minutes=1)),
                          ('before_prev_minute', cut_min - timedelta(minutes=1))):
            for s in ('av', 'st', 'wb'):
                rep['cutoff_check'][f'{s}_{label}'] = ctx(srcs[s], t, cm, filt)['pre_vwap']
        pc = PREV_CLOSE[t]
        rep['prior_close_prints_oc'] = {s: [et(k) for k in prior_close_prints(b, pc)] for s, b in srcs.items()}
        rep['prior_close_prints_any'] = {s: [et(k) for k in prior_close_prints(b, pc, oc_only=False)] for s, b in srcs.items()}
        rep['one_share_bars'] = {s: sum(1 for k in b if b[k][4] == 1) for s, b in srcs.items()}
        rep['under_100_bars'] = {s: sum(1 for k in b if b[k][4] < 100) for s, b in srcs.items()}
        rep['total_volume'] = {s: int(sum(x[4] for x in b.values())) for s, b in srcs.items()}
        report[t] = rep
        # minute dumps used in the issue tables
        dumps = {}
        for k in ([datetime(2026, 11, 16, 13, 5, tzinfo=UTC)] if t == 'IWM' else []) + \
                 ([datetime(2026, 11, 16, 12, m, tzinfo=UTC) for m in range(35, 44)] if t == 'QQQ' else []):
            dumps[et(k)] = {s: srcs[s].get(k) for s in srcs}
        report[t]['minutes'] = dumps
    # QQQ fourth read: AV about 17:05 ET
    q4 = load_av('QQQ', f'{S}/av1116/QQQ_close.csv')
    st = load_st('QQQ'); av = load_av('QQQ')
    ks = sorted(set(q4) & set(st))
    report['QQQ_av_1705_read'] = {
        'bars': len(q4), 'common_with_stored': len(ks),
        'all4_cent_agree_with_stored': sum(all(same_cent(q4[k][i], st[k][i]) for i in range(4)) for k in ks),
        'volume_equal_stored': sum(q4[k][4] == st[k][4] for k in ks),
        'all4_cent_agree_with_insession': sum(all(same_cent(q4[k][i], av[k][i]) for i in range(4)) for k in sorted(set(q4) & set(av))),
        'volume_equal_insession': sum(q4[k][4] == av[k][4] for k in sorted(set(q4) & set(av))),
        'common_with_insession': len(set(q4) & set(av)),
    }
    json.dump(report, open(f'{D}/compare_report.json', 'w'), indent=1, default=str)
    print(json.dumps(report, indent=1, default=str))


if __name__ == '__main__':
    main()
