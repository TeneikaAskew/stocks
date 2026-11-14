"""Watched-ticker ingest job (fetch-watched-tickers), v2.

Run as ``python -m gcp.fetchers.fetch_watched_tickers``. ``main`` parses the
config and calls ``run``, which resolves the session, reads the watched set
from Cloud SQL with its exact overflow, dedups it, pulls daily bars planned
from stored coverage, computes indicators where the session bar exists,
refreshes ticker info, verifies every ticker and records one ``job_runs`` row.

CLAUDE.md Rule 3.7: a failed set read raises ``SetReadError``; it is never
an empty set. An empty frame from a read that ran is a legitimate zero.
"""
from __future__ import annotations

import logging
import numbers
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable, Mapping, Sequence

import pandas as pd

from gcp.fetchers import fetch_market_data
from gcp.fetchers.fetch_market_data import (
    BACKFILL_DEPTH_THRESHOLD_BARS,
    _pick_backfill_outputsize,
)
from gcp.database import query_to_dataframe_strict, record_job_run
from lib.eastern_time import is_session, market_today

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
            n = int(raw)
        except ValueError as e:
            raise ValueError(f'WATCHED_TICKERS_MAX must be an integer, got {raw!r}') from e
        if n < 1:
            # 0 would serve nothing yet never learn the eligible count, so
            # the overflow of unserved tickers would go unreported.
            raise ValueError(f'WATCHED_TICKERS_MAX must be at least 1, got {raw!r}')
        return cls(max_tickers=n)


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

# Coverage counts real bars only: an indicator-only row (close NULL) holds
# indicators but no bar, so it neither adds to the count nor makes a date
# current nor marks the ticker as another writer's.
COVERAGE_SQL = (
    "SELECT ticker, COUNT(*) AS bar_count, MAX(date) AS max_date, "
    "bool_or(data_source = 'av_watched_backfill') AS bootstrapped "
    "FROM market_data_daily WHERE ticker = ANY(:kept) AND close IS NOT NULL "
    "GROUP BY ticker"
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

    Strict read: a failure raises (Rule 3.7). A ticker with no real bars
    (no rows, or only indicator-only rows) is the explicit
    ``Coverage(t, 0, None, False)``, a true "no bars" state.
    """
    if query is None:
        from gcp.database import query_to_dataframe_strict as query
    df = query(COVERAGE_SQL, {'kept': list(kept)}, timeout_s=_SET_QUERY_TIMEOUT_S)
    found: dict[str, Coverage] = {}
    for _, r in df.iterrows():
        t = r['ticker']
        # bool_or over all-NULL data_source is NULL (None or NaN here); it
        # reads False, never bool(nan), which is True.
        flag = r['bootstrapped']
        found[t] = Coverage(t, int(r['bar_count']), _as_date(r['max_date']),
                            bool(pd.notna(flag) and flag))
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


def upsert_indicators(tickers: list[str], with_bar: list[str], fetch_date: date) -> None:
    """Indicators for ``with_bar`` (the ``tickers`` holding the session bar),
    in order; ``run`` reads ``with_bar`` itself so each step names its phase.
    Level parameters are read once for the batch; a read failure raises."""
    have = set(with_bar)
    skipped = [t for t in tickers if t not in have]
    if skipped:
        log.info("no session bar for %s on %s, indicators skipped", skipped, fetch_date)
    if not with_bar:
        return
    date_str = fetch_date.isoformat()
    params = fetch_market_data.read_level_params_for_run(with_bar, date_str)
    for i, t in enumerate(with_bar, 1):
        fetch_market_data.compute_and_upsert_daily_indicators(
            t, date_str, level_params=params.get(t.upper()))
        log.info("ticker=%s step=%s processed=%d/%d", t, 'indicators', i, len(with_bar))


def refresh_ticker_info(tickers: list[str]) -> None:
    """Refresh ticker info (cached up to 30 days) per ticker. One ticker's
    failure is logged and does not stop the rest; the run's verification counts
    a missing or stale row per ticker."""
    from lib.ticker_info import get_ticker_info
    for i, t in enumerate(tickers, 1):
        try:
            get_ticker_info(t, max_age_days=30)
        except Exception as e:  # logged per ticker, verified afterwards
            log.error("ticker_info refresh failed for %s: %s", t, e)
        log.info("ticker=%s step=%s processed=%d/%d", t, 'ticker_info', i, len(tickers))


# Per-ticker verification. The bars read pairs the session row with the
# ticker's stored count of real bars (close NOT NULL; an indicator-only row
# cannot lift a short series over the indicator minimum); the info read
# returns when each ticker_info row was last refreshed.
VERIFY_BARS_SQL = (
    "SELECT m.ticker, m.close, m.atr_14, c.bar_count FROM market_data_daily m "
    "JOIN (SELECT ticker, COUNT(*) AS bar_count FROM market_data_daily "
    "WHERE ticker = ANY(:kept) AND close IS NOT NULL GROUP BY ticker) c USING (ticker) "
    "WHERE m.date = :fetch_date AND m.ticker = ANY(:kept)"
)
VERIFY_INFO_SQL = "SELECT ticker, updated_at FROM ticker_info WHERE ticker = ANY(:kept)"
# Fewer bars than this cannot yield an ATR(14), so a null atr_14 is expected.
INDICATOR_MIN_BARS = 15
TICKER_INFO_MAX_AGE = timedelta(days=30)


@dataclass(frozen=True)
class Verdict:
    failed: dict[str, str]   # ticker -> 'bars' | 'indicators' | 'ticker_info'
    too_short: list[str]     # too few bars for indicators; not a failure


def _as_utc(v) -> datetime | None:
    """A frame's updated_at as a tz-aware UTC datetime (naive means UTC), or None."""
    if v is None or pd.isna(v):
        return None
    ts = pd.Timestamp(v)
    ts = ts.tz_localize('UTC') if ts.tzinfo is None else ts.tz_convert('UTC')
    return ts.to_pydatetime()


def verify_tickers(kept: list[str], fetch_date: date, now: datetime,
                   query: Query | None = None) -> Verdict:
    """Per-ticker check of the session bar, indicators and ticker info.

    One reason per ticker, in the order bars, indicators, ticker_info. Both
    reads are strict: a failure raises (Rule 3.7). ``now`` is tz-aware UTC.
    """
    if query is None:
        from gcp.database import query_to_dataframe_strict as query
    params = {'fetch_date': fetch_date, 'kept': list(kept)}
    bars = query(VERIFY_BARS_SQL, params, timeout_s=_SET_QUERY_TIMEOUT_S)
    info = query(VERIFY_INFO_SQL, {'kept': list(kept)}, timeout_s=_SET_QUERY_TIMEOUT_S)
    bar_rows = {r['ticker']: r for _, r in bars.iterrows()}
    info_at = {r['ticker']: _as_utc(r['updated_at']) for _, r in info.iterrows()}
    cutoff = now - TICKER_INFO_MAX_AGE
    failed: dict[str, str] = {}
    too_short: list[str] = []
    for t in kept:
        row = bar_rows.get(t)
        if row is None or pd.isna(row['close']):
            failed[t] = 'bars'
            continue
        short = int(row['bar_count']) < INDICATOR_MIN_BARS
        if short:
            too_short.append(t)
        elif pd.isna(row['atr_14']):
            failed[t] = 'indicators'
            continue
        updated = info_at.get(t)
        if updated is None or updated < cutoff:
            failed[t] = 'ticker_info'
    return Verdict(failed, too_short)


# ── the run ─────────────────────────────────────────────────────────────


def _record(started: datetime, status: str, **fields) -> None:
    """The run's one job_runs row. record_job_run swallows its own failure and
    returns False; that is logged at ERROR and never changes the exit code."""
    if not record_job_run(JOB_NAME, started, status, **fields):
        log.error("job_runs write failed: job=%s status=%s note=%s",
                  JOB_NAME, status, fields.get('note'))


class _PhaseError(Exception):
    def __init__(self, phase: str, exc: BaseException):
        super().__init__(f'{phase}: {exc}')
        self.phase = phase


def _phase(name: str, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        raise _PhaseError(name, e) from e


def _note(*parts: str | None) -> str | None:
    kept = [p for p in parts if p]
    return '; '.join(kept) if kept else None


def run(cfg: Config, *, today: date, now: datetime,
        query: Query = query_to_dataframe_strict) -> int:
    """One run of the job; returns the exit code and records exactly one
    ``job_runs`` row.

    0: success (a non-session day, an empty set, or a run where some but not
    every kept ticker failed verification). 1: every kept ticker failed. 2: the
    set read failed, or any later phase raised (``session``, ``coverage``,
    ``backfill``, ``session_bars``, ``indicators``, ``ticker_info``,
    ``verify``): that is logged at ERROR and recorded as ``'error'`` with the
    phase (and ``overflow=<n>`` when above zero) in the note and the rows the
    backfill wrote before the failure in ``rows_written``. Examples of a phase
    failure: ``_run_backfill``'s RuntimeError for a missing Alpha Vantage key
    or an unconfigured Cloud SQL, ``LevelParamsUnavailable``, a failed strict
    read.

    A per-ticker Alpha Vantage failure is not a phase failure: ``_run_backfill``
    logs it and moves on, and the ticker, having no session bar, is counted by
    ``verify_tickers`` as a ``bars`` failure in ``items_failed`` while the run
    stays ``'success'`` unless every kept ticker failed.
    """
    started = now
    try:
        fetch_date = _phase('session', resolve_session, today)
    except _PhaseError as e:
        log.exception("fetch-watched-tickers failed in phase %s", e.phase)
        _record(started, 'error', items_total=0, note=str(e))
        return 2
    if fetch_date is None:
        log.info("%s is not a session; nothing to do", today)
        _record(started, 'success', items_total=0, note='non_session')
        return 0

    try:
        ws = read_watched_set(query, fetch_market_data.TICKERS, cfg.max_tickers)
    except SetReadError as e:
        log.exception("set_read failed")
        _record(started, 'error', items_total=0, note=f'set_read: {e}')
        return 2

    overflow = f'overflow={ws.overflow}' if ws.overflow > 0 else None
    if overflow:
        log.error("%d watched tickers above the ceiling of %d: %s",
                  ws.overflow, cfg.max_tickers, overflow)
    kept = dedup(ws.tickers, fetch_market_data.TICKERS)
    if not kept:
        _record(started, 'success', items_total=0, note=overflow or 'empty_set')
        return 0

    n = len(kept)
    rows_written = 0   # visible to the error branch: what was written before a failure
    try:
        coverages = _phase('coverage', read_coverage, kept, query=query)
        plan = _phase('coverage', plan_pulls, coverages, fetch_date)
        planned = {t for group in plan.values() for t in group}
        done = 0
        for t in kept:
            if t not in planned:
                done += 1
                log.info("ticker=%s step=%s processed=%d/%d", t, 'bars_current', done, n)
        for (size, source), group in plan.items():
            rows_written += _phase('backfill', fetch_market_data._run_backfill,
                                   group, outputsize=size, data_source=source)
            for t in group:
                done += 1
                log.info("ticker=%s step=%s processed=%d/%d", t, 'bars', done, n)
        with_bar = _phase('session_bars', tickers_with_session_bar,
                          kept, fetch_date, query=query)
        _phase('indicators', upsert_indicators, kept, with_bar, fetch_date)
        _phase('ticker_info', refresh_ticker_info, kept)
        verdict = _phase('verify', verify_tickers, kept, fetch_date, now, query=query)
    except _PhaseError as e:
        log.exception("fetch-watched-tickers failed in phase %s", e.phase)
        _record(started, 'error', items_total=n, rows_written=rows_written,
                note=_note(str(e), overflow))
        return 2

    failed = verdict.failed
    for i, t in enumerate(kept, 1):
        log.info("ticker=%s step=%s processed=%d/%d", t, 'verify', i, n)
        if t in failed:
            log.warning("ticker=%s failed verification: %s", t, failed[t])
    all_failed = len(failed) == n
    note = _note(
        overflow,
        f"too_short=[{','.join(verdict.too_short)}]" if verdict.too_short else None,
        'failed=' + ','.join(f'{t}:{r}' for t, r in failed.items()) if failed else None,
    )
    _record(started, 'error' if all_failed else 'success',
            items_total=n, items_processed=n - len(failed),
            items_failed=len(failed), rows_written=rows_written, note=note)
    log.info("fetch-watched-tickers done: kept=%d failed=%d rows_written=%d",
             n, len(failed), rows_written)
    return 1 if all_failed else 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    started = datetime.now(timezone.utc)
    try:
        cfg = Config.from_env(os.environ)
    except ValueError as e:
        log.error("config: %s", e)
        _record(started, 'error', items_total=0, note=f'config: {e}')
        return 2
    return run(cfg, today=market_today(), now=started)


if __name__ == '__main__':
    sys.exit(main())
