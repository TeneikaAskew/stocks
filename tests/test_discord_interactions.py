"""Unit tests for gcp/discord_interactions/main.py.

Covers:
* Signature verification (good signature passes, bad signature fails,
  replay-tamper rejected)
* PING-PONG handshake
* Date parser (absolute / relative / 'today' / future-rejected)
* Autocomplete handler (with prefix filter + static fallback)
* /replay command dispatch (deferred response shape, env vars passed
  to the Cloud Run Job dispatcher)
* Stub responses for /watchlist, /validate, /backtest

The tests don't actually deploy or call Discord — they exercise the
FastAPI app via the test client and stub out `execute_cloud_run_job`
so no live job execution happens.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from nacl.signing import SigningKey


# Build a fresh keypair once per test session — reused across tests via
# the `signed_request` fixture below.
@pytest.fixture(scope="session")
def keypair():
    sk = SigningKey.generate()
    return {
        "private": sk,
        "public_hex": sk.verify_key.encode().hex(),
    }


@pytest.fixture(autouse=True)
def stub_env(monkeypatch, keypair):
    """Inject Discord secrets into the env so the app accepts requests."""
    monkeypatch.setenv("DISCORD_PUBLIC_KEY", keypair["public_hex"])
    monkeypatch.setenv("DISCORD_APP_ID", "1234567890")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    monkeypatch.setenv("GCP_PROJECT", "test-project")
    monkeypatch.setenv("GCP_REGION", "us-east1")


@pytest.fixture
def client():
    from gcp.discord_interactions.main import app
    return TestClient(app)


def signed_post(client, keypair, body: dict, *, timestamp: str = "1700000000"):
    """POST /discord/interactions with a valid Ed25519 signature."""
    raw = json.dumps(body).encode()
    sig = keypair["private"].sign(timestamp.encode() + raw).signature.hex()
    return client.post(
        "/discord/interactions",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Signature-Ed25519": sig,
            "X-Signature-Timestamp": timestamp,
        },
    )


# ── Signature verification ────────────────────────────────────────────────


def test_good_signature_accepted(client, keypair):
    r = signed_post(client, keypair, {"type": 1})  # PING
    assert r.status_code == 200
    assert r.json() == {"type": 1}  # PONG


def test_bad_signature_rejected_401(client):
    r = client.post(
        "/discord/interactions",
        content=b'{"type": 1}',
        headers={
            "Content-Type": "application/json",
            "X-Signature-Ed25519": "00" * 64,
            "X-Signature-Timestamp": "1700000000",
        },
    )
    assert r.status_code == 401


def test_tampered_body_rejected(client, keypair):
    """Signature was for one body but the request has a different body."""
    sig = keypair["private"].sign(b"1700000000" + b'{"type": 1}').signature.hex()
    r = client.post(
        "/discord/interactions",
        content=b'{"type": 2}',  # tampered
        headers={
            "Content-Type": "application/json",
            "X-Signature-Ed25519": sig,
            "X-Signature-Timestamp": "1700000000",
        },
    )
    assert r.status_code == 401


def test_missing_public_key_returns_503(client, keypair, monkeypatch):
    monkeypatch.delenv("DISCORD_PUBLIC_KEY", raising=False)
    r = signed_post(client, keypair, {"type": 1})
    assert r.status_code == 503


# ── Health probe ──────────────────────────────────────────────────────────


def test_health_reports_secret_presence(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["discord_public_key"] is True
    assert body["discord_app_id"] is True
    assert body["discord_bot_token"] is True


# ── Date parser ───────────────────────────────────────────────────────────


def test_parse_date_absolute():
    from gcp.discord_interactions.main import parse_date_arg
    today = date(2026, 4, 28)
    assert parse_date_arg("2026-04-23", today=today) == date(2026, 4, 23)


def test_parse_date_relative():
    from gcp.discord_interactions.main import parse_date_arg
    today = date(2026, 4, 28)
    assert parse_date_arg("-1", today=today) == date(2026, 4, 27)
    assert parse_date_arg("-3", today=today) == date(2026, 4, 25)


def test_parse_date_today_keyword():
    from gcp.discord_interactions.main import parse_date_arg
    today = date(2026, 4, 28)
    assert parse_date_arg("today", today=today) == today
    assert parse_date_arg("TODAY", today=today) == today


def test_parse_date_future_rejected():
    from gcp.discord_interactions.main import parse_date_arg
    today = date(2026, 4, 28)
    future = (today + timedelta(days=5)).isoformat()
    with pytest.raises(ValueError, match="future"):
        parse_date_arg(future, today=today)


def test_parse_date_garbage_rejected():
    from gcp.discord_interactions.main import parse_date_arg
    with pytest.raises(ValueError):
        parse_date_arg("not-a-date")


def test_parse_date_blank_rejected():
    from gcp.discord_interactions.main import parse_date_arg
    with pytest.raises(ValueError, match="required"):
        parse_date_arg("")


# ── Autocomplete ──────────────────────────────────────────────────────────


def test_autocomplete_filters_by_prefix(monkeypatch):
    from gcp.discord_interactions.main import autocomplete_tickers
    # Force the static fallback path
    monkeypatch.delenv("CLOUD_SQL_CONNECTION_NAME", raising=False)
    out = autocomplete_tickers("S")
    names = [c["name"] for c in out]
    assert "SPY" in names
    assert "SPX" in names
    assert "IWM" not in names  # filtered out


def test_autocomplete_empty_prefix_returns_all_fallback(monkeypatch):
    from gcp.discord_interactions.main import autocomplete_tickers
    monkeypatch.delenv("CLOUD_SQL_CONNECTION_NAME", raising=False)
    out = autocomplete_tickers("")
    names = [c["name"] for c in out]
    assert {"IWM", "SPY", "QQQ", "AVGO", "SPX"}.issubset(set(names))


def test_autocomplete_returns_choice_dict_shape(monkeypatch):
    from gcp.discord_interactions.main import autocomplete_tickers
    monkeypatch.delenv("CLOUD_SQL_CONNECTION_NAME", raising=False)
    out = autocomplete_tickers("S")
    for c in out:
        assert set(c.keys()) == {"name", "value"}
        assert c["name"] == c["value"]
        assert isinstance(c["name"], str)


def test_autocomplete_sql_uses_removed_at_not_active_column(monkeypatch):
    """The watchlists table has no `active` column — `removed_at IS NULL`
    is how 'active' is encoded. Regression test for the column-mismatch
    error that broke autocomplete in production ('Loading options
    failed' in Discord)."""
    import gcp.discord_interactions.main as svc

    captured: dict = {}

    def fake_query(sql: str, params: dict):
        captured["sql"] = sql
        captured["params"] = params
        import pandas as pd
        return pd.DataFrame({"ticker": ["IWM", "SPY"]})

    # Make Cloud SQL appear configured so autocomplete takes the SQL path
    monkeypatch.setenv("CLOUD_SQL_CONNECTION_NAME", "fake:proj:db")
    monkeypatch.setenv("DB_USER", "u")
    monkeypatch.setenv("DB_PASS", "p")
    monkeypatch.setenv("DB_NAME", "d")
    monkeypatch.setattr("gcp.database.query_to_dataframe", fake_query)

    out = svc.autocomplete_tickers("I")

    assert "removed_at IS NULL" in captured["sql"]
    assert "active = true" not in captured["sql"]
    # Result still flows through normally
    assert any(c["value"] == "IWM" for c in out)


def test_execute_cloud_run_job_uses_request_object(monkeypatch):
    """JobsClient.run_job() does NOT accept `overrides=` as a kwarg —
    it must be passed inside a RunJobRequest. Regression test for the
    TypeError that broke every /replay dispatch in production
    (`JobsClient.run_job() got an unexpected keyword argument 'overrides'`).
    """
    from unittest.mock import MagicMock, patch
    import gcp.discord_interactions.main as svc

    captured: dict = {}

    fake_op = MagicMock()
    fake_op.operation.name = "fake-op-id"

    fake_client = MagicMock()
    def fake_run_job(**kwargs):
        # Reject the buggy kwarg shape exactly the way the real client does
        if "name" in kwargs or "overrides" in kwargs:
            raise TypeError("JobsClient.run_job() got an unexpected keyword argument 'overrides'")
        captured["kwargs"] = kwargs
        return fake_op
    fake_client.run_job = fake_run_job

    fake_run_v2 = MagicMock()
    fake_run_v2.JobsClient.return_value = fake_client

    # Stash the patched module so `from google.cloud import run_v2`
    # inside execute_cloud_run_job picks it up
    fake_google_cloud = MagicMock()
    fake_google_cloud.run_v2 = fake_run_v2

    monkeypatch.setattr(svc, "_gcp_project", lambda: "proj")
    monkeypatch.setattr(svc, "_gcp_region", lambda: "us-east1")

    with patch.dict("sys.modules", {"google.cloud": fake_google_cloud,
                                    "google.cloud.run_v2": fake_run_v2}):
        ok = svc.execute_cloud_run_job("test-job", {"FOO": "bar"})

    assert ok is True
    # The CRITICAL assertion: `request` is the kwarg, NOT `name`/`overrides`
    assert "request" in captured["kwargs"]
    assert "name" not in captured["kwargs"]
    assert "overrides" not in captured["kwargs"]


def test_autocomplete_interaction_returns_type_8(client, keypair, monkeypatch):
    monkeypatch.delenv("CLOUD_SQL_CONNECTION_NAME", raising=False)
    body = {
        "type": 4,  # APPLICATION_COMMAND_AUTOCOMPLETE
        "data": {
            "name": "replay",
            "options": [
                {"name": "ticker", "value": "S", "focused": True, "type": 3},
                {"name": "date", "value": "", "type": 3},
            ],
        },
    }
    r = signed_post(client, keypair, body)
    assert r.status_code == 200
    payload = r.json()
    assert payload["type"] == 8  # APPLICATION_COMMAND_AUTOCOMPLETE_RESULT
    assert "choices" in payload["data"]
    names = [c["name"] for c in payload["data"]["choices"]]
    assert "SPY" in names


# ── /replay command dispatch ──────────────────────────────────────────────


def test_replay_command_returns_deferred_ack(client, keypair):
    body = {
        "type": 2,
        "data": {
            "name": "replay",
            "options": [
                {"name": "ticker", "value": "IWM", "type": 3},
                {"name": "date", "value": "2026-04-23", "type": 3},
            ],
        },
        "token": "test-interaction-token",
        "application_id": "1234567890",
    }
    with patch("gcp.discord_interactions.main.execute_cloud_run_job",
               return_value=True):
        r = signed_post(client, keypair, body)
    assert r.status_code == 200
    assert r.json()["type"] == 5  # DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
    assert "IWM" in r.json()["data"]["content"]
    assert "2026-04-23" in r.json()["data"]["content"]


def test_replay_dispatches_brief_and_insight_jobs():
    """handle_replay() should dispatch BOTH premarket-brief and insight-pipeline."""
    from gcp.discord_interactions.main import handle_replay
    calls = []

    def fake_execute(name, env):
        calls.append((name, env))
        return True

    with patch("gcp.discord_interactions.main.execute_cloud_run_job",
               side_effect=fake_execute), \
         patch("gcp.discord_interactions.main.edit_deferred_reply"):
        msg = handle_replay("AMD", "2026-04-24",
                            "1234567890", "test-token")

    job_names = [c[0] for c in calls]
    assert "premarket-brief" in job_names
    assert "insight-pipeline" in job_names

    brief_env = next(env for name, env in calls if name == "premarket-brief")
    assert brief_env["BRIEF_TICKERS"] == "AMD"
    assert brief_env["BRIEF_AS_OF"] == "2026-04-24"

    insight_env = next(env for name, env in calls if name == "insight-pipeline")
    assert insight_env["INSIGHT_TICKERS"] == "AMD"
    assert insight_env["INSIGHT_AS_OF"].startswith("2026-04-24T13:15")

    assert "✅" in msg or "queued" in msg.lower()


def test_replay_invalid_date_returns_error_string():
    from gcp.discord_interactions.main import handle_replay
    msg = handle_replay("IWM", "not-a-date", "1234567890", "test-token")
    assert msg.startswith("❌")


def test_replay_missing_args_ephemeral_error(client, keypair):
    body = {
        "type": 2,
        "data": {
            "name": "replay",
            "options": [{"name": "ticker", "value": "IWM", "type": 3}],
            # no `date`
        },
        "token": "tk",
        "application_id": "1234567890",
    }
    r = signed_post(client, keypair, body)
    assert r.status_code == 200
    payload = r.json()
    assert payload["type"] == 4  # immediate channel message
    assert payload["data"].get("flags") == 64  # ephemeral
    assert "ticker" in payload["data"]["content"].lower()
    assert "date" in payload["data"]["content"].lower()


# ── Stub commands (Slice 2 / 3) ───────────────────────────────────────────


@pytest.mark.parametrize("cmd", ["watchlist", "validate", "backtest"])
def test_stub_commands_return_coming_soon(client, keypair, cmd):
    body = {
        "type": 2,
        "data": {"name": cmd, "options": []},
        "token": "tk",
        "application_id": "1234567890",
    }
    r = signed_post(client, keypair, body)
    assert r.status_code == 200
    payload = r.json()
    assert payload["type"] == 4  # immediate ephemeral
    assert "follow-up slice" in payload["data"]["content"]
    assert payload["data"].get("flags") == 64


def test_unknown_command_returns_error(client, keypair):
    body = {
        "type": 2,
        "data": {"name": "nonexistent", "options": []},
        "token": "tk",
        "application_id": "1234567890",
    }
    r = signed_post(client, keypair, body)
    assert r.status_code == 200
    payload = r.json()
    assert "Unknown" in payload["data"]["content"]
