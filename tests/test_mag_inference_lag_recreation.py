"""Regression test for the lag-recreation contract in mag_inference.

Background — verified 2026-06-20: post-#629 (which fixed the levels-join
drift), the magnitude-inference predictions were collapsed to 98% TIGHT
across IWM/SPY/QQQ vs ~36% true base rate. Root cause was that training
adds prev1/2/3_candle in label_next_bar_type() BEFORE featurize() one-hot
encodes them — so feature_cols.txt lists ~12 prev*_candle_<value> dummies.
Inference did NOT recreate those lags, so every dummy was missing at
featurize time and the zero-fill heuristic in _score_and_persist silently
erased the sequence feature on every prediction.

The fix: route both training (via label_next_bar_type) and inference
(via _load_recent_features) through the SAME add_session_aware_lags
helper. This test pins both call sites so a future refactor can't
silently regress.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


def _stub_missing_modules(mods: list[str]) -> None:
    """Only stub when the real package is unavailable; setdefault()
    poisons sys.modules for sibling tests (caught 2026-06-09 in
    PR #597 CI)."""
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


def test_load_recent_features_recreates_training_lags():
    """The inference loader MUST return a frame with prev1/2/3_candle
    populated. featurize() relies on the lag columns being present to
    produce the prev*_candle_<value> dummies the model was trained on;
    if they're missing the model sees all-zero sequence features for
    every prediction — verified to collapse 98% of live predictions
    to bucket TIGHT vs ~36% true base rate (2026-06-20)."""
    from gcp.research.magnitude_engine import mag_inference as mod

    raw = pd.DataFrame({
        "ts": pd.date_range("2026-06-19 13:30", periods=6,
                            freq="5min", tz="UTC"),
        "ticker": ["IWM"] * 6,
        "bar_date": [pd.Timestamp("2026-06-19").date()] * 6,
        "strat_candle": ["1", "2U", "2D", "3", "1", "2U"],
        "orb_5m_high": [205.0] * 6,
    })
    with patch(
        "gcp.research.strat_engine.strat_dataset.load_strat_features_with_levels",
        return_value=raw,
    ), patch.object(mod, "get_engine", return_value=MagicMock()), \
         patch.object(mod, "_last_settled_ts", return_value=None):
        out = mod._load_recent_features("IWM", "5m", 24)

    assert "prev1_candle" in out.columns
    assert "prev2_candle" in out.columns
    assert "prev3_candle" in out.columns
    # Session-aware: row index 3 (4th raw row) has prev1 = raw row 2 = '2D'.
    # Warmup drop removes rows 0/1/2 (prev3_candle NaN); 4th raw row becomes
    # the first surviving row.
    assert len(out) == 3
    assert out.iloc[0]["prev1_candle"] == "2D"
    assert out.iloc[0]["prev2_candle"] == "2U"
    assert out.iloc[0]["prev3_candle"] == "1"
    assert out.iloc[2]["prev1_candle"] == "1"


def test_load_recent_features_drops_session_warmup_bars():
    """Training calls label_next_bar_type with drop_warmup=True (default)
    so the model NEVER trained on a row where prev3_candle is NaN.
    Inference must drop those too — feeding them to the model would
    supply all-zero prev*_candle_* dummies which is out-of-distribution."""
    from gcp.research.magnitude_engine import mag_inference as mod

    raw = pd.DataFrame({
        "ts": pd.date_range("2026-06-19 13:30", periods=5,
                            freq="5min", tz="UTC"),
        "ticker": ["IWM"] * 5,
        "bar_date": [pd.Timestamp("2026-06-19").date()] * 5,
        "strat_candle": ["1", "2U", "2D", "3", "1"],
    })
    with patch(
        "gcp.research.strat_engine.strat_dataset.load_strat_features_with_levels",
        return_value=raw,
    ), patch.object(mod, "get_engine", return_value=MagicMock()), \
         patch.object(mod, "_last_settled_ts", return_value=None):
        out = mod._load_recent_features("IWM", "5m", 24)

    # First 3 raw bars have prev3_candle NaN → dropped.
    assert len(out) == 2
    assert out["prev3_candle"].notna().all()


def test_load_recent_features_handles_empty_loader_result():
    """An empty frame must NOT raise from the lag/warmup step — the
    guard at the top of _load_recent_features returns the empty frame
    before the shift call would die on a missing column."""
    from gcp.research.magnitude_engine import mag_inference as mod

    with patch(
        "gcp.research.strat_engine.strat_dataset.load_strat_features_with_levels",
        return_value=pd.DataFrame(),
    ), patch.object(mod, "get_engine", return_value=MagicMock()), \
         patch.object(mod, "_last_settled_ts", return_value=None):
        out = mod._load_recent_features("IWM", "5m", 24)

    assert out.empty


def test_add_session_aware_lags_matches_label_next_bar_type():
    """Pin that the shared helper produces identical prev1/2/3_candle
    columns to label_next_bar_type for every row the labeler kept. If
    the helper's shift semantics drift apart from the labeler, training
    and inference will produce different sequence features for the same
    raw frame — the failure mode this refactor exists to prevent."""
    from gcp.research.strat_engine.strat_dataset import (
        add_session_aware_lags, label_next_bar_type,
    )

    raw = pd.DataFrame({
        "ts": pd.date_range("2026-06-19 13:30", periods=8,
                            freq="5min", tz="UTC"),
        "bar_date": [pd.Timestamp("2026-06-19").date()] * 4 +
                    [pd.Timestamp("2026-06-20").date()] * 4,
        "strat_candle": ["1", "2U", "2D", "3", "1", "2U", "2D", "3"],
        "open": [100.0] * 8, "high": [101.0] * 8,
        "low": [99.0] * 8, "close": [100.5] * 8,
    })

    lags_only = add_session_aware_lags(raw, "5m")
    full = label_next_bar_type(raw, "5m", drop_warmup=False)

    for col in ("prev1_candle", "prev2_candle", "prev3_candle"):
        merged = full[["ts", col]].merge(
            lags_only[["ts", col]], on="ts", suffixes=("_full", "_helper"),
        )
        for _, row in merged.iterrows():
            full_val = row[f"{col}_full"]
            helper_val = row[f"{col}_helper"]
            if pd.isna(full_val) and pd.isna(helper_val):
                continue
            assert full_val == helper_val, (
                f"{col} mismatch at ts={row['ts']}: "
                f"label_next_bar_type={full_val!r} vs "
                f"add_session_aware_lags={helper_val!r}"
            )

    # Session-aware: first row of session 2 (2026-06-20) has prev=NaN
    # because the shift doesn't cross days.
    session_two_first = lags_only[
        lags_only["bar_date"] == pd.Timestamp("2026-06-20").date()
    ].iloc[0]
    assert pd.isna(session_two_first["prev1_candle"]), (
        "session-aware shift must produce NaN for the first bar of a "
        "new session — it crossed days, which is the bug this helper "
        "exists to prevent"
    )
