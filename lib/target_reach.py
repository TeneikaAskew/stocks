"""FEAT-STRAT-001 target hit rates: how often a ticker's past trades reached
a distance past the trigger before the stop
(docs/superpowers/specs/2026-11-17-feat-strat-001-target-hit-rates-r2.md,
Design 1 and Design 5).

The brief reads, in ONE query per run for all of its tickers, the
plan_excursions rows of the entry rule version of the basis being built
(lib.strat_levels.entry_rule_version, passed in, never a constant here)
from sessions before its own, in the window the target_reach_rate policy
row names (since a date, or the ticker's last lookback_sessions trades),
and the stored measure that row names (touch_atr: excursion_atr,
held_5m_atr: excursion_held5_atr, touch: excursion_r, held_5m:
excursion_held5_r). A line d past the trigger, in the measure's unit, is
counted by the trades whose excursion is at least d. A NULL excursion
reaches nothing and still counts as a trade.

Display only: nothing here changes a trigger, stop, target or exit. This
module formats the counts; the quarter-target change prints them on its
target and level lines. A failed read raises TargetReachUnavailable; there
is no fallback count (CLAUDE.md 3.7).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, Optional, Tuple

from lib.strat_levels import (
    TARGET_REACH_MEASURE_COLUMNS, TARGET_REACH_RATE_KEY, target_reach_policy_usable,
)

# measure -> the plan_excursions column it reads (defined with the policy
# check in lib.strat_levels).
MEASURE_COLUMNS = TARGET_REACH_MEASURE_COLUMNS

# {column} is a MEASURE_COLUMNS value, {tickers} bound placeholders.
_SINCE_SQL = (
    "SELECT ticker, session_date, {column} AS x FROM plan_excursions "
    "WHERE rule_version = :rule_version AND ticker IN ({tickers}) "
    "AND session_date < :session_date AND session_date >= :since "
    "ORDER BY ticker, session_date")
_LOOKBACK_SQL = (
    "SELECT ticker, session_date, x FROM ("
    "SELECT ticker, session_date, {column} AS x, ROW_NUMBER() OVER "
    "(PARTITION BY ticker ORDER BY session_date DESC) AS rn FROM plan_excursions "
    "WHERE rule_version = :rule_version AND ticker IN ({tickers}) "
    "AND session_date < :session_date) w WHERE rn <= :lookback "
    "ORDER BY ticker, session_date")

# Design 5's words, exactly.
HEADER_TEXT = 'Reached before the stop: {ticker} trades {first} to {last} ({n})'
UNAVAILABLE_TEXT = 'Reached before the stop: unavailable ({status}).'
NO_STOP_TEXT = 'Reached before the stop: unavailable (no stop to measure from).'
NO_HISTORY_TEXT = 'no history yet'


class TargetReachUnavailable(RuntimeError):
    """The counts cannot be read: the policy row or the entry version is
    unusable, or the query failed (a missing table included)."""


def pct_half_up(k: int, n: int) -> int:
    """k of n as a whole percent, rounded half up (n > 0)."""
    return (200 * k + n) // (2 * n)


@dataclass(frozen=True)
class ReachTable:
    """One ticker's past trades in the window: the count, the first and last
    session, and each trade's excursion in the policy's measure (None
    reaches nothing)."""
    ticker: str
    n: int
    first: Optional[str]
    last: Optional[str]
    values: Tuple[Optional[float], ...]

    def count_at_least(self, d: float) -> int:
        """How many of the n trades' excursions are at least d (a 1e-9
        tolerance for a distance computed from prices)."""
        return sum(1 for v in self.values if v is not None and v >= d - 1e-9)

    def share_at_least(self, d: float) -> Optional[float]:
        """The share of the n trades whose excursion is at least d; None
        with no trades."""
        if self.n == 0:
            return None
        return self.count_at_least(d) / self.n

    def count_text(self, d: float, min_sample: int) -> str:
        """The words at the end of a target or level line d past the trigger
        (Design 5): 'reached k of n (p%)' at or above min_sample trades,
        'reached k of n' below it, 'no history yet' with none."""
        if self.n == 0:
            return NO_HISTORY_TEXT
        k = self.count_at_least(d)
        if self.n < min_sample:
            return f'reached {k} of {self.n}'
        return f'reached {k} of {self.n} ({pct_half_up(k, self.n)}%)'

    def header_text(self) -> str:
        """The line after the stop line (Design 5)."""
        return HEADER_TEXT.format(ticker=self.ticker, first=self.first, last=self.last, n=self.n)


def unavailable_text(status: str) -> str:
    """The line printed instead of any count when the row or the table is
    unusable (Design 5)."""
    return UNAVAILABLE_TEXT.format(status=status)


def _iso(v) -> Optional[str]:
    if v is None:
        return None
    if hasattr(v, 'date') and not isinstance(v, date):
        v = v.date()
    return v.isoformat() if hasattr(v, 'isoformat') else str(v)[:10]


def _value(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def load_target_reach(query_fn, tickers: Iterable[str], session_date, param,
                      rule_version: Optional[str]) -> Dict[str, ReachTable]:
    """Every run ticker's ReachTable for the brief of `session_date`, in ONE
    query. `param` is the target_reach_rate LevelParam in force (the same
    for every ticker); `rule_version` is entry_rule_version of the basis
    being built, the rows' key. `query_fn(sql, params)` returns a DataFrame
    and must raise on failure. A ticker with no rows gets n 0."""
    if param is None or getattr(param, 'key', None) != TARGET_REACH_RATE_KEY or not param.ok:
        raise TargetReachUnavailable(
            f"{TARGET_REACH_RATE_KEY} is not usable ({getattr(param, 'status', 'missing')})")
    extra = dict(param.extra or {})
    if not target_reach_policy_usable(param.min_sample, param.lookback_sessions, extra):
        raise TargetReachUnavailable(f"{TARGET_REACH_RATE_KEY} row is not usable: {extra!r}")
    if not rule_version:
        raise TargetReachUnavailable("the basis being built has no entry rule version")
    names = sorted({str(t).upper() for t in tickers if t})
    if not names:
        return {}
    session = session_date if isinstance(session_date, str) else _iso(session_date)
    placeholders = ', '.join(f':t{i}' for i in range(len(names)))
    params = {f't{i}': t for i, t in enumerate(names)}
    params.update(rule_version=rule_version, session_date=session)
    column = MEASURE_COLUMNS[extra['measure']]
    if param.lookback_sessions is not None:
        sql = _LOOKBACK_SQL.format(column=column, tickers=placeholders)
        params['lookback'] = int(param.lookback_sessions)
    else:
        sql = _SINCE_SQL.format(column=column, tickers=placeholders)
        params['since'] = extra['since']
    try:
        df = query_fn(sql, params)
    except Exception as exc:
        raise TargetReachUnavailable(f"plan_excursions read failed: {exc}") from exc
    if df is None:
        raise TargetReachUnavailable("plan_excursions read returned no result set")
    rows: Dict[str, list] = {t: [] for t in names}
    for r in (df.to_dict('records') if len(df) else []):
        t = str(r.get('ticker') or '').upper()
        if t in rows:
            rows[t].append((_iso(r.get('session_date')), _value(r.get('x'))))
    out: Dict[str, ReachTable] = {}
    for t in names:
        got = sorted(rows[t], key=lambda x: x[0] or '')
        out[t] = ReachTable(
            ticker=t, n=len(got), first=got[0][0] if got else None,
            last=got[-1][0] if got else None, values=tuple(v for _, v in got))
    return out
