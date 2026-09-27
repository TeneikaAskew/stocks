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
