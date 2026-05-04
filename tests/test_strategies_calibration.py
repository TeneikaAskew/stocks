"""Unit tests for lib.strategies.calibration (Tier-A resolver).

Pure-function tests with no DB. Monkeypatches the internal
`_latest_calibration` helper to inject row shapes and exercise the
resolution chain.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from lib.strategies import calibration
from lib.strategies.config import CALL_RSI_RANGE, PUT_RSI_RANGE


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the lru_cache between tests so monkeypatches take effect."""
    calibration._latest_calibration.cache_clear()
    yield
    calibration._latest_calibration.cache_clear()


def test_no_row_returns_tier_b_put():
    with patch.object(calibration, "_latest_calibration", return_value=None):
        assert calibration.get_put_rsi_range("UNKNOWN") == PUT_RSI_RANGE


def test_no_row_returns_tier_b_call():
    with patch.object(calibration, "_latest_calibration", return_value=None):
        assert calibration.get_call_rsi_range("UNKNOWN") == CALL_RSI_RANGE


def test_fresh_row_returns_tier_a_put():
    fresh = {
        "calibration_date": date.today(),
        "rsi_p10": 35.0,
        "rsi_p25": 43.0,
        "rsi_p50": 50.5,
        "rsi_p75": 57.5,
        "rsi_p90": 65.0,
    }
    with patch.object(calibration, "_latest_calibration", return_value=fresh):
        assert calibration.get_put_rsi_range("QQQ") == (50.5, 65.0)


def test_fresh_row_returns_tier_a_call():
    fresh = {
        "calibration_date": date.today(),
        "rsi_p10": 35.0,
        "rsi_p50": 50.5,
        "rsi_p90": 65.0,
    }
    with patch.object(calibration, "_latest_calibration", return_value=fresh):
        assert calibration.get_call_rsi_range("QQQ") == (35.0, 50.5)


def test_null_p50_falls_back_put():
    """Tier-A requires both p50 and p90 to be non-NULL for PUT."""
    row = {
        "calibration_date": date.today(),
        "rsi_p50": None,
        "rsi_p90": 65.0,
    }
    with patch.object(calibration, "_latest_calibration", return_value=row):
        assert calibration.get_put_rsi_range("QQQ") == PUT_RSI_RANGE


def test_null_p90_falls_back_put():
    row = {
        "calibration_date": date.today(),
        "rsi_p50": 50.5,
        "rsi_p90": None,
    }
    with patch.object(calibration, "_latest_calibration", return_value=row):
        assert calibration.get_put_rsi_range("QQQ") == PUT_RSI_RANGE


def test_null_p10_falls_back_call():
    row = {
        "calibration_date": date.today(),
        "rsi_p10": None,
        "rsi_p50": 50.5,
    }
    with patch.object(calibration, "_latest_calibration", return_value=row):
        assert calibration.get_call_rsi_range("QQQ") == CALL_RSI_RANGE


def test_resolution_tier_returns_a_when_populated():
    fresh = {
        "calibration_date": date.today(),
        "rsi_p10": 35.0, "rsi_p50": 50.5, "rsi_p90": 65.0,
    }
    with patch.object(calibration, "_latest_calibration", return_value=fresh):
        assert calibration.get_resolution_tier("QQQ", "PUT") == "A"
        assert calibration.get_resolution_tier("QQQ", "CALL") == "A"


def test_resolution_tier_returns_b_when_no_row():
    with patch.object(calibration, "_latest_calibration", return_value=None):
        assert calibration.get_resolution_tier("UNKNOWN", "PUT") == "B"
        assert calibration.get_resolution_tier("UNKNOWN", "CALL") == "B"


def test_resolution_tier_b_when_columns_null():
    row = {"calibration_date": date.today(), "rsi_p50": None, "rsi_p90": 65.0}
    with patch.object(calibration, "_latest_calibration", return_value=row):
        assert calibration.get_resolution_tier("X", "PUT") == "B"


def test_strategy_uses_resolved_range_put():
    """End-to-end: MomentumStrategy.evaluate respects passed-in range."""
    import pandas as pd

    from lib.strategies import MOMENTUM

    # Bar with RSI=72 — falls inside Tier-B PUT (50,75) but OUTSIDE
    # a Tier-A range like (50, 65) which would block the rsi condition
    # from contributing.
    row = pd.Series({
        "RSI14_W": 72.0,
        "Consecutive_Down": 4,
        "StochRSI_K": 85.0,  # not oversold
        "Close": 100.0,
        "VWAP": 102.0,
        "EMA9": 103.0,
    })

    sig_b = MOMENTUM.evaluate(row)  # Tier-B default (50, 75) — RSI 72 in range
    assert sig_b is not None
    assert sig_b.direction == "PUT"
    assert "rsi_bearish_recovery" in sig_b.conditions_met

    sig_a = MOMENTUM.evaluate(row, put_rsi_range=(50.0, 65.0))  # RSI 72 OUT of range
    # With one fewer condition met (no rsi credit), score may drop below MIN_CONDITIONS
    if sig_a is not None:
        assert "rsi_bearish_recovery" not in sig_a.conditions_met


def test_lru_cache_one_query_per_ticker():
    """The cache is hit on the second call. Verified via call_count on a mock."""
    calibration._latest_calibration.cache_clear()

    # is_cloud_sql_configured is imported inside the function body, so patch
    # at its source module. First call runs the body (1 invocation); second
    # call is cached and must not increment the counter.
    with patch("gcp.database.is_cloud_sql_configured", return_value=False) as m:
        assert calibration._latest_calibration("AAPL") is None
        first_call_count = m.call_count
        assert first_call_count >= 1

        assert calibration._latest_calibration("AAPL") is None
        assert m.call_count == first_call_count
