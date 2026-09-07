"""The `Open refresh PR` step has never executed in production. Run it here.

Runs 18 and 19 skipped it as dry runs; 20, 21 and 22 failed before reaching
it. So the one step that actually DELIVERS the monthly refresh -- the branch,
the commit, the push, the PR -- has no production evidence behind it at all,
and every fix so far has been to code that runs before it.

These tests extract the step's own script out of the workflow and run it
against a real temporary repository with a real bare remote, with only `gh`
stubbed. Nothing is reconstructed: the shell that runs on the 1st of the month
is the shell that runs here.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github/workflows/refresh-architecture-docs.yml"
DOC = yaml.safe_load(WORKFLOW.read_text())
STEPS = DOC["jobs"]["refresh"]["steps"]
OPEN_PR = next(s for s in STEPS if s.get("name") == "Open refresh PR")

# The documents the step stages, read off the step itself so a document added
# to the refresh cannot leave this fixture behind.
STAGED = [w for w in OPEN_PR["run"].split("git add ", 1)[1].split("\n", 1)[0].split()]

GH_STUB = """#!/usr/bin/env bash
echo "$@" >> "$GH_CALLS"
case "$1 $2" in
  "pr list") printf '%s' "$GH_EXISTING_PR" ;;
  "pr create") printf '%s' "$*" > "$GH_OUT/create.txt" ;;
  "pr edit")   printf '%s' "$*" > "$GH_OUT/edit.txt" ;;
esac
"""


def _run_step(tmp_path: Path, *, existing_pr: str = "", touch: list[str] | None = None):
    work, remote, bin_dir, out = (tmp_path / n for n in ("work", "remote", "bin", "out"))
    for d in (work, remote, bin_dir, out):
        d.mkdir()
    git = lambda *a, **kw: subprocess.run(["git", *a], cwd=kw.pop("cwd", work),
                                          check=True, capture_output=True, text=True)
    git("init", "-q", "--bare", "origin.git", cwd=remote)
    git("init", "-q", "-b", "main", ".")
    git("config", "user.email", "t@e.st")
    git("config", "user.name", "t")
    for f in STAGED:
        (work / f).parent.mkdir(parents=True, exist_ok=True)
        (work / f).write_text(f"old {f}\n")
    (work / "refresh-inputs").mkdir()
    (work / "refresh-inputs/diff_report.md").write_text("### Added / removed\n\n| doc | + | - |\n|---|---|---|\n| ARCH | 12 | 3 |\n")
    (work / "refresh-inputs/verify_other.md").write_text("### Docs-vs-live findings\n\n_none_\n")
    git("add", "-A")
    git("commit", "-qm", "init")
    git("remote", "add", "origin", str(remote / "origin.git"))
    git("push", "-q", "-u", "origin", "main")

    for f in (touch if touch is not None else STAGED[:2]):
        (work / f).write_text(f"regenerated {f}\n")

    (bin_dir / "gh").write_text(GH_STUB)
    (bin_dir / "gh").chmod(0o755)
    env = dict(os.environ)
    env.update(PATH=f"{bin_dir}:{env['PATH']}", PR_BRANCH_PREFIX="bot/arch-refresh",
               GEMINI_MODEL="gemini-2.5-pro", GH_TOKEN="stub",
               GH_OUT=str(out), GH_CALLS=str(out / "calls.txt"),
               GH_EXISTING_PR=existing_pr)
    proc = subprocess.run(["bash", "-c", OPEN_PR["run"]], cwd=work, env=env,
                          capture_output=True, text=True)
    return proc, work, remote / "origin.git", out


def test_the_step_branches_commits_pushes_and_opens_one_pr(tmp_path):
    proc, work, remote, out = _run_step(tmp_path)
    assert proc.returncode == 0, proc.stderr

    month = time.strftime("%Y-%m", time.gmtime())
    branch = f"bot/arch-refresh-{month}"
    head = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=work,
                          capture_output=True, text=True).stdout.strip()
    assert head == branch

    # The commit really landed on the real remote, not just locally.
    pushed = subprocess.run(["git", "log", "-1", "--format=%s", branch], cwd=remote,
                            capture_output=True, text=True)
    assert pushed.returncode == 0, pushed.stderr
    assert pushed.stdout.strip() == f"docs: monthly architecture doc refresh {month}"

    args = (out / "create.txt").read_text()
    assert "--base main" in args and f"--head {branch}" in args
    assert f"Monthly architecture doc refresh: {month}" in args
    assert not (out / "edit.txt").exists(), "opened AND edited a PR"


def test_the_body_carries_this_run_s_accounting(tmp_path):
    """`refresh-inputs/diff_report.md` and `verify_other.md` are what a
    reviewer reads instead of the whole diff, and the heredoc that assembles
    them has never run outside a test."""
    _, _, _, out = _run_step(tmp_path)
    body = (out / "create.txt").read_text()
    assert "| ARCH | 12 | 3 |" in body
    assert "### Docs-vs-live findings" in body
    # A heading immediately after a table row is not reliably a heading.
    assert "| ARCH | 12 | 3 |\n\n### Docs-vs-live" in body
    # Backticks in the heredoc are escaped; unescaped they would have been
    # executed by the shell and their output substituted into the body.
    assert "`scripts/maintenance/doc_inventory.py --write-snapshot --db-live`" in body
    assert "Gemini gemini-2.5-pro (Vertex AI)" in body, "GEMINI_MODEL did not expand"
    assert "${" not in body, "an unexpanded placeholder reached the PR body"
    # The `git diff --stat` block, which is the summary of what moved.
    assert "2 files changed" in body


def test_a_second_run_in_the_same_month_updates_the_open_pr(tmp_path):
    """The branch is force-pushed with fresh content, so leaving the body
    alone would describe the PREVIOUS run's documents. (Codex, PR #1009.)"""
    proc, _, _, out = _run_step(tmp_path, existing_pr="123")
    assert proc.returncode == 0, proc.stderr
    assert not (out / "create.txt").exists(), "created a duplicate PR"
    edit = (out / "edit.txt").read_text()
    assert edit.startswith("pr edit 123 --body")
    assert "| ARCH | 12 | 3 |" in edit


def test_nothing_staged_exits_clean_without_touching_github(tmp_path):
    """`Detect meaningful changes` reverts timestamp-only files, so this step
    can legitimately find an empty index. That is a no-op, not a failure."""
    proc, _, remote, out = _run_step(tmp_path, touch=[])
    assert proc.returncode == 0, proc.stderr
    assert "nothing staged" in proc.stdout
    assert not (out / "create.txt").exists() and not (out / "edit.txt").exists()
    branches = subprocess.run(["git", "branch", "--format=%(refname:short)"], cwd=remote,
                              capture_output=True, text=True).stdout.split()
    assert branches == ["main"], f"pushed a branch with nothing on it: {branches}"


def test_the_step_only_runs_on_a_real_change_and_not_on_a_dry_run():
    cond = " ".join(OPEN_PR["if"].split())
    assert "steps.detect.outputs.meaningful == '1'" in cond
    assert "inputs.dry_run != 'true'" in cond


def test_the_pr_token_is_used_because_the_default_one_cannot_open_prs():
    """The default GITHUB_TOKEN is refused when the repo disables Actions
    opening PRs, which is a Settings toggle no workflow permission overrides."""
    assert OPEN_PR["env"]["GH_TOKEN"] == "${{ secrets.PR_WORKFLOW_TOKEN }}"


def test_the_job_can_push_a_branch_and_open_a_pr():
    perms = DOC["permissions"]
    assert perms["contents"] == "write" and perms["pull-requests"] == "write"


def test_every_staged_document_is_one_the_refresh_produces():
    """A path typo here stages nothing and the run exits clean with no PR --
    the quietest possible failure of the whole workflow."""
    import scripts.maintenance.check_generated_docs as gate
    assert set(gate.DOCS) <= set(STAGED), set(gate.DOCS) - set(STAGED)
    for f in STAGED:
        assert (REPO / f).exists(), f"{f} is staged by the refresh but not in the repo"


# ── the run has to be able to authenticate at all ───────────────────────────

def test_a_dispatch_from_a_branch_fails_before_it_burns_a_run():
    """Run 23 was dispatched from a feature branch to validate a fix and died
    inside `google-github-actions/auth` with three unexplained lines, then
    opened a failure issue and a draft PR about it.

    The cause is the Workload Identity provider's attribute condition, read
    from GCP on 2026-09-07:

        assertion.repository=='TeneikaAskew/stocks' && assertion.ref=='refs/heads/main'

    That is the boundary stopping any PR branch from assuming this project's
    GCP identity, so the workflow says so instead of the condition being
    relaxed. This pins the guard's position: after it, an opaque auth failure
    from a branch is a regression.
    """
    names = [s.get("name") for s in STEPS]
    guard = "Refuse to run from anywhere but main"
    assert guard in names, "the branch-dispatch guard is gone"
    assert names.index(guard) < names.index("Authenticate to GCP (WIF)")
    step = STEPS[names.index(guard)]
    assert step["if"] == "github.ref != 'refs/heads/main'"
    assert "refs/heads/main" in step["run"] and "::error::" in step["run"]
    assert "exit 1" in step["run"]
