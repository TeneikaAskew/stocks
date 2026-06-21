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

import numpy as np
import pandas as pd
import pytest

# Skip cleanly when the heavy ML / cloud libraries aren't installed
# (offline sandbox). Production CI installs them via requirements.txt and
# runs these tests for real. We must NOT inject MagicMock stubs into
# sys.modules: a stub inserted at collection time leaks into the shared
# module cache, so a later sibling test that imports the real library
# silently receives the fake instead (order-dependent false pass / crash;
# caught 2026-06-09 on PR #597, re-audited 2026-06-21). importorskip is
# the no-leak equivalent of the old lazy-stub.
pytest.importorskip("google.cloud.storage")
pytest.importorskip("sklearn.calibration")
pytest.importorskip("sklearn.metrics")
pytest.importorskip("lightgbm")


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
    # The value column is imputed to 0 for the model's numeric contract...
    assert (X["vix_close"] == 0.0).all()
    # ...but the imputed 0 must NOT be silently indistinguishable from a
    # real zero reading (CLAUDE.md §3.7). featurize emits a companion
    # missing-data flag so the model (and any auditor) can tell that the
    # whole column was unavailable rather than legitimately zero.
    assert "vix_close__isna" in cols, (
        "all-NaN feature must carry an explicit missing-data indicator; "
        "a bare fillna(0) hides the gap (see CLAUDE.md §3.7)"
    )
    assert (X["vix_close__isna"] == 1.0).all(), (
        "the missing-data flag must be 1 wherever the source was NULL"
    )


def test_featurize_missing_flag_distinguishes_real_zero_from_missing():
    """A genuine 0 reading and a missing (NULL) reading must produce
    different feature rows — the whole point of the missing-data flag.
    A column that is half real-zeros and half NULL gets an __isna flag
    that is 0 on the real rows and 1 on the NULL rows."""
    from gcp.research.magnitude_engine.mag_pred_train import featurize
    df = _make_frame_with_all_nan_object_col()
    # rsi_14 already present and fully populated; introduce a sparse-NULL
    # numeric where row 0 is a real 0.0 and row 1 is missing.
    df["sparse_feat"] = [0.0, np.nan, 2.0, 3.0]
    X, cols = featurize(df)
    assert "sparse_feat" in cols
    assert "sparse_feat__isna" in cols
    # Real 0.0 row: value 0, flag 0.  Missing row: value imputed to 0, flag 1.
    assert X["sparse_feat"].iloc[0] == 0.0
    assert X["sparse_feat__isna"].iloc[0] == 0.0  # real zero, not missing
    assert X["sparse_feat"].iloc[1] == 0.0        # imputed
    assert X["sparse_feat__isna"].iloc[1] == 1.0  # but flagged missing
    # A fully-populated column gets NO redundant flag.
    assert "rsi_14" in cols
    assert "rsi_14__isna" not in cols


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
