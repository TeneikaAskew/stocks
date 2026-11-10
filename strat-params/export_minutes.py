"""Read-only export of SPY, QQQ and IWM one-minute bars from production
through scripts/db_query_cr.sh, which caps every statement at 50,000 rows
(gcp/queries/run_query.py ROW_CAP). So it first counts the bars per ticker
and UTC month, packs consecutive months into statements of at most 45,000
rows, sends up to 6 statements per job run, downloads each statement's CSV,
checks every CSV holds exactly the counted rows, and writes
<out>/minutes/{spy,qqq,iwm}.csv (ts, open, high, low, close, volume).

No --commit is ever passed: every run rolls back. Run from the repo root:
  python3 export_minutes.py <out_dir> [first_month, default 2012-01]
Re-running skips parts already downloaded and checked.
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path

TICKERS = ("SPY", "QQQ", "IWM")
CAP = 45_000
PER_RUN = 6

COUNT_SQL = (
    "SELECT ticker, to_char(date_trunc('month', ts AT TIME ZONE 'UTC'), 'YYYY-MM') AS ym, count(*) AS n "
    "FROM market_data_intraday WHERE interval = '1min' AND ticker IN ('SPY', 'QQQ', 'IWM') "
    "AND ts >= TIMESTAMPTZ '{first}-01 00:00:00+00' GROUP BY 1, 2 ORDER BY 1, 2")
PART_SQL = (
    "SELECT ts, open, high, low, close, volume FROM market_data_intraday "
    "WHERE ticker = '{t}' AND interval = '1min' AND ts >= TIMESTAMPTZ '{lo}-01 00:00:00+00' "
    "AND ts < TIMESTAMPTZ '{hi}-01 00:00:00+00' ORDER BY ts")


def next_month(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    return f"{y + (m == 12)}-{1 if m == 12 else m + 1:02d}"


def run(sql: str, out: Path) -> str:
    """One read-only db-query run; returns its GCS prefix."""
    res = subprocess.run(["./scripts/db_query_cr.sh", "--timeout", "900", "--wait-timeout", "1500",
                          "-q", sql], capture_output=True, text=True)
    (out / "last_run.err").write_text(res.stderr)
    m = re.search(r"gs://\S+/query-results/\S+", res.stdout + res.stderr)
    if res.returncode != 0 or not m:
        # --quiet hides "results at:"; find the prefix in the summary instead
        raise SystemExit(f"db-query run failed (exit {res.returncode}); see {out / 'last_run.err'}\n"
                         + res.stderr[-2000:])
    return m.group(0).rstrip("/").rsplit("/summary", 1)[0]


def fetch(prefix: str, name: str, dest: Path) -> None:
    subprocess.run(["gcloud", "storage", "cp", f"{prefix}/{name}", str(dest)], check=True,
                   capture_output=True)


def main(out: Path, first: str = "2012-01") -> None:
    out.mkdir(parents=True, exist_ok=True)
    parts = out / "parts"
    parts.mkdir(exist_ok=True)
    counts_csv = out / "counts.csv"
    if not counts_csv.exists():
        prefix = run(COUNT_SQL.format(first=first), out)
        fetch(prefix, "result_001.csv", counts_csv)
    counts = {}
    with open(counts_csv) as f:
        for r in csv.DictReader(f):
            counts.setdefault(r["ticker"], []).append((r["ym"], int(r["n"])))
    for t in TICKERS:
        months = counts.get(t, [])
        print(t, "months", len(months), "bars", sum(n for _, n in months),
              "from", months[0][0] if months else None, "to", months[-1][0] if months else None, flush=True)
    # pack consecutive months into statements of at most CAP rows
    stmts = []  # (ticker, lo, hi_exclusive, expected)
    for t in TICKERS:
        cur = None
        for ym, n in counts.get(t, []):
            if n > CAP:
                raise SystemExit(f"{t} {ym} has {n} bars, over one statement; split by day")
            if cur and cur[3] + n <= CAP and cur[2] == ym:
                cur = (t, cur[1], next_month(ym), cur[3] + n)
            else:
                if cur:
                    stmts.append(cur)
                cur = (t, ym, next_month(ym), n)
        if cur:
            stmts.append(cur)
    todo = [s for s in stmts if not (parts / f"{s[0]}_{s[1]}.ok").exists()]
    print(len(stmts), "statements,", len(todo), "to fetch", flush=True)
    for i in range(0, len(todo), PER_RUN):
        batch = todo[i:i + PER_RUN]
        prefix = run(";\n".join(PART_SQL.format(t=t, lo=lo, hi=hi) for t, lo, hi, _ in batch), out)
        for j, (t, lo, hi, n) in enumerate(batch, 1):
            dest = parts / f"{t}_{lo}.csv"
            fetch(prefix, f"result_{j:03d}.csv", dest)
            got = sum(1 for _ in open(dest)) - 1
            if got != n:
                raise SystemExit(f"{t} {lo}..{hi}: {got} rows, counted {n} (truncated or changed)")
            (parts / f"{t}_{lo}.ok").write_text(f"{n}\n")
        print(f"run {i // PER_RUN + 1}: {', '.join(f'{t} {lo}' for t, lo, _, _ in batch)} ok", flush=True)
    mdir = out / "minutes"
    mdir.mkdir(exist_ok=True)
    for t in TICKERS:
        files = sorted(parts.glob(f"{t}_*.csv"))
        total = 0
        with open(mdir / f"{t.lower()}.csv", "w") as w:
            w.write("ts,open,high,low,close,volume\n")
            for p in files:
                with open(p) as f:
                    next(f)
                    for line in f:
                        w.write(line)
                        total += 1
        print(t, "wrote", total, "bars", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), *sys.argv[2:3])
