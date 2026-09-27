from datetime import date

import pandas as pd
import pytest

from gcp.research.magnitude_engine.evaluation_windows import (
    EASTERN, WINDOWS, assert_disjoint, eastern_sessions, purged_session_masks,
    assert_window_complete,
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


def test_final_window_cannot_run_until_it_is_complete():
    with pytest.raises(ValueError, match="incomplete"):
        assert_window_complete(WINDOWS["final_test"], date(2026, 9, 27))
    assert_window_complete(WINDOWS["final_test"], date(2027, 1, 1))


def test_gate_threshold_scales_from_six_of_eight_to_window_fold_count():
    from gcp.research.magnitude_engine.mag_walk_forward import _evaluate_phase_gate

    passing = {
        "status": "OK", "beat": 0.1, "ece_pass": True,
        "explosive": {"lift": 2.0},
        "decisive_hit": {
            "0.40": {"accuracy": 0.5}, "0.50": {"accuracy": 0.6},
            "0.60": {"accuracy": 0.7}, "0.70": {"accuracy": 0.8},
        },
    }
    gates = _evaluate_phase_gate([passing.copy(), passing.copy()], "5m")
    assert gates["required_pass_folds"] == 2
    assert gates["cell_pass_gates_1_to_4"] is True
