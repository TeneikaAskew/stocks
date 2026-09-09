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

import json
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



# What actually follows a failed Gemini step in the job log: the `if: failure()`
# artifact upload, then the runner's own post-job cleanup. Transcribed from run
# 20 (34145300708) -- 42 lines, which is what its failed job's last 42 lines
# hold, with no Gemini record among them. The COUNT is the point: a 40-line
# whole-job tail cannot reach past this to the record above it.
_POST_FAILURE_LINES = [
    "  CLOUDSDK_PROJECT: adept-mountain-474619-d4",
    "  GCLOUD_PROJECT: adept-mountain-474619-d4",
    "  GOOGLE_CLOUD_PROJECT: adept-mountain-474619-d4",
    "  CLOUDSDK_METRICS_ENVIRONMENT: github-actions-setup-gcloud",
    "  CLOUDSDK_METRICS_ENVIRONMENT_VERSION: 2.2.1",
    "##[endgroup]",
    "(node:3111) [DEP0040] DeprecationWarning: The `punycode` module is deprecated.",
    "(Use `node --trace-deprecation ...` to show where the warning was created)",
    "Multiple search paths detected. Calculating the least common ancestor of all paths",
    "The least common ancestor is /home/runner/work/stocks/stocks.",
    "With the provided path, there will be 4 files uploaded",
    "Artifact name is valid!",
    "Root directory input is valid!",
    "Beginning upload of artifact content to blob storage",
    "(node:3111) [DEP0169] DeprecationWarning: `url.parse()` behavior is not standardized.",
    "Uploaded bytes 66565",
    "Finished uploading artifact content to blob storage!",
    "SHA256 digest of uploaded artifact zip is b93d0b136e75b7fd776f0fc4861826108405033a",
    "Finalizing artifact upload",
    "Artifact regenerated-docs.zip successfully finalized. Artifact ID 10027741656",
    "Artifact regenerated-docs has been successfully uploaded! Final size is 66565 bytes.",
    "Artifact download URL: https://github.com/TeneikaAskew/stocks/actions/runs/34145300708/artifacts/10027741656",
    "Node 20 is being deprecated. This workflow is running with Node 24 by default.",
    "Post job cleanup.",
    'Removed exported credentials at "/home/runner/work/stocks/stocks/gha-creds-c9d19b5809b1981c.json".',
    "Node 20 is being deprecated. This workflow is running with Node 24 by default.",
    "Post job cleanup.",
    "[command]/usr/bin/git version",
    "git version 2.55.0",
    "Temporarily overriding HOME before making global git config changes",
    "Adding repository directory to the temporary git global config as a safe directory",
    "[command]/usr/bin/git config --global --add safe.directory /home/runner/work/stocks/stocks",
    "[command]/usr/bin/git config --local --name-only --get-regexp core.sshCommand",
    "[command]/usr/bin/git submodule foreach --recursive sh -c 'git config core.sshCommand'",
    "[command]/usr/bin/git config --local --name-only --get-regexp http.https://github.com/.extraheader",
    "http.https://github.com/.extraheader",
    "[command]/usr/bin/git config --local --unset-all http.https://github.com/.extraheader",
    "[command]/usr/bin/git submodule foreach --recursive sh -c 'git config extraheader'",
    "[command]/usr/bin/git config --local --name-only --get-regexp ^includeIf.gitdir:",
    "[command]/usr/bin/git submodule foreach --recursive git config --local --show-origin",
    "Cleaning up orphan processes",
    "##[warning]Node.js 20 is deprecated.",
]
assert len(_POST_FAILURE_LINES) == 42, len(_POST_FAILURE_LINES)
# The first few land in the same SECOND as the failed step's completed_at, as
# they do in the real log: the API reports whole seconds, so the window carries
# a second of slop by construction and these lines are inside it. They are not
# records, so being inside changes nothing -- which is the point of checking.
POST_FAILURE_NOISE = "".join(
    (f"2026-09-07T17:06:59.{64 + i}Z " if i < 6 else f"2026-09-07T17:07:00.{i:02d}Z ") + line + "\n"
    for i, line in enumerate(_POST_FAILURE_LINES))


SCRIPT = REPO / ".github/scripts/is_transient_gemini_failure.sh"


def _classify(log_text: str, window="all", tmp_path=None) -> bool:
    return _classify_rc(log_text, window, tmp_path) == 0


def _classify_rc(log_text: str, window="all", tmp_path=None, fail_on: str = "") -> int:
    """Run the REAL classifier script over a log, returning whether it would
    re-run. `gh` is stubbed on PATH so the script's own API calls and its own
    parsing are exercised -- not a reconstruction of them.

    `window` is the failed step's (started_at, completed_at) as the jobs API
    reports it, or a list of them; "all" spans every timestamp in `log_text`,
    and `()` is a job that failed with no failed step to attribute it to.
    Spanning everything is a fixture convenience for the tests that are about
    the RECORD's shape rather than about where it sits.

    An earlier helper rebuilt the condition from variables scraped out of the
    workflow and so tested a combination the workflow did not use: it reported
    run 20's real log as not-a-transport-failure while the shipped code would
    have recognised it. A test that reconstructs the logic it checks is not
    checking that logic.
    """
    import tempfile
    d = Path(tmp_path or tempfile.mkdtemp())
    (d / "log.txt").write_text(log_text)

    if window == "all":
        stamps = sorted(re.findall(r"^(\S+Z) ", log_text, re.M))
        window = [(stamps[0], stamps[-1])] if stamps else []
    elif window and isinstance(window[0], str):
        window = [window]
    (d / "windows.txt").write_text("".join(f"{lo}\t{hi}\n" for lo, hi in window))

    bin_dir = d / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        # `.../jobs?per_page=` -> one failed job id; `.../jobs/<id>` -> the
        # failed step windows; `.../jobs/<id>/logs` -> the raw log.
        # FAIL_ON names a request fragment that must fail the way a 403 or an
        # unavailable log does: gh exits 1.
        'if [ -n "$FAIL_ON" ] && [[ "$*" == *"$FAIL_ON"* ]]; then echo "gh: HTTP 403" >&2; exit 1; fi\n'
        'case "$*" in\n'
        # Refuses an escape-sequence body without the flag, as gh does; the
        # first production run of the classifier died on exactly that.
        '  *"/logs"*)\n'
        '    if grep -q $\'\\x1b\' "$LOG_FIXTURE" && [[ "$*" != *"--allow-escape-sequences"* ]]; then\n'
        '      echo "the response contains terminal escape sequences; pass --allow-escape-sequences to output it anyway" >&2; exit 1; fi\n'
        '    cat "$LOG_FIXTURE" ;;\n'
        '  *"actions/jobs/"*) cat "$WINDOW_FIXTURE" ;;\n'
        '  *) echo 1 ;;\n'
        'esac\n'
    )
    gh.chmod(0o755)
    env = dict(os.environ)
    env.update(PATH=f"{bin_dir}:{env['PATH']}", REPO="TeneikaAskew/stocks",
               LOG_FIXTURE=str(d / "log.txt"), WINDOW_FIXTURE=str(d / "windows.txt"),
               FAIL_ON=fail_on)
    out = subprocess.run(["bash", str(SCRIPT), "12345"], cwd=d, env=env,
                         capture_output=True, text=True)
    return out.returncode


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


def test_the_annotate_job_re_derives_the_verdict_and_never_closes():
    """Round 8 asked for the verdict to be re-derived before acting; round 11
    pointed out that the same classifier over the same attempt-1 log is not
    independent evidence, so a forged record believed once is believed twice.
    The re-derivation stays -- it is what distinguishes a stall from a
    maintainer's hand re-run of a real failure, and words the comment -- but
    the one action with lasting effect, closing someone's PR, is gone."""
    job = DOC["jobs"]["annotate-obsolete-failure-pr"]
    run = next(st for st in job["steps"] if "run" in st)["run"]
    assert 'is_transient_gemini_failure.sh "$RUN_ID" 1' in run
    assert "leaving its failure PR alone" in run
    code = "\n".join(ln.split("#", 1)[0] for ln in run.splitlines())
    assert "gh pr close" not in code and "--delete-branch" not in code


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
    assert set(hf["needs"]) == {"rerun", "annotate-obsolete-failure-pr"}
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


def test_a_successful_rerun_annotates_the_obsolete_failure_pr():
    """The refresh workflow's handler runs with create_pr: true, so a transient
    stall leaves a draft `fix/workflow-...` PR saying a fix is required. The
    issue is the incident record; the PR gets told the re-run succeeded."""
    job = DOC["jobs"]["annotate-obsolete-failure-pr"]
    cond = " ".join(job["if"].split())
    assert "conclusion == 'success'" in cond
    assert "run_attempt > 1" in cond, "it would annotate on a first-attempt success too"
    step = next(st for st in job["steps"] if "run" in st)
    # The branch name must match what the failure handler actually builds.
    src = (REPO / "scripts/handle_workflow_failure.py").read_text()
    assert 'f"fix/workflow-{workflow_file.replace(\'.yml\', \'\')}-{run_number}"' in src, \
        "the failure handler's branch pattern changed; this job's BRANCH must follow"
    assert step["env"]["BRANCH"].startswith("fix/workflow-refresh-architecture-docs-")
    assert "run_number" in step["env"]["BRANCH"]
    assert "gh pr comment" in step["run"]
    assert 'is_transient_gemini_failure.sh "$RUN_ID" 1' in step["run"], \
        "the job trusts the attempt counter instead of re-checking attempt 1"
    assert job["permissions"]["contents"] == "read"


def test_it_can_rerun_and_asks_for_nothing_more():
    perms = DOC["permissions"]
    assert perms["actions"] == "write", "cannot re-run without actions: write"
    assert perms["contents"] == "read"
    assert set(perms) == {"actions", "contents"}, f"extra permissions: {perms}"
    # A job-level permissions block REPLACES the workflow-level one. The
    # cleanup job runs the classifier, which reads attempt 1's jobs and logs
    # through the API, so it needs actions: read of its own -- an earlier
    # version had only contents/pull-requests here and would have failed on
    # its first `gh api .../actions/...` call, every time.
    assert DOC["jobs"]["annotate-obsolete-failure-pr"]["permissions"] == {
        "actions": "read", "contents": "read", "pull-requests": "write"}
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


def test_the_stall_is_recognised_behind_its_post_failure_output():
    """The defect that made the whole workflow a no-op. (Codex P1, round 9.)

    An earlier version matched in the last 40 lines of the WHOLE job. But the
    refresh job runs `Upload the regenerated documents when a gate fails`
    (`if: failure()`) and then the runner's post-job cleanup after the Gemini
    step dies, and all of it lands in the same log after the fatal record.

    Measured, not assumed: run 20 (34145300708) is the stall this workflow was
    written for, and its failed job's last 42 log lines contain no Gemini
    record at all -- they start at 17:06:59.6486851Z, after the record at
    17:06:59.6028585Z, and run to the end of cleanup. The shipped tail would
    have called that run "the repo's own failure" and never re-run it.
    """
    assert _classify(REAL_STALL + POST_FAILURE_NOISE,
                     window=("2026-09-07T17:00:14Z", "2026-09-07T17:06:59Z")) is True
    # And the noise alone is not a stall, so the window is doing the work.
    assert _classify(POST_FAILURE_NOISE,
                     window=("2026-09-07T17:00:14Z", "2026-09-07T17:06:59Z")) is False


def test_a_record_outside_the_failed_step_does_not_count():
    """Narrower than the old whole-job tail, not merely bigger: a record
    emitted while a step that SUCCEEDED was running did not fail this job."""
    log = (
        "2026-09-07T17:00:01.0Z Error when talking to Gemini API Full report available at:"
        " /tmp/gemini-client-error-earlier.json TypeError: terminated\n"
        "2026-09-07T17:05:05.0Z The input file could not be read. Stopping.\n"
        "2026-09-07T17:05:05.1Z ##[error]Process completed with exit code 1.\n"
    )
    assert _classify(log, window=("2026-09-07T17:05:00Z", "2026-09-07T17:05:10Z")) is False


def test_a_job_with_no_failed_step_is_not_transient():
    """Cancellation or a job-level timeout leaves no failed step to attribute
    the failure to. Fail closed: the run stays red (Rule 3.7)."""
    assert _classify(REAL_STALL, window=()) is False


def test_the_failed_step_filter_is_the_one_the_script_runs():
    """The window comes from a jq filter, so run THAT filter -- a stub that
    hands back an already-filtered answer tests nothing about it."""
    filt = re.search(r"FAILED_STEP_JQ='([^']*)'", SCRIPT.read_text()).group(1)
    payload = {"steps": [
        {"name": "Checkout", "conclusion": "success",
         "started_at": "2026-09-07T16:54:00Z", "completed_at": "2026-09-07T16:54:20Z"},
        {"name": "Regenerate 05-c-DATA_DEPENDENCIES.md", "conclusion": "failure",
         "started_at": "2026-09-07T17:00:14Z", "completed_at": "2026-09-07T17:06:59Z"},
        {"name": "Never started", "conclusion": "failure",
         "started_at": None, "completed_at": None},
        {"name": "Upload the regenerated documents when a gate fails",
         "conclusion": "success",
         "started_at": "2026-09-07T17:06:59Z", "completed_at": "2026-09-07T17:07:00Z"},
    ]}
    out = subprocess.run(["jq", "-r", filt], input=json.dumps(payload),
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["2026-09-07T17:00:14Z", "2026-09-07T17:06:59Z"]


def test_the_refresh_workflow_does_not_retry_in_job():
    """The in-job retry was abandoned deliberately (PR #1032). If one comes
    back, the guards this design removes have to come back with it."""
    refresh = yaml.safe_load(REFRESH.read_text())
    runs = [s.get("run") or "" for s in refresh["jobs"]["refresh"]["steps"]]
    gemini_steps = [r for r in runs if "gemini --model" in r]
    # three: 05-a, 05-c and 05-d. README is rendered, not regenerated. (Run 32.)
    assert len(gemini_steps) == 3, f"expected 3 inline prompt steps, found {len(gemini_steps)}"
    for r in gemini_steps:
        assert "for ATTEMPT" not in r and "MAX_ATTEMPTS" not in r, \
            "an in-job retry loop is back in the refresh workflow"


# ── the cleanup step, executed ──────────────────────────────────────────────

CLEANUP_STEP = next(st for st in DOC["jobs"]["annotate-obsolete-failure-pr"]["steps"] if "run" in st)
RERUN_STEP = next(st for st in DOC["jobs"]["rerun"]["steps"] if "run" in st)

CLEANUP_GH_STUB = """#!/usr/bin/env bash
echo "$@" >> "$GH_CALLS"
if [ -n "$FAIL_ON" ] && [[ "$*" == *"$FAIL_ON"* ]]; then echo "gh: HTTP 403" >&2; exit 1; fi
case "$*" in
  *"/logs"*)
    if grep -q $'\x1b' "$LOG_FIXTURE" && [[ "$*" != *"--allow-escape-sequences"* ]]; then
      echo "the response contains terminal escape sequences; pass --allow-escape-sequences to output it anyway" >&2; exit 1; fi
    cat "$LOG_FIXTURE" ;;
  *"actions/jobs/"*)      cat "$WINDOW_FIXTURE" ;;
  *"attempts/1/jobs"*)    echo 1 ;;
  *"/jobs?per_page="*)    echo 1 ;;
  *"pulls?state=open&head="*) printf '%s' "$PER_RUN_PR" ;;
  *"pulls?state=open&per_page="*) printf '%s' "$OLDER_PR" ;;
  "pr comment"*)          printf '%s' "$*" >> "$GH_OUT/comments.txt" ;;
  "pr close"*)            printf '%s' "$*" >> "$GH_OUT/closes.txt" ;;
  "api --method POST"*)   printf '%s' "$*" >> "$GH_OUT/reruns.txt" ;;
esac
"""


def _run_cleanup(tmp_path, *, log_text, per_run_pr="", older_pr="", fail_on="", step=None):
    """Run the cleanup step's own script. `gh` answers the classifier's calls
    with the given log and a window spanning it, the per-run PR lookup with
    `per_run_pr`, and the prefix lookup with `older_pr` -- both already in
    the shape `--jq` would have produced, since the stub ignores --jq."""
    d = tmp_path
    (d / "log.txt").write_text(log_text)
    stamps = sorted(re.findall(r"^(\S+Z) ", log_text, re.M))
    (d / "windows.txt").write_text(f"{stamps[0]}\t{stamps[-1]}\n" if stamps else "")
    bin_dir = d / "bin"; bin_dir.mkdir()
    out = d / "out"; out.mkdir()
    (bin_dir / "gh").write_text(CLEANUP_GH_STUB)
    (bin_dir / "gh").chmod(0o755)
    env = dict(os.environ)
    env.update(PATH=f"{bin_dir}:{env['PATH']}", GH_TOKEN="stub",
               REPO="TeneikaAskew/stocks", RUN_ID="777",
               BRANCH="fix/workflow-refresh-architecture-docs-25",
               RUN_URL="https://example.invalid/run/777",
               LOG_FIXTURE=str(d / "log.txt"), WINDOW_FIXTURE=str(d / "windows.txt"),
               GH_OUT=str(out), GH_CALLS=str(out / "calls.txt"),
               PER_RUN_PR=per_run_pr, OLDER_PR=older_pr, FAIL_ON=fail_on,
               GITHUB_STEP_SUMMARY=str(out / "summary.md"))
    proc = subprocess.run(["bash", "-c", (step or CLEANUP_STEP)["run"]], cwd=REPO, env=env,
                          capture_output=True, text=True)
    comments = (out / "comments.txt").read_text() if (out / "comments.txt").exists() else ""
    closes = (out / "closes.txt").read_text() if (out / "closes.txt").exists() else ""
    return proc, comments, closes


def test_the_per_run_pr_is_annotated_and_never_closed(tmp_path):
    """Round 11: the re-check is the same classifier over the same log, so it
    cannot be the evidence that closes a PR. The job tells the PR what it
    found and leaves the decision to a person."""
    proc, comments, closes = _run_cleanup(tmp_path, log_text=REAL_STALL, per_run_pr="4242")
    assert proc.returncode == 0, proc.stderr
    assert "pr comment 4242" in comments
    assert "not closed automatically" in comments
    assert closes == "", closes


def test_cleanup_annotates_but_never_closes_an_older_failure_pr(tmp_path):
    """The handler creates fix/...-<run_number> only when no failure PR for
    this workflow is open; otherwise it comments "please review this
    additional failure" on the existing one. That PR is about an EARLIER
    failure and must survive; the request it now carries must not."""
    proc, comments, closes = _run_cleanup(tmp_path, log_text=REAL_STALL, older_pr="1021")
    assert proc.returncode == 0, proc.stderr
    assert "pr comment 1021" in comments
    assert "transient Vertex transport stall" in comments
    assert closes == "", closes


def test_cleanup_touches_nothing_when_attempt_1_was_a_real_failure(tmp_path):
    proc, comments, closes = _run_cleanup(tmp_path, log_text=REAL_REFUSAL,
                                          per_run_pr="4242", older_pr="1021")
    assert proc.returncode == 0, proc.stderr
    assert "was not a transport stall" in proc.stdout
    assert comments == "" and closes == ""


def test_cleanup_is_quiet_when_no_failure_pr_exists(tmp_path):
    proc, comments, closes = _run_cleanup(tmp_path, log_text=REAL_STALL)
    assert proc.returncode == 0, proc.stderr
    assert "nothing to annotate" in proc.stdout
    assert comments == "" and closes == ""


def test_the_older_pr_lookup_matches_the_handlers_own_prefix():
    """`find_existing_pr` matches `OWNER:fix/workflow-<file>-`; the lookup
    here strips the run number off BRANCH to rebuild exactly that prefix."""
    src = (REPO / "scripts/handle_workflow_failure.py").read_text()
    assert 'head_pattern = f"{self.owner}:fix/workflow-{workflow_base}-"' in src
    run = CLEANUP_STEP["run"]
    assert 'startswith(\\"${REPO%%/*}:${BRANCH%-*}-\\")' in run


# ── the exit-code contract, executed ────────────────────────────────────────

def test_an_api_failure_is_could_not_classify_not_a_negative():
    """Round 11. `gh` exits 1 on a failed request and so did "not transient",
    so a 403 or an unavailable log was indistinguishable from evidence of a
    real failure: the caller took its negative branch and the recovery went
    green having examined nothing. Three codes now, and every request goes
    through a wrapper that maps its failure to 2."""
    assert _classify_rc(REAL_STALL) == 0
    assert _classify_rc(REAL_REFUSAL) == 1
    assert _classify_rc(REAL_STALL, fail_on="/logs") == 2
    assert _classify_rc(REAL_STALL, fail_on="actions/jobs/") == 2
    assert _classify_rc(REAL_STALL, fail_on="/jobs?per_page") == 2


def test_the_rerun_step_reruns_only_on_0_and_fails_on_2(tmp_path):
    """The step's own script, executed. 0 re-runs, 1 leaves the run red and
    exits clean, 2 fails the step -- which is what fires handle-failure."""
    for log, fail_on, want_rc, want_rerun in (
        (REAL_STALL, "", 0, True),
        (REAL_REFUSAL, "", 0, False),
        (REAL_STALL, "/logs", 2, False),
    ):
        sub = tmp_path / f"case-{len(list(tmp_path.iterdir()))}"
        sub.mkdir()
        proc, _, _ = _run_cleanup(sub, log_text=log, fail_on=fail_on, step=RERUN_STEP)
        reruns = sub / "out" / "reruns.txt"
        assert proc.returncode == want_rc, (log[:40], fail_on, proc.stdout, proc.stderr)
        assert reruns.exists() == want_rerun, (fail_on, proc.stdout)
        if want_rerun:
            assert "rerun-failed-jobs" in reruns.read_text()


def test_the_annotate_step_fails_on_2_rather_than_leaving_a_pr_quietly(tmp_path):
    proc, comments, closes = _run_cleanup(tmp_path, log_text=REAL_STALL, per_run_pr="4242",
                                          fail_on="/logs")
    assert proc.returncode == 2, (proc.stdout, proc.stderr)
    assert "could not classify" in proc.stdout
    assert comments == "" and closes == ""


def test_a_long_section_after_the_record_does_not_become_a_false_negative():
    """Codex P2, round 12. `printf "$SECTION" | grep -q` under `set -o
    pipefail`: grep exits on its first match, and if more than a pipe buffer
    of output is still to be written, printf takes SIGPIPE, the pipeline is
    non-zero, and the `if` reads a confirmed stall as "not transient". The
    ERR trap does not fire inside an `if`, so nothing said so. The model can
    emit as much as it likes after the CLI's fatal line -- and did, in the
    transcripts this workflow has already seen -- so the trailer here is a
    megabyte of in-window lines behind run 20's real record."""
    trailer = "".join(f"2026-09-07T17:06:59.7{i:06d}Z model output line {i} " + "x" * 80 + "\n"
                      for i in range(12000))
    assert len(trailer) > 1_000_000
    assert _classify_rc(REAL_STALL + trailer) == 0


# Run 24's real shape: the runner colours its own `##[group]Run` echo of the
# step script, so every real job log carries ANSI sequences. gh refuses to
# print such a body unless told to, and the first production execution of the
# classifier died on exactly that -- exit 2 on every real log.
ANSI_STEP_HEADER = (
    "2026-09-07T22:19:40.5620813Z \x1b[36;1m    echo \"blocking. Each line is a claim\"\x1b[0m\n"
    "2026-09-07T22:19:40.5621244Z \x1b[36;1m    exit $FAIL\x1b[0m\n"
    "2026-09-07T22:19:40.5667162Z ##[endgroup]\n"
)


def test_a_real_log_with_ansi_sequences_is_read_not_refused():
    """The stub refuses exactly as gh does when the flag is absent, so this
    can only pass if the script asks for escape sequences and then strips
    them before matching."""
    assert _classify_rc(ANSI_STEP_HEADER + REAL_STALL) == 0
    assert _classify_rc(ANSI_STEP_HEADER + REAL_REFUSAL) == 1
    # And a record wrapped in colour is still anchored at start of line.
    coloured = REAL_STALL.replace("Z Error when talking", "Z \x1b[31mError when talking", 1)
    assert _classify_rc(ANSI_STEP_HEADER + coloured) == 0


# Run 25's real failure (34169070513, 2026-09-07 23:25:58Z): Vertex answered
# 429 RESOURCE_EXHAUSTED ten times over six minutes, the CLI's own backoff gave
# up, and it emitted the same attributable record with a different cause. The
# classifier read the log (the #1039 fix held) and correctly, by its rules at
# the time, left the run red: a quota exhaustion the vendor tells you to retry
# is as transient as a stalled body and costs the same unattended refresh.
REAL_QUOTA = """\
2026-09-07T23:25:58.8115932Z Attempt 10 failed: Resource exhausted. Please try again later. Please refer to https://cloud.google.com/vertex-ai/generative-ai/docs/error-code-429 for more details.. Max attempts reached
2026-09-07T23:25:58.8209197Z Error when talking to Gemini API Full report available at: /tmp/gemini-client-error-Turn.run-sendMessageStream-2026-09-07T23-25-58-812Z.json RetryableQuotaError: Resource exhausted. Please try again later. Please refer to https://cloud.google.com/vertex-ai/generative-ai/docs/error-code-429 for more details.
2026-09-07T23:25:58.8210989Z     at classifyGoogleError (file:///opt/hostedtoolcache/node/20.20.2/x64/lib/node_modules/@google/gemini-cli/bundle/chunk-UN6XCVMJ.js:269736:14)
2026-09-07T23:25:58.8221543Z   cause: {
2026-09-07T23:25:58.8221768Z     code: 429,
2026-09-07T23:25:58.8228116Z An unexpected critical error occurred:[object Object]
2026-09-07T23:25:58.8368595Z ##[error]Process completed with exit code 1.
"""


def test_run_25s_quota_exhaustion_is_transient():
    assert _classify_rc(ANSI_STEP_HEADER + REAL_QUOTA) == 0


def test_a_quota_word_outside_the_cli_record_is_not_enough():
    """The cause must sit on the CLI's own record line. The model can write
    "RetryableQuotaError" into its stdout as easily as any other token."""
    echoed = (
        "2026-09-07T23:20:00.0Z I see RetryableQuotaError in the docs as a retry signal.\n"
        "2026-09-07T23:20:01.0Z The input file could not be read. Stopping.\n"
        "2026-09-07T23:20:02.0Z ##[error]Process completed with exit code 1.\n"
    )
    assert _classify_rc(echoed) == 1
