"""Hermetic tests for lib/features/intraday_flow.compute_derived — the PURE
OFI feature math (numpy+pandas only, no DB). Pins the §3.7 no-silent-fallback
contract (zero/empty volume -> NaN, never 0) and the within-day grouping.
"""
import numpy as np
import pandas as pd
import pytest

from lib.features.intraday_flow import compute_derived, FEATURE_COLS


def _buckets(rows):
    """rows: list of (ts_iso_utc, signed_vol, tot_vol, up_vol, dn_vol, n_min)."""
    return pd.DataFrame(
        [{"ts": r[0], "signed_vol": r[1], "tot_vol": r[2],
          "up_vol": r[3], "dn_vol": r[4], "n_min": r[5]} for r in rows])


def test_empty_returns_empty_with_cols():
    out = compute_derived(_buckets([]))
    assert list(out.columns) == FEATURE_COLS
    assert out.empty


def test_ofi_norm_basic():
    # 9:30 and 9:45 ET = 14:30/14:45 UTC, same ET day.
    b = _buckets([
        ("2024-03-01 14:30:00+00:00", 5.0, 10.0, 7.0, 2.0, 15),
        ("2024-03-01 14:45:00+00:00", -3.0, 6.0, 1.0, 4.0, 15),
    ])
    out = compute_derived(b)
    assert out["ofi_norm"].iloc[0] == pytest.approx(0.5)
    assert out["ofi_norm"].iloc[1] == pytest.approx(-0.5)


def test_zero_total_volume_is_nan_not_zero():
    # §3.7: a zero-volume bucket must read as MISSING (NaN), never 0 imbalance.
    b = _buckets([
        ("2024-03-01 14:30:00+00:00", 0.0, 0.0, 0.0, 0.0, 0),
        ("2024-03-01 14:45:00+00:00", 4.0, 8.0, 6.0, 2.0, 15),
    ])
    out = compute_derived(b)
    assert np.isnan(out["ofi_norm"].iloc[0])
    assert out["ofi_norm"].iloc[1] == pytest.approx(0.5)


def test_cvd_intraday_runs_within_day():
    b = _buckets([
        ("2024-03-01 14:30:00+00:00", 5.0, 10.0, 7.0, 2.0, 15),
        ("2024-03-01 14:45:00+00:00", -3.0, 6.0, 1.0, 4.0, 15),
    ])
    out = compute_derived(b)
    # bar1: 5/10 = 0.5 ; bar2: (5-3)/(10+6) = 2/16 = 0.125
    assert out["cvd_intraday"].iloc[0] == pytest.approx(0.5)
    assert out["cvd_intraday"].iloc[1] == pytest.approx(0.125)


def test_cvd_resets_across_days():
    b = _buckets([
        ("2024-03-01 14:30:00+00:00", 8.0, 10.0, 9.0, 1.0, 15),  # day1
        ("2024-03-04 14:30:00+00:00", -2.0, 10.0, 3.0, 5.0, 15),  # day2 (Mon)
    ])
    out = compute_derived(b)
    # day2's first bar CVD must be its own, not carry day1's +8.
    assert out["cvd_intraday"].iloc[1] == pytest.approx(-0.2)


def test_ofi_3bar_persistence_within_day():
    b = _buckets([
        ("2024-03-01 14:30:00+00:00", 6.0, 10.0, 8.0, 2.0, 15),  # ofi 0.6
        ("2024-03-01 14:45:00+00:00", 0.0, 10.0, 5.0, 5.0, 15),  # ofi 0.0
        ("2024-03-01 15:00:00+00:00", 3.0, 10.0, 6.0, 4.0, 15),  # ofi 0.3
    ])
    out = compute_derived(b)
    # min_periods=1 expanding-to-3 mean: [0.6, 0.3, 0.3]
    assert out["ofi_3bar"].iloc[0] == pytest.approx(0.6)
    assert out["ofi_3bar"].iloc[1] == pytest.approx(0.3)
    assert out["ofi_3bar"].iloc[2] == pytest.approx(0.3)


def test_nan_signed_vol_propagates():
    b = _buckets([
        ("2024-03-01 14:30:00+00:00", np.nan, 10.0, np.nan, np.nan, 15),
    ])
    out = compute_derived(b)
    assert np.isnan(out["ofi_norm"].iloc[0])
    assert np.isnan(out["cvd_intraday"].iloc[0])


def test_index_is_ts_and_sorted():
    b = _buckets([
        ("2024-03-01 14:45:00+00:00", -3.0, 6.0, 1.0, 4.0, 15),
        ("2024-03-01 14:30:00+00:00", 5.0, 10.0, 7.0, 2.0, 15),
    ])
    out = compute_derived(b)
    assert out.index.name == "ts"
    assert list(out.index) == sorted(out.index)
