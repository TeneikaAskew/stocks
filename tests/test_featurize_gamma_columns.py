"""Raw gamma price levels must not be model features; normalized distances are.

Holdout finding 2026-08-26: the gamma rebuild (#771) densified
strat_features' gamma_balance_price / gamma_flip from 22-60% non-null
(NULL→fillna(0)) to ~100% real dollar levels. Re-running the phase0
magnitude walk-forward on IDENTICAL fold windows and training-bar counts
flipped the 15m log-loss beat from ~+0.01 (6-8/8 positive folds) to
~-0.10 (0/8), and 30m the same; 5m was unchanged. Raw price levels are
non-stationary (IWM ~$130 in 2019 → ~$230 in 2026), so tree splits
learned on them are time proxies that cannot generalize out-of-fold —
harmless while the columns were mostly zeros, poison once dense.

Contract pinned here:
  1. featurize() derives dist_to_balance_pct = (close - balance)/close*100
     — the normalized, cross-year-comparable form (mirror of the persisted
     dist_to_gamma_flip_pct) — NaN where balance is missing or close<=0,
     then matrix-level fillna(0) like every sparse feature.
  2. featurize() drops the raw gamma_balance_price / gamma_flip levels
     from the feature matrix. dist_to_gamma_flip_pct (already normalized)
     stays.
  3. mag_walk_forward's task-parallel dispatch treats an out-of-plan
     CLOUD_RUN_TASK_INDEX as a clean no-op (exit 0), not the usage
     SystemExit — 18 of 27 tasks "failed" cosmetically on the 2026-08-26
     phase0 dispatch because _resolve_task's no-op return was
     indistinguishable from "not task-parallel at all".
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
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
])


def _frame_with_gamma_columns() -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": ["IWM"] * 4,
        "ts": pd.date_range("2026-08-25 13:30", periods=4, freq="15min", tz="UTC"),
        "tf": ["15m"] * 4,
        "bar_date": pd.date_range("2026-08-25", periods=4, freq="D").date,
        "open":   [230.0, 231.0, 232.0, 233.0],
        "high":   [231.0, 232.0, 233.0, 234.0],
        "low":    [229.0, 230.0, 231.0, 232.0],
        "close":  [230.0, 232.0, 231.0, 234.0],
        "volume": [1000, 1100, 1200, 1300],
        "rsi_14": [55.0, 60.0, 45.0, 50.0],
        # Raw dollar levels — must NOT survive as features.
        "gamma_balance_price": [225.0, np.nan, 233.0, 230.0],
        "gamma_flip": [220.0, 221.0, np.nan, 222.0],
        # Already-normalized distance — must stay a feature.
        "dist_to_gamma_flip_pct": [4.3, 4.7, np.nan, 5.1],
        "magnitude_atr": [0.4, 1.1, 0.7, 2.3],
    })


def test_raw_gamma_price_levels_are_not_features():
    from gcp.research.magnitude_engine.mag_pred_train import featurize
    X, cols = featurize(_frame_with_gamma_columns())
    assert "gamma_balance_price" not in cols, (
        "raw balance dollar level leaked into the feature matrix — "
        "non-stationary price splits are the 2026-08-26 15m/30m collapse")
    assert "gamma_flip" not in cols, "raw flip dollar level leaked into features"
    assert "dist_to_gamma_flip_pct" in cols, (
        "the normalized flip distance is the sanctioned form and must stay")


def test_dist_to_balance_pct_derived_and_normalized():
    from gcp.research.magnitude_engine.mag_pred_train import featurize
    X, cols = featurize(_frame_with_gamma_columns())
    assert "dist_to_balance_pct" in cols
    got = X["dist_to_balance_pct"].to_numpy()
    # Row 0: (230-225)/230*100; row 2: (231-233)/231*100; row 3: (234-230)/234*100
    assert got[0] == pytest.approx((230.0 - 225.0) / 230.0 * 100, abs=1e-4)
    assert got[2] == pytest.approx((231.0 - 233.0) / 231.0 * 100, abs=1e-4)
    assert got[3] == pytest.approx((234.0 - 230.0) / 234.0 * 100, abs=1e-4)
    # Row 1: balance NaN -> derivation NaN -> matrix fillna(0), the same
    # convention every sparse feature gets.
    assert got[1] == pytest.approx(0.0, abs=1e-6)


def test_featurize_without_gamma_columns_still_works():
    """Frames lacking the gamma columns (older fixtures, non-gamma tables)
    must featurize unchanged — no KeyError, no phantom column."""
    from gcp.research.magnitude_engine.mag_pred_train import featurize
    df = _frame_with_gamma_columns().drop(
        columns=["gamma_balance_price", "gamma_flip", "dist_to_gamma_flip_pct"])
    X, cols = featurize(df)
    assert "dist_to_balance_pct" not in cols
    assert "rsi_14" in cols


def test_mag_ablate_gamma_dist_drops_distance_features(monkeypatch):
    """MAG_ABLATE=gamma_dist excludes the gamma DISTANCE features too.

    Experiment knob (mirrors the MAG_FEATURES env precedent): the
    2026-08-26 ablation showed dropping only the raw levels did NOT
    recover the 15m/30m fold metrics, leaving dist_to_gamma_flip_pct
    (the one remaining rebuilt column) as the candidate driver. This
    knob removes dist_to_gamma_flip_pct and skips the dist_to_balance
    derivation so one phase0 run can measure the no-gamma-distance
    baseline. Unset env leaves the standard behavior untouched."""
    from gcp.research.magnitude_engine.mag_pred_train import featurize
    monkeypatch.setenv("MAG_ABLATE", "gamma_dist")
    X, cols = featurize(_frame_with_gamma_columns())
    assert "dist_to_gamma_flip_pct" not in cols
    assert "dist_to_balance_pct" not in cols
    assert "gamma_balance_price" not in cols and "gamma_flip" not in cols
    assert "rsi_14" in cols
    monkeypatch.delenv("MAG_ABLATE")
    _, cols_default = featurize(_frame_with_gamma_columns())
    assert "dist_to_gamma_flip_pct" in cols_default
    assert "dist_to_balance_pct" in cols_default


def test_out_of_plan_task_index_is_clean_noop(monkeypatch):
    """CLOUD_RUN_TASK_INDEX beyond the plan is a deliberate no-op, exit 0."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    monkeypatch.setenv("MAG_PLAN", "phase0")
    monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", "12")  # phase0 has 9 cells
    monkeypatch.setattr(sys, "argv", ["mag_walk_forward"])
    monkeypatch.setattr(mwf, "get_engine", lambda: MagicMock())
    called = []
    monkeypatch.setattr(mwf, "walk_forward",
                        lambda *a, **k: called.append((a, k)))
    # Must return cleanly: no SystemExit, no walk_forward call.
    mwf.main()
    assert called == []
