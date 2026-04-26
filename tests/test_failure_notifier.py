"""Unit tests for gcp/failure_notifier.py."""
from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from gcp import failure_notifier as fn


# ── Pub/Sub envelope parsing ────────────────────────────────────────────────
def _make_envelope(log_entry: dict) -> bytes:
    data = base64.b64encode(json.dumps(log_entry).encode()).decode()
    return json.dumps({"message": {"data": data, "messageId": "1"}}).encode()


def test_parse_pubsub_envelope_decodes_log_entry():
    log_entry = {"severity": "ERROR", "textPayload": "boom"}
    envelope = _make_envelope(log_entry)

    parsed = fn.parse_pubsub_envelope(envelope)

    assert parsed["severity"] == "ERROR"
    assert parsed["textPayload"] == "boom"


def test_parse_pubsub_envelope_handles_empty_data():
    envelope = json.dumps({"message": {"messageId": "1"}}).encode()
    assert fn.parse_pubsub_envelope(envelope) == {}


def test_parse_pubsub_envelope_handles_non_json_payload():
    raw = base64.b64encode(b"plain text crash").decode()
    envelope = json.dumps({"message": {"data": raw}}).encode()

    parsed = fn.parse_pubsub_envelope(envelope)

    assert parsed["textPayload"] == "plain text crash"


# ── Detail extraction ────────────────────────────────────────────────────────
def test_extract_failure_details_pulls_job_name_and_builds_log_url(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    log_entry = {
        "resource": {
            "type": "cloud_run_job",
            "labels": {"job_name": "fetch-etf-options", "location": "us-east1"},
        },
        "labels": {"run.googleapis.com/execution_name": "fetch-etf-options-abc123"},
        "severity": "ERROR",
        "timestamp": "2026-04-14T12:00:00Z",
        "textPayload": "Traceback...",
    }

    details = fn.extract_failure_details(log_entry)

    assert details["job_name"] == "fetch-etf-options"
    assert details["execution_name"] == "fetch-etf-options-abc123"
    assert "fetch-etf-options-abc123" in details["log_url"]
    assert "project=test-project" in details["log_url"]
    assert details["message"] == "Traceback..."


def test_extract_failure_details_defaults_when_fields_missing():
    details = fn.extract_failure_details({})

    assert details["job_name"] == "unknown-job"
    assert details["execution_name"] == ""
    assert details["message"]  # non-empty fallback


# ── Discord payload ──────────────────────────────────────────────────────────
def test_build_discord_payload_truncates_long_messages():
    details = {
        "job_name": "j",
        "execution_name": "e",
        "severity": "ERROR",
        "timestamp": "2026-04-14T00:00:00Z",
        "message": "x" * 2000,
        "log_url": "https://example.test/logs",
        "project_id": "p",
        "location": "us-east1",
    }

    payload = fn.build_discord_payload(details)

    embed = payload["embeds"][0]
    error_field = next(f for f in embed["fields"] if f["name"] == "Error")
    assert "…" in error_field["value"]
    assert len(error_field["value"]) < 900
    assert embed["url"] == "https://example.test/logs"
    assert embed["color"] == 0xE74C3C


# ── GitHub issue dedup ───────────────────────────────────────────────────────
@patch("gcp.failure_notifier.requests.post")
@patch("gcp.failure_notifier.requests.get")
def test_create_or_update_comments_on_existing_issue(mock_get, mock_post):
    mock_get.return_value = MagicMock(
        status_code=200, json=lambda: [{"number": 42}]
    )
    mock_get.return_value.raise_for_status = MagicMock()
    mock_post.return_value = MagicMock(status_code=201, json=lambda: {})
    mock_post.return_value.raise_for_status = MagicMock()

    details = {
        "job_name": "premarket-brief",
        "execution_name": "pb-xyz",
        "severity": "ERROR",
        "timestamp": "2026-04-14T00:00:00Z",
        "message": "oops",
        "log_url": "https://example.test/logs",
        "project_id": "p",
        "location": "us-east1",
    }

    number, created = fn.create_or_update_github_issue("owner/repo", "ghp_test", details)

    assert number == 42
    assert created is False
    # Should have POSTed exactly one comment, not a new issue
    assert mock_post.call_count == 1
    posted_url = mock_post.call_args[0][0]
    assert "/issues/42/comments" in posted_url


@patch("gcp.failure_notifier.requests.post")
@patch("gcp.failure_notifier.requests.get")
def test_create_or_update_creates_new_issue_when_none_exists(mock_get, mock_post):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
    mock_get.return_value.raise_for_status = MagicMock()
    mock_post.return_value = MagicMock(status_code=201, json=lambda: {"number": 99})
    mock_post.return_value.raise_for_status = MagicMock()

    details = {
        "job_name": "signal-monitor",
        "execution_name": "sm-xyz",
        "severity": "ERROR",
        "timestamp": "2026-04-14T00:00:00Z",
        "message": "crash",
        "log_url": "https://example.test/logs",
        "project_id": "p",
        "location": "us-east1",
    }

    number, created = fn.create_or_update_github_issue("owner/repo", "ghp_test", details)

    assert number == 99
    assert created is True
    posted_url = mock_post.call_args[0][0]
    assert posted_url.endswith("/repos/owner/repo/issues")
    body = mock_post.call_args.kwargs["json"]
    assert "gcp-job-failure" in body["labels"]
    assert "signal-monitor" in body["labels"]


# ── End-to-end handler ───────────────────────────────────────────────────────
def test_handle_notification_skips_self_loop(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
    monkeypatch.setenv("GITHUB_PAT", "ghp_x")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")

    envelope = _make_envelope(
        {
            "resource": {"labels": {"job_name": "failure-notifier"}},
            "severity": "ERROR",
            "textPayload": "self",
        }
    )

    with patch("gcp.failure_notifier.send_discord") as mock_discord, patch(
        "gcp.failure_notifier.create_or_update_github_issue"
    ) as mock_gh:
        status, _ = fn.handle_notification(envelope)

    assert status == 204
    mock_discord.assert_not_called()
    mock_gh.assert_not_called()


def test_handle_notification_skips_gracefully_when_env_missing(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)

    envelope = _make_envelope(
        {
            "resource": {"labels": {"job_name": "fetch-market-data"}},
            "severity": "ERROR",
            "textPayload": "boom",
        }
    )

    status, _ = fn.handle_notification(envelope)

    # No destinations configured → still ack (204), no exception
    assert status == 204


def test_handle_notification_fires_both_channels(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
    monkeypatch.setenv("GITHUB_PAT", "ghp_x")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    envelope = _make_envelope(
        {
            "resource": {
                "labels": {"job_name": "fetch-etf-options", "location": "us-east1"}
            },
            "labels": {"run.googleapis.com/execution_name": "exec-1"},
            "severity": "ERROR",
            "timestamp": "2026-04-14T00:00:00Z",
            "textPayload": "oops",
        }
    )

    with patch("gcp.failure_notifier.send_discord") as mock_discord, patch(
        "gcp.failure_notifier.create_or_update_github_issue", return_value=(7, True)
    ) as mock_gh:
        status, _ = fn.handle_notification(envelope)

    assert status == 204
    mock_discord.assert_called_once()
    mock_gh.assert_called_once()
    details = mock_gh.call_args[0][2]
    assert details["job_name"] == "fetch-etf-options"


# ── Tenacity retry behaviour ────────────────────────────────────────────────


def test_send_discord_retries_on_transient_failure(monkeypatch):
    """First two attempts fail, third succeeds. Tenacity must retry
    rather than abort on the first 5xx."""
    call_log = []

    def fake_post(url, json=None, timeout=None):
        call_log.append(url)
        resp = MagicMock()
        if len(call_log) < 3:
            resp.raise_for_status.side_effect = RuntimeError("502 transient")
        else:
            resp.raise_for_status.return_value = None
            resp.status_code = 204
        return resp

    monkeypatch.setattr(fn.requests, "post", fake_post)
    # Speed up the test — replace the wait with no-op
    monkeypatch.setattr(fn, "wait_exponential", lambda *a, **k: lambda *a2, **k2: 0)

    fn.send_discord("https://discord.example/hook", {"content": "hi"})
    assert len(call_log) == 3, "tenacity must retry until success"


def test_send_discord_reraises_after_max_attempts(monkeypatch):
    """All 3 attempts fail → tenacity reraises (we don't want to swallow
    a persistently failing webhook silently)."""
    def fake_post(*a, **k):
        resp = MagicMock()
        resp.raise_for_status.side_effect = RuntimeError("503 still down")
        return resp

    monkeypatch.setattr(fn.requests, "post", fake_post)
    with pytest.raises(RuntimeError, match="503"):
        fn.send_discord("https://x", {"content": "hi"})


def test_create_issue_retries_on_transient_failure(monkeypatch):
    """Same retry contract on the GitHub side."""
    call_log = []

    def fake_post(url, headers=None, json=None, timeout=None):
        call_log.append(url)
        resp = MagicMock()
        if len(call_log) < 2:
            resp.raise_for_status.side_effect = RuntimeError("500 transient")
        else:
            resp.raise_for_status.return_value = None
            resp.json.return_value = {"number": 1234}
        return resp

    monkeypatch.setattr(fn.requests, "post", fake_post)
    n = fn.create_issue("owner/repo", "title", "body", ["bug"], token="ghp_xxx")
    assert n == 1234
    assert len(call_log) == 2


def test_find_existing_issue_swallows_request_exception(monkeypatch):
    """The lookup is best-effort — if GitHub is down, returning None and
    creating a new issue is preferable to crashing the notifier loop."""
    def fake_get(*a, **k):
        raise fn.requests.RequestException("github unreachable")

    monkeypatch.setattr(fn.requests, "get", fake_get)
    assert fn.find_existing_issue("owner/repo", ["x"], token="t") is None


# ── HTTP Handler — do_POST / do_GET ─────────────────────────────────────────


class _MockSocket:
    """Stand-in for the BaseHTTPRequestHandler socket layer. Captures
    response bytes so tests can assert what the handler sent back."""
    def __init__(self, request_bytes: bytes):
        self._req = request_bytes
        self.sent: list = []

    def makefile(self, mode, *args, **kwargs):
        import io
        if mode == "rb":
            return io.BytesIO(self._req)
        # The handler writes to wfile; we use a BytesIO that records
        # everything for assertion
        buf = io.BytesIO()
        self.sent.append(buf)
        return buf


def _invoke_handler(http_method: str, body: bytes, monkeypatch=None,
                    handle_returns=(204, "")):
    """Drive the BaseHTTPRequestHandler synchronously without spawning
    a real HTTP server. Patches `handle_notification` so we test the
    HTTP layer in isolation."""
    if monkeypatch is not None:
        monkeypatch.setattr(fn, "handle_notification",
                            lambda raw: handle_returns)

    request_line = (
        f"{http_method} / HTTP/1.1\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"\r\n"
    ).encode() + body

    class _ConnectingHandler(fn.Handler):
        # The base class auto-calls handle() in __init__; we let it run
        # and capture via the mock socket above.
        pass

    sock = _MockSocket(request_line)
    handler = _ConnectingHandler.__new__(_ConnectingHandler)
    handler.request = sock
    handler.client_address = ("127.0.0.1", 12345)
    handler.server = None
    handler.rfile = sock.makefile("rb")

    import io
    handler.wfile = io.BytesIO()
    # Manually parse the request line + headers (BaseHTTPRequestHandler does this)
    handler.raw_requestline = handler.rfile.readline(65537)
    handler.parse_request()
    if http_method == "POST":
        handler.do_POST()
    else:
        handler.do_GET()
    return handler.wfile.getvalue()


def test_handler_get_returns_health_check(monkeypatch):
    """GET / → 200 ok body. Used by Cloud Run health probes."""
    out = _invoke_handler("GET", b"")
    assert b"HTTP/1.0 200" in out or b"HTTP/1.1 200" in out
    assert out.endswith(b"ok")


def test_handler_post_proxies_to_handle_notification(monkeypatch):
    """POST body is passed through to handle_notification; the returned
    (status, message) tuple becomes the HTTP response."""
    out = _invoke_handler(
        "POST", b'{"message":{"data":"abc"}}',
        monkeypatch=monkeypatch, handle_returns=(204, ""),
    )
    assert b"HTTP/1.0 204" in out or b"HTTP/1.1 204" in out


def test_handler_post_writes_error_message_in_body(monkeypatch):
    """500 from handle_notification → message is written as the response
    body so log readers can see why."""
    out = _invoke_handler(
        "POST", b'{"x":1}',
        monkeypatch=monkeypatch,
        handle_returns=(500, "discord webhook failed"),
    )
    assert b"500" in out
    assert b"discord webhook failed" in out


def test_handler_post_clamps_oversized_body(monkeypatch):
    """`MAX_BODY` clamps `Content-Length` so a malicious / runaway client
    can't tie up the worker reading 100 MB. The handler must read AT MOST
    MAX_BODY bytes and then dispatch normally."""
    received_lengths: list[int] = []

    def fake_handle(raw):
        received_lengths.append(len(raw))
        return (204, "")

    # Send Content-Length = MAX_BODY + 1000, but only MAX_BODY bytes
    # of actual body — handler should read MAX_BODY-sized window
    body = b"x" * (fn.MAX_BODY + 1000)
    monkeypatch.setattr(fn, "handle_notification", fake_handle)

    request_line = (
        f"POST / HTTP/1.1\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"\r\n"
    ).encode() + body

    import io
    sock = _MockSocket(request_line)
    handler = fn.Handler.__new__(fn.Handler)
    handler.request = sock
    handler.client_address = ("127.0.0.1", 12345)
    handler.server = None
    handler.rfile = sock.makefile("rb")
    handler.wfile = io.BytesIO()
    handler.raw_requestline = handler.rfile.readline(65537)
    handler.parse_request()
    handler.do_POST()

    assert received_lengths == [fn.MAX_BODY], (
        "handler must clamp the read at MAX_BODY"
    )
