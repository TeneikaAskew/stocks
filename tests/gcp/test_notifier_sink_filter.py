"""Regression test for the gcp-job-failures Cloud Logging sink filter.

deploy_notifier()'s sink_filter originally excluded every
`cloudaudit.googleapis.com` log via a blanket `logName:"run.googleapis.com"`
clause, to suppress the ERROR-severity audit noise `gcloud run jobs update`
generates (Jobs.CreateJob ALREADY_EXISTS before falling back to
Jobs.UpdateJob). That blanket exclusion had a blind spot: a job that calls
sys.exit(1) after its own INFO/WARNING logging (no ERROR-severity Python
traceback) has no run.googleapis.com log line at severity>=ERROR at all —
the only severity>=ERROR record is the audit log's Jobs.RunJob entry
("Execution <name> has failed to complete..."), which the blanket exclusion
silently dropped. signal-monitor-eod-resolver hit this twice (2026-07-09,
2026-07-14) with zero Discord/GitHub notification either time.

The fix excludes only the two noisy methods (CreateJob/UpdateJob) instead of
the whole cloudaudit.googleapis.com log family, letting Jobs.RunJob failures
through. Verified manually against 30 days of production Cloud Logging
before merging (see PR description) — this test pins the filter's structure
so a future edit can't silently reintroduce either the old blind spot or the
original deploy-noise false positives.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPLOY_SH = (REPO / "gcp/deploy.sh").read_text()

# Real methodName values observed in production Cloud Logging (30-day dry
# run) — the same audit sub-log family uses different formats depending on
# whether the entry lands on .../system_event or .../activity.
_REAL_CREATE_JOB_SHORT = "/Jobs.CreateJob"
_REAL_CREATE_JOB_FULL = "google.cloud.run.v1.Jobs.CreateJob"
_REAL_UPDATE_JOB_FULL = "google.cloud.run.v1.Jobs.UpdateJob"
_REAL_RUN_JOB_FAILURE = "/Jobs.RunJob"  # e.g. signal-monitor-eod-resolver-6wb24


def _deploy_notifier_body() -> str:
    m = re.search(r"deploy_notifier\(\)\s*\{(.*?)\n\}", DEPLOY_SH, re.DOTALL)
    assert m is not None, "deploy_notifier function not found in deploy.sh"
    return m.group(1)


def _sink_filter() -> str:
    body = _deploy_notifier_body()
    m = re.search(r"sink_filter='(.*?)'\n", body, re.DOTALL)
    assert m is not None, "sink_filter assignment not found in deploy_notifier()"
    return m.group(1)


def _excluded_method_markers(sink_filter: str) -> list[str]:
    """Extract the substrings excluded via `protoPayload.methodName:"..."`."""
    return re.findall(r'protoPayload\.methodName:"([^"]+)"', sink_filter)


def test_sink_filter_does_not_blanket_exclude_run_googleapis_com():
    """The old blind-spot clause must not reappear."""
    sink_filter = _sink_filter()
    assert 'logName:"run.googleapis.com"' not in sink_filter, (
        "sink_filter reintroduces the blanket run.googleapis.com-only clause "
        "that silently dropped Jobs.RunJob failure audit entries (the "
        "signal-monitor-eod-resolver 2026-07-09/07-14 blind spot)"
    )


def test_sink_filter_still_requires_error_severity_and_excludes_self():
    sink_filter = _sink_filter()
    assert "severity>=ERROR" in sink_filter
    assert 'resource.labels.job_name!="' in sink_filter


def test_sink_filter_excludes_createjob_and_updatejob_by_substring():
    """Must use `:` (contains) markers that match BOTH observed methodName
    formats, not an exact `=` match against only one literal form."""
    markers = _excluded_method_markers(_sink_filter())
    assert any("CreateJob" in m for m in markers), "no CreateJob exclusion marker"
    assert any("UpdateJob" in m for m in markers), "no UpdateJob exclusion marker"

    for marker in markers:
        if "CreateJob" in marker or "UpdateJob" in marker:
            # A marker that's the exact fully-qualified or short literal
            # would fail to match the OTHER real-world form via substring
            # containment — it must be a bare method name fragment.
            assert marker in _REAL_CREATE_JOB_SHORT or marker in _REAL_CREATE_JOB_FULL \
                or marker in _REAL_UPDATE_JOB_FULL, (
                f"exclusion marker {marker!r} doesn't match observed "
                f"production methodName formats"
            )


def test_sink_filter_semantics_exclude_noise_but_admit_real_failure():
    """Re-implement the filter's `NOT (A:x OR A:y)` methodName clause in
    Python and assert it produces the correct decision for each of the
    three real-world methodName values captured from 30 days of production
    Cloud Logging."""
    markers = _excluded_method_markers(_sink_filter())

    def is_excluded(method_name: str) -> bool:
        return any(marker in method_name for marker in markers)

    assert is_excluded(_REAL_CREATE_JOB_SHORT) is True
    assert is_excluded(_REAL_CREATE_JOB_FULL) is True
    assert is_excluded(_REAL_UPDATE_JOB_FULL) is True
    # The actual failure signature this fix exists to surface must NOT be
    # excluded.
    assert is_excluded(_REAL_RUN_JOB_FAILURE) is False
