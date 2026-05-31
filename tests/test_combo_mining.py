"""Hermetic tests for lib.combo_mining (shared combo-prediction core).

No I/O, no network. Synthetic frames exercise the real combo math and the
leakage controls (train-only thresholds, shuffled-test control).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib import combo_mining as cm  # noqa: E402


# ---------------------------------------------------------------------------
# stationary_feature_filter
# ---------------------------------------------------------------------------

def test_filter_keeps_stationary_drops_absolute_price():
    cols = ["RSI14", "ATR_Expansion", "EMA9", "VWAP", "SMA200", "OBV",
            "ORB_15m_High", "ORB_15m_High_Pct", "ORB_15m_Trend",
            "Daily_Range_Pct_Lag1", "EMA9_Slope"]
    kept = cm.stationary_feature_filter(cols)
    # stationary kept
    assert "RSI14" in kept and "ATR_Expansion" in kept and "EMA9_Slope" in kept
    # normalised ORB kept, raw ORB price dropped
    assert "ORB_15m_High_Pct" in kept and "ORB_15m_Trend" in kept
    assert "ORB_15m_High" not in kept
    # absolute-price columns dropped
    for c in ("EMA9", "VWAP", "SMA200", "OBV"):
        assert c not in kept
    # lagged whitelist variant kept
    assert "Daily_Range_Pct_Lag1" in kept


# ---------------------------------------------------------------------------
# binarize_conditions — train-only median (leakage control)
# ---------------------------------------------------------------------------

def test_binarize_uses_train_median_only():
    n = 200
    # feature: train half is 0..99, test half is 1000..1099 (very different).
    x = np.concatenate([np.arange(100), np.arange(1000, 1100)]).astype(float)
    df = pd.DataFrame({"F": x})
    train_mask = np.array([True] * 100 + [False] * 100)
    conds = cm.binarize_conditions(df, ["F"], train_mask)
    # median of TRAIN (0..99) is ~49.5 → all test rows are > med.
    hi = conds["F>med"]
    assert hi[100:].all(), "test rows must be classified vs the TRAIN median"
    # train split is balanced
    assert 40 <= hi[:100].sum() <= 60


def test_binarize_skips_constant_feature():
    df = pd.DataFrame({"C": np.ones(50), "G": np.arange(50.0)})
    tm = np.array([True] * 25 + [False] * 25)
    conds = cm.binarize_conditions(df, ["C", "G"], tm)
    assert "C>med" not in conds  # degenerate split skipped
    assert "G>med" in conds


# ---------------------------------------------------------------------------
# mine_combos — surfaces an engineered combo; respects support floor
# ---------------------------------------------------------------------------

def _engineered_frame(seed=0):
    """A=high & B=high → target true 80% of the time; else ~20%."""
    rng = np.random.default_rng(seed)
    n = 4000
    A = rng.normal(size=n)
    B = rng.normal(size=n)
    both_high = (A > 0) & (B > 0)
    p = np.where(both_high, 0.80, 0.20)
    y = np.where(rng.random(n) < p, "UP", "DOWN")
    df = pd.DataFrame({"A": A, "B": B})
    train_mask = np.arange(n) < int(0.7 * n)
    test_mask = ~train_mask
    return df, pd.Series(y), train_mask, test_mask


def test_mine_combos_surfaces_known_combo():
    df, y, tr, te = _engineered_frame()
    res = cm.mine_combos(df, ["A", "B"], y, "UP", tr, te,
                         max_order=2, min_support=50, top_k=10)
    assert res, "should find combos"
    top = res[0]
    # the A>med AND B>med combo should be at/near the top with strong lift
    assert top.lift > 1.5
    cond_sets = [set(r.conditions) for r in res[:3]]
    assert {"A>med", "B>med"} in cond_sets


def test_mine_combos_respects_support_floor():
    df, y, tr, te = _engineered_frame()
    huge = cm.mine_combos(df, ["A", "B"], y, "UP", tr, te,
                          max_order=3, min_support=10_000, top_k=10)
    assert huge == []  # nothing clears an impossibly high floor


def test_mine_combos_no_high_low_same_feature():
    df, y, tr, te = _engineered_frame()
    res = cm.mine_combos(df, ["A", "B"], y, "UP", tr, te,
                         max_order=2, min_support=50, top_k=50)
    for r in res:
        bases = [c.rsplit(">med", 1)[0].rsplit("<=med", 1)[0] for c in r.conditions]
        assert len(set(bases)) == len(bases), "must not combine a feature's hi+lo"


# ---------------------------------------------------------------------------
# Leakage control — shuffled label → no edge (hit ≈ base)
# ---------------------------------------------------------------------------

def test_shuffled_label_yields_no_edge():
    df, y, tr, te = _engineered_frame(seed=1)
    y_shuf = pd.Series(np.random.default_rng(99).permutation(y.values))
    res = cm.mine_combos(df, ["A", "B"], y_shuf, "UP", tr, te,
                         max_order=2, min_support=200, top_k=10)
    # With labels shuffled, the best combo's hit-rate should be ~ base rate.
    for r in res:
        assert abs(r.hit_rate - r.base_rate) < 0.08


# ---------------------------------------------------------------------------
# model_lift — binary and multiclass both work
# ---------------------------------------------------------------------------

def test_model_lift_binary():
    pytest.importorskip("sklearn")
    df, y, tr, te = _engineered_frame(seed=2)
    ml = cm.model_lift(df, ["A", "B"], y, tr, te, "direction")
    assert 0.0 <= ml.oos_accuracy <= 1.0
    assert ml.oos_accuracy > ml.base_rate  # engineered signal beats base
    assert set(ml.perm_importance) <= {"A", "B"}


def test_model_lift_multiclass():
    pytest.importorskip("sklearn")
    rng = np.random.default_rng(3)
    n = 3000
    A = rng.normal(size=n)
    # 4-class label driven by A bucket (so the model has real signal)
    cls = np.where(A < -0.7, "1", np.where(A < 0, "2D",
                   np.where(A < 0.7, "2U", "3")))
    df = pd.DataFrame({"A": A, "B": rng.normal(size=n)})
    tr = np.arange(n) < 2000
    ml = cm.model_lift(df, ["A", "B"], pd.Series(cls), tr, ~tr, "next_bar_type")
    assert len(ml.class_mix) == 4
    assert ml.oos_accuracy > ml.base_rate


# ---------------------------------------------------------------------------
# select_top_features
# ---------------------------------------------------------------------------

def test_select_top_features_ranks_informative_first():
    rng = np.random.default_rng(4)
    n = 1000
    signal = rng.normal(size=n)
    df = pd.DataFrame({"good": signal, "noise": rng.normal(size=n)})
    target = pd.Series(signal + 0.05 * rng.normal(size=n))  # good correlates
    tr = np.arange(n) < 700
    top = cm.select_top_features(df, ["good", "noise"], target, tr, k=1,
                                 method="spearman")
    assert top == ["good"]


# ---------------------------------------------------------------------------
# add_candidate_features
# ---------------------------------------------------------------------------

def _ohlcv(n=120):
    rng = np.random.default_rng(7)
    idx = pd.date_range("2024-01-02 09:30", periods=n, freq="1min")
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    df = pd.DataFrame({
        "Time": idx,
        "Open": close, "High": close * 1.001, "Low": close * 0.999,
        "Close": close, "Volume": rng.integers(1e4, 5e4, n).astype(float),
    }, index=idx)
    return df


def test_promoted_features_flow_from_engine():
    """Post-promotion: the engine produces the winners; add_candidate_features
    leaves them untouched (research↔live parity) and only adds the experimental
    + leakage-control columns."""
    from lib.indicators import add_all_indicators
    base = add_all_indicators(_ohlcv())
    # promoted features are the ENGINE's responsibility now
    for col in ["EMA9_Slope", "Mins_Since_Open", "Price_vs_EMA9_ATR",
                "Price_vs_VWAP_ATR", "EMA_Spread_ATR", "BB_Squeeze",
                "Realized_Vol_Short", "RSI_Divergence"]:
        assert col in base.columns, f"engine missing promoted {col}"

    out = cm.add_candidate_features(base)
    # candidate layer adds only the un-promoted / research-only columns
    added = [c for c in out.columns if c not in base.columns]
    assert set(added) == {"MACD_Hist_Slope", "Daily_Range_Pct_Lag1",
                          "Close_vs_Range_Lag1"}
    # and it does NOT mutate a promoted feature
    pd.testing.assert_series_equal(out["Realized_Vol_Short"], base["Realized_Vol_Short"])


def test_candidate_layer_idempotent_on_lags():
    """Calling twice doesn't double-add or overwrite (guarded by not-in-columns)."""
    from lib.indicators import add_all_indicators
    base = add_all_indicators(_ohlcv())
    once = cm.add_candidate_features(base)
    twice = cm.add_candidate_features(once)
    assert list(once.columns) == list(twice.columns)
    pd.testing.assert_series_equal(once["Daily_Range_Pct_Lag1"],
                                   twice["Daily_Range_Pct_Lag1"])
