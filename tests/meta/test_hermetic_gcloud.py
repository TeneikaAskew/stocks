"""The test suite never reaches a real gcloud (FEAT-CICD-001).

Tests under tests/gcp/ check deploy.sh with a fake gcloud written into
pytest's temp directory and put first on PATH. When that fake cannot execute
(a noexec temp mount), bash keeps searching PATH; it used to find the installed
gcloud, signed in, with production as its default project. On 2026-10-12 that
sent audit-infra-drift job writes and build submissions to production.

tests/conftest.py now points gcloud at an empty config directory, drops its
token variable, and puts tests/fixtures/gcloud_tripwire/ first on PATH.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

TRIPWIRE = Path(__file__).resolve().parents[1] / "fixtures" / "gcloud_tripwire"
TOOLS = ("gcloud", "gsutil", "bq")


# Windows resolves commands through PATHEXT, so it finds the .cmd forms; bash
# (Git Bash included) finds the extensionless scripts.
SUFFIX = ".cmd" if os.name == "nt" else ""


@pytest.mark.parametrize("tool", TOOLS)
def test_each_cli_resolves_to_the_tripwire_and_refuses(tool):
    found = shutil.which(tool)
    assert found and os.path.normcase(found) == os.path.normcase(str(TRIPWIRE / f"{tool}{SUFFIX}"))
    proc = subprocess.run([found, "run", "jobs", "list"], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 97
    assert f"real {tool} refused: run jobs list" in proc.stderr


def _call_through(fake_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PATH=f"{fake_dir}{os.pathsep}{os.environ['PATH']}")
    return subprocess.run(["bash", "-c", "gcloud run jobs create audit-infra-drift"],
                          capture_output=True, text=True, env=env, timeout=30)


@pytest.mark.parametrize("tool", TOOLS)
def test_the_windows_tripwires_keep_the_same_contract(tool):
    """Checked on every platform, so the .cmd forms cannot drift unseen."""
    body = (TRIPWIRE / f"{tool}.cmd").read_text()
    assert "echo hermetic test suite: real %~n0 refused: %* 1>&2" in body
    assert "exit /b 97" in body


@pytest.mark.skipif(os.name == "nt", reason="Windows has no execute bit, so a fake cannot be skipped this way")
def test_a_fake_that_cannot_execute_falls_through_to_the_tripwire(tmp_path):
    """The noexec case: bash skips a file it cannot execute and keeps looking."""
    fake = tmp_path / "gcloud"
    fake.write_text("#!/usr/bin/env bash\necho FAKE\n")
    fake.chmod(0o755)
    ran = _call_through(tmp_path)
    assert (ran.returncode, ran.stdout.strip()) == (0, "FAKE")   # control: the fake wins

    fake.chmod(0o644)
    skipped = _call_through(tmp_path)
    assert skipped.returncode == 97, skipped.stderr
    assert "real gcloud refused: run jobs create audit-infra-drift" in skipped.stderr
    assert "FAKE" not in skipped.stdout


def test_gcloud_has_no_credentials_or_project_in_the_suite():
    config = os.environ.get("CLOUDSDK_CONFIG")
    assert config and Path(config).is_dir()
    assert list(Path(config).iterdir()) == []
    assert Path(config).resolve() != (Path.home() / ".config" / "gcloud").resolve()
    assert os.environ.get("CLOUDSDK_AUTH_DISABLE_CREDENTIALS") == "true"
    assert "CLOUDSDK_AUTH_ACCESS_TOKEN" not in os.environ
    assert "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE" not in os.environ


def test_the_live_secret_read_keeps_the_environment_from_before_the_guard(monkeypatch):
    """--mode=live's db_conn reads the database secrets with the owner's gcloud
    at its absolute path. It must keep the owner's config and credentials, or
    db_conn would skip where it used to connect."""
    from tests import conftest
    seen = {}

    def fake_check_output(cmd, **kwargs):
        seen.update(cmd=cmd, env=kwargs.get("env"))
        return "secret\n"

    monkeypatch.setattr(conftest.subprocess, "check_output", fake_check_output)
    assert conftest._gcloud_secret("db-trading-user") == "secret"
    assert seen["cmd"][0] == conftest._GCLOUD
    assert seen["env"] is conftest._PRE_GUARD_ENV
    assert seen["env"].get("CLOUDSDK_CONFIG") != os.environ["CLOUDSDK_CONFIG"]
