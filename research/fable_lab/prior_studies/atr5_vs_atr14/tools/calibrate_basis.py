"""History-mode calibration of one ticker in one ATR basis, offline, with the
#1784 job's own logic (gcp.calibrate_level_params.run: policy_on with
atr_basis override, window_policy_resolver, lib.level_calibration
HistoryCalibrator, to_rows), fed from local files instead of Cloud SQL.
Effective dates: every session from START to END (each from bars strictly
before it). Writes <out>/rows_{T}_{basis}.csv.gz.
Usage (cwd = #1784 worktree, PYTHONPATH=platform:.):
  calibrate_basis.py <daily_dir> <out_dir> <ticker> <atr_14|atr_5> [START END]"""
import sys, os, glob, time, json
from pathlib import Path
import pandas as pd
from gcp import calibrate_level_params as job
from lib import level_calibration as lc
from tests.lib.level_params_fixtures import ParamsDb

daily_dir, out, T, basis = sys.argv[1:5]
START, END = (sys.argv[5:7] + ['2025-03-03', '2026-11-10'][len(sys.argv[5:7]):])[:2]
out = Path(out); out.mkdir(parents=True, exist_ok=True)
BARS = '/mnt/project-files/stocks-scorecard/inputs/bars_raw'
daily = pd.read_csv(f'{daily_dir}/daily_{T}.csv', parse_dates=['date'])
minutes = pd.concat([pd.read_csv(p, parse_dates=['timestamp']) for p in sorted(glob.glob(f'{BARS}/{T}_1min_*.csv'))])
minutes = minutes.drop_duplicates('timestamp').sort_values('timestamp').reset_index(drop=True)
# sessions: the daily index from START, plus END when it is past the last daily bar
dates = [d for d in daily.date if pd.Timestamp(START) <= d <= pd.Timestamp(END)]
if pd.Timestamp(END) > daily.date.max():
    dates.append(pd.Timestamp(END))
dates = sorted(set(pd.Timestamp(d).normalize() for d in dates))
pdb = ParamsDb()
policy_rows = pdb.query("SELECT * FROM level_param_policy").to_dict('records')
# Optional deviation for the holdout (env MIN_SAMPLE_BREAK=N): the minimum
# sample of every break-derived key (entry buffers, stops, min stop, targets)
# set to N, because the one-minute history starts 2025-03-03 and the policy
# minimum of 150 breaks is not reached until 2025-09 (entries) or 2026-05
# (stops, targets). Applied to both bases alike; no lookahead.
MSB = os.environ.get('MIN_SAMPLE_BREAK')
if MSB:
    for r in policy_rows:
        if r['param_key'].startswith(('entry_buffer_', 'stop_', 'min_stop', 'target_')):
            r['min_sample'] = int(MSB)
policies = {eff: job.policy_on(policy_rows, eff, atr_basis=basis) for eff in dates}
unique = []
for p in policies.values():
    if p not in unique:
        unique.append(p)
resolvers = [job.window_policy_resolver(policy_rows, p) for p in unique]
window_at = {eff: resolvers[unique.index(policies[eff])] for eff in dates}
t0 = time.time()
hc = lc.HistoryCalibrator(T, daily, minutes, dates[-1])
rows = []
for i, eff in enumerate(dates):
    pol = policies[eff]
    rows.extend(lc.to_rows(T, hc.calibrate(pol, eff, window_at[eff]), pol, eff, f'offline-{basis}', 'history', None))
    if i % 50 == 0:
        print(T, basis, eff.date(), f'{time.time() - t0:.0f}s', flush=True)
df = pd.DataFrame(rows)
df.to_csv(out / f'rows_{T}_{basis}.csv.gz', index=False)
print(T, basis, len(dates), 'dates', len(df), 'rows', df.status.value_counts().to_dict(), f'{time.time() - t0:.0f}s')
