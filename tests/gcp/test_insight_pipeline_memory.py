"""The insight-pipeline job's memory limit must reach the LIVE job.

Added 2026-09-15, after the first auto-refresh fan-out that ever actually
dispatched OOM-killed two of its three children.

`deploy_insight_pipeline` is a `create ... || update ...` pair. The job has
existed since 2026-08, so `create` always fails and `update` is the branch
that runs on every deploy — and `update` carried no `--memory` flag at all.
Raising the limit on the `create` line alone would have read as a fix, been
reviewed as a fix, and silently no-op'd against production forever, because
nothing re-creates that job.

So these tests pin the property that actually matters — the flag is on the
path that executes — rather than "the file contains 4Gi somewhere".

The OOM itself: NVDA and AMD both pinned
`run.googleapis.com/container/memory/utilizations` at bucket 100 (>=100% of
2Gi) for three consecutive minutes and were killed with signal 9, while AVGO
completed in the same run. The daily SPY/IWM/QQQ batch has never OOM'd;
auto-refresh reaches heavier option chains by ranking a ~16-ticker pool.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DEPLOY_SH = (REPO / "gcp/deploy.sh").read_text()


def _function_body(name: str) -> str:
    """Return the body of a shell function, comments stripped."""
    match = re.search(rf"^{name}\(\) \{{\n(.*?)^\}}", DEPLOY_SH, re.S | re.M)
    assert match, f"{name}() not found in deploy.sh"
    return "\n".join(
        line for line in match.group(1).splitlines()
        if not line.lstrip().startswith("#")
    )


def _gcloud_invocation(body: str, verb: str, job: str) -> str:
    """Return ONE `gcloud run jobs <verb> <job> ...` call.

    `create ... --quiet 2>/dev/null || gcloud run jobs update ...` is a single
    continued shell chain, so naively joining continuations puts both calls on
    one line. An earlier version of this helper did exactly that and happily
    read the `create` block's --memory when asked for `update`'s — passing
    against the very bug it was written to catch. So slice at the next
    `gcloud ` after the match, and assert the slice does not contain the other
    verb.
    """
    joined = body.replace("\\\n", " ")
    needle = f"gcloud run jobs {verb} {job}"
    start = joined.find(needle)
    assert start != -1, f"no `{needle}` call found"
    nxt = joined.find("gcloud ", start + len(needle))
    slice_ = joined[start:nxt if nxt != -1 else len(joined)]
    other = "update" if verb == "create" else "create"
    assert f"gcloud run jobs {other} {job}" not in slice_, (
        f"the {verb} slice still contains the {other} call; the helper is "
        f"reading both branches as one and cannot tell them apart"
    )
    return slice_


def _memory_of(invocation: str) -> str | None:
    match = re.search(r"--memory\s+(\S+)", invocation)
    return match.group(1) if match else None


def test_the_update_path_sets_memory_at_all():
    """The branch that actually runs must carry --memory.

    Red before the fix: `update` had no --memory, so the live job kept the
    2Gi it was created with no matter what the create line said.
    """
    body = _function_body("deploy_insight_pipeline")
    update = _gcloud_invocation(body, "update", "insight-pipeline")
    assert _memory_of(update) is not None, (
        "`gcloud run jobs update insight-pipeline` passes no --memory. The job "
        "already exists, so this is the branch that runs on every deploy; "
        "without the flag the live memory limit can never change."
    )


def test_create_and_update_agree_on_memory():
    """Both paths must request the same limit.

    Otherwise a rebuild from scratch and an in-place deploy produce jobs with
    different memory, and which one you get depends on whether the job
    happened to exist — the drift is invisible until something OOMs.
    """
    body = _function_body("deploy_insight_pipeline")
    create = _memory_of(_gcloud_invocation(body, "create", "insight-pipeline"))
    update = _memory_of(_gcloud_invocation(body, "update", "insight-pipeline"))
    assert create == update, (
        f"create requests {create} but update requests {update}; a fresh "
        f"environment and an existing one would not get the same job."
    )


def test_memory_is_above_the_limit_that_oomed():
    """2Gi is disproven, so the floor is anything strictly above it.

    Deliberately not asserting exactly 4Gi: the utilization metric is
    censored at the limit, so 2Gi is the only value this incident actually
    ruled out. Raising further on new evidence should not fail a test.
    """
    body = _function_body("deploy_insight_pipeline")
    value = _memory_of(_gcloud_invocation(body, "update", "insight-pipeline"))
    match = re.fullmatch(r"(\d+)(Mi|Gi)", value or "")
    assert match, f"unparseable --memory value {value!r}"
    mib = int(match.group(1)) * (1024 if match.group(2) == "Gi" else 1)
    assert mib > 2048, (
        f"--memory {value} is {mib} MiB; 2048 MiB is the limit that was "
        f"OOM-killed on 2026-09-15, so it cannot be the fix."
    )
