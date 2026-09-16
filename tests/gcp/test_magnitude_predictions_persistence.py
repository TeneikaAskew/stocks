"""Per-bar predictions: where they live and where they must not.

magnitude_per_bar_predictions is written by the live inference job only.
The walk-forward harness keeps its per-bar predictions in the GCS CSV
(gates 5-7 read it) and never writes them to Cloud SQL: the copy would
be ~140k unread rows per cell per phase0 run, with no reader (every live
read and the auditor filter to source='inference') and no retention, and
each run's history would sit in the auditor's scan window (Codex P2 on
#1117). Its write had in fact never succeeded (SQLSTATE 42804 on every
6hp7l cell, ts bound as VARCHAR). These tests pin the DDL the inference
job applies and the absence of the harness write.
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
    """source column: 'inference' on every row; live reads filter on it."""
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


def test_the_summary_json_never_carries_the_per_bar_predictions():
    """The pop must still happen before the summary is serialised -- moving
    it later must not reintroduce the bloat it exists to prevent."""
    import inspect
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    src = inspect.getsource(mwf.walk_forward)
    pop_at = src.index('f.pop("_predictions"')
    dump_at = src.index("json.dumps(summary")
    assert pop_at < dump_at, (
        "the summary JSON would be serialised with _predictions still "
        "attached to every fold")


def test_the_harness_never_writes_per_bar_rows_to_cloud_sql():
    """The per-bar CSV in GCS is the harness's evidence; the SQL table is
    the inference job's. A write here is ~140k unread rows per cell per run
    and a scan-window tax on the auditor (Codex P2 on #1117)."""
    import inspect
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    src = inspect.getsource(mwf)
    assert "_persist_predictions_table" not in src
    assert 'to_sql("magnitude_per_bar_predictions"' not in src
    assert "INSERT INTO magnitude_per_bar_predictions" not in src
    wf = inspect.getsource(mwf.walk_forward)
    assert "predictions_{run_id}.csv" in wf          # the CSV is still written
    assert "execute_sql(PREDICTIONS_DDL" not in wf   # and the table is inference's to create


def test_the_inference_job_owns_the_predictions_table_ddl():
    import inspect
    from gcp.research.magnitude_engine import mag_inference as mi
    src = inspect.getsource(mi)
    assert "PREDICTIONS_DDL_CREATE" in src and "PREDICTIONS_DDL_INDEX" in src
