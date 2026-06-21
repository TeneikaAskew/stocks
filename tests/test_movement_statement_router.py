"""Tests for `GET /api/movement-statement` — the PHASE 3 feature-flagged,
read-only endpoint that exposes the Phase 2 movement-statement assembler.

What this asserts (the Phase 3 acceptance criteria):
  (a) the endpoint returns the assembled object ONLY when the feature flag
      is ON; with the flag OFF (default) it 404s (the card does not render);
  (b) only IWM/SPY/QQQ at 5m/15m are accepted — invalid ticker / timeframe
      (incl. 30m) is rejected with 400;
  (c) the assembler's per-field UNAVAILABLE envelopes are passed through
      VERBATIM — the endpoint never fabricates a value (CLAUDE.md Rule 3.7);
  (d) the headline probability equals the continuation probability (the
      endpoint does not alter the assembler's CONFIDENCE RULE output).

The assembler itself + its level-map builder are patched so the test runs
hermetically (no GCS, no Cloud SQL, no model load). The endpoint is a thin
pass-through, so patching `assemble_movement_statement` exercises exactly
the endpoint's flag/validation/pass-through logic.
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
    from routers import dashboard as dashboard_router
except ModuleNotFoundError as exc:  # pragma: no cover
    pytest.skip(f"dashboard router unavailable: {exc}", allow_module_level=True)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(dashboard_router.router)
    return app


def _sample_statement(
    *,
    ticker: str = "SPY",
    timeframe: str = "15m",
    continuation_prob: float = 0.62,
    magnitude_unavailable: bool = False,
) -> dict:
    """The exact dict shape assemble_movement_statement produces (flag ON)."""
    expected_move: dict
    if magnitude_unavailable:
        expected_move = {
            "status": "UNAVAILABLE",
            "reason": "no magnitude prediction for SPY:15m",
            "role": "context",
        }
    else:
        expected_move = {
            "status": "OK",
            "role": "context",
            "size_class": "EXPANDED",
            "pred_bucket": 2,
            "usage_guidance": "Sizing / context only.",
        }
    return {
        "status": "OK",
        "ticker": ticker,
        "timeframe": timeframe,
        "as_of": None,
        "scope_statement": "Structure read, not a directional or P&L edge.",
        "headline": {
            "status": "OK",
            "current_type": "2U",
            "probability": continuation_prob,
            "probability_source": "structure_continuation_model",
            "timeframe": timeframe,
            "statement": (
                f"{ticker} {timeframe}: current structure is a 2U candle; "
                f"calibrated probability the next bar continues that structure "
                f"is {continuation_prob:.0%}."
            ),
        },
        "continuation": {
            "status": "OK",
            "current_type": "2U",
            "continuation_prob": continuation_prob,
            "timeframe": timeframe,
        },
        "levels": {
            "status": "OK",
            "calls": [
                {
                    "price": 101.0,
                    "name": "PDH",
                    "reach_rate": {
                        "status": "OK",
                        "reach_rate": 0.48,
                        "hits": 24,
                        "sample_n": 50,
                        "low_sample": False,
                    },
                },
                {
                    "price": 102.0,
                    "name": "PWH",
                    "reach_rate": {
                        "status": "UNAVAILABLE",
                        "reason": "no reach-rate computed for this tier",
                    },
                },
            ],
            "puts": [],
            "current_price": 100.0,
        },
        "confidence_modifiers": {
            "note": "Context only. These DO NOT change the headline probability.",
            "expected_move": expected_move,
            "regime": {
                "status": "OK",
                "role": "context",
                "regime": "positive_gamma",
                "mood": "pinning",
            },
        },
    }


def _get(client, *, ticker="SPY", tf="15m"):
    return client.get(f"/api/movement-statement?ticker={ticker}&timeframe={tf}")


# ─── (a) Feature flag gates the endpoint's existence ────────────────────────


def test_flag_off_returns_404(monkeypatch):
    """Flag OFF (default) → endpoint behaves as if it doesn't exist."""
    monkeypatch.delenv("MOVEMENT_STATEMENT_ENABLED", raising=False)
    client = TestClient(_build_app())
    r = _get(client)
    assert r.status_code == 404


def test_flag_explicitly_false_returns_404(monkeypatch):
    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "false")
    client = TestClient(_build_app())
    r = _get(client)
    assert r.status_code == 404


def test_flag_on_returns_object(monkeypatch):
    """Flag ON → the assembled movement statement is returned."""
    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "true")
    with patch.object(
        dashboard_router, "_build_movement_level_map", return_value=object()
    ), patch(
        "lib.movement_statement.assemble_movement_statement",
        return_value=_sample_statement(),
    ):
        client = TestClient(_build_app())
        r = _get(client)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "OK"
    assert data["ticker"] == "SPY"
    assert data["timeframe"] == "15m"


# ─── (b) Only IWM/SPY/QQQ at 5m/15m — invalid rejected with 400 ─────────────


@pytest.mark.parametrize("tf", ["5m", "15m"])
def test_allowed_timeframes(monkeypatch, tf):
    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "1")
    with patch.object(
        dashboard_router, "_build_movement_level_map", return_value=None
    ), patch(
        "lib.movement_statement.assemble_movement_statement",
        return_value=_sample_statement(timeframe=tf),
    ):
        client = TestClient(_build_app())
        r = _get(client, tf=tf)
    assert r.status_code == 200, r.text


def test_30m_is_rejected(monkeypatch):
    """30m is never consulted — rejected even with the flag ON."""
    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "on")
    client = TestClient(_build_app())
    r = _get(client, tf="30m")
    assert r.status_code == 400
    assert "30m is never consulted" in r.text


def test_unknown_ticker_rejected(monkeypatch):
    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "on")
    client = TestClient(_build_app())
    r = _get(client, ticker="TSLA")
    assert r.status_code == 400
    assert "ticker must be one of" in r.text


def test_30m_never_exposed_constant():
    """Belt-and-suspenders: the exposed-TF tuple must not contain 30m."""
    assert "30m" not in dashboard_router.MOVEMENT_STATEMENT_TFS
    assert set(dashboard_router.MOVEMENT_STATEMENT_TFS) == {"5m", "15m"}
    assert set(dashboard_router.MOVEMENT_STATEMENT_TICKERS) == {"IWM", "SPY", "QQQ"}


# ─── (c) Rule 3.7 — UNAVAILABLE envelopes pass through unfabricated ─────────


def test_unavailable_field_passes_through(monkeypatch):
    """A tier reach-rate / modifier that the assembler marked UNAVAILABLE must
    arrive at the client VERBATIM — no fabricated number, no stripped reason."""
    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "true")
    with patch.object(
        dashboard_router, "_build_movement_level_map", return_value=None
    ), patch(
        "lib.movement_statement.assemble_movement_statement",
        return_value=_sample_statement(magnitude_unavailable=True),
    ):
        client = TestClient(_build_app())
        r = _get(client)
    assert r.status_code == 200, r.text
    data = r.json()
    # The unavailable tier reach-rate survived with its reason and NO value.
    tier = data["levels"]["calls"][1]["reach_rate"]
    assert tier["status"] == "UNAVAILABLE"
    assert "reach_rate" not in tier  # never a fabricated rate
    assert tier["reason"]
    # The unavailable modifier survived too.
    em = data["confidence_modifiers"]["expected_move"]
    assert em["status"] == "UNAVAILABLE"
    assert "size_class" not in em  # never a fabricated bucket
    assert em["reason"]


# ─── (d) Headline == continuation (endpoint preserves the CONFIDENCE RULE) ──


def test_headline_equals_continuation(monkeypatch):
    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "true")
    with patch.object(
        dashboard_router, "_build_movement_level_map", return_value=None
    ), patch(
        "lib.movement_statement.assemble_movement_statement",
        return_value=_sample_statement(continuation_prob=0.62),
    ):
        client = TestClient(_build_app())
        r = _get(client)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["headline"]["probability"] == pytest.approx(0.62)
    assert data["continuation"]["continuation_prob"] == pytest.approx(0.62)
    assert data["headline"]["probability"] == data["continuation"]["continuation_prob"]


# ─── Pass-through fidelity — the endpoint does not re-derive the object ──────


def test_endpoint_passes_assembler_output_unchanged(monkeypatch):
    """The endpoint is a thin pass-through; the JSON body must be byte-for-byte
    the assembler's dict (modulo JSON round-trip), proving no re-computation."""
    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "true")
    expected = _sample_statement()
    with patch.object(
        dashboard_router, "_build_movement_level_map", return_value=None
    ), patch(
        "lib.movement_statement.assemble_movement_statement",
        return_value=expected,
    ):
        client = TestClient(_build_app())
        r = _get(client)
    assert r.status_code == 200, r.text
    assert r.json() == expected


def test_flag_on_but_assembler_returns_none_is_404(monkeypatch):
    """Defensive: if the assembler returns None despite the flag check (env
    race), surface 404 rather than a null body — never fabricate a payload."""
    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "true")
    with patch.object(
        dashboard_router, "_build_movement_level_map", return_value=None
    ), patch(
        "lib.movement_statement.assemble_movement_statement", return_value=None
    ):
        client = TestClient(_build_app())
        r = _get(client)
    assert r.status_code == 404
