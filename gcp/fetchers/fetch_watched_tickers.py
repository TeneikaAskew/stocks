"""Watched-ticker ingest job (fetch-watched-tickers), v2.

This module holds the job's config, the read of the watched set from Cloud
SQL with its exact overflow, and the second-guard dedup. Later steps add the
session check, coverage, indicators and verification.

CLAUDE.md Rule 3.7: a failed set read raises ``SetReadError``; it is never
an empty set. An empty frame from a read that ran is a legitimate zero.
"""
from __future__ import annotations

import numbers
from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterable, Mapping, Sequence

import pandas as pd

from lib.eastern_time import is_session

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
