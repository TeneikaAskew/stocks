"""Daily inputs for the ATR5 vs ATR14 calibration experiment, plus the
consistency checks. Writes <out>/daily_{T}.csv with date, open, high, low,
close (unadjusted, as traded), atr_14, atr_5 (lib.indicators.calculate_atr,
Wilder) and sma_200, the columns gcp/calibrate_level_params.py reads from
market_data_daily.
Usage (cwd = #1784 worktree, PYTHONPATH=platform:.): prep_data.py <out_dir>"""
import sys, json, glob
from pathlib import Path
import pandas as pd
from lib.indicators import calculate_atr

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
RAW = '/mnt/project-files/strat-verify/ftfc-replay/raw'
BARS = '/mnt/project-files/stocks-scorecard/inputs/bars_raw'
fx = json.loads(Path('tests/fixtures/strat_levels_2026-11-06_daily.json').read_text())
# Monday 2026-11-09 bar, the same values replay_day.py appends (AV TIME_SERIES_DAILY, unadjusted)
NOV9 = {"SPY": ["2026-11-09", 741.95, 755.42, 741.025, 752.69, 50281221],
        "QQQ": ["2026-11-09", 662.64, 682.48, 662.02, 679.35, 53587228],
        "IWM": ["2026-11-09", 277.44, 283.79, 276.81, 282.51, 28942482]}
checks = {}
for t in ('SPY', 'QQQ', 'IWM'):
    a = pd.read_csv(f'{RAW}/{t}_daily_adjusted.csv', parse_dates=['timestamp']).sort_values('timestamp')
    a = a.rename(columns={'timestamp': 'date'}).set_index('date')
    f = pd.DataFrame(fx['tickers'][t] + [NOV9[t]], columns=fx['columns'])
    f['date'] = pd.to_datetime(f['date']); f = f.set_index('date')
    ov = a.index.intersection(f.index)
    c = {'fixture_overlap_days': len(ov),
         'fixture_max_abs_diff': float(max((a.loc[ov, k] - f.loc[ov, k]).abs().max() for k in ('open', 'high', 'low', 'close'))),
         'adjusted_vs_raw_close_max_pct_since_2023': float(((a.adjusted_close / a.close - 1).abs()[a.index >= '2023-01-01']).max() * 100)}
    # 1-min RTH aggregates vs daily close/high/low (unadjusted both)
    m = pd.concat([pd.read_csv(p, parse_dates=['timestamp']) for p in sorted(glob.glob(f'{BARS}/{t}_1min_*.csv'))])
    m = m.drop_duplicates('timestamp').set_index('timestamp').sort_index()
    r = m.between_time('09:30', '15:59')
    g = r.groupby(r.index.normalize()).agg(high=('high', 'max'), low=('low', 'min'), close=('close', 'last'), n=('close', 'size'))
    g = g[g.n >= 300]
    ov2 = g.index.intersection(a.index)
    rel = lambda k: ((g.loc[ov2, k] / a.loc[ov2, k] - 1).abs() * 100)
    c.update({'minute_overlap_days': len(ov2), 'minute_close_err_pct_median': float(rel('close').median()),
              'minute_close_err_pct_max': float(rel('close').max()), 'minute_high_err_pct_p95': float(rel('high').quantile(.95)),
              'minute_low_err_pct_p95': float(rel('low').quantile(.95))})
    # adjusted file through 2026-11-04, then the fixture rows (Nov 5, 6) and Nov 9
    d = pd.concat([a[['open', 'high', 'low', 'close']], f.loc[f.index > a.index.max(), ['open', 'high', 'low', 'close']]]).sort_index()
    d = d[~d.index.duplicated(keep='first')]
    d['atr_14'] = calculate_atr(d.high, d.low, d.close, 14)
    d['atr_5'] = calculate_atr(d.high, d.low, d.close, 5)
    d['sma_200'] = d.close.rolling(200).mean()
    d = d[d.index >= '2015-01-01']
    d.reset_index().to_csv(OUT / f'daily_{t}.csv', index=False)
    c['daily_rows'] = len(d); c['daily_first'] = str(d.index.min().date()); c['daily_last'] = str(d.index.max().date())
    checks[t] = c
(OUT / 'data_checks.json').write_text(json.dumps(checks, indent=1))
print(json.dumps(checks, indent=1))
