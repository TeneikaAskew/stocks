"""Tempered class weights for the magnitude model.

`class_weight='balanced'` de-collapsed the model but OVER-corrected: it
predicted the minority buckets too often (IWM 5m: 47/27/19/7 vs true 66/25/6/2),
and isotonic calibration over-corrected the other way (re-collapse to 100%
TIGHT). Tempered weights = balanced_weight ** alpha give a tunable middle
ground: alpha=1 is full 'balanced', alpha=0 is uniform (== None). These tests
pin the math and that a tempered model's majority-class share lands strictly
between the None (collapsed) and balanced (over-corrected) extremes.
"""
import numpy as np
import pytest

from gcp.research.magnitude_engine.mag_pred_train import (
    make_lgbm, tempered_class_weight, resolve_class_weight,
)


def _require_real_lgbm():
    import importlib
    from unittest.mock import Mock
    try:
        mod = importlib.import_module("lightgbm")
    except Exception as e:  # pragma: no cover
        pytest.skip(f"lightgbm unavailable: {e}")
    if isinstance(mod, Mock):
        pytest.skip("lightgbm is a mock stub (sys.modules poisoned by a sibling test)")


_Y = np.array([0] * 60 + [1] * 30 + [2] * 10)  # n=100, k=3, counts 60/30/10


def test_alpha_1_equals_balanced():
    w = tempered_class_weight(_Y, alpha=1.0)
    for c, cnt in ((0, 60), (1, 30), (2, 10)):
        assert w[c] == pytest.approx(100 / (3 * cnt))


def test_alpha_0_is_uniform():
    w = tempered_class_weight(_Y, alpha=0.0)
    assert all(v == pytest.approx(1.0) for v in w.values())


def test_alpha_half_is_sqrt_of_balanced():
    w = tempered_class_weight(_Y, alpha=0.5)
    assert w[2] == pytest.approx((100 / (3 * 10)) ** 0.5)


def test_resolve_default_is_tempered_075(monkeypatch):
    # Env unset → validated production default alpha=0.75 (a tempered dict,
    # not 'balanced' and not None).
    monkeypatch.delenv("MAG_CLASS_WEIGHT_POWER", raising=False)
    w = resolve_class_weight(_Y)
    assert isinstance(w, dict)
    assert w[2] == pytest.approx((100 / (3 * 10)) ** 0.75)


def test_resolve_env_override(monkeypatch):
    monkeypatch.setenv("MAG_CLASS_WEIGHT_POWER", "1.0")
    assert resolve_class_weight(_Y) == "balanced"
    monkeypatch.setenv("MAG_CLASS_WEIGHT_POWER", "0")
    assert resolve_class_weight(_Y) is None


def _imbalanced_overlapping(rng):
    centres = {0: (0.0, 0.0), 1: (3.0, 0.0), 2: (0.0, 3.0), 3: (3.0, 3.0)}
    counts = {0: 2600, 1: 1000, 2: 240, 3: 160}
    Xs, ys = [], []
    for cls, (cx, cy) in centres.items():
        pts = rng.normal(loc=(cx, cy), scale=2.6, size=(counts[cls], 2))
        Xs.append(pts)
        ys.append(np.full(counts[cls], cls))
    X = np.vstack(Xs)
    y = np.concatenate(ys)
    order = rng.permutation(len(y))
    return X[order], y[order]


def _majority_share(class_weight, X, y):
    m = make_lgbm(class_weight=class_weight, random_state=0)
    m.fit(X, y)
    preds = m.predict(X)
    return float((preds == 0).mean())


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_tempered_share_between_none_and_balanced():
    _require_real_lgbm()
    rng = np.random.default_rng(0)
    X, y = _imbalanced_overlapping(rng)
    share_none = _majority_share(None, X, y)
    share_balanced = _majority_share("balanced", X, y)
    share_tempered = _majority_share(tempered_class_weight(y, alpha=0.5), X, y)
    # tempered sits strictly between the collapsed and over-corrected extremes
    assert share_balanced < share_tempered < share_none
