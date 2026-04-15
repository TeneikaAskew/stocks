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
