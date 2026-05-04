#!/usr/bin/env python3
"""
Cloud Run Job: prune stale rows from earnings_calendar, market_data_daily,
and market_data_intraday so the working set tracks the in-window earnings
universe + curated watchlist + always-on static set instead of accumulating
indefinitely.

Why this exists
---------------
Through 2026-04 the daily fetcher kept upserting OHLC for any ticker that
ever appeared in earnings_calendar. Tickers that fell out of the window
(reported >21d ago, or moved past +14d ahead) kept their daily rows but
never got refreshed — stale, wasting query budget on every reaction-window
join. earnings_calendar itself accumulates ~9k rows where we only need
~7.5k in-window. The audit on 2026-05-04 found 1,499 stale rows / 1,497
stale tickers in earnings_calendar, 31 stale in market_data_daily,
and 8 stale in market_data_intraday.

Per the user directive (2026-05-04): stale tickers are DROPPED, not
archived. Re-fetching when a ticker rotates back into the window is
cheap (one AV TIME_SERIES_DAILY_ADJUSTED call → 100 bars). The static
SPY/IWM/QQQ/SPX set is always preserved regardless of window.

Active-ticker set (preserved):
    - earnings_calendar tickers in [today - WINDOW_BACK_DAYS,
      today + WINDOW_AHEAD_DAYS]   (default: 21 back, 14 ahead)
    - watchlists table (any active row, all surfaces)
    - STATIC_SET hard-coded in fetch_market_data.TICKERS

earnings_reactions is INTENTIONALLY NOT pruned — historical reaction
rows are useful even for tickers no longer in the window, and the table
isn't the bottleneck. Re-confirmed with user 2026-05-04.

Usage:
    python -m gcp.cleanup_stale_data --dry-run    # report counts only
    python -m gcp.cleanup_stale_data              # actually delete

Environment:
    CLEANUP_WINDOW_BACK_DAYS   default 21
    CLEANUP_WINDOW_AHEAD_DAYS  default 14
    CLOUD_SQL_CONNECTION_NAME / DB_USER / DB_PASS / DB_NAME

Capacity (CLAUDE.md §0):
    - 4 SQL DELETEs total (one count + one delete per table)
    - DELETEs are bounded by single SQL statements (no row iteration)
    - Wall clock: ~10 seconds for 1.5k row deletes against Cloud SQL
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.logging_config import setup_logging  # noqa: E402

setup_logging()
log = logging.getLogger(__name__)


# Always-on static set — these tickers are essential infrastructure
# (index proxies the brief, ranker, and signal monitor depend on)
# regardless of whether they're in any earnings window. Kept in sync
# with gcp.fetchers.fetch_market_data.TICKERS.
STATIC_SET = ('IWM', 'SPY', 'QQQ', 'SPX')


def _window_days() -> tuple[int, int]:
    back = int(os.environ.get('CLEANUP_WINDOW_BACK_DAYS', '21'))
    ahead = int(os.environ.get('CLEANUP_WINDOW_AHEAD_DAYS', '14'))
    return back, ahead


def _scalar(sql: str, params: dict | None = None) -> int:
    """Run a SELECT that returns a single integer (e.g. COUNT(*))."""
    from gcp.database import query_to_dataframe
    df = query_to_dataframe(sql, params or {})
    if df.empty:
        return 0
    return int(df.iloc[0, 0])


def _execute(sql: str, params: dict | None = None) -> int:
    """Execute a write SQL and return rowcount. Idempotent: a no-op
    re-run on already-clean state returns 0 with no errors."""
    from gcp.database import get_engine
    import sqlalchemy
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(sqlalchemy.text(sql), params or {})
        return int(result.rowcount or 0)


def _build_active_ticker_set() -> list[str]:
    """Active = in-window calendar ∪ watchlists ∪ STATIC_SET.

    Built BEFORE cleanup_earnings_calendar so newly-rotated-out tickers
    are correctly identified as inactive and their daily/intraday bars
    can be pruned in the same run.
    """
    from gcp.database import query_to_dataframe
    back, ahead = _window_days()
    sql = """
        SELECT DISTINCT ticker FROM earnings_calendar
         WHERE earnings_date BETWEEN
            CURRENT_DATE - (:back || ' days')::interval AND
            CURRENT_DATE + (:ahead || ' days')::interval
        UNION
        SELECT ticker FROM watchlists
         WHERE removed_at IS NULL
    """
    df = query_to_dataframe(sql, {'back': back, 'ahead': ahead})
    active = {str(t).upper() for t in df['ticker'].tolist()} if not df.empty else set()
    active.update(STATIC_SET)
    return sorted(active)


def cleanup_earnings_calendar(active: list[str], dry_run: bool) -> tuple[int, int]:
    """Delete earnings_calendar rows OUTSIDE the in-window range.

    Returns (before_count, deleted_count). active is unused here — the
    cut is purely date-based — but we keep the parameter symmetric with
    the OHLC cleanups for caller readability.
    """
    back, ahead = _window_days()
    before = _scalar("SELECT COUNT(*) FROM earnings_calendar")
    in_window = _scalar(
        """
        SELECT COUNT(*) FROM earnings_calendar
         WHERE earnings_date BETWEEN
            CURRENT_DATE - (:back || ' days')::interval AND
            CURRENT_DATE + (:ahead || ' days')::interval
        """,
        {'back': back, 'ahead': ahead},
    )
    candidates = before - in_window
    log.info(
        "  earnings_calendar: %d total / %d in-window [-%dd..+%dd] / %d to delete",
        before, in_window, back, ahead, candidates,
    )
    if dry_run or candidates == 0:
        return before, 0

    deleted = _execute(
        """
        DELETE FROM earnings_calendar
         WHERE earnings_date NOT BETWEEN
            CURRENT_DATE - (:back || ' days')::interval AND
            CURRENT_DATE + (:ahead || ' days')::interval
        """,
        {'back': back, 'ahead': ahead},
    )
    log.info("  ✓ deleted %d rows from earnings_calendar", deleted)
    return before, deleted


def cleanup_market_data_daily(active: list[str], dry_run: bool) -> tuple[int, int]:
    """Delete market_data_daily rows for tickers NOT in the active set.

    All rows for a stale ticker go (we don't need partial OHLC for a
    ticker we're not refreshing — re-fetching from AV gives us full
    history again the moment it rotates back in).
    """
    if not active:
        log.warning("  market_data_daily: empty active set — refusing to wipe table")
        return 0, 0
    n_distinct = _scalar("SELECT COUNT(DISTINCT ticker) FROM market_data_daily")
    n_active = _scalar(
        """SELECT COUNT(DISTINCT ticker) FROM market_data_daily
            WHERE ticker = ANY(:active)""",
        {'active': active},
    )
    n_stale_tickers = n_distinct - n_active
    rows_before = _scalar("SELECT COUNT(*) FROM market_data_daily")
    log.info(
        "  market_data_daily: %d rows / %d tickers (%d active, %d stale)",
        rows_before, n_distinct, n_active, n_stale_tickers,
    )
    if dry_run or n_stale_tickers == 0:
        return rows_before, 0

    deleted = _execute(
        "DELETE FROM market_data_daily WHERE ticker <> ALL(:active)",
        {'active': active},
    )
    log.info("  ✓ deleted %d rows from market_data_daily", deleted)
    return rows_before, deleted


def cleanup_market_data_intraday(active: list[str], dry_run: bool) -> tuple[int, int]:
    """Delete market_data_intraday rows for tickers NOT in the active set."""
    if not active:
        log.warning("  market_data_intraday: empty active set — refusing to wipe table")
        return 0, 0
    n_distinct = _scalar("SELECT COUNT(DISTINCT ticker) FROM market_data_intraday")
    n_active = _scalar(
        """SELECT COUNT(DISTINCT ticker) FROM market_data_intraday
            WHERE ticker = ANY(:active)""",
        {'active': active},
    )
    n_stale_tickers = n_distinct - n_active
    rows_before = _scalar("SELECT COUNT(*) FROM market_data_intraday")
    log.info(
        "  market_data_intraday: %d rows / %d tickers (%d active, %d stale)",
        rows_before, n_distinct, n_active, n_stale_tickers,
    )
    if dry_run or n_stale_tickers == 0:
        return rows_before, 0

    deleted = _execute(
        "DELETE FROM market_data_intraday WHERE ticker <> ALL(:active)",
        {'active': active},
    )
    log.info("  ✓ deleted %d rows from market_data_intraday", deleted)
    return rows_before, deleted


def run(dry_run: bool = False) -> dict:
    """Top-level driver. Returns a per-table {before, deleted} dict."""
    from gcp.database import is_cloud_sql_configured
    if not is_cloud_sql_configured():
        log.error("Cloud SQL not configured — cleanup cannot proceed")
        sys.exit(1)

    log.info("cleanup_stale_data: dry_run=%s", dry_run)

    # IMPORTANT: build the active set FIRST, before pruning
    # earnings_calendar. Pruning the calendar first would reduce the
    # active set in the same run and could erase OHLC for tickers that
    # would otherwise still qualify under the original window.
    active = _build_active_ticker_set()
    log.info("Active ticker set: %d tickers (sample: %s%s)",
             len(active), active[:10], '...' if len(active) > 10 else '')

    # Order: calendar → daily → intraday. Symmetric outcome regardless.
    cal_before, cal_deleted = cleanup_earnings_calendar(active, dry_run)
    daily_before, daily_deleted = cleanup_market_data_daily(active, dry_run)
    intra_before, intra_deleted = cleanup_market_data_intraday(active, dry_run)

    summary = {
        'dry_run': dry_run,
        'active_count': len(active),
        'earnings_calendar': {'before': cal_before, 'deleted': cal_deleted},
        'market_data_daily': {'before': daily_before, 'deleted': daily_deleted},
        'market_data_intraday': {'before': intra_before, 'deleted': intra_deleted},
    }
    log.info("cleanup_stale_data done: %s", summary)
    return summary


def main():
    p = argparse.ArgumentParser(description="Prune stale data from Cloud SQL.")
    p.add_argument('--dry-run', action='store_true',
                   help="Report counts only; perform no deletes.")
    args = p.parse_args()
    run(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
