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
from unittest.mock import MagicMock, patch

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


# ── as_of clamp + auto-backfill ──────────────────────────────────────────


def test_replay_today_clamps_insight_as_of_below_now():
    """Regression: if the user runs /replay date:today before 9:15 ET,
    the canonical 13:15 UTC anchor would be in the future and
    insight_pipeline_job.parse_as_of would reject it (caught in prod
    on 2026-04-29 at 13:04 UTC). Clamp to "now" so the cutoff is
    always safely in the past."""
    from datetime import datetime, timezone
    from gcp.discord_interactions.main import handle_replay
    calls = []
    with patch("gcp.discord_interactions.main.execute_cloud_run_job",
               side_effect=lambda n, e: calls.append((n, e)) or True), \
         patch("gcp.discord_interactions.main.ticker_has_daily_data",
               return_value=True), \
         patch("gcp.discord_interactions.main.edit_deferred_reply"):
        handle_replay("IWM", "today", "appid", "tok")
    insight_env = next(env for name, env in calls if name == "insight-pipeline")
    parsed = datetime.strptime(
        insight_env["INSIGHT_AS_OF"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=timezone.utc)
    assert parsed <= datetime.now(timezone.utc), \
        f"INSIGHT_AS_OF {parsed} is in the future"


def test_replay_past_date_uses_canonical_915_et_anchor():
    """For a date safely in the past, INSIGHT_AS_OF should be the
    canonical 13:15 UTC (= 09:15 ET in DST) anchor on that day."""
    from gcp.discord_interactions.main import handle_replay
    calls = []
    with patch("gcp.discord_interactions.main.execute_cloud_run_job",
               side_effect=lambda n, e: calls.append((n, e)) or True), \
         patch("gcp.discord_interactions.main.ticker_has_daily_data",
               return_value=True), \
         patch("gcp.discord_interactions.main.edit_deferred_reply"):
        handle_replay("IWM", "2026-04-23", "appid", "tok")
    insight_env = next(env for name, env in calls if name == "insight-pipeline")
    assert insight_env["INSIGHT_AS_OF"] == "2026-04-23T13:15:00Z"


def test_replay_skips_backfill_when_ticker_has_data():
    """Ticker already in market_data_daily → no backfill job dispatched."""
    from gcp.discord_interactions.main import handle_replay
    calls = []
    with patch("gcp.discord_interactions.main.execute_cloud_run_job",
               side_effect=lambda n, e: calls.append((n, e)) or True), \
         patch("gcp.discord_interactions.main.execute_cloud_run_job_blocking") as blocking, \
         patch("gcp.discord_interactions.main.ticker_has_daily_data",
               return_value=True), \
         patch("gcp.discord_interactions.main.edit_deferred_reply"):
        msg = handle_replay("IWM", "2026-04-23", "appid", "tok")
    job_names = [c[0] for c in calls]
    assert "premarket-brief" in job_names
    assert "insight-pipeline" in job_names
    blocking.assert_not_called()
    assert "Backfill" not in msg


def test_replay_dispatches_backfill_when_ticker_missing():
    """Missing ticker → backfill-ticker FIRST (blocking), then brief + insight."""
    from gcp.discord_interactions.main import handle_replay
    fire_and_forget: list = []
    blocking_calls: list = []

    def fake_blocking(name, env, timeout_sec=540):
        blocking_calls.append((name, env))
        return True

    with patch("gcp.discord_interactions.main.execute_cloud_run_job",
               side_effect=lambda n, e: fire_and_forget.append((n, e)) or True), \
         patch("gcp.discord_interactions.main.execute_cloud_run_job_blocking",
               side_effect=fake_blocking), \
         patch("gcp.discord_interactions.main.ticker_has_daily_data",
               return_value=False), \
         patch("gcp.discord_interactions.main.edit_deferred_reply"):
        msg = handle_replay("AMD", "2026-04-24", "appid", "tok")

    assert len(blocking_calls) == 1
    bf_name, bf_env = blocking_calls[0]
    assert bf_name == "backfill-ticker"
    assert bf_env["BACKFILL_TICKER"] == "AMD"
    assert bf_env["BACKFILL_DATES"] == "2026-04-24"
    assert bf_env["BACKFILL_INCLUDE_NEWS"] == "true"

    async_names = [c[0] for c in fire_and_forget]
    assert "premarket-brief" in async_names
    assert "insight-pipeline" in async_names

    assert "Backfill complete" in msg
    assert "Replay queued" in msg


def test_replay_returns_error_when_backfill_fails():
    """If backfill-ticker fails, abort BEFORE brief + insight dispatch
    so we don't post empty embeds against an empty database."""
    from gcp.discord_interactions.main import handle_replay
    fire_and_forget: list = []
    with patch("gcp.discord_interactions.main.execute_cloud_run_job",
               side_effect=lambda n, e: fire_and_forget.append((n, e)) or True), \
         patch("gcp.discord_interactions.main.execute_cloud_run_job_blocking",
               return_value=False), \
         patch("gcp.discord_interactions.main.ticker_has_daily_data",
               return_value=False), \
         patch("gcp.discord_interactions.main.edit_deferred_reply"):
        msg = handle_replay("UNKNOWN", "2026-04-23", "appid", "tok")
    assert msg.startswith("❌")
    assert "Backfill failed" in msg
    assert fire_and_forget == []


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


# ── Stub commands (Slice 3) ────────────────────────────────────────────


@pytest.mark.parametrize("cmd", ["validate", "backtest"])
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


# ── /watchlist subcommands (Slice 2) ──────────────────────────────────────


def _watchlist_payload(sub: str, ticker: str = "") -> dict:
    """Build the Discord interaction payload for /watchlist <sub> ..."""
    sub_options = ([{"name": "ticker", "value": ticker, "type": 3}]
                   if ticker else [])
    return {
        "type": 2,
        "data": {
            "name": "watchlist",
            "options": [{
                "name": sub, "type": 1,  # SUB_COMMAND
                "options": sub_options,
            }],
        },
        "token": "tk",
        "application_id": "1234567890",
    }


def test_watchlist_subcommand_extraction():
    """_watchlist_subcommand pulls the right name + options."""
    from gcp.discord_interactions.main import _watchlist_subcommand
    payload = _watchlist_payload("add", "NVDA")
    sub, opts = _watchlist_subcommand(payload["data"])
    assert sub == "add"
    assert opts == {"ticker": "NVDA"}

    list_payload = _watchlist_payload("list")
    sub, opts = _watchlist_subcommand(list_payload["data"])
    assert sub == "list"
    assert opts == {}


def test_watchlist_add_inserts_ticker(client, keypair):
    from gcp.discord_interactions.main import _watchlist_add
    captured = []
    fake_engine = MagicMock()
    fake_conn = MagicMock()

    def fake_execute(stmt, params=None):
        captured.append((str(stmt), dict(params) if params else {}))
        result = MagicMock()
        result.fetchone.return_value = (True,)  # inserted=True
        return result

    fake_conn.execute.side_effect = fake_execute
    fake_engine.begin.return_value.__enter__.return_value = fake_conn
    fake_engine.begin.return_value.__exit__.return_value = False

    with patch("gcp.database.get_engine", return_value=fake_engine):
        msg = _watchlist_add("nvda")

    assert "✅" in msg and "NVDA" in msg
    sql, params = captured[0]
    assert "INSERT INTO watchlists" in sql
    assert "user_id" in sql and "ticker" in sql
    assert "ON CONFLICT (user_id, ticker)" in sql
    assert params["t"] == "NVDA"


def test_watchlist_add_already_present(client, keypair):
    from gcp.discord_interactions.main import _watchlist_add
    fake_engine = MagicMock()
    fake_conn = MagicMock()
    result = MagicMock()
    result.fetchone.return_value = (False,)  # inserted=False (was UPDATE)
    fake_conn.execute.return_value = result
    fake_engine.begin.return_value.__enter__.return_value = fake_conn
    fake_engine.begin.return_value.__exit__.return_value = False

    with patch("gcp.database.get_engine", return_value=fake_engine):
        msg = _watchlist_add("AVGO")

    assert "ℹ️" in msg
    assert "already" in msg.lower()


def test_watchlist_add_invalid_ticker():
    from gcp.discord_interactions.main import _watchlist_add
    msg = _watchlist_add("not-a-ticker!")  # symbols not allowed
    assert msg.startswith("❌")


def test_watchlist_remove_existing(client, keypair):
    from gcp.discord_interactions.main import _watchlist_remove
    fake_engine = MagicMock()
    fake_conn = MagicMock()
    result = MagicMock()
    result.fetchone.return_value = ("NVDA",)
    fake_conn.execute.return_value = result
    fake_engine.begin.return_value.__enter__.return_value = fake_conn
    fake_engine.begin.return_value.__exit__.return_value = False

    with patch("gcp.database.get_engine", return_value=fake_engine):
        msg = _watchlist_remove("nvda")

    assert "✅" in msg and "Removed" in msg


def test_watchlist_remove_not_in_list():
    from gcp.discord_interactions.main import _watchlist_remove
    fake_engine = MagicMock()
    fake_conn = MagicMock()
    result = MagicMock()
    result.fetchone.return_value = None
    fake_conn.execute.return_value = result
    fake_engine.begin.return_value.__enter__.return_value = fake_conn
    fake_engine.begin.return_value.__exit__.return_value = False

    with patch("gcp.database.get_engine", return_value=fake_engine):
        msg = _watchlist_remove("UNKNOWN")

    assert "ℹ️" in msg
    assert "wasn't" in msg


def test_watchlist_list_renders_rows():
    from gcp.discord_interactions.main import _watchlist_list
    import pandas as pd
    df = pd.DataFrame([
        {"ticker": "IWM", "added_at": "2026-04-01", "source": "seed"},
        {"ticker": "NVDA", "added_at": "2026-04-29", "source": "discord-replay"},
    ])
    with patch("gcp.database.query_to_dataframe", return_value=df):
        msg = _watchlist_list()
    assert "Watchlist" in msg
    assert "2 active" in msg
    assert "IWM" in msg
    assert "NVDA" in msg
    assert "discord-replay" in msg


def test_watchlist_list_empty():
    from gcp.discord_interactions.main import _watchlist_list
    import pandas as pd
    with patch("gcp.database.query_to_dataframe", return_value=pd.DataFrame()):
        msg = _watchlist_list()
    assert "empty" in msg.lower()


def test_watchlist_dispatch_routes_to_subcommand_handler(client, keypair):
    """Full request → /watchlist list → reply rendered (Cloud SQL stubbed)."""
    import pandas as pd
    body = _watchlist_payload("list")
    with patch("gcp.database.query_to_dataframe", return_value=pd.DataFrame()):
        r = signed_post(client, keypair, body)
    assert r.status_code == 200
    payload = r.json()
    assert payload["type"] == 4  # CHANNEL_MESSAGE_WITH_SOURCE (immediate)
    assert "Watchlist" in payload["data"]["content"] or \
           "empty" in payload["data"]["content"].lower()


def test_watchlist_unknown_subcommand_returns_error():
    from gcp.discord_interactions.main import handle_watchlist
    msg = handle_watchlist({
        "name": "watchlist",
        "options": [{"name": "doesnotexist", "type": 1, "options": []}],
    })
    assert msg.startswith("❌")


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
