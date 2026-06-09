"""Phase C regression tests for platform/api/routers/magnitude.py.

Pins the no-silent-fallback contract (CLAUDE.md §3.7):
  - 404 when no row exists for the requested (ticker, tf) or (ticker, tf, ts)
  - NEVER fabricates a uniform {0.25, 0.25, 0.25, 0.25} distribution
  - Embeds the gate-7 caveat in every successful response

Also pins basic route shape and that the gate-7 guidance text is
present so a future refactor can't silently drop the consumer warning.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Match the import path the production app uses: platform/api/main.py
# does `sys.path.insert(PROJECT_ROOT)` and then `from api.routers
# import …`, not `from platform.api.routers import …`. Python's stdlib
# `platform` module shadows the directory name, so a top-level
# `import platform.api` raises 'platform is not a package'. CI caught
# this on PR #597 first push of the router tests.
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "platform"))

# router imports gcp.database.query_to_dataframe which itself imports
# the Cloud SQL connector. Only stub when the real package is missing
# (setdefault would poison sys.modules for sibling tests).
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
    "google.cloud.sql.connector",
    "pg8000.dbapi",
])


# Skip the whole module if fastapi isn't installed (sandbox parity with
# tests/test_routers_insights_admin.py).
try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    pytest.skip("fastapi not installed", allow_module_level=True)


def _app_with_router():
    from fastapi import FastAPI
    from api.routers import magnitude as mag_router  # noqa: E402
    app = FastAPI()
    app.include_router(mag_router.router)
    return app, mag_router


# ──────────────────── /latest ────────────────────

def test_latest_returns_prediction_when_row_exists():
    app, mod = _app_with_router()
    fake_row = pd.DataFrame([{
        "ticker": "IWM", "tf": "5m",
        "ts": pd.Timestamp("2026-06-02 13:30:00", tz="UTC"),
        "p_tight": 0.1, "p_normal": 0.3, "p_expanded": 0.5,
        "p_explosive": 0.1,
        "pred_bucket": 2, "max_proba": 0.5,
        "model_version": "v1-2026-06-01",
        "source": "inference",
        "computed_at": pd.Timestamp("2026-06-02 13:25:00", tz="UTC"),
    }])
    with patch.object(mod, "query_to_dataframe", return_value=fake_row):
        client = TestClient(app)
        r = client.get("/api/magnitude/IWM/5m/latest")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ticker"] == "IWM"
    assert data["pred_bucket"] == 2
    assert data["pred_bucket_label"] == "EXPANDED"
    assert data["probabilities"]["p_explosive"] == 0.1


def test_latest_404_when_no_row_exists():
    app, mod = _app_with_router()
    with patch.object(mod, "query_to_dataframe", return_value=pd.DataFrame()):
        client = TestClient(app)
        r = client.get("/api/magnitude/IWM/5m/latest")
    assert r.status_code == 404
    body = r.json()
    # Diagnostic detail must NOT contain anything that looks like a
    # uniform distribution masquerading as a real prediction.
    assert "0.25" not in str(body)


def test_latest_carries_gate7_caveat_in_response():
    app, mod = _app_with_router()
    fake_row = pd.DataFrame([{
        "ticker": "IWM", "tf": "5m",
        "ts": pd.Timestamp("2026-06-02 13:30:00", tz="UTC"),
        "p_tight": 0.25, "p_normal": 0.25, "p_expanded": 0.25,
        "p_explosive": 0.25,
        "pred_bucket": 0, "max_proba": 0.25,
        "model_version": "v1",
        "source": "inference",
        "computed_at": pd.Timestamp("2026-06-02 13:25:00", tz="UTC"),
    }])
    with patch.object(mod, "query_to_dataframe", return_value=fake_row):
        client = TestClient(app)
        r = client.get("/api/magnitude/IWM/5m/latest")
    data = r.json()
    # Gate-7 fingerprint terms — a refactor that drops the warning will
    # fail one of these.
    assert "gate-7" in data["usage_guidance"].lower() or \
           "gate7" in data["usage_guidance"].lower() or \
           "ratio < 1.25" in data["usage_guidance"]
    assert "directional" in str(data["not_for"]).lower()
    assert data["docs_ref"].endswith("RESULTS.md")


# ──────────────────── /at/{ts} ────────────────────

def test_at_ts_404_when_specific_bar_missing():
    """No silent-fallback to uniform: 404 means 'no prediction', not
    'pretend it was 25% each'."""
    app, mod = _app_with_router()
    with patch.object(mod, "query_to_dataframe", return_value=pd.DataFrame()):
        client = TestClient(app)
        r = client.get("/api/magnitude/IWM/5m/at/2026-06-02T13:30:00")
    assert r.status_code == 404


def test_at_ts_returns_specific_bar():
    app, mod = _app_with_router()
    fake_row = pd.DataFrame([{
        "ticker": "SPY", "tf": "5m",
        "ts": pd.Timestamp("2026-06-02 14:00:00", tz="UTC"),
        "p_tight": 0.05, "p_normal": 0.10, "p_expanded": 0.20,
        "p_explosive": 0.65,
        "pred_bucket": 3, "max_proba": 0.65,
        "model_version": "v1",
        "source": "inference",
        "computed_at": pd.Timestamp("2026-06-02 13:55:00", tz="UTC"),
    }])
    with patch.object(mod, "query_to_dataframe", return_value=fake_row):
        client = TestClient(app)
        r = client.get("/api/magnitude/SPY/5m/at/2026-06-02T14:00:00")
    assert r.status_code == 200
    assert r.json()["pred_bucket_label"] == "EXPLOSIVE"


# ──────────────────── input validation ────────────────────

def test_invalid_tf_rejected_at_path():
    """tf pattern is r'^[0-9]+[mhd]$' — 'invalid' must 422 not 500."""
    app, _ = _app_with_router()
    client = TestClient(app)
    r = client.get("/api/magnitude/IWM/invalid/latest")
    assert r.status_code == 422


def test_invalid_ticker_rejected_at_path():
    """Ticker pattern excludes lowercase/special chars beyond .-"""
    app, _ = _app_with_router()
    client = TestClient(app)
    r = client.get("/api/magnitude/iwm!/5m/latest")
    assert r.status_code == 422


def test_no_silent_uniform_fallback_in_module_constants():
    """Regression guard: the module must NOT define a uniform-distribution
    fallback. A future 'helpful' refactor that adds e.g.
    `_UNIFORM_FALLBACK = (0.25,)*4` is exactly what §3.7 forbids."""
    from api.routers import magnitude as mod
    import inspect
    src = inspect.getsource(mod)
    # No literal uniform distribution in the source.
    assert "0.25, 0.25, 0.25, 0.25" not in src
    # The 'usage_guidance' constant must mention gate-7 / non-directional
    # to keep the consumer warning intact.
    assert "non-directional" in src.lower()


def test_latest_uses_computed_at_tiebreaker():
    """Codex P2 regression guard on PR #597: PRIMARY KEY allows multiple
    model_version rows per (ticker, tf, ts). /latest must order by
    (ts DESC, computed_at DESC) so a fresher inference row beats a stale
    walk_forward backfill at the same ts. Without the tiebreaker
    Postgres returns an arbitrary row from the tie."""
    from api.routers import magnitude as mod
    import inspect
    src = inspect.getsource(mod.get_latest_prediction)
    # The ORDER BY must include computed_at DESC as a tiebreaker.
    assert "computed_at DESC" in src, (
        "/latest must tie-break by computed_at; otherwise stale "
        "walk_forward rows can beat fresh inference rows"
    )
