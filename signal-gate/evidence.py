"""Live evidence for the intraday alert gate question (FEAT-SIGNAL-001).

READ-ONLY. Every database read goes through scripts/db_query_cr.sh WITHOUT
--commit (each run rolls back). The gcloud calls only read logs. Nothing is
written to any table, nothing is deployed, nothing posts. Results land in
signal-gate/results/.

Pulls:
  alerts.csv    every live signal_alerts row for SPY, QQQ, IWM since 2026-05-01
  brief.csv     the live premarket_analysis direction inputs for the same days
  insight.csv   the live insight_reports direction rows for the same days
  gate_log.txt  signal-monitor log lines from the direction, level and RVOL
                gates on 2026-11-09 (the gate decision is not persisted)

Usage, from the root of a stocks clone on this branch:
  python3 signal-gate/evidence.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SINCE = "2026-05-01"
T = "('SPY', 'QQQ', 'IWM')"
QUERIES = {
    "alerts": (
        "SELECT a.id, a.alert_date, a.alert_ts, a.ticker, a.direction, a.strength_label, "
        "a.base_score, a.total_score, a.strat_bonus, a.price_at_signal, a.brief_bias, "
        "a.brief_alignment, a.brief_setup_count, a.level_state, a.opp_level_state, "
        "a.rvol_gate, a.rvol_mod, a.timeframe_tag, a.expected_hold_min, a.fire_seq, "
        "a.exit_ts, a.exit_reason, a.exit_price, a.exit_return_pct, a.target_price, "
        "a.conditions_met::text AS conditions_met "
        f"FROM signal_alerts a WHERE a.ticker IN {T} AND a.alert_date >= DATE '{SINCE}' "
        "AND a.run_kind = 'live' AND a.replay_id IS NULL ORDER BY a.alert_ts"),
    "brief": (
        "SELECT ticker, analysis_date, analysis_ts, signal_status, ftfc_direction, ftfc_score, "
        "calls_trigger_price, calls_t1_price, calls_stop_price, "
        "puts_trigger_price, puts_t1_price, puts_stop_price "
        f"FROM premarket_analysis WHERE ticker IN {T} AND analysis_date >= DATE '{SINCE}' "
        "AND run_kind = 'live' ORDER BY analysis_date, ticker"),
    "insight": (
        "SELECT ticker, as_of, created_at, report->>'direction' AS direction, "
        "report->>'conviction' AS conviction, report->>'regime' AS regime, "
        "report->>'invalidation_level' AS invalidation_level "
        f"FROM insight_reports WHERE ticker IN {T} AND as_of >= TIMESTAMPTZ '{SINCE} 00:00+00' "
        "AND run_kind = 'live' ORDER BY as_of, ticker"),
}
LOG_FILTER = (
    'resource.type="cloud_run_job" AND resource.labels.job_name="signal-monitor" '
    'AND timestamp>="2026-11-09T13:00:00Z" AND timestamp<"2026-11-09T21:30:00Z" '
    'AND (textPayload:"direction gate" OR textPayload:"InsightCache" '
    'OR textPayload:"level_gate" OR textPayload:"rvol_gate" OR textPayload:"SUPPRESSED" '
    'OR textPayload:"DOWNGRADED")')


def run(sql: str, out: Path) -> str:
    """One read-only db-query run (no --commit, so it rolls back); returns its GCS prefix."""
    res = subprocess.run(["./scripts/db_query_cr.sh", "--timeout", "600", "--wait-timeout", "1200",
                          "-q", sql], capture_output=True, text=True)
    (out / "last_run.err").write_text(res.stderr)
    m = re.search(r"gs://\S+/query-results/\S+", res.stdout + res.stderr)
    if res.returncode != 0 or not m:
        raise SystemExit(f"db-query run failed (exit {res.returncode}); see {out / 'last_run.err'}\n"
                         + res.stderr[-2000:])
    return m.group(0).rstrip("/").rsplit("/summary", 1)[0]


def fetch(prefix: str, name: str, dest: Path) -> None:
    subprocess.run(["gcloud", "storage", "cp", f"{prefix}/{name}", str(dest)], check=True,
                   capture_output=True)


def main() -> None:
    out = Path(__file__).resolve().parent / "results"
    out.mkdir(parents=True, exist_ok=True)
    for name, sql in QUERIES.items():
        prefix = run(sql, out)
        fetch(prefix, "result_001.csv", out / f"{name}.csv")
        rows = sum(1 for _ in open(out / f"{name}.csv")) - 1
        print(name, "ok", rows, "rows", file=sys.stderr, flush=True)
    logs = subprocess.run(["gcloud", "logging", "read", LOG_FILTER, "--limit", "2000",
                           "--format", "value(timestamp,textPayload)"],
                          capture_output=True, text=True)
    (out / "gate_log.txt").write_text(logs.stdout + logs.stderr)
    print("gate_log ok", len(logs.stdout.splitlines()), "lines", file=sys.stderr, flush=True)
    (out / "last_run.err").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
