"""The db-query dispatcher refuses a --timeout the job's task timeout cannot reach.

Issue #1861: two executions (`db-query-cb2fs`, `db-query-szg6b`, 2026-11-13) were
dispatched with `DB_QUERY_TIMEOUT_SECONDS=900` against a job whose `--task-timeout`
is 600s. Cloud Run killed both at 600s, run_query uploaded nothing, and the
failure notifier opened an issue for what was a configuration that could never
have worked. These tests run the real script with a stub `gcloud` on PATH, so no
Cloud Run job is dispatched.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/db_query_cr.sh"
DEPLOY = ROOT / "gcp/deploy.sh"

# Keep in step with the script; asserted against it below.
TASK_TIMEOUT_S = 600
OVERHEAD_S = 60
MAX_TIMEOUT_S = TASK_TIMEOUT_S - OVERHEAD_S


def _shell_int(name: str) -> int:
    """The literal a top-level `NAME="123"` assignment in the dispatcher sets."""
    m = re.search(rf'^{name}="(\d+)"$', SCRIPT.read_text(), re.M)
    assert m, f"{name} is not a plain literal assignment in {SCRIPT.name}"
    return int(m.group(1))


@pytest.fixture
def stub_gcloud(tmp_path):
    """A gcloud that records its arguments and refuses to dispatch anything.

    `run jobs execute` exits nonzero, so a run that gets past the guard stops
    there instead of reaching into Cloud Run.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls = tmp_path / "calls.log"
    stub = bindir / "gcloud"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$*" >> "{calls}"\n'
        'case "$*" in\n'
        '  "config get-value project"*) echo stub-project ;;\n'
        '  *"run jobs execute"*) echo "stub: refusing to dispatch" >&2; exit 1 ;;\n'
        '  *) exit 0 ;;\n'
        'esac\n'
    )
    stub.chmod(0o755)
    return bindir, calls


def _run(bindir, *args):
    env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(bindir.parent), "PROJECT_ID": "stub-project"}
    return subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=120)


def test_script_bound_matches_the_deployed_task_timeout():
    """The script's bound is the task timeout gcp/deploy.sh actually deploys."""
    block = re.search(r"deploy_db_query\(\) \{.*?\n\}", DEPLOY.read_text(), re.S)
    assert block, "deploy_db_query not found in gcp/deploy.sh"
    deployed = re.search(r"--task-timeout (\d+)", block.group(0))
    assert deployed, "deploy_db_query sets no --task-timeout"
    assert int(deployed.group(1)) == _shell_int("TASK_TIMEOUT_S") == TASK_TIMEOUT_S
    assert _shell_int("OVERHEAD_S") == OVERHEAD_S


def test_timeout_beyond_the_task_budget_is_refused_before_dispatch(stub_gcloud):
    """The #1861 invocation: 900s against a 600s task timeout."""
    bindir, calls = stub_gcloud
    r = _run(bindir, "-q", "SELECT 1", "--timeout", "900")
    assert r.returncode == 2, r.stderr
    assert "does not fit the db-query job's 600s task timeout" in r.stderr
    assert str(MAX_TIMEOUT_S) in r.stderr
    assert "run jobs execute" not in (calls.read_text() if calls.exists() else "")


def test_timeout_at_the_bound_reaches_dispatch(stub_gcloud):
    """The largest accepted value is not refused; the stub stops the dispatch."""
    bindir, calls = stub_gcloud
    r = _run(bindir, "-q", "SELECT 1", "--timeout", str(MAX_TIMEOUT_S))
    assert "does not fit" not in r.stderr, r.stderr
    assert "run jobs execute" in calls.read_text()


def test_one_second_over_the_bound_is_refused(stub_gcloud):
    bindir, calls = stub_gcloud
    r = _run(bindir, "-q", "SELECT 1", "--timeout", str(MAX_TIMEOUT_S + 1))
    assert r.returncode == 2, r.stderr
    assert "does not fit" in r.stderr
    assert "run jobs execute" not in (calls.read_text() if calls.exists() else "")


def test_default_timeout_is_accepted(stub_gcloud):
    bindir, calls = stub_gcloud
    r = _run(bindir, "-q", "SELECT 1")
    assert "does not fit" not in r.stderr, r.stderr
    assert "run jobs execute" in calls.read_text()


@pytest.mark.parametrize("bad", ["abc", "0", "-30", "90s", ""])
def test_non_positive_integer_timeout_is_refused(stub_gcloud, bad):
    """Before this guard these reached `$(( TIMEOUT_S + 180 ))` or the job itself."""
    bindir, calls = stub_gcloud
    r = _run(bindir, "-q", "SELECT 1", "--timeout", bad)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "positive whole number" in r.stderr
    assert "run jobs execute" not in (calls.read_text() if calls.exists() else "")
