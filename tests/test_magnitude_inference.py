"""Phase B regression tests for gcp/research/magnitude_engine/mag_inference.py.

The job has three failure modes that MUST surface as exit 1 (CLAUDE.md
§3.7 no silent fallback):

1. Model artifact missing in GCS -> RuntimeError that propagates
2. Feature column drift between training schema and live features
3. Zero-output (model returned wrong shape, all bars dropped to NaN
   filter, etc.) -> reported but not silently treated as success

Tests use the same import-stub pattern as Phase A.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Same lightweight stubs as Phase A. Only insert when the real package
# is unavailable; setdefault() poisons sys.modules for sibling tests
# (caught 2026-06-09 in PR #597 CI). See test_magnitude_predictions_
# persistence.py for the full rationale.
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


# ──────────────────── _parse_cells ────────────────────

def test_parse_cells_default_when_empty():
    from gcp.research.magnitude_engine.mag_inference import (
        _parse_cells, DEFAULT_CELLS,
    )
    assert _parse_cells(None) == list(DEFAULT_CELLS)
    assert _parse_cells("") == list(DEFAULT_CELLS)
    assert _parse_cells("   ") == list(DEFAULT_CELLS)


def test_parse_cells_one():
    from gcp.research.magnitude_engine.mag_inference import _parse_cells
    assert _parse_cells("IWM:5m") == [("IWM", "5m")]


def test_parse_cells_many_with_whitespace():
    from gcp.research.magnitude_engine.mag_inference import _parse_cells
    assert _parse_cells(" iwm:5m , SPY:15m ") == [
        ("IWM", "5m"), ("SPY", "15m"),
    ]


def test_parse_cells_invalid_raises():
    from gcp.research.magnitude_engine.mag_inference import _parse_cells
    with pytest.raises(ValueError):
        _parse_cells("IWM")  # missing :tf


# ──────────────────── _score_and_persist contract ────────────────────

@pytest.fixture
def fake_features():
    """3 rows with 4 features; matches what a 5m intraday slice looks like."""
    return pd.DataFrame({
        "ts": pd.date_range("2026-06-02 13:25", periods=3,
                            freq="5min", tz="UTC"),
        "rsi_14": [55.0, 60.0, 65.0],
        "atr_14": [1.0, 1.2, 1.5],
        "ema_9":  [100.0, 100.5, 101.0],
        "vwap":   [99.5, 100.0, 100.5],
    })


def _fake_model(probs):
    """Build a mock model whose predict_proba returns the given probs."""
    m = MagicMock()
    m.predict_proba.return_value = np.array(probs)
    return m


def test_score_and_persist_returns_zero_on_empty_features():
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist
    engine = MagicMock()
    n = _score_and_persist(engine, "IWM", "5m",
                            _fake_model([]), ["rsi_14"], "v1",
                            pd.DataFrame())
    assert n == 0
    engine.begin.assert_not_called()


def test_score_and_persist_raises_on_feature_drift(fake_features):
    """If the model was trained on a column that's no longer in
    `features`, fail loud — don't silently fabricate."""
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist
    engine = MagicMock()
    # Model expects 'gone_feature' which fake_features doesn't have.
    with pytest.raises(RuntimeError, match="feature drift"):
        _score_and_persist(engine, "IWM", "5m",
                            _fake_model([[0.25] * 4] * 3),
                            ["rsi_14", "atr_14", "gone_feature"],
                            "v1", fake_features)


def test_score_and_persist_raises_on_wrong_class_count(fake_features):
    """Model returning N != 4 classes is a contract violation — must
    raise so we don't insert garbage."""
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist
    engine = MagicMock()
    # Model returns 3-class output instead of 4.
    bad_model = _fake_model([[0.33, 0.34, 0.33]] * 3)
    feature_cols = ["rsi_14", "atr_14", "ema_9", "vwap"]
    with pytest.raises(RuntimeError, match="expected 4"):
        _score_and_persist(engine, "IWM", "5m",
                            bad_model, feature_cols, "v1", fake_features)


def test_score_and_persist_skips_nan_rows(fake_features):
    """Rows with any-NaN features are filtered out before scoring (model
    can't handle them); the count is logged but doesn't fail the job."""
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist

    # Inject a NaN into one feature row.
    fake_features.loc[1, "rsi_14"] = np.nan

    # Model expects to be called with only the surviving rows (2 of 3).
    proba = np.array([[0.1, 0.2, 0.3, 0.4]] * 2)
    model = MagicMock()
    model.predict_proba.return_value = proba

    engine = MagicMock()
    feature_cols = ["rsi_14", "atr_14", "ema_9", "vwap"]
    n = _score_and_persist(engine, "IWM", "5m",
                            model, feature_cols, "v1", fake_features)
    # 2 surviving bars persisted.
    assert n == 2
    # Model was called with 2 rows (not 3).
    args, _ = model.predict_proba.call_args
    assert args[0].shape == (2, 4)


def test_score_and_persist_zero_after_nan_filter(fake_features):
    """If EVERY bar has NaN features, return 0 cleanly — don't crash on
    empty input to model.predict_proba."""
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist
    fake_features["rsi_14"] = np.nan
    model = MagicMock()
    engine = MagicMock()
    n = _score_and_persist(engine, "IWM", "5m",
                            model, ["rsi_14"], "v1", fake_features)
    assert n == 0
    model.predict_proba.assert_not_called()


# ──────────────────── main() exit-disposition contract ────────────────────
#
# Codex P1 on PR #597: when every cell quietly returns 0 (data outage,
# universal NaN filter), the cell loop has no failures but
# total_written == 0. That was making a real outage look like a healthy
# scheduled run. main() must exit 1 in that case.

def test_main_exits_1_when_total_written_is_zero(monkeypatch):
    """Zero-output across all cells -> exit 1 (regression guard for
    Codex P1 finding on PR #597)."""
    monkeypatch.setenv("INFERENCE_CELLS", "IWM:5m,SPY:5m")
    from gcp.research.magnitude_engine import mag_inference as mod

    # Every cell returns 0 from _score_and_persist (e.g. empty features
    # window). No exceptions raised -> failures stays []. Pre-fix this
    # path returned 0; we now require exit 1.
    fake_engine = MagicMock()
    with patch("sys.argv", ["mag_inference"]), \
         patch.object(mod, "get_engine", return_value=fake_engine), \
         patch.object(mod, "_load_model_and_version",
                       return_value=(MagicMock(), ["rsi_14"], "v1")), \
         patch.object(mod, "_load_recent_features",
                       return_value=pd.DataFrame()), \
         patch.object(mod, "_score_and_persist", return_value=0):
        rc = mod.main()
    assert rc == 1, "zero predictions across all cells must exit 1"


def test_main_exits_0_when_some_predictions_written(monkeypatch):
    """Happy path: at least one cell produced predictions -> exit 0."""
    monkeypatch.setenv("INFERENCE_CELLS", "IWM:5m,SPY:5m")
    from gcp.research.magnitude_engine import mag_inference as mod

    with patch("sys.argv", ["mag_inference"]), \
         patch.object(mod, "get_engine", return_value=MagicMock()), \
         patch.object(mod, "_load_model_and_version",
                       return_value=(MagicMock(), ["rsi_14"], "v1")), \
         patch.object(mod, "_load_recent_features",
                       return_value=pd.DataFrame()), \
         patch.object(mod, "_score_and_persist", side_effect=[5, 7]):
        rc = mod.main()
    assert rc == 0


def test_main_exits_1_when_majority_cells_fail(monkeypatch):
    """Existing 50% threshold preserved — operator gets paged when most
    cells raise."""
    monkeypatch.setenv("INFERENCE_CELLS", "IWM:5m,SPY:5m,QQQ:5m")
    from gcp.research.magnitude_engine import mag_inference as mod

    def fake_load(ticker, tf):
        if ticker in ("IWM", "SPY"):
            raise FileNotFoundError(f"missing model for {ticker}:{tf}")
        return (MagicMock(), ["rsi_14"], "v1")

    with patch("sys.argv", ["mag_inference"]), \
         patch.object(mod, "get_engine", return_value=MagicMock()), \
         patch.object(mod, "_load_model_and_version", side_effect=fake_load), \
         patch.object(mod, "_load_recent_features",
                       return_value=pd.DataFrame()), \
         patch.object(mod, "_score_and_persist", return_value=5):
        rc = mod.main()
    # 2/3 cells failed -> >50% threshold -> exit 1
    assert rc == 1


# ─────────── _load_recent_features train/inference parity ───────────
#
# Root cause of the 2026-06-19 outage (13/13 executions failed): inference
# SELECTed from strat_features_<tf> ONLY, while TRAINING joins the
# strat_features_levels_<tf> companion table that carries the ORB / level
# columns (orb_5m_high, orb_5m_broke_high, …). The model's feature_cols
# therefore referenced columns inference never loaded, so _score_and_persist
# raised "feature drift" on every cell. These tests guard the join so the
# train/inference skew can't silently return when someone adds a level
# column and retrains. (CLAUDE.md §0.3 — assert the I/O shape.)

def test_load_recent_features_joins_levels_table():
    """Inference MUST LEFT JOIN strat_features_levels_<tf> so the model's
    ORB / level columns are present — mirrors strat_dataset's
    load_labeled_dataset(include_levels=True) path."""
    from gcp.research.magnitude_engine import mag_inference as mod
    captured = {}

    def fake_q(sql):
        captured["sql"] = sql
        return pd.DataFrame({"ts": [], "ticker": []})

    with patch.object(mod, "query_to_dataframe_strict", side_effect=fake_q):
        mod._load_recent_features("IWM", "5m")

    sql = captured["sql"].lower()
    assert "strat_features_levels_5m" in sql, \
        "inference must join the levels table that carries the ORB columns"
    assert "left join" in sql
    assert "l.ticker = s.ticker" in sql and "l.ts = s.ts" in sql
    assert "_has_levels" in sql, \
        "must mark rows lacking a levels match so they can be skipped"


def test_load_recent_features_dedupes_join_key_columns():
    """SELECT s.*, l.* duplicates ticker/ts; the loader must drop the
    duplicate labels so downstream featurize() sees a clean frame."""
    from gcp.research.magnitude_engine import mag_inference as mod

    # Frame as returned by `SELECT s.*, l.*` — duplicate 'ticker' and 'ts'.
    dup = pd.DataFrame(
        [["IWM", 1, 10.0, "IWM", 1],
         ["IWM", 2, 11.0, "IWM", 2]],
        columns=["ticker", "ts", "orb_5m_high", "ticker", "ts"],
    )
    with patch.object(mod, "query_to_dataframe_strict", return_value=dup):
        out = mod._load_recent_features("IWM", "5m")

    assert list(out.columns).count("ticker") == 1
    assert list(out.columns).count("ts") == 1
    assert "orb_5m_high" in out.columns


def test_load_recent_features_skips_bars_without_levels_row():
    """A bar present in strat_features_<tf> but missing from the levels
    companion table comes back with _has_levels=False (LEFT JOIN miss). It
    MUST be dropped — scoring it would feed the model NULL->0 ORB/level
    features (fabricated). Refuse, don't fabricate (CLAUDE.md §3.7)."""
    from gcp.research.magnitude_engine import mag_inference as mod

    # Row 0 has a matching levels row; row 1 does not (_has_levels=False).
    df = pd.DataFrame({
        "ts": [1, 2],
        "ticker": ["IWM", "IWM"],
        "orb_5m_high": [10.0, None],
        "_has_levels": [True, False],
    })
    with patch.object(mod, "query_to_dataframe_strict", return_value=df):
        out = mod._load_recent_features("IWM", "5m")

    assert len(out) == 1, "bar without a levels row must be skipped"
    assert int(out.iloc[0]["ts"]) == 1
    assert "_has_levels" not in out.columns, "marker column must be dropped"


def test_load_recent_features_uses_strict_query_helper():
    """Must use query_to_dataframe_strict (raises) not query_to_dataframe
    (which swallows errors into an empty frame). A missing levels table /
    DB error has to fail LOUD, not masquerade as 'no recent bars' — the P2
    finding on PR #631 (CLAUDE.md §3.7)."""
    from gcp.research.magnitude_engine import mag_inference as mod
    with patch.object(mod, "query_to_dataframe_strict",
                      side_effect=RuntimeError("relation does not exist")):
        with pytest.raises(RuntimeError):
            mod._load_recent_features("IWM", "5m")
