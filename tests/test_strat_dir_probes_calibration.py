"""Hermetic tests for the E4 triple-barrier probe's NEW --holdout and
--calibrate machinery (gcp.research.strat_engine.strat_dir_probes).

These lock the three contracts the IWM-flicker settle-test depends on:

  1. LOCKED HOLDOUT — bars dated >= the holdout are excluded from EVERY
     training fold (and from the calibration slice). A holdout that leaked
     into training would make the "out-of-sample" verdict a lie.
  2. CALIBRATION — the isotonic/platt path runs, fits ONLY on a date-carved
     slice of TRAIN, and reports a (binary) ECE. Per E-20 the verdict on
     whether it HELPS is empirical; here we only assert the path is wired,
     honest (no test/holdout leak into the calibrator), and reports a number.
  3. LEAK GUARD — a planted forward-looking column still trips the fail-loud
     leak check (it must never silently enter the feature matrix).

Tier-1 (pure numpy+pandas) tests need no heavy deps. The fold-level tests
import the LightGBM/sklearn fold helpers; those transitively pull
strat_pred_train, which eagerly imports google.cloud.storage. We stub that
one symbol (it's only used for the GCS upload, never in a fold) so the fold
math runs hermetically; if lightgbm/sklearn aren't installed the fold tests
skip rather than fail (same posture as the repo's other heavy-stack tests).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


# ── Tier 1: pure helpers (numpy/pandas only) ────────────────────────────────

from gcp.research.strat_engine.strat_dir_probes import (  # noqa: E402
    binary_ece,
    calibration_split,
    _fit_calibrator,
)


def test_binary_ece_zero_when_perfectly_calibrated():
    # 0.2-bin frequency 0.2, 0.8-bin frequency 0.8 → ECE exactly 0.
    p = np.array([0.2] * 5 + [0.8] * 5)
    y = np.array([0, 0, 0, 0, 1] + [1, 1, 1, 1, 0])
    assert binary_ece(y, p, n_bins=10) == pytest.approx(0.0, abs=1e-12)


def test_binary_ece_large_when_inverted():
    # Predict 0.2 where truth is all-1 and 0.8 where truth is all-0 → ECE 0.8.
    p = np.array([0.2] * 5 + [0.8] * 5)
    y = np.array([1, 1, 1, 1, 1] + [0, 0, 0, 0, 0])
    assert binary_ece(y, p, n_bins=10) == pytest.approx(0.8, abs=1e-12)


def test_binary_ece_empty_is_nan_not_zero():
    # Rule 3.7: a 0 here would be indistinguishable from perfect calibration.
    assert np.isnan(binary_ece(np.array([]), np.array([])))


def _dates(spec: dict[str, int]) -> np.ndarray:
    """spec = {YYYY-MM-DD: n_rows}; returns a day-precision bar_dates array."""
    out = []
    for d, n in spec.items():
        out += [np.datetime64(d)] * n
    return np.array(out, dtype="datetime64[D]")


def test_calibration_split_is_disjoint_and_date_based():
    bar_dates = _dates({f"2020-01-{d:02d}": 3 for d in range(1, 11)})  # 10 days
    train = np.ones(len(bar_dates), dtype=bool)
    fit, calib = calibration_split(bar_dates, train, calib_frac=0.2)
    # Partitions the train block, no overlap, no bar lost.
    assert int((fit & calib).sum()) == 0
    assert int((fit | calib).sum()) == int(train.sum())
    # 0.2 of 10 distinct days → ceil = 2 days → 6 rows in the calib slice.
    assert int(calib.sum()) == 6
    # Date-based: every calib date is strictly newer than every fit date.
    assert bar_dates[calib].min() > bar_dates[fit].max()


def test_calibration_split_falls_back_when_too_few_days():
    # < 5 distinct dates → cannot carve an honest slice → (all-train, none).
    bar_dates = _dates({"2020-01-01": 50, "2020-01-02": 50})
    train = np.ones(len(bar_dates), dtype=bool)
    fit, calib = calibration_split(bar_dates, train, calib_frac=0.2)
    assert int(calib.sum()) == 0
    assert int(fit.sum()) == int(train.sum())


def test_fit_calibrator_single_class_slice_fails_loud():
    # Rule 3.7: a single-class calibration slice must RAISE, not silently
    # return an identity map that the caller can't distinguish from success.
    with pytest.raises(RuntimeError, match="single-class"):
        _fit_calibrator("isotonic", np.array([0.3, 0.6, 0.9]), np.array([1, 1, 1]))


def test_fit_calibrator_rejects_unknown_method():
    with pytest.raises(ValueError, match="unknown calibration method"):
        _fit_calibrator("sigmoidish", np.array([0.3, 0.6]), np.array([0, 1]))


def test_fit_calibrator_isotonic_is_monotone():
    # A monotone calibrator must preserve ordering of inputs.
    rng = np.random.default_rng(1)
    p = rng.uniform(size=400)
    y = (rng.uniform(size=400) < p).astype(int)  # well-calibrated truth
    apply = _fit_calibrator("isotonic", p, y)
    grid = np.linspace(0.05, 0.95, 19)
    out = apply(grid)
    assert np.all(np.diff(out) >= -1e-9)  # non-decreasing
    assert out.min() >= 0.0 and out.max() <= 1.0


# ── Tier 2: fold-level holdout + calibration (heavy stack, stubbed GCS) ──────

def _import_fold_helpers():
    """Import the LightGBM/sklearn fold helpers, stubbing the one eager
    google.cloud.storage import that the heavy module pulls in (used only for
    a GCS upload that never runs inside a fold). Skips if lightgbm/sklearn are
    absent."""
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
    try:
        from gcp.research.strat_engine.strat_dir_probes import (
            _side_fold, _side_holdout_eval,
        )
    except Exception as e:  # pragma: no cover - environment-dependent
        pytest.skip(f"heavy stack unavailable: {e}")
    return _side_fold, _side_holdout_eval


def _synthetic(n_days: int = 24, per_day: int = 50, seed: int = 0):
    """A mildly-predictable binary fold problem with a clean day structure."""
    rng = np.random.default_rng(seed)
    n = n_days * per_day
    start = np.datetime64("2020-01-01")
    bar_dates = np.repeat(
        np.arange(start, start + np.timedelta64(n_days, "D")), per_day)
    X = rng.normal(size=(n, 4)).astype(np.float32)
    y = (X[:, 0] + rng.normal(scale=2.0, size=n) > 0).astype(np.int64)
    return X, y, bar_dates


def test_holdout_bars_never_enter_any_training_fold():
    """CONTRACT (a): with a holdout_mask, the fold's train set contains ZERO
    holdout rows. We assert this by monkeypatching make_direction_lgbm so we
    can capture exactly which rows the model was fit on."""
    _side_fold, _ = _import_fold_helpers()
    import gcp.research.strat_engine.strat_dir_walk_forward as wf

    X, y, bar_dates = _synthetic()
    holdout = bar_dates >= np.datetime64("2020-01-19")
    ev = np.ones(len(y), dtype=bool)
    cond = np.ones(len(y), dtype=bool)

    captured = {}
    real = wf.make_direction_lgbm

    class _Spy:
        def __init__(self, inner):
            self._inner = inner

        def fit(self, Xf, yf):
            # Record the fingerprint of the rows used (X[:,0] is unique-ish).
            captured.setdefault("fit_x0", []).append(np.array(Xf[:, 0]))
            return self._inner.fit(Xf, yf)

        def __getattr__(self, k):
            return getattr(self._inner, k)

    wf.make_direction_lgbm = lambda **kw: _Spy(real(**kw))
    try:
        r = _side_fold(X, y, bar_dates, "2020-01-15", "2020-01-19", 1,
                       cond, cond, ev, 1, "long",
                       calibrate="none", holdout_mask=holdout)
    finally:
        wf.make_direction_lgbm = real

    assert r["status"] == "OK", r
    holdout_x0 = set(np.round(X[holdout, 0], 6).tolist())
    for fit_x0 in captured["fit_x0"]:
        used = set(np.round(fit_x0, 6).tolist())
        assert used.isdisjoint(holdout_x0), (
            "a holdout bar leaked into a training fold")


def test_calibration_path_runs_and_reports_ece():
    """CONTRACT (b): the isotonic path runs end-to-end and reports a finite
    binary ECE with calib_status='isotonic' (the calibrator was actually
    applied, not silently skipped)."""
    _side_fold, _ = _import_fold_helpers()
    X, y, bar_dates = _synthetic()
    holdout = bar_dates >= np.datetime64("2020-01-19")
    ev = np.ones(len(y), dtype=bool)
    cond = np.ones(len(y), dtype=bool)
    r = _side_fold(X, y, bar_dates, "2020-01-15", "2020-01-19", 1,
                   cond, cond, ev, 1, "long",
                   calibrate="isotonic", holdout_mask=holdout)
    assert r["status"] == "OK"
    assert r["calib_status"] == "isotonic"
    assert np.isfinite(r["ece"])
    assert 0.0 <= r["ece"] <= 1.0


def test_locked_holdout_eval_trains_only_on_preholdout():
    """CONTRACT (a, holdout-eval form): the final locked-holdout evaluation
    trains only on pre-holdout bars and tests ONLY on holdout bars."""
    _, _side_holdout_eval = _import_fold_helpers()
    import gcp.research.strat_engine.strat_dir_walk_forward as wf

    X, y, bar_dates = _synthetic()
    holdout = bar_dates >= np.datetime64("2020-01-19")
    ev = np.ones(len(y), dtype=bool)
    cond = np.ones(len(y), dtype=bool)

    captured = {}
    real = wf.make_direction_lgbm

    class _Spy:
        def __init__(self, inner):
            self._inner = inner

        def fit(self, Xf, yf):
            captured.setdefault("fit_x0", []).append(np.array(Xf[:, 0]))
            return self._inner.fit(Xf, yf)

        def __getattr__(self, k):
            return getattr(self._inner, k)

    wf.make_direction_lgbm = lambda **kw: _Spy(real(**kw))
    try:
        hr = _side_holdout_eval(X, y, bar_dates, holdout, "2020-01-19", 1,
                                cond, ev, 1, "long", "none")
    finally:
        wf.make_direction_lgbm = real

    assert hr["status"] == "OK"
    # The eval set size must equal the holdout-bar count (minus embargo/cond,
    # which are all-true here) — i.e. it tested on the locked block.
    assert hr["n_test"] == int(holdout.sum())
    holdout_x0 = set(np.round(X[holdout, 0], 6).tolist())
    for fit_x0 in captured["fit_x0"]:
        assert set(np.round(fit_x0, 6).tolist()).isdisjoint(holdout_x0)


# ── Tier 2: leak guard still fires on a planted forward column ───────────────

def test_leak_guard_fires_on_planted_fwd_column():
    """CONTRACT (c): the fail-loud forward-looking-column check in the E4 probe
    must trip when a `fwd_`/`next_` column would enter the feature matrix.

    We don't need the DB: the guard is a pure list-comprehension on
    feature_cols. We reconstruct exactly the guard expression the probe uses
    and assert it raises-worthy (non-empty) on a planted column and is empty
    on a clean column set — pinning the contract source-side."""
    import inspect
    from gcp.research.strat_engine import strat_dir_probes as probe
    src = inspect.getsource(probe.run_triple_barrier_probe)
    # The guard must still be present in the E4 path.
    assert 'startswith(("fwd_", "next_", "_fwd"))' in src, (
        "E4 leak guard removed — forward-looking columns could enter the "
        "feature matrix undetected")
    assert 'raise SystemExit' in src and "LEAKAGE" in src

    # Reproduce the guard predicate and prove it discriminates.
    def _leak(cols):
        return [c for c in cols
                if c.startswith(("fwd_", "next_", "_fwd")) or "fwd_ret" in c]

    assert _leak(["rsi_14", "ema_9", "fwd_ret_5bars_bps"]) == ["fwd_ret_5bars_bps"]
    assert _leak(["rsi_14", "ema_9", "next_open"]) == ["next_open"]
    assert _leak(["rsi_14", "ema_9", "vwap"]) == []
