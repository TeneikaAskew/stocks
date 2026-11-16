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
import shlex
import subprocess
from pathlib import Path

import pytest

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


def test_notifier_can_read_audit_evidence_without_swallowing_iam_errors():
    body = _deploy_notifier_body()
    commands = re.findall(r'gcloud projects add-iam-policy-binding.*?(?=\n\n)', body, re.DOTALL)
    logging_bindings = [command for command in commands if '--role="roles/logging.viewer"' in command]
    assert len(logging_bindings) == 1
    assert '--member="serviceAccount:${notifier_sa}"' in logging_bindings[0]
    assert "||" not in logging_bindings[0]


def test_notifier_identity_and_secrets_are_isolated_from_trading_jobs():
    body = _deploy_notifier_body()
    assert 'local notifier_sa="${NOTIFIER_SERVICE}@${PROJECT_ID}.iam.gserviceaccount.com"' in body
    assert '--service-account "${notifier_sa}"' in body
    assert '--role="roles/run.viewer"' in body
    assert 'for secret in github-pat github-repo discord-webhook-gcp' in body
    assert "DB_SECRET_FLAG" not in body


@pytest.mark.parametrize("failure", ["none", "account", "secret", "run", "logging"])
def test_notifier_deployment_setup_is_fail_visible_and_precedes_revision(tmp_path, failure):
    calls = tmp_path / "gcloud-calls"
    script = r'''
set -euo pipefail
PROJECT_ID=test-project
REGION=us-east1
NOTIFIER_SERVICE=failure-notifier
NOTIFIER_TOPIC=failures
NOTIFIER_SUB=failures-push
NOTIFIER_SINK=failures-sink
SA_EMAIL=trading-runner@test-project.iam.gserviceaccount.com
IMAGE_REF=test-image
gcloud() {
  printf '%s\n' "$*" >> CALL_FILE
  case "$*" in
    'iam service-accounts describe '*) return 1 ;;
    'iam service-accounts create '*) if [ FAILURE = account ]; then return 1; fi ;;
    'secrets add-iam-policy-binding discord-webhook-gcp '*) if [ FAILURE = secret ]; then return 1; fi ;;
    'projects add-iam-policy-binding '*roles/run.viewer*) if [ FAILURE = run ]; then return 1; fi ;;
    'projects add-iam-policy-binding '*roles/logging.viewer*) if [ FAILURE = logging ]; then return 1; fi ;;
    'run services describe '*) printf '%s\n' 'https://notifier.example.test' ;;
    'projects describe '*) printf '%s\n' '123456' ;;
    'logging sinks describe '*) printf '%s\n' 'serviceAccount:sink@example.test' ;;
  esac
  return 0
}
deploy_notifier() {
FUNCTION_BODY
}
deploy_notifier
'''.replace('CALL_FILE', shlex.quote(str(calls))).replace('FAILURE', shlex.quote(failure)).replace('FUNCTION_BODY', _deploy_notifier_body())
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    commands = calls.read_text().splitlines()
    deployed = [c for c in commands if c.startswith("run deploy ")]
    if failure != "none":
        assert result.returncode != 0
        assert not deployed, "missing access must not publish a revision"
        return
    assert result.returncode == 0, result.stderr
    assert len(deployed) == 1
    assert '--service-account failure-notifier@test-project.iam.gserviceaccount.com' in deployed[0]
    assert 'DB_PASS=' not in deployed[0]
    deploy_index = commands.index(deployed[0])
    grants = [c for c in commands if c.startswith(("secrets add-iam-policy-binding", "projects add-iam-policy-binding"))]
    assert len(grants) == 5
    assert all(commands.index(c) < deploy_index for c in grants)
    assert all('serviceAccount:failure-notifier@test-project.iam.gserviceaccount.com' in c for c in grants)
    push = next(c for c in commands if c.startswith("pubsub subscriptions create "))
    scheduler = next(c for c in commands if c.startswith("scheduler jobs create http "))
    assert '--push-auth-service-account=trading-runner@test-project.iam.gserviceaccount.com' in push
    assert '--oidc-service-account-email trading-runner@test-project.iam.gserviceaccount.com' in scheduler


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
