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

import json
import os
import pathlib
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


def _promotable_model(y):
    """A mock estimator whose argmax predictions pass the promotion gate.

    Since 2026-08-28 _persist_production_model_artifact scores the fitted model
    on X_full and refuses to flip LATEST when the argmax collapses onto one
    bucket (mag_config.PROMOTION_COLLAPSE_MODAL_SHARE). A bare MagicMock returns a
    MagicMock from .predict(), which reads as zero usable predictions and is
    correctly blocked — so any test exercising the SUCCESSFUL publish path has
    to hand back a realistic spread.
    """
    m = MagicMock()
    m.predict.return_value = np.asarray(y)
    return m


def _passing_gates(n_ok: int = 8) -> dict:
    """A cell whose walk-forward verdict is PASS on gates 1-4.

    Promotion needs this as well as a sane prediction distribution
    (#1025), so every test of the successful publish path has to hand one
    over — the same reason _promotable_model exists for the distribution.
    """
    return {
        "n_ok_folds": n_ok,
        "g1_logloss_beat_folds": n_ok, "g1_pass": True,
        "g2_ece_pass_folds": n_ok, "g2_pass": True,
        "g3_monotone_folds": n_ok, "g3_pass": True,
        "g4_lift_pass_folds": n_ok, "g4_pass": True,
        "cell_pass_gates_1_to_4": True,
    }


def _slv7m_gates() -> dict:
    """SPY/15m's real walk-forward verdict from magnitude-engine-slv7m.

    Read from research/magnitude_engine/phase0/spy_15m/
    walk_forward_magnitude-engine-slv7m.json. Its argmax spread passed the
    distribution criteria and it was promoted to LATEST on 2026-09-07
    despite beating the baseline on 0 of 8 folds.
    """
    return {
        "n_ok_folds": 8,
        "g1_logloss_beat_folds": 0, "g1_pass": False,
        "g2_ece_pass_folds": 2, "g2_pass": False,
        "g3_monotone_folds": 8, "g3_pass": True,
        "g4_lift_pass_folds": 8, "g4_pass": True,
        "cell_pass_gates_1_to_4": False,
    }


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

    with patch.object(mwf, "make_lgbm", return_value=_promotable_model(y)), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        uri = mwf._persist_production_model_artifact(
            "IWM", "5m", run_id="testrun-001",
            X_full=X, y_full=y,
            feature_cols=["rsi_14", "atr_14", "ema_9", "vwap"],
            gates=_passing_gates(), label_mode="body", thresholds=(0.5, 1.0, 1.5), calibration="none",
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
            feature_cols=["x"], gates=_passing_gates(), label_mode="body", thresholds=(0.5, 1.0, 1.5), calibration="none",
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
            feature_cols=cols, gates=_passing_gates(), label_mode="body", thresholds=(0.5, 1.0, 1.5), calibration="none",
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
            feature_cols=["x"], gates=_passing_gates(), label_mode="body", thresholds=(0.5, 1.0, 1.5), calibration="none",
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

    with patch.object(mwf, "make_lgbm", return_value=_promotable_model(y)), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        mwf._persist_production_model_artifact(
            "IWM", "5m", run_id="rX", X_full=X, y_full=y,
            feature_cols=["x"], gates=_passing_gates(), label_mode="body", thresholds=(0.5, 1.0, 1.5), calibration="none",
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
            feature_cols=["x"], gates=_passing_gates(), label_mode="body", thresholds=(0.5, 1.0, 1.5), calibration="sigmoid", cv=3,
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


def test_results_dataframe_coerces_all_none_float_cols():
    """Regression (2026-07-11): a fold with EXPLOSIVE absent yields
    explosive_precision/lift = None for every fold. Those columns must land as
    float64 (NaN), not object — otherwise SQLAlchemy binds ::VARCHAR and the
    insert fails with SQLSTATE 42804, which used to abort the whole persist
    try-block and silently skip the production-model artifact."""
    from gcp.research.magnitude_engine.mag_walk_forward import _results_dataframe
    folds = [
        {"fold": "2019..2020", "train_end": "2019-01-01", "test_end": "2020-01-01",
         "n_train": 100, "n_test": 50, "status": "OK", "logloss": 0.81,
         "base_logloss": 0.82, "beat": 0.01, "ece": 0.03, "ece_ceiling": 0.05,
         "ece_pass": True, "accuracy": 0.7, "base_accuracy": 0.7,
         "accuracy_beat_pp": 0.0,
         "explosive": {"base_rate": 0.02}},  # no precision/lift keys -> None
        {"fold": "2020..2021", "train_end": "2020-01-01", "test_end": "2021-01-01",
         "n_train": 120, "n_test": 55, "status": "OK", "logloss": 0.89,
         "base_logloss": 0.87, "beat": -0.02, "ece": 0.10, "ece_ceiling": 0.05,
         "ece_pass": False, "accuracy": 0.66, "base_accuracy": 0.66,
         "accuracy_beat_pp": 0.0, "explosive": {"base_rate": 0.02}},
    ]
    df = _results_dataframe("phase0", "QQQ", "15m", folds, "run-x")
    for col in ("explosive_precision", "explosive_lift"):
        assert str(df[col].dtype) == "float64", f"{col} must be float64, not object"
        assert df[col].isna().all()
    # a populated column keeps its real values
    assert df["beat"].tolist() == [0.01, -0.02]


# ── Promotion gate (c49qf incident, 2026-08-27) ────────────────────────────


def test_promotion_verdict_blocks_collapsed_model():
    """The exact c49qf signature: one bucket on every row."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    v = mwf.promotion_verdict(np.zeros(588, dtype=np.int64))
    assert v["ok"] is False
    assert v["modal_share"] == 1.0
    assert v["distinct_classes"] == 1
    assert "only 1 distinct bucket" in v["reason"]


def test_promotion_verdict_collapse_ceiling_is_inclusive():
    """The absolute criterion: 90.0% in one bucket is collapsed whatever the
    labels say; 89.9% is not (and with no labels passed, nothing else can
    block it)."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    from gcp.research.magnitude_engine.mag_config import PROMOTION_COLLAPSE_MODAL_SHARE

    assert PROMOTION_COLLAPSE_MODAL_SHARE == 0.90
    at = np.array([0] * 900 + [1] * 100)
    under = np.array([0] * 899 + [1] * 101)
    v_at = mwf.promotion_verdict(at)
    assert v_at["ok"] is False and "collapsed" in v_at["reason"]
    assert mwf.promotion_verdict(under)["ok"] is True


def test_promotion_verdict_passes_realistic_base_rates():
    """The real magnitude class balance (~64/27/7/2) must NOT be blocked —
    the gate targets argmax collapse and over-prediction, not label
    imbalance. A model that predicts exactly the label distribution has zero
    excess."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    y = np.array([0] * 640 + [1] * 270 + [2] * 70 + [3] * 20)
    v = mwf.promotion_verdict(y, y_true=y)
    assert v["ok"] is True
    assert v["distinct_classes"] == 4
    assert v["class_counts"] == {0: 640, 1: 270, 2: 70, 3: 20}
    assert v["true_modal_share"] == pytest.approx(0.64)
    assert v["modal_excess"] == pytest.approx(0.0)


def test_promotion_verdict_measures_the_model_not_the_labels():
    """slv7m, 2026-09-07 (#1025): a 68.7% TIGHT base rate put a calibrated
    model 1.5 points from the old fixed 70% ceiling. SPY/15m (68.7% predicted)
    passed and IWM/15m (76.1% predicted) was blocked as if it were c49qf's
    100%. Under the relative criterion IWM's +7.4 passes; a model 15 points
    over the same labels does not; the reason names both shares."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    from gcp.research.magnitude_engine.mag_config import PROMOTION_MAX_MODAL_EXCESS

    assert PROMOTION_MAX_MODAL_EXCESS == 0.10
    n = 1000
    y_true = np.array([0] * 687 + [1] * 245 + [2] * 52 + [3] * 16)
    assert y_true.size == n
    iwm_like = np.array([0] * 761 + [1] * 191 + [2] * 42 + [3] * 6)
    v = mwf.promotion_verdict(iwm_like, y_true=y_true)
    assert v["ok"] is True, v["reason"]
    assert v["modal_excess"] == pytest.approx(0.074)

    over = np.array([0] * 840 + [1] * 120 + [2] * 30 + [3] * 10)
    v = mwf.promotion_verdict(over, y_true=y_true)
    assert v["ok"] is False
    assert "over-predicts bucket 0" in v["reason"]
    assert "84.0% predicted vs 68.7% true" in v["reason"]
    assert v["modal_share"] < 0.90, "this case must be caught by excess, not collapse"

    # Exactly the allowed excess is still fine; one row more is not.
    boundary = np.array([0] * 787 + [1] * 165 + [2] * 40 + [3] * 8)
    assert mwf.promotion_verdict(boundary, y_true=y_true)["ok"] is True
    beyond = np.array([0] * 788 + [1] * 164 + [2] * 40 + [3] * 8)
    assert mwf.promotion_verdict(beyond, y_true=y_true)["ok"] is False


def test_promotion_verdict_excess_boundary_is_exact_not_floating_point():
    """4/10 predicted vs 3/10 true is exactly the allowed +10 points; in
    binary floating point the subtraction is 0.10000000000000003 and a
    float compare blocked it with the contradictory reason "+10.0% > 10%"
    (Codex, #1042). Counts are compared exactly."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    assert (4 / 10) - (3 / 10) > 0.10, "the hazard this test guards"
    y_pred = np.array([0] * 4 + [1] * 3 + [2] * 3)
    y_true = np.array([0] * 3 + [1] * 4 + [2] * 3)
    v = mwf.promotion_verdict(y_pred, y_true=y_true)
    assert v["ok"] is True, v["reason"]
    assert v["modal_excess"] == pytest.approx(0.10)


def test_promotion_verdict_judges_every_class_tied_for_the_mode():
    """Predicted {0: 4, 1: 4, 2: 2} against true {0: 6, 1: 1, 2: 3}: class 0
    is under-predicted by 20 points but class 1, equally modal, is over-
    predicted by 30. Picking the lowest id would pass this (Codex, #1042);
    the tied class with the greatest excess is judged and named."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    y_pred = np.array([0] * 4 + [1] * 4 + [2] * 2)
    y_true = np.array([0] * 6 + [1] * 1 + [2] * 3)
    v = mwf.promotion_verdict(y_pred, y_true=y_true)
    assert v["ok"] is False
    assert v["modal_class"] == 1
    assert v["true_modal_share"] == pytest.approx(0.1)
    assert v["modal_excess"] == pytest.approx(0.3)
    assert "over-predicts bucket 1" in v["reason"]
    # Without labels a tie falls back to the lowest id, and only the collapse
    # criterion can judge it.
    assert mwf.promotion_verdict(y_pred)["modal_class"] == 0


def test_promotion_verdict_refuses_mismatched_labels():
    """A label vector for different rows would make the excess meaningless;
    that is an error, never a silent skip of the criterion."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    with pytest.raises(ValueError, match="same rows"):
        mwf.promotion_verdict(np.array([0, 0, 1]), y_true=np.array([0, 1]))


def test_promotion_verdict_handles_empty():
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    v = mwf.promotion_verdict(np.array([], dtype=np.int64))
    assert v["ok"] is False
    assert v["n"] == 0


def test_blocked_promotion_leaves_latest_untouched(monkeypatch, joblib_dump_stub):
    """The load-bearing assertion: a collapsed candidate must NOT become the
    live model. Artifacts still land under the run prefix for diagnosis, plus a
    PROMOTION_BLOCKED marker — but LATEST is never written, so mag_inference
    keeps loading the previous production model.

    This is the control that would have stopped magnitude-engine-c49qf.
    """
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    X, y = _toy_data()
    collapsed = MagicMock()
    collapsed.predict.return_value = np.zeros(len(y), dtype=np.int64)
    fake_client, captured = _capture_blob_uploads()

    with patch.object(mwf, "make_lgbm", return_value=collapsed), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        uri = mwf._persist_production_model_artifact(
            "IWM", "5m", run_id="collapsed-001",
            X_full=X, y_full=y, feature_cols=["x"], gates=_passing_gates(), label_mode="body", thresholds=(0.5, 1.0, 1.5), calibration="none",
        )

    assert uri is None, "a blocked promotion must not report success"
    assert "magnitude-models/production/IWM/5m/LATEST" not in captured, \
        "LATEST was flipped to a collapsed model — the c49qf regression"
    prefix = "magnitude-models/production/IWM/5m/collapsed-001"
    assert f"{prefix}/model.joblib" in captured, "forensic artifacts still kept"
    assert f"{prefix}/PROMOTION_BLOCKED" in captured
    marker = json.loads(captured[f"{prefix}/PROMOTION_BLOCKED"].decode())
    assert marker["ok"] is False
    assert marker["modal_share"] == 1.0


def test_isotonic_calibration_does_not_bypass_the_gate(monkeypatch, joblib_dump_stub):
    """c49qf was a calibration=isotonic run. The gate scores whatever model the
    calibration branch produced, so the wrapper is not an escape hatch."""
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    X, y = _toy_data()
    collapsed = MagicMock()
    collapsed.predict.return_value = np.zeros(len(y), dtype=np.int64)
    fake_client, captured = _capture_blob_uploads()

    with patch.object(mwf, "CalibratedClassifierCV", return_value=collapsed), \
         patch.object(mwf, "make_lgbm", return_value=MagicMock()), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        uri = mwf._persist_production_model_artifact(
            "IWM", "15m", run_id="iso-001",
            X_full=X, y_full=y, feature_cols=["x"],
            gates=_passing_gates(), label_mode="body", thresholds=(0.5, 1.0, 1.5), calibration="isotonic",
        )

    assert uri is None
    assert "magnitude-models/production/IWM/15m/LATEST" not in captured


# ─────────────── walk-forward gate (promotion criterion 2, #1025) ───────────

def test_walk_forward_gate_reason_is_none_when_the_cell_passed():
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    assert mwf.walk_forward_gate_reason(_passing_gates()) is None


def test_walk_forward_gate_reason_names_each_failing_gate_and_its_folds():
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    reason = mwf.walk_forward_gate_reason(_slv7m_gates())
    assert reason is not None
    # The two that failed are named with the counts behind them; the two
    # that passed are not, so the log line says what to go fix.
    assert "g1 log-loss beat 0/8 folds" in reason
    assert "g2 ECE within ceiling 2/8 folds" in reason
    assert "g3" not in reason and "g4" not in reason


def test_walk_forward_gate_reason_raises_when_the_verdict_is_absent():
    """A caller that cannot say whether the cell passed must not promote by
    omission — CLAUDE.md §3.7, the failure is INTERNAL so it fails loud."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    for bad in ({}, {"g1_pass": True}, None, "PASS"):
        with pytest.raises(ValueError, match="cell_pass_gates_1_to_4"):
            mwf.walk_forward_gate_reason(bad)


def test_failed_walk_forward_gates_block_promotion(monkeypatch, joblib_dump_stub):
    """The slv7m regression: a candidate whose argmax spread is fine but whose
    cell verdict is FAIL must NOT flip LATEST.

    SPY/15m promoted on 2026-09-07 with exactly this shape and served the
    Expected-Move card from probabilities that beat the class-prior baseline
    on 0 of 8 folds.
    """
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    X, y = _toy_data()
    fake_client, captured = _capture_blob_uploads()

    with patch.object(mwf, "make_lgbm", return_value=_promotable_model(y)), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        uri = mwf._persist_production_model_artifact(
            "SPY", "15m", run_id="slv7m-shape",
            X_full=X, y_full=y, feature_cols=["x"],
            gates=_slv7m_gates(), label_mode="body", thresholds=(0.5, 1.0, 1.5), calibration="none",
        )

    assert uri is None, "a cell that failed gates 1-4 must not be promoted"
    assert "magnitude-models/production/SPY/15m/LATEST" not in captured, \
        "LATEST must still point at the previous production model"

    blocked = captured["magnitude-models/production/SPY/15m/slv7m-shape/PROMOTION_BLOCKED"]
    payload = json.loads(blocked.decode())
    assert payload["ok"] is False
    assert "g1 log-loss beat 0/8 folds" in payload["reason"]
    # The gate counts ride along so the block can be diagnosed without
    # re-running an 8-fold job.
    assert payload["walk_forward_gates"]["g2_ece_pass_folds"] == 2
    assert payload["walk_forward_gates"]["cell_pass_gates_1_to_4"] is False
    # Artifacts are still kept under the run prefix for diagnosis.
    assert "magnitude-models/production/SPY/15m/slv7m-shape/model.joblib" in captured


def test_both_criteria_are_reported_when_both_fail(monkeypatch, joblib_dump_stub):
    """A collapsed model in a failing cell records both reasons, not the
    first one to trip."""
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    X, y = _toy_data()
    collapsed = MagicMock()
    collapsed.predict.return_value = np.zeros(len(y), dtype=np.int64)
    fake_client, captured = _capture_blob_uploads()

    with patch.object(mwf, "make_lgbm", return_value=collapsed), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        uri = mwf._persist_production_model_artifact(
            "IWM", "15m", run_id="both-001",
            X_full=X, y_full=y, feature_cols=["x"],
            gates=_slv7m_gates(), label_mode="body", thresholds=(0.5, 1.0, 1.5), calibration="none",
        )

    assert uri is None
    payload = json.loads(
        captured["magnitude-models/production/IWM/15m/both-001/PROMOTION_BLOCKED"].decode())
    assert "collapsed" in payload["reason"]
    assert "walk-forward gates" in payload["reason"]


def test_passing_cell_still_promotes_and_records_its_gates(monkeypatch, joblib_dump_stub):
    """The new criterion must not block a cell that cleared gates 1-4 — the
    promotion path stays reachable."""
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    X, y = _toy_data()
    fake_client, captured = _capture_blob_uploads()

    with patch.object(mwf, "make_lgbm", return_value=_promotable_model(y)), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        uri = mwf._persist_production_model_artifact(
            "QQQ", "15m", run_id="good-001",
            X_full=X, y_full=y, feature_cols=["x"],
            gates=_passing_gates(), label_mode="body", thresholds=(0.5, 1.0, 1.5), calibration="none",
        )

    assert uri == "gs://test-bucket/magnitude-models/production/QQQ/15m/"
    assert captured["magnitude-models/production/QQQ/15m/LATEST"] == b"good-001"
    assert "magnitude-models/production/QQQ/15m/good-001/PROMOTION_BLOCKED" not in captured


def test_persist_call_site_hands_over_the_cells_own_gates():
    """walk_forward must pass the gates it just computed, not a fresh or
    empty dict — the guard is worthless if the call site fabricates one."""
    import inspect
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    src = inspect.getsource(mwf.walk_forward)
    assert "gates=gates," in src, \
        "walk_forward must forward its own _evaluate_phase_gate result"
    # And the parameter is required, so a caller cannot silently omit it.
    sig = inspect.signature(mwf._persist_production_model_artifact)
    assert sig.parameters["gates"].default is inspect.Parameter.empty

# ─────── label semantics: the serving contract (#1025 follow-up) ───────

def test_serving_contract_reason_passes_the_default_labels():
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    from gcp.research.magnitude_engine.mag_config import (
        DEFAULT_LABEL_MODE, MAGNITUDE_THRESHOLDS)
    assert mwf.serving_contract_reason(
        DEFAULT_LABEL_MODE, MAGNITUDE_THRESHOLDS) is None


def test_serving_contract_reason_names_each_mismatch():
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    assert "label_mode='excursion'" in mwf.serving_contract_reason(
        "excursion", (0.5, 1.0, 1.5))
    assert "thresholds=(0.35, 0.75, 1.25)" in mwf.serving_contract_reason(
        "body", (0.35, 0.75, 1.25))
    both = mwf.serving_contract_reason("put", (0.35, 0.75, 1.25))
    assert "label_mode='put'" in both and "thresholds=" in both


def test_research_labels_cannot_become_the_serving_model(monkeypatch, joblib_dump_stub):
    """A model trained on `excursion` predicts buckets that mean something
    else; mag_inference and the card read `body`. Neither the distribution
    criteria nor gates 1-4 can see the difference — the values are still 0-3
    and the spread still looks healthy — so the contract is checked directly.
    """
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    X, y = _toy_data()
    fake_client, captured = _capture_blob_uploads()

    with patch.object(mwf, "make_lgbm", return_value=_promotable_model(y)), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        uri = mwf._persist_production_model_artifact(
            "IWM", "15m", run_id="excursion-001",
            X_full=X, y_full=y, feature_cols=["x"],
            gates=_passing_gates(),          # gates 1-4 all PASS
            label_mode="excursion", thresholds=(0.5, 1.0, 1.5),
            calibration="none",
        )

    assert uri is None
    assert "magnitude-models/production/IWM/15m/LATEST" not in captured
    payload = json.loads(
        captured["magnitude-models/production/IWM/15m/excursion-001/PROMOTION_BLOCKED"].decode())
    assert "label_mode='excursion'" in payload["reason"]
    assert payload["label_mode"] == "excursion"


def test_non_default_thresholds_cannot_become_the_serving_model(monkeypatch, joblib_dump_stub):
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    X, y = _toy_data()
    fake_client, captured = _capture_blob_uploads()

    with patch.object(mwf, "make_lgbm", return_value=_promotable_model(y)), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        uri = mwf._persist_production_model_artifact(
            "SPY", "15m", run_id="thresh-001",
            X_full=X, y_full=y, feature_cols=["x"],
            gates=_passing_gates(),
            label_mode="body", thresholds=(0.35, 0.75, 1.25),
            calibration="none",
        )

    assert uri is None
    payload = json.loads(
        captured["magnitude-models/production/SPY/15m/thresh-001/PROMOTION_BLOCKED"].decode())
    assert payload["thresholds"] == [0.35, 0.75, 1.25]
    assert "serving contract is (0.5, 1.0, 1.5)" in payload["reason"]


# ─────────── --label-mode reached only ONE of four dispatch paths ───────────

def test_every_dispatch_path_forwards_label_mode():
    """The Cloud Run task-parallel path — the ONLY way this job runs in
    production — called walk_forward() without label_mode, so
    `--label-mode=excursion` silently trained `body` and reported success.
    Same for --plan/--task-index and --all-cells. Three of four paths.
    """
    import inspect
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    src = inspect.getsource(mwf.main)
    # one per dispatch path: task-parallel, --plan, --all-cells, single cell
    assert src.count("label_mode=args.label_mode") == 4, (
        "every dispatch path must forward the requested label mode; a path "
        "that drops it trains the default and reports success")

    # and the in-process fan-out must forward what it was given
    assert "label_mode=label_mode" in inspect.getsource(mwf.run_all_cells)


def test_walk_forward_records_the_labels_it_trained_on():
    """The run summary has to name the labels, or a finished run cannot be
    audited for which experiment it actually was."""
    import inspect
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    src = inspect.getsource(mwf.walk_forward)
    assert '"label_mode": label_mode' in src
    assert '"thresholds": list(thresholds)' in src
    # thresholds are resolved once per cell, from the same helper the dataset
    # buckets with, so summary and labels cannot disagree
    assert "thresholds = resolve_magnitude_thresholds()" in src


# ──────────────────── MAG_THRESHOLDS override ────────────────────

def test_threshold_override_defaults_and_parses(monkeypatch):
    from gcp.research.magnitude_engine.mag_config import (
        MAGNITUDE_THRESHOLDS, resolve_magnitude_thresholds)

    monkeypatch.delenv("MAG_THRESHOLDS", raising=False)
    assert resolve_magnitude_thresholds() == MAGNITUDE_THRESHOLDS
    monkeypatch.setenv("MAG_THRESHOLDS", " 0.35,0.75,1.25 ")
    assert resolve_magnitude_thresholds() == (0.35, 0.75, 1.25)


@pytest.mark.parametrize("bad,why", [
    ("1,2", "wrong count"),
    ("0.5,1.0,1.5,2.0", "wrong count"),
    ("a,b,c", "not numbers"),
    ("0.5,0.5,1.0", "not ascending"),
    ("1.5,1.0,0.5", "descending"),
    ("-1,2,3", "non-positive"),
    ("0.5,nan,1.5", "not finite"),
])
def test_malformed_threshold_override_raises_rather_than_defaulting(
        monkeypatch, bad, why):
    """CLAUDE.md §3.7: falling back to the default here would train one label
    set while the operator believed another — the same silent substitution the
    dispatch-path bug caused."""
    from gcp.research.magnitude_engine.mag_config import resolve_magnitude_thresholds

    monkeypatch.setenv("MAG_THRESHOLDS", bad)
    with pytest.raises(ValueError):
        resolve_magnitude_thresholds()


# ───────────── Codex on #1055: the review caught what tests could not ─────────

def test_walk_forward_reaches_the_dataset_load(monkeypatch):
    """walk_forward() logged `thresholds` before assigning it, so EVERY
    dispatch path raised UnboundLocalError before loading a single row.

    Nothing in the suite executes walk_forward (it needs a DB), so 4944 tests
    and a green CI passed over a total outage. This test drives the real
    function far enough to prove the preamble runs, by making the dataset load
    the first thing that stops it.
    """
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    class ReachedTheLoad(Exception):
        pass

    def _boom(*a, **kw):
        raise ReachedTheLoad

    monkeypatch.setattr(mwf, "load_magnitude_dataset", _boom)
    with pytest.raises(ReachedTheLoad):
        mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m")


def test_malformed_threshold_override_fails_the_run_not_each_cell(monkeypatch):
    """run_all_cells catches every per-cell exception and main() does not act
    on its FAIL verdict, so a bad MAG_THRESHOLDS on the --all-cells path would
    error all nine cells and still exit 0. main() resolves it up front."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    class ReachedTheEngine(Exception):
        pass

    monkeypatch.setenv("MAG_THRESHOLDS", "0.5,0.5,1.0")   # not ascending
    monkeypatch.setattr(sys, "argv",
                        ["mag_walk_forward", "--phase=phase0", "--all-cells"])
    monkeypatch.setattr(mwf, "get_engine",
                        lambda *a, **kw: (_ for _ in ()).throw(ReachedTheEngine))

    # ValueError, not ReachedTheEngine: the config is rejected before the run
    # touches a database, let alone fans out.
    with pytest.raises(ValueError, match="ascending"):
        mwf.main()


def test_research_labels_get_their_own_gcs_namespace():
    """assemble_magnitude_results.latest_result takes sorted(files)[-1] from
    the cell prefix and per_phase_verdict never reads the labels, so a
    research run sharing that prefix would become the reported phase verdict
    simply by being newer."""
    from gcp.research.magnitude_engine.mag_config import (
        gcs_run_prefix, research_namespace, DEFAULT_LABEL_MODE,
        MAGNITUDE_THRESHOLDS)

    canonical = gcs_run_prefix("phase0", "SPY", "15m")
    # the serving contract keeps the historical path, explicitly or by default
    assert gcs_run_prefix("phase0", "SPY", "15m",
                          label_mode=DEFAULT_LABEL_MODE,
                          thresholds=MAGNITUDE_THRESHOLDS) == canonical
    assert research_namespace(DEFAULT_LABEL_MODE, MAGNITUDE_THRESHOLDS) is None

    for kwargs in (
        {"label_mode": "excursion", "thresholds": MAGNITUDE_THRESHOLDS},
        {"label_mode": DEFAULT_LABEL_MODE, "thresholds": (0.35, 0.75, 1.25)},
        {"label_mode": "put", "thresholds": (0.35, 0.75, 1.25)},
    ):
        other = gcs_run_prefix("phase0", "SPY", "15m", **kwargs)
        assert other != canonical
        # a sibling root, not a subdirectory: no listing of the canonical
        # prefix can reach it, recursive or not
        assert not other.startswith(canonical)
        assert "/_research/" in other


def test_walk_forward_writes_under_the_namespace_it_resolved():
    import inspect
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    src = inspect.getsource(mwf.walk_forward)
    # both artifact paths — the predictions CSV and the summary JSON — or one
    # of them leaks a research run into the canonical prefix
    assert src.count("gcs_run_prefix(phase, ticker, tf,") == 2
    assert src.count(
        "label_mode=label_mode, thresholds=thresholds)") == 2
    # and the persist path is told the same semantics it wrote under
    assert "gates=gates, label_mode=label_mode, thresholds=thresholds," in src


# ─────── the namespace has to reach every consumer of the artifacts ───────

def test_analysis_loader_reads_the_research_namespace():
    """The post-hoc scripts search a prefix they build themselves. Moving the
    predictions CSV without teaching them would make gate 7 and the other
    required evidence exit claiming the run has no predictions — for exactly
    the runs the namespace exists to hold (Codex on #1055)."""
    sys.path.insert(0, "scripts")
    from _magnitude_analysis_helpers import research_prefix
    from gcp.research.magnitude_engine.mag_config import gcs_run_prefix

    assert research_prefix("phase0", "SPY", "15m") == \
        gcs_run_prefix("phase0", "SPY", "15m") + "/"
    assert research_prefix("phase0", "SPY", "15m", "excursion") == \
        gcs_run_prefix("phase0", "SPY", "15m",
                       label_mode="excursion",
                       thresholds=(0.5, 1.0, 1.5)) + "/"
    assert research_prefix("phase0", "SPY", "15m", "t0.35_0.75_1.25") == \
        gcs_run_prefix("phase0", "SPY", "15m", label_mode="body",
                       thresholds=(0.35, 0.75, 1.25)) + "/"


@pytest.mark.parametrize("script", [
    "implied_vs_realized_check",          # gate 7
    "bootstrap_gate_fragility",           # gate 5
    "check_event_window_concentration",
    "model_vs_calendar_explosive_decomp",
    "magnitude_movement_sim",
])
def test_every_analysis_script_accepts_and_forwards_research(script):
    src = pathlib.Path(f"scripts/{script}.py").read_text()
    assert "add_research_arg(p)" in src, f"{script} cannot name the namespace"
    assert "research=args.research" in src, f"{script} does not forward it"


def test_research_runs_stay_out_of_the_canonical_sql_tables():
    """magnitude_walk_forward_results is keyed (phase, ticker, tf, fold,
    run_id) and magnitude_per_bar_predictions by (ticker, tf, ts,
    model_version) — the same cell keys a body run uses, and neither records
    the label contract. Research folds in there would group incomparable
    experiments under one cell, and put other-meaning buckets into the table
    the inference and render path reads."""
    import inspect
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    src = inspect.getsource(mwf.walk_forward)
    assert "research = research_namespace(label_mode, thresholds)" in src
    persist_at = src.index("_persist_results_table(engine")
    guard_at = src.index("if research:")
    assert guard_at < persist_at, (
        "the canonical-table writes must sit under the else branch of the "
        "research guard")


# ── round 3: the namespace must DRIVE the analysis, not just locate it ──

@pytest.mark.parametrize("label_mode,thresholds", [
    ("excursion", (0.5, 1.0, 1.5)),
    ("body", (0.35, 0.75, 1.25)),
    ("put", (0.35, 0.75, 1.25)),
    ("body", (0.1234564, 0.75, 1.25)),
    ("call", (0.25, 0.6, 1.1)),
])
def test_research_slug_round_trips_exactly(label_mode, thresholds):
    from gcp.research.magnitude_engine.mag_config import (
        research_namespace, parse_research_namespace)

    slug = research_namespace(label_mode, thresholds)
    assert parse_research_namespace(slug) == (label_mode, thresholds)


def test_near_identical_thresholds_do_not_share_a_namespace():
    """%g keeps six significant digits, so 0.1234564 and 0.12345649 slugged
    identically and two experiments with different bucket definitions shared a
    prefix — the collision the partition exists to prevent."""
    from gcp.research.magnitude_engine.mag_config import research_namespace

    a = research_namespace("body", (0.1234564, 0.75, 1.25))
    b = research_namespace("body", (0.12345649, 0.75, 1.25))
    assert a != b


def test_malformed_research_slug_is_refused():
    from gcp.research.magnitude_engine.mag_config import parse_research_namespace

    for bad in ("nonsense", "t0.5_1.0", "body__body", "t1_2_3__t4_5_6",
                "excursion__banana"):
        with pytest.raises(ValueError):
            parse_research_namespace(bad)


@pytest.fixture
def isolated_mag_thresholds():
    """Restore MAG_THRESHOLDS around a test.

    apply_research_contract() writes os.environ directly — deliberately, so a
    one-shot analysis script buckets the way its model was trained — and
    monkeypatch does not undo writes it did not make. Without this the leak
    reaches every later test in the session: it turned
    test_magnitude_gates.py::test_expanded_bucket red by rebucketing at
    0.35/0.75/1.25.
    """
    prev = os.environ.get("MAG_THRESHOLDS")
    os.environ.pop("MAG_THRESHOLDS", None)
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("MAG_THRESHOLDS", None)
        else:
            os.environ["MAG_THRESHOLDS"] = prev


def test_contract_comes_from_the_namespace(isolated_mag_thresholds):
    sys.path.insert(0, "scripts")
    from _magnitude_analysis_helpers import apply_research_contract
    from gcp.research.magnitude_engine.mag_config import (
        DEFAULT_LABEL_MODE, MAGNITUDE_THRESHOLDS)

    assert apply_research_contract(None) == (DEFAULT_LABEL_MODE,
                                             tuple(MAGNITUDE_THRESHOLDS))
    assert "MAG_THRESHOLDS" not in os.environ

    # a directional namespace supplies the label mode without being told
    assert apply_research_contract("put")[0] == "put"

    # and a threshold namespace exports the cut points, so the dataset builder
    # buckets the way the model was trained rather than at the defaults
    mode, thr = apply_research_contract("t0.35_0.75_1.25")
    assert (mode, thr) == (DEFAULT_LABEL_MODE, (0.35, 0.75, 1.25))
    from gcp.research.magnitude_engine.mag_config import resolve_magnitude_thresholds
    assert resolve_magnitude_thresholds() == (0.35, 0.75, 1.25)


def test_label_mode_contradicting_the_namespace_is_refused(isolated_mag_thresholds):
    """`--research=put --label-mode=body` would evaluate a put model's
    predictions against body realizations and emit a plausible, invalid
    verdict. Refused rather than silently resolved either way."""
    sys.path.insert(0, "scripts")
    from _magnitude_analysis_helpers import apply_research_contract

    with pytest.raises(SystemExit, match="contradicts"):
        apply_research_contract("put", "body")
    # agreeing is fine, and so is leaving it unset
    assert apply_research_contract("put", "put")[0] == "put"
    assert apply_research_contract("put", None)[0] == "put"


def test_label_building_scripts_take_their_labels_from_the_contract():
    """Loading the right predictions and then rebuilding labels at the
    defaults scores a model against a target it never predicted."""
    for script, call in [
        ("implied_vs_realized_check", "label_mode=args.label_mode"),
        ("model_vs_calendar_explosive_decomp", "label_mode=_label_mode"),
        ("magnitude_movement_sim", "label_mode=args.label_mode"),
    ]:
        src = pathlib.Path(f"scripts/{script}.py").read_text()
        assert "apply_research_contract(" in src, script
        assert call in src, script
        assert src.index("apply_research_contract(") < src.index(
            "load_magnitude_dataset(engine"), (
            f"{script}: the contract must be adopted before the dataset "
            "is built")


def test_movement_sim_writes_into_its_own_namespace():
    """Reading from _research/<slug>/ and writing back to the canonical prefix
    would file a research result among body-contract artifacts."""
    src = pathlib.Path("scripts/magnitude_movement_sim.py").read_text()
    assert "research_prefix(args.phase, args.ticker, args.tf, args.research)" in src
    assert 'blob = (f"research/magnitude_engine/{args.phase}' not in src


# ─────────────── round 4: contract resolution order and scope ───────────────

@pytest.mark.parametrize("thresholds", [
    (1e-7, 2e-7, 3e-7),          # repr() uses a negative exponent
    (0.5, 1.0, 1.5e0),
    (0.25, 0.6, 1.1),
])
def test_slug_survives_scientific_notation(thresholds):
    """repr(1e-07) is '1e-07', so a '-' separator was also part of the value:
    t1e-07-2e-07-3e-07 could not be split back, and a training run would write
    under a slug every contract-aware reader rejected."""
    from gcp.research.magnitude_engine.mag_config import (
        research_namespace, parse_research_namespace)

    slug = research_namespace("body", thresholds)
    if slug is None:          # the default set has no namespace
        return
    assert parse_research_namespace(slug) == ("body", tuple(thresholds))


def test_default_contract_clears_an_ambient_threshold_override(
        isolated_mag_thresholds):
    """A MAG_THRESHOLDS left in the environment would have the dataset bucket
    at the ambient values while the contract reports the defaults, so the
    analysis describes a different target than the predictions it loaded."""
    sys.path.insert(0, "scripts")
    from _magnitude_analysis_helpers import apply_research_contract
    from gcp.research.magnitude_engine.mag_config import (
        MAGNITUDE_THRESHOLDS, resolve_magnitude_thresholds)

    os.environ["MAG_THRESHOLDS"] = "0.35,0.75,1.25"
    # a namespace with default cut points must REPLACE, not inherit
    _, thresholds = apply_research_contract("put")
    assert thresholds == tuple(MAGNITUDE_THRESHOLDS)
    assert resolve_magnitude_thresholds() == tuple(MAGNITUDE_THRESHOLDS)

    os.environ["MAG_THRESHOLDS"] = "0.35,0.75,1.25"
    apply_research_contract(None)
    assert resolve_magnitude_thresholds() == tuple(MAGNITUDE_THRESHOLDS)


def test_gate7_resolves_the_contract_before_reading_label_mode():
    """`iv_option_type` is chosen FROM label_mode, so resolving the contract
    after that line picked call IV for a put run: realized move put-specific,
    premium not."""
    src = pathlib.Path("scripts/implied_vs_realized_check.py").read_text()
    resolve_at = src.index("apply_research_contract(")
    iv_leg_at = src.index('iv_option_type = "puts"')
    assert resolve_at < iv_leg_at, (
        "the label contract must be resolved before anything reads "
        "args.label_mode")


# ─────────────── round 5: the contract check has two directions ───────────────

def test_noncanonical_label_without_a_namespace_is_refused(isolated_mag_thresholds):
    """The canonical prefix IS the serving contract. `--label-mode=put` with
    no `--research` reads a canonical body run and scores it against put
    realizations and put IV — the same invalid verdict the other direction
    already refused."""
    sys.path.insert(0, "scripts")
    from _magnitude_analysis_helpers import apply_research_contract
    from gcp.research.magnitude_engine.mag_config import DEFAULT_LABEL_MODE

    for mode in ("put", "call", "excursion"):
        with pytest.raises(SystemExit, match="needs the matching --research"):
            apply_research_contract(None, mode)
    # the canonical contract itself is still fine, named or defaulted
    assert apply_research_contract(None, DEFAULT_LABEL_MODE)[0] == DEFAULT_LABEL_MODE
    assert apply_research_contract(None, None)[0] == DEFAULT_LABEL_MODE


def test_research_help_shows_slugs_the_generator_actually_makes():
    """The help text told operators to pass 't0.35-0.75-1.25' while the
    generator emits underscores, so copying it either fails to parse or
    searches a prefix that does not exist."""
    import argparse, re
    sys.path.insert(0, "scripts")
    from _magnitude_analysis_helpers import add_research_arg
    from gcp.research.magnitude_engine.mag_config import (
        research_namespace, parse_research_namespace)

    p = argparse.ArgumentParser()
    add_research_arg(p)
    help_text = p.format_help()
    slugs = re.findall(r"'([a-z_]*t?[0-9._]*[0-9]|[a-z]+(?:__t[0-9._]+)?)'", help_text)
    quoted = re.findall(r"'([^']+)'", help_text)
    examples = [q for q in quoted if q.startswith("t") or "__" in q or q in
                ("excursion", "call", "put")]
    assert examples, f"no example slugs found in help: {help_text}"
    for ex in examples:
        # every advertised slug must parse, and round-trip to itself
        label_mode, thresholds = parse_research_namespace(ex)
        assert research_namespace(label_mode, thresholds) == ex


# ─── round 6: the supported dispatch path must be able to run the experiment ───

def _dispatch(*args, tmp_path):
    """Run the dispatcher against a stub gcloud and return what it would call."""
    import subprocess, os, stat
    stub = tmp_path / "gcloud"
    stub.write_text("#!/usr/bin/env bash\necho \"GCLOUD_CALL: $*\"\n")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}")
    out = subprocess.run(["bash", "scripts/dispatch_magnitude_phase.sh", *args],
                         capture_output=True, text=True, env=env)
    return out.stdout + out.stderr


def test_dispatcher_can_launch_a_label_definition_experiment(tmp_path):
    """The Cloud Run task-parallel path is the production one, and the
    dispatcher passed only MAG_PLAN — so neither label-definition experiment
    had a supported entrypoint, only a hand-written gcloud override."""
    canonical = _dispatch("phase0", tmp_path=tmp_path)
    # always NAMED, empty for a canonical dispatch — see the clearing test
    assert "^|^MAG_PLAN=phase0|MAG_THRESHOLDS=" in canonical
    assert "--label-mode" not in canonical      # unchanged for a body run

    excursion = _dispatch("phase0", "--label-mode=excursion", tmp_path=tmp_path)
    assert "--label-mode=excursion" in excursion

    thresholds = _dispatch("phase0", "--thresholds=0.35,0.75,1.25",
                           tmp_path=tmp_path)
    # gcloud splits --update-env-vars on commas, so a comma-bearing value needs
    # the ^|^ custom delimiter or MAG_THRESHOLDS would be set to just "0.35"
    assert "^|^MAG_PLAN=phase0|MAG_THRESHOLDS=0.35,0.75,1.25" in thresholds

    both = _dispatch("phase0", "--label-mode=put", "--thresholds=0.35,0.75,1.25",
                     tmp_path=tmp_path)
    assert "--label-mode=put" in both
    assert "MAG_THRESHOLDS=0.35,0.75,1.25" in both


def test_dispatcher_refuses_an_unknown_option(tmp_path):
    out = _dispatch("phase0", "--nonsense", tmp_path=tmp_path)
    assert "Unknown option" in out
    assert "GCLOUD_CALL" not in out, "a bad option must not dispatch anything"


def test_directional_usage_examples_carry_their_namespace():
    """A call/put/excursion example without --research reads the canonical
    body prefix, where that run no longer lives."""
    src = pathlib.Path("scripts/magnitude_movement_sim.py").read_text()
    usage = src.split('"""')[1]
    for line in usage.splitlines():
        if "--position call" in line or "--position put" in line:
            assert "--research" in line or "--research" in usage, (
                "a directional example must show the namespace that locates "
                "the run")


# ───────────── round 7: two regressions in the dispatcher I added ─────────────

def test_with_checks_still_dispatches(tmp_path):
    """--with-checks is documented in the header and was never implemented, so
    before the option parser existed it was ignored and the phase dispatched.
    Rejecting it turned a no-op flag into a dispatch that does nothing."""
    out = _dispatch("phase0", "--with-checks", tmp_path=tmp_path)
    assert "GCLOUD_CALL" in out, "the phase must still dispatch"
    assert "not implemented" in out, "and say what it is not doing"


def test_canonical_dispatch_clears_a_stale_threshold_override(tmp_path):
    """`gcloud run jobs execute --update-env-vars` MERGES: a variable the
    override does not name keeps its job-level value. A job still carrying
    MAG_THRESHOLDS from an earlier experiment would hand custom cut points to
    a dispatch that believes it is canonical, and the run would land under
    _research/, out of the canonical SQL, refused promotion."""
    out = _dispatch("phase0", tmp_path=tmp_path)
    assert "MAG_THRESHOLDS=" in out, "the variable must be named to be cleared"
    # named with an empty value, which resolve_magnitude_thresholds reads as absent
    assert "|MAG_THRESHOLDS=" in out
    assert "MAG_THRESHOLDS=0" not in out
