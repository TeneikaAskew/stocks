"""Unit tests for gcp/audit_infra_drift.py.

Pins the contract of the two drift checks shipped today:
  - check_image_drift: flags jobs whose executions ran against a digest
    older than current :latest.
  - check_scheduler_orphans: flags scheduler entries that fire a
    Cloud Run Job which no longer exists.

The gcloud calls themselves are mocked — we test the pure decision logic.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


# ──────────────────── Report aggregation ────────────────────

def test_report_summary_empty():
    from gcp.audit_infra_drift import Report
    r = Report()
    assert "no findings" in r.summary()


def test_report_summary_orders_by_severity():
    from gcp.audit_infra_drift import Report
    r = Report()
    r.add("LOW", "x", "a", "low one")
    r.add("HIGH", "x", "b", "high one")
    r.add("MEDIUM", "x", "c", "med one")
    s = r.summary()
    # HIGH should appear before MEDIUM should appear before LOW.
    assert s.index("HIGH") < s.index("MEDIUM") < s.index("LOW")
    assert "3 finding" in s


def test_report_includes_errors_section():
    from gcp.audit_infra_drift import Report
    r = Report()
    r.errors.append("gcloud auth refresh failed")
    s = r.summary()
    assert "check-execution errors" in s
    assert "gcloud auth refresh failed" in s


# ──────────────────── Image-drift logic ────────────────────

def test_image_drift_flags_outdated_pinned_digest(monkeypatch):
    """If a job's latest execution image @sha256 != current :latest, flag."""
    from gcp import audit_infra_drift as mod

    latest = "sha256:" + "a" * 64
    outdated = "sha256:" + "b" * 64

    with patch.object(mod, "latest_image_digest", return_value=latest), \
         patch.object(mod, "list_run_jobs",
                      return_value=[{"name": "fetch-earnings-history",
                                     "image": "..../trading-system:latest"}]), \
         patch.object(mod, "latest_execution_image",
                      return_value=f"..../trading-system@{outdated}"):
        r = mod.Report()
        mod.check_image_drift(r)

    assert len(r.findings) == 1
    f = r.findings[0]
    assert f.check == "image-drift"
    assert f.target == "fetch-earnings-history"
    assert "re-pin" in f.detail.lower() or "update" in f.detail.lower()


def test_image_drift_silent_when_pinned_matches_latest(monkeypatch):
    """If the digests match, no finding."""
    from gcp import audit_infra_drift as mod

    digest = "sha256:" + "a" * 64

    with patch.object(mod, "latest_image_digest", return_value=digest), \
         patch.object(mod, "list_run_jobs",
                      return_value=[{"name": "j1",
                                     "image": "..../trading-system:latest"}]), \
         patch.object(mod, "latest_execution_image",
                      return_value=f"..../trading-system@{digest}"):
        r = mod.Report()
        mod.check_image_drift(r)

    assert r.findings == []


def test_image_drift_skips_non_trading_system_image(monkeypatch):
    """Jobs running a different base image (e.g. research) are skipped."""
    from gcp import audit_infra_drift as mod

    latest = "sha256:" + "a" * 64

    with patch.object(mod, "latest_image_digest", return_value=latest), \
         patch.object(mod, "list_run_jobs",
                      return_value=[{"name": "strat-engine",
                                     "image": "..../trading-system:research"}]):
        r = mod.Report()
        # trading-system:research IS picked up by the substring check —
        # then skipped at the inner if-not-exec_image branch.
        with patch.object(mod, "latest_execution_image", return_value=""):
            mod.check_image_drift(r)

    assert r.findings == []


def test_image_drift_skips_never_executed_jobs(monkeypatch):
    """If a job has no executions yet, can't compare digests — skip."""
    from gcp import audit_infra_drift as mod

    latest = "sha256:" + "a" * 64

    with patch.object(mod, "latest_image_digest", return_value=latest), \
         patch.object(mod, "list_run_jobs",
                      return_value=[{"name": "j-new",
                                     "image": "..../trading-system:latest"}]), \
         patch.object(mod, "latest_execution_image", return_value=""):
        r = mod.Report()
        mod.check_image_drift(r)

    assert r.findings == []


# ──────────────────── Scheduler-orphan logic ────────────────────

def test_scheduler_orphan_flagged_when_target_job_missing():
    from gcp import audit_infra_drift as mod
    with patch.object(mod, "list_schedulers", return_value=[
        {"name": "p7b-daily", "target_job": "p7b-next-candle-classifier",
         "uri": "..../jobs/p7b-next-candle-classifier:run"},
        {"name": "freshness-watchdog-hourly", "target_job": "freshness-watchdog",
         "uri": "..../jobs/freshness-watchdog:run"},
    ]), patch.object(mod, "list_run_jobs", return_value=[
        {"name": "freshness-watchdog", "image": ""},
        {"name": "fetch-market-data", "image": ""},
    ]):
        r = mod.Report()
        mod.check_scheduler_orphans(r)

    assert len(r.findings) == 1
    f = r.findings[0]
    assert f.check == "scheduler-orphan"
    assert f.target == "p7b-daily"
    assert "p7b-next-candle-classifier" in f.detail


def test_scheduler_with_no_cr_target_ignored():
    """Non-Cloud-Run schedulers (e.g. pubsub-only) shouldn't be flagged."""
    from gcp import audit_infra_drift as mod
    with patch.object(mod, "list_schedulers", return_value=[
        {"name": "some-pubsub-cron", "target_job": "",
         "uri": "https://pubsub.googleapis.com/..."},
    ]), patch.object(mod, "list_run_jobs", return_value=[]):
        r = mod.Report()
        mod.check_scheduler_orphans(r)

    assert r.findings == []


# ──────────────────── Discord posting ────────────────────

def test_discord_post_handles_missing_webhook(monkeypatch, capsys):
    """No webhook env → log and return True (graceful no-op)."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    from gcp import audit_infra_drift as mod
    assert mod.post_to_discord("test message") is True


def test_discord_post_truncates_long_message(monkeypatch):
    """Discord's 2000-char limit must not raise; long messages get a
    `(truncated)` marker."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.invalid/wh")
    from gcp import audit_infra_drift as mod
    long = "x" * 5000

    captured = {}
    class _R:
        ok = True
        text = ""
    def _post(url, json=None, timeout=None):
        captured["body"] = (json or {}).get("content", "")
        return _R()
    with patch.object(mod.requests, "post", side_effect=_post):
        mod.post_to_discord(long)

    assert len(captured["body"]) < 2000
    assert "truncated" in captured["body"]


# ──────────────────── latest_execution_image SDK contract ────────────────────
#
# Codex P1 on PR #601: an earlier draft of latest_execution_image had a
# `finally: return ""` that silently overrode the successful return,
# making the function always blank. The Codex review correctly noted
# that mocking latest_execution_image() in the image-drift tests above
# couldn't catch that bug. These tests mock the underlying SDK instead,
# exercising the real function body.


def test_latest_execution_image_returns_image_when_execution_exists():
    """If the job has at least one execution, return its image string."""
    from gcp import audit_infra_drift as mod

    fake_image = "us-east1-docker.pkg.dev/p/r/trading-system@sha256:abcd"
    # The SDK call yields execution objects; we need .template.containers[0].image.
    fake_exec = MagicMock()
    fake_exec.template.containers = [MagicMock(image=fake_image)]

    fake_client = MagicMock()
    fake_client.list_executions.return_value = iter([fake_exec])

    # Patch the import inside the function (it's a local import).
    fake_run_v2 = MagicMock()
    fake_run_v2.ExecutionsClient.return_value = fake_client
    fake_run_v2.ListExecutionsRequest = MagicMock()

    fake_google_cloud = MagicMock(run_v2=fake_run_v2)
    with patch.dict("sys.modules", {
        "google": MagicMock(cloud=fake_google_cloud),
        "google.cloud": fake_google_cloud,
        "google.cloud.run_v2": fake_run_v2,
    }):
        got = mod.latest_execution_image("fetch-earnings-history")

    assert got == fake_image, (
        f"latest_execution_image should return the execution's image; "
        f"got {got!r}. A `return` in a `finally` block on this function "
        f"would silently override the success return — Codex P1 #601."
    )


def test_latest_execution_image_returns_empty_when_no_executions():
    """If the job has zero executions, return empty string (not None)."""
    from gcp import audit_infra_drift as mod

    fake_client = MagicMock()
    fake_client.list_executions.return_value = iter([])  # empty page

    fake_run_v2 = MagicMock()
    fake_run_v2.ExecutionsClient.return_value = fake_client
    fake_run_v2.ListExecutionsRequest = MagicMock()

    fake_google_cloud = MagicMock(run_v2=fake_run_v2)
    with patch.dict("sys.modules", {
        "google": MagicMock(cloud=fake_google_cloud),
        "google.cloud": fake_google_cloud,
        "google.cloud.run_v2": fake_run_v2,
    }):
        got = mod.latest_execution_image("never-executed-job")

    assert got == ""


def test_latest_execution_image_handles_malformed_template():
    """If exe.template.containers is missing/empty, return empty
    string (don't raise)."""
    from gcp import audit_infra_drift as mod

    fake_exec = MagicMock()
    # Simulate AttributeError on .containers[0]
    fake_exec.template.containers = []

    fake_client = MagicMock()
    fake_client.list_executions.return_value = iter([fake_exec])

    fake_run_v2 = MagicMock()
    fake_run_v2.ExecutionsClient.return_value = fake_client
    fake_run_v2.ListExecutionsRequest = MagicMock()

    fake_google_cloud = MagicMock(run_v2=fake_run_v2)
    with patch.dict("sys.modules", {
        "google": MagicMock(cloud=fake_google_cloud),
        "google.cloud": fake_google_cloud,
        "google.cloud.run_v2": fake_run_v2,
    }):
        got = mod.latest_execution_image("malformed-job")

    assert got == ""
