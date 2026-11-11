"""Replay every session START..END at one cutoff with that session's own
params file (per-day params, no lookahead: each file holds rows effective
that session, calibrated from bars before it).
Usage: run_basis.py <worktree> <params_dir> <label> <cutoff HH:MM> <outdir>
(env START, END; session list as run_hist.py: fixture days plus Nov 9, 10)"""
import sys, subprocess, os
from concurrent.futures import ThreadPoolExecutor
wt, pdir, label, cut, out = sys.argv[1:6]
sys.path.insert(0, wt)
import tests.lib.strat_2026_11_06 as fx
days = sorted(r[0] for r in fx._raw()['tickers']['SPY'])
START, END = os.environ.get('START', '2026-05-01'), os.environ.get('END', '2026-11-10')
days = [d for d in days if d >= '2025-02-01'] + ['2026-11-09', '2026-11-10']
pairs = [(p, s) for p, s in zip(days[:-1], days[1:]) if START <= s <= END]
B = '/mnt/project-files/stocks-scorecard/inputs/bars_raw'
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'replay_basis.py')
os.makedirs(out, exist_ok=True)
def run(ps):
    p, s = ps
    o = f'{out}/{label}{cut.replace(":", "")}_{s}.json'
    pj = f'{pdir}/params_{s}.json'
    if os.path.exists(o):
        return s, 0
    if not os.path.exists(pj):
        open(o + '.err', 'w').write(f'no params file {pj}'); return s, 2
    r = subprocess.run(['/home/claude/venv/bin/python', R, s, p, cut, B, o, pj], cwd=wt,
                       env=dict(os.environ, PYTHONPATH='platform:.'), capture_output=True, text=True, timeout=900)
    if r.returncode:
        open(o + '.err', 'w').write(r.stdout[-3000:] + r.stderr[-5000:])
    return s, r.returncode
with ThreadPoolExecutor(int(os.environ.get('JOBS', '4'))) as ex:
    res = list(ex.map(run, pairs))
bad = [s for s, c in res if c]
print(label, cut, len(res), 'sessions', len(bad), 'failed', bad[:10])
