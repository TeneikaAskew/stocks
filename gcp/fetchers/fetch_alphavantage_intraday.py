#!/usr/bin/env python3
"""
Cloud Run Job: Fetch AlphaVantage 1-min historical intraday → Cloud SQL.

Replaces the GitHub Actions workflow fetch-alphavantage-intraday-monthly.yml.
Scheduled on the 1st of each month by Cloud Scheduler.

Usage:
    python -m gcp.fetchers.fetch_alphavantage_intraday --symbol SPY
    python -m gcp.fetchers.fetch_alphavantage_intraday --symbol ALL --start-date 2026-01-01
"""

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from lib.eastern_time import eastern_index_to_utc, stored_intraday_to_eastern, utc_to_eastern_naive

from gcp.database import (
    bulk_insert_dataframe,
    execute_sql,
    is_cloud_sql_configured,
    query_to_dataframe_strict,
    WindowChanged,
    replace_rows_in_window,
    upsert_dataframe,
)
from lib.config import AlphaVantageConfig

from lib.logging_config import setup_logging
setup_logging()
log = logging.getLogger(__name__)

SYMBOLS = ['SPY', 'IWM', 'QQQ']
AV_BASE_URL = 'https://www.alphavantage.co/query'

# Watchlist data-quality issue routing — see _file_data_quality_issue().
# A separate label from `gcp-job-failure` so the auto-issue scanner can
# distinguish "actionable code/infra bug" (gcp-job-failure → page) from
# "watchlist hygiene needed" (data-quality → batch-prune on a cadence).
_DQ_REPO = 'TeneikaAskew/stocks'
_DQ_LABELS = ['data-quality', 'intraday-bulk-backfill', 'dead-tickers']
# Per-call interval is read from AlphaVantageConfig so the 150 RPM
# premium-tier setting is the single source of truth across fetchers.
# (Previously hardcoded to 13 s — the 5-RPM free-tier value — which
# made a 50-ticker backfill take 5+ hours instead of ~10 minutes.)
_av_cfg = AlphaVantageConfig()


def get_api_keys() -> list:
    """Collect all available AlphaVantage API keys from environment."""
    keys = []
    primary = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    if primary:
        keys.append(primary)
    # Support backup keys: ALPHA_VANTAGE_API_KEY_2, _3, _4, _5
    for i in range(2, 6):
        k = os.environ.get(f'ALPHA_VANTAGE_API_KEY_{i}', '')
        if k:
            keys.append(k)
    return keys


def get_trading_months(start_date: str, end_date: str) -> list:
    """Return list of (year, month) tuples covering the date range."""
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    months = []
    current = start.replace(day=1)
    while current <= end:
        months.append((current.year, current.month))
        current = (current + pd.offsets.MonthBegin(1))
    return months


# Per-month outcome reasons returned from fetch_month. The string is
# distinct from None so the caller can categorise WHY a fetch returned
# no data — critical for the dead-ticker vs transient-error
# classification in process_symbol's outcome (see _TICKER_OUTCOME_*).
FETCH_OK             = 'success'
FETCH_INVALID_API    = 'invalid_api_call'   # AV "Error Message" — symbol unknown / delisted
FETCH_RATE_LIMIT     = 'rate_limit'         # AV "Note" — burned through RPM
FETCH_INFO_MSG       = 'info_message'       # AV "Information" — generic non-data response
FETCH_NO_TIMESERIES  = 'no_timeseries'      # response shape unexpected
FETCH_REQUEST_ERROR  = 'request_error'      # network / HTTP error

# Reasons that indicate a permanently-broken ticker (not a transient).
# A symbol whose entire month-range returns ONLY these is treated as
# a data-quality failure (dead/delisted ticker), not a systemic failure.
_DEAD_TICKER_REASONS = {FETCH_INVALID_API, FETCH_INFO_MSG, FETCH_NO_TIMESERIES}


def fetch_month(
    symbol: str, year: int, month: int, api_key: str,
) -> Tuple[Optional[pd.DataFrame], str]:
    """Fetch one month of 1-minute data from AlphaVantage.

    Returns ``(df, reason)`` where ``df`` is the data (or None on any
    failure) and ``reason`` is one of the ``FETCH_*`` constants above.
    The reason is what lets process_symbol categorise the outcome:
    "every month said INVALID_API" → dead ticker (data quality),
    "every month said REQUEST_ERROR" → systemic (network outage).
    """
    month_str = f"{year}-{month:02d}"
    params = {
        'function': 'TIME_SERIES_INTRADAY',
        'symbol': symbol,
        'interval': '1min',
        'month': month_str,
        'outputsize': 'full',
        'entitlement': 'realtime',
        'extended_hours': 'true',
        'datatype': 'json',
        'apikey': api_key,
    }
    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if 'Error Message' in data:
            log.warning("    AV error for %s %s: %s", symbol, month_str, data['Error Message'])
            return None, FETCH_INVALID_API
        if 'Note' in data:
            log.warning("    AV rate limit for %s %s", symbol, month_str)
            return None, FETCH_RATE_LIMIT
        if 'Information' in data:
            log.warning("    AV info: %s", data['Information'])
            return None, FETCH_INFO_MSG

        ts_key = 'Time Series (1min)'
        if ts_key not in data:
            log.warning("    No time series data for %s %s", symbol, month_str)
            return None, FETCH_NO_TIMESERIES

        records = []
        for ts, values in data[ts_key].items():
            records.append({
                'ts': pd.Timestamp(ts),
                'open':   float(values['1. open']),
                'high':   float(values['2. high']),
                'low':    float(values['3. low']),
                'close':  float(values['4. close']),
                'volume': int(values['5. volume']),
            })

        df = pd.DataFrame(records)
        df['ticker'] = symbol
        df['interval'] = '1min'
        df['data_source'] = 'alphavantage'
        return df.sort_values('ts').reset_index(drop=True), FETCH_OK

    except Exception as e:
        log.error("    Request error for %s %s: %s", symbol, year, e)
        return None, FETCH_REQUEST_ERROR


# Per-ticker outcome categories returned by process_symbol. Used by the
# outer loop to decide whether to exit(1). Only OUTCOME_SYSTEMIC trips
# the failure exit — dead-ticker outcomes are logged at WARNING level
# but don't fail the task (3.7 §5: typed UNAVAILABLE envelope, not
# silent fallback). Per CLAUDE.md Rule 0.4 (bounded retries, idempotent
# re-runs), a single delisted ticker in a 339-ticker watchlist must
# not crash the entire task and auto-file a gcp-job-failure issue —
# that pattern produced 8 spurious issues over 6 days on `s2fpq`.
OUTCOME_OK         = 'ok'                 # at least one month yielded data
OUTCOME_SKIPPED    = 'skipped'            # already-backfilled (not a failure)
OUTCOME_DEAD       = 'dead_ticker'        # every month returned a data-quality reason
OUTCOME_SYSTEMIC   = 'systemic'           # process_symbol raised (caught by outer loop)


# Ticker-level skip threshold for the bulk-backfill re-run path.
# A fully backfilled ticker over 24 months has ~500k 1-min bars; 100k
# is the floor for "substantial coverage already" while still leaving
# room for partial-fetch tickers (where a daily-fetch wrote a single
# day) to be re-fetched. This is intentionally coarser than per-month
# checking because 1,356 tickers × 24 months = 32k queries vs 1,356
# queries — the per-month variant adds 15 minutes of pure DB overhead
# to avoid maybe 5 minutes of AV re-fetches per partial ticker.
_SKIP_TICKER_ROW_THRESHOLD = 100_000


def _ticker_already_backfilled(symbol: str) -> bool:
    """Fast check: does this ticker already have substantial 1-min coverage?

    Returns True when ``market_data_intraday`` has ≥100k rows for this
    ticker in the 2024-01-01+ range — the indicator that a previous
    backfill run completed this ticker. The query uses the
    (ticker, interval, ts) primary-key prefix so it's index-scan fast
    (~10 ms typical). False on any failure (table missing, creds
    missing, transient query error) so a flaky DB doesn't silently
    skip a ticker that should run.
    """
    try:
        from gcp.database import query_to_dataframe, is_cloud_sql_configured
    except ImportError:
        return False
    if not is_cloud_sql_configured():
        return False
    try:
        df = query_to_dataframe(
            "SELECT count(*) AS n FROM market_data_intraday "
            "WHERE ticker = :t AND interval = '1min' "
            "AND ts >= '2024-01-01'",
            {"t": symbol.upper()},
        )
    except Exception as e:
        log.debug("    skip-check failed for %s: %s — will fetch", symbol, e)
        return False
    if df is None or df.empty:
        return False
    try:
        n = int(df.iloc[0]['n'])
    except (TypeError, ValueError, KeyError):
        return False
    return n >= _SKIP_TICKER_ROW_THRESHOLD


def process_symbol(
    symbol: str,
    start_date: str,
    end_date: str,
    api_keys: list,
    force: bool,
) -> str:
    """Fetch all months for a symbol and write to Cloud SQL.

    Returns one of the ``OUTCOME_*`` constants so the outer loop can
    distinguish data-quality failures (dead ticker — every month said
    "Invalid API call") from real successes from systemic errors
    (which still propagate as raised exceptions and are caught by the
    outer loop's try/except). Per CLAUDE.md Rule 3.7: this is a TYPED
    envelope — never a silent fallback.

    Re-fetches every month in the range unconditionally. The previous
    parquet_exists_in_gcs sentinel had completion semantics — a parquet
    only existed after the monthly fetch finished — so it was safe to
    skip on. The SQL table doesn't carry the same signal: fetch_market_data
    inserts daily 1-min bars into the same (ticker, year, month) bucket,
    so an "any row exists" check would mark a month as covered after one
    daily insert and silently drop the rest of the monthly backfill.

    Re-fetching is cheap enough to make the simpler approach worthwhile:
    default range is current_month-1 → today (~2 months), 3 tickers, AV
    premium 150 RPM ≈ 3 sec per night. Backfill of 5 years × 3 tickers ≈
    180 calls ≈ 1.2 min. Idempotent via ON CONFLICT DO UPDATE on
    (ticker, interval, ts).

    For BULK BACKFILL (1,356 tickers via --symbols-file): the script
    skips tickers that already have substantial coverage (≥100k rows
    in 2024-01-01+) so a re-run after a task-timeout completes only
    the NEW tickers, not the ones we already finished. The skip is
    bypassed with --force.
    """
    if not force and _ticker_already_backfilled(symbol):
        log.info("  %s: already has ≥%d rows from a prior run — skipping",
                 symbol, _SKIP_TICKER_ROW_THRESHOLD)
        return OUTCOME_SKIPPED
    months = get_trading_months(start_date, end_date)
    log.info("  %s: %d months (%s → %s)", symbol, len(months), start_date, end_date)

    key_idx = 0
    call_count = 0
    last_call_time = 0.0
    inserted_total = 0
    # Track per-reason counts for the dead-ticker classification at end.
    reason_counts: dict = {}

    for year, month in months:
        month_str = f"{year}-{month:02d}"

        # Rate limiting — uses AlphaVantageConfig.delay_between_calls
        # so premium-tier callers get the full 150 RPM throughput.
        elapsed = time.time() - last_call_time
        if elapsed < _av_cfg.delay_between_calls:
            time.sleep(_av_cfg.delay_between_calls - elapsed)

        api_key = api_keys[key_idx % len(api_keys)]
        df, reason = fetch_month(symbol, year, month, api_key)
        last_call_time = time.time()
        call_count += 1
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

        # Rotate key on rate limit detection
        if df is None and call_count % 5 == 0:
            key_idx += 1
            log.info("    Rotating to API key %d", key_idx + 1)

        if df is None or df.empty:
            continue

        # Naive Eastern vendor stamps -> UTC instants (CLAUDE.md 3.9).
        df['ts'] = eastern_index_to_utc(df['ts'])

        log.info("    %s: %d bars", month_str, len(df))

        # Write to Cloud SQL — upsert so re-runs are safe (overwrites
        # existing rows instead of failing on duplicate primary key).
        if is_cloud_sql_configured():
            upsert_dataframe(
                df, 'market_data_intraday',
                conflict_cols=['ticker', 'interval', 'ts'],
                chunksize=5000,
            )
            inserted_total += len(df)

    log.info("  %s complete: %d rows inserted (reasons=%s)",
             symbol, inserted_total, reason_counts)

    # Dead-ticker classification: ZERO successful fetches AND every
    # non-success fetch returned a permanently-broken reason (Invalid
    # API call / info / no timeseries). If ANY month returned a
    # transient reason (rate_limit, request_error) the ticker is NOT
    # confirmed-dead — a re-run gets another shot at the transient
    # month. We key on FETCH_OK count rather than inserted_total
    # because inserted_total is also 0 when Cloud SQL is unconfigured
    # (dev / dry-run env), which should NOT mark a ticker as dead.
    got_any_data = reason_counts.get(FETCH_OK, 0) > 0
    if not got_any_data and reason_counts:
        non_dead_reasons = set(reason_counts) - _DEAD_TICKER_REASONS
        if not non_dead_reasons:
            return OUTCOME_DEAD
    return OUTCOME_OK


def _file_data_quality_issue(dead_tickers: list) -> None:
    """Create-or-update a GitHub issue summarising dead tickers from
    this run. Idempotent: if an open issue with our labels exists, we
    append a comment with the new run's findings instead of opening a
    duplicate. The issue lives on a different label (``data-quality``)
    than the failure-notifier path (``gcp-job-failure``) so the
    operator can triage hygiene separately from real bugs.

    Token source: ``GH_DATA_QUALITY_TOKEN`` env (Secret Manager
    secret ``gh-stocks-repo-pat``). If unset, log and skip — the
    dead-ticker WARNING is already in stdout.
    """
    token = os.environ.get('GH_DATA_QUALITY_TOKEN', '').strip()
    if not token:
        log.warning('GH_DATA_QUALITY_TOKEN unset — skipping data-quality '
                    'issue. Dead tickers visible only in this log line.')
        return

    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    api = 'https://api.github.com'
    task_idx = os.environ.get('CLOUD_RUN_TASK_INDEX', '0')
    task_cnt = os.environ.get('CLOUD_RUN_TASK_COUNT', '1')
    exec_name = os.environ.get('CLOUD_RUN_EXECUTION', 'unknown-exec')
    ts = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    comment_body = (
        f"### Dead tickers detected — {ts}\n\n"
        f"**Execution:** `{exec_name}` (task {task_idx}/{task_cnt})\n\n"
        f"**{len(dead_tickers)} ticker(s)** returned a permanently-broken "
        "AV reason (Invalid API call / info / no timeseries) for every "
        "month attempted:\n\n```\n"
        + ', '.join(dead_tickers)
        + "\n```\n\n"
        "These should be pruned from "
        "`gcp/fetchers/symbol_lists/earnings_universe.txt` (or whichever "
        "watchlist this run consumed). A pure-dead run is NOT a code bug "
        "and does NOT exit 1 — see CLAUDE.md §3.7."
    )

    # Look for an existing open data-quality issue. Using the labels
    # AND the issue title prefix as the dedupe key so a label-rename
    # doesn't accidentally fork the issue.
    label_q = ','.join(_DQ_LABELS)
    list_url = (f'{api}/repos/{_DQ_REPO}/issues?state=open'
                f'&labels={label_q}&per_page=1')
    resp = requests.get(list_url, headers=headers, timeout=15)
    resp.raise_for_status()
    existing = resp.json()

    if existing:
        issue_number = existing[0]['number']
        comment_url = (
            f'{api}/repos/{_DQ_REPO}/issues/{issue_number}/comments')
        r = requests.post(comment_url, headers=headers,
                          json={'body': comment_body}, timeout=15)
        r.raise_for_status()
        log.info('Appended dead-ticker comment to existing issue #%d',
                 issue_number)
    else:
        title = (f'Data quality: intraday-bulk-backfill — '
                 f'{len(dead_tickers)} dead ticker(s)')
        create_url = f'{api}/repos/{_DQ_REPO}/issues'
        r = requests.post(create_url, headers=headers, json={
            'title': title,
            'body': comment_body,
            'labels': _DQ_LABELS,
        }, timeout=15)
        r.raise_for_status()
        new_num = r.json()['number']
        log.info('Created new data-quality issue #%d for dead tickers',
                 new_num)



# -- Re-framing migration (CLAUDE.md 3.9) -------------------------------------
#
# Two writers used to store AV's naive Eastern wall time as if it were UTC, so
# market_data_intraday holds months in two conventions, and at colliding keys
# the Eastern-labelled bar overwrote the true one. An upsert cannot repair
# that: a row at the wrong key stays there. --replace-months refetches each
# listed (ticker, month) from AV and swaps the whole month in one transaction.

# Every row month M can hold, in either convention, lies in
#   [M-01 02:00Z, (M+1)-01 02:00Z)
#   * Eastern-labelled rows: raw labels 04:00-20:00 on each day of M.
#   * True-UTC rows: 04:00 ET on the 1st (08:00Z EDT / 09:00Z EST) through
#     the 20:00 ET bar on the last day (00:00Z EDT / 01:00Z EST on the next 1st).
#     AV stores a bar AT 20:00 ET; the window must include it (code review C1).
# and no neighbouring month's rows do: M-1's true-UTC rows end at 01:00Z on
# the 1st of M; M+1's labelled rows start at 04:00Z on its 1st. Any boundary
# in (01:00Z, 04:00Z] works; 02:00Z leaves an hour either side.
# tests/gcp/test_intraday_replace_months.py checks this across DST changes.
_WINDOW_HOUR_UTC = 2


def month_replace_window(year: int, month: int) -> tuple[datetime, datetime]:
    """UTC ``[start, end)`` holding every row of (year, month) in either convention."""
    start = datetime(year, month, 1, _WINDOW_HOUR_UTC, tzinfo=timezone.utc)
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    return start, datetime(ny, nm, 1, _WINDOW_HOUR_UTC, tzinfo=timezone.utc)


REPLACE_OK = 'replaced'
REPLACE_DRY = 'dry_run'
REPLACE_INCOMPLETE = 'incomplete_refetch'   # vendor returned fewer sessions than we hold
REPLACE_NOTHING_HELD = 'nothing_held'       # window holds no session; never delete blind
REPLACE_CHANGED = 'changed_during_replace'  # a writer changed the month mid-replace; rolled back


class _HeldChanged(Exception):
    """Raised under the replace lock when the held sessions moved since the
    pre-check; rolls the transaction back."""
# A replaced month holds at most both conventions of each session (x2) plus
# stragglers. Deleting more than this multiple of what is re-inserted means
# something is wrong with the window or the list; the transaction rolls back.
REPLACE_MAX_DELETE_RATIO = 3.0
# A refetched session may hold this share fewer bars than already held
# (rounded down, so a session under 50 bars must be complete) before the
# month is refused as incomplete.
REPLACE_SHORT_TOLERANCE = 0.02


def _held_session_dates(symbol: str, start: datetime, end: datetime, conn=None) -> dict:
    """{Eastern session date: distinct bars held} for the window.

    Reads the window's rows and resolves them with
    lib.eastern_time.stored_intraday_to_eastern, the same rule the Charts API
    reads by: each row placed in its own convention and duplicates left where
    both writers collided counted once. So a session both writers touched
    counts its real bars, not up to twice as many rows, and the 20:00 ET spill
    counts toward the session it closes, never toward a holiday after it (code
    review C1). Weekday sessions only. Strict query: a DB error must never read
    as "nothing held".
    """
    sql = """
        SELECT ts, volume
          FROM market_data_intraday
         WHERE ticker = :t AND interval = '1min' AND ts >= :s AND ts < :e
    """
    params = {'t': symbol, 's': start, 'e': end}
    if conn is None:
        df = query_to_dataframe_strict(sql, params, timeout_s=120)
    else:
        # Inside the replace transaction, under its write lock.
        import sqlalchemy
        res = conn.execute(sqlalchemy.text(sql), params)
        df = pd.DataFrame(res.fetchall(), columns=['ts', 'volume'])
    if df.empty:
        return {}
    idx, keep = stored_intraday_to_eastern(df['ts'], df['volume'])
    days = pd.Series(idx[keep].date).value_counts()
    return {d: int(n) for d, n in days.items() if d.weekday() < 5}


def _held_digest(symbol: str, start: datetime, end: datetime, conn=None) -> str:
    """md5 of every stored row in the window, in ts order, computed
    server-side so only 32 characters cross the wire. Times are rendered as
    epoch values so the text never depends on the session's TimeZone.

    Bar counts cannot see a writer that upserts new values at keys already
    held; this changes on any insert, delete or value update, so the locked
    re-check in replace_month refuses the month rather than let the DELETE
    replace a newer write with an older refetch (Codex P1 on #1185).
    """
    sql = """
        SELECT md5(coalesce(string_agg(concat_ws(',',
                   extract(epoch FROM m.ts), m.open, m.high, m.low, m.close,
                   m.volume, m.data_source, extract(epoch FROM m.inserted_at)),
                   E'\\n' ORDER BY m.ts), '')) AS digest
          FROM market_data_intraday m
         WHERE m.ticker = :t AND m.interval = '1min' AND m.ts >= :s AND m.ts < :e
    """
    params = {'t': symbol, 's': start, 'e': end}
    if conn is None:
        df = query_to_dataframe_strict(sql, params, timeout_s=120)
        return str(df['digest'].iloc[0])
    import sqlalchemy
    return str(conn.execute(sqlalchemy.text(sql), params).scalar_one())


def replace_month(symbol: str, year: int, month: int, api_key: str,
                  commit: bool) -> dict:
    """Refetch one (symbol, month) from AV and swap it in atomically.

    Footprint-preserving: only the sessions the month already holds are
    re-inserted, so the migration re-frames data and never adds coverage the
    table did not have. Nothing is deleted unless the refetch succeeded AND
    contains every held session; a shortfall is reported and the month is left
    untouched.
    """
    start, end = month_replace_window(year, month)
    out = {'symbol': symbol, 'month': f"{year}-{month:02d}", 'deleted': 0,
           'inserted': 0, 'held_sessions': None, 'missing_sessions': 0}
    # Snapshot BEFORE the refetch: a writer that commits while the request is
    # in flight then differs from this snapshot, and the locked re-check in
    # verify() below refuses the month. Snapshotting after the fetch let such
    # bars into ``held`` but not into the refetch, where the shortfall
    # tolerance could pass them and the DELETE erase them (Codex P1 on #1185).
    held = _held_session_dates(symbol, start, end)
    out['held_sessions'] = len(held)
    if not held:
        # Nothing to re-frame: deleting would only remove rows (code review
        # H2), and there is no reason to spend a vendor call finding that out.
        out['status'] = REPLACE_NOTHING_HELD
        return out
    # Content, not just counts: a same-count upsert must also refuse the month.
    # Only a committed run deletes, so only it needs the baseline.
    digest = _held_digest(symbol, start, end) if commit else None
    df, reason = fetch_month(symbol, year, month, api_key)
    if df is None or df.empty or reason != FETCH_OK:
        out['status'] = reason if reason != FETCH_OK else FETCH_NO_TIMESERIES
        return out
    df['ts'] = eastern_index_to_utc(df['ts'])
    df = df.drop_duplicates(subset=['ticker', 'interval', 'ts'])
    session = utc_to_eastern_naive(df['ts']).dt.date
    fetched = session.value_counts()
    # A held session is missing if the refetch lacks it, or returns fewer
    # bars than the distinct bars already held (a partial vendor month that
    # still touches every day, Codex P1 on #1185). REPLACE_SHORT_TOLERANCE
    # absorbs the odd bar AV revises away on a full session; anything more
    # leaves the month untouched.
    # The tolerance is a share of the session, floored, with no absolute
    # minimum: a sparse session (under 50 bars) must come back whole. A fixed
    # 2-bar allowance let 0 of 2 or 1 of 3 through, deleting bars for good
    # (Codex P1 x2 on #1185).
    missing = sorted(
        d for d, n in held.items()
        if int(fetched.get(d, 0)) < n - int(n * REPLACE_SHORT_TOLERANCE))
    out['missing_sessions'] = len(missing)
    if missing:
        out['status'] = REPLACE_INCOMPLETE
        out['missing'] = [f"{d.isoformat()} ({int(fetched.get(d, 0))}/{held[d]})"
                          for d in missing[:10]]
        return out
    df = df[session.isin(set(held))]
    if df.empty:
        out['status'] = REPLACE_NOTHING_HELD
        return out
    if not commit:
        out['status'] = REPLACE_DRY
        out['inserted'] = len(df)
        return out
    def verify(conn) -> None:
        # Under the row locks: the month must still hold exactly what it held
        # before the refetch, in sessions, bar counts and row content. A writer
        # that landed in between would otherwise lose its rows (or its newer
        # values) to the DELETE.
        now = _held_session_dates(symbol, start, end, conn=conn)
        if now != held:
            raise _HeldChanged(f"held sessions changed: {len(held)} -> {len(now)}")
        if _held_digest(symbol, start, end, conn=conn) != digest:
            raise _HeldChanged("held rows changed (same bar counts, new content)")

    try:
        deleted, inserted = replace_rows_in_window(
            df, 'market_data_intraday', {'ticker': symbol, 'interval': '1min'},
            'ts', start, end, chunksize=5000,
            max_delete_ratio=REPLACE_MAX_DELETE_RATIO, verify=verify)
    except (_HeldChanged, WindowChanged) as e:
        out.update(status=REPLACE_CHANGED, detail=str(e))
        return out
    out.update(status=REPLACE_OK, deleted=deleted, inserted=inserted)
    return out


def _read_text(path: str) -> str:
    """Local file or ``gs://bucket/object``. The list is regenerated right
    before a run (gcp/queries/list_intraday_ticker_months.sql) and uploaded,
    so it never goes stale inside an image."""
    if path.startswith('gs://'):
        from google.cloud import storage as gcs
        bucket, _, blob = path[len('gs://'):].partition('/')
        return gcs.Client().bucket(bucket).blob(blob).download_as_text()
    with open(path) as f:
        return f.read()


def _read_replace_list(path: str) -> list[tuple[str, int, int]]:
    """Parse ``TICKER,YYYY-MM`` lines (``#`` comments and a header allowed)."""
    items = []
    for line in _read_text(path).splitlines():
        line = line.split('#', 1)[0].strip()
        if not line or line.lower().startswith('ticker,'):
            continue
        sym, ym = [x.strip() for x in line.split(',')]
        y, m = ym.split('-')
        items.append((sym.upper(), int(y), int(m)))
    return items


def run_replace_months(path: str, commit: bool, limit: Optional[int]) -> int:
    """Drive replace_month over the list; striped across Cloud Run tasks.

    Exits non-zero unless EVERY item reached the expected status (replaced,
    or dry_run without --commit). A rate limit, request error, empty vendor
    month or incomplete refetch leaves that month untouched, which is safe,
    but it means the migration is not done, and a green run must never imply
    it is (the reader cutover depends on it). Each such month is printed as a
    ``RETRY TICKER,YYYY-MM`` line: collect them into the next list.
    """
    items = _read_replace_list(path)
    task_idx = int(os.environ.get('CLOUD_RUN_TASK_INDEX', '0'))
    task_cnt = int(os.environ.get('CLOUD_RUN_TASK_COUNT', '1'))
    items = items[task_idx::task_cnt]
    if limit is not None:
        items = items[:limit]
    api_keys = get_api_keys()
    if not api_keys:
        log.error("No ALPHA_VANTAGE_API_KEY set. Exiting.")
        return 1
    expected = REPLACE_OK if commit else REPLACE_DRY
    log.info("replace-months: task %d/%d, %d ticker-months, commit=%s",
             task_idx, task_cnt, len(items), commit)
    counts: dict = {}
    retry: list[str] = []
    last = 0.0
    # The AV key's RPM is shared by every task, so each task paces at
    # delay x task_count (code review H1): N tasks together stay at the cap.
    pace = _av_cfg.delay_between_calls * max(task_cnt, 1)
    for n, (sym, y, m) in enumerate(items, 1):
        wait = pace - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        last = time.time()
        try:
            r = replace_month(sym, y, m, api_keys[n % len(api_keys)], commit)
        except Exception as e:
            log.error("  ✗ %s %d-%02d SYSTEMIC: %s", sym, y, m, e)
            counts['systemic'] = counts.get('systemic', 0) + 1
            retry.append(f"{sym},{y}-{m:02d}")
            continue
        counts[r['status']] = counts.get(r['status'], 0) + 1
        if r['status'] != expected:
            retry.append(f"{r['symbol']},{r['month']}")
        log.info("  %d/%d %s %s status=%s held_sessions=%s missing_sessions=%d "
                 "deleted=%d inserted=%d%s", n, len(items), r['symbol'], r['month'],
                 r['status'], r['held_sessions'], r['missing_sessions'],
                 r['deleted'], r['inserted'],
                 f" missing={r['missing']}" if r.get('missing') else "")
    log.info("replace-months summary: %s (expected %s for all %d)",
             counts, expected, len(items))
    if retry:
        for item in retry:
            log.error("RETRY %s", item)
        log.error("%d of %d ticker-months did not reach %s; the migration is NOT "
                  "complete. Re-run with the RETRY lines above as the list.",
                  len(retry), len(items), expected)
        return 1
    return 0

def verify_month(symbol: str, year: int, month: int) -> dict:
    """Is one ticker-month fully in the true-UTC convention?

    Reads the month's window (the same read replace_month's snapshot does)
    and runs it through stored_intraday_to_eastern. A migrated month reads
    every row as a true instant and drops nothing; a row read as an Eastern
    label, or a duplicate left where both writers met, means the month still
    holds legacy data. No vendor call.

    Blind spot, by construction: a flat-volume legacy slice confined to one
    ambiguous stretch (no premarket label rows, no opening spike, under half a
    regular session) reads as true UTC here too, as it does in the reader
    (see the reply on #1185). Every month in the migration list either
    reached ``replaced`` or is on the RETRY list, which is the check for those.
    """
    start, end = month_replace_window(year, month)
    df = query_to_dataframe_strict(
        "SELECT ts, volume FROM market_data_intraday "
        "WHERE ticker = :t AND interval = '1min' AND ts >= :s AND ts < :e",
        {'t': symbol, 's': start, 'e': end}, timeout_s=120)
    out = {'symbol': symbol, 'month': f"{year}-{month:02d}", 'rows': len(df),
           'label_rows': 0, 'dropped_rows': 0}
    if df.empty:
        out['status'] = 'empty'
        return out
    inst = pd.DatetimeIndex(pd.to_datetime(df['ts']))
    if inst.tz is None:
        inst = inst.tz_localize('UTC')  # pg8000 TIMESTAMPTZ read in a UTC session
    idx, keep = stored_intraday_to_eastern(inst, df['volume'])
    out['label_rows'] = int((idx != utc_to_eastern_naive(inst)).sum())
    out['dropped_rows'] = int((~keep).sum())
    out['status'] = 'clean' if not (out['label_rows'] or out['dropped_rows']) else 'legacy'
    return out


def run_verify_months(path: str, limit: Optional[int]) -> int:
    """Verify every listed ticker-month; exit non-zero if any is not clean.

    Generate the list from the TABLE (gcp/queries/list_intraday_ticker_months.sql)
    at verification time, not from the migration manifest, so a month the
    manifest omitted is checked too (Codex P1 on #1185). Capacity: one indexed
    window read per item, measured 607 ms for an SPY month (25,174 rows) and
    less for the long tail: 39,311 items over 4 tasks is at most ~1.7 h, with
    no AlphaVantage calls.
    """
    items = _read_replace_list(path)
    task_idx = int(os.environ.get('CLOUD_RUN_TASK_INDEX', '0'))
    task_cnt = int(os.environ.get('CLOUD_RUN_TASK_COUNT', '1'))
    items = items[task_idx::task_cnt]
    if limit is not None:
        items = items[:limit]
    log.info("verify-months: task %d/%d, %d ticker-months", task_idx, task_cnt, len(items))
    counts: dict = {}
    failed: list[str] = []
    for n, (sym, y, m) in enumerate(items, 1):
        r = verify_month(sym, y, m)      # strict: a DB error fails the run loudly
        counts[r['status']] = counts.get(r['status'], 0) + 1
        # Anything but clean fails, empty included: a listed month with no rows
        # is data that went missing after the list was made (Codex P1 on #1185).
        if r['status'] != 'clean':
            failed.append(f"{sym},{y}-{m:02d} status={r['status']} "
                          f"label_rows={r['label_rows']} "
                          f"dropped_rows={r['dropped_rows']} rows={r['rows']}")
        if n % 500 == 0:
            log.info("  verify %d/%d %s", n, len(items), counts)
    log.info("verify-months summary: %s over %d", counts, len(items))
    for line in failed:
        log.error("VERIFY-FAIL %s", line)
    if failed:
        log.error("%d of %d ticker-months are not clean (legacy rows, or empty).",
                  len(failed), len(items))
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description='Fetch AV intraday → Cloud SQL')
    parser.add_argument('--symbol', default='ALL',
                        help='Single symbol, comma- or space-separated list, or ALL '
                             '(SPY IWM QQQ). Examples: --symbol AMD, '
                             '--symbol "AMD NVDA QCOM", --symbol AMD,NVDA,QCOM')
    parser.add_argument('--symbols-file', default=None,
                        help='Path to text file with one ticker per line. Lines '
                             'starting with # are treated as comments. Used by the '
                             'earnings backfill — gives us 50+ tickers without a '
                             'huge --args string in the Cloud Run job spec.')
    parser.add_argument('--start-date', default=None,
                        help='Start date YYYY-MM-DD. Defaults to first of previous month.')
    parser.add_argument('--end-date', default=None,
                        help='End date YYYY-MM-DD. Defaults to today.')
    parser.add_argument('--interval', default='1min',
                        help='Interval (only 1min supported for now)')
    parser.add_argument('--force', action='store_true',
                        help='Re-fetch even if data already exists in GCS')
    parser.add_argument('--replace-months', default=None, metavar='PATH',
                        help='Re-framing migration: file of TICKER,YYYY-MM lines. Each '
                             'month is refetched and swapped in atomically. Dry run '
                             'unless --commit.')
    parser.add_argument('--commit', action='store_true',
                        help='With --replace-months: actually delete and insert.')
    parser.add_argument('--limit', type=int, default=None,
                        help='With --replace-months / --verify-months: process at '
                             'most N items per task.')
    parser.add_argument('--verify-months', default=None, metavar='PATH',
                        help='Read-only: check each TICKER,YYYY-MM holds only true-UTC '
                             'rows. Exits 1 listing VERIFY-FAIL lines otherwise.')
    args = parser.parse_args()

    if args.replace_months and args.verify_months:
        parser.error('--replace-months and --verify-months are separate runs')
    if args.replace_months:
        sys.exit(run_replace_months(args.replace_months, args.commit, args.limit))
    if args.verify_months:
        sys.exit(run_verify_months(args.verify_months, args.limit))

    # Default date range: previous month → today
    today = date.today()
    first_of_prev_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    start_date = args.start_date or first_of_prev_month.strftime('%Y-%m-%d')
    end_date = args.end_date or today.strftime('%Y-%m-%d')

    api_keys = get_api_keys()
    if not api_keys:
        log.error("No ALPHA_VANTAGE_API_KEY set. Exiting.")
        sys.exit(1)

    # Resolve symbols: ALL → SYMBOLS; file → parse; otherwise split on
    # comma/whitespace to support "AMD,NVDA,QCOM" and "AMD NVDA QCOM"
    # uniformly. Allows the Cloud Run job to take a long list via
    # --args="--symbol,AMD NVDA QCOM" without quoting headaches.
    if args.symbols_file:
        with open(args.symbols_file) as f:
            symbols = [
                line.strip().upper() for line in f
                if line.strip() and not line.strip().startswith('#')
            ]
    elif args.symbol == 'ALL':
        symbols = SYMBOLS
    else:
        raw = args.symbol.replace(',', ' ')
        symbols = [s.strip().upper() for s in raw.split() if s.strip()]

    # Cloud Run Job task sharding — when --tasks=N is set on the job,
    # Cloud Run injects CLOUD_RUN_TASK_INDEX (0..N-1) and
    # CLOUD_RUN_TASK_COUNT (=N) into each task's env. We carve the
    # symbol list into N stripes and each task processes its own.
    # Striping rather than contiguous chunking spreads
    # heavyweight (high-volume) tickers across tasks instead of
    # piling them onto task 0 alphabetically.
    task_idx = int(os.environ.get('CLOUD_RUN_TASK_INDEX', '0'))
    task_cnt = int(os.environ.get('CLOUD_RUN_TASK_COUNT', '1'))
    if task_cnt > 1:
        before = len(symbols)
        symbols = symbols[task_idx::task_cnt]
        log.info("  Task %d/%d — processing %d/%d symbols (stripe)",
                 task_idx, task_cnt, len(symbols), before)

    log.info("AlphaVantage Intraday Fetch Job")
    log.info("  Symbols   : %s", symbols)
    log.info("  Date range: %s → %s", start_date, end_date)
    log.info("  API keys  : %d available", len(api_keys))
    log.info("  SQL       : %s", 'yes' if is_cloud_sql_configured() else 'NO')

    # Per-CLAUDE.md Rule 3.7: typed UNAVAILABLE envelope, not silent
    # swallow. We track three buckets so partial failures are surfaced
    # but only SYSTEMIC failures crash the task:
    #   * dead_tickers    — every month returned a permanently-broken
    #                       AV reason (Invalid API call / info / no
    #                       timeseries). Logged WARNING. Not fatal —
    #                       these tickers should be pruned from the
    #                       watchlist on the next manual sweep.
    #   * systemic_errors — process_symbol raised (DB write failed,
    #                       network outage, anything else). Logged
    #                       ERROR. EXIT 1 — the operator must triage.
    #   * (implicit OK)   — at least one month yielded data.
    dead_tickers: list = []
    systemic_errors: list = []
    succeeded = 0
    for symbol in symbols:
        try:
            outcome = process_symbol(
                symbol, start_date, end_date, api_keys, args.force)
        except Exception as e:
            log.error("  ✗ %s SYSTEMIC failure: %s", symbol, e)
            systemic_errors.append(symbol)
            continue
        if outcome == OUTCOME_DEAD:
            dead_tickers.append(symbol)
        elif outcome in (OUTCOME_OK, OUTCOME_SKIPPED):
            succeeded += 1

    log.info("Run summary: %d succeeded, %d dead_tickers, %d systemic",
             succeeded, len(dead_tickers), len(systemic_errors))
    if dead_tickers:
        log.warning("Dead tickers (consider pruning from watchlist): %s",
                    dead_tickers)
        # Cloud Run logs age out after 30d; without a durable record the
        # operator can't act on watchlist pruning. File (or update) a
        # GitHub issue under a distinct label so the dead-ticker view
        # is cumulative across runs and doesn't fight gcp-job-failure
        # for the operator's attention. Issue-filing failure is logged
        # but doesn't fail the task — the dead-ticker data is already
        # in the log line above, and a Discord webhook outage here
        # shouldn't cascade into a fake systemic_error.
        try:
            _file_data_quality_issue(dead_tickers)
        except Exception as e:
            log.error("Failed to file data-quality issue (dead tickers "
                      "already logged above): %s", e)
    if systemic_errors:
        log.error("Systemic failures: %s", systemic_errors)
        sys.exit(1)

    log.info("Done.")


if __name__ == '__main__':
    main()
