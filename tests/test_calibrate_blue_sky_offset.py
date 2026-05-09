"""Unit tests for scripts.calibrate_blue_sky_offset.

Pure-helper tests against synthetic DataFrames — no Cloud SQL touched.
The DB write (`update_offset`) is exercised by integration runs and a
schema-shape test in tests/test_exit_config_overrides_schema.py.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from scripts.calibrate_blue_sky_offset import compute_blue_sky_offset


def _bars(rows: list[dict]) -> pd.DataFrame:
    """Build a daily-bar DataFrame matching the SQL projection.

    Prepends a "seed" day so each input row has a prev_close (the
    calibration step computes prev_close = close.shift(1).dropna()).
    The seed has pre_high == prev_close → gap_up_atr = 0, so it does
    NOT itself contribute extension events.
    """
    base_date = date(2026, 1, 1)
    out = []
    # Seed day — close=99 means pre_high (=99) and pre_low (=99) both
    # equal prev_close on day 2, so gap_up_atr/gap_down_atr both = 0.
    out.append({
        "date": base_date,
        "close": 99.0,
        "pre_high": 99.0, "pre_low": 99.0,
        "high": 99.0, "low": 99.0,
        "atr_14": 1.0,
    })
    for i, r in enumerate(rows, start=1):
        full = {
            "date": base_date + timedelta(days=i),
            "close": r.get("close", 100.0),
            "pre_high": r.get("pre_high"),
            "pre_low": r.get("pre_low"),
            "high": r.get("high", 100.0),
            "low": r.get("low", 100.0),
            "atr_14": r.get("atr_14", 1.0),
        }
        out.append(full)
    return pd.DataFrame(out)


def test_returns_none_on_empty_bars():
    assert compute_blue_sky_offset(pd.DataFrame()) is None


def test_returns_none_when_no_atr():
    df = _bars([
        {"close": 100, "pre_high": 102, "pre_low": 99, "high": 103, "low": 99,
         "atr_14": 0},
    ])
    assert compute_blue_sky_offset(df) is None


def test_returns_none_when_no_extension_events():
    """Pre_high pinned at session high every day → no positive extensions."""
    df = _bars([
        # Each row: gap up, but RTH high == pre_high (no extension)
        {"close": 100 + i, "pre_high": 102 + i, "pre_low": 99 + i,
         "high": 102 + i, "low": 99 + i, "atr_14": 1.0}
        for i in range(20)
    ])
    assert compute_blue_sky_offset(df) is None


def test_computes_mean_extension_in_atr_units():
    """Long extensions: 0.10, 0.20, 0.30 ATR → mean 0.20 → rounded 0.20."""
    df = _bars([
        {"close": 100, "pre_high": 102, "pre_low": 99,
         "high": 102.10, "low": 99, "atr_14": 1.0},   # extension 0.10
        {"close": 100, "pre_high": 102, "pre_low": 99,
         "high": 102.20, "low": 99, "atr_14": 1.0},   # extension 0.20
        {"close": 100, "pre_high": 102, "pre_low": 99,
         "high": 102.30, "low": 99, "atr_14": 1.0},   # extension 0.30
    ])
    result = compute_blue_sky_offset(df, metric="mean")
    assert result is not None
    assert result["n_events"] == 3
    assert result["n_long_events"] == 3
    assert result["raw_value"] == pytest.approx(0.20, abs=1e-3)
    assert result["offset"] == 0.20  # rounded to 0.05 grid


def test_p75_metric_picks_higher_value():
    df = _bars([
        {"close": 100, "pre_high": 102, "pre_low": 99,
         "high": 102 + ext, "low": 99, "atr_14": 1.0}
        for ext in [0.05, 0.10, 0.15, 0.30, 0.40]
    ])
    result = compute_blue_sky_offset(df, metric="p75")
    assert result is not None
    # p75 of [0.05, 0.10, 0.15, 0.30, 0.40] = 0.30 → rounded
    assert result["raw_value"] == pytest.approx(0.30, abs=1e-3)
    assert result["offset"] == 0.30


def test_short_side_extensions_are_combined_with_longs():
    """A gap-down day with RTH extending below pre_low contributes to
    the same offset distribution as a gap-up extension."""
    df = _bars([
        # Gap-up + 0.20 ATR long extension
        {"close": 100, "pre_high": 102, "pre_low": 100.5,
         "high": 102.20, "low": 100, "atr_14": 1.0},
        # Gap-down + 0.20 ATR short extension (pre_low - low = 0.20)
        {"close": 100, "pre_high": 99.5, "pre_low": 98,
         "high": 100, "low": 97.80, "atr_14": 1.0},
    ])
    result = compute_blue_sky_offset(df, metric="mean")
    assert result is not None
    assert result["n_long_events"] == 1
    assert result["n_short_events"] == 1
    assert result["n_events"] == 2
    assert result["raw_value"] == pytest.approx(0.20, abs=1e-3)


def test_floor_clamps_tiny_extensions():
    """Mean extension below 0.05 ATR floors at 0.05."""
    df = _bars([
        {"close": 100, "pre_high": 102, "pre_low": 99,
         "high": 102.01, "low": 99, "atr_14": 1.0},   # 0.01
        {"close": 100, "pre_high": 102, "pre_low": 99,
         "high": 102.02, "low": 99, "atr_14": 1.0},   # 0.02
    ])
    result = compute_blue_sky_offset(df, metric="mean")
    assert result is not None
    assert result["raw_value"] == pytest.approx(0.015, abs=1e-3)
    assert result["clamped_value"] == 0.05  # floored
    assert result["offset"] == 0.05


def test_ceiling_clamps_huge_extensions():
    """Mean extension above 0.50 ATR ceilings at 0.50."""
    df = _bars([
        {"close": 100, "pre_high": 102, "pre_low": 99,
         "high": 102.80, "low": 99, "atr_14": 1.0},   # 0.80 ATR
        {"close": 100, "pre_high": 102, "pre_low": 99,
         "high": 103.00, "low": 99, "atr_14": 1.0},   # 1.00 ATR
    ])
    result = compute_blue_sky_offset(df, metric="mean")
    assert result is not None
    assert result["raw_value"] == pytest.approx(0.90, abs=1e-3)
    assert result["clamped_value"] == 0.50  # ceilinged
    assert result["offset"] == 0.50


def test_rounding_to_grid_is_stable():
    """0.18 raw → 0.20 (nearest 0.05); 0.12 → 0.10."""
    df_high = _bars([
        {"close": 100, "pre_high": 102, "pre_low": 99,
         "high": 102.18, "low": 99, "atr_14": 1.0},
    ] * 10)  # 10 identical rows
    r = compute_blue_sky_offset(df_high, metric="mean")
    assert r["offset"] == 0.20  # 0.18 rounds up

    df_low = _bars([
        {"close": 100, "pre_high": 102, "pre_low": 99,
         "high": 102.12, "low": 99, "atr_14": 1.0},
    ] * 10)
    r = compute_blue_sky_offset(df_low, metric="mean")
    assert r["offset"] == 0.10  # 0.12 rounds down


def test_only_gap_up_days_contribute_to_long_extensions():
    """A flat-or-down day where pre_high < prev_close should NOT count
    as a long extension — even if RTH printed a higher high."""
    df = _bars([
        # prev_close=100, pre_high=99 (flat or gap-down). Excluded
        # from long_extensions even though high=102 > pre_high.
        {"close": 100, "pre_high": 102, "pre_low": 99,
         "high": 102, "low": 99, "atr_14": 1.0},   # day 1 establishes prev_close
        {"close": 100, "pre_high": 99, "pre_low": 95,
         "high": 102, "low": 99, "atr_14": 1.0},   # day 2: gap-DOWN, RTH long ext ignored
    ])
    result = compute_blue_sky_offset(df, metric="mean")
    # Day 2 gap_up_atr = (99-100)/1.0 = -1.0 (NOT > 0) → long_ext excluded.
    # Day 2 gap_down_atr = (100-95)/1.0 = +5.0 > 0; short_ext = (95-99)/1.0 = -4.0 ≤ 0 → excluded.
    # Day 1 has no prev_close so it gets dropped by .shift().dropna().
    assert result is None  # No usable events
