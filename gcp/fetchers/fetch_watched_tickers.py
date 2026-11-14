"""Watched-ticker ingest job (fetch-watched-tickers), v2.

This module holds the job's config, the read of the watched set from Cloud
SQL with its exact overflow, and the second-guard dedup. Later steps add the
session check, coverage, indicators and verification.

CLAUDE.md Rule 3.7: a failed set read raises ``SetReadError``; it is never
an empty set. An empty frame from a read that ran is a legitimate zero.
"""
from __future__ import annotations

import logging
import numbers
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Iterable, Mapping, Sequence

import pandas as pd

from gcp.fetchers import fetch_market_data
from gcp.fetchers.fetch_market_data import (
    BACKFILL_DEPTH_THRESHOLD_BARS,
    _pick_backfill_outputsize,
)
from lib.eastern_time import is_session

log = logging.getLogger(__name__)

JOB_NAME = 'fetch-watched-tickers'
WATCHED_DATA_SOURCE = 'av_watched_backfill'

# Same bound the other fetchers in gcp/fetchers/ put on a single statement
# (fetch_alphavantage_intraday.py passes timeout_s=120 to the strict reader).
_SET_QUERY_TIMEOUT_S = 120

# Tickers with at least one active membership, minus the static list, oldest
# first. ``COUNT(*) OVER ()`` is computed before LIMIT, so every row carries
# the full eligible count and the overflow is exact however many LIMIT cut.
# user_watchlists is named only inside the EXISTS predicate and no owner
# column is selected: the job needs tickers, never who watches them.
WATCHED_SET_SQL = (
    "SELECT w.ticker, COUNT(*) OVER () AS eligible_total FROM watched_tickers w "
    "WHERE EXISTS (SELECT 1 FROM user_watchlists u WHERE u.ticker = w.ticker AND u.removed_at IS NULL) "
    "AND w.ticker <> ALL(:exclude) "
    "ORDER BY w.created_at LIMIT :limit"
)


class SetReadError(RuntimeError):
    """The watched set could not be read or the result is malformed."""


@dataclass(frozen=True)
class Config:
    max_tickers: int = 50

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> 'Config':
        raw = env.get('WATCHED_TICKERS_MAX')
        if raw is None:
            return cls()
        try:
            return cls(max_tickers=int(raw))
        except ValueError as e:
            raise ValueError(f'WATCHED_TICKERS_MAX must be an integer, got {raw!r}') from e


# The strict reader's shape: query(sql, params, timeout_s=...)
Query = Callable[..., pd.DataFrame]


@dataclass(frozen=True)
class WatchedSet:
    tickers: list[str]
    eligible_total: int
    overflow: int


def read_watched_set(query: Query, exclude: Sequence[str], max_tickers: int) -> WatchedSet:
    try:
        df = query(WATCHED_SET_SQL,
                   {'limit': max_tickers, 'exclude': list(exclude)},
                   timeout_s=_SET_QUERY_TIMEOUT_S)
    except Exception as e:
        raise SetReadError(f'watched set read failed: {e}') from e
    if df is None or 'ticker' not in df.columns:
        raise SetReadError('watched set read returned no ticker column')
    if df.empty:
        return WatchedSet(tickers=[], eligible_total=0, overflow=0)
    if 'eligible_total' not in df.columns:
        raise SetReadError('watched set read returned no eligible_total column')

    tickers: list[str] = []
    for t in df['ticker']:
        if not isinstance(t, str) or not t.strip():
            raise SetReadError(f'watched set has a null or non-string ticker: {t!r}')
        tickers.append(t.strip().upper())

    totals = set()
    for n in df['eligible_total']:
        if isinstance(n, bool) or not isinstance(n, numbers.Integral):
            raise SetReadError(f'eligible_total is missing or not an integer: {n!r}')
        totals.add(int(n))
    if len(totals) != 1:
        raise SetReadError(f'eligible_total differs between rows: {sorted(totals)}')
    total = totals.pop()
    return WatchedSet(tickers=tickers, eligible_total=total,
                      overflow=total - len(tickers))


def dedup(tickers: list[str], exclude: Iterable[str]) -> list[str]:
    """Order-preserving unique, dropping ``exclude``: a second guard behind the query."""
    drop = {t.strip().upper() for t in exclude}
    seen: set[str] = set()
    out: list[str] = []
    for t in tickers:
        t = t.strip().upper()
        if t in drop or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def resolve_session(today: date) -> date | None:
    """``today`` when NYSE trades that day, else ``None`` (weekend or holiday)."""
    return today if is_session(today) else None


# ── coverage and the plan of pulls ──────────────────────────────────────

# Stamp for rows this job writes for a ticker another writer already owns: it
# keeps the all-history backfill union (which skips av_watched_backfill) true
# for an existing orphan.
_OTHER_WRITER_SOURCE = 'av_daily_backfill'

COVERAGE_SQL = (
    "SELECT ticker, COUNT(*) AS bar_count, MAX(date) AS max_date, "
    "bool_or(data_source = 'av_watched_backfill') AS bootstrapped "
    "FROM market_data_daily WHERE ticker = ANY(:kept) GROUP BY ticker"
)


@dataclass(frozen=True)
class Coverage:
    ticker: str
    bar_count: int
    max_date: date | None
    bootstrapped: bool


def _as_date(v) -> date | None:
    """A frame's max_date (date, Timestamp or NaT) as a date, or None."""
    if v is None or pd.isna(v):
        return None
    if isinstance(v, datetime):  # Timestamp is a datetime
        return v.date()
    return v


def read_coverage(kept: list[str], query: Query | None = None) -> dict[str, Coverage]:
    """Stored coverage per kept ticker, in ``kept`` order.

    Strict read: a failure raises (Rule 3.7). A ticker with no rows is the
    explicit ``Coverage(t, 0, None, False)``, a true "no rows" state.
    """
    if query is None:
        from gcp.database import query_to_dataframe_strict as query
    df = query(COVERAGE_SQL, {'kept': list(kept)}, timeout_s=_SET_QUERY_TIMEOUT_S)
    found: dict[str, Coverage] = {}
    for _, r in df.iterrows():
        t = r['ticker']
        found[t] = Coverage(t, int(r['bar_count']), _as_date(r['max_date']),
                            bool(r['bootstrapped']))
    return {t: found.get(t, Coverage(t, 0, None, False)) for t in kept}


def _pick_watched_outputsize(bar_count: int, max_date: date | None,
                             bootstrapped: bool, today: date) -> str | None:
    """'full', 'compact' or None (nothing to pull).

    A bar dated today or later (a stray future-dated bar included) is current,
    never a negative staleness. A bootstrapped ticker is judged as if it had
    the depth threshold, since this job only ever bootstraps it to compact depth.
    """
    if bar_count == 0:
        return 'full'
    max_date = _as_date(max_date)
    if max_date is not None and max_date >= today:
        return None
    if bootstrapped:
        return _pick_backfill_outputsize(
            max(bar_count, BACKFILL_DEPTH_THRESHOLD_BARS), max_date, today)
    return _pick_backfill_outputsize(bar_count, max_date, today)


def stamp_for(cov: Coverage) -> str:
    """The data_source this job writes for ``cov``'s ticker."""
    if cov.bar_count == 0 or cov.bootstrapped:
        return WATCHED_DATA_SOURCE
    return _OTHER_WRITER_SOURCE


def plan_pulls(coverages: dict[str, Coverage],
               today: date) -> dict[tuple[str, str], list[str]]:
    """{(outputsize, data_source): tickers}; tickers needing nothing are omitted."""
    plan: dict[tuple[str, str], list[str]] = {}
    for t, cov in coverages.items():
        size = _pick_watched_outputsize(cov.bar_count, cov.max_date,
                                        cov.bootstrapped, today)
        if size is None:
            continue
        plan.setdefault((size, stamp_for(cov)), []).append(t)
    return plan


# A ticker whose fetch returned nothing has no bar for the session, so its
# indicators are not computed (they would run on a stale series).
SESSION_BAR_SQL = (
    "SELECT ticker FROM market_data_daily WHERE date = :fetch_date "
    "AND ticker = ANY(:kept) AND close IS NOT NULL"
)


def tickers_with_session_bar(kept: list[str], fetch_date: date,
                             query: Query | None = None) -> list[str]:
    """The ``kept`` tickers that have a close for ``fetch_date``, in ``kept``
    order. Strict read: a failure raises (Rule 3.7)."""
    if query is None:
        from gcp.database import query_to_dataframe_strict as query
    df = query(SESSION_BAR_SQL, {'fetch_date': fetch_date, 'kept': list(kept)},
               timeout_s=_SET_QUERY_TIMEOUT_S)
    have = set(df['ticker']) if len(df) else set()
    return [t for t in kept if t in have]


def compute_indicators(tickers: list[str], fetch_date: date) -> None:
    """Indicators for the tickers that have the session bar, in order. Level
    parameters are read once for the batch; a read failure raises."""
    with_bar = tickers_with_session_bar(tickers, fetch_date)
    skipped = [t for t in tickers if t not in set(with_bar)]
    if skipped:
        log.info("no session bar for %s on %s, indicators skipped", skipped, fetch_date)
    if not with_bar:
        return
    date_str = fetch_date.isoformat()
    params = fetch_market_data.read_level_params_for_run(with_bar, date_str)
    for t in with_bar:
        fetch_market_data.compute_and_upsert_daily_indicators(
            t, date_str, level_params=params.get(t.upper()))


def refresh_ticker_info(tickers: list[str]) -> None:
    """Refresh ticker info (cached up to 30 days) per ticker. One ticker's
    failure is logged and does not stop the rest; the run's verification counts
    a missing or stale row per ticker."""
    from lib.ticker_info import get_ticker_info
    for t in tickers:
        try:
            get_ticker_info(t, max_age_days=30)
        except Exception as e:  # logged per ticker, verified afterwards
            log.error("ticker_info refresh failed for %s: %s", t, e)
