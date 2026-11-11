"""Replay the signal monitor on given sessions for given commits, with the
repo's own harness (scripts/replay_signal_monitor.py, CLAUDE.md 3.6), and
keep every fire it would have sent. Nothing is written: the harness mocks
Discord and the database writes, and this wrapper also puts every
database session in READ ONLY mode (sitecustomize patch on
sqlalchemy.create_engine), checks that it is on before replaying, and
leaves REPLAY_PERSIST unset. Results: results/alerts_replay/<sha>_<day>.json

Usage (from the root of a stocks clone, as for run_all.sh):
  python3 /tmp/strat-params/harness/strat-params/alerts_replay.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SHAS = {"live_monitor": "11135c4d", "main": "d7a0100e"}
DAYS = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06",
        "2026-11-09", "2026-11-10"]
ROOT = Path("/tmp/strat-params")
GUARD = ROOT / "ro_guard"
OUT = Path(__file__).resolve().parent / "results" / "alerts_replay"

SITECUSTOMIZE = '''
import sqlalchemy
from sqlalchemy import event
_orig_create_engine = sqlalchemy.create_engine
def _read_only_engine(*a, **k):
    eng = _orig_create_engine(*a, **k)
    @event.listens_for(eng, "connect")
    def _ro(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        cur.close()
        dbapi_conn.commit()
    return eng
sqlalchemy.create_engine = _read_only_engine
'''

PROBE = ("from gcp.database import get_engine\n"
         "from sqlalchemy import text\n"
         "with get_engine().connect() as c:\n"
         "    print('transaction_read_only=' + str(c.execute(text('SHOW transaction_read_only')).scalar()))\n")


def env_for(wt: Path) -> dict:
    env = dict(os.environ)
    env.pop("REPLAY_PERSIST", None)
    env["PYTHONPATH"] = f"{GUARD}:{wt}" + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def main() -> None:
    repo = Path.cwd()
    GUARD.mkdir(parents=True, exist_ok=True)
    (GUARD / "sitecustomize.py").write_text(SITECUSTOMIZE)
    OUT.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "fetch", "origin", "main"], cwd=repo, check=True)
    for label, sha in SHAS.items():
        wt = ROOT / f"mon_{sha}"
        if not wt.exists():
            subprocess.run(["git", "worktree", "add", "--detach", str(wt), sha], cwd=repo, check=True)
        probe = subprocess.run([sys.executable, "-c", PROBE], cwd=wt, env=env_for(wt),
                               capture_output=True, text=True)
        if "transaction_read_only=on" not in probe.stdout:
            sys.exit(f"read-only guard not active for {sha}; nothing replayed\n{probe.stdout}{probe.stderr[-2000:]}")
        print(label, sha, probe.stdout.strip(), file=sys.stderr, flush=True)
        for day in DAYS:
            r = subprocess.run([sys.executable, "-m", "scripts.replay_signal_monitor", "--date", day,
                                "--tickers", "SPY,QQQ,IWM", "--json"],
                               cwd=wt, env=env_for(wt), capture_output=True, text=True)
            (OUT / f"{sha}_{day}.log").write_text(r.stderr[-200000:])
            out = r.stdout
            fires = []
            if "\n[" in out:
                fires = json.loads(out[out.index("\n[") + 1:])
            (OUT / f"{sha}_{day}.json").write_text(json.dumps(
                {"label": label, "sha": sha, "day": day, "exit": r.returncode,
                 "summary": out[: out.index("\n[")] if "\n[" in out else out[-20000:], "fires": fires}, indent=1))
            print(label, day, "exit", r.returncode, "fires", len(fires), file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
