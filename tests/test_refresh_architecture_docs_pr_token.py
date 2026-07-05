"""Regression tests for refresh-architecture-docs.yml PR creation + failure visibility.

Two runs of this workflow (2026-05-04 ok, then 2026-06-01 and 2026-07-01
both failed) hit `gh pr create failed: GraphQL: GitHub Actions is not
permitted to create or approve pull requests` — the default GITHUB_TOKEN
is blocked at the GraphQL API level when the repo/org "Allow GitHub
Actions to create and approve pull requests" setting is off, regardless
of the `pull-requests: write` permission declared in the workflow.
`handle-workflow-failure.yml` already solves this for every other
workflow via the `PR_WORKFLOW_TOKEN` PAT (see
docs/CLAUDE_CODE_ON_WEB.md "Secret naming for blast-radius isolation").
This workflow also had no `handle-failure` job, so the failure recurred
silently for two months with no issue/PR trail.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO / ".github/workflows/refresh-architecture-docs.yml"
RAW = WORKFLOW_PATH.read_text()
DOC = yaml.safe_load(RAW)


def test_workflow_yaml_is_valid():
    assert DOC["jobs"]["refresh"] is not None


def test_open_pr_step_uses_pr_workflow_token_not_default_github_token():
    steps = DOC["jobs"]["refresh"]["steps"]
    open_pr_steps = [s for s in steps if s.get("name") == "Open refresh PR"]
    assert len(open_pr_steps) == 1, "expected exactly one 'Open refresh PR' step"
    gh_token = open_pr_steps[0]["env"]["GH_TOKEN"]
    assert "PR_WORKFLOW_TOKEN" in gh_token, (
        "'Open refresh PR' must authenticate gh with secrets.PR_WORKFLOW_TOKEN, "
        "not the default GITHUB_TOKEN — the default token is blocked from "
        "creating PRs when the repo disallows Actions-created PRs, which is "
        "exactly what broke the 2026-06-01 and 2026-07-01 runs."
    )
    assert "secrets.GITHUB_TOKEN" not in gh_token


def test_handle_failure_job_exists_and_is_wired_correctly():
    jobs = DOC["jobs"]
    assert "handle-failure" in jobs, (
        "refresh-architecture-docs.yml must have a handle-failure job "
        "(CLAUDE.md 'Automated Workflow Failure Handling') so a future "
        "failure opens an issue instead of recurring silently for months."
    )
    job = jobs["handle-failure"]
    assert job["needs"] == "refresh"
    assert job["if"] == "failure()"
    assert job["uses"] == "./.github/workflows/handle-workflow-failure.yml"
    assert job["permissions"]["actions"] == "read"
    assert job["permissions"]["pull-requests"] == "write"
    assert "PR_WORKFLOW_TOKEN" in job["secrets"]["PR_WORKFLOW_TOKEN"]
    assert job["with"]["workflow_file"] == "refresh-architecture-docs.yml"
