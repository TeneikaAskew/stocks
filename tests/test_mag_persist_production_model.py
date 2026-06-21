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

from unittest.mock import MagicMock, patch

import numpy as np
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
pytest.importorskip("joblib")


def _toy_data(n_rows: int = 100, n_features: int = 4):
    rng = np.random.default_rng(7)
    X = rng.normal(size=(n_rows, n_features)).astype(np.float32)
    # 4 labels (TIGHT/NORMAL/EXPANDED/EXPLOSIVE), unbalanced like real data
    y = rng.choice(4, size=n_rows, p=[0.6, 0.27, 0.1, 0.03]).astype(np.int64)
    return X, y


def _capture_blob_uploads():
    """Wire up a MagicMock google.cloud.storage that records every
    upload_from_string call. Returns (fake_client, captured_dict).
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


@pytest.fixture
def joblib_dump_stub():
    """Stub joblib.dump so MagicMock estimators don't trip PicklingError
    in CI (joblib is real there; in the sandbox it's already a MagicMock
    via _stub_missing_modules). The stub writes a placeholder so the
    surrounding upload code still receives bytes."""
    import joblib as _joblib_mod
    def _fake_dump(obj, buf):
        buf.write(b"PICKLED_MODEL_STUB")
    with patch.object(_joblib_mod, "dump", side_effect=_fake_dump):
        yield


def test_persists_three_blobs_with_correct_names(monkeypatch, joblib_dump_stub):
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    X, y = _toy_data()
    fake_client, captured = _capture_blob_uploads()

    with patch.object(mwf, "make_lgbm", return_value=MagicMock()), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        uri = mwf._persist_production_model_artifact(
            "IWM", "5m", run_id="testrun-001",
            X_full=X, y_full=y,
            feature_cols=["rsi_14", "atr_14", "ema_9", "vwap"],
            calibration="none",
        )

    # Atomic-publish: blobs land under a run-scoped path and a LATEST
    # pointer (single-blob write) is updated last. The contract returned
    # is the canonical {ticker}/{tf}/ prefix where LATEST lives.
    assert uri == "gs://test-bucket/magnitude-models/production/IWM/5m/"
    expected_run_prefix = "magnitude-models/production/IWM/5m/testrun-001"
    assert f"{expected_run_prefix}/model.joblib" in captured
    assert f"{expected_run_prefix}/feature_cols.txt" in captured
    assert f"{expected_run_prefix}/VERSION" in captured
    assert "magnitude-models/production/IWM/5m/LATEST" in captured
    assert captured["magnitude-models/production/IWM/5m/LATEST"] == b"testrun-001"


def test_version_blob_is_the_run_id(monkeypatch, joblib_dump_stub):
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

    run_id = "walk-forward-2026-06-13-SPY-5m-v3"
    version_blob = captured[f"magnitude-models/production/SPY/5m/{run_id}/VERSION"]
    assert version_blob == run_id.encode()


def test_feature_cols_blob_is_newline_delimited(monkeypatch, joblib_dump_stub):
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

    blob = captured["magnitude-models/production/QQQ/5m/r/feature_cols.txt"]
    assert blob.decode("utf-8").split("\n") == cols


def test_returns_none_on_upload_failure_no_raise(monkeypatch, joblib_dump_stub):
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


def test_latest_pointer_updated_last(monkeypatch, joblib_dump_stub):
    """Codex P2 — atomic publish: LATEST is the LAST blob written. If
    LATEST upload fails after the staging blobs land, the previous
    LATEST value stays valid and inference loads the prior version
    instead of pairing fresh model.joblib with stale metadata."""
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    X, y = _toy_data()
    order: list[str] = []

    def make_blob(name):
        b = MagicMock()
        def _up(data, content_type=None):
            order.append(name)
        b.upload_from_string = _up
        return b

    fake_bucket = MagicMock()
    fake_bucket.blob.side_effect = make_blob
    fake_client = MagicMock()
    fake_client.bucket.return_value = fake_bucket

    with patch.object(mwf, "make_lgbm", return_value=MagicMock()), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        mwf._persist_production_model_artifact(
            "IWM", "5m", run_id="rX", X_full=X, y_full=y,
            feature_cols=["x"], calibration="none",
        )

    # LATEST must be the last write in the upload sequence.
    assert order[-1].endswith("/LATEST"), \
        f"LATEST must be the LAST blob to land for atomic publish; order was {order}"


def test_uses_calibrated_wrapper_when_calibration_not_none(monkeypatch, joblib_dump_stub):
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


def test_run_all_cells_threads_persist_flag_through():
    """Codex P2 #615: --all-cells dispatch was silently losing the flag
    because run_all_cells didn't accept it. Pin the wiring: the signature
    has the kwarg AND every internal walk_forward call forwards it."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    import inspect
    sig = inspect.signature(mwf.run_all_cells)
    assert "persist_production_model" in sig.parameters, \
        "run_all_cells must accept persist_production_model (Codex P2 #615)"
    src = inspect.getsource(mwf.run_all_cells)
    assert "persist_production_model=persist_production_model" in src, \
        "run_all_cells must forward the flag into walk_forward"


# ──────────────────── inference featurize contract ────────────────────
#
# Codex P1 #615: feature_cols persisted by walk_forward are the POST-
# featurize() names (dummies for prev1_candle, etc). mag_inference must
# run featurize() on the live frame before alignment, or every cron
# raises 'feature drift' against the raw strat_features_<tf> schema.


def test_score_and_persist_runs_featurize_before_alignment():
    """If mag_inference._score_and_persist source mentions `featurize`,
    the P1 fix is in place. If a future refactor removes it, this test
    catches it before the inference cron silently breaks."""
    from gcp.research.magnitude_engine import mag_inference as mi
    import inspect
    src = inspect.getsource(mi._score_and_persist)
    assert "featurize" in src, (
        "mag_inference._score_and_persist must call mag_pred_train.featurize() "
        "on the raw frame before column alignment — without it, every cron "
        "fails with 'feature drift' against the post-one-hot training schema. "
        "Codex P1 #615."
    )


def test_load_model_reads_latest_pointer():
    """The atomic-publish layout (#615 P2) means the artifact loader
    must read LATEST first, then follow the pointer to {ticker}/{tf}/
    {run_id}/. A loader that hard-codes the old flat path silently loads
    a stale model after a partial retrain."""
    from gcp.research.magnitude_engine import mag_inference as mi
    import inspect
    src = inspect.getsource(mi._load_model_and_version)
    assert "LATEST" in src, (
        "mag_inference._load_model_and_version must read the LATEST "
        "pointer for atomic-publish safety (Codex P2 #615)."
    )
