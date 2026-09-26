"""Unit tests for gcp/audit_infra_drift.py.

Pins the contract of the drift checks:
  - check_floating_images: flags trading-system jobs whose spec names an
    image tag, which Cloud Run resolves at each execution (#1171).
  - check_scheduler_orphans: flags scheduler entries that fire a
    Cloud Run Job which no longer exists.
  - check_scheduler_state: flags schedulers that are not ENABLED (#833).

The gcloud calls themselves are mocked — we test the pure decision logic.
"""
from __future__ import annotations

from unittest.mock import patch


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


# ──────────────────── #833 — paused schedulers are drift ────────────────────

def test_paused_scheduler_is_flagged():
    """#833 (audit D1): `signal-quality-report-hourly` sat PAUSED for four
    months with nothing in the repo recording why. Nothing in the detector
    read scheduler state. A PAUSED scheduler that deploy.sh would (re)create
    ENABLED is drift either way — resume it or retire it in deploy.sh."""
    from gcp import audit_infra_drift as mod

    with patch.object(mod, "list_schedulers", return_value=[
        {"name": "signal-quality-report-hourly", "target_job": "signal-quality-report",
         "uri": "..../jobs/signal-quality-report:run", "state": "PAUSED"},
        {"name": "premarket-brief-daily", "target_job": "premarket-brief",
         "uri": "..../jobs/premarket-brief:run", "state": "ENABLED"},
    ]):
        r = mod.Report()
        mod.check_scheduler_state(r)

    assert [(f.check, f.target) for f in r.findings] == [("scheduler-paused", "signal-quality-report-hourly")]
    assert "PAUSED" in r.findings[0].detail


def test_scheduler_state_missing_is_reported_not_assumed_enabled():
    """A listing row without `state` (older shape) must not pass as ENABLED."""
    from gcp import audit_infra_drift as mod

    with patch.object(mod, "list_schedulers", return_value=[
        {"name": "x", "target_job": "y", "uri": "..../jobs/y:run"},
    ]):
        r = mod.Report()
        mod.check_scheduler_state(r)

    assert r.findings == []
    assert any("state" in e for e in r.errors)


def test_main_runs_all_checks():
    from gcp import audit_infra_drift as mod
    calls = []
    with patch.object(mod, "check_floating_images", side_effect=lambda r: calls.append("image")), \
         patch.object(mod, "check_scheduler_orphans", side_effect=lambda r: calls.append("orphans")), \
         patch.object(mod, "check_scheduler_state", side_effect=lambda r: calls.append("state")), \
         patch.object(mod, "post_to_discord", return_value=True):
        assert mod.main() == 0
    assert set(calls) == {"image", "orphans", "state"}


# ──────────────── #1171 — a job pinned by digest is not drift ────────────────
#
# Cloud Run resolves a job's image TAG at each execution (measured 2026-09-25,
# #1171), so the check that compared each job's last execution with its tag's
# current digest rested on a false premise: a job whose spec names a tag runs
# whatever the tag holds NEXT time, and a job pinned by digest runs exactly
# that digest. These go through main(), so they describe what the daily post
# says rather than which function says it.

_RESEARCH_BUILD = "sha256:" + "c" * 64
_MAIN_LATEST = "sha256:" + "a" * 64


def _audit_summary(jobs, last_run_image):
    # The three create=True patches feed the comparison this replaced, so the
    # two tests below also run against the pre-#1171 module, where both fail.
    from gcp import audit_infra_drift as mod
    with patch.object(mod, "list_run_jobs", return_value=jobs), \
         patch.object(mod, "list_schedulers", return_value=[]), \
         patch.object(mod, "latest_image_digest", return_value=_MAIN_LATEST, create=True), \
         patch.object(mod, "resolve_tag_digest", return_value=_MAIN_LATEST, create=True), \
         patch.object(mod, "latest_execution_image", return_value=last_run_image, create=True), \
         patch.object(mod, "post_to_discord", return_value=True) as post:
        assert mod.main() == 0
    return post.call_args[0][0]


def test_a_job_pinned_by_digest_is_not_drift():
    """On 2026-09-26 the daily post flagged `magnitude-inference`, pinned to
    the research build's digest, against `:latest`, and advised
    `gcloud run jobs update --image=...:latest`: the main image, which lacks
    the research stack. After `pin-floating` every job is pinned by digest,
    so every research job would get that advice every day."""
    summary = _audit_summary(
        [{"name": "magnitude-inference", "image": f"..../trading-system@{_RESEARCH_BUILD}"}],
        last_run_image=f"..../trading-system@{_RESEARCH_BUILD}")
    assert "magnitude-inference" not in summary, summary
    assert ":latest" not in summary, summary


def test_a_job_whose_spec_names_a_tag_is_flagged_with_pin_floating():
    """A spec naming a tag floats: every build of the tag reaches the job at
    its next run. The old check stayed silent whenever the job's last run
    matched the tag's current digest, which says nothing about the next."""
    summary = _audit_summary(
        [{"name": "premarket-brief", "image": "..../trading-system"},
         {"name": "strat-engine", "image": "..../trading-system:research"}],
        last_run_image=f"..../trading-system@{_MAIN_LATEST}")
    assert "premarket-brief" in summary and "strat-engine" in summary, summary
    assert "pin-floating" in summary, summary


def test_check_floating_images_flags_every_tag_and_no_digest():
    from gcp import audit_infra_drift as mod
    with patch.object(mod, "list_run_jobs", return_value=[
        {"name": "tagless", "image": "..../trading-system"},
        {"name": "latest", "image": "..../trading-system:latest"},
        {"name": "research", "image": "..../trading-system:research"},
        {"name": "handmade", "image": "..../trading-system:spx-removal-fred-20260516"},
        {"name": "pinned", "image": f"..../trading-system@{_MAIN_LATEST}"},
        {"name": "other-image", "image": "gcr.io/p/solyra-api:latest"},
    ]):
        r = mod.Report()
        mod.check_floating_images(r)
    got = {f.target: f for f in r.findings}
    assert set(got) == {"tagless", "latest", "research", "handmade"}
    assert {f.check for f in r.findings} == {"image-floating"}
    assert "trading-system:latest" in got["tagless"].detail
    assert "trading-system:spx-removal-fred-20260516" in got["handmade"].detail
    assert all("pin-floating" in f.detail for f in r.findings)
    assert r.errors == []


def test_check_floating_images_reports_an_unreadable_listing_or_image():
    """A job list that cannot be read, or a job with no image in its spec,
    is an error in the post, never an empty result."""
    from gcp import audit_infra_drift as mod
    with patch.object(mod, "list_run_jobs", side_effect=RuntimeError("403")):
        r = mod.Report()
        mod.check_floating_images(r)
    assert r.findings == [] and any("403" in e for e in r.errors)
    with patch.object(mod, "list_run_jobs", return_value=[{"name": "odd", "image": ""}]):
        r = mod.Report()
        mod.check_floating_images(r)
    assert r.findings == [] and any("odd" in e for e in r.errors)
