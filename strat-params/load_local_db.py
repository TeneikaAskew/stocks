"""Load results/monitor_inputs/ (the read-only production export) into a
throwaway LOCAL Postgres, so the signal monitor's own replay harness
(scripts/replay_signal_monitor.py) can run against a copy of what it reads
in production. Nothing here connects to Cloud SQL, writes anywhere but the
local database, deploys or posts.

The local database must already carry gcp/schema.sql. Tables exported as
one to_jsonb row per line are restored with jsonb_populate_record, so every
column the local schema has keeps its production value. A key the
production row has but the local schema lacks is reported (never silently
dropped), and a local column the export never filled is reported too.

Usage:
  python3 load_local_db.py <monitor_inputs_dir> <postgres_dsn>
  e.g. load_local_db.py results/monitor_inputs "host=localhost port=55432 user=postgres dbname=trading"
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import psycopg2

csv.field_size_limit(sys.maxsize)
INTRADAY_COLS = ["ticker", "interval", "ts", "open", "high", "low", "close", "volume", "data_source"]


def table_columns(cur, table: str) -> dict[str, bool]:
    """column -> is_generated, for a public table."""
    cur.execute("SELECT column_name, is_generated FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position", (table,))
    return {c: g == "ALWAYS" for c, g in cur.fetchall()}


def load_json_table(cur, table: str, path: Path) -> dict:
    cols = table_columns(cur, table)
    if not cols:
        raise SystemExit(f"{table}: not in the local schema; cannot load {path.name}")
    insertable = [c for c, gen in cols.items() if not gen]
    collist = ", ".join(f'"{c}"' for c in insertable)
    sql = (f'INSERT INTO "{table}" ({collist}) SELECT {collist} '
           f'FROM jsonb_populate_record(NULL::"{table}", %s::jsonb)')
    n, extra, seen = 0, set(), set()
    if path.stat().st_size == 0:
        return {"table": table, "rows": 0, "extra_keys": [], "unfilled_columns": []}
    with open(path, newline="") as f:
        for rec in csv.DictReader(f):
            row = json.loads(rec["row"])
            extra |= set(row) - set(cols)
            seen |= set(row) & set(cols)
            cur.execute(sql, (json.dumps(row),))
            n += 1
    return {"table": table, "rows": n, "extra_keys": sorted(extra),
            "unfilled_columns": sorted(set(insertable) - seen)}


def load_intraday(cur, path: Path) -> dict:
    if path.stat().st_size == 0:
        return {"table": "market_data_intraday", "file": path.name, "rows": 0}
    collist = ", ".join(INTRADAY_COLS)
    with open(path, newline="") as f:
        header = f.readline().strip().split(",")
        if header != INTRADAY_COLS:
            raise SystemExit(f"{path.name}: unexpected header {header}")
        cur.copy_expert(f"COPY market_data_intraday ({collist}) FROM STDIN WITH (FORMAT csv)", f)
    return {"table": "market_data_intraday", "file": path.name, "rows": cur.rowcount}


def main(src: Path, dsn: str) -> None:
    conn = psycopg2.connect(dsn)
    report = []
    with conn, conn.cursor() as cur:
        # The local copy holds exactly the exported production rows: schema.sql
        # seeds some tables (exit_config_overrides), so every table loaded here
        # is emptied first. LOCAL database only; the DSN is checked below.
        loaded = sorted({"market_data_intraday" if p.name.startswith("intraday_") else p.stem
                         for p in src.glob("*.csv")})
        cur.execute("SELECT inet_server_addr()::text, current_setting('port')")
        addr, port = cur.fetchone()
        if addr not in ("127.0.0.1/32", "::1/128"):
            raise SystemExit(f"refusing to truncate on a non-local server ({addr}:{port})")
        cur.execute("TRUNCATE " + ", ".join(f'"{t}"' for t in loaded) + " CASCADE")
        for p in sorted(src.glob("*.csv")):
            if p.name.startswith("intraday_"):
                r = load_intraday(cur, p)
            else:
                r = load_json_table(cur, p.stem, p)
            report.append(r)
            print(json.dumps(r), flush=True)
    conn.close()
    (src.parent / "monitor_inputs_load_report.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
