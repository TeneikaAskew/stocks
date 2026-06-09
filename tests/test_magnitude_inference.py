"""Phase B regression tests for gcp/research/magnitude_engine/mag_inference.py.

The job has three failure modes that MUST surface as exit 1 (CLAUDE.md
§3.7 no silent fallback):

1. Model artifact missing in GCS -> RuntimeError that propagates
2. Feature column drift between training schema and live features
3. Zero-output (model returned wrong shape, all bars dropped to NaN
   filter, etc.) -> reported but not silently treated as success

Tests use the same import-stub pattern as Phase A.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Same lightweight import stubs as Phase A — sklearn/lightgbm/GCS are
# in requirements.txt but not in this sandbox.
for _mod in (
    "google", "google.cloud", "google.cloud.storage",
    "sklearn", "sklearn.calibration", "sklearn.metrics",
    "lightgbm", "joblib",
):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["sklearn.metrics"].log_loss = lambda *a, **k: 0.5
sys.modules["sklearn.calibration"].CalibratedClassifierCV = MagicMock


# ──────────────────── _parse_cells ────────────────────

def test_parse_cells_default_when_empty():
    from gcp.research.magnitude_engine.mag_inference import (
        _parse_cells, DEFAULT_CELLS,
    )
    assert _parse_cells(None) == list(DEFAULT_CELLS)
    assert _parse_cells("") == list(DEFAULT_CELLS)
    assert _parse_cells("   ") == list(DEFAULT_CELLS)


def test_parse_cells_one():
    from gcp.research.magnitude_engine.mag_inference import _parse_cells
    assert _parse_cells("IWM:5m") == [("IWM", "5m")]


def test_parse_cells_many_with_whitespace():
    from gcp.research.magnitude_engine.mag_inference import _parse_cells
    assert _parse_cells(" iwm:5m , SPY:15m ") == [
        ("IWM", "5m"), ("SPY", "15m"),
    ]


def test_parse_cells_invalid_raises():
    from gcp.research.magnitude_engine.mag_inference import _parse_cells
    with pytest.raises(ValueError):
        _parse_cells("IWM")  # missing :tf


# ──────────────────── _score_and_persist contract ────────────────────

@pytest.fixture
def fake_features():
    """3 rows with 4 features; matches what a 5m intraday slice looks like."""
    return pd.DataFrame({
        "ts": pd.date_range("2026-06-02 13:25", periods=3,
                            freq="5min", tz="UTC"),
        "rsi_14": [55.0, 60.0, 65.0],
        "atr_14": [1.0, 1.2, 1.5],
        "ema_9":  [100.0, 100.5, 101.0],
        "vwap":   [99.5, 100.0, 100.5],
    })


def _fake_model(probs):
    """Build a mock model whose predict_proba returns the given probs."""
    m = MagicMock()
    m.predict_proba.return_value = np.array(probs)
    return m


def test_score_and_persist_returns_zero_on_empty_features():
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist
    engine = MagicMock()
    n = _score_and_persist(engine, "IWM", "5m",
                            _fake_model([]), ["rsi_14"], "v1",
                            pd.DataFrame())
    assert n == 0
    engine.begin.assert_not_called()


def test_score_and_persist_raises_on_feature_drift(fake_features):
    """If the model was trained on a column that's no longer in
    `features`, fail loud — don't silently fabricate."""
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist
    engine = MagicMock()
    # Model expects 'gone_feature' which fake_features doesn't have.
    with pytest.raises(RuntimeError, match="feature drift"):
        _score_and_persist(engine, "IWM", "5m",
                            _fake_model([[0.25] * 4] * 3),
                            ["rsi_14", "atr_14", "gone_feature"],
                            "v1", fake_features)


def test_score_and_persist_raises_on_wrong_class_count(fake_features):
    """Model returning N != 4 classes is a contract violation — must
    raise so we don't insert garbage."""
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist
    engine = MagicMock()
    # Model returns 3-class output instead of 4.
    bad_model = _fake_model([[0.33, 0.34, 0.33]] * 3)
    feature_cols = ["rsi_14", "atr_14", "ema_9", "vwap"]
    with pytest.raises(RuntimeError, match="expected 4"):
        _score_and_persist(engine, "IWM", "5m",
                            bad_model, feature_cols, "v1", fake_features)


def test_score_and_persist_skips_nan_rows(fake_features):
    """Rows with any-NaN features are filtered out before scoring (model
    can't handle them); the count is logged but doesn't fail the job."""
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist

    # Inject a NaN into one feature row.
    fake_features.loc[1, "rsi_14"] = np.nan

    # Model expects to be called with only the surviving rows (2 of 3).
    proba = np.array([[0.1, 0.2, 0.3, 0.4]] * 2)
    model = MagicMock()
    model.predict_proba.return_value = proba

    engine = MagicMock()
    feature_cols = ["rsi_14", "atr_14", "ema_9", "vwap"]
    n = _score_and_persist(engine, "IWM", "5m",
                            model, feature_cols, "v1", fake_features)
    # 2 surviving bars persisted.
    assert n == 2
    # Model was called with 2 rows (not 3).
    args, _ = model.predict_proba.call_args
    assert args[0].shape == (2, 4)


def test_score_and_persist_zero_after_nan_filter(fake_features):
    """If EVERY bar has NaN features, return 0 cleanly — don't crash on
    empty input to model.predict_proba."""
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist
    fake_features["rsi_14"] = np.nan
    model = MagicMock()
    engine = MagicMock()
    n = _score_and_persist(engine, "IWM", "5m",
                            model, ["rsi_14"], "v1", fake_features)
    assert n == 0
    model.predict_proba.assert_not_called()
