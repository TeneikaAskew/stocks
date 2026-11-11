"""Per-session params files (the replay_day.py format of params_run_84421818)
from calibrate_basis.py rows. Usage: make_params.py <calib_dir> <out_dir>
Writes <out_dir>/<basis>/params_<day>.json for each basis with rows."""
import sys, json, glob
from pathlib import Path
import pandas as pd
calib, out = Path(sys.argv[1]), Path(sys.argv[2])
df = pd.concat([pd.read_csv(p) for p in sorted(glob.glob(f'{calib}/rows_*_atr_*.csv.gz'))])
for (basis, day), g in df.groupby(['atr_basis', 'effective_from']):
    o = out / basis; o.mkdir(parents=True, exist_ok=True)
    tick = {}
    for r in g.to_dict('records'):
        tick.setdefault(r['ticker'], {})[r['param_key']] = {
            k: (None if (isinstance(r[k], float) and r[k] != r[k]) else r[k]) for k in
            ('value', 'status', 'atr_basis', 'method_id', 'policy_effective_from', 'sample_n',
             'input_from', 'input_to', 'effective_from', 'run_id', 'source')}
        tick[r['ticker']][r['param_key']]['sample_n'] = int(r['sample_n']) if r['sample_n'] == r['sample_n'] else None
    (o / f'params_{day}.json').write_text(json.dumps(
        {'description': f'offline calibration, {basis}', 'session': day, 'atr_basis': basis, 'tickers': tick}, indent=1))
print(df.groupby(['atr_basis', 'ticker', 'status']).size())
