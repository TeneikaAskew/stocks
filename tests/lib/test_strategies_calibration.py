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


def test_nan_p50_falls_back_put():
    """pd.read_sql returns SQL NULL as NaN for numeric columns (not None).

    Regression for the P1 bug Codex flagged on PR #248: a pure `is not None`
    check would let NaN through, producing a (nan, nan) Tier-A range that
    silently disables the RSI gate (NaN comparisons return False).
    """
    import math
    row = {
        "calibration_date": date.today(),
        "rsi_p50": math.nan,
        "rsi_p90": 65.0,
    }
    with patch.object(calibration, "_latest_calibration", return_value=row):
        assert calibration.get_put_rsi_range("QQQ") == PUT_RSI_RANGE


def test_nan_p90_falls_back_put():
    import math
    row = {
        "calibration_date": date.today(),
        "rsi_p50": 50.5,
        "rsi_p90": math.nan,
    }
    with patch.object(calibration, "_latest_calibration", return_value=row):
        assert calibration.get_put_rsi_range("QQQ") == PUT_RSI_RANGE


def test_nan_p10_falls_back_call():
    import math
    row = {
        "calibration_date": date.today(),
        "rsi_p10": math.nan,
        "rsi_p50": 50.5,
    }
    with patch.object(calibration, "_latest_calibration", return_value=row):
        assert calibration.get_call_rsi_range("QQQ") == CALL_RSI_RANGE


def test_resolution_tier_b_when_columns_nan():
    """Tier reporting must also see NaN as 'unusable' to avoid claiming
    Tier-A audit when the calibration is effectively NULL."""
    import math
    row = {
        "calibration_date": date.today(),
        "rsi_p10": 35.0, "rsi_p50": math.nan, "rsi_p90": 65.0,
    }
    with patch.object(calibration, "_latest_calibration", return_value=row):
        assert calibration.get_resolution_tier("X", "PUT") == "B"
        assert calibration.get_resolution_tier("X", "CALL") == "B"


def test_inf_falls_back():
    """Inf should also be rejected — math.isfinite catches it."""
    import math
    row = {
        "calibration_date": date.today(),
        "rsi_p50": math.inf,
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
        # B+: MIN_CONDITIONS_MOMENTUM=5 → need scaffolding to push score to 5.
        # 4 core (consec_down + rsi + below_vwap + below_ema9) + rvol = 5.
        "RVol_Recent_20": 1.5,
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


# ── #250 drift_flagged → Tier-B fallback ────────────────────────────

def test_resolver_falls_back_to_tier_b_when_drift_flagged():
    """Production drift-guard contract: when ticker_calibration row
    has drift_flagged=TRUE, _latest_calibration returns None so callers
    fall through to Tier-B (universal RSI ranges from
    lib/strategies/config.py). A single anomalous quarter doesn't
    whipsaw production thresholds."""
    import pandas as pd
    calibration._latest_calibration.cache_clear()
    flagged_row = pd.DataFrame([{
        "calibration_date": date.today(),
        "rsi_p10": 25.0, "rsi_p25": 35.0, "rsi_p50": 50.0,
        "rsi_p75": 65.0, "rsi_p90": 75.0,
        "lookback_days": 60, "n_bars_used": 30000,
        "drift_flagged": True,
    }])
    with patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         patch("gcp.database.get_engine", return_value=None), \
         patch("pandas.read_sql", return_value=flagged_row):
        result = calibration._latest_calibration("DRIFT_SPY")
    assert result is None, (
        "drift_flagged=TRUE must trigger Tier-B fallback (return None)"
    )


def test_resolver_returns_row_when_drift_flagged_false():
    """Counter-test: drift_flagged=FALSE → row resolves normally."""
    import pandas as pd
    calibration._latest_calibration.cache_clear()
    clean_row = pd.DataFrame([{
        "calibration_date": date.today(),
        "rsi_p10": 25.0, "rsi_p25": 35.0, "rsi_p50": 50.0,
        "rsi_p75": 65.0, "rsi_p90": 75.0,
        "lookback_days": 60, "n_bars_used": 30000,
        "drift_flagged": False,
    }])
    with patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         patch("gcp.database.get_engine", return_value=None), \
         patch("pandas.read_sql", return_value=clean_row):
        result = calibration._latest_calibration("CLEAN_SPY")
    assert result is not None
    assert result["rsi_p50"] == 50.0


def test_resolver_legacy_query_when_drift_column_missing():
    """Pre-#250 deploys without the drift_flagged column: resolver
    falls back to the legacy SELECT (drift_flagged-less rows treated
    as drift_flagged=False)."""
    import pandas as pd
    calibration._latest_calibration.cache_clear()
    legacy_row = pd.DataFrame([{
        "calibration_date": date.today(),
        "rsi_p10": 25.0, "rsi_p25": 35.0, "rsi_p50": 50.0,
        "rsi_p75": 65.0, "rsi_p90": 75.0,
        "lookback_days": 60, "n_bars_used": 30000,
        # No drift_flagged column — pre-#250 deploy
    }])
    call_count = {"n": 0}
    def fake_read_sql(sql, eng, params):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise Exception('column "drift_flagged" does not exist')
        return legacy_row
    with patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         patch("gcp.database.get_engine", return_value=None), \
         patch("pandas.read_sql", side_effect=fake_read_sql):
        result = calibration._latest_calibration("LEGACY_SPY")
    assert result is not None
    assert result["rsi_p50"] == 50.0
    assert call_count["n"] == 2, "Should attempt both new + legacy SELECT"


# ── FEAT-SIGNAL-001 (2026-11-11 spec): point-in-time reads for the brief ──

_PIT_ROWS = [
    {"calibration_date": date(2026, 1, 1), "rsi_p10": 36.0, "rsi_p25": 43.0, "rsi_p50": 50.5,
     "rsi_p75": 57.0, "rsi_p90": 65.0, "lookback_days": 60, "n_bars_used": 39000,
     "drift_flagged": False},
    {"calibration_date": date(2026, 4, 1), "rsi_p10": 34.8, "rsi_p25": 42.0, "rsi_p50": 49.9,
     "rsi_p75": 57.0, "rsi_p90": 64.0, "lookback_days": 60, "n_bars_used": 40000,
     "drift_flagged": False},
    {"calibration_date": date(2026, 7, 1), "rsi_p10": 35.9, "rsi_p25": 43.0, "rsi_p50": 50.6,
     "rsi_p75": 57.0, "rsi_p90": 64.9, "lookback_days": 60, "n_bars_used": 39000,
     "drift_flagged": False},
]


def _fake_table(seen, *, legacy_first=False):
    """A ticker_calibration stand-in that honours the SQL it is sent: the
    as_of filter only when the statement carries it."""
    import pandas as pd

    def read_sql(sql, eng, params):
        text_sql = str(sql)
        seen.append((text_sql, dict(params)))
        if legacy_first and len(seen) == 1:
            raise Exception('column "drift_flagged" does not exist')
        rows = list(_PIT_ROWS)
        if "calibration_date <= :as_of" in text_sql:
            rows = [r for r in rows if r["calibration_date"] <= params["as_of"]]
        rows.sort(key=lambda r: r["calibration_date"], reverse=True)
        return pd.DataFrame(rows[:1])
    return read_sql


@pytest.mark.parametrize("legacy_first", [False, True])
def test_as_of_reads_the_row_in_force_on_that_date(legacy_first):
    seen = []
    with patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         patch("gcp.database.get_engine", return_value=None), \
         patch("pandas.read_sql", side_effect=_fake_table(seen, legacy_first=legacy_first)):
        row = calibration._latest_calibration("SPY", date(2026, 5, 4))
    assert row is not None and row["calibration_date"] == date(2026, 4, 1)
    assert all("calibration_date <= :as_of" in s and p["as_of"] == date(2026, 5, 4) for s, p in seen)


def test_as_of_staleness_is_measured_from_as_of():
    """2026-04-01 is over 180 days before the day this was written, but
    33 days before the replayed session, so a replay of 2026-05-04 uses it."""
    seen = []
    with patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         patch("gcp.database.get_engine", return_value=None), \
         patch("pandas.read_sql", side_effect=_fake_table(seen)), \
         patch.object(calibration, "date") as fake_date:
        fake_date.today.return_value = date(2026, 11, 11)
        assert calibration._latest_calibration("SPY", date(2026, 5, 4)) is not None
        calibration._latest_calibration.cache_clear()
        assert calibration._latest_calibration("SPY", date(2027, 1, 15)) is None  # 198 days after 07-01


def test_without_as_of_the_query_is_unchanged():
    seen = []
    with patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         patch("gcp.database.get_engine", return_value=None), \
         patch("pandas.read_sql", side_effect=_fake_table(seen)), \
         patch.object(calibration, "date") as fake_date:
        fake_date.today.return_value = date(2026, 7, 2)
        row = calibration._latest_calibration("SPY")
    assert row["calibration_date"] == date(2026, 7, 1)
    assert len(seen) == 1 and ":as_of" not in seen[0][0] and seen[0][1] == {"ticker": "SPY"}


def test_range_getters_pass_as_of_through():
    with patch.object(calibration, "_latest_calibration", return_value=None) as m:
        calibration.get_call_rsi_range("SPY", as_of=date(2026, 5, 4))
        calibration.get_put_rsi_range("SPY", as_of=date(2026, 5, 4))
        calibration.get_resolution_tier("SPY", "PUT", as_of=date(2026, 5, 4))
    assert [c.args for c in m.call_args_list] == [("SPY", date(2026, 5, 4))] * 3


def test_resolve_rsi_bands_tier_a():
    row = dict(_PIT_ROWS[1])
    with patch.object(calibration, "_latest_calibration", return_value=row) as m:
        bands = calibration.resolve_rsi_bands("IWM", as_of=date(2026, 5, 4))
    m.assert_called_once_with("IWM", date(2026, 5, 4))
    assert bands == {"call": (34.8, 49.9), "put": (49.9, 64.0), "call_tier": "A",
                     "put_tier": "A", "calibration_date": date(2026, 4, 1)}


def test_resolve_rsi_bands_tier_b_without_a_usable_row():
    with patch.object(calibration, "_latest_calibration", return_value=None):
        bands = calibration.resolve_rsi_bands("IWM", as_of=date(2026, 5, 4))
    assert bands == {"call": CALL_RSI_RANGE, "put": PUT_RSI_RANGE, "call_tier": "B",
                     "put_tier": "B", "calibration_date": None}
    half = {"calibration_date": date(2026, 4, 1), "rsi_p10": float("nan"), "rsi_p50": 50.0, "rsi_p90": 64.0}
    with patch.object(calibration, "_latest_calibration", return_value=half):
        bands = calibration.resolve_rsi_bands("IWM")
    assert bands["call"] == CALL_RSI_RANGE and bands["call_tier"] == "B"
    assert bands["put"] == (50.0, 64.0) and bands["put_tier"] == "A"
