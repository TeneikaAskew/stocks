"""Integration test: walk-forward param-sweep persistence (real SQL).

Exercises scripts/run_param_sweep.py's DB-write paths against the real
schema on the ephemeral test Postgres:

  - persist_results writes one walk_forward_results row per combo and
    flags exactly one as selected
  - apply_winner overlays the swept params onto a new exit_config_overrides
    snapshot while carrying forward the non-swept knobs (call_stop etc.)
  - a same-day re-run converges via ON CONFLICT instead of duplicating
"""
from __future__ import annotations

import uuid

import pandas as pd
import pytest
import sqlalchemy

from scripts.run_param_sweep import apply_winner, combo_label, persist_results
from lib.walk_forward import select_calibration_winner


@pytest.fixture
def clean_sweep(db_engine):
    """Drop this test's rows before and after — order-independent."""
    def _wipe():
        with db_engine.begin() as c:
            c.execute(sqlalchemy.text(
                "DELETE FROM walk_forward_results WHERE ticker = 'TST'"))
            c.execute(sqlalchemy.text(
                "DELETE FROM exit_config_overrides WHERE ticker = 'TST'"))
    _wipe()
    yield db_engine
    _wipe()


def _sweep_df() -> pd.DataFrame:
    """Two combos: the first clears the selection gates, the second
    (stability 0.40) does not."""
    return pd.DataFrame([
        {"call_target": 0.0030, "put_target": 0.0038,
         "call_time_stop": 30, "put_time_stop": 35,
         "avg_expectancy_pct": 0.0020, "avg_win_rate": 0.55,
         "std_expectancy_pct": 0.001, "stability_score": 0.75,
         "total_folds": 10, "total_trades": 120},
        {"call_target": 0.0035, "put_target": 0.0044,
         "call_time_stop": 25, "put_time_stop": 40,
         "avg_expectancy_pct": 0.0010, "avg_win_rate": 0.52,
         "std_expectancy_pct": 0.002, "stability_score": 0.40,
         "total_folds": 10, "total_trades": 80},
    ])


def _seed_base_row(engine) -> None:
    with engine.begin() as c:
        c.execute(sqlalchemy.text(
            "INSERT INTO exit_config_overrides "
            "(ticker, calibration_date, call_target, put_target, "
            " call_stop, put_stop, call_time_stop, put_time_stop, notes) "
            "VALUES ('TST', DATE '2026-01-01', 0.0020, 0.0020, "
            " 0.0009, 0.0011, 20, 20, 'seed')"))


def test_persist_results_writes_every_combo(clean_sweep):
    run_id = str(uuid.uuid4())
    df = _sweep_df()
    winner = select_calibration_winner(df)
    n = persist_results(df, run_id, "TST", combo_label(winner))
    assert n == 2

    with clean_sweep.begin() as c:
        rows = c.execute(sqlalchemy.text(
            "SELECT label, selected FROM walk_forward_results "
            "WHERE run_id = :r"), {"r": run_id}).all()
    assert len(rows) == 2
    # Exactly one combo is flagged as the strategic winner.
    assert sum(1 for _, selected in rows if selected) == 1


def test_apply_winner_carries_forward_non_swept_knobs(clean_sweep):
    _seed_base_row(clean_sweep)
    winner = select_calibration_winner(_sweep_df())
    apply_winner("TST", winner, str(uuid.uuid4()))

    with clean_sweep.begin() as c:
        row = c.execute(sqlalchemy.text(
            "SELECT call_target, call_time_stop, call_stop, put_stop "
            "FROM exit_config_overrides WHERE ticker = 'TST' "
            "ORDER BY calibration_date DESC LIMIT 1")).one()
    call_target, call_time_stop, call_stop, put_stop = row
    # Swept knobs updated to the winning combo.
    assert abs(call_target - 0.0030) < 1e-9
    assert call_time_stop == 30
    # Non-swept knobs carried forward from the 2026-01-01 base row —
    # a new snapshot must never silently drop earlier calibration.
    assert abs(call_stop - 0.0009) < 1e-9
    assert abs(put_stop - 0.0011) < 1e-9


def test_apply_winner_idempotent_rerun(clean_sweep):
    _seed_base_row(clean_sweep)
    winner = select_calibration_winner(_sweep_df())
    run_id = str(uuid.uuid4())
    apply_winner("TST", winner, run_id)
    apply_winner("TST", winner, run_id)  # same-day re-run -> ON CONFLICT

    with clean_sweep.begin() as c:
        n = c.execute(sqlalchemy.text(
            "SELECT count(*) FROM exit_config_overrides "
            "WHERE ticker = 'TST' AND calibration_date = CURRENT_DATE"
        )).scalar()
    assert n == 1  # converged, did not duplicate
