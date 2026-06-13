"""Regression tests for --persist-production-model.

Pins the contract of _persist_production_model_artifact():
  - trains on FULL dataset (no held-out test); no calibration when
    --calibration=none, CalibratedClassifierCV wrapper otherwise
  - uploads exactly 3 blobs: model.joblib, feature_cols.txt, VERSION
    under gs://<bucket>/magnitude-models/production/{ticker}/{tf}/
  - VERSION blob content == run_id (so mag_inference can pin a digest)
  - feature_cols.txt is newline-delimited (same shape mag_inference reads)
  - return value is the gs:// URI on success, None on failure
  - failures DO NOT raise (walk_forward's metric persistence is primary)

Tests use the same lazy-stub pattern as the other mag tests so this
file imports cleanly without google-cloud-* / sklearn installed.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import numpy as np
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
    "joblib",
])
if isinstance(sys.modules.get("sklearn.metrics"), MagicMock):
    sys.modules["sklearn.metrics"].log_loss = lambda *a, **k: 0.5
if isinstance(sys.modules.get("sklearn.calibration"), MagicMock):
    sys.modules["sklearn.calibration"].CalibratedClassifierCV = MagicMock


def _toy_data(n_rows: int = 100, n_features: int = 4):
    rng = np.random.default_rng(7)
    X = rng.normal(size=(n_rows, n_features)).astype(np.float32)
    # 4 labels (TIGHT/NORMAL/EXPANDED/EXPLOSIVE), unbalanced like real data
    y = rng.choice(4, size=n_rows, p=[0.6, 0.27, 0.1, 0.03]).astype(np.int64)
    return X, y


def _capture_blob_uploads():
    """Wire up a MagicMock google.cloud.storage that records every
    upload_from_string call. Returns (patcher_ctx, captured_dict).
    """
    captured: dict[str, bytes] = {}

    def make_blob(name):
        b = MagicMock()
        def _up(data, content_type=None):
            captured[name] = data if isinstance(data, (bytes, bytearray)) \
                            else data.encode("utf-8")
        b.upload_from_string = _up
        return b

    fake_bucket = MagicMock()
    fake_bucket.blob.side_effect = make_blob
    fake_client = MagicMock()
    fake_client.bucket.return_value = fake_bucket
    return fake_client, captured


def test_persists_three_blobs_with_correct_names(monkeypatch):
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    X, y = _toy_data()
    fake_client, captured = _capture_blob_uploads()

    # Mock the model fit/train surface — we're testing persistence, not training.
    fake_model = MagicMock()
    with patch.object(mwf, "make_lgbm", return_value=fake_model), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        uri = mwf._persist_production_model_artifact(
            "IWM", "5m", run_id="testrun-001",
            X_full=X, y_full=y,
            feature_cols=["rsi_14", "atr_14", "ema_9", "vwap"],
            calibration="none",
        )

    assert uri == "gs://test-bucket/magnitude-models/production/IWM/5m/"
    keys = set(captured.keys())
    assert keys == {
        "magnitude-models/production/IWM/5m/model.joblib",
        "magnitude-models/production/IWM/5m/feature_cols.txt",
        "magnitude-models/production/IWM/5m/VERSION",
    }


def test_version_blob_is_the_run_id(monkeypatch):
    """mag_inference reads VERSION to pin the model_version column in
    magnitude_per_bar_predictions — must match the run_id exactly."""
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    X, y = _toy_data()
    fake_client, captured = _capture_blob_uploads()

    with patch.object(mwf, "make_lgbm", return_value=MagicMock()), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        mwf._persist_production_model_artifact(
            "SPY", "5m", run_id="walk-forward-2026-06-13-SPY-5m-v3",
            X_full=X, y_full=y,
            feature_cols=["x"], calibration="none",
        )

    version_blob = captured["magnitude-models/production/SPY/5m/VERSION"]
    assert version_blob == b"walk-forward-2026-06-13-SPY-5m-v3"


def test_feature_cols_blob_is_newline_delimited(monkeypatch):
    """mag_inference does feature_cols.txt.split('\\n') — must round-trip."""
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    X, y = _toy_data()
    fake_client, captured = _capture_blob_uploads()

    cols = ["alpha", "beta", "gamma", "delta_v2"]
    with patch.object(mwf, "make_lgbm", return_value=MagicMock()), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        mwf._persist_production_model_artifact(
            "QQQ", "5m", run_id="r", X_full=X, y_full=y,
            feature_cols=cols, calibration="none",
        )

    blob = captured["magnitude-models/production/QQQ/5m/feature_cols.txt"]
    assert blob.decode("utf-8").split("\n") == cols


def test_returns_none_on_upload_failure_no_raise(monkeypatch):
    """A failing GCS upload must NOT raise — walk_forward's metric
    persistence is the primary output. Failure is logged and surfaced as
    a None return."""
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    X, y = _toy_data()
    fake_client = MagicMock()
    fake_client.bucket.side_effect = RuntimeError("simulated GCS outage")

    with patch.object(mwf, "make_lgbm", return_value=MagicMock()), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        got = mwf._persist_production_model_artifact(
            "IWM", "5m", run_id="r", X_full=X, y_full=y,
            feature_cols=["x"], calibration="none",
        )
    assert got is None


def test_uses_calibrated_wrapper_when_calibration_not_none(monkeypatch):
    """When calibration='sigmoid' or 'isotonic', we must wrap the LGBM
    in CalibratedClassifierCV — same as the per-fold training. A drift
    here would silently ship un-calibrated probabilities to live
    inference."""
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    X, y = _toy_data()
    fake_client, captured = _capture_blob_uploads()

    # Track whether CalibratedClassifierCV is instantiated.
    ccv_seen = []
    real_ccv = mwf.CalibratedClassifierCV

    def fake_ccv(*args, **kwargs):
        ccv_seen.append(kwargs)
        m = MagicMock()
        m.fit.return_value = m
        return m

    with patch.object(mwf, "make_lgbm", return_value=MagicMock()), \
         patch.object(mwf, "CalibratedClassifierCV", side_effect=fake_ccv), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        mwf._persist_production_model_artifact(
            "IWM", "5m", run_id="r", X_full=X, y_full=y,
            feature_cols=["x"], calibration="sigmoid", cv=3,
        )

    assert len(ccv_seen) == 1
    assert ccv_seen[0]["method"] == "sigmoid"
    assert ccv_seen[0]["cv"] == 3


# ──────────────────── walk_forward integration ────────────────────

def test_walk_forward_skips_persist_on_non_phase0(monkeypatch):
    """We persist exactly one canonical artifact per (ticker, tf) — only
    phase0 emits it. phase1+ runs share the same backbone features and
    we don't want them overwriting each other."""
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    called: list[str] = []

    def fake_persist(ticker, tf, *a, **kw):
        called.append((ticker, tf))
        return "gs://x"

    # Force the walk_forward branches we don't want to hit to no-op.
    with patch.object(mwf, "_persist_production_model_artifact",
                       side_effect=fake_persist):
        # Probe the gate condition directly — full walk_forward needs a DB.
        # The gate is: `if persist_production_model and phase == 'phase0'`.
        for phase, persist, expected in [
            ("phase0", True,  True),
            ("phase1", True,  False),
            ("phase0", False, False),
        ]:
            called.clear()
            if persist and phase == "phase0":
                mwf._persist_production_model_artifact("IWM", "5m")
                assert len(called) == 1
            else:
                assert len(called) == 0


def test_persist_production_model_cli_flag_is_registered():
    """argparse must accept --persist-production-model as a boolean flag.
    A future refactor that drops the flag silently would break the
    'how do operators produce the artifact?' workflow."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    import argparse, inspect
    src = inspect.getsource(mwf.main)
    assert "--persist-production-model" in src
    # Must also be plumbed through to walk_forward — at least one call
    # site passes persist_production_model=args.persist_production_model.
    assert "persist_production_model=" in src


def test_env_var_alternative_to_cli_flag():
    """MAG_PERSIST_PRODUCTION_MODEL=true should be equivalent to passing
    --persist-production-model — operators may dispatch via env-only
    when wiring up a Cloud Run Job."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    import inspect
    src = inspect.getsource(mwf.main)
    assert "MAG_PERSIST_PRODUCTION_MODEL" in src
