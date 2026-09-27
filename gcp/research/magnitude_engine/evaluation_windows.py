"""Immutable, session-aware evaluation windows for magnitude research.

Dates are half-open Eastern trading-session ranges.  They are deliberately
code constants: changing an already observed boundary requires a new criteria
and final-test version, rather than silently redefining an experiment.

Every timezone conversion here goes through lib/eastern_time.py (CLAUDE.md
3.9); this module adds session semantics on top, never its own clock rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from gcp.research.magnitude_engine.mag_config import DEFAULT_CUTOFFS
from lib.eastern_time import ET as EASTERN, utc_to_eastern_naive

CRITERIA_VERSION = "magnitude-evaluation-v1"
FINAL_TEST_VERSION = "magnitude-final-v1"
PREDICTION_HORIZON_SESSIONS = 1


@dataclass(frozen=True)
class EvaluationWindow:
    name: str
    start: date
    end: date
    purpose: str
    final: bool = False

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError(f"invalid {self.name} window: {self.start}..{self.end}")

    @property
    def start_eastern(self) -> datetime:
        return datetime.combine(self.start, datetime.min.time(), EASTERN)

    @property
    def end_eastern(self) -> datetime:
        return datetime.combine(self.end, datetime.min.time(), EASTERN)


WINDOWS = {
    "development": EvaluationWindow(
        "development", date(2017, 1, 1), date(2024, 1, 1),
        "feature construction and broad configuration screening"),
    "validation": EvaluationWindow(
        "validation", date(2024, 1, 1), date(2026, 1, 1),
        "configuration and threshold selection"),
    "final_test": EvaluationWindow(
        "final_test", date(2026, 1, 1), date(2027, 1, 1),
        "one-time production decision only", final=True),
}


def validate_windows() -> None:
    ordered = sorted(WINDOWS.values(), key=lambda w: w.start)
    for left, right in zip(ordered, ordered[1:]):
        if left.end > right.start:
            raise ValueError(f"evaluation windows overlap: {left.name}/{right.name}")


def assert_window_complete(window: EvaluationWindow, as_of: date) -> None:
    """Refuse a window whose sessions can not all exist yet.

    `as_of` is a market date (lib.eastern_time.market_today), since the
    window is an Eastern-session range. Claiming the final test earlier would
    evaluate a partial year and consume the one-time version on it,
    permanently (Codex P1 on #1193).
    """
    if as_of < window.end:
        raise ValueError(
            f"{window.name} window is incomplete: it runs through "
            f"{window.end.isoformat()} and the market date is "
            f"{as_of.isoformat()}")


def window_cutoffs(window: EvaluationWindow,
                   cutoffs: list[str] | None = None) -> list[str]:
    """The fold schedule a window evaluates: the one rule for every consumer.

    Default: the DEFAULT_CUTOFFS that fall inside the window, so the harness
    and the naive baseline (scripts/naive_calendar_lookup_baseline.py) score
    the same folds. The final window has exactly one fold, training before
    it and evaluating all of it: a later cutoff would train on part of the
    holdout and evaluate the rest, a leak and a silently changed final-test
    population (Codex P1 on #1193), so custom cutoffs are refused there.
    """
    if cutoffs is None:
        cutoffs = ([window.start.isoformat()] if window.final else
                   [c for c in DEFAULT_CUTOFFS
                    if window.start <= pd.Timestamp(c).date() < window.end])
    cutoffs = [str(c) for c in cutoffs]
    if not cutoffs:
        raise ValueError(f"no folds fall in evaluation window {window.name}")
    for cutoff in cutoffs:
        if not window.start <= pd.Timestamp(cutoff).date() < window.end:
            raise ValueError(f"cutoff {cutoff} is outside immutable {window.name} "
                             f"window [{window.start}, {window.end})")
    if window.final and [pd.Timestamp(c).date() for c in cutoffs] != [window.start]:
        raise ValueError(
            f"{window.name} folds are fixed at [{window.start.isoformat()}]: "
            f"custom cutoffs {cutoffs} would train on part of the holdout")
    return cutoffs


def last_expected_session(window: EvaluationWindow) -> date:
    """The last NYSE session strictly before `window.end`.

    Honors exchange holidays through pandas_market_calendars, the calendar
    lib/strat_levels already relies on. Without it the last weekday stands
    in, which fails CLOSED: it can refuse a window whose last weekday was a
    holiday, never accept one whose last session is missing.
    """
    end = pd.Timestamp(window.end)
    try:
        import pandas_market_calendars as mcal
    except ImportError:
        return (end - pd.offsets.BDay(1)).date()
    days = mcal.get_calendar("NYSE").valid_days(
        start_date=(end - pd.Timedelta(days=14)).strftime("%Y-%m-%d"),
        end_date=(end - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    if len(days) == 0:
        raise RuntimeError(f"NYSE calendar returned no session in the two "
                           f"weeks before {window.end}")
    return days[-1].date()


def assert_window_covered(window: EvaluationWindow, session_labels) -> None:
    """Refuse a window whose loaded sessions stop short of its last one.

    assert_window_complete proves the period has ended; this proves the
    data reached its end. Without it a stale source table consumed the
    one-time final-test version and only then found a thin or empty final
    fold (Codex P1 on #1193).
    """
    sessions = pd.DatetimeIndex(session_labels)
    if len(sessions) == 0:
        raise ValueError(f"no sessions loaded for the {window.name} window")
    last = sessions.max().date()
    expected = last_expected_session(window)
    if last < expected:
        raise ValueError(
            f"{window.name} data ends at session {last.isoformat()} but the "
            f"window's last session is {expected.isoformat()}; the source "
            f"table is incomplete, refusing to consume the final-test version")


def expected_session_bars(window: EvaluationWindow, tf_minutes: int) -> dict[date, int]:
    """Every NYSE session in the window with the regular-hours bar count a
    `tf_minutes` table must hold for it: (close - open) / tf_minutes, so an
    early close expects fewer. Requires pandas_market_calendars; without it
    the window cannot be verified and this refuses rather than guessing.
    """
    try:
        import pandas_market_calendars as mcal
    except ImportError as exc:
        raise RuntimeError("pandas_market_calendars is required to verify the "
                           "final window's sessions") from exc
    if tf_minutes < 1:
        raise ValueError(f"tf_minutes must be positive, got {tf_minutes}")
    sched = mcal.get_calendar("NYSE").schedule(
        start_date=window.start.isoformat(),
        end_date=(pd.Timestamp(window.end) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    expected: dict[date, int] = {}
    for day, row in sched.iterrows():
        minutes = (row["market_close"] - row["market_open"]).total_seconds() / 60
        expected[day.date()] = int(minutes // tf_minutes)
    if not expected:
        raise RuntimeError(f"NYSE calendar returned no session in {window.name}")
    return expected


def assert_final_window_complete(window: EvaluationWindow,
                                 expected: dict[date, int],
                                 observed: dict[date, int]) -> None:
    """Refuse a final window whose source rows are not every session, whole.

    `expected` is expected_session_bars; `observed` is the per-session bar
    count the source table holds inside the window, read unlabelled. A
    session the calendar has and the table lacks, a session holding fewer
    bars than its regular hours, or a date the calendar has no session for,
    each refuse the claim: checking only the newest date and count let a
    truncated holdout consume the one-time version (Codex P1 on #1193).
    """
    missing = sorted(d for d in expected if d not in observed)
    short = sorted((d, observed[d], n) for d, n in expected.items()
                   if d in observed and observed[d] < n)
    extra = sorted(d for d in observed if d not in expected)
    problems = []
    if missing:
        problems.append(f"missing sessions {[d.isoformat() for d in missing]}")
    if short:
        problems.append("incomplete sessions " + str(
            [f"{d.isoformat()}: {have} < {need}" for d, have, need in short]))
    if extra:
        problems.append(f"rows on non-session dates {[d.isoformat() for d in extra]}")
    if problems:
        raise ValueError(f"{window.name} window is not complete in the source "
                         f"table, refusing to consume the final-test version: "
                         + "; ".join(problems))


def utc_instants(timestamps) -> pd.DatetimeIndex:
    """Aware UTC index for the harness's bar timestamps.

    Naive input is UTC by contract: ``strat_features.ts`` is TIMESTAMPTZ read
    in the UTC session, and the walk-forward hands each fold a
    ``datetime64[ns]`` view of the index it built from that column. Aware
    input is converted, never relabelled.
    """
    values = pd.DatetimeIndex(timestamps)
    if values.tz is None:
        return values.tz_localize("UTC")
    return values.tz_convert("UTC")


def eastern_sessions(timestamps) -> pd.DatetimeIndex:
    """Return normalized America/New_York session labels for UTC timestamps."""
    return utc_to_eastern_naive(utc_instants(timestamps)).normalize()


def assert_disjoint(train_sessions, evaluation_sessions) -> None:
    train = set(pd.DatetimeIndex(train_sessions).normalize())
    evaluation = set(pd.DatetimeIndex(evaluation_sessions).normalize())
    overlap = train & evaluation
    if overlap:
        first = min(overlap).date()
        raise ValueError(f"training and evaluation intervals overlap at {first}")


def purged_session_masks(session_labels, evaluation_start, evaluation_end,
                         embargo_sessions: int = PREDICTION_HORIZON_SESSIONS):
    """Build masks by whole Eastern sessions, purging before evaluation.

    ``embargo_sessions`` is measured in observed trading sessions (not calendar
    days), so weekends and exchange holidays cannot shorten the separation.
    """
    if embargo_sessions < PREDICTION_HORIZON_SESSIONS:
        raise ValueError("embargo must be at least the prediction horizon")
    sessions = pd.DatetimeIndex(session_labels).normalize()
    start = pd.Timestamp(evaluation_start)
    end = pd.Timestamp(evaluation_end)
    evaluation = (sessions >= start) & (sessions < end)
    earlier = sorted(pd.unique(sessions[sessions < start]))
    train_end = earlier[-embargo_sessions] if len(earlier) >= embargo_sessions else None
    train = sessions < train_end if train_end is not None else sessions < sessions.min()
    assert_disjoint(sessions[train], sessions[evaluation])
    return train, evaluation


validate_windows()
