"""What production actually did on one session (default 2026-11-10), for
the day's evaluation. READ-ONLY: every database read goes through
scripts/db_query_cr.sh WITHOUT --commit (each run rolls back); the gcloud
calls only describe and list. Nothing is written to any table, nothing is
deployed, nothing posts. Results land in results/live_<day>/.

Usage (from the root of a stocks clone, as for run_all.sh):
  python3 /tmp/strat-params/harness/strat-params/live_day.py 2026-11-10
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_minutes import fetch, run  # noqa: E402

import datetime as _dt
DAY = sys.argv[1] if len(sys.argv) > 1 else "2026-11-10"
_d = _dt.date.fromisoformat(DAY)
PREV = (_d - _dt.timedelta(days=1)).isoformat()
NEXT = (_d + _dt.timedelta(days=1)).isoformat()
WEEK_BEFORE = (_d - _dt.timedelta(days=8)).isoformat()
T = "('SPY', 'QQQ', 'IWM')"
BIG = "- 'llm_overview' - 'llm_analysis' - 'llm_orb_explanation' - 'playbook'"
QUERIES = {
    # the brief's stored rows: levels, direction inputs, continuity, freshness
    "brief": f"SELECT p.ticker, p.analysis_ts, (to_jsonb(p) {BIG} - 'llm_playbook')::text AS row "
             f"FROM premarket_analysis p WHERE p.analysis_date = DATE '{DAY}' ORDER BY p.ticker",
    "brief_playbook": f"SELECT ticker, llm_playbook FROM premarket_analysis "
                      f"WHERE analysis_date = DATE '{DAY}' ORDER BY ticker",
    "brief_history": f"SELECT h.ticker, h.written_at, (to_jsonb(h) {BIG} - 'llm_playbook')::text AS row "
                     f"FROM premarket_analysis_history h WHERE h.analysis_date = DATE '{DAY}' "
                     f"ORDER BY h.ticker, h.written_at",
    "alerts": f"SELECT a.ticker, a.alert_ts, to_jsonb(a)::text AS row FROM signal_alerts a "
              f"WHERE a.alert_date = DATE '{DAY}' ORDER BY a.alert_ts",
    "strat_levels": f"SELECT s.ticker, s.as_of, to_jsonb(s)::text AS row FROM strat_levels s "
                    f"WHERE s.ticker IN {T} AND s.as_of >= TIMESTAMPTZ '{PREV} 00:00+00' "
                    f"AND s.as_of < TIMESTAMPTZ '{NEXT} 00:00+00' ORDER BY s.ticker, s.as_of, s.level_name",
    "daily": f"SELECT d.ticker, d.date, to_jsonb(d)::text AS row FROM market_data_daily d "
             f"WHERE d.ticker IN {T} AND d.date BETWEEN DATE '{WEEK_BEFORE}' AND DATE '{NEXT}' "
             f"ORDER BY d.ticker, d.date",
    "minutes": f"SELECT ticker, ts, open, high, low, close, volume FROM market_data_intraday "
               f"WHERE interval = '1min' AND ticker IN {T} AND ts >= TIMESTAMPTZ '{DAY} 09:00+00' "
               f"AND ts < TIMESTAMPTZ '{NEXT} 01:00+00' ORDER BY ticker, ts",
}
JOBS = ("premarket-brief", "signal-monitor", "signal-monitor-eod-resolver")


def sh(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return f"$ {' '.join(cmd)}\n{r.stdout}{r.stderr}\n"


def main() -> None:
    out = Path(__file__).resolve().parent / "results" / f"live_{DAY}"
    out.mkdir(parents=True, exist_ok=True)
    region = ["--region", "us-east1"]
    text = []
    for job in JOBS:
        desc = sh(["gcloud", "run", "jobs", "describe", job, *region])
        text.append(desc)
        # when the pinned image was built: upload time of the digest the job runs
        for ref in sorted({w for w in desc.split() if "docker.pkg.dev" in w and "@sha256:" in w}):
            text.append(sh(["gcloud", "artifacts", "docker", "images", "describe", ref]))
        text.append(sh(["gcloud", "run", "jobs", "executions", "list", "--job", job, *region,
                        "--limit", "12"]))
    (out / "jobs.txt").write_text("".join(text))
    for name, sql in QUERIES.items():
        prefix = run(sql, out)
        try:
            fetch(prefix, "result_001.csv", out / f"{name}.csv")
        except subprocess.CalledProcessError:
            # a query with 0 rows writes no result file (the day's minutes
            # land with the 23:00 ET fetch); keep going with an empty table
            (out / f"{name}.csv").write_text("")
            print(name, "0 rows (no result file)", file=sys.stderr, flush=True)
            continue
        print(name, "ok", file=sys.stderr, flush=True)
    shutil.rmtree(out / "parts", ignore_errors=True)
    (out / "last_run.err").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
