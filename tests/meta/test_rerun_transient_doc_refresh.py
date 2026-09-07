"""The job-level re-run fires on a Vertex transport stall and nothing else.

Run 20 of the monthly refresh died on `UND_ERR_BODY_TIMEOUT` from the Gemini
CLI's undici client; run 21 completed the same step normally, confirming it
transient. One vendor blip should not cost the whole unattended monthly run.

An in-job retry was tried first and abandoned: retrying inside the job starts
a second CLI process in a workspace the model has already written to, and
every guard that needs is a guard that can be got wrong. Re-running the JOB
gets a fresh checkout, so none of it applies. What is left to get right is the
classification, and the classifier reads a log the model's own stdout is part
of -- so these tests RUN it rather than reading its shape.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github/workflows/rerun-transient-doc-refresh.yml"
REFRESH = REPO / ".github/workflows/refresh-architecture-docs.yml"
DOC = yaml.safe_load(WORKFLOW.read_text())
STEP = next(st["run"] for st in DOC["jobs"]["rerun"]["steps"] if "run" in st)
# YAML 1.1 reads a bare `on:` key as the boolean True.
TRIGGERS = DOC.get("on", DOC.get(True))

# Run 20's real tail, with the timestamps GitHub prefixes onto log lines.
REAL_STALL = """\
2026-09-07T17:06:59.6028585Z Error when talking to Gemini API Full report available at: /tmp/gemini-client-error-Turn.run-sendMessageStream-2026-09-07T17-06-59-594Z.json TypeError: terminated
2026-09-07T17:06:59.6042582Z   [cause]: BodyTimeoutError: Body Timeout Error
2026-09-07T17:06:59.6049884Z     code: 'UND_ERR_BODY_TIMEOUT'
2026-09-07T17:06:59.6051440Z An unexpected critical error occurred:[object Object]
2026-09-07T17:06:59.6400154Z ##[error]Process completed with exit code 1.
"""

# Run 16's shape: the model could not read its inputs and said so.
REAL_REFUSAL = """\
2026-09-07T13:20:44.8Z The input file refresh-inputs/billing_by_sku.csv could not be read
2026-09-07T13:20:44.9Z (ignored by configured ignore patterns). Stopping.
2026-09-07T13:20:45.0Z ##[error]Process completed with exit code 1.
"""

# The model quoting the signature list it can read out of the repo.
ECHOED = """\
2026-09-07T13:20:44.8Z I inspected the workflow; it mentions UND_ERR_BODY_TIMEOUT
2026-09-07T13:20:44.8Z and TypeError: terminated and ECONNRESET as retry signals.
2026-09-07T13:20:44.9Z The input file could not be read. Stopping.
2026-09-07T13:20:45.0Z ##[error]Process completed with exit code 1.
"""

# The model quoting the CLI's fatal PREFIX and, separately, a transport token.
# Two independent greps were both satisfied by this. (Codex, PR #1032.)
ECHOED_ANCHORED = """\
2026-09-07T13:20:44.7Z Error when talking to Gemini API Full report available at: /tmp/x.json Error: quoted
2026-09-07T13:20:44.8Z The docs mention UND_ERR_BODY_TIMEOUT as the retry signal.
2026-09-07T13:20:44.9Z The input file could not be read. Stopping.
2026-09-07T13:20:45.0Z ##[error]Process completed with exit code 1.
"""

# A REAL non-transport CLI failure, from this project's own Gemini logs. The
# CLI emits the same prefix and the same report path for an internal error --
# which is why the prefix alone never discriminated, and the cause on that
# same line does.
REAL_CLI_INTERNAL_ERROR = """\
2026-09-07T09:05:01.2Z Error when talking to Gemini API Full report available at: /tmp/gemini-client-error-Turn.run-sendMessageStream-2026-09-07T09-05-01-225Z.json Error: Couldn't complete the request
2026-09-07T09:05:01.3Z ##[error]Process completed with exit code 1.
"""


SCRIPT = REPO / ".github/scripts/is_transient_gemini_failure.sh"


def _classify(log_text: str, tmp_path=None) -> bool:
    """Run the REAL classifier script over a log, returning whether it would
    re-run. `gh` is stubbed on PATH so the script's own API calls and its own
    parsing are exercised -- not a reconstruction of them.

    An earlier helper rebuilt the condition from variables scraped out of the
    workflow and so tested a combination the workflow did not use: it reported
    run 20's real log as not-a-transport-failure while the shipped code would
    have recognised it. A test that reconstructs the logic it checks is not
    checking that logic.
    """
    import tempfile
    d = Path(tmp_path or tempfile.mkdtemp())
    (d / "log.txt").write_text(log_text)
    bin_dir = d / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        # `gh api .../jobs` -> one failed job id; `gh api .../logs` -> the log.
        'case "$*" in\n'
        '  *"/logs"*) cat "$LOG_FIXTURE" ;;\n'
        '  *) echo 1 ;;\n'
        'esac\n'
    )
    gh.chmod(0o755)
    env = dict(os.environ)
    env.update(PATH=f"{bin_dir}:{env['PATH']}", REPO="TeneikaAskew/stocks",
               LOG_FIXTURE=str(d / "log.txt"))
    out = subprocess.run(["bash", str(SCRIPT), "12345"], cwd=d, env=env,
                         capture_output=True, text=True)
    return out.returncode == 0


def test_workflow_yaml_is_valid_and_watches_the_refresh():
    assert TRIGGERS["workflow_run"]["workflows"] == ["Monthly architecture doc refresh"]
    assert TRIGGERS["workflow_run"]["types"] == ["completed"]
    # The name it watches must be the refresh workflow's actual name, or this
    # never fires and nothing says so.
    assert yaml.safe_load(REFRESH.read_text())["name"] == "Monthly architecture doc refresh"


def test_it_is_bounded_to_one_rerun_per_run():
    """`run_attempt == 1` is what stops a loop, and it needs no state."""
    cond = " ".join(DOC["jobs"]["rerun"]["if"].split())
    assert "github.event.workflow_run.conclusion == 'failure'" in cond
    assert "github.event.workflow_run.run_attempt == 1" in cond


# What `gh run view --log-failed` actually emits: job and step columns before
# the timestamp. The classifier must NEVER be fed this -- a start-anchored
# match sees the job name, not the CLI's emitter, so a real stall would stay
# red and the workflow would be a silent no-op. (Codex, PR #1032.)
GH_RUN_VIEW_COLUMNS = (
    "refresh\tRegenerate 05-c-DATA_DEPENDENCIES.md\t"
    "2026-09-07T17:06:59.6028585Z Error when talking to Gemini API Full report "
    "available at: /tmp/gemini-client-error-x.json TypeError: terminated\n"
)


# Codex's exact forgery: the model emitting the COMPLETE expected line, with a
# plausible-looking report path, before the CLI exits for an unrelated refusal.
FORGED_FULL_RECORD = """\
2026-09-07T13:20:44.7Z Error when talking to Gemini API Full report available at: /tmp/gemini-client-error-forged.json TypeError: terminated
2026-09-07T13:20:44.9Z The input file could not be read. Stopping.
2026-09-07T13:20:45.0Z ##[error]Process completed with exit code 1.
"""


def test_a_fully_forged_record_is_still_accepted_and_that_is_bounded():
    """Codex P2, round 8, reproduced -- and NOT fixed, deliberately.

    The classifier matches a textual shape in a stream that merges the model's
    stdout with the CLI's stderr, so a model emitting the whole line verbatim
    is believed. This test pins that as a known limit rather than letting it be
    discovered later as a surprise.

    Separating the CLI's diagnostics would need the refresh workflow to capture
    stderr to its own file, and that file would live in the workspace the model
    can write to -- not obviously stronger, and it would un-revert a workflow
    this PR deliberately restored to byte-identical with main.

    What bounds the damage is the job-level design, not the match:

      * a false positive costs one re-run and can publish nothing, because the
        re-run passes through every gate exactly as a first attempt does
      * the cleanup job re-derives this verdict from attempt 1 before closing
        anything, so a forgery cannot close a still-actionable failure PR
    """
    assert _classify(FORGED_FULL_RECORD) is True, \
        "if this now returns False the limitation is fixed -- update the docs and this test"


def test_the_cleanup_is_gated_on_re_deriving_the_verdict():
    """The bound that makes the forgery above tolerable: the only consequence
    with lasting effect -- closing someone's failure PR -- re-checks attempt 1
    rather than trusting that a re-run happened."""
    job = DOC["jobs"]["close-obsolete-failure-pr"]
    run = next(st for st in job["steps"] if "run" in st)["run"]
    assert 'is_transient_gemini_failure.sh "$RUN_ID" 1' in run
    # And it must bail out, not continue, when attempt 1 was a real failure.
    assert "leaving its failure PR alone" in run and "exit 0" in run


def test_the_classifier_reads_raw_job_logs_not_gh_run_view():
    """`gh run view --log-failed` prefixes `<job>\\t<step>\\t<timestamp> ...`, so
    the start-anchored record never matches and nothing is ever re-run. The raw
    per-job log endpoint returns timestamp-first lines, which is the shape every
    real sample in this file was taken from."""
    # Comments only, stripped: the step explains at length WHY it does not use
    # `gh run view --log-failed`, and a naive substring check trips on that
    # explanation rather than on the code -- a trap this repo has hit before.
    code = "\n".join(ln.split("#", 1)[0] for ln in SCRIPT.read_text().splitlines())
    assert "actions/jobs/" in code and "/logs" in code, \
        "the classifier does not read raw per-job logs"
    assert "--log-failed" not in code and "run view" not in code, \
        "the classifier is back on gh run view, whose column prefixes it cannot parse"
    # And prove it: the columned shape is not recognised, so if the workflow
    # ever fed it that, this test fails rather than the workflow going quiet.
    assert _classify(GH_RUN_VIEW_COLUMNS) is False


def test_a_failed_recovery_is_not_silent():
    """Repo convention (.github/workflows/README.md): a workflow without a
    handle-failure job fails only on the Actions page. If the recovery itself
    breaks -- logs unavailable, a rerun API error -- the original issue would
    record only the stall."""
    hf = DOC["jobs"]["handle-failure"]
    assert hf["uses"] == "./.github/workflows/handle-workflow-failure.yml"
    assert hf["if"] == "failure()"
    assert set(hf["needs"]) == {"rerun", "close-obsolete-failure-pr"}
    # No second placeholder PR for a failure of the thing that cleans up
    # placeholder PRs.
    assert hf["with"]["create_pr"] is False
    # handle-workflow-failure.yml declares PR_WORKFLOW_TOKEN required: true.
    # Omitting it makes the call invalid, so the handler this job exists to
    # provide would never run -- the reporting gap, still unreported.
    # (Codex, PR #1032.)
    reusable = yaml.safe_load((REPO / ".github/workflows/handle-workflow-failure.yml").read_text())
    required = {k for k, v in (reusable.get("on", reusable.get(True))["workflow_call"]
                               .get("secrets") or {}).items() if v.get("required")}
    assert required <= set(hf.get("secrets") or {}), \
        f"required secrets not passed to the reusable workflow: {required - set(hf.get('secrets') or {})}"


def test_a_successful_rerun_closes_the_obsolete_failure_pr():
    """The refresh workflow's handler runs with create_pr: true, so a transient
    stall leaves a draft `fix/workflow-...` PR saying a fix is required. The
    issue is the incident record; the PR is an actionable no-op."""
    job = DOC["jobs"]["close-obsolete-failure-pr"]
    cond = " ".join(job["if"].split())
    assert "conclusion == 'success'" in cond
    assert "run_attempt > 1" in cond, "it would close the PR on a first-attempt success too"
    step = next(st for st in job["steps"] if "run" in st)
    # The branch name must match what the failure handler actually builds.
    src = (REPO / "scripts/handle_workflow_failure.py").read_text()
    assert 'f"fix/workflow-{workflow_file.replace(\'.yml\', \'\')}-{run_number}"' in src, \
        "the failure handler's branch pattern changed; this job's BRANCH must follow"
    assert step["env"]["BRANCH"].startswith("fix/workflow-refresh-architecture-docs-")
    assert "run_number" in step["env"]["BRANCH"]
    assert "gh pr close" in step["run"]
    # `run_attempt > 1` is not evidence this workflow caused the re-run: a
    # maintainer re-running a genuinely broken refresh by hand also lands here.
    # The verdict must be re-derived from attempt 1. (Codex, PR #1032.)
    assert 'is_transient_gemini_failure.sh "$RUN_ID" 1' in step["run"], \
        "the cleanup trusts the attempt counter instead of re-checking attempt 1"
    # --delete-branch would need contents: write, which this job has no other
    # reason to hold. Comments stripped: the step explains its own absence, and
    # a naive substring check trips on the explanation -- the third time that
    # trap has fired on this branch.
    run_code = "\n".join(ln.split("#", 1)[0] for ln in step["run"].splitlines())
    assert "--delete-branch" not in run_code
    assert job["permissions"]["contents"] == "read"


def test_it_can_rerun_and_asks_for_nothing_more():
    perms = DOC["permissions"]
    assert perms["actions"] == "write", "cannot re-run without actions: write"
    assert perms["contents"] == "read"
    assert set(perms) == {"actions", "contents"}, f"extra permissions: {perms}"
    assert DOC["jobs"]["close-obsolete-failure-pr"]["permissions"] == {
        "contents": "read", "pull-requests": "write"}
    assert "rerun-failed-jobs" in STEP


def test_run_20s_real_failure_is_recognised():
    assert _classify(REAL_STALL) is True


def test_a_real_repo_failure_is_left_red():
    """Run 16's shape. Re-running cannot fix an unreadable input, and the red
    run is what got it fixed."""
    assert _classify(REAL_REFUSAL) is False


def test_an_echoed_signature_does_not_trigger_a_rerun():
    """The log carries the model's own stdout, and the model can read the
    signature list out of this repo. A substring match would let it fake a
    vendor outage; the classifier wants the CLI's line-anchored fatal record
    AND a transport cause."""
    assert _classify(ECHOED) is False


def test_a_quoted_prefix_plus_a_quoted_token_does_not_trigger_a_rerun():
    """Codex P2, round 6. Two independent greps -- a fatal prefix somewhere and
    a transport token somewhere -- were both satisfiable by text the model
    wrote, because the log interleaves its stdout with the CLI's stderr. The
    match is now one attributable record on one line."""
    assert _classify(ECHOED_ANCHORED) is False


def test_a_real_internal_cli_error_is_left_red():
    """The CLI emits the same prefix and report path for internal errors. Two
    real samples from this project differ only in the cause on that line:

        ...gemini-client-error-<id>.json TypeError: terminated   -> transport
        ...gemini-client-error-<id>.json Error: Couldn't ...     -> internal
    """
    assert _classify(REAL_CLI_INTERNAL_ERROR) is False


def test_a_stall_scrolled_out_of_the_tail_is_not_recognised():
    """The CLI emits its fatal record last and exits, so only the tail counts.
    This is the bound that makes echoing hard rather than merely unlikely."""
    assert _classify(REAL_STALL + "".join(
        f"2026-09-07T17:07:0{i%10}.0Z line {i}\n" for i in range(60))) is False


def test_the_refresh_workflow_does_not_retry_in_job():
    """The in-job retry was abandoned deliberately (PR #1032). If one comes
    back, the guards this design removes have to come back with it."""
    refresh = yaml.safe_load(REFRESH.read_text())
    runs = [s.get("run") or "" for s in refresh["jobs"]["refresh"]["steps"]]
    gemini_steps = [r for r in runs if "gemini --model" in r]
    assert len(gemini_steps) == 4, f"expected 4 inline prompt steps, found {len(gemini_steps)}"
    for r in gemini_steps:
        assert "for ATTEMPT" not in r and "MAX_ATTEMPTS" not in r, \
            "an in-job retry loop is back in the refresh workflow"
