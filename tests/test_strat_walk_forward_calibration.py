"""Tests for the NEW principled post-hoc isotonic calibration in the TYPE
walk-forward (gcp.research.strat_engine.strat_walk_forward).

Context: the TYPE (next_bar_type) model passes 8/8 on 5m/15m but the 30m cells
miss the ECE<=0.05 gate on thin sample. `--calibration isotonic_oos` is the
principled lever — per-class isotonic fit on a DATE-carved slice of TRAIN only
(NOT the CV-refit CalibratedClassifierCV that E-20 found HURT ECE). These tests
pin three honesty contracts:

  1. The calibration validation slice is carved from TRAIN by date, disjoint,
     and never the test fold.
  2. The isotonic_oos fold path runs, reports an ECE, and the ECE gate is
     evaluated against the UNCHANGED 0.05 ceiling (not loosened for 30m).
  3. The base model in the calibrated path is fit ONLY on the fit-slice, never
     on the calibration slice or the test fold (no leak).

The walk-forward module eagerly imports google.cloud.storage (for the GCS
upload that never runs in a fold); we stub that one symbol so the fold math
runs hermetically. Skips if lightgbm/sklearn are unavailable.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _stub_gcs():
    if "google.cloud.storage" not in sys.modules:
        g = types.ModuleType("google")
        gc = types.ModuleType("google.cloud")
        st = types.ModuleType("google.cloud.storage")
        st.Client = object
        gc.storage = st
        g.cloud = gc
        sys.modules.setdefault("google", g)
        sys.modules.setdefault("google.cloud", gc)
        sys.modules.setdefault("google.cloud.storage", st)


def _wf():
    _stub_gcs()
    try:
        import gcp.research.strat_engine.strat_walk_forward as wf
    except Exception as e:  # pragma: no cover - environment-dependent
        pytest.skip(f"heavy stack unavailable: {e}")
    return wf


# ── 1. The date-carved train/calibration split ──────────────────────────────

def test_train_holdout_split_is_disjoint_by_date():
    wf = _wf()
    bd = np.repeat(
        np.arange(np.datetime64("2020-01-01"),
                  np.datetime64("2020-01-01") + np.timedelta64(20, "D")), 30)
    train = bd < np.datetime64("2020-01-15")  # 14 distinct train days
    fit, calib = wf._train_holdout_split_by_date(bd, train, calib_frac=0.2)
    assert int((fit & calib).sum()) == 0
    assert int((fit | calib).sum()) == int(train.sum())
    # newest calib_frac of days → ceil(14*0.2)=3 distinct days in calib slice
    assert len(np.unique(bd[calib])) == 3
    # date-based: calib strictly newer than fit, and neither touches the test
    assert bd[calib].min() > bd[fit].max()
    assert bd[calib].max() < np.datetime64("2020-01-15")


def test_train_holdout_split_falls_back_when_thin():
    wf = _wf()
    bd = np.repeat(np.arange(np.datetime64("2020-01-01"),
                             np.datetime64("2020-01-01") + np.timedelta64(3, "D")), 50)
    train = np.ones(len(bd), dtype=bool)
    fit, calib = wf._train_holdout_split_by_date(bd, train, calib_frac=0.2)
    # < 5 distinct dates → no calib slice carved → caller falls back to raw
    assert int(calib.sum()) == 0
    assert int(fit.sum()) == int(train.sum())


# ── 2. The isotonic_oos fold path runs and the gate is honest ───────────────

def _synthetic_multiclass(n_days=20, per_day=200, seed=0):
    """4-class next_bar_type-shaped problem, weakly predictable from X[:,0]."""
    rng = np.random.default_rng(seed)
    n = n_days * per_day
    start = np.datetime64("2019-01-01")
    bd = np.repeat(np.arange(start, start + np.timedelta64(n_days, "D")), per_day)
    X = rng.normal(size=(n, 5)).astype(np.float32)
    lin = X[:, 0] + rng.normal(scale=2.0, size=n)
    y = np.digitize(lin, [-1.0, 0.0, 1.0]).astype(np.int64)  # 0..3
    return X, y, bd


def test_isotonic_oos_fold_runs_and_reports_calibrated_ece():
    wf = _wf()
    X, y, bd = _synthetic_multiclass()
    r = wf.train_and_evaluate_fold(
        X, y, bd, "2019-01-15", "2019-01-21", 1, calibration="isotonic_oos")
    assert r["status"] == "OK"
    assert r["calib_status"] == "isotonic_oos"
    assert np.isfinite(r["ece"]) and 0.0 <= r["ece"] <= 1.0
    # proba renormalization contract: ECE computed on a proper distribution
    # (the helper renormalizes rows) — a >1 ECE would signal a broken stack.


def test_ece_gate_ceiling_unchanged_at_005():
    """HONESTY: the ECE ceiling must NOT have been loosened for 30m. The task
    forbids raising the gate to force a 30m pass; assert the single ceiling
    constant is still 0.05 (the per-tf 0.075 mentioned in the registry doc was
    never code, and must not be introduced as a silent loosening)."""
    wf = _wf()
    from gcp.research.strat_engine.strat_config import DEFAULT_ECE_CEILING
    assert DEFAULT_ECE_CEILING == 0.05
    # And the walk-forward must evaluate PASS/FAIL against that exact constant.
    import inspect
    src = inspect.getsource(wf.walk_forward)
    assert "DEFAULT_ECE_CEILING" in src
    assert "r[\"ece\"] <= DEFAULT_ECE_CEILING" in src or \
           'r["ece"] <= DEFAULT_ECE_CEILING' in src


def test_isotonic_oos_base_model_excludes_calib_slice_and_test():
    """No-leak contract: in the isotonic_oos path the BASE model is fit only on
    the fit-slice — never the calibration slice, never the test fold."""
    wf = _wf()
    X, y, bd = _synthetic_multiclass()
    captured = {}
    real = wf.make_lgbm

    class _Spy:
        def __init__(self, inner):
            self._inner = inner

        def fit(self, Xf, yf):
            captured["fit_x0"] = np.array(Xf[:, 0])
            return self._inner.fit(Xf, yf)

        def __getattr__(self, k):
            return getattr(self._inner, k)

    wf.make_lgbm = lambda **kw: _Spy(real(**kw))
    try:
        r = wf.train_and_evaluate_fold(
            X, y, bd, "2019-01-15", "2019-01-21", 1, calibration="isotonic_oos")
    finally:
        wf.make_lgbm = real

    assert r["status"] == "OK" and r["calib_status"] == "isotonic_oos"
    train_mask = bd < np.datetime64("2019-01-15")
    test_mask = (bd >= np.datetime64("2019-01-15")) & (bd < np.datetime64("2019-01-21"))
    fit_mask, calib_mask = wf._train_holdout_split_by_date(bd, train_mask, 0.2)
    used = set(np.round(captured["fit_x0"], 6).tolist())
    assert used.isdisjoint(set(np.round(X[calib_mask, 0], 6).tolist())), \
        "base model saw the calibration slice"
    assert used.isdisjoint(set(np.round(X[test_mask, 0], 6).tolist())), \
        "base model saw the test fold"
    # And it DID train on the fit slice.
    assert used == set(np.round(X[fit_mask, 0], 6).tolist())


def test_calibration_choices_include_isotonic_oos_and_default_is_none():
    """The new mode must be a valid CLI choice, and the production default must
    stay 'none' so sibling jobs sharing the harness are unaffected."""
    wf = _wf()
    from gcp.research.strat_engine.strat_config import DEFAULT_CALIBRATION
    assert DEFAULT_CALIBRATION == "none"
    import inspect
    src = inspect.getsource(wf.main)
    assert "isotonic_oos" in src
