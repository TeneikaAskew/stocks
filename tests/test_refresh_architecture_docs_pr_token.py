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

import re
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


def _open_pr_run_script() -> str:
    steps = DOC["jobs"]["refresh"]["steps"]
    open_pr_steps = [s for s in steps if s.get("name") == "Open refresh PR"]
    assert len(open_pr_steps) == 1, "expected exactly one 'Open refresh PR' step"
    return open_pr_steps[0]["run"]


def test_bot_branch_push_is_forced_not_plain():
    """Regression for issue #688 (2026-07-06): bot/arch-refresh-YYYY-MM is
    re-created fresh from main every run, so a second run in the same month
    (e.g. a manual workflow_dispatch after the 1st-of-month schedule already
    ran) shares no history with the remote branch a prior run pushed. A
    plain `git push` is rejected as non-fast-forward and the whole job fails
    with no PR opened, even though the doc content itself regenerated fine.
    Force-push is safe: this branch is bot-owned, disposable, and never
    `main` (CLAUDE.md's force-push ban is scoped to main).
    """
    script = _open_pr_run_script()
    assert "git push --force -u origin \"$BRANCH\"" in script, (
        "the push to the disposable bot branch must be forced so a second "
        "run in the same month doesn't fail with a non-fast-forward "
        "rejection (issue #688)"
    )
    assert "git push -u origin \"$BRANCH\"\n" not in script.replace(
        "git push --force -u origin \"$BRANCH\"\n", ""
    ), "found a non-forced push to $BRANCH alongside the forced one"


def test_existing_pr_for_branch_is_detected_before_create():
    """Companion to the force-push fix: after a force-push, `gh pr create`
    still errors loudly if a PR from an earlier run this month is already
    open for the branch. That's not a failure — the force-push already
    delivered fresh content to it — so the step must check for an existing
    open PR and exit clean instead of calling `gh pr create` again.
    """
    script = _open_pr_run_script()
    assert "gh pr list --state open --head \"$BRANCH\"" in script
    assert re.search(r"if \[ -n \"\$EXISTING_PR\" \]; then", script)
    # The existing-PR branch must exit before reaching the actual `gh pr
    # create` invocation (a start-of-line command, not just a mention of
    # the phrase in a comment).
    exists_idx = script.index("EXISTING_PR=")
    create_match = re.search(r"^\s*gh pr create \\", script, re.MULTILINE)
    assert create_match, "expected a `gh pr create \\` command invocation"
    assert exists_idx < create_match.start(), (
        "the existing-open-PR check must run before gh pr create, not after"
    )
