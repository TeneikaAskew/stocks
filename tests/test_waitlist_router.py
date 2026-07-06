"""Tests for POST /api/waitlist — the public landing-page signup endpoint.

Asserts (spec §7 + CLAUDE.md Rule 3.7):
  (a) valid email → 200 + one idempotent upsert executed;
  (b) malformed email → 400, no DB call;
  (c) filled honeypot (`website`) → 200 fake-success WITHOUT a DB call
      (the one sanctioned anti-bot fake success, documented in the router);
  (d) DB failure → LOUD 503, never a fake success;
  (e) >5 requests / window from one IP → 429.
Hermetic: gcp.database.get_engine is patched — no Cloud SQL.
"""
from __future__ import annotations

import sys
import time
from collections import deque
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "platform" / "api"))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import waitlist as waitlist_router


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    waitlist_router._hits.clear()
    yield
    waitlist_router._hits.clear()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(waitlist_router.router)
    return TestClient(app)


def _engine_mock() -> MagicMock:
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    engine.begin.return_value.__exit__.return_value = False
    return engine


def test_valid_email_upserts_and_returns_ok():
    engine = _engine_mock()
    with patch("gcp.database.get_engine", return_value=engine):
        r = _client().post(
            "/api/waitlist",
            json={"email": "Trader@Example.com", "source": "landing-hero", "website": ""},
        )
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    conn = engine.begin.return_value.__enter__.return_value
    assert conn.execute.call_count == 1
    params = conn.execute.call_args.args[1]
    assert params["email"] == "trader@example.com"  # normalized lowercase


def test_invalid_email_is_400_and_no_db_call():
    with patch("gcp.database.get_engine") as ge:
        r = _client().post("/api/waitlist", json={"email": "not-an-email", "website": ""})
    assert r.status_code == 400
    ge.assert_not_called()


def test_honeypot_returns_fake_success_without_db_call():
    with patch("gcp.database.get_engine") as ge:
        r = _client().post(
            "/api/waitlist",
            json={"email": "bot@spam.com", "website": "http://spam"},
        )
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    ge.assert_not_called()


def test_honeypot_checked_before_email_validation():
    """A bot that fills the honeypot AND sends a malformed email must still
    get the fake-success 200 (not the 400 that would tell the bot 'this is a
    validation endpoint'), and must never touch the DB."""
    with patch("gcp.database.get_engine") as ge:
        r = _client().post(
            "/api/waitlist",
            json={"email": "not-an-email", "website": "http://spam"},
        )
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    ge.assert_not_called()


def test_db_failure_is_loud_503():
    with patch("gcp.database.get_engine", side_effect=RuntimeError("db down")):
        r = _client().post("/api/waitlist", json={"email": "a@b.co", "website": ""})
    assert r.status_code == 503


def test_rate_limit_429_after_five_requests():
    engine = _engine_mock()
    client = _client()
    with patch("gcp.database.get_engine", return_value=engine):
        for _ in range(5):
            assert client.post(
                "/api/waitlist", json={"email": "a@b.co", "website": ""}
            ).status_code == 200
        r = client.post("/api/waitlist", json={"email": "a@b.co", "website": ""})
    assert r.status_code == 429


def test_rate_limit_keys_on_x_forwarded_for_last_hop_not_socket_peer():
    """On Cloud Run every request arrives from the proxy's socket address, so
    keying on request.client.host would bucket every visitor together. The
    limiter must key on the LAST X-Forwarded-For entry (the hop Google's
    frontend itself observed) so independent visitors get independent
    buckets, and must ignore spoofable earlier entries in the header."""
    engine = _engine_mock()
    client = _client()
    with patch("gcp.database.get_engine", return_value=engine):
        for _ in range(5):
            assert (
                client.post(
                    "/api/waitlist",
                    json={"email": "a@b.co", "website": ""},
                    headers={"X-Forwarded-For": "1.1.1.1"},
                ).status_code
                == 200
            )
        # 6th request from the same forwarded IP is rate-limited.
        r = client.post(
            "/api/waitlist",
            json={"email": "a@b.co", "website": ""},
            headers={"X-Forwarded-For": "1.1.1.1"},
        )
        assert r.status_code == 429

        # A different forwarded IP gets its own, independent bucket.
        r2 = client.post(
            "/api/waitlist",
            json={"email": "a@b.co", "website": ""},
            headers={"X-Forwarded-For": "2.2.2.2"},
        )
        assert r2.status_code == 200

        # A spoofed header with extra client-supplied hops still buckets by
        # the LAST (trustworthy) entry, "3.3.3.3" — not the spoofed prefix.
        for _ in range(5):
            assert (
                client.post(
                    "/api/waitlist",
                    json={"email": "a@b.co", "website": ""},
                    headers={"X-Forwarded-For": "9.9.9.9, 3.3.3.3"},
                ).status_code
                == 200
            )
        r3 = client.post(
            "/api/waitlist",
            json={"email": "a@b.co", "website": ""},
            headers={"X-Forwarded-For": "9.9.9.9, 3.3.3.3"},
        )
        assert r3.status_code == 429
        assert waitlist_router._hits.get("3.3.3.3") is not None
        assert "9.9.9.9, 3.3.3.3" not in waitlist_router._hits


def test_rate_limiter_evicts_stale_ips():
    engine = _engine_mock()
    client = _client()
    with patch("gcp.database.get_engine", return_value=engine):
        # Seed a stale IP whose entire window has expired
        waitlist_router._hits["10.0.0.9"] = deque(
            [time.monotonic() - waitlist_router._RATE_WINDOW_S - 1]
        )
        client.post("/api/waitlist", json={"email": "a@b.co", "website": ""})
    assert "10.0.0.9" not in waitlist_router._hits
