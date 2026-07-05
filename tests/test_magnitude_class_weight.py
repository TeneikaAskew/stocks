"""Magnitude model must train with balanced class weights.

The production model `magnitude-engine-rmcwj` collapsed to predicting TIGHT
97-100% of the time on well-formed inputs, even though the real label
distribution is ~66/25/6/2 (TIGHT/NORMAL/EXPANDED/EXPLOSIVE). Root cause:
`make_lgbm` trained with `class_weight=None` on imbalanced labels, so the
learner minimised log-loss by predicting the majority class and abandoning the
NORMAL/EXPANDED/EXPLOSIVE bars traders actually care about. These tests pin the
fix: the default is balanced, and a default model recovers minority classes on
imbalanced-but-separable data instead of collapsing to the majority.
"""
import numpy as np
import pytest

from gcp.research.magnitude_engine.mag_pred_train import make_lgbm

pytest.importorskip("lightgbm")


def test_make_lgbm_defaults_to_balanced_class_weight():
    # Contract guard: the production default must correct label imbalance.
    assert make_lgbm(random_state=0).get_params()["class_weight"] == "balanced"


def _imbalanced_overlapping(rng):
    """4 classes at distinct 2-D centres, imbalanced like the real labels
    (~66/25/6/2), with heavy overlap (scale >> centre spacing). The overlap is
    what makes imbalance bite: an unweighted learner predicts the majority
    class across the shared region and abandons the rare ones; balanced class
    weights lift the minority gradient enough to recover them in their region."""
    centres = {0: (0.0, 0.0), 1: (3.0, 0.0), 2: (0.0, 3.0), 3: (3.0, 3.0)}
    counts = {0: 2600, 1: 1000, 2: 240, 3: 160}  # ~65/25/6/4; rare >= min_child
    Xs, ys = [], []
    for cls, (cx, cy) in centres.items():
        n = counts[cls]
        pts = rng.normal(loc=(cx, cy), scale=2.6, size=(n, 2))
        Xs.append(pts)
        ys.append(np.full(n, cls))
    X = np.vstack(Xs)
    y = np.concatenate(ys)
    order = rng.permutation(len(y))
    return X[order], y[order]


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_default_model_does_not_collapse_on_imbalanced_labels():
    rng = np.random.default_rng(0)
    X, y = _imbalanced_overlapping(rng)
    model = make_lgbm(random_state=0)  # DEFAULT class_weight
    model.fit(X, y)
    preds = model.predict(X)
    # Collapse signature: the majority class (0, ~65% prevalence) floods the
    # predictions and starves the minorities. With class_weight=None the model
    # predicts class 0 ~78% of the time (over its 65% base rate); balanced
    # weighting brings it to ~41%. Anything under 65% means minorities are
    # being recovered rather than abandoned.
    majority_share = float((preds == 0).mean())
    assert majority_share < 0.65, (
        f"model collapsed to the majority class (share={majority_share:.2f})"
    )
