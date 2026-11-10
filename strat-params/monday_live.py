"""What production actually did on Monday 2026-11-09, for the Monday
evaluation. READ-ONLY: every database read goes through
scripts/db_query_cr.sh WITHOUT --commit (each run rolls back); the gcloud
calls only describe and list. Nothing is written to any table, nothing is
deployed, nothing posts. Results land in results/monday_live/.

Usage (from the root of a stocks clone, as for run_all.sh):
  python3 /tmp/strat-params/harness/strat-params/monday_live.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_minutes import fetch, run  # noqa: E402

DAY = "2026-11-09"
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
                    f"WHERE s.ticker IN {T} AND s.as_of >= TIMESTAMPTZ '2026-11-08 00:00+00' "
                    f"AND s.as_of < TIMESTAMPTZ '2026-11-10 00:00+00' ORDER BY s.ticker, s.as_of, s.level_name",
    "daily": f"SELECT d.ticker, d.date, to_jsonb(d)::text AS row FROM market_data_daily d "
             f"WHERE d.ticker IN {T} AND d.date BETWEEN DATE '2026-11-02' AND DATE '2026-11-10' "
             f"ORDER BY d.ticker, d.date",
    "minutes": f"SELECT ticker, ts, open, high, low, close, volume FROM market_data_intraday "
               f"WHERE interval = '1min' AND ticker IN {T} AND ts >= TIMESTAMPTZ '{DAY} 09:00+00' "
               f"AND ts < TIMESTAMPTZ '2026-11-10 01:00+00' ORDER BY ticker, ts",
}
JOBS = ("premarket-brief", "signal-monitor", "signal-monitor-eod-resolver")


def sh(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return f"$ {' '.join(cmd)}\n{r.stdout}{r.stderr}\n"


def main() -> None:
    out = Path(__file__).resolve().parent / "results" / "monday_live"
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
        fetch(prefix, "result_001.csv", out / f"{name}.csv")
        print(name, "ok", file=sys.stderr, flush=True)
    shutil.rmtree(out / "parts", ignore_errors=True)
    (out / "last_run.err").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
