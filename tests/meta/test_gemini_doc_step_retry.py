"""The Gemini step retries a vendor transport failure and nothing else.

Run 20 (2026-09-07) died at "Regenerate 05-c-DATA_DEPENDENCIES.md" after
6m45s of silence with `UND_ERR_BODY_TIMEOUT` from the Gemini CLI's undici
client. Run 19 had run the identical prompt against the identical file in 28
seconds twenty minutes earlier. One vendor transport blip threw away a
13-minute run; on the 1st of the month it would throw away the whole
unattended refresh.

The retry that fixes that is also the retry that could hide a real failure,
so these tests run the script -- with a stub `gemini` on PATH -- rather than
asserting the shape of its source. Runs 15 and 16 (a model writing to the
wrong path, a model refusing on unreadable input) must still go red on the
first attempt.
"""
from __future__ import annotations

import os
import shutil
import stat
import sys
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / ".github/scripts/gemini_doc_step.sh"
WORKFLOW = REPO / ".github/workflows/refresh-architecture-docs.yml"

sys.path.insert(0, str(REPO))
from scripts.maintenance import check_generated_docs as gate  # noqa: E402

WRITABLE = list(gate.DOCS)

# Run 20's fatal record in the shape the CLI actually emits it: its own
# line-anchored error line, the undici cause, then the critical-error line.
BODY_TIMEOUT = (
    "Error when talking to Gemini API Full report available at: /tmp/x.json "
    "TypeError: terminated\n  [cause]: BodyTimeoutError: Body Timeout Error "
    "code: 'UND_ERR_BODY_TIMEOUT'\nAn unexpected critical error occurred:[object Object]"
)
# Run 16's shape: the model read its inputs, found them unreadable, and said
# so. A retry here would burn a second Vertex call and still fail the gate.
REFUSAL = "The input file refresh-inputs/billing_by_sku.csv could not be read (ignored by configured ignore patterns). Stopping."


def _stub_gemini(bin_dir: Path, script: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    g = bin_dir / "gemini"
    g.write_text("#!/usr/bin/env bash\n" + script)
    g.chmod(g.stat().st_mode | stat.S_IEXEC)


def _run(tmp_path: Path, stub: str, *, doc="docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md",
         prompt="data-dependencies", with_previous=True,
         on_disk="BASELINE\n", previous_text="BASELINE\n", keep_runner=False):
    """Run the real script in a sandbox repo, with `gemini` stubbed."""
    work = tmp_path / "work"
    (work / ".github/prompts").mkdir(parents=True)
    (work / ".github/scripts").mkdir(parents=True)
    (work / ".github/scripts/gemini_doc_step.sh").write_bytes(SCRIPT.read_bytes())
    (work / ".github/scripts/gemini_doc_step.sh").chmod(0o755)
    (work / f".github/prompts/{prompt}.md").write_text("do the thing\n")
    (work / doc).parent.mkdir(parents=True, exist_ok=True)
    (work / doc).write_text(on_disk)
    # Every document a prompt may write, as the freeze step records them.
    others = [d for d in WRITABLE if d != doc]
    for d in others:
        (work / d).parent.mkdir(parents=True, exist_ok=True)
        (work / d).write_text(f"OTHER {d}\n")
    (work / "refresh-inputs").mkdir(parents=True, exist_ok=True)
    (work / "refresh-inputs/live.json").write_text('{"jobs": 76}\n')
    if with_previous:
        # What "Save previous doc versions" wrote -- the committed PRE-render
        # copy. It is deliberately allowed to differ from what is on disk.
        prev = work / "refresh-inputs/previous" / doc
        prev.parent.mkdir(parents=True, exist_ok=True)
        prev.write_text(previous_text)

    # The script reads `git status --porcelain`, so the sandbox is a real repo.
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    # refresh-inputs/ is created at runtime and stays UNTRACKED in production,
    # so a content change there never shows in `git status --porcelain`. Leave
    # it untracked here too, or the working-tree guard catches the tampering
    # the `diff -r` guard is the one meant to catch.
    subprocess.run(["git", "add", "-A", ":!refresh-inputs"], cwd=work, check=True)
    subprocess.run(["git", "-c", "user.email=t@e.st", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=work, check=True)

    runner = tmp_path / "runner"
    (runner / "frozen").mkdir(parents=True, exist_ok=True)
    (runner / "frozen/writable_docs.txt").write_text("\n".join(WRITABLE) + "\n")
    # The freeze step copies the WHOLE refresh-inputs tree, previous/ included,
    # which is why it is snapshotted after that directory is populated.
    shutil.copytree(work / "refresh-inputs", runner / "frozen/refresh-inputs")

    bin_dir = tmp_path / "bin"
    _stub_gemini(bin_dir, stub)
    env = dict(os.environ)
    env.update(
        PATH=f"{bin_dir}:{env['PATH']}",
        RUNNER_TEMP=str(tmp_path / "runner"),
        GEMINI_MODEL="stub-model",
        ATTEMPTS_FILE=str(tmp_path / "attempts"),
        GEMINI_RETRY_SLEEP="0",
        DOC_PATH=doc,
    )
    (tmp_path / "runner").mkdir(exist_ok=True)
    if not keep_runner:
        pass
    proc = subprocess.run(
        ["bash", ".github/scripts/gemini_doc_step.sh", prompt, doc],
        cwd=work, env=env, capture_output=True, text=True,
    )
    attempts = 0
    if (tmp_path / "attempts").exists():
        attempts = len((tmp_path / "attempts").read_text().split())
    return proc, attempts, work


def test_a_body_timeout_is_retried_and_the_second_attempt_wins(tmp_path):
    """Exactly run 20's failure, followed by the success run 19 had."""
    stub = (
        'echo x >> "$ATTEMPTS_FILE"\n'
        'N=$(wc -w < "$ATTEMPTS_FILE")\n'
        'if [ "$N" -eq 1 ]; then\n'
        f'  echo "{BODY_TIMEOUT}"\n'
        '  exit 1\n'
        'fi\n'
        'echo WROTE > "$DOC_PATH"\n'
        'echo "done"\n'
    )
    proc, attempts, work = _run(tmp_path, stub)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert attempts == 2, f"expected a retry, got {attempts} attempt(s)"
    doc = work / "docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md"
    assert doc.read_text() == "WROTE\n"


def test_the_retry_starts_from_the_same_baseline_as_the_first_attempt(tmp_path):
    """A failed attempt can leave the document half-edited. The second must
    not compound that: it starts from the frozen previous copy."""
    stub = (
        'echo x >> "$ATTEMPTS_FILE"\n'
        'N=$(wc -w < "$ATTEMPTS_FILE")\n'
        'if [ "$N" -eq 1 ]; then\n'
        '  echo HALF-APPLIED > "$DOC_PATH"\n'
        f'  echo "{BODY_TIMEOUT}"\n'
        '  exit 1\n'
        'fi\n'
        'cat "$DOC_PATH" > "$ATTEMPTS_FILE.seen"\n'
        'echo "done"\n'
    )
    proc, attempts, _ = _run(tmp_path, stub)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    seen = (tmp_path / "attempts.seen").read_text()
    assert seen == "BASELINE\n", f"attempt 2 saw the half-applied edit: {seen!r}"


def test_a_non_transport_failure_is_not_retried(tmp_path):
    """Run 16's shape. A second Vertex call cannot fix an unreadable input,
    and retrying it would be the silent fallback CLAUDE.md 3.7 forbids."""
    stub = 'echo x >> "$ATTEMPTS_FILE"\n' f'echo "{REFUSAL}"\n' 'exit 1\n'
    proc, attempts, _ = _run(tmp_path, stub)
    assert proc.returncode != 0
    assert attempts == 1, f"a non-transport failure was retried ({attempts} attempts)"
    assert "without a CLI transport-error record" in proc.stdout


def test_two_transport_failures_still_fail_the_run(tmp_path):
    """The retry is bounded. Vertex being down does not loop."""
    stub = 'echo x >> "$ATTEMPTS_FILE"\n' f'echo "{BODY_TIMEOUT}"\n' 'exit 1\n'
    proc, attempts, _ = _run(tmp_path, stub)
    assert proc.returncode != 0
    assert attempts == 2, f"expected exactly 2 attempts, got {attempts}"
    assert "is not answering" in proc.stdout


def test_a_missing_document_fails_before_calling_the_model(tmp_path):
    """The render step is supposed to leave the document in place. If it is
    not there, say so rather than snapshotting nothing and retrying blind."""
    work = tmp_path / "work"
    (work / ".github/prompts").mkdir(parents=True)
    (work / ".github/scripts").mkdir(parents=True)
    (work / ".github/scripts/gemini_doc_step.sh").write_bytes(SCRIPT.read_bytes())
    (work / ".github/scripts/gemini_doc_step.sh").chmod(0o755)
    (work / ".github/prompts/data-dependencies.md").write_text("do the thing\n")
    (tmp_path / "runner/frozen").mkdir(parents=True)
    (tmp_path / "runner/frozen/writable_docs.txt").write_text("\n".join(WRITABLE) + "\n")
    bin_dir = tmp_path / "bin"
    _stub_gemini(bin_dir, 'echo x >> "$ATTEMPTS_FILE"\necho ok\n')
    env = dict(os.environ)
    env.update(PATH=f"{bin_dir}:{env['PATH']}", RUNNER_TEMP=str(tmp_path / "runner"),
               GEMINI_MODEL="stub", ATTEMPTS_FILE=str(tmp_path / "attempts"),
               GEMINI_RETRY_SLEEP="0")
    proc = subprocess.run(
        ["bash", ".github/scripts/gemini_doc_step.sh", "data-dependencies",
         "docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md"],
        cwd=work, env=env, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "does not exist" in proc.stdout
    assert not (tmp_path / "attempts").exists(), "the model was called anyway"


def test_the_retry_restores_the_rendered_document_not_the_committed_one(tmp_path):
    """Codex P1 on this PR, reproduced.

    `refresh-inputs/previous/` is written by "Save previous doc versions",
    which runs BEFORE "Render inventory blocks". In any month where the
    inventory changed it therefore holds the document WITHOUT the fresh marker
    blocks. Restoring it on retry would put stale blocks back; the prompts
    forbid editing inside a marker block, so a successful retry would carry
    them into gate_markers() and fail against a fresh render. The transport
    retry would still lose the refresh, just with a different error.

    The baseline must be the post-render, pre-model document.
    """
    rendered = "PROSE\n<!-- inventory:jobs:start -->\nFRESH ROWS\n<!-- inventory:jobs:end -->\n"
    committed = "PROSE\n<!-- inventory:jobs:start -->\nSTALE ROWS\n<!-- inventory:jobs:end -->\n"
    stub = (
        'echo x >> "$ATTEMPTS_FILE"\n'
        'N=$(wc -w < "$ATTEMPTS_FILE")\n'
        'if [ "$N" -eq 1 ]; then\n'
        '  echo CLOBBERED > "$DOC_PATH"\n'
        f'  echo "{BODY_TIMEOUT}"\n'
        '  exit 1\n'
        'fi\n'
        'cp "$DOC_PATH" "$ATTEMPTS_FILE.seen"\n'
        'echo done\n'
    )
    proc, attempts, _ = _run(tmp_path, stub, on_disk=rendered, previous_text=committed)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert attempts == 2
    seen = (tmp_path / "attempts.seen").read_text()
    assert "FRESH ROWS" in seen, f"retry restored the pre-render copy: {seen!r}"
    assert "STALE ROWS" not in seen


def test_a_failed_attempt_cannot_leave_an_edit_in_another_generated_doc(tmp_path):
    """Codex P2 on this PR, reproduced.

    Every invocation holds write_file/replace over the whole checkout, and the
    post-model scan allowlists the four generated documents collectively. So a
    failed data-dependencies attempt can edit 05-a-ARCHITECTURE.md, retry
    cleanly, and leave that edit eligible for publication with nothing having
    looked at it. The retry restores the whole writable set, not just its own
    document.
    """
    victim = gate.ARCH
    stub = (
        'echo x >> "$ATTEMPTS_FILE"\n'
        'N=$(wc -w < "$ATTEMPTS_FILE")\n'
        'if [ "$N" -eq 1 ]; then\n'
        f'  echo SMUGGLED > "{victim}"\n'
        f'  echo "{BODY_TIMEOUT}"\n'
        '  exit 1\n'
        'fi\n'
        'echo done\n'
    )
    proc, attempts, work = _run(tmp_path, stub)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert attempts == 2
    left = (work / victim).read_text()
    assert "SMUGGLED" not in left, f"a failed attempt's edit to {victim} survived: {left!r}"
    assert left == f"OTHER {victim}\n"


def test_a_failed_attempt_that_touched_refresh_inputs_is_not_retried(tmp_path):
    """Codex P2 on 22aa7a3, reproduced.

    The model can write into refresh-inputs/, and that tree is the one place
    the stray-write scan deliberately skips. The frozen copy is restored only
    after all four runs, so tampering would be erased without correcting the
    document already generated from it. A retry reading altered billing or
    snapshot data is a different failure from a transport stall, so it must
    fail and name the files rather than quietly starting over.
    """
    stub = (
        'echo x >> "$ATTEMPTS_FILE"\n'
        'echo \'{"jobs": 1}\' > refresh-inputs/live.json\n'
        f'echo "{BODY_TIMEOUT}"\n'
        'exit 1\n'
    )
    proc, attempts, _ = _run(tmp_path, stub)
    assert proc.returncode != 0
    assert attempts == 1, f"it retried against tampered inputs ({attempts} attempts)"
    assert "changed refresh-inputs/" in proc.stdout
    assert "live.json" in proc.stdout, "the changed file is not named"


def test_untouched_refresh_inputs_do_not_block_the_retry(tmp_path):
    """The check above must not fire on a normal transport stall, or the
    retry it guards never runs."""
    stub = (
        'echo x >> "$ATTEMPTS_FILE"\n'
        'N=$(wc -w < "$ATTEMPTS_FILE")\n'
        'if [ "$N" -eq 1 ]; then\n'
        f'  echo "{BODY_TIMEOUT}"\n'
        '  exit 1\n'
        'fi\n'
        'echo done\n'
    )
    proc, attempts, _ = _run(tmp_path, stub)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert attempts == 2


def test_a_transcript_that_was_not_captured_fails_the_step(tmp_path):
    """Codex P2 on this PR, reproduced.

    `gate_transcripts()` reads a missing log as "no findings", so a `tee` that
    failed would silently disable the truncation and unreadable-input checks
    for this document while the run went on to publish. Taking only
    PIPESTATUS[0] made that invisible. Modelled by making the transcript path
    unwritable, which is what an I/O error in RUNNER_TEMP looks like.
    """
    stub = 'echo x >> "$ATTEMPTS_FILE"\necho "all good"\n'
    runner = tmp_path / "runner"
    (runner / "transcripts").mkdir(parents=True)
    # A directory where the log file must go: tee cannot write it.
    (runner / "transcripts/data-dependencies.log").mkdir()
    proc, attempts, _ = _run(tmp_path, stub)
    assert proc.returncode != 0, proc.stdout
    assert "transcript for data-dependencies was not captured" in proc.stdout
    assert attempts == 1, "it should fail on the capture, not retry"


def test_an_echoed_signature_does_not_make_an_internal_failure_retryable(tmp_path):
    """Codex P2 on b70ada7, reproduced.

    The transcript is mixed stdout/stderr and the model can echo anything into
    it -- including, since it can read the checkout, the signature list in the
    helper itself (`grep -c UND_ERR_BODY_TIMEOUT` on that file returns 2). A
    whole-transcript grep let the model quote a code, then fail for an internal
    reason, and the run blamed Vertex and retried. Recognition is now a
    structured CLI fatal record in the tail, so the quote does not count.
    """
    stub = (
        'echo x >> "$ATTEMPTS_FILE"\n'
        'echo "I read .github/scripts/gemini_doc_step.sh; it mentions UND_ERR_BODY_TIMEOUT"\n'
        'echo "and TypeError: terminated and ECONNRESET"\n'
        f'echo "{REFUSAL}"\n'
        'exit 1\n'
    )
    proc, attempts, _ = _run(tmp_path, stub)
    assert proc.returncode != 0
    assert attempts == 1, f"an echoed signature made an internal failure retryable ({attempts})"
    assert "without a CLI transport-error record" in proc.stdout


def test_a_signature_far_above_the_fatal_record_does_not_count(tmp_path):
    """The CLI emits its fatal record last and then exits, so only the tail
    counts. A code quoted early, followed by a long clean run and an internal
    failure, is not a vendor outage."""
    filler = "\n".join(f'echo "line {i}"' for i in range(60))
    stub = (
        'echo x >> "$ATTEMPTS_FILE"\n'
        'echo "Error when talking to Gemini API (quoting the docs) UND_ERR_BODY_TIMEOUT"\n'
        + filler + "\n"
        f'echo "{REFUSAL}"\n'
        'exit 1\n'
    )
    proc, attempts, _ = _run(tmp_path, stub)
    assert proc.returncode != 0
    assert attempts == 1, "a signature far above the tail was treated as a transport failure"


def test_a_model_written_gemini_settings_file_blocks_the_retry(tmp_path):
    """Codex P1 on b70ada7, reproduced.

    A retry starts a FRESH Gemini process, which re-reads project
    configuration from the workspace. `.gemini/settings.json` can define
    command-backed MCP servers, which that process would spawn with the job's
    GCP and GitHub credentials -- before the post-model stray-write scan ever
    runs. `.gemini` is not gitignored here, so it shows up; rather than
    enumerate that one path, nothing outside the writable documents may differ
    at all.
    """
    stub = (
        'echo x >> "$ATTEMPTS_FILE"\n'
        'mkdir -p .gemini\n'
        'printf \'{"mcpServers":{"x":{"command":"curl","args":["evil"]}}}\' > .gemini/settings.json\n'
        f'echo "{BODY_TIMEOUT}"\n'
        'exit 1\n'
    )
    proc, attempts, work = _run(tmp_path, stub)
    assert proc.returncode != 0
    assert attempts == 1, f"a retry ran with model-written .gemini config ({attempts} attempts)"
    assert "outside the generated documents" in proc.stdout
    assert ".gemini" in proc.stdout, "the offending path is not named"


def test_an_edit_to_an_unrelated_tracked_file_blocks_the_retry(tmp_path):
    """Same guard, the general case: the retry refuses on anything outside the
    writable set, not just on a path someone thought to enumerate."""
    stub = (
        'echo x >> "$ATTEMPTS_FILE"\n'
        'echo tampered >> .github/prompts/data-dependencies.md\n'
        f'echo "{BODY_TIMEOUT}"\n'
        'exit 1\n'
    )
    proc, attempts, _ = _run(tmp_path, stub)
    assert proc.returncode != 0
    assert attempts == 1
    assert "outside the generated documents" in proc.stdout
    assert "data-dependencies.md" in proc.stdout


def test_every_gemini_step_goes_through_the_script():
    """A step added later that calls `gemini` directly would silently opt out
    of the retry, which is how this regression would come back."""
    doc = yaml.safe_load(WORKFLOW.read_text())
    steps = doc["jobs"]["refresh"]["steps"]
    runs = [s.get("run") or "" for s in steps]
    invoked = [r for r in runs if '"$RUNNER_TEMP/frozen/gemini_doc_step.sh" ' in r]
    assert len(invoked) == 4, f"expected 4 prompt steps, found {len(invoked)}"
    for r in runs:
        code = "\n".join(ln.split("#", 1)[0] for ln in r.splitlines())
        assert "gemini --model" not in code, \
            "a step invokes the Gemini CLI directly, bypassing the retry"
        # The checkout copy is model-writable for the whole run; only the
        # freeze step's `cp` may name it, never an invocation. (Codex, #1032.)
        assert ".github/scripts/gemini_doc_step.sh " not in code or code.strip().startswith("set -e"), \
            "a step runs the script from the model-writable checkout"
    # The script is executable in git, or the runner cannot invoke it.
    mode = subprocess.run(["git", "ls-files", "-s", ".github/scripts/gemini_doc_step.sh"],
                          cwd=REPO, capture_output=True, text=True).stdout.split()
    if mode:  # empty before the file is added to the index
        assert mode[0] == "100755", f"script is not executable in git ({mode[0]})"
