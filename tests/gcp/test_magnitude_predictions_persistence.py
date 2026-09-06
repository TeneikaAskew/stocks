"""Phase A regression tests: per-bar predictions persistence.

Pins the contract of magnitude_per_bar_predictions persistence wired
into mag_walk_forward.

We mock the SQLAlchemy engine so we don't need a live Cloud SQL —
focus is on the row-shape + filtering contract.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# mag_walk_forward imports google-cloud-storage, sklearn, lightgbm at
# module load. All three are in requirements.txt (CI installs them) but
# not in the offline sandbox. We only stub when the real package is
# unavailable — using setdefault() at module load poisons the shared
# sys.modules cache for sibling tests (e.g. test_combo_mining does
# `from sklearn.ensemble import RandomForestClassifier`, which fails
# with "'sklearn' is not a package" if our MagicMock was inserted
# first). Caught 2026-06-09 by the CI failure on PR #597.
# We TRACK what we stub and evict it in a module-scoped teardown (below) so
# the mocks don't leak into sibling tests that need the REAL lightgbm/sklearn.
_STUBBED_BY_THIS_MODULE: list[str] = []


def _stub_missing_modules(mods: list[str]) -> None:
    for m in mods:
        try:
            __import__(m)
        except ImportError:
            # Walk parents so child stubs find non-package parents.
            parts = m.split(".")
            for i in range(1, len(parts) + 1):
                key = ".".join(parts[:i])
                if key not in sys.modules:
                    sys.modules[key] = MagicMock()
                    _STUBBED_BY_THIS_MODULE.append(key)


_stub_missing_modules([
    "google.cloud.storage",
    "sklearn.calibration",
    "sklearn.metrics",
    "lightgbm",
])
# If we just stubbed sklearn.metrics, give it a callable log_loss so
# mag_walk_forward's `from sklearn.metrics import log_loss` succeeds.
if isinstance(sys.modules.get("sklearn.metrics"), MagicMock):
    sys.modules["sklearn.metrics"].log_loss = lambda *a, **k: 0.5
if isinstance(sys.modules.get("sklearn.calibration"), MagicMock):
    sys.modules["sklearn.calibration"].CalibratedClassifierCV = MagicMock


@pytest.fixture(scope="module", autouse=True)
def _restore_stubbed_modules():
    """Evict the MagicMock import-stubs this module inserted so they don't
    leak into sibling test modules. Only pops keys that are still OUR mock —
    never evicts a real module that got imported later."""
    yield
    for key in _STUBBED_BY_THIS_MODULE:
        if isinstance(sys.modules.get(key), MagicMock):
            sys.modules.pop(key, None)
    _STUBBED_BY_THIS_MODULE.clear()


@pytest.fixture
def fake_folds():
    """Two folds, each with 3 per-bar predictions in the documented
    tuple shape."""
    fold_a_preds = [
        # (fold_label, ts_str, true_idx, pred_idx, max_proba,
        #  p_TIGHT, p_NORMAL, p_EXPANDED, p_EXPLOSIVE)
        ("2022..2023", "2022-01-03 14:30:00+00:00", 1, 2, 0.55,
         0.10, 0.30, 0.55, 0.05),
        ("2022..2023", "2022-01-03 14:35:00+00:00", 0, 0, 0.62,
         0.62, 0.30, 0.05, 0.03),
        ("2022..2023", "2022-01-03 14:40:00+00:00", 3, 3, 0.71,
         0.05, 0.10, 0.14, 0.71),
    ]
    fold_b_preds = [
        ("2023..2024", "2023-01-03 14:30:00+00:00", 1, 1, 0.48,
         0.20, 0.48, 0.27, 0.05),
    ]
    return [
        {"fold": "2022..2023", "_predictions": fold_a_preds,
         "predictions_columns": ["fold", "ts", "true_bucket_idx",
                                  "pred_bucket_idx", "max_proba",
                                  "p_TIGHT", "p_NORMAL",
                                  "p_EXPANDED", "p_EXPLOSIVE"]},
        {"fold": "2023..2024", "_predictions": fold_b_preds,
         "predictions_columns": ["fold", "ts", "true_bucket_idx",
                                  "pred_bucket_idx", "max_proba",
                                  "p_TIGHT", "p_NORMAL",
                                  "p_EXPANDED", "p_EXPLOSIVE"]},
    ]


def _capture_to_sql():
    """Return a (mock_engine, captured_dfs) tuple where every df.to_sql
    call's data is appended to captured_dfs."""
    captured: list[pd.DataFrame] = []
    mock_conn = MagicMock()
    mock_engine = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn

    original_to_sql = pd.DataFrame.to_sql
    def fake_to_sql(self, name, con, *args, **kw):
        if name == "magnitude_per_bar_predictions":
            captured.append(self.copy())
    with patch.object(pd.DataFrame, "to_sql", fake_to_sql):
        yield mock_engine, captured


@pytest.fixture
def engine_and_capture():
    """Yield (mock_engine, list_to_be_filled_with_to_sql_dataframes)."""
    gen = _capture_to_sql()
    yield next(gen)


# ──────────────────── persistence shape ────────────────────

def test_predictions_persisted_with_expected_schema(fake_folds,
                                                    engine_and_capture):
    """Verify each persisted row carries the expected per-bar columns."""
    mock_engine, captured = engine_and_capture
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    mwf._persist_predictions_table(mock_engine, "IWM", "5m",
                                    fake_folds, run_id="test-run-1")

    assert len(captured) == 1, "to_sql should be called exactly once"
    df = captured[0]
    assert len(df) == 4, "3 + 1 per-bar rows from 2 folds"
    required = {
        "ticker", "tf", "ts",
        "p_tight", "p_normal", "p_expanded", "p_explosive",
        "pred_bucket", "max_proba",
        "model_version", "fold_label", "source",
    }
    assert required.issubset(df.columns), \
        f"missing columns: {required - set(df.columns)}"


def test_predictions_carry_run_id_as_model_version(fake_folds,
                                                   engine_and_capture):
    """model_version must equal run_id so a later run with a different
    model can coexist with the original."""
    mock_engine, captured = engine_and_capture
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    mwf._persist_predictions_table(mock_engine, "IWM", "5m",
                                    fake_folds, run_id="2026-06-02-IWM-5m-v1")

    df = captured[0]
    assert (df["model_version"] == "2026-06-02-IWM-5m-v1").all()


def test_predictions_source_is_walk_forward(fake_folds, engine_and_capture):
    """Walk-forward-emitted rows must be tagged source='walk_forward' so
    Phase B's live-inference rows can be distinguished."""
    mock_engine, captured = engine_and_capture
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    mwf._persist_predictions_table(mock_engine, "IWM", "5m",
                                    fake_folds, run_id="test-run")
    df = captured[0]
    assert (df["source"] == "walk_forward").all()


def test_predictions_probabilities_match_input_tuples(fake_folds,
                                                      engine_and_capture):
    """Verify the unpacking from the tuple shape into columns is correct
    — the 3rd row of fold A is the EXPLOSIVE example (p_explosive=0.71)."""
    mock_engine, captured = engine_and_capture
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    mwf._persist_predictions_table(mock_engine, "IWM", "5m",
                                    fake_folds, run_id="t")
    df = captured[0]
    row = df[df["ts"] == "2022-01-03 14:40:00+00:00"].iloc[0]
    assert row["p_explosive"] == 0.71
    assert row["p_tight"] == 0.05
    assert row["pred_bucket"] == 3
    assert row["max_proba"] == 0.71


def test_predictions_drops_no_predictions_folds(engine_and_capture):
    """Folds without `_predictions` (e.g. SKIP_THIN) are silently skipped,
    not raising or producing junk rows."""
    folds = [
        {"fold": "skipped", "_predictions": None},
        {"fold": "empty", "_predictions": []},
        {"fold": "ok", "_predictions": [
            ("ok", "2024-01-01 14:30:00", 0, 0, 0.55,
             0.55, 0.30, 0.10, 0.05)
        ]},
    ]
    mock_engine, captured = engine_and_capture
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    mwf._persist_predictions_table(mock_engine, "IWM", "5m", folds,
                                    run_id="t")
    assert len(captured) == 1
    assert len(captured[0]) == 1


def test_no_predictions_no_insert(engine_and_capture):
    """If no fold has any predictions, skip the INSERT entirely (don't
    open a tx just to do nothing)."""
    mock_engine, captured = engine_and_capture
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    mwf._persist_predictions_table(mock_engine, "IWM", "5m",
                                    [{"fold": "a", "_predictions": []}],
                                    run_id="t")
    assert len(captured) == 0
    # begin() shouldn't be called either
    mock_engine.begin.assert_not_called()


# ──────────────────── DDL contract ────────────────────

def test_predictions_ddl_contains_primary_key():
    """PK on (ticker, tf, ts, model_version) is load-bearing — it allows
    multiple model versions for the same bar without overwriting each
    other. A regression that drops model_version from the PK would
    silently overwrite rows on re-run."""
    from gcp.research.magnitude_engine.mag_walk_forward import (
        PREDICTIONS_DDL_CREATE,
    )
    assert "PRIMARY KEY (ticker, tf, ts, model_version)" in PREDICTIONS_DDL_CREATE


def test_predictions_ddl_has_source_column():
    """source column distinguishes walk_forward vs inference rows."""
    from gcp.research.magnitude_engine.mag_walk_forward import (
        PREDICTIONS_DDL_CREATE,
    )
    assert "source" in PREDICTIONS_DDL_CREATE
    assert "VARCHAR(16)" in PREDICTIONS_DDL_CREATE


def test_predictions_ddl_index_exists():
    """A descending-ts index is needed for 'latest prediction for ticker'
    queries from the API surface."""
    from gcp.research.magnitude_engine.mag_walk_forward import (
        PREDICTIONS_DDL_INDEX,
    )
    assert "magnitude_per_bar_predictions" in PREDICTIONS_DDL_INDEX
    assert "ts DESC" in PREDICTIONS_DDL_INDEX
