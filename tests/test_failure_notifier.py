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



@patch("gcp.failure_notifier.time.sleep")
@patch("gcp.failure_notifier.random.uniform", return_value=0.0)
@patch("gcp.failure_notifier.requests.post")
@patch("gcp.failure_notifier.requests.get")
def test_create_or_update_closes_race_duplicates(mock_get, mock_post, _mock_uniform, mock_sleep):
    """After creating an issue, if re-query finds duplicates the non-canonical
    ones should be closed and their content routed to the canonical issue."""
    # First GET (find_existing): no existing issue
    # Second GET (find_all): two issues already open — #10 (ours) + #9 (peer)
    # Third POST (close_issue comment on #10)
    # Fourth PATCH (close #10)
    # Fifth POST (add content from #10 to canonical #9)
    first_get = MagicMock(status_code=200, json=lambda: [], raise_for_status=MagicMock())
    second_get = MagicMock(
        status_code=200,
        json=lambda: [{"number": 10}, {"number": 9}],
        raise_for_status=MagicMock(),
    )
    mock_get.side_effect = [first_get, second_get]

    create_resp = MagicMock(status_code=201, json=lambda: {"number": 10}, raise_for_status=MagicMock())
    comment_resp = MagicMock(status_code=201, json=lambda: {}, raise_for_status=MagicMock())
    close_patch = MagicMock(status_code=200, json=lambda: {}, raise_for_status=MagicMock())
    mock_post.side_effect = [create_resp, comment_resp, comment_resp]

    with patch("gcp.failure_notifier.requests.patch", return_value=close_patch):
        details = {
            "job_name": "fetch-market-data",
            "execution_name": "fmd-race-xyz",
            "severity": "ERROR",
            "timestamp": "2026-06-25T00:00:00Z",
            "message": "crash",
            "log_url": "https://example.test/logs",
            "project_id": "p",
            "location": "us-east1",
        }
        number, created = fn.create_or_update_github_issue("owner/repo", "ghp_test", details)

    # Non-canonical #10 should be closed; canonical #9 returned
    assert number == 9
    assert created is False
    # The 5-second dedup sleep must have been called
    assert any(call.args == (5,) for call in mock_sleep.call_args_list)


@patch("gcp.failure_notifier.time.sleep")
@patch("gcp.failure_notifier.random.uniform", return_value=0.0)
@patch("gcp.failure_notifier.requests.post")
@patch("gcp.failure_notifier.requests.get")
def test_jitter_sleep_called_before_initial_check(mock_get, mock_post, mock_uniform, mock_sleep):
    """random.uniform jitter sleep must fire before find_existing_issue."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: [{"number": 5}], raise_for_status=MagicMock())
    mock_post.return_value = MagicMock(status_code=201, json=lambda: {}, raise_for_status=MagicMock())

    details = {
        "job_name": "some-job",
        "execution_name": "sj-001",
        "severity": "ERROR",
        "timestamp": "2026-06-25T00:00:00Z",
        "message": "err",
        "log_url": "https://example.test/logs",
        "project_id": "p",
        "location": "us-east1",
    }
    fn.create_or_update_github_issue("owner/repo", "ghp_test", details)

    # random.uniform(0, 2) was called to produce the jitter value
    mock_uniform.assert_called_once_with(0, 2)
    # time.sleep was called with the jitter value (0.0 in this test)
    assert mock_sleep.call_args_list[0].args == (0.0,)


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


# ── Race-aware dedupe (close-after-create) ──────────────────────────────────


@patch("gcp.failure_notifier.requests.patch")
@patch("gcp.failure_notifier.requests.post")
@patch("gcp.failure_notifier.requests.get")
def test_create_or_update_closes_race_created_duplicate(mock_get, mock_post, mock_patch):
    """When two notifier instances race and both create issues, the
    second one (higher number) must close itself with a comment routing
    content to the canonical (lower number)."""
    # First GET (find_existing_issue) → no existing
    # Second GET (find_all_open_issues after create) → 2 issues found
    mock_get.side_effect = [
        MagicMock(status_code=200, json=lambda: [], raise_for_status=MagicMock()),
        MagicMock(
            status_code=200,
            json=lambda: [{"number": 100}, {"number": 105}],
            raise_for_status=MagicMock(),
        ),
    ]
    # POST 1: create issue → returns 105 (we lost the race)
    # POST 2: comment on canonical (#100) about closure
    # POST 3: comment on duplicate (#105) before closing
    mock_post.return_value = MagicMock(
        status_code=201,
        json=lambda: {"number": 105},
        raise_for_status=MagicMock(),
    )
    mock_patch.return_value = MagicMock(status_code=200, raise_for_status=MagicMock())

    details = {
        "job_name": "fetch-market-data",
        "execution_name": "abc",
        "severity": "ERROR",
        "timestamp": "2026-05-14T12:00:00Z",
        "message": "ssl error",
        "log_url": "https://example.test/logs",
        "project_id": "p",
        "location": "us-east1",
    }

    number, created = fn.create_or_update_github_issue("owner/repo", "ghp_t", details)

    # Returns the CANONICAL number, not the duplicate we created
    assert number == 100
    assert created is False
    # PATCH was called to close the duplicate
    mock_patch.assert_called_once()
    patched_url = mock_patch.call_args[0][0]
    assert patched_url.endswith("/issues/105")
    assert mock_patch.call_args.kwargs["json"]["state"] == "closed"


@patch("gcp.failure_notifier.requests.patch")
@patch("gcp.failure_notifier.requests.post")
@patch("gcp.failure_notifier.requests.get")
def test_create_or_update_no_dedupe_when_only_one_issue(mock_get, mock_post, mock_patch):
    """When the post-create re-query returns only our newly-created issue,
    no dedupe close happens."""
    mock_get.side_effect = [
        MagicMock(status_code=200, json=lambda: [], raise_for_status=MagicMock()),
        MagicMock(
            status_code=200,
            json=lambda: [{"number": 99}],
            raise_for_status=MagicMock(),
        ),
    ]
    mock_post.return_value = MagicMock(
        status_code=201,
        json=lambda: {"number": 99},
        raise_for_status=MagicMock(),
    )

    number, created = fn.create_or_update_github_issue(
        "owner/repo", "ghp_t",
        {
            "job_name": "fetch-news-sentiment",
            "execution_name": "x",
            "severity": "ERROR",
            "timestamp": "2026-05-14T12:00:00Z",
            "message": "ok",
            "log_url": "https://e.test",
            "project_id": "p",
            "location": "us-east1",
        },
    )

    assert number == 99
    assert created is True
    mock_patch.assert_not_called()  # no close


# ── close_issue helper ──────────────────────────────────────────────────────


@patch("gcp.failure_notifier.requests.patch")
@patch("gcp.failure_notifier.requests.post")
def test_close_issue_posts_comment_then_patches_state(mock_post, mock_patch):
    mock_post.return_value = MagicMock(status_code=201, raise_for_status=MagicMock())
    mock_patch.return_value = MagicMock(status_code=200, raise_for_status=MagicMock())

    fn.close_issue("owner/repo", 42, "all good now", "ghp_t")

    # POST = comment, PATCH = state change
    posted_url = mock_post.call_args[0][0]
    patched_url = mock_patch.call_args[0][0]
    assert "/issues/42/comments" in posted_url
    assert patched_url.endswith("/issues/42")
    assert mock_patch.call_args.kwargs["json"] == {"state": "closed"}


@patch("gcp.failure_notifier.requests.patch")
def test_close_issue_skips_comment_when_blank(mock_patch):
    mock_patch.return_value = MagicMock(status_code=200, raise_for_status=MagicMock())
    fn.close_issue("owner/repo", 7, "", "t")
    # Only PATCH was called; no comment POST
    mock_patch.assert_called_once()


# ── reconcile_closures ──────────────────────────────────────────────────────


def test_reconcile_closures_closes_recovered_jobs(monkeypatch):
    """Open issues for a job whose latest execution succeeded must be closed."""
    # Two issues open: one for fetch-market-data (recovered), one for
    # signal-monitor (still failing).
    open_issues = [
        {"number": 474, "labels": [
            {"name": "automated"}, {"name": "gcp-job-failure"},
            {"name": "fetch-market-data"},
        ]},
        {"number": 475, "labels": [
            {"name": "gcp-job-failure"}, {"name": "fetch-market-data"},
        ]},
        {"number": 480, "labels": [
            {"name": "gcp-job-failure"}, {"name": "signal-monitor"},
        ]},
    ]

    def fake_find_all(repo, labels, token):
        return open_issues

    def fake_status(job_name, project_id, region):
        if job_name == "fetch-market-data":
            return {"name": "tpw6z", "completed": True, "succeeded": True,
                    "completion_time": "2026-05-14T12:06:47Z"}
        if job_name == "signal-monitor":
            return {"name": "abc", "completed": True, "succeeded": False,
                    "completion_time": "2026-05-14T13:00:00Z"}
        return None

    closed: list[int] = []

    def fake_close(repo, num, comment, token):
        closed.append(num)

    monkeypatch.setattr(fn, "find_all_open_issues", fake_find_all)
    monkeypatch.setattr(fn, "_get_latest_execution_status", fake_status)
    monkeypatch.setattr(fn, "close_issue", fake_close)

    summary = fn.reconcile_closures(
        "owner/repo", "ghp_t", "my-project", "us-east1",
    )

    assert sorted(closed) == [474, 475]  # both fetch-market-data issues closed
    assert summary["closed"] == 2
    assert summary["still_failing"] == 1
    assert summary["jobs_inspected"] == 2
    assert summary["issues_inspected"] == 3


def test_reconcile_closures_handles_unknown_status(monkeypatch):
    """When Cloud Run query fails (404 / auth / network), the job is
    marked unknown and the issue stays open."""
    monkeypatch.setattr(fn, "find_all_open_issues", lambda *a, **kw: [
        {"number": 999, "labels": [
            {"name": "gcp-job-failure"}, {"name": "ghost-job"},
        ]},
    ])
    monkeypatch.setattr(fn, "_get_latest_execution_status",
                        lambda *a, **kw: None)
    closed: list[int] = []
    monkeypatch.setattr(fn, "close_issue",
                        lambda *a, **kw: closed.append(a[1]))

    summary = fn.reconcile_closures("o/r", "t", "p", "us-east1")

    assert closed == []  # no closure
    assert summary["unknown"] == 1
    assert summary["closed"] == 0


def test_reconcile_closures_handles_no_open_issues(monkeypatch):
    """Empty case: no open issues → 0 across the board."""
    monkeypatch.setattr(fn, "find_all_open_issues", lambda *a, **kw: [])
    summary = fn.reconcile_closures("o/r", "t", "p", "us-east1")
    assert summary == {
        "issues_inspected": 0, "jobs_inspected": 0, "closed": 0,
        "still_failing": 0, "unknown": 0,
    }


# ── /reconcile HTTP endpoint ────────────────────────────────────────────────


def test_handle_reconcile_returns_summary_json(monkeypatch):
    monkeypatch.setenv("GITHUB_PAT", "ghp_t")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GCP_PROJECT_ID", "my-project")
    monkeypatch.setenv("GCP_REGION", "us-east1")

    captured = {}

    def fake_reconcile(repo, token, project_id, region):
        captured["repo"] = repo
        captured["project_id"] = project_id
        return {"closed": 3, "still_failing": 1, "issues_inspected": 4,
                "jobs_inspected": 2, "unknown": 0}

    monkeypatch.setattr(fn, "reconcile_closures", fake_reconcile)
    status, body = fn.handle_reconcile()
    assert status == 200
    payload = json.loads(body)
    assert payload["closed"] == 3
    assert captured["repo"] == "owner/repo"
    assert captured["project_id"] == "my-project"


def test_handle_reconcile_503_when_env_missing(monkeypatch):
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    status, body = fn.handle_reconcile()
    assert status == 503
    assert "GITHUB_PAT" in body or "GITHUB_REPO" in body


def test_handler_post_reconcile_routes_to_reconciler(monkeypatch):
    """POST /reconcile invokes handle_reconcile, not handle_notification."""
    notif_called = []
    monkeypatch.setattr(fn, "handle_notification",
                        lambda raw: notif_called.append(1) or (204, ""))
    monkeypatch.setattr(fn, "handle_reconcile",
                        lambda: (200, '{"closed": 0}'))

    request_line = (
        b"POST /reconcile HTTP/1.1\r\n"
        b"Content-Length: 0\r\n"
        b"\r\n"
    )

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

    out = handler.wfile.getvalue()
    assert b"200" in out
    assert b'"closed": 0' in out
    assert notif_called == []  # notify was NOT routed
