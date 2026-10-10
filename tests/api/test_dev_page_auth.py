"""Who may open the `/dev` diagnostics page, per AUTH_MODE.

`/dev` lists the Playwright service account, the IAP audience, the revision,
the Cloud SQL connection name and the strat-engine model state. It sits outside
`/api/`, so the auth middleware never sees it, and it used to admit any request
without an IAP header. On the public Firebase staging service no request
carries one, so the page was open to anyone (stocks#943). REQ-AUTH-003: such a
page is gated like `/api/*` or not deployed on a public service.

| mode     | no IAP header | other email | DEV_ALLOWED_EMAIL |
|----------|---------------|-------------|-------------------|
| firebase | 404           | 404         | 404               |
| iap      | 403           | 403         | 200               |
| open     | 200           | 403         | 200               |
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PLATFORM = Path(__file__).resolve().parent.parent.parent / "platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

ALLOWED = "dev-owner@example.com"


def _get(monkeypatch, mode: str, header: str | None):
    import api.auth as a
    import api.main as m

    monkeypatch.setattr(a, "AUTH_MODE", mode)
    monkeypatch.setattr(m, "_DEV_ALLOWED_EMAIL", ALLOWED)
    # No GCS call from a unit test: the page renders an "unavailable" note.
    monkeypatch.setattr(m, "_strat_engine_state", lambda: [])
    headers = (
        {"x-goog-authenticated-user-email": f"accounts.google.com:{header}"}
        if header else {}
    )
    return TestClient(m.app).get("/dev", headers=headers)


@pytest.mark.parametrize("header", [None, "someone@example.com", ALLOWED])
def test_dev_is_absent_on_the_public_firebase_service(monkeypatch, header):
    r = _get(monkeypatch, "firebase", header)
    assert r.status_code == 404
    assert "service account" not in r.text.lower()


def test_dev_in_iap_mode_refuses_a_request_without_the_iap_header(monkeypatch):
    r = _get(monkeypatch, "iap", None)
    assert r.status_code == 403


def test_dev_in_iap_mode_refuses_another_email(monkeypatch):
    assert _get(monkeypatch, "iap", "someone@example.com").status_code == 403


def test_dev_in_iap_mode_serves_the_allowed_email(monkeypatch):
    r = _get(monkeypatch, "iap", ALLOWED)
    assert r.status_code == 200
    assert ALLOWED in r.text


def test_dev_in_open_mode_serves_local_development(monkeypatch):
    assert _get(monkeypatch, "open", None).status_code == 200
    assert _get(monkeypatch, "open", "someone@example.com").status_code == 403
