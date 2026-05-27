"""Tests for `POST /api/admin/strat-engine/predict` — the admin-gated
on-demand single-bar prediction endpoint.

Auth, response shape, and the mute decision branch are covered. The
underlying model load + Cloud SQL feature fetch is patched out so the
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
    ticker: str = "IWM",
    timeframe: str = "15m",
    top_class: str | None = "2U",
    top_prob: float | None = 0.62,
) -> dict:
    """Build the exact response shape `predict_one` produces, for stubbing."""
    if not available:
        return {
            "ticker": ticker,
            "timeframe": timeframe,
            "available": False,
            "top_class": None,
            "top_prob": None,
            "class_probs": {},
            "model_version": None,
            "last_train_date": None,
            "live_ece": None,
            "muted": False,
            "mute_reason": None,
            "scope_statement": SCOPE_STATEMENT,
            "ts": None,
            "note": "No model.pkl found at gs://... — dispatch the Cloud Run Job to train first.",
        }
    if muted:
        return {
            "ticker": ticker,
            "timeframe": timeframe,
            "available": True,
            "top_class": None,
            "top_prob": None,
            "class_probs": {},
            "model_version": "epoch-1779781975",
            "last_train_date": "2026-05-26T07:52:55+00:00",
            "live_ece": 0.073,
            "muted": True,
            "mute_reason": "model muted, ECE breach (live ECE 0.073 > ceiling 0.050)",
            "scope_statement": SCOPE_STATEMENT,
            "ts": None,
            "note": None,
        }
    return {
        "ticker": ticker,
        "timeframe": timeframe,
        "available": True,
        "top_class": top_class,
        "top_prob": top_prob,
        "class_probs": {
            "1": 0.10,
            "2U": top_prob if top_class == "2U" else 0.20,
            "2D": top_prob if top_class == "2D" else 0.20,
            "3": 0.10,
        },
        "model_version": "epoch-1779781975",
        "last_train_date": "2026-05-26T07:52:55+00:00",
        "live_ece": 0.023,
        "muted": False,
        "mute_reason": None,
        "scope_statement": SCOPE_STATEMENT,
        "ts": "2026-05-22T19:30:00+00:00",
        "note": None,
    }


# ─── Auth tests ──────────────────────────────────────────────────────────────


def test_predict_requires_admin_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    client = TestClient(_build_app())
    r = client.post("/api/admin/strat-engine/predict",
                     json={"ticker": "IWM", "timeframe": "15m"})
    # 401 when token absent, 503 when ADMIN_TOKEN env var unset. We set
    # it above so 401 is the expected response.
    assert r.status_code == 401


def test_predict_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    client = TestClient(_build_app())
    r = client.post("/api/admin/strat-engine/predict",
                     json={"ticker": "IWM", "timeframe": "15m"},
                     headers={"X-Admin-Token": "wrong-token"})
    assert r.status_code == 401


def test_predict_rejects_unknown_ticker(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    client = TestClient(_build_app())
    r = client.post("/api/admin/strat-engine/predict",
                     json={"ticker": "TSLA", "timeframe": "15m"},
                     headers={"X-Admin-Token": "secret-token"})
    assert r.status_code == 400
    assert "ticker must be one of" in r.text


def test_predict_rejects_unknown_timeframe(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    client = TestClient(_build_app())
    r = client.post("/api/admin/strat-engine/predict",
                     json={"ticker": "IWM", "timeframe": "4h"},
                     headers={"X-Admin-Token": "secret-token"})
    assert r.status_code == 400
    assert "timeframe must be one of" in r.text


# ─── Happy path / response shape ─────────────────────────────────────────────


def test_predict_returns_valid_shape(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    stub = _stub_predict_response()
    with patch("gcp.research.strat_engine.strat_pred_serve.predict_one",
               return_value=stub), \
         patch("gcp.database.get_engine", return_value=None):
        client = TestClient(_build_app())
        r = client.post("/api/admin/strat-engine/predict",
                         json={"ticker": "IWM", "timeframe": "15m"},
                         headers={"X-Admin-Token": "secret-token"})
    assert r.status_code == 200, r.text
    data = r.json()
    # Spec contract — every field must be present
    for k in ("ticker", "timeframe", "ts", "available", "top_class",
              "top_prob", "class_probs", "model_version", "last_train_date",
              "live_ece", "muted", "mute_reason", "scope_statement", "note"):
        assert k in data, f"missing field: {k}"
    assert data["ticker"] == "IWM"
    assert data["timeframe"] == "15m"
    assert data["top_class"] == "2U"
    assert 0.0 <= data["top_prob"] <= 1.0
    assert set(data["class_probs"].keys()) == {"1", "2U", "2D", "3"}
    assert data["scope_statement"] == SCOPE_STATEMENT
    assert data["muted"] is False


def test_predict_normalizes_ticker_casing(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    stub = _stub_predict_response(ticker="IWM")
    with patch("gcp.research.strat_engine.strat_pred_serve.predict_one",
               return_value=stub), \
         patch("gcp.database.get_engine", return_value=None):
        client = TestClient(_build_app())
        r = client.post("/api/admin/strat-engine/predict",
                         json={"ticker": "iwm", "timeframe": "15m"},
                         headers={"X-Admin-Token": "secret-token"})
    assert r.status_code == 200, r.text
    # Endpoint upper-cases the ticker before validation + dispatch
    assert r.json()["ticker"] == "IWM"


# ─── Mute branch ─────────────────────────────────────────────────────────────


def test_predict_returns_muted_payload(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    stub = _stub_predict_response(muted=True)
    with patch("gcp.research.strat_engine.strat_pred_serve.predict_one",
               return_value=stub), \
         patch("gcp.database.get_engine", return_value=None):
        client = TestClient(_build_app())
        r = client.post("/api/admin/strat-engine/predict",
                         json={"ticker": "IWM", "timeframe": "15m"},
                         headers={"X-Admin-Token": "secret-token"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["muted"] is True
    assert data["top_class"] is None
    assert data["top_prob"] is None
    assert data["class_probs"] == {}
    assert "ECE breach" in (data["mute_reason"] or "")
    # Even when muted the scope statement is rendered
    assert data["scope_statement"] == SCOPE_STATEMENT


# ─── Unavailable branch (model.pkl missing for the cell) ─────────────────────


def test_predict_returns_unavailable_when_no_model(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    stub = _stub_predict_response(available=False)
    with patch("gcp.research.strat_engine.strat_pred_serve.predict_one",
               return_value=stub), \
         patch("gcp.database.get_engine", return_value=None):
        client = TestClient(_build_app())
        r = client.post("/api/admin/strat-engine/predict",
                         json={"ticker": "SPY", "timeframe": "30m"},
                         headers={"X-Admin-Token": "secret-token"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["available"] is False
    assert data["top_class"] is None
    assert data["note"] is not None
    assert data["scope_statement"] == SCOPE_STATEMENT


# ─── Language audit on the verbatim scope statement ──────────────────────────


def test_scope_statement_is_verbatim_constant():
    # The constant in the admin router must match the spec character-for-character.
    assert admin_router.STRUCTURE_BRIEF_SCOPE_STATEMENT == SCOPE_STATEMENT


def test_scope_statement_contains_no_disallowed_language():
    banned = [
        "entry", "buy", "sell", "trade signal", "trade this",
        "predicts upside", "predicts downside",
        "buy at", "sell at", "directional edge",
    ]
    lower = SCOPE_STATEMENT.lower()
    for word in banned:
        assert word not in lower, f"banned language in scope statement: {word!r}"
