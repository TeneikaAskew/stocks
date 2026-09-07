"""
Backfill + replay for historical brief/insight testing.

Use this when you need to ask "would our system have caught the move on
ticker X on date D?" — e.g. AMD 4/24 gap-up, CARS 3/31 catalyst, ARM
multi-day setup. Three steps:

    1. Data backfill through the PRODUCTION per-ticker job
       (`backfill-ticker`, gcp/backfill_ticker.py — the same job the
       Discord /replay command dispatches): AV daily history →
       market_data_daily, AV 1-min bars → market_data_intraday,
       (optional) AV news → news_sentiment, then indicators + strat
       fields + pre-market context via gcp.database.
       DAILY_INDICATOR_TO_SQL_COLUMN, the one indicator map.
    2. (optional) Cloud Run insight-pipeline job execution at as_of=09:15 ET
       → 8-agent LLM analyst run with pre-market context block
    3. (optional) Cloud Run insight-discord-push for review notification

Then a side-by-side report: insight entry zone vs actual session H/L vs
pre-market context.

Audit 2026-08-27 R7 (#824): this script used to re-implement step 1
itself — its own AV fetch, its own market_data_daily writer stamping
data_source='alphavantage' (a value production never writes) and its own
indicator-to-column map that disagreed with production on 14 keys each
way (MA5 vs SMA5, RSI vs RSI14, consecutive_up vs Consecutive_Up, none of
the seven columns promoted 2026-05-31). 1686 stored rows (AMD, CARS, MCK,
NVDA) came from that path. CLAUDE.md §3.6 names the production fetcher
as the one sanctioned backfill path, so the duplicate pipeline is gone
and the job is dispatched instead. tests/scripts/test_backfill_and_replay.py
pins it.

Usage:
    # Single ticker, one date, full pipeline (backfill + LLM)
    python -m scripts.backfill_and_replay --ticker AMD --dates 2026-04-24

    # Multiple dates, with news, no Discord push
    python -m scripts.backfill_and_replay --ticker ARM \\
        --dates 2026-04-20,2026-04-21,2026-04-22,2026-04-23 \\
        --include-news --skip-discord

    # Skip data backfill (already backfilled), just rerun the LLM
    python -m scripts.backfill_and_replay --ticker CARS \\
        --dates 2026-03-31 --skip-backfill

    # Skip the LLM (just data backfill, no Cloud Run insight cost)
    python -m scripts.backfill_and_replay --ticker AMD \\
        --dates 2026-04-24 --skip-replay

Prereqs:
    * Run locally with the user's IP whitelisted on Cloud SQL (104.8.79.228/32)
      — only the comparison report reads the DB directly
    * gcloud CLI authenticated for the project (job execs)
    * DB user/pass in Secret Manager as `db-trading-user` / `db-trading-pass`
    * The backfill-ticker job carries its own AV key binding
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras

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

# gcp.backfill_ticker reads BACKFILL_HISTORY_DAYS (its own default is 800,
# the floor that lets compute_earnings_reactions populate 12 quarters).
DAILY_HISTORY_DAYS = 800


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
    return psycopg2.connect(
        host=DB_HOST,
        user=secret('db-trading-user'),
        password=secret('db-trading-pass'),
        dbname=DB_NAME,
        sslmode='require',
    )


# ──────────────────────────────────────────────────────────────────────
# Cloud Run — job execution
# ──────────────────────────────────────────────────────────────────────
def _execute_job(job: str, env: dict[str, str], wait: bool = True) -> bool:
    """Execute a Cloud Run Job with per-execution env overrides. Returns
    True on success; logs (never raises) on failure so the caller can
    decide whether the next step still makes sense."""
    # A value containing ',' would be split by --update-env-vars; callers
    # must pre-join multi-valued settings with ';' (backfill_ticker's
    # _parse_dates accepts ';').
    assert not any(',' in v for v in env.values()), env
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


def _month_groups(dates: list[date]) -> list[list[date]]:
    """Group dates by calendar month, ascending.

    backfill-ticker pulls one full AV 1-minute month per month a date
    touches (plus the prior trading day's month), sequentially, inside a
    600 s task timeout (gcp/deploy.sh deploy_backfill_ticker) while each
    AV monthly request may take up to 120 s. One execution per month keeps
    every run inside that deadline instead of letting a long --dates list
    exhaust it after the fetches and before the indicators (Codex on
    #1022)."""
    groups: dict[tuple[int, int], list[date]] = {}
    for d in sorted(set(dates)):
        groups.setdefault((d.year, d.month), []).append(d)
    return [groups[k] for k in sorted(groups)]


def trigger_backfill_ticker(ticker: str, dates: list[date], *,
                            include_news: bool, history_days: int,
                            news_window_days: int, wait: bool = True) -> bool:
    """Run the production per-ticker backfill (gcp/backfill_ticker.py):
    daily history, 1-min bars for every month a date touches, optional
    news, then indicators + strat + pre-market context through the one
    production indicator map. Same job the Discord /replay command
    dispatches (gcp/discord_interactions/main.py), minus its watchlist
    side effect. One execution per calendar month of ``dates`` (see
    _month_groups); returns False on the first failed month."""
    for group in _month_groups(dates):
        log.info("Cloud Run backfill-ticker → %s dates=%s history=%dd news=%s",
                 ticker, [d.isoformat() for d in group], history_days, include_news)
        ok = _execute_job('backfill-ticker', {
            'BACKFILL_TICKER': ticker,
            'BACKFILL_DATES': ';'.join(d.isoformat() for d in group),
            'BACKFILL_INCLUDE_NEWS': 'true' if include_news else 'false',
            'BACKFILL_HISTORY_DAYS': str(history_days),
            'BACKFILL_NEWS_WINDOW': str(news_window_days),
            # Historical-test tickers must not join (or be reactivated in) the
            # shared production watchlist that every fetcher iterates.
            'BACKFILL_ADD_TO_WATCHLIST': 'false',
        }, wait=wait)
        if not ok:
            return False
    return True


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
    p.add_argument('--history-days', type=int, default=DAILY_HISTORY_DAYS,
                   help=f'Daily-history depth (default {DAILY_HISTORY_DAYS}d)')
    p.add_argument('--include-news', action='store_true',
                   help='Also fetch AV NEWS_SENTIMENT for the ticker')
    p.add_argument('--news-window-days', type=int, default=7,
                   help='News lookback window in days (default 7)')
    p.add_argument('--insight-time-et', default='09:15',
                   help='ET time-of-day for insight as_of (default 09:15)')
    p.add_argument('--skip-backfill', action='store_true',
                   help='Skip the backfill-ticker job (use existing DB state)')
    p.add_argument('--skip-replay', action='store_true',
                   help='Only backfill data; do not trigger insight-pipeline runs')
    p.add_argument('--skip-discord', action='store_true',
                   help='Skip Discord push after insight runs (default: push)')
    args = p.parse_args()

    ticker = args.ticker.upper()
    dates = [pd.to_datetime(d.strip()).date() for d in args.dates.split(',') if d.strip()]
    if not dates:
        sys.exit('--dates required')

    log.info('Backfill+replay: ticker=%s dates=%s history=%dd', ticker, dates, args.history_days)

    # 1. Data backfill through the production job. It handles the prior
    #    trading day of every date itself (prev_close / gap_pct need it).
    if not args.skip_backfill:
        ok = trigger_backfill_ticker(
            ticker, dates,
            include_news=args.include_news,
            history_days=args.history_days,
            news_window_days=args.news_window_days,
        )
        if not ok:
            sys.exit(f'backfill-ticker failed for {ticker}; not replaying on partial data')

    # 2. Replay LLM insight pipeline
    if not args.skip_replay:
        hh, mm = args.insight_time_et.split(':')
        for d in dates:
            # ET → UTC. ET is UTC-4 in DST (EDT, Mar-Nov), UTC-5 otherwise.
            # Approximation: 09:15 ET = 13:15 UTC during DST.
            as_of = datetime(d.year, d.month, d.day, int(hh) + 4, int(mm),
                             tzinfo=timezone.utc)
            as_of_iso = as_of.strftime('%Y-%m-%dT%H:%M:%SZ')
            if not trigger_insight_pipeline(ticker, as_of_iso):
                sys.exit(f'insight-pipeline failed for {ticker} as_of={as_of_iso}; '
                         'not continuing to the next date or the comparison report')
            if not args.skip_discord:
                if not trigger_discord_push(ticker, d.strftime('%Y-%m-%d')):
                    sys.exit(f'insight-discord-push failed for {ticker} date={d}; '
                             'the insight exists in insight_reports but was not pushed')

    # 3. Side-by-side report
    conn = db_connect()
    try:
        report_comparison(conn, ticker, dates)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
