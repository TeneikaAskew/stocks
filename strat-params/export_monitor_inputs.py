"""Read-only export of what the signal monitor reads, so its own replay
harness (scripts/replay_signal_monitor.py) can run offline against a copy.
Every statement goes through scripts/db_query_cr.sh WITHOUT --commit, so
each run rolls back; nothing is written, deployed or posted. Each table is
exported as one JSON text column per row (to_jsonb), so the copy keeps
every column whatever the schema.  Results: results/monitor_inputs/<name>.csv

Usage (from the root of a stocks clone, as for run_all.sh):
  python3 /tmp/strat-params/harness/strat-params/export_monitor_inputs.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_minutes import fetch, run  # noqa: E402

T = "('SPY', 'QQQ', 'IWM')"
J = "SELECT to_jsonb(x)::text AS row FROM {table} x WHERE {where}"
QUERIES = {
    "premarket_analysis": J.format(table="premarket_analysis", where="x.analysis_date BETWEEN DATE '2026-10-26' AND DATE '2026-11-10'"),
    "premarket_analysis_history": J.format(table="premarket_analysis_history", where="x.analysis_date BETWEEN DATE '2026-10-26' AND DATE '2026-11-10'"),
    "strat_levels": J.format(table="strat_levels", where=f"x.ticker IN {T} AND x.as_of >= TIMESTAMPTZ '2026-10-29 00:00+00' AND x.as_of < TIMESTAMPTZ '2026-11-12 00:00+00'"),
    "insight_reports": J.format(table="insight_reports", where=f"x.ticker IN {T} AND x.as_of >= DATE '2026-10-26' AND x.as_of < DATE '2026-11-12'"),
    "economic_events": J.format(table="economic_events", where="x.event_date BETWEEN DATE '2026-10-20' AND DATE '2026-11-20'"),
    "earnings_calendar": J.format(table="earnings_calendar", where=f"x.ticker IN {T}"),
    "sec_filings": J.format(table="sec_filings", where=f"x.ticker IN {T} AND x.filing_date >= DATE '2026-10-01'"),
    "exit_config_overrides": J.format(table="exit_config_overrides", where=f"x.ticker IN {T}"),
    "ticker_calibration": J.format(table="ticker_calibration", where=f"x.ticker IN {T}"),
    "market_data_daily": J.format(table="market_data_daily", where=f"x.ticker IN {T} AND x.date >= DATE '2024-01-01'"),
}
# one-minute bars Oct 1 to Nov 10 (the RVOL baseline looks back 30 days), one
# statement per ticker and month, each well under db_query's 50,000-row cap
for t in ("SPY", "QQQ", "IWM"):
    for lo, hi in (("2026-10-01", "2026-11-01"), ("2026-11-01", "2026-11-12")):
        QUERIES[f"intraday_{t}_{lo[:7]}"] = (
            "SELECT ticker, interval, ts, open, high, low, close, volume, data_source "
            f"FROM market_data_intraday WHERE ticker = '{t}' AND interval = '1min' "
            f"AND ts >= TIMESTAMPTZ '{lo} 00:00+00' AND ts < TIMESTAMPTZ '{hi} 00:00+00' ORDER BY ts")


def main() -> None:
    out = Path(__file__).resolve().parent / "results" / "monitor_inputs"
    out.mkdir(parents=True, exist_ok=True)
    for name, sql in QUERIES.items():
        dest = out / f"{name}.csv"
        if dest.exists():
            continue
        prefix = run(sql, out)
        try:
            fetch(prefix, "result_001.csv", dest)
        except subprocess.CalledProcessError:
            dest.write_text("")  # 0 rows writes no result file
            print(name, "0 rows", file=sys.stderr, flush=True)
            continue
        print(name, "ok", file=sys.stderr, flush=True)
    (out / "last_run.err").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
