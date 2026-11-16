"""2026-11-16 from the local Alpha Vantage files, cut at 08:20 ET.
usage: item5.py <worktree> <bars_root> <daily_csv> <out_dir> X <av_dir>"""
import sys
import measure as M
from measure import *
AV = sys.argv[6]
PC = {'QQQ': 679.89, 'SPY': 754.37, 'IWM': 277.54}
d = pd.read_csv(DAILY, low_memory=False)
rows = []
for t, pc in PC.items():
    b = pd.read_csv(f'{AV}/{t}.csv', parse_dates=['timestamp']).sort_values('timestamp').reset_index(drop=True)
    p = json.loads(d[(d.ticker == t) & (d.date == '2026-11-16')].iloc[0].pfp_text)
    fk = dict(atr=p['atr'], stale_print_atr=p['pm_stale_print_atr']['value'], spike_atr=p['pm_spike_atr']['value'])
    for cut in ('08:20', '09:30'):
        g = b[(b.timestamp >= '2026-11-16 04:00') & (b.timestamp < f'2026-11-16 {cut}')].reset_index(drop=True)
        raw = {k: g[n].to_numpy(float) for k, n in (('o', 'open'), ('h', 'high'), ('l', 'low'), ('c', 'close'))}
        v = g.volume.to_numpy(float); pc_c = price_cents(pc); cents = {k: cents_arr(raw[k]) for k in 'ohlc'}
        kw = dict(times=g.timestamp, open_=g.open, high=g.high, low=g.low, close=g.close, volume=g.volume, prev_close=pc)
        for mode, fkw in (('filter_off', dict(atr=None, stale_print_atr=None, spike_atr=None)), ('filter_recorded', fk)):
            ship = cpc(**kw, **fkw)
            f = premarket_print_filter(*(pd.Series(raw[k]) for k in 'ohlc'), prev_close=pc, **fkw)
            fc = {'o': f['open'].to_numpy(), 'h': f['high'].to_numpy(), 'l': f['low'].to_numpy(), 'c': f['close'].to_numpy()}
            base = engine(raw, fc, v, pc, pc_c)
            assert (base[0], base[1]) == (ship['pre_high'], ship['pre_low']), (base, ship['pre_high'], ship['pre_low'])
            d1, _ = pc_drop(raw, cents, pc, pc_c, 0); d2, _ = pc_drop(raw, cents, pc, pc_c, 5); d4, _ = pc_drop_ctx(raw, cents, v, pc, pc_c, 5)
            d5 = median_drop(raw, v, 0.005); d5b = median_drop(raw, v, 0.0025)
            res = {'shipped': base,
                   'P1': engine(raw, fc, v, pc, pc_c, drop=d1), 'P2': engine(raw, fc, v, pc, pc_c, drop=d2),
                   'P3': engine(raw, fc, v, pc, pc_c, stale=False, body_ok=isolated_bodies(raw, v, D_FRAC)),
                   'P4': engine(raw, fc, v, pc, pc_c, drop=d4),
                   'P5_D0.25': engine(raw, fc, v, pc, pc_c, drop=d5b), 'P5_D0.50': engine(raw, fc, v, pc, pc_c, drop=d5),
                   'P2+P5_D0.50': engine(raw, fc, v, pc, pc_c, drop={k: d2[k] | d5[k] for k in 'ohlc'})}
            for name, e in res.items():
                def bd(s):
                    if s is None: return None
                    i, kind = s
                    return f"{g.timestamp.iloc[i].strftime('%H:%M')} {kind} o{raw['o'][i]} h{raw['h'][i]} l{raw['l'][i]} c{raw['c'][i]} v{int(v[i])}"
                rows.append({'ticker': t, 'cut': cut, 'mode': mode, 'bars': len(g), 'rule': name, 'pre_high': e[0], 'pre_low': e[1],
                             'high_set_by': bd(e[2]), 'low_set_by': bd(e[3])})
out = pd.DataFrame(rows); out.to_csv(f'{OUT}/item5_2026-11-16.csv', index=False)
pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 80)
print(out.to_string(index=False))
