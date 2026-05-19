"""Integration test: earnings calibration persistence (real SQL).

Exercises scripts/calibrate_earnings.py:apply_winner against the real
earnings_calibration schema on the ephemeral test Postgres — confirms
the winning combo lands and a same-day re-run converges via ON CONFLICT.
"""
from __future__ import annotations

import pytest
import sqlalchemy

from scripts.calibrate_earnings import apply_winner


@pytest.fixture
def clean_earnings_cal(db_engine):
    """Drop today's earnings_calibration row before and after."""
    def _wipe():
        with db_engine.begin() as c:
            c.execute(sqlalchemy.text(
                "DELETE FROM earnings_calibration "
                "WHERE calibration_date = CURRENT_DATE"))
    _wipe()
    yield db_engine
    _wipe()


_WINNER = {
    "min_nq": 10, "lookback_quarters": 16,
    "quintile_spread": 0.23, "overall_hit_rate": 0.56,
    "n_predictions": 9000,
}


def test_apply_winner_writes_row(clean_earnings_cal):
    apply_winner(dict(_WINNER))
    with clean_earnings_cal.begin() as c:
        row = c.execute(sqlalchemy.text(
            "SELECT min_nq, lookback_quarters, quintile_spread, n_predictions "
            "FROM earnings_calibration "
            "WHERE calibration_date = CURRENT_DATE")).one()
    min_nq, lookback, spread, n = row
    assert min_nq == 10
    assert lookback == 16
    assert abs(spread - 0.23) < 1e-9
    assert n == 9000


def test_apply_winner_idempotent_rerun(clean_earnings_cal):
    apply_winner(dict(_WINNER))
    # Same-day re-run with an updated metric -> ON CONFLICT DO UPDATE.
    apply_winner({**_WINNER, "quintile_spread": 0.30})
    with clean_earnings_cal.begin() as c:
        rows = c.execute(sqlalchemy.text(
            "SELECT quintile_spread FROM earnings_calibration "
            "WHERE calibration_date = CURRENT_DATE")).all()
    assert len(rows) == 1  # converged, did not duplicate
    assert abs(rows[0][0] - 0.30) < 1e-9  # updated to the re-run value
