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
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Sequence, Tuple

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from lib.eastern_time import (
    eastern_index_to_utc,
    intraday_month_window,
    market_today,
    place_stored_rows,
    session_minute_readings,
    session_schedule,
    stored_intraday_to_eastern,
    utc_now,
    utc_to_eastern_naive,
)

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



def resolve_all_symbols() -> list:
    """--symbol=ALL: the brief tickers (lib.config MarketConfig.tickers), the
    insight default tickers (gcp.insight_pipeline_job.DEFAULT_TICKERS) and
    the watchlist, deduplicated, resolved at run time, so av-intraday-nightly
    stores one-minute bars for every ticker the level parameters are
    calibrated for (FEAT-STRAT-001 per-ticker params, Design 5)."""
    from gcp.calibrate_level_params import brief_insight_watchlist_tickers  # noqa: PLC0415
    return brief_insight_watchlist_tickers()
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
        'outputsize': 'full', 'adjusted': 'false',  # as traded: AV adjusts as of the call unless told not to
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

# The month window and why its boundary is 02:00Z: lib.eastern_time.intraday_month_window.


def month_replace_window(year: int, month: int) -> tuple[datetime, datetime]:
    """UTC ``[start, end)`` holding every row of (year, month) in either convention."""
    return intraday_month_window(year, month)


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

# Tables materialised from market_data_intraday and keyed by (ticker, ts). A
# replace that moves keys leaves their rows at keys no bar has any more (and a
# legacy raw 04:00-07:59Z key has no true-UTC bar at all), so the replace
# deletes the window from each in the same transaction and the run lists the
# rebuilds (Codex P1 on #1185). Each builder recomputes a range:
#   build-intraday-flow --backfill, build-intraday-gex --backfill,
#   build-realtime-gex, strat_data_builder --rebuild.
# The six levels tables are one step further down: computed from the feature
# tables, not from the bars (strat_enrich_levels.backfill_one reads
# strat_features_{tf}), and keyed by (ticker, ts) like them. Left out, a
# replaced month's level rows would sit at keys no feature row has. That
# module rebuilds them, after the feature tables are rebuilt.
DERIVED_TS_TABLES = (
    "intraday_flow_15m", "intraday_gex_15m", "realtime_gex_15m",
    "strat_features_1m", "strat_features_5m", "strat_features_15m",
    "strat_features_30m", "strat_features_60m", "strat_features_4h",
    "strat_features_levels_1m", "strat_features_levels_5m",
    "strat_features_levels_15m", "strat_features_levels_30m",
    "strat_features_levels_60m", "strat_features_levels_4h",
)

# Result tables computed FROM the bars that the migration does NOT touch:
# they hold outcomes people have read, so invalidating them is a separate,
# approved recompute step, not a side effect of the replace (Codex P1 on
# #1185). The run lists every replaced ticker-month (REPLACED lines) and, per
# table, the recompute path or that none exists yet (RECOMPUTE lines). Two
# tables have no correct path today, so a committed run is gated on #1190
# (CLAUDE.md Rule 0.1: the runbook says "do not run X until Y lands" rather
# than naming a command that does not do the job).
BAR_DERIVED_RESULTS = {
    "historical_signals / signal_metrics":
        "FULL regeneration only: run_historical_signals --force deletes every row "
        "for the ticker and strategy, so --start-date must be the ticker's earliest "
        "history (a window-bounded force is #1190)",
    "premarket_analysis outcomes":
        "PLAYBOOK_RESOLVE_DATE=<d> PLAYBOOK_RESOLVE_TICKERS=<t> "
        "PLAYBOOK_RESOLVE_FORCE=true python -m gcp.premarket_playbook_resolver, "
        "per replaced session",
    "signal_alerts exits":
        "NO PATH YET: the EOD resolver never re-selects resolved alerts (#1190)",
    "market_data_daily premarket fields (pre_high/pre_low/pre_vwap/gap_pct)":
        "NO PATH YET: only fetch_market_data computes them, right after its fetch (#1190)",
}
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

    cleared: dict = {}
    try:
        deleted, inserted = replace_rows_in_window(
            df, 'market_data_intraday', {'ticker': symbol, 'interval': '1min'},
            'ts', start, end, chunksize=5000,
            max_delete_ratio=REPLACE_MAX_DELETE_RATIO, verify=verify,
            clear_tables=DERIVED_TS_TABLES, cleared=cleared)
    except (_HeldChanged, WindowChanged) as e:
        out.update(status=REPLACE_CHANGED, detail=str(e))
        return out
    out.update(status=REPLACE_OK, deleted=deleted, inserted=inserted,
               derived_cleared={k: v for k, v in cleared.items() if v})
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
    if not items:
        # A truncated or failed list upload must not read as "nothing to do".
        log.error("replace-months: %s lists no ticker-months; refusing to run.", path)
        return 1
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
    rebuild: dict = {}
    replaced: list[str] = []
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
        if r['status'] == REPLACE_OK:
            replaced.append(f"{r['symbol']},{r['month']}")
        for t, n in (r.get('derived_cleared') or {}).items():
            rebuild[t] = rebuild.get(t, 0) + n
        if r['status'] != expected:
            retry.append(f"{r['symbol']},{r['month']}")
        log.info("  %d/%d %s %s status=%s held_sessions=%s missing_sessions=%d "
                 "deleted=%d inserted=%d%s", n, len(items), r['symbol'], r['month'],
                 r['status'], r['held_sessions'], r['missing_sessions'],
                 r['deleted'], r['inserted'],
                 f" missing={r['missing']}" if r.get('missing') else "")
    log.info("replace-months summary: %s (expected %s for all %d)",
             counts, expected, len(items))
    if rebuild:
        # Derived rows for replaced windows were deleted, not recomputed: the
        # gaps are explicit until each builder re-runs over the range.
        for t in sorted(rebuild):
            log.warning("REBUILD %s rows_cleared=%d", t, rebuild[t])
    if replaced:
        # Results computed from the old bars are still in place until the
        # approved recompute step runs over exactly these windows.
        for item in replaced:
            log.warning("REPLACED %s", item)
        for table, how in BAR_DERIVED_RESULTS.items():
            log.warning("RECOMPUTE %s: %s", table, how)
        if commit:
            log.warning("Tables marked NO PATH YET stay computed from the old bars "
                        "until #1190 lands; the reader cutover is not complete.")
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
    if not items:
        # This is the reader-cutover gate: an empty or header-only list (a
        # failed or truncated upload) must fail, not pass having checked
        # nothing (Codex P1 on #1185). Checked before sharding, since a task
        # may legitimately get no items when the list is shorter than the
        # task count.
        log.error("verify-months: %s lists no ticker-months; nothing was verified.", path)
        return 1
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


# -- Basis check (FEAT-DATA-001, Design C) ------------------------------------
#
# Until 2026-11-13 the 1-min requests returned split- and dividend-adjusted
# prices, adjusted as of the call, so every stored bar sits at the basis of its
# last fetch. A session's basis is read off the daily table: its regular-hours
# high and low against the daily high and low, which are as traded. Read-only.

# market_data_daily.data_source values whose high and low came from the daily
# endpoint (TIME_SERIES_DAILY_ADJUSTED's "2. high" / "3. low", as traded). A
# row stamped alphavantage_1min was built from the session's own 1-min bars, so
# those bars read 1.0 against it whatever basis they are on; a row with any
# other stamp, or none, has an origin the row cannot tell. Neither is ever a
# measure. A new daily writer is measured only once its stamp is added here.
TRUE_DAILY_SOURCES = ("alphavantage_daily", "av_daily_backfill", "av_watched_backfill")
_DAILY_FROM_INTRADAY = "alphavantage_1min"

# The as-traded band, in units of 0.00001 of the ratio: 0.99970 to 1.00030.
_BASIS_UNIT = 100_000
_BASIS_LOW, _BASIS_HIGH = 99_970, 100_030


def session_basis_verdicts(rows: pd.DataFrame, daily: pd.DataFrame,
                           schedule: pd.DataFrame) -> list[dict]:
    """One record per session of *schedule*, in its order: is the session's
    stored 1-min data as traded?

    *rows* is a month window of market_data_intraday (``ts``, ``high``,
    ``low``, ``volume``, ``inserted_at``); *daily* is market_data_daily for the
    ticker (``date``, ``high``, ``low``, ``data_source``); *schedule* is the
    frame lib.eastern_time.session_schedule returns. Nothing is read here.

    Each record has ``session``, ``status`` and ``exact`` (the session's
    reading, lib.eastern_time.session_minute_readings), ``verdict``,
    ``reason``, ``f_high``, ``f_low`` and ``factor``.

    ``verdict``:
      INCOMPLETE  the session is not OK (missing, thin, or its count depends
                  on the timestamp convention): never measured, so thinness
                  cannot read as a basis.
      UNMEASURED  no measurable daily row or no regular-hours high and low;
                  ``reason`` is the first that applies of ``no_daily_row``,
                  ``daily_from_intraday``, ``daily_source_unknown``,
                  ``daily_not_positive``, ``no_rth_high_low``.
      AS-TRADED   f_high and f_low both from 0.99970 to 1.00030, and every row
                  the reading counts is proven a true instant.
      INFERRED    the same ratios, resting on a row that is not proven: never
                  a pass.
      ADJUSTED    both ratios below 0.99970, or both above 1.00030.
      ODD         anything else. Missing minutes can only lower the high and
                  raise the low, moving the ratios apart; an adjustment moves
                  both the same way.

    ``f_high`` is the highest regular-hours 1-min high over the daily high and
    ``f_low`` the lowest low over the daily low, each rounded to 5 decimals;
    ``factor`` is their mean, rounded to 5 decimals. All three are None unless
    the session was measured.
    """
    readings = session_minute_readings(rows["ts"], rows["inserted_at"], schedule)

    daily_by_date: dict = {}
    for day, high, low, source in zip(
            daily["date"], daily["high"], daily["low"], daily["data_source"]):
        # A DATE column comes back as Timestamps (datetime subclasses); a bare
        # date never equals one, so normalise before keying.
        key = day.date() if isinstance(day, datetime) else day
        if key in daily_by_date:
            raise ValueError(f"market_data_daily frame holds {key} twice")
        daily_by_date[key] = (high, low, source)

    placed = None
    out = []
    for reading, opened, closed in zip(
            readings, schedule["market_open"], schedule["market_close"]):
        record = {"session": reading.session, "status": reading.status,
                  "exact": reading.exact, "verdict": "INCOMPLETE", "reason": None,
                  "f_high": None, "f_low": None, "factor": None}
        out.append(record)
        if reading.status != "OK":
            continue

        record["verdict"] = "UNMEASURED"
        if reading.session not in daily_by_date:
            record["reason"] = "no_daily_row"
            continue
        day_high, day_low, source = daily_by_date[reading.session]
        if source == _DAILY_FROM_INTRADAY:
            record["reason"] = "daily_from_intraday"
            continue
        if source not in TRUE_DAILY_SOURCES:
            record["reason"] = "daily_source_unknown"
            continue
        if pd.isna(day_high) or pd.isna(day_low) or day_high <= 0 or day_low <= 0:
            record["reason"] = "daily_not_positive"
            continue

        if placed is None:
            # Once, over the whole window: the resolver must see each date entire.
            placed = place_stored_rows(rows["ts"], rows["volume"], rows["inserted_at"])
        instants, keep, _proven = placed
        rth = keep & ((instants >= opened) & (instants < closed))
        highs = pd.to_numeric(rows["high"][rth], errors="raise").dropna()
        lows = pd.to_numeric(rows["low"][rth], errors="raise").dropna()
        if highs.empty or lows.empty:
            record["reason"] = "no_rth_high_low"
            continue

        high_units = round(float(highs.max()) / float(day_high) * _BASIS_UNIT)
        low_units = round(float(lows.min()) / float(day_low) * _BASIS_UNIT)
        record["reason"] = None
        record["f_high"] = high_units / _BASIS_UNIT
        record["f_low"] = low_units / _BASIS_UNIT
        record["factor"] = round((record["f_high"] + record["f_low"]) / 2, 5)
        high_in = _BASIS_LOW <= high_units <= _BASIS_HIGH
        low_in = _BASIS_LOW <= low_units <= _BASIS_HIGH
        if high_in and low_in:
            record["verdict"] = "AS-TRADED" if reading.exact else "INFERRED"
        elif (high_units < _BASIS_LOW and low_units < _BASIS_LOW) or (
                high_units > _BASIS_HIGH and low_units > _BASIS_HIGH):
            record["verdict"] = "ADJUSTED"
        else:
            record["verdict"] = "ODD"
    return out


# The basis check covers the three tickers the session scan covers.
BASIS_TICKERS = ("SPY", "QQQ", "IWM")

_BASIS_BARS_SQL = """
    SELECT ts, high, low, volume, inserted_at
      FROM market_data_intraday
     WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end
"""
_BASIS_DAILY_SQL = """
    SELECT date, high, low, data_source
      FROM market_data_daily
     WHERE ticker = :t AND date >= :first AND date <= :last
"""
_UNMEASURED_REASONS = ("no_daily_row", "daily_from_intraday", "daily_source_unknown",
                       "daily_not_positive", "no_rth_high_low")


def _month_last_day(year: int, month: int) -> date:
    first_of_next = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return first_of_next - timedelta(days=1)


def run_verify_basis(path: str, now_utc: Optional[datetime] = None) -> int:
    """Say which listed ticker-months hold 1-min sessions that are not as traded.

    Read-only, no vendor call. One bars read per listed ticker-month (the
    month window) and one market_data_daily read per ticker over the span of
    its listed months; both strict, so a failed read ends the run with a
    traceback and no summary line. One month's bars are in memory at a time.
    Not striped across Cloud Run tasks and not limited: the list is at most 3
    tickers by 143 months.

    A month's sessions are the calendar's sessions of that month whose close
    has passed at *now_utc* (aware UTC; default: now). Lines, printed (not
    logged), one per ticker-month and kind that counts at least one session:

      BASIS-FAIL T YYYY-MM sessions=N first..last factor=MIN..MAX inferred=N
      EMPTY T YYYY-MM                       (a listed month with no rows)
      UNMEASURED T YYYY-MM sessions=N first..last <reason>=N ...
      INCOMPLETE T YYYY-MM sessions=N first..last inexact=N
      INFERRED T YYYY-MM sessions=N first..last
      ODD T YYYY-MM-DD high=F low=F exact=yes|no   (one per session)
      verify-basis summary: ...             (last; a run without it crashed)

    Returns the exit code:
      1  a BASIS-FAIL or EMPTY line was printed; or the list has no lines or
         names a ticker other than SPY, QQQ and IWM (before any query);
      3  none of that, and a line rests on a row that is not proven a true
         instant: an INFERRED line, an INCOMPLETE line with inexact above 0,
         or an ODD line with exact=no;
      0  otherwise: every measured session is AS-TRADED from proven rows, and
         every session that was not measured is exact and listed. It does not
         say every session was measured; the lines and the summary do.
    """
    items = list(dict.fromkeys(_read_replace_list(path)))
    if not items:
        # A truncated or failed list upload must fail, not pass having
        # checked nothing.
        log.error("verify-basis: %s lists no ticker-months; nothing was checked.", path)
        return 1
    others = sorted({sym for sym, _, _ in items if sym not in BASIS_TICKERS})
    if others:
        log.error("verify-basis: %s names %s; only %s are checked. Nothing was read.",
                  path, ", ".join(others), ", ".join(BASIS_TICKERS))
        return 1
    now = utc_now() if now_utc is None else now_utc

    span: dict = {}
    for sym, y, m in items:
        first, last = span.get(sym, ((y, m), (y, m)))
        span[sym] = (min(first, (y, m)), max(last, (y, m)))

    daily_frames: dict = {}
    totals = {"AS-TRADED": 0, "INFERRED": 0, "ADJUSTED": 0, "ODD": 0,
              "UNMEASURED": 0, "INCOMPLETE": 0}
    empty_months = 0
    failed = False       # a BASIS-FAIL or EMPTY line
    unproven = False     # a line that rests on a row that is not proven

    for sym, y, m in items:
        label = f"{sym} {y}-{m:02d}"
        if sym not in daily_frames:
            (fy, fm), (ly, lm) = span[sym]
            daily_frames[sym] = query_to_dataframe_strict(
                _BASIS_DAILY_SQL,
                {"t": sym, "first": date(fy, fm, 1), "last": _month_last_day(ly, lm)},
                timeout_s=120)
        start, end = intraday_month_window(y, m)
        rows = query_to_dataframe_strict(
            _BASIS_BARS_SQL, {"t": sym, "start": start, "end": end}, timeout_s=120)
        if rows.empty:
            # Data that went missing after the list was made.
            print(f"EMPTY {label}")
            empty_months += 1
            failed = True
            continue

        schedule = session_schedule(date(y, m, 1), _month_last_day(y, m))
        # A session still trading (or not yet open) is not read at all: it is
        # neither incomplete nor counted.
        schedule = schedule[schedule["market_close"] <= now]
        records = session_basis_verdicts(rows, daily_frames[sym], schedule)
        del rows
        by_verdict: dict = {}
        for r in records:
            by_verdict.setdefault(r["verdict"], []).append(r)
            totals[r["verdict"]] += 1

        def span_of(group: list) -> str:
            return f"{group[0]['session'].isoformat()}..{group[-1]['session'].isoformat()}"

        adjusted = by_verdict.get("ADJUSTED", [])
        if adjusted:
            factors = [r["factor"] for r in adjusted]
            print(f"BASIS-FAIL {label} sessions={len(adjusted)} {span_of(adjusted)} "
                  f"factor={min(factors):.5f}..{max(factors):.5f} "
                  f"inferred={sum(1 for r in adjusted if not r['exact'])}")
            failed = True
        unmeasured = by_verdict.get("UNMEASURED", [])
        if unmeasured:
            reasons = " ".join(
                f"{name}={sum(1 for r in unmeasured if r['reason'] == name)}"
                for name in _UNMEASURED_REASONS)
            print(f"UNMEASURED {label} sessions={len(unmeasured)} "
                  f"{span_of(unmeasured)} {reasons}")
        incomplete = by_verdict.get("INCOMPLETE", [])
        if incomplete:
            inexact = sum(1 for r in incomplete if not r["exact"])
            print(f"INCOMPLETE {label} sessions={len(incomplete)} "
                  f"{span_of(incomplete)} inexact={inexact}")
            unproven = unproven or inexact > 0
        inferred = by_verdict.get("INFERRED", [])
        if inferred:
            print(f"INFERRED {label} sessions={len(inferred)} {span_of(inferred)}")
            unproven = True
        for r in by_verdict.get("ODD", []):
            print(f"ODD {sym} {r['session'].isoformat()} high={r['f_high']:.5f} "
                  f"low={r['f_low']:.5f} exact={'yes' if r['exact'] else 'no'}")
            unproven = unproven or not r["exact"]

    print(f"verify-basis summary: months={len(items)} as_traded={totals['AS-TRADED']} "
          f"inferred={totals['INFERRED']} adjusted={totals['ADJUSTED']} "
          f"odd={totals['ODD']} unmeasured={totals['UNMEASURED']} "
          f"incomplete={totals['INCOMPLETE']} empty={empty_months}")
    if failed:
        return 1
    return 3 if unproven else 0


# -- Bucket files of the bars (FEAT-DATA-001, Design E) ------------------------


def _run_bars_export(tickers: Sequence[str], months: Sequence[tuple[int, int]]) -> bool:
    """Write *months* of *tickers* to the bucket; True only when every month
    was written.

    The bars are already in Cloud SQL when this runs, so a failed export does
    not undo the fetch, but it is never reported as success: the failure is
    logged with its traceback, as an outage or as a defect
    (lib.infra_errors), False is returned, and main() exits 1.
    """
    from gcp.fetchers import export_intraday_bars  # noqa: PLC0415
    from lib.infra_errors import is_infrastructure_error  # noqa: PLC0415

    try:
        done = export_intraday_bars.export_window(tickers, months)
    except Exception as exc:
        kind = "outage" if is_infrastructure_error(exc) else "defect"
        log.error("bars export failed (%s): %s", kind, exc, exc_info=True)
        return False
    log.info("bars export: %d months, %d rows, %.1f s",
             done["months"], done["rows"], done["seconds"])
    return True


def run_export_bars_from(first: tuple[int, int], symbol: str) -> int:
    """Write every month from *first* (year, month) to the current Eastern
    month to the bucket, for SPY, QQQ and IWM (*symbol* ``ALL``) or the one of
    them *symbol* names. Fetches nothing and needs no API key. Returns the
    exit code.

    An explicit export never ends quietly: more than one Cloud Run task (each
    would write the same months at once), a ticker other than the three, the
    database not configured, ``GCS_BUCKET`` unset, or no month to write all
    return 1, each before any query. The manifest is written after each
    month, so a run that stops keeps what it wrote and a rerun converges.
    """
    from gcp.fetchers.export_intraday_bars import (  # noqa: PLC0415
        EXPORT_TICKERS,
        months_between,
    )

    task_cnt = int(os.environ.get('CLOUD_RUN_TASK_COUNT', '1'))
    if task_cnt > 1:
        log.error("export-bars-from: %d Cloud Run tasks would each write the same "
                  "months; run it as one task. Nothing was read.", task_cnt)
        return 1
    name = symbol.strip().upper()
    if name == 'ALL':
        tickers = tuple(EXPORT_TICKERS)
    elif name in EXPORT_TICKERS:
        tickers = (name,)
    else:
        log.error("export-bars-from: --symbol %r; only ALL or one of %s is exported. "
                  "Nothing was read.", symbol, ", ".join(EXPORT_TICKERS))
        return 1
    if not is_cloud_sql_configured():
        log.error("export-bars-from: the database is not configured. Nothing was read.")
        return 1
    if not os.environ.get('GCS_BUCKET', '').strip():
        log.error("export-bars-from: GCS_BUCKET is not set. Nothing was read.")
        return 1
    today = market_today()
    months = months_between(tuple(first), (today.year, today.month))
    if not months:
        log.error("export-bars-from: %d-%02d is after the current Eastern month "
                  "%d-%02d. Nothing was read.", first[0], first[1], today.year, today.month)
        return 1
    return 0 if _run_bars_export(tickers, months) else 1


def main():
    parser = argparse.ArgumentParser(description='Fetch AV intraday → Cloud SQL')
    parser.add_argument('--symbol', default='ALL',
                        help='Single symbol, comma- or space-separated list, or ALL '
                             '(the brief tickers, the insight default tickers and the '
                             'watchlist, resolved at run time). Examples: --symbol AMD, '
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
    parser.add_argument('--verify-basis', default=None, metavar='PATH',
                        help='Read-only, no vendor call: for each TICKER,YYYY-MM line '
                             '(SPY, QQQ and IWM only) say which sessions are not stored '
                             'as traded. A local file or a gs:// object, e.g. '
                             '--verify-basis=gs://adept-mountain-474619-d4-trading-data/'
                             'intraday-lists/<name>.csv. Exits 1 on a BASIS-FAIL or EMPTY '
                             'line, 3 when a line rests on a row that is not proven a '
                             'true instant, else 0.')
    parser.add_argument('--export-bars-from', default=None, metavar='YYYY-MM',
                        help='Fetches nothing: writes every month from the one given '
                             'to the current Eastern month of the stored 1-min bars '
                             'to the bucket, one file per ticker-month and a manifest, '
                             'for SPY, QQQ and IWM or the one of them named by '
                             '--symbol. One task. Run per ticker, e.g. '
                             '--args="--export-bars-from=2015-01,--symbol=SPY".')
    args = parser.parse_args()

    list_modes = [flag for flag, value in (
        ('--replace-months', args.replace_months),
        ('--verify-months', args.verify_months),
        ('--verify-basis', args.verify_basis),
        ('--export-bars-from', args.export_bars_from)) if value]
    if len(list_modes) > 1:
        parser.error(f"{' and '.join(list_modes)} are separate runs")
    if args.export_bars_from:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", args.export_bars_from):
            parser.error(f"--export-bars-from takes a month as YYYY-MM, "
                         f"not {args.export_bars_from!r}")
        export_first = (int(args.export_bars_from[:4]), int(args.export_bars_from[5:]))
        export_today = market_today()
        if export_first > (export_today.year, export_today.month):
            parser.error(f"--export-bars-from {args.export_bars_from} is after the "
                         f"current Eastern month "
                         f"{export_today.year}-{export_today.month:02d}")
        if args.symbols_file or args.start_date or args.end_date:
            parser.error("--export-bars-from fetches nothing: it takes --symbol and "
                         "no --symbols-file, --start-date or --end-date")
        sys.exit(run_export_bars_from(export_first, args.symbol))
    if args.replace_months:
        sys.exit(run_replace_months(args.replace_months, args.commit, args.limit))
    if args.verify_months:
        sys.exit(run_verify_months(args.verify_months, args.limit))
    if args.verify_basis:
        sys.exit(run_verify_basis(args.verify_basis))

    # Default date range: previous month → today
    today = date.today()
    first_of_prev_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    start_date = args.start_date or first_of_prev_month.strftime('%Y-%m-%d')
    end_date = args.end_date or today.strftime('%Y-%m-%d')

    api_keys = get_api_keys()
    if not api_keys:
        log.error("No ALPHA_VANTAGE_API_KEY set. Exiting.")
        sys.exit(1)

    # Resolve symbols: ALL → resolve_all_symbols(); file → parse; otherwise split on
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
        symbols = resolve_all_symbols()
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

    # The nightly run also writes the bars of SPY, QQQ and IWM to the bucket,
    # after its fetch: the current Eastern month and the one before it. The
    # trigger is the nightly's own argument shape (--symbol=ALL --force, no
    # dates, no symbols file, one task), so the monthly run, a dated run and
    # the striped bulk backfill never export. It runs when a ticker failed
    # too; the exit is 1 if either failed. The months come from the exchange's
    # date: at 21:00 ET the container's date is already the next day.
    export_failed = False
    if (args.symbol == 'ALL' and not args.symbols_file and args.force
            and not args.start_date and not args.end_date and task_cnt == 1):
        if os.environ.get('INTRADAY_BARS_EXPORT', '').strip().lower() == 'off':
            log.info("bars export skipped: INTRADAY_BARS_EXPORT is off")
        elif not is_cloud_sql_configured():
            log.info("bars export skipped: the database is not configured")
        else:
            from gcp.fetchers.export_intraday_bars import (  # noqa: PLC0415
                EXPORT_TICKERS,
                nightly_months,
            )
            export_failed = not _run_bars_export(
                EXPORT_TICKERS, nightly_months(market_today()))

    if systemic_errors:
        log.error("Systemic failures: %s", systemic_errors)
        sys.exit(1)
    if export_failed:
        sys.exit(1)

    log.info("Done.")


if __name__ == '__main__':
    main()
