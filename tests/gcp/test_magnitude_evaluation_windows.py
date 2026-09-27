from datetime import date

import pandas as pd
import pytest

from gcp.research.magnitude_engine.evaluation_windows import (
    EASTERN, WINDOWS, assert_disjoint, eastern_sessions, purged_session_masks,
)


def test_windows_are_immutable_non_overlapping_and_eastern():
    ordered = list(WINDOWS.values())
    assert ordered[0].end <= ordered[1].start
    assert ordered[1].end <= ordered[2].start
    assert ordered[2].final
    assert ordered[0].start_eastern.tzinfo == EASTERN
    with pytest.raises(Exception):
        ordered[0].start = date(2020, 1, 1)


def test_sessions_are_eastern_and_embargo_whole_session():
    timestamps = pd.to_datetime([
        "2025-01-02T14:30:00Z", "2025-01-02T20:00:00Z",
        "2025-01-03T15:00:00Z", "2025-01-06T15:00:00Z",
    ])
    sessions = eastern_sessions(timestamps)
    train, test = purged_session_masks(
        sessions, "2025-01-06", "2025-01-07", embargo_sessions=1)
    assert train.tolist() == [True, True, False, False]
    assert test.tolist() == [False, False, False, True]


def test_rejects_overlap_and_short_embargo():
    sessions = pd.to_datetime(["2025-01-02", "2025-01-03"])
    with pytest.raises(ValueError, match="overlap"):
        assert_disjoint(sessions, sessions[-1:])
    with pytest.raises(ValueError, match="prediction horizon"):
        purged_session_masks(sessions, "2025-01-03", "2025-01-04", 0)
