"""deploy_audit_infra_drift and the scheduler role its two scheduler checks need.

audit-infra-drift runs as trading-runner@, which held no Cloud Scheduler role,
so its orphan and paused-scheduler checks answered 403 on every retained run
(#1201). Granting roles/cloudscheduler.viewer takes a project owner. The deploy
checks, tries once, and otherwise prints the owner's command: it never fails
over it, because the audit's other checks still run and its post names the 403.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CODE = "\n".join(l for l in (REPO / "gcp/deploy.sh").read_text().splitlines()
                 if not l.lstrip().startswith("#"))
SA = "sa@proj.iam.gserviceaccount.com"

_GCLOUD = """
    echo "$*" >> "$OUT/calls"
    case "$1 $2" in
      "projects get-iam-policy") [ -z "${POLICY_FAILS:-}" ] || exit 1; printf '%s' "${HAS_ROLE:-}"; exit 0 ;;
      "projects add-iam-policy-binding") exit "${ADD_RC:-1}" ;;
      "run jobs") case " ${FAIL_JOBS:-} " in *" $3 "*) exit 1 ;; esac; exit 0 ;;
    esac
    exit 0
"""


def _fn(name: str) -> str:
    m = re.search(r"^" + name + r"\(\)\s*\{(.*?)^\}", CODE, re.M | re.S)
    assert m, f"{name} not found in deploy.sh"
    return m.group(1)


def _run(tmp_path, call: str, **env) -> tuple[subprocess.CompletedProcess, list[str]]:
    binder = tmp_path / "bin"
    binder.mkdir(exist_ok=True)
    g = binder / "gcloud"
    g.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(_GCLOUD))
    g.chmod(g.stat().st_mode | stat.S_IEXEC)
    full = dict(os.environ, PATH=f"{binder}:{os.environ['PATH']}", OUT=str(tmp_path), **env)
    defs = "\n".join(f"{n}() {{{_fn(n)}}}" for n in
                     ("_ensure_audit_scheduler_viewer", "deploy_audit_infra_drift"))
    script = f"""set -uo pipefail
PROJECT_ID=proj; REGION=us-east1; SA_EMAIL={SA}; IMAGE_REF=img@sha256:1
{defs}
{call}
echo "rc=$?"
"""
    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                          env=full, timeout=60)
    calls = (tmp_path / "calls").read_text().splitlines() if (tmp_path / "calls").exists() else []
    return proc, calls


def _adds(calls):
    return [c for c in calls if c.startswith("projects add-iam-policy-binding")]


def test_a_held_role_is_left_alone(tmp_path):
    proc, calls = _run(tmp_path, "_ensure_audit_scheduler_viewer",
                       HAS_ROLE="roles/cloudscheduler.viewer")
    assert proc.stdout.strip().endswith("rc=0")
    assert _adds(calls) == [] and "WARNING" not in proc.stderr


def test_an_owner_deploying_grants_it(tmp_path):
    proc, calls = _run(tmp_path, "_ensure_audit_scheduler_viewer", ADD_RC="0")
    assert proc.stdout.strip().endswith("rc=0") and "granted" in proc.stdout
    assert len(_adds(calls)) == 1
    assert f"--member=serviceAccount:{SA}" in _adds(calls)[0]
    assert "--role=roles/cloudscheduler.viewer" in _adds(calls)[0]


def test_an_identity_that_cannot_grant_it_prints_the_owners_command(tmp_path):
    proc, calls = _run(tmp_path, "_ensure_audit_scheduler_viewer")
    assert proc.stdout.strip().endswith("rc=0")
    assert len(_adds(calls)) == 1
    assert "gcloud projects add-iam-policy-binding proj" in proc.stderr
    assert "roles/cloudscheduler.viewer" in proc.stderr and "#1201" in proc.stderr


def test_an_unreadable_policy_warns_and_does_not_guess(tmp_path):
    proc, calls = _run(tmp_path, "_ensure_audit_scheduler_viewer", POLICY_FAILS="1")
    assert proc.stdout.strip().endswith("rc=0")
    assert _adds(calls) == [] and "cannot read" in proc.stderr


def test_the_deploy_checks_the_role_after_the_job_is_in_place(tmp_path):
    proc, calls = _run(tmp_path, "deploy_audit_infra_drift",
                       HAS_ROLE="roles/cloudscheduler.viewer")
    assert proc.stdout.strip().endswith("rc=0")
    jobs = [i for i, c in enumerate(calls) if c.startswith("run jobs")]
    policy = [i for i, c in enumerate(calls) if c.startswith("projects get-iam-policy")]
    assert jobs and policy and max(jobs) < min(policy)


def test_a_failed_job_update_still_fails_the_deploy(tmp_path):
    """The role check comes after the update, so it must not become the
    function's exit status and hide a failed deploy. `create` fails as it
    does for a job that exists, and then the update fails too."""
    proc, calls = _run(tmp_path, "deploy_audit_infra_drift",
                       FAIL_JOBS="create update", HAS_ROLE="roles/cloudscheduler.viewer")
    assert not proc.stdout.strip().endswith("rc=0"), proc.stdout
    assert any(c.startswith("run jobs update") for c in calls)
