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

import re
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github/workflows/rerun-transient-doc-refresh.yml"
REFRESH = REPO / ".github/workflows/refresh-architecture-docs.yml"
DOC = yaml.safe_load(WORKFLOW.read_text())
STEP = DOC["jobs"]["rerun"]["steps"][0]["run"]
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


def _classify(log_text: str) -> bool:
    """Run the workflow's own classifier over a log, returning whether it would
    re-run.

    The block is sliced out of the step VERBATIM -- from `TAIL=$(` through the
    `; then` -- and executed. An earlier version of this helper rebuilt the
    condition from the extracted RECORD and TRANSPORT variables, and so tested
    a combination the workflow did not necessarily use: it reported the real
    run-20 log as not-a-transport-failure while the shipped workflow would have
    recognised it. A test that reconstructs the logic it is checking is not
    checking that logic.
    """
    start = STEP.index("TAIL=$(")
    end = STEP.index("; then", start) + len("; then")
    block = STEP[start:end]
    script = (
        "set -euo pipefail\n"
        "cat > failed.log\n"
        + block + "\n"
        "  echo RERUN\n"
        "else\n"
        "  echo LEAVE_RED\n"
        "fi\n"
    )
    out = subprocess.run(["bash", "-c", script], input=log_text,
                         capture_output=True, text=True, check=True)
    return out.stdout.strip() == "RERUN"


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


def test_it_can_rerun_and_asks_for_nothing_more():
    perms = DOC["permissions"]
    assert perms["actions"] == "write", "cannot re-run without actions: write"
    assert perms["contents"] == "read"
    assert set(perms) == {"actions", "contents"}, f"extra permissions: {perms}"
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
