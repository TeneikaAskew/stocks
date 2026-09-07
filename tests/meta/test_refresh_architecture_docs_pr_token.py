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

REPO = Path(__file__).resolve().parents[2]
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


# ── 2026-09-07 rebuild: live snapshot, deterministic blocks, loss gates ──────
# The 2026-09-02 run replaced a 394-line hand-maintained ARCHITECTURE.md with
# a 158-line regeneration that named 4 of 67 declared jobs, and went green.
# These tests pin the shape that prevents a repeat: the inventory blocks are
# rendered by scripts/maintenance/doc_inventory.py BEFORE Gemini runs, the
# live GCP snapshot and digests exist and fail loud, and the verify step runs
# the structural gates plus scripts/verify_docs_against_live.py.

def _steps():
    return DOC["jobs"]["refresh"]["steps"]


def _index(name_fragment: str) -> int:
    for i, s in enumerate(_steps()):
        if name_fragment in (s.get("name") or ""):
            return i
    raise AssertionError(f"no step named like {name_fragment!r}")


def test_live_snapshot_step_exists_and_fails_loud():
    step = _steps()[_index("Snapshot live")]
    run = step["run"]
    assert "doc_inventory --write-snapshot refresh-inputs/live.json --db-live" in run
    assert "verify_docs_against_live.py --write-snapshot refresh-inputs/verify_live.json" in run
    assert "refusing to generate docs" in run, "an empty snapshot must stop the run (Rule 3.7)"
    for secret in ("CLOUD_SQL_CONNECTION_NAME", "DB_USER", "DB_PASS", "DB_NAME"):
        assert secret in step["env"], f"live table stats need {secret}"


def test_digest_and_render_precede_the_first_gemini_step():
    first_gemini = min(i for i, s in enumerate(_steps()) if "Regenerate" in (s.get("name") or ""))
    assert _index("Snapshot live") < first_gemini
    assert _index("Digest inputs") < first_gemini
    assert _index("Save previous doc versions") < first_gemini
    assert _index("Render inventory blocks") < first_gemini
    render = _steps()[_index("Render inventory blocks")]["run"]
    assert "--insert ARCHITECTURE.md DATA_DEPENDENCIES.md docs/API.md" in render


def test_digest_step_writes_the_small_files_the_prompts_read():
    run = _steps()[_index("Digest inputs")]["run"]
    for f in ("jobs.txt", "services.txt", "secrets.txt", "service_accounts.txt", "buckets.txt",
              "billing_by_sku.csv", "billing_by_month.csv", "repo_inventory.json", "live_vs_repo.md"):
        assert f in run, f"digest step must write refresh-inputs/{f}"
    assert "is empty" in run, "an empty digest must fail the run"


def test_gemini_transcripts_are_captured_for_the_truncation_gate():
    for s in _steps():
        if "Regenerate" in (s.get("name") or ""):
            assert "$RUNNER_TEMP/transcripts/" in s["run"], s["name"]


def test_verify_step_runs_the_structural_gates_and_the_live_verifier():
    run = _steps()[_index("Verify regenerated docs")]["run"]
    assert "scripts/maintenance/check_generated_docs.py" in run
    assert "--previous-dir refresh-inputs/previous" in run
    assert '--transcripts-dir "$RUNNER_TEMP/transcripts"' in run
    assert "scripts/verify_docs_against_live.py --snapshot refresh-inputs/verify_live.json" in run
    # the original three gates survive
    assert "Generated" in run and "CREATE TABLE" in run and "placeholder" in run


def test_prompts_update_in_place_and_never_touch_marker_blocks():
    prompts = REPO / ".github/prompts"
    for name in ("architecture.md", "data-dependencies.md", "readme.md"):
        text = (prompts / name).read_text()
        assert "in place" in text.lower(), name
        assert "never regenerate from scratch" in text.lower(), name
        assert "marker" in text.lower(), name
    for name in ("architecture.md", "data-dependencies.md", "readme.md", "cost-analysis.md"):
        text = (prompts / name).read_text()
        assert "hard stop" in text.lower(), name
        for stale in ("React + FastAPI dashboard", "no public auth, no per-user", "Vite 5173", "`/watch`", "all 27 jobs"):
            assert stale not in text, f"{name} still hardcodes {stale!r}"


def test_marker_names_agree_between_module_docs_and_gate():
    from scripts.maintenance import doc_inventory as inv
    from scripts.maintenance import check_generated_docs as gate
    arch = (REPO / "ARCHITECTURE.md").read_text()
    deps = (REPO / "DATA_DEPENDENCIES.md").read_text()
    for name in ("jobs", "schedulers", "tables", "routes", "services", "reconcile", "modules", "dbtables"):
        assert inv.MARKER_START.format(name=name) in arch, name
    for name in ("tables", "dbtables", "writes", "reads", "multiwriter", "orphans", "blast"):
        assert inv.MARKER_START.format(name=name) in deps, name
    api = (REPO / "docs/API.md").read_text()
    for name in ("routers", "routes"):
        assert inv.MARKER_START.format(name=name) in api, name
    assert set(gate.MARKER_DOCS) == {"ARCHITECTURE.md", "DATA_DEPENDENCIES.md", "docs/API.md"}


def test_gcp_reads_and_rendering_all_precede_gemini():
    """The order the accuracy of this workflow depends on.

    Every live read, the digest, the saved previous versions and the
    deterministic block render must happen BEFORE the first model step, so
    the model is editing prose around numbers that were already measured
    rather than supplying numbers of its own.
    """
    first_gemini = min(i for i, s in enumerate(_steps()) if "Regenerate" in (s.get("name") or ""))
    for name in ("Dump asset inventory", "Dump IAM policy", "Dump 90-day billing rollup",
                 "Snapshot live", "Digest inputs", "Save previous doc versions",
                 "Render inventory blocks", "Freeze gate inputs"):
        assert _index(name) < first_gemini, f"{name} must run before Gemini"


def test_snapshot_step_tolerates_drift_findings_but_not_a_crash():
    """verify_docs_against_live exits 1 when the CURRENT docs have drifted --
    the condition the refresh exists to repair. Under the Actions shell's
    set -e that aborted the run before anything regenerated."""
    run = _steps()[_index("Snapshot live")]["run"]
    assert "VRC=$?" in run and '"$VRC" -ne 1' in run, (
        "a findings exit (1) from the verifier must not abort the snapshot step")
    assert "test -s refresh-inputs/verify_live.json" in run


def test_repo_jobs_are_read_from_the_nested_inventory_key():
    """doc_inventory --json nests under .repo; `.jobs[]` is null and jq exits 5."""
    run = _steps()[_index("Render inventory blocks")]["run"]
    assert ".repo.jobs[].name" in run
    assert "refresh_architecture_drawio.py" in run, "the drawio companions are regenerated here"


def test_gate_step_writes_the_added_removed_accounting():
    run = _steps()[_index("Verify regenerated docs")]["run"]
    assert "--report refresh-inputs/diff_report.md" in run
    assert "GITHUB_STEP_SUMMARY" in run
    commands = [ln for ln in run.splitlines() if not ln.lstrip().startswith("#")]
    assert not any("--allow-rewrite" in ln for ln in commands), (
        "the churn ceiling's escape hatch is for a human reconstruction; the bot "
        "must never be able to exempt itself")


def test_freeze_and_restore_prove_they_actually_happened():
    """A control that reports success without doing its job is the failure
    class this whole pipeline is about. `cp -r src dst` nests when dst
    exists, so a freeze into a dirty RUNNER_TEMP copied to
    frozen/refresh-inputs/refresh-inputs/ and the restore then copied
    nothing and exited 0, leaving the model's inputs for the gates to judge.
    """
    freeze = _steps()[_index("Freeze gate inputs")]["run"]
    assert 'rm -rf "$RUNNER_TEMP/frozen"' in freeze, "the freeze destination must be cleared first"
    assert "manifest.sha256" in freeze, "the freeze must record what it captured"
    for f in ("live.json", "verify_live.json", "previous"):
        assert f in freeze, f"the freeze must assert it captured {f}"

    restore = _steps()[_index("Restore gate inputs")]["run"]
    assert "manifest.sha256" in restore, "the restore must verify against the frozen manifest"
    assert "sha256sum -c" in restore
    assert "refusing to verify" in restore, "a missing frozen copy must stop the run"


def test_transcripts_are_written_where_the_model_cannot_reach_them():
    """Gemini holds write_file/replace over the checkout for every one of the
    four runs, so a transcript under refresh-inputs/ could be erased by a
    later invocation before the truncation gate reads it -- and the stray-write
    check excludes refresh-inputs/ (Codex, #1009)."""
    for s in _steps():
        if "Regenerate" in (s.get("name") or ""):
            assert "refresh-inputs/transcripts" not in s["run"], s["name"]
            assert "$RUNNER_TEMP/transcripts" in s["run"], s["name"]


def test_previous_tree_carries_every_doc_the_churn_gate_scores():
    """diff_stats() skips a document with no previous version, so a doc left
    out of this copy silently bypasses its churn ceiling."""
    run = _steps()[_index("Save previous doc versions")]["run"]
    for d in ("ARCHITECTURE.md", "DATA_DEPENDENCIES.md", "COST_ANALYSIS.md", "README.md", "docs/API.md"):
        assert d in run, f"{d} must be saved for the loss and churn gates"


def test_the_diagrams_are_frozen_restored_and_revalidated_after_gemini():
    """The drawio validation ran only BEFORE the model could reach the files.

    All four Gemini steps hold write_file/replace over the checkout, and the
    stray-write allowlist named both diagrams, so an edit made after the
    render step's `--check` was staged and published unchecked.
    (Codex, PR #1009.)
    """
    steps = {s.get("name"): s.get("run") or "" for s in _steps()}
    freeze = next(v for k, v in steps.items() if k and k.startswith("Freeze gate inputs"))
    assert 'cp Architecture.drawio Architecture-icons.drawio "$RUNNER_TEMP/frozen/"' in freeze
    assert 'test -f "$RUNNER_TEMP/frozen/Architecture.drawio"' in freeze

    restore = next(v for k, v in steps.items() if k and k.startswith("Restore gate inputs"))
    allowed = re.search(r'ALLOWED="([^"]+)"', restore).group(1).split()
    assert "Architecture.drawio" not in allowed, \
        "a rendered file the model must not write is still allowlisted"
    assert 'cp "$RUNNER_TEMP/frozen/Architecture.drawio" Architecture.drawio' in restore

    names = [s.get("name") for s in _steps()]
    revalidate = "Re-validate the diagrams after the model ran"
    assert revalidate in names
    assert "--check" in steps[revalidate]
    # and it must come after every model step AND after the restore, so it
    # validates the bytes that get committed rather than the model's copy
    last_gemini = max(i for i, n in enumerate(names) if n and n.startswith("Regenerate "))
    restore_i = next(i for i, n in enumerate(names) if n and n.startswith("Restore gate inputs"))
    assert last_gemini < restore_i < names.index(revalidate)
    # it reads the frozen inputs, which the restore has just put back
    assert "refresh-inputs/live.json" in steps[revalidate]
    assert "refresh-inputs/repo_jobs.json" in steps[revalidate]


def test_verifier_drift_outside_the_regenerated_docs_reaches_the_pr_body():
    """The step comment promised the PR body carries it; nothing interpolated
    it. (Codex, PR #1009.)"""
    steps = {s.get("name"): s.get("run") or "" for s in _steps()}
    verify = steps["Verify regenerated docs"]
    assert "refresh-inputs/verify_other.md" in verify, \
        "the non-blocking findings are not written anywhere a later step can read"
    assert 'cat refresh-inputs/verify_other.md >> "$GITHUB_STEP_SUMMARY"' in verify

    pr = next(v for k, v in steps.items() if k and k.startswith("Open refresh PR"))
    assert "DRIFT=$(cat refresh-inputs/verify_other.md" in pr
    assert "${DRIFT}" in pr


def test_a_second_run_in_the_same_month_updates_the_existing_pr_body():
    """A force-push replaced the branch content and left the body describing
    the previous run's documents. (Codex, PR #1009.)"""
    steps = {s.get("name"): s.get("run") or "" for s in _steps()}
    pr = next(v for k, v in steps.items() if k and k.startswith("Open refresh PR"))
    assert "BODY=$(cat <<EOF" in pr, "the body must be built once for both paths"
    assert 'gh pr edit "$EXISTING_PR" --body "$BODY"' in pr
    assert '--body "$BODY"' in pr, "gh pr create must use the same body"
    # the edit has to happen inside the EXISTING_PR branch, before ITS exit --
    # the step has an earlier exit for the nothing-to-commit case, so anchor on
    # the branch rather than on the first `exit 0` in the file
    branch = pr[pr.index('if [ -n "$EXISTING_PR" ]'):]
    assert branch.index('gh pr edit "$EXISTING_PR"') < branch.index("exit 0")


def test_the_pr_body_heredoc_cannot_execute_its_own_markdown():
    """An UNQUOTED heredoc runs backticks. Before they were escaped, expanding
    the body actually executed `gcloud asset search-all-resources` and dropped
    every backticked span from the text."""
    steps = {s.get("name"): s.get("run") or "" for s in _steps()}
    pr = next(v for k, v in steps.items() if k and k.startswith("Open refresh PR"))
    body = pr[pr.index("BODY=$(cat <<EOF"):pr.index("\nEOF\n)")]
    unescaped = re.findall(r"(?<!\\)`", body[body.index("\n"):])
    assert not unescaped, f"{len(unescaped)} unescaped backticks would be executed"


def test_the_deterministic_docs_are_frozen_not_allowlisted():
    """No prompt writes docs/API.md or docs/INVESTMENT_MODELS_SUMMARY.md, so a
    model edit to either is a stray write. (Codex, PR #1009.)"""
    prompts = (WORKFLOW_PATH.parent.parent / "prompts")
    written = {"ARCHITECTURE.md", "DATA_DEPENDENCIES.md", "COST_ANALYSIS.md", "README.md"}
    steps = {s.get("name"): s.get("run") or "" for s in _steps()}
    restore = next(v for k, v in steps.items() if k and k.startswith("Restore gate inputs"))
    allowed = set(re.search(r'ALLOWED="([^"]+)"', restore).group(1).split())
    assert allowed == written, f"allowlist must be exactly the prompt-written docs, got {allowed}"

    freeze = next(v for k, v in steps.items() if k and k.startswith("Freeze gate inputs"))
    for f in ("docs/API.md", "docs/INVESTMENT_MODELS_SUMMARY.md"):
        assert f in freeze, f"{f} is not frozen"
        assert f'cp "$RUNNER_TEMP/frozen/{f}" {f}' in restore, f"{f} is not restored"
    # the calibration renderer is the legitimate writer of the summary, and it
    # must run AFTER the restore or its work would be thrown away
    names = [s.get("name") for s in _steps()]
    restore_i = next(i for i, n in enumerate(names) if n and n.startswith("Restore gate inputs"))
    calib_i = next(i for i, n in enumerate(names) if n and "ticker_calibration" in n)
    assert calib_i > restore_i


def test_a_state_change_sharing_a_line_with_a_timestamp_is_not_reverted():
    """Dropping every line containing a date threw away real state changes.

    The drawio sched_group cell is one XML line carrying both the read date and
    the paused-scheduler list, so a scheduler becoming paused was classified
    timestamp-only and reverted. (Codex, PR #1009.)
    """
    steps = {s.get("name"): s.get("run") or "" for s in _steps()}
    detect = steps["Detect meaningful changes"]
    assert "grep -vE '(read live|Live|read) 20" not in detect, \
        "the line-dropping filter is back; it discards content that shares a line with a date"
    assert "<DATE>" in detect, "dates must be masked, not used to drop lines"
    # removed and added lines are COMPARED once masked
    assert ".old" in detect and ".new" in detect and "diff " in detect


def test_a_legitimate_render_change_is_not_a_stray_write():
    """P1: the render is the whole point of the run, and excluding the
    deterministic files from ALLOWED classified their INTENDED changes as
    model writes -- so every month that added a route or a job would have
    failed. They are compared with their frozen copies instead.
    (Codex, PR #1009.)"""
    steps = {s.get("name"): s.get("run") or "" for s in _steps()}
    restore = next(v for k, v in steps.items() if k and k.startswith("Restore gate inputs"))
    assert "DETERMINISTIC=" in restore
    det = set(re.search(r'DETERMINISTIC="([^"]+)"', restore).group(1).split())
    assert det == {"Architecture.drawio", "Architecture-icons.drawio",
                   "docs/API.md", "docs/INVESTMENT_MODELS_SUMMARY.md"}, det
    # each is judged against the frozen copy, not against HEAD
    assert 'cmp -s "$F" "$RUNNER_TEMP/frozen/$F"' in restore
    # and they are still not simply allowed
    allowed = set(re.search(r'ALLOWED="([^"]+)"', restore).group(1).split())
    assert not (det & allowed), "a deterministic file is allowlisted again"


def test_a_pure_line_move_is_not_treated_as_timestamp_only():
    """Sorting the two sides made a moved paragraph look identical to a date
    change; ordering alone does not separate them either, because a move has
    identical sides by definition. The unmasked sides decide.
    (Codex, PR #1009.)"""
    detect = {s.get("name"): s.get("run") or "" for s in _steps()}["Detect meaningful changes"]
    assert "| sort >" not in detect, "the sorted comparison is back; a line move would be reverted"
    assert ".rold" in detect and ".rnew" in detect, "the unmasked sides are not compared"
    # timestamp-only requires masked-equal AND unmasked-different
    assert 'diff -q "/tmp/${DIFF_NAME}.rold" "/tmp/${DIFF_NAME}.rnew"' in detect


def test_the_wif_credentials_file_is_ignored_and_the_guard_says_so():
    """google-github-actions/auth@v2 writes gha-creds-*.json into
    $GITHUB_WORKSPACE on every run. Untracked and unignored, it was picked up by
    the stray-write scan, so EVERY run would have died at
    "the model wrote outside the generated docs" before verification or the PR.
    (Codex, PR #1009.)"""
    import subprocess
    gitignore = (REPO / ".gitignore").read_text()
    assert "gha-creds-*.json" in gitignore, "the WIF credentials file is not ignored"
    # the pattern must actually take effect: a later negation could undo it
    probe = subprocess.run(["git", "check-ignore", "-q", "gha-creds-probe.json"],
                           cwd=REPO)
    assert probe.returncode == 0, "gha-creds-*.json is present but does not match"
    # and the workflow asserts it rather than trusting it
    restore = {s.get("name"): s.get("run") or "" for s in _steps()}[
        "Restore gate inputs and refuse model edits outside the docs"]
    assert "git check-ignore -q gha-creds-probe.json" in restore, \
        "the stray-write step does not verify the credentials file is ignored"
    assert restore.index("git check-ignore -q gha-creds-probe.json") < restore.index('STRAY=""'), \
        "the guard must run before the scan it protects"


def test_auth_still_writes_the_credentials_file_the_gemini_steps_need():
    """The fix is to ignore the file, not to stop creating it: gcloud, the
    BigQuery client and the Gemini CLI on Vertex all resolve ADC through it."""
    auth = [s for s in _steps() if str(s.get("uses", "")).startswith("google-github-actions/auth")]
    assert len(auth) == 1, auth
    assert "create_credentials_file" not in (auth[0].get("with") or {}), \
        "credential-file creation was disabled; ADC for gcloud/BigQuery/Gemini would break"
