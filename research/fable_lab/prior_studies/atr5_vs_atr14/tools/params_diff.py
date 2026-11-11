"""Calibrated parameters in points (value x the basis ATR of the prior
session) per basis, and their paired change, per ticker and window.
Usage: params_diff.py <work dir> <out_dir>"""
import sys, glob, json
from pathlib import Path
import pandas as pd
W, out = Path(sys.argv[1]), Path(sys.argv[2])
KEYS = ['trigger_window_long_atr', 'trigger_window_short_atr', 'level_cluster_atr', 'pm_spike_atr',
        'entry_buffer_neutral_hi_atr', 'stop_neutral_atr', 'min_stop_atr', 'target_neutral_1_r']
res = {}
for calib, label, lo, hi in (('calib', 'recent', '2026-05-01', '2026-11-10'), ('calib40', 'holdout_minsample40', '2025-03-03', '2026-04-30')):
    df = pd.concat([pd.read_csv(p) for p in glob.glob(f'{W}/{calib}/rows_*.csv.gz')])
    df = df[(df.effective_from >= lo) & (df.effective_from <= hi)]
    for t in ('SPY', 'QQQ', 'IWM'):
        d = pd.read_csv(f'{W}/daily/daily_{t}.csv', parse_dates=['date']).set_index('date')
        prior = d[['atr_14', 'atr_5']].shift(0)
        x = df[df.ticker == t].pivot_table(index=['effective_from', 'param_key'], columns='atr_basis', values='value').reset_index()
        def atr_before(day, col):
            s = d[d.index < pd.Timestamp(day)][col]; return float(s.iloc[-1])
        days = sorted(x.effective_from.unique())
        atrs = {day: (atr_before(day, 'atr_14'), atr_before(day, 'atr_5')) for day in days}
        o = {}
        for k in KEYS:
            y = x[x.param_key == k].dropna()
            if k.endswith('_r'):
                o[k] = dict(n=len(y), median_atr14_R=round(y.atr_14.median(), 3), median_atr5_R=round(y.atr_5.median(), 3))
                continue
            p14 = y.apply(lambda r: r.atr_14 * atrs[r.effective_from][0], axis=1)
            p5 = y.apply(lambda r: r.atr_5 * atrs[r.effective_from][1], axis=1)
            o[k] = dict(n=len(y), median_value_atr14=round(y.atr_14.median(), 3), median_value_atr5=round(y.atr_5.median(), 3),
                        median_pts_atr14=round(p14.median(), 3), median_pts_atr5=round(p5.median(), 3),
                        median_abs_pts_change=round((p5 - p14).abs().median(), 3),
                        p10_p90_pts_change=[round((p5 - p14).quantile(q), 3) for q in (.1, .9)])
        r = pd.Series({day: atrs[day][1] / atrs[day][0] for day in days})
        o['atr5_over_atr14'] = dict(median=round(r.median(), 3), p10=round(r.quantile(.1), 3), p90=round(r.quantile(.9), 3))
        res.setdefault(label, {})[t] = o
(out / 'params_points.json').write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
