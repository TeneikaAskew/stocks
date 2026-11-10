"""History-mode calibration for SPY, QQQ and IWM through the job's own run(),
with its two reads answered from the exports and its writes collected to a
file instead of ticker_level_params. Same code path as
`python3 -m gcp.calibrate_level_params --tickers SPY,QQQ,IWM --history
2015-01-02 2026-11-06`, minus the database.

Usage (run from a #1766 worktree):
  PYTHONPATH=platform:. python3 <this dir>/calib.py <daily.csv> <minutes_dir> <out_dir>
minutes_dir holds spy.csv, qqq.csv, iwm.csv (the export_minutes_* results).
Writes out_dir/ticker_level_params.csv.gz (every row the job wrote) and
out_dir/in_force_2026-11-06.json (per ticker, the row in force on that
session for every key, with run_id and input range).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

from gcp import calibrate_level_params as job  # noqa: E402


def main(daily_csv: Path, minutes_dir: Path, out_dir: Path, start: str = "2015-01-02") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    export = common.load_daily_export(daily_csv)
    daily = {t: common.daily_for_job(export, t) for t in common.TICKERS}
    minutes = {t: common.load_minutes(minutes_dir / f"{t.lower()}.csv") for t in common.TICKERS}
    for t in common.TICKERS:
        print(t, "daily", len(daily[t]), daily[t]["date"].min(), daily[t]["date"].max(),
              "minutes", len(minutes[t]), minutes[t]["ts"].min(), minutes[t]["ts"].max(),
              file=sys.stderr, flush=True)
    rows: list[dict] = []

    def write(batch):
        rows.extend(batch)
        return len(batch)

    dates = job.history_sessions(start, common.AS_OF)
    t0 = time.time()
    res = job.run(list(common.TICKERS), dates, query=common.make_query(daily, minutes), write=write,
                  policy_rows=common.policy_rows(), source="history",
                  chunk_sessions=job.HISTORY_CHUNK_SESSIONS)
    print(f"run {res.run_id}: {res.rows_written} rows, ok {res.succeeded}, failed {res.failed},"
          f" {time.time() - t0:.0f} s", file=sys.stderr, flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "ticker_level_params.csv.gz", index=False)

    session = pd.Timestamp(common.AS_OF).date()
    in_force = {}
    for t in common.TICKERS:
        x = df[(df["ticker"] == t)].copy()
        x["eff"] = pd.to_datetime(x["effective_from"]).dt.date
        x = x[x["eff"] <= session].sort_values("eff").groupby("param_key").tail(1)
        in_force[t] = {r["param_key"]: {k: (None if pd.isna(r[k]) else
                                            (r[k] if not hasattr(r[k], "isoformat") else r[k].isoformat()))
                                        for k in ("value", "status", "atr_basis", "method_id",
                                                  "policy_effective_from", "sample_n", "input_from",
                                                  "input_to", "effective_from", "run_id", "source")}
                       for r in x.to_dict("records")}
    (out_dir / f"in_force_{common.AS_OF}.json").write_text(json.dumps(
        {"run_id": res.run_id, "rows_written": res.rows_written, "failed": res.failed,
         "tickers": in_force}, indent=1, default=str))
    by = df.groupby(["ticker", "status"]).size().unstack(fill_value=0)
    print(by.to_string())
    sys.exit(res.exit_code)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), *sys.argv[4:5])
