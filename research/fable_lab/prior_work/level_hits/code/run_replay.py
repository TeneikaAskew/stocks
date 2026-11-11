"""Rebuild the 08:30 ET brief for every session with the repo's own code (read only worktree).
Usage: run_replay.py <worktree> <outdir> [START=2025-03-03] [END=2026-11-10]
Needs: /home/claude/venv/bin/python (the repo's venv), bars in bars_raw. Writes <outdir>/main0830_<day>.json."""
import sys, subprocess, os, json
from concurrent.futures import ThreadPoolExecutor
wt, out = sys.argv[1:3]
START = sys.argv[3] if len(sys.argv) > 3 else '2025-03-03'
END = sys.argv[4] if len(sys.argv) > 4 else '2026-11-10'
HERE = os.path.dirname(os.path.abspath(__file__))
B = '/mnt/project-files/stocks-scorecard/inputs/bars_raw'
raw = json.load(open(f'{wt}/tests/fixtures/strat_levels_2026-11-06_daily.json'))
days = sorted(r[0] for r in raw['tickers']['SPY'])
days = [d for d in days if d >= '2025-02-01'] + ['2026-11-09', '2026-11-10']
pairs = [(p, s) for p, s in zip(days[:-1], days[1:]) if START <= s <= END]
os.makedirs(out, exist_ok=True)
def run(ps):
    p, s = ps
    o = f'{out}/main0830_{s}.json'
    if os.path.exists(o):
        return s, 0
    r = subprocess.run(['/home/claude/venv/bin/python', f'{HERE}/replay_day.py', s, p, '08:30', B, o], cwd=wt,
                       env=dict(os.environ, PYTHONPATH='platform:.'), capture_output=True, text=True, timeout=900)
    if r.returncode:
        open(o + '.err', 'w').write(r.stdout[-3000:] + r.stderr[-5000:])
    return s, r.returncode
with ThreadPoolExecutor(6) as ex:
    res = list(ex.map(run, pairs))
bad = [s for s, c in res if c]
print(len(res), 'sessions', len(bad), 'failed', bad[:10])
