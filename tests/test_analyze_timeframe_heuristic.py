"""Hermetic tests for the timeframe-heuristic analysis helpers.

The script's pure helpers (bucketization, lookup-table build, prediction,
holdout evaluation) are tested here without DB access.

Coverage:
  1. bucket_atr — high/avg/low/unknown thresholds
  2. bucket_rsi — low/mid/high/unknown thresholds
  3. make_bucket — combines feature buckets
  4. build_lookup_table — picks mode of best_tf per bucket; falls
     through 'none' when the mode is "no clean tf"
  5. predict_with_lookup — cold-start fallback when bucket unseen
  6. evaluate_predictions — counts CLEAN_HIT/WRONG/NOISE/MIXED;
     INSUFFICIENT_DATA excluded from the denominator
  7. split_train_holdout — deterministic with fixed seed
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.analyze_timeframe_heuristic import (  # noqa: E402
    Bucket,
    bucket_atr,
    bucket_rsi,
    build_lookup_table,
    evaluate_predictions,
    make_bucket,
    predict_with_lookup,
    predict_with_placeholder,
    split_train_holdout,
)


# ── 1) bucket_atr ──────────────────────────────────────────────────────

def test_bucket_atr_high_threshold():
    """0.4% threshold: 0.005 → high, 0.003 → avg."""
    assert bucket_atr(0.005) == "high"
    assert bucket_atr(0.0041) == "high"


def test_bucket_atr_avg_band():
    assert bucket_atr(0.002) == "avg"


def test_bucket_atr_low_threshold():
    """≤ 0.001 = quiet."""
    assert bucket_atr(0.0005) == "low"
    assert bucket_atr(0.001) == "low"


def test_bucket_atr_unknown_on_none_or_nan():
    assert bucket_atr(None) == "unknown"
    assert bucket_atr(float("nan")) == "unknown"


# ── 2) bucket_rsi ──────────────────────────────────────────────────────

def test_bucket_rsi_low_below_30():
    assert bucket_rsi(20) == "low"
    assert bucket_rsi(29.9) == "low"


def test_bucket_rsi_high_above_70():
    assert bucket_rsi(75) == "high"
    assert bucket_rsi(70.1) == "high"


def test_bucket_rsi_mid_band():
    assert bucket_rsi(30) == "mid"
    assert bucket_rsi(50) == "mid"
    assert bucket_rsi(70) == "mid"


def test_bucket_rsi_unknown_on_none_or_nan():
    assert bucket_rsi(None) == "unknown"
    assert bucket_rsi(float("nan")) == "unknown"


# ── 3) make_bucket ─────────────────────────────────────────────────────

def test_make_bucket_combines_features():
    b = make_bucket({
        "strategy": "momentum", "signal_strength": 4,
        "atr_5m_pct": 0.005, "entry_rsi": 35.0,
    })
    assert b.strategy == "momentum"
    assert b.signal_strength == 4
    assert b.atr_bucket == "high"
    assert b.rsi_bucket == "mid"


def test_make_bucket_handles_missing_fields():
    b = make_bucket({"strategy": None, "signal_strength": None,
                     "atr_5m_pct": None, "entry_rsi": None})
    assert b.strategy == "unknown"
    assert b.signal_strength == 0
    assert b.atr_bucket == "unknown"
    assert b.rsi_bucket == "unknown"


# ── 4) build_lookup_table ──────────────────────────────────────────────

def _make_train_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_build_lookup_picks_mode_of_best_tf_per_bucket():
    """3 rows in same bucket: 2 vote 30m, 1 votes 60m → 30m wins."""
    df = _make_train_df([
        {"strategy": "momentum", "signal_strength": 4,
         "atr_5m_pct": 0.002, "entry_rsi": 50.0, "best_tf": "30m"},
        {"strategy": "momentum", "signal_strength": 4,
         "atr_5m_pct": 0.002, "entry_rsi": 50.0, "best_tf": "30m"},
        {"strategy": "momentum", "signal_strength": 4,
         "atr_5m_pct": 0.002, "entry_rsi": 50.0, "best_tf": "60m"},
    ])
    lookup = build_lookup_table(df)
    bucket = make_bucket(df.iloc[0].to_dict())
    assert lookup[bucket] == "30m"


def test_build_lookup_skips_none_when_mode_then_picks_second():
    """If 'no clean timeframe' is the mode (2 rows) but a real TF exists
    (1 row), pick the real TF — heuristic must produce SOMETHING."""
    df = _make_train_df([
        {"strategy": "momentum", "signal_strength": 4,
         "atr_5m_pct": 0.002, "entry_rsi": 50.0, "best_tf": None},
        {"strategy": "momentum", "signal_strength": 4,
         "atr_5m_pct": 0.002, "entry_rsi": 50.0, "best_tf": None},
        {"strategy": "momentum", "signal_strength": 4,
         "atr_5m_pct": 0.002, "entry_rsi": 50.0, "best_tf": "60m"},
    ])
    lookup = build_lookup_table(df)
    bucket = make_bucket(df.iloc[0].to_dict())
    assert lookup[bucket] == "60m"


def test_build_lookup_all_none_falls_through_to_30m():
    """Every row in a bucket has best_tf=None — heuristic still must
    return SOMETHING. Defaults to 30m."""
    df = _make_train_df([
        {"strategy": "momentum", "signal_strength": 4,
         "atr_5m_pct": 0.002, "entry_rsi": 50.0, "best_tf": None}
        for _ in range(3)
    ])
    lookup = build_lookup_table(df)
    bucket = make_bucket(df.iloc[0].to_dict())
    assert lookup[bucket] == "30m"


# ── 5) predict_with_lookup ─────────────────────────────────────────────

def test_predict_with_lookup_returns_table_value_for_known_bucket():
    df = _make_train_df([
        {"strategy": "momentum", "signal_strength": 4,
         "atr_5m_pct": 0.002, "entry_rsi": 50.0, "best_tf": "15m"},
    ])
    lookup = build_lookup_table(df)
    pred = predict_with_lookup(df.iloc[0].to_dict(), lookup)
    assert pred == "15m"


def test_predict_with_lookup_cold_start_falls_back():
    """Bucket not in train → cold_start_default ('30m')."""
    df = _make_train_df([
        {"strategy": "momentum", "signal_strength": 4,
         "atr_5m_pct": 0.002, "entry_rsi": 50.0, "best_tf": "15m"},
    ])
    lookup = build_lookup_table(df)
    # A holdout row with a different bucket
    pred = predict_with_lookup({
        "strategy": "mean_reversion", "signal_strength": 3,
        "atr_5m_pct": 0.0005, "entry_rsi": 80.0,
    }, lookup)
    assert pred == "30m"


# ── 6) evaluate_predictions ────────────────────────────────────────────

def test_evaluate_predictions_counts_clean_hits():
    holdout = pd.DataFrame([
        {"cls_15m": "CLEAN_HIT"},
        {"cls_15m": "CLEAN_HIT"},
        {"cls_15m": "WRONG_DIRECTION"},
        {"cls_15m": "NOISE"},
    ])
    metrics = evaluate_predictions(holdout, ["15m"] * 4)
    assert metrics["n_total"] == 4
    assert metrics["n_clean"] == 2
    assert metrics["n_wrong"] == 1
    assert metrics["n_noise"] == 1
    assert metrics["clean_rate_pct"] == 50.0


def test_evaluate_predictions_excludes_insufficient_from_denominator():
    """INSUFFICIENT_DATA shouldn't be counted as a wrong prediction —
    we just couldn't evaluate that timeframe yet."""
    holdout = pd.DataFrame([
        {"cls_240m": "CLEAN_HIT"},
        {"cls_240m": "INSUFFICIENT_DATA"},
        {"cls_240m": None},
        {"cls_240m": "CLEAN_HIT"},
    ])
    metrics = evaluate_predictions(holdout, ["240m"] * 4)
    assert metrics["n_total"] == 4
    assert metrics["n_insufficient"] == 2
    # 2 clean / (4-2) = 100%
    assert metrics["clean_rate_pct"] == 100.0


def test_evaluate_predictions_uses_per_row_predicted_timeframe():
    """Per-row predicted TF — ensure the right cls_<tf> column is read."""
    holdout = pd.DataFrame([
        {"cls_15m": "CLEAN_HIT", "cls_60m": "WRONG_DIRECTION"},
        {"cls_15m": "WRONG_DIRECTION", "cls_60m": "CLEAN_HIT"},
    ])
    metrics = evaluate_predictions(holdout, ["15m", "60m"])
    # Row 0 predicted 15m → CLEAN_HIT; Row 1 predicted 60m → CLEAN_HIT
    assert metrics["n_clean"] == 2
    assert metrics["clean_rate_pct"] == 100.0


# ── 7) split_train_holdout ─────────────────────────────────────────────

def test_split_train_holdout_deterministic_with_seed():
    df = pd.DataFrame({"x": range(100)})
    t1, h1 = split_train_holdout(df, holdout_pct=0.20, seed=42)
    t2, h2 = split_train_holdout(df, holdout_pct=0.20, seed=42)
    pd.testing.assert_frame_equal(t1, t2)
    pd.testing.assert_frame_equal(h1, h2)


def test_split_train_holdout_correct_sizes():
    df = pd.DataFrame({"x": range(100)})
    train, holdout = split_train_holdout(df, holdout_pct=0.20, seed=42)
    assert len(train) == 80
    assert len(holdout) == 20


def test_split_train_holdout_partitions_input():
    """Train + holdout exactly equals input (no row dropped, no overlap)."""
    df = pd.DataFrame({"x": range(100)})
    train, holdout = split_train_holdout(df, holdout_pct=0.30, seed=7)
    combined = set(train["x"]) | set(holdout["x"])
    assert combined == set(range(100))
    assert len(train["x"].tolist()) + len(holdout["x"].tolist()) == 100


# ── 8) sanity: predict_with_placeholder mirrors live heuristic ─────────

def test_predict_with_placeholder_uses_live_heuristic_branches():
    """Confirm the placeholder predictor matches the live
    assign_timeframe_for_backfill — they share the exact code path."""
    # high vol + strong → 15m
    assert predict_with_placeholder({
        "strategy": "momentum", "signal_strength": 4, "atr_5m_pct": 0.005,
    }) == "15m"
    # low vol mean-rev → 30m
    assert predict_with_placeholder({
        "strategy": "mean_reversion", "signal_strength": 3, "atr_5m_pct": 0.0005,
    }) == "30m"


# ── 9) build_lookup_table — alternative targets ────────────────────────

def test_build_lookup_max_clean_rate_picks_tf_with_highest_clean_rate():
    """In one bucket, 5m is clean 1/3 times but 30m is clean 3/3.
    max_clean_rate target must pick 30m, not 5m."""
    df = _make_train_df([
        # Three rows in same bucket, varying clean-rate per TF
        {"strategy": "momentum", "signal_strength": 4,
         "atr_5m_pct": 0.002, "entry_rsi": 50.0, "best_tf": "5m",
         "cls_5m": "CLEAN_HIT", "cls_15m": "CLEAN_HIT", "cls_30m": "CLEAN_HIT",
         "cls_60m": None, "cls_90m": None, "cls_120m": None, "cls_240m": None},
        {"strategy": "momentum", "signal_strength": 4,
         "atr_5m_pct": 0.002, "entry_rsi": 50.0, "best_tf": "30m",
         "cls_5m": "WRONG_DIRECTION", "cls_15m": "CLEAN_HIT", "cls_30m": "CLEAN_HIT",
         "cls_60m": None, "cls_90m": None, "cls_120m": None, "cls_240m": None},
        {"strategy": "momentum", "signal_strength": 4,
         "atr_5m_pct": 0.002, "entry_rsi": 50.0, "best_tf": "30m",
         "cls_5m": "NOISE", "cls_15m": "CLEAN_HIT", "cls_30m": "CLEAN_HIT",
         "cls_60m": None, "cls_90m": None, "cls_120m": None, "cls_240m": None},
    ])
    lookup = build_lookup_table(df, target="max_clean_rate")
    bucket = make_bucket(df.iloc[0].to_dict())
    # 5m: 1/3 clean = 33%; 15m: 3/3 = 100%; 30m: 3/3 = 100%
    # Tie at 100% → first one encountered in VALID_TFS order: 15m
    assert lookup[bucket] in ("15m", "30m")


def test_build_lookup_max_clean_rate_min_15m_excludes_5m():
    """Even when 5m has the highest clean-rate, the min_15m target
    excludes it from the candidate set."""
    df = _make_train_df([
        {"strategy": "momentum", "signal_strength": 4,
         "atr_5m_pct": 0.002, "entry_rsi": 50.0, "best_tf": "5m",
         "cls_5m": "CLEAN_HIT", "cls_15m": "WRONG_DIRECTION", "cls_30m": "WRONG_DIRECTION",
         "cls_60m": "WRONG_DIRECTION", "cls_90m": "WRONG_DIRECTION",
         "cls_120m": "WRONG_DIRECTION", "cls_240m": "WRONG_DIRECTION"},
    ])
    lookup = build_lookup_table(df, target="max_clean_rate_min_15m")
    bucket = make_bucket(df.iloc[0].to_dict())
    # 5m would win on raw clean-rate (100%) but is excluded
    assert lookup[bucket] != "5m"
    assert lookup[bucket] in VALID_TFS_NON_5M


def test_build_lookup_unknown_target_raises():
    df = _make_train_df([
        {"strategy": "momentum", "signal_strength": 4,
         "atr_5m_pct": 0.002, "entry_rsi": 50.0, "best_tf": "30m"},
    ])
    import pytest
    with pytest.raises(ValueError, match="unknown target"):
        build_lookup_table(df, target="garbage")


VALID_TFS_NON_5M = ("15m", "30m", "60m", "90m", "120m", "240m")
