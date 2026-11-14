"""
Replay the insight pipeline for dates the tables hold, then compare.

Use this when you need to ask "would our system have caught the move on
ticker X on date D?" (AMD 4/24 gap-up, CARS 3/31 catalyst, ARM multi-day
setup). The file keeps its name; it no longer backfills anything.

A replay reads bars only from the Cloud SQL tables the nightly pull fills.
This script fetches nothing and starts no data job. Three steps:

    1. Coverage check, per date D, on the script's own connection:
       market_data_intraday holds a 1-min bar for the ticker in the 7 days
       before D, and market_data_daily holds a daily bar before D. If any
       date fails, the script exits non-zero naming the ticker, the dates
       and the tables, and no job is started. A ticker gets its bars by
       being on the watchlist the nightly pulls read, not from here.
    2. (optional) Cloud Run insight-pipeline job execution at as_of=09:15 ET
       -> 8-agent LLM analyst run with pre-market context block, then
       (optional) insight-discord-push for review notification
    3. A side-by-side report: insight entry zone vs actual session H/L vs
       pre-market context.

History. Audit 2026-08-27 R7 (#824): the script used to re-implement the
daily fetch itself (its own AV fetch, its own market_data_daily writer and
an indicator map that disagreed with production on 14 keys each way). That
went, and the script dispatched the production per-ticker job instead.
FEAT-REPLAY-001 (2026-11-13) removed that dispatch too: a replay does not
fetch. tests/scripts/test_backfill_and_replay.py pins both.

Usage:
    # Single ticker, one date: check, replay, push, report
    python -m scripts.backfill_and_replay --ticker AMD --dates 2026-04-24

    # Multiple dates, no Discord push
    python -m scripts.backfill_and_replay --ticker ARM \\
        --dates 2026-04-20,2026-04-21,2026-04-22,2026-04-23 \\
        --skip-discord

    # Report only (no Cloud Run insight cost)
    python -m scripts.backfill_and_replay --ticker AMD \\
        --dates 2026-04-24 --skip-replay

Prereqs:
    * Run locally with the user's IP whitelisted on Cloud SQL (104.8.79.228/32)
      -- the coverage check and the comparison report read the DB directly
    * gcloud CLI authenticated for the project (job execs)
    * DB user/pass in Secret Manager as `db-trading-user` / `db-trading-pass`
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_ET = ZoneInfo('America/New_York')

# Make `lib.*` importable when invoked as a script from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
log = logging.getLogger('backfill_and_replay')


# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────
GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
PROJECT = 'adept-mountain-474619-d4'
REGION = 'us-east1'
DB_HOST = '34.24.66.12'
DB_NAME = 'trading'


# ──────────────────────────────────────────────────────────────────────
# Secrets + DB
# ──────────────────────────────────────────────────────────────────────
def secret(name: str) -> str:
    return subprocess.check_output(
        [GCLOUD, 'secrets', 'versions', 'access', 'latest',
         f'--secret={name}', f'--project={PROJECT}'],
        text=True,
    ).rstrip('\n')


def db_connect():
    # Imported here, not at module level: importing this script must not
    # need the driver (tests/scripts/test_generate_historical_report.py
    # states the convention for this family).
    import psycopg2  # noqa: PLC0415
    return psycopg2.connect(
        host=DB_HOST,
        user=secret('db-trading-user'),
        password=secret('db-trading-pass'),
        dbname=DB_NAME,
        sslmode='require',
    )


# The two tables a replay of D needs, and what the refusal says of each.
_REPLAY_TABLE_LACKS = {
    'market_data_intraday': 'market_data_intraday has no 1-min bars for {t} in the 7 days before {d}',
    'market_data_daily': 'market_data_daily has no daily bar for {t} before {d}',
}


def missing_replay_dates(conn, ticker: str, dates: list[date]) -> list[tuple[date, str]]:
    """The dates the tables cannot serve a replay for, each with the table
    that lacks it, in date order; at most one entry per date.

    The same two single-row probes Discord /replay runs, on this script's
    own connection: a 1-min bar for the ticker in the 7 days before the
    date (lib.eastern_time.replay_probe_window), and only if that finds a
    row, a daily bar before the date. Each distinct date is probed once.
    A query error propagates: "could not read" is not "no bars".
    """
    from lib.eastern_time import replay_probe_window  # noqa: PLC0415
    missing: list[tuple[date, str]] = []
    with conn.cursor() as cur:
        for d in sorted(set(dates)):
            lo, hi = replay_probe_window(d)
            cur.execute(
                "SELECT 1 FROM market_data_intraday WHERE ticker = %s AND interval = '1min' "
                "AND ts >= %s AND ts < %s LIMIT 1",
                (ticker, lo, hi),
            )
            if cur.fetchone() is None:
                missing.append((d, 'market_data_intraday'))
                continue
            cur.execute(
                "SELECT 1 FROM market_data_daily WHERE ticker = %s AND date < %s LIMIT 1",
                (ticker, d),
            )
            if cur.fetchone() is None:
                missing.append((d, 'market_data_daily'))
    return missing


# ──────────────────────────────────────────────────────────────────────
# Cloud Run — job execution
# ──────────────────────────────────────────────────────────────────────
def _execute_job(job: str, env: dict[str, str], wait: bool = True) -> bool:
    """Execute a Cloud Run Job with per-execution env overrides. Returns
    True on success; logs (never raises) on failure so the caller can
    decide whether the next step still makes sense."""
    # A value containing ',' would be split by --update-env-vars; callers
    # must pre-join multi-valued settings with ';'.
    bad = {k: v for k, v in env.items() if ',' in v}
    if bad:
        raise ValueError(f"env override values must not contain a comma "
                         f"(--update-env-vars splits on it); pre-join with ';': {bad}")
    cmd = [
        GCLOUD, 'run', 'jobs', 'execute', job,
        f'--region={REGION}', f'--project={PROJECT}',
        '--update-env-vars', ','.join(f'{k}={v}' for k, v in env.items()),
    ]
    if wait:
        cmd.append('--wait')
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log.error("  %s failed: %s", job, proc.stderr.strip()[-500:])
        return False
    log.info("  ✓ %s complete", job)
    return True


def insight_as_of_utc(d: date, hhmm_et: str) -> datetime:
    """The UTC instant of ``hhmm_et`` on Eastern date ``d``.

    Through the named zone (CLAUDE.md 3.9): the earlier ``int(hh) + 4``
    hard-coded EDT, so on an EST date 09:15 ET became 08:15 ET and a
    winter replay was not the as-of production ran.
    """
    hh, mm = (int(x) for x in hhmm_et.split(':'))
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=_ET).astimezone(timezone.utc)


def trigger_insight_pipeline(ticker: str, as_of_iso_utc: str, wait: bool = True) -> bool:
    """Execute the insight-pipeline Cloud Run Job for one (ticker, as_of) pair.

    Returns _execute_job's verdict; main() stops on False so the comparison
    report never runs against a replay that did not happen.
    """
    log.info("Cloud Run insight-pipeline → %s as_of=%s", ticker, as_of_iso_utc)
    return _execute_job('insight-pipeline',
                        {'INSIGHT_TICKERS': ticker, 'INSIGHT_AS_OF': as_of_iso_utc},
                        wait=wait)


def trigger_discord_push(ticker: str, push_date: str, wait: bool = True) -> bool:
    log.info("Cloud Run insight-discord-push → %s date=%s", ticker, push_date)
    return _execute_job('insight-discord-push',
                        {'INSIGHT_PUSH_TICKER': ticker, 'INSIGHT_PUSH_DATE': push_date},
                        wait=wait)


# ──────────────────────────────────────────────────────────────────────
# Reporting — comparison
# ──────────────────────────────────────────────────────────────────────
def report_comparison(conn, ticker: str, dates: list[date]):
    """Print a side-by-side: insight zone vs actual session H/L vs pre-market."""
    print()
    print('=' * 92)
    print(f'  {ticker}  --  insight vs actual')
    print('=' * 92)
    import psycopg2.extras  # noqa: PLC0415
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        for d in dates:
            cur.execute(
                """SELECT open, high, low, close, pre_high, pre_low,
                          pre_vwap, gap_pct, ftfc_score, ftfc_direction
                     FROM market_data_daily
                    WHERE ticker=%s AND date=%s""",
                (ticker, d),
            )
            row = cur.fetchone()
            cur.execute(
                """SELECT as_of, report
                     FROM insight_reports
                    WHERE ticker=%s AND as_of::date=%s
                    ORDER BY as_of DESC LIMIT 1""",
                (ticker, d),
            )
            ins = cur.fetchone()
            print(f'\n  {d} -- actual session: O={_fmt(row, "open")} H={_fmt(row, "high")} '
                  f'L={_fmt(row, "low")} C={_fmt(row, "close")}')
            print(f'    pre-market: pre_H={_fmt(row, "pre_high")} pre_L={_fmt(row, "pre_low")} '
                  f'pre_VWAP={_fmt(row, "pre_vwap")} gap={_pct(row, "gap_pct")}')
            print(f'    FTFC: score={_fmt(row, "ftfc_score")} dir={row.get("ftfc_direction") if row else "-"}')
            if ins:
                rep = ins['report'] if isinstance(ins['report'], dict) else json.loads(ins['report'])
                ez = rep.get('entry_zone') or {}
                print(f'    insight @ {ins["as_of"]} -> {rep.get("direction"):>5} '
                      f'({rep.get("conviction")}) entry=${ez.get("low")}-${ez.get("high")} '
                      f'stop=${rep.get("stop")} targets={rep.get("targets")}')
                # Reachability check
                if row and row.get('low') is not None and row.get('high') is not None:
                    if ez.get('low') is not None and ez.get('high') is not None:
                        reached = (row['low'] <= ez['high'] and row['high'] >= ez['low'])
                        print(f'    entry reached during RTH? {"YES" if reached else "NO"}')
            else:
                print('    insight: (none)')
    print('=' * 92)


def _fmt(row: dict | None, key: str) -> str:
    if not row or row.get(key) is None:
        return '-'
    return f'{row[key]:.2f}'


def _pct(row: dict | None, key: str) -> str:
    """Format a value already stored as a percent (1.62 = 1.62%)."""
    if not row or row.get(key) is None:
        return '-'
    return f'{row[key]:+.2f}%'


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--ticker', required=True,
                   help='Ticker symbol (e.g. AMD, CARS, ARM)')
    p.add_argument('--dates', required=True,
                   help='Comma-separated YYYY-MM-DD dates to replay')
    p.add_argument('--insight-time-et', default='09:15',
                   help='ET time-of-day for insight as_of (default 09:15)')
    p.add_argument('--skip-replay', action='store_true',
                   help='Report only; do not trigger insight-pipeline runs')
    p.add_argument('--skip-discord', action='store_true',
                   help='Skip Discord push after insight runs (default: push)')
    args = p.parse_args()

    ticker = args.ticker.upper()
    dates = [pd.to_datetime(d.strip()).date() for d in args.dates.split(',') if d.strip()]
    if not dates:
        sys.exit('--dates required')

    log.info('Replay: ticker=%s dates=%s', ticker, dates)

    conn = db_connect()
    try:
        # Read-only connection, held from the probes to the report with
        # minutes of job runs in between. psycopg2 opens a transaction on
        # the first statement and keeps it until commit or rollback, so
        # without this the probes' transaction would sit idle across every
        # job. In autocommit each read is its own transaction.
        conn.autocommit = True

        # 1. Coverage check. A replay reads bars only from the tables, so a
        #    date they lack is refused here, before any job. Runs with
        #    --skip-replay too: the report would compare against nothing.
        missing = missing_replay_dates(conn, ticker, dates)
        if missing:
            sys.exit(
                f'No replay for {ticker}: '
                + '; '.join(_REPLAY_TABLE_LACKS[table].format(t=ticker, d=d.isoformat())
                            for d, table in missing)
                + '. Nothing was fetched and no job was started.')

        # 2. Replay LLM insight pipeline
        if not args.skip_replay:
            for d in dates:
                as_of_iso = insight_as_of_utc(d, args.insight_time_et).strftime('%Y-%m-%dT%H:%M:%SZ')
                if not trigger_insight_pipeline(ticker, as_of_iso):
                    sys.exit(f'insight-pipeline failed for {ticker} as_of={as_of_iso}; '
                             'not continuing to the next date or the comparison report')
                if not args.skip_discord:
                    if not trigger_discord_push(ticker, d.strftime('%Y-%m-%d')):
                        sys.exit(f'insight-discord-push failed for {ticker} date={d}; '
                                 'the insight exists in insight_reports but was not pushed')

        # 3. Side-by-side report
        report_comparison(conn, ticker, dates)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
