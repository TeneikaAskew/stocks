"""Tests for `POST /api/admin/strat-engine/structure-continuation` — the
Phase 1 feature-flagged, read-only structure-continuation endpoint.

What this asserts (the Phase 1 acceptance criteria):
  (a) the continuation field appears ONLY when the feature flag is ON;
      with the flag OFF the endpoint 404s (the field does not exist).
  (b) only 5m / 15m are exposed — 30m is rejected (calibration not cleared).
  (c) the scope disclaimer is present in the response envelope.
  (d) when the model is unavailable / muted / has no anchorable current type
      the response is an explicit UNAVAILABLE envelope with a NULL
      continuation_prob — NEVER a fabricated number (CLAUDE.md Rule 3.7).

The underlying model load + Cloud SQL feature fetch is patched out so the
test runs hermetically without GCS or Cloud SQL credentials.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "platform" / "api"))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import admin as admin_router
    import gcp.research.strat_engine.strat_pred_serve  # noqa: F401
    import gcp.database  # noqa: F401
except ModuleNotFoundError as exc:  # pragma: no cover
    pytest.skip(f"admin router unavailable: {exc}", allow_module_level=True)


SCOPE_STATEMENT = (
    "Calibrated structure prediction. Not a directional or P&L edge. "
    "Use with discretion."
)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(admin_router.router)
    return app


def _stub_predict_response(
    *,
    available: bool = True,
    muted: bool = False,
    current_type: str | None = "2U",
    continuation_prob: float | None = 0.58,
    ticker: str = "IWM",
    timeframe: str = "15m",
) -> dict:
    """Build the exact dict shape `predict_one` produces, for stubbing."""
    if not available:
        return {
            "ticker": ticker,
            "timeframe": timeframe,
            "available": False,
            "top_class": None,
            "top_prob": None,
            "class_probs": {},
            "current_type": None,
            "continuation_prob": None,
            "model_version": None,
            "last_train_date": None,
            "live_ece": None,
            "muted": False,
            "mute_reason": None,
            "scope_statement": SCOPE_STATEMENT,
            "ts": None,
            "note": "No model.pkl found — dispatch the Cloud Run Job first.",
        }
    if muted:
        return {
            "ticker": ticker,
            "timeframe": timeframe,
            "available": True,
            "top_class": None,
            "top_prob": None,
            "class_probs": {},
            "current_type": current_type,
            "continuation_prob": None,
            "model_version": "epoch-1779781975",
            "last_train_date": "2026-05-26T07:52:55+00:00",
            "live_ece": 0.073,
            "muted": True,
            "mute_reason": "model muted, ECE breach (live ECE 0.073 > ceiling 0.050)",
            "scope_statement": SCOPE_STATEMENT,
            "ts": None,
            "note": None,
        }
    cp = {"1": 0.12, "2U": 0.20, "2D": 0.20, "3": 0.10}
    if current_type is not None and continuation_prob is not None:
        cp[current_type] = continuation_prob
    return {
        "ticker": ticker,
        "timeframe": timeframe,
        "available": True,
        "top_class": current_type,
        "top_prob": continuation_prob,
        "class_probs": cp,
        "current_type": current_type,
        "continuation_prob": continuation_prob,
        "model_version": "epoch-1779781975",
        "last_train_date": "2026-05-26T07:52:55+00:00",
        "live_ece": 0.023,
        "muted": False,
        "mute_reason": None,
        "scope_statement": SCOPE_STATEMENT,
        "ts": "2026-05-22T19:30:00+00:00",
        "note": None,
    }


def _post(client, *, ticker="IWM", tf="15m", token="secret-token"):
    return client.post(
        "/api/admin/strat-engine/structure-continuation",
        json={"ticker": ticker, "timeframe": tf},
        headers={"X-Admin-Token": token},
    )


# ─── (a) Feature flag gates the field's existence ───────────────────────────


def test_flag_off_returns_404(monkeypatch):
    """Flag OFF (default) → endpoint behaves as if it doesn't exist."""
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    monkeypatch.delenv("STRUCTURE_CONTINUATION_ENABLED", raising=False)
    stub = _stub_predict_response()
    with patch("gcp.research.strat_engine.strat_pred_serve.predict_one",
               return_value=stub), \
         patch("gcp.database.get_engine", return_value=None):
        client = TestClient(_build_app())
        r = _post(client)
    assert r.status_code == 404


def test_flag_explicitly_false_returns_404(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("STRUCTURE_CONTINUATION_ENABLED", "false")
    with patch("gcp.research.strat_engine.strat_pred_serve.predict_one",
               return_value=_stub_predict_response()), \
         patch("gcp.database.get_engine", return_value=None):
        client = TestClient(_build_app())
        r = _post(client)
    assert r.status_code == 404


def test_flag_on_returns_continuation_prob(monkeypatch):
    """Flag ON → the continuation probability field appears."""
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("STRUCTURE_CONTINUATION_ENABLED", "true")
    stub = _stub_predict_response(current_type="2U", continuation_prob=0.58)
    with patch("gcp.research.strat_engine.strat_pred_serve.predict_one",
               return_value=stub), \
         patch("gcp.database.get_engine", return_value=None):
        client = TestClient(_build_app())
        r = _post(client, ticker="IWM", tf="15m")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "OK"
    assert data["current_type"] == "2U"
    assert data["continuation_prob"] == pytest.approx(0.58)
    assert 0.0 <= data["continuation_prob"] <= 1.0


# ─── (b) Only 5m / 15m exposed — 30m rejected ───────────────────────────────


@pytest.mark.parametrize("tf", ["5m", "15m"])
def test_allowed_timeframes(monkeypatch, tf):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("STRUCTURE_CONTINUATION_ENABLED", "1")
    stub = _stub_predict_response(timeframe=tf)
    with patch("gcp.research.strat_engine.strat_pred_serve.predict_one",
               return_value=stub), \
         patch("gcp.database.get_engine", return_value=None):
        client = TestClient(_build_app())
        r = _post(client, tf=tf)
    assert r.status_code == 200, r.text


def test_30m_is_rejected(monkeypatch):
    """30m is NOT cleared — must be rejected even with the flag ON."""
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("STRUCTURE_CONTINUATION_ENABLED", "on")
    with patch("gcp.research.strat_engine.strat_pred_serve.predict_one",
               return_value=_stub_predict_response()), \
         patch("gcp.database.get_engine", return_value=None):
        client = TestClient(_build_app())
        r = _post(client, tf="30m")
    assert r.status_code == 400
    assert "30m is not exposed" in r.text


def test_unknown_ticker_rejected(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("STRUCTURE_CONTINUATION_ENABLED", "on")
    with patch("gcp.research.strat_engine.strat_pred_serve.predict_one",
               return_value=_stub_predict_response()), \
         patch("gcp.database.get_engine", return_value=None):
        client = TestClient(_build_app())
        r = _post(client, ticker="TSLA")
    assert r.status_code == 400
    assert "ticker must be one of" in r.text


def test_30m_never_exposed_constant():
    """Belt-and-suspenders: the exposed-TF tuple must not contain 30m."""
    assert "30m" not in admin_router.STRUCTURE_CONTINUATION_TFS
    assert set(admin_router.STRUCTURE_CONTINUATION_TFS) == {"5m", "15m"}


# ─── (c) Scope disclaimer present ───────────────────────────────────────────


def test_scope_statement_present_when_ok(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("STRUCTURE_CONTINUATION_ENABLED", "true")
    with patch("gcp.research.strat_engine.strat_pred_serve.predict_one",
               return_value=_stub_predict_response()), \
         patch("gcp.database.get_engine", return_value=None):
        client = TestClient(_build_app())
        r = _post(client)
    assert r.status_code == 200, r.text
    assert r.json()["scope_statement"] == SCOPE_STATEMENT


# ─── (d) Rule 3.7 — explicit UNAVAILABLE envelope, never a fabricated number ─


def test_unavailable_when_no_model(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("STRUCTURE_CONTINUATION_ENABLED", "true")
    stub = _stub_predict_response(available=False)
    with patch("gcp.research.strat_engine.strat_pred_serve.predict_one",
               return_value=stub), \
         patch("gcp.database.get_engine", return_value=None):
        client = TestClient(_build_app())
        r = _post(client)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "UNAVAILABLE"
    assert data["continuation_prob"] is None  # NOT 0, NOT 0.5
    assert data["reason"]
    assert data["scope_statement"] == SCOPE_STATEMENT


def test_unavailable_when_muted(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("STRUCTURE_CONTINUATION_ENABLED", "true")
    stub = _stub_predict_response(muted=True)
    with patch("gcp.research.strat_engine.strat_pred_serve.predict_one",
               return_value=stub), \
         patch("gcp.database.get_engine", return_value=None):
        client = TestClient(_build_app())
        r = _post(client)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "UNAVAILABLE"
    assert data["continuation_prob"] is None
    assert "ECE breach" in (data["reason"] or "")


def test_unavailable_when_no_current_type(monkeypatch):
    """Available + un-muted but no anchorable current type → UNAVAILABLE,
    not a fabricated continuation probability."""
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("STRUCTURE_CONTINUATION_ENABLED", "true")
    stub = _stub_predict_response(current_type=None, continuation_prob=None)
    with patch("gcp.research.strat_engine.strat_pred_serve.predict_one",
               return_value=stub), \
         patch("gcp.database.get_engine", return_value=None):
        client = TestClient(_build_app())
        r = _post(client)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "UNAVAILABLE"
    assert data["continuation_prob"] is None
    assert data["current_type"] is None


# ─── Auth — the existing admin gate still protects this endpoint ────────────


def test_requires_admin_token_even_with_flag_on(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("STRUCTURE_CONTINUATION_ENABLED", "true")
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    client = TestClient(_build_app())
    r = client.post(
        "/api/admin/strat-engine/structure-continuation",
        json={"ticker": "IWM", "timeframe": "15m"},
    )
    assert r.status_code == 401


def test_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("STRUCTURE_CONTINUATION_ENABLED", "true")
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    client = TestClient(_build_app())
    r = _post(client, token="wrong-token")
    assert r.status_code == 401


# ─── predict_one() continuation derivation (model-layer unit tests) ─────────
#
# These exercise the real `predict_one` code that derives current_type and
# continuation_prob, with GCS / Cloud SQL / featurize internals mocked. They
# guard the contract that continuation_prob == class_probs[current_type] and
# that a missing current type yields None (Rule 3.7), independent of the API.


class _StubModel:
    """Minimal stand-in for the frozen LightGBM/sklearn model."""

    classes_ = ["1", "2U", "2D", "3"]

    def predict_proba(self, X):
        # Fixed distribution: 2U is the mode at 0.55.
        import numpy as np
        return np.array([[0.15, 0.55, 0.20, 0.10]])


def _serve():
    return sys.modules["gcp.research.strat_engine.strat_pred_serve"]


def _patch_serve_internals(current_strat_candle):
    """Patch predict_one's GCS/SQL/featurize internals to be hermetic.

    Returns a list of context managers the caller enters.
    """
    import pandas as pd

    serve = _serve()

    latest_df = pd.DataFrame(
        {
            "ts": [pd.Timestamp("2026-05-22T19:30:00Z")],
            "bar_date": [pd.Timestamp("2026-05-22").date()],
            "strat_candle": [current_strat_candle],
        }
    )

    return [
        patch.object(serve, "_load_model", return_value=_StubModel()),
        patch.object(serve, "_load_metrics", return_value={
            "run_id": "epoch-test", "trained_at": "2026-05-26T00:00:00+00:00",
        }),
        patch.object(serve, "_load_features_list", return_value=None),
        patch.object(serve, "_load_classes_list", return_value=None),
        patch.object(serve, "_load_live_ece_snapshot", return_value={}),
        patch.object(serve, "load_labeled_dataset", return_value=latest_df),
        patch.object(serve, "featurize",
                     return_value=(pd.DataFrame({"f0": [0.0]}), ["f0"])),
    ]


def test_predict_one_sets_continuation_to_current_type_prob(monkeypatch):
    serve = _serve()
    import contextlib
    with contextlib.ExitStack() as stack:
        for cm in _patch_serve_internals(current_strat_candle="2U"):
            stack.enter_context(cm)
        result = serve.predict_one(engine=None, ticker="IWM", tf="15m")
    assert result["available"] is True
    assert result["current_type"] == "2U"
    # continuation_prob must equal the model's probability mass on 2U.
    assert result["continuation_prob"] == pytest.approx(0.55)
    assert result["continuation_prob"] == pytest.approx(result["class_probs"]["2U"])


def test_predict_one_no_current_type_yields_none(monkeypatch):
    """A missing/blank current Strat type must NOT fabricate a probability."""
    serve = _serve()
    import contextlib
    with contextlib.ExitStack() as stack:
        for cm in _patch_serve_internals(current_strat_candle=None):
            stack.enter_context(cm)
        result = serve.predict_one(engine=None, ticker="IWM", tf="15m")
    assert result["current_type"] is None
    assert result["continuation_prob"] is None  # NOT 0, NOT 0.5
