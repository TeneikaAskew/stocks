"""Regression test for featurize() robustness to all-NaN columns.

Real failure 2026-06-19: magnitude-inference rejected `vix_close` as
feature drift because pd.read_sql returned the column as `dtype=object`
when the recently-backfilled strat_features_5m bars had vix_close=NULL
for every row in the inference window. The training featurize had seen
~99% of the column populated and included it in feature_cols.txt; the
inference featurize dropped it via the strict-dtype filter, then the
alignment check raised 'feature drift for vix_close'.

This test asserts that featurize() force-casts all-NaN object columns
to float64 BEFORE the dtype filter, so the train-vs-inference contract
holds. The downstream `.fillna(0)` produces a zero column with the same
semantics training would have used for sparse-NULL rows.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest


def _stub_missing_modules(mods: list[str]) -> None:
    for m in mods:
        try:
            __import__(m)
        except ImportError:
            parts = m.split(".")
            for i in range(1, len(parts) + 1):
                key = ".".join(parts[:i])
                if key not in sys.modules:
                    sys.modules[key] = MagicMock()


_stub_missing_modules([
    "google.cloud.storage",
    "sklearn.calibration",
    "sklearn.metrics",
    "lightgbm",
])


def _make_frame_with_all_nan_object_col() -> pd.DataFrame:
    """Mirror the live pd.read_sql shape that triggered the bug:
    most columns are real floats, one column (vix_close) arrives as
    object dtype because every row was NULL."""
    return pd.DataFrame({
        "ticker": ["IWM"] * 4,
        "ts": pd.date_range("2026-06-18 13:30", periods=4, freq="5min", tz="UTC"),
        "tf": ["5m"] * 4,
        "bar_date": pd.date_range("2026-06-18", periods=4, freq="D").date,
        "open":   [200.0, 201.0, 202.0, 203.0],
        "high":   [201.0, 202.0, 203.0, 204.0],
        "low":    [199.0, 200.0, 201.0, 202.0],
        "close":  [200.5, 201.5, 202.5, 203.5],
        "volume": [1000, 1100, 1200, 1300],
        # Real numeric features that the model will request.
        "rsi_14": [55.0, 60.0, 65.0, 70.0],
        "atr_14": [1.0, 1.2, 1.5, 1.8],
        # The bug-trigger: all-NULL column arriving as object dtype.
        # This is what pd.read_sql produces from DOUBLE PRECISION with
        # every row NULL.
        "vix_close": pd.Series([None, None, None, None], dtype=object),
        # Forward-look column that featurize() drops.
        "fwd_close_5bars": [200.6, 201.6, 202.6, 203.6],
    })


def test_featurize_includes_all_nan_object_column_as_float64():
    """The regression fix: featurize must promote object-dtype all-NaN
    columns to float64 so the dtype filter accepts them and the column
    appears in feature_cols. Pre-fix this test fails — `vix_close` is
    not in the returned cols list because its dtype=object was rejected."""
    from gcp.research.magnitude_engine.mag_pred_train import featurize
    df = _make_frame_with_all_nan_object_col()
    X, cols = featurize(df)
    assert "vix_close" in cols, (
        "featurize must include all-NaN columns that the model expects; "
        "dropping them silently breaks train-vs-inference contract "
        "(see 2026-06-19 magnitude-inference feature drift)"
    )
    # The downstream fillna(0).astype(float32) should also keep it.
    assert "vix_close" in X.columns
    assert X["vix_close"].dtype == np.float32
    # All values should be 0 (semantically: "no signal", same as training
    # would have produced for a sparse-NULL row).
    assert (X["vix_close"] == 0.0).all()


def test_featurize_preserves_non_nan_columns_unchanged():
    """The fix must be surgical — non-all-NaN columns are unaffected."""
    from gcp.research.magnitude_engine.mag_pred_train import featurize
    df = _make_frame_with_all_nan_object_col()
    X, cols = featurize(df)
    assert "rsi_14" in cols
    assert "atr_14" in cols
    # Forward-look features still dropped.
    assert "fwd_close_5bars" not in cols
    # Bookkeeping columns still dropped.
    for c in ("ticker", "ts", "tf", "bar_date", "open", "high", "low",
              "close", "volume"):
        assert c not in cols, f"{c} should be dropped by featurize"


def test_featurize_does_not_promote_object_columns_with_real_values():
    """If a column legitimately has dtype=object (e.g. a string), we must
    NOT silently coerce it to float — that would corrupt categoricals
    that featurize doesn't know about yet."""
    from gcp.research.magnitude_engine.mag_pred_train import featurize
    df = _make_frame_with_all_nan_object_col()
    df["unknown_category"] = pd.Series(["x", "y", "z", "w"], dtype=object)
    X, cols = featurize(df)
    # Mixed-string column is NOT all-NaN -> stays object -> dtype filter
    # drops it. That's the safe behavior; we only promote ALL-NaN cols.
    assert "unknown_category" not in cols
