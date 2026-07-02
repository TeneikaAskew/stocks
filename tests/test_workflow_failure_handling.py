"""Regression tests for GH Actions workflow failure-handling wiring.

Pins two things the 2026-07-01 refresh-architecture-docs.yml incident
exposed:
  1. Every active (non-.disabled) workflow that can fail on a schedule
     wires up the shared handle-workflow-failure.yml job (CLAUDE.md
     "Automated Workflow Failure Handling" — a workflow with no handler
     fails silently with no gcp-job-failure/workflow-failure issue).
  2. refresh-architecture-docs.yml's PR-creation step no longer relies
     solely on secrets.GITHUB_TOKEN, which cannot create pull requests
     unless the repo's "Allow GitHub Actions to create and approve pull
     requests" setting is enabled (it wasn't — see the 2026-07-01 run:
     "GraphQL: GitHub Actions is not permitted to create or approve pull
     requests").

Pure YAML-structure assertions — no network calls, no GitHub API.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_WORKFLOWS_DIR = _REPO / ".github" / "workflows"
_ARCH_REFRESH = _WORKFLOWS_DIR / "refresh-architecture-docs.yml"

# Workflows that are schedule-triggered but intentionally have no
# handle-failure job, with the reason documented inline. Extend this list
# (with a reason) rather than silently skip a new schedule-triggered
# workflow that lacks a handler.
_NO_HANDLER_ALLOWLIST: dict[str, str] = {
    "handle-workflow-failure.yml": "this IS the handler",
}


def _load_workflow(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def _is_schedule_triggered(doc: dict) -> bool:
    on = doc.get("on") or doc.get(True)  # PyYAML parses bare `on:` as True in some configs
    if not isinstance(on, dict):
        return False
    return "schedule" in on


class TestArchRefreshFailureHandling:
    def test_workflow_yaml_parses(self):
        doc = _load_workflow(_ARCH_REFRESH)
        assert "refresh" in doc["jobs"]

    def test_handle_failure_job_present_and_wired(self):
        doc = _load_workflow(_ARCH_REFRESH)
        jobs = doc["jobs"]
        assert "handle-failure" in jobs, (
            "refresh-architecture-docs.yml has no handle-failure job — "
            "the 2026-07-01 failure went untracked because of exactly this gap"
        )
        job = jobs["handle-failure"]
        assert job["needs"] == "refresh"
        assert job["if"] == "failure()"
        assert job["uses"] == "./.github/workflows/handle-workflow-failure.yml"
        assert job["secrets"]["PR_WORKFLOW_TOKEN"] == "${{ secrets.PR_WORKFLOW_TOKEN }}"
        assert job["with"]["workflow_file"] == "refresh-architecture-docs.yml"

    def test_pr_creation_step_does_not_rely_solely_on_github_token(self):
        text = _ARCH_REFRESH.read_text()
        # The exact failure from 2026-07-01: GITHUB_TOKEN alone can't create PRs.
        assert "GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}" not in text, (
            "GH_TOKEN reverted to bare secrets.GITHUB_TOKEN — this is the "
            "token that failed with 'GitHub Actions is not permitted to "
            "create or approve pull requests' on 2026-07-01"
        )
        assert "GH_TOKEN: ${{ secrets.PR_WORKFLOW_TOKEN || secrets.GITHUB_TOKEN }}" in text


class TestActiveWorkflowsHaveFailureHandling:
    """CLAUDE.md: 'Every workflow MUST include the handle-failure job.'

    Scoped to schedule-triggered workflows: those are the ones that fail
    unattended with nobody watching the run in real time, which is exactly
    the scenario the handler exists for.
    """

    @pytest.mark.parametrize(
        "path",
        sorted(p for p in _WORKFLOWS_DIR.glob("*.yml") if p.name != "handle-workflow-failure.yml"),
        ids=lambda p: p.name,
    )
    def test_scheduled_workflow_has_failure_handler_or_is_allowlisted(self, path: Path):
        doc = _load_workflow(path)
        if not _is_schedule_triggered(doc):
            pytest.skip(f"{path.name} is not schedule-triggered")
        if path.name in _NO_HANDLER_ALLOWLIST:
            pytest.skip(f"{path.name}: {_NO_HANDLER_ALLOWLIST[path.name]}")

        jobs = doc.get("jobs", {})
        has_handler = any(
            job.get("uses") == "./.github/workflows/handle-workflow-failure.yml"
            for job in jobs.values()
        )
        assert has_handler, (
            f"{path.name} is schedule-triggered but has no handle-failure job — "
            "add one (see refresh-architecture-docs.yml for the pattern) or add "
            "it to _NO_HANDLER_ALLOWLIST with a reason"
        )
