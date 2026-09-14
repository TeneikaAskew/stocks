"""Unit tests for gcp.insight_tasks, the shared Cloud Tasks enqueue.

The load-bearing test here is the run_kind parity suite. A Cloud Run
container override REPLACES the child's env, so a fanned-out ticker
resolves `(allow_update, run_kind)` from whatever `build_child_env`
chose to forward and nothing else. If that disagrees with what the
parent would have resolved running the ticker in-process, every daily
report silently lands in insight_reports_history under the wrong
run_kind and nothing fails.

These tests never construct a Cloud Tasks client.
"""

from __future__ import annotations

import pytest

from gcp import insight_tasks
from gcp.insight_pipeline_job import (
    _resolve_run_kind_and_update,
    _update_explicitly_requested,
)


def _as_dict(env: list[dict[str, str]]) -> dict[str, str]:
    return {e["name"]: e["value"] for e in env}


# ---------------------------------------------------------------------------
# build_child_env
# ---------------------------------------------------------------------------


def test_child_env_always_carries_run_id_and_ticker():
    env = _as_dict(insight_tasks.build_child_env("run-1", "SPY"))
    assert env["INSIGHT_RUN_ID"] == "run-1"
    assert env["INSIGHT_TICKER"] == "SPY"


def test_child_env_omits_optional_keys_when_unset():
    env = _as_dict(insight_tasks.build_child_env("run-1", "SPY"))
    assert "INSIGHT_AS_OF" not in env
    assert "INSIGHT_TRIGGERED_BY" not in env
    assert "INSIGHT_UPDATE" not in env


def test_child_env_forwards_as_of():
    env = _as_dict(
        insight_tasks.build_child_env("r", "SPY", as_of_iso="2026-09-04")
    )
    assert env["INSIGHT_AS_OF"] == "2026-09-04"


def test_child_env_forwards_triggered_by():
    """The daily scheduler passes INSIGHT_TRIGGERED_BY as an override, so
    it is NOT in the job definition. Dropping it here is what silently
    reclassifies a scheduled run as manual_replay."""
    env = _as_dict(
        insight_tasks.build_child_env(
            "r", "SPY", triggered_by="cloud-scheduler:insight-pipeline-daily"
        )
    )
    assert env["INSIGHT_TRIGGERED_BY"] == "cloud-scheduler:insight-pipeline-daily"


def test_child_env_sets_update_only_when_requested():
    assert "INSIGHT_UPDATE" not in _as_dict(
        insight_tasks.build_child_env("r", "SPY", force_update=False)
    )
    assert _as_dict(
        insight_tasks.build_child_env("r", "SPY", force_update=True)
    )["INSIGHT_UPDATE"] == "true"


# ---------------------------------------------------------------------------
# run_kind parity: child resolution == parent resolution
# ---------------------------------------------------------------------------


def _resolve_as_child(env: dict[str, str], monkeypatch) -> tuple[bool, str]:
    """Resolve run_kind the way a child execution would: ONLY the
    forwarded override env exists."""
    for key in ("INSIGHT_UPDATE", "INSIGHT_AS_OF", "INSIGHT_TRIGGERED_BY"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # arg_update is False: the child is launched by Cloud Tasks, which
    # cannot pass the --update CLI flag. Everything must ride in env.
    return _resolve_run_kind_and_update(False)


@pytest.mark.parametrize(
    "arg_update,env_as_of,env_triggered_by",
    [
        (False, None, "cloud-scheduler:insight-pipeline-daily"),  # daily cron
        (True, None, "cloud-scheduler:insight-pipeline-daily"),   # --update
        (False, "2026-09-04", None),                              # replay
        (True, "2026-09-04", None),                               # --update replay
        (False, None, None),                                      # manual
        (True, None, None),                                       # manual --update
    ],
)
def test_fanned_out_child_resolves_same_run_kind_as_parent(
    arg_update, env_as_of, env_triggered_by, monkeypatch
):
    # 1. What the parent resolves, running the ticker in-process.
    for key in ("INSIGHT_UPDATE", "INSIGHT_AS_OF", "INSIGHT_TRIGGERED_BY"):
        monkeypatch.delenv(key, raising=False)
    if env_as_of:
        monkeypatch.setenv("INSIGHT_AS_OF", env_as_of)
    if env_triggered_by:
        monkeypatch.setenv("INSIGHT_TRIGGERED_BY", env_triggered_by)
    parent_allow_update, parent_run_kind = _resolve_run_kind_and_update(arg_update)

    # 2. What the child resolves from the forwarded override env alone.
    child_env = _as_dict(
        insight_tasks.build_child_env(
            "run-1",
            "SPY",
            as_of_iso=env_as_of,
            triggered_by=env_triggered_by,
            # The dispatcher forwards the CAUSE (was update asked for?),
            # not the resolved effect. Passing parent_allow_update here
            # instead relabels every replay as manual_update.
            force_update=_update_explicitly_requested(arg_update),
        )
    )
    child_allow_update, child_run_kind = _resolve_as_child(child_env, monkeypatch)

    assert (child_allow_update, child_run_kind) == (
        parent_allow_update,
        parent_run_kind,
    )


def test_child_keeps_as_of_cutoff_not_just_run_kind():
    """A replay child must carry the cutoff itself, not merely resolve to
    replay_refresh — without INSIGHT_AS_OF it would read live data."""
    env = _as_dict(
        insight_tasks.build_child_env(
            "r", "SPY", as_of_iso="2026-09-04", force_update=False
        )
    )
    assert env["INSIGHT_AS_OF"] == "2026-09-04"


# ---------------------------------------------------------------------------
# Ambiguous enqueue (Codex, PR #1094)
# ---------------------------------------------------------------------------
#
# create_task can reach Cloud Tasks and have the task accepted, then fail on
# the way back (timeout, reset). Treating that as a failure makes the caller
# run the same run_id in-process while the accepted child also runs it: two
# paid pipelines, duplicate history rows, racing status writes. A
# deterministic task name turns the retry into a question with an
# authoritative answer.


class _FakeAlreadyExists(Exception):
    pass


def _fake_tasks_modules(monkeypatch, create_side_effects):
    """Install fake google.cloud.tasks_v2 + google.api_core.exceptions whose
    create_task walks `create_side_effects` (an exception to raise, or None
    to succeed). Records every task dict it is handed."""
    import sys
    import types

    seen: list = []

    class _Client:
        def queue_path(self, p, r, q):
            return f"projects/{p}/locations/{r}/queues/{q}"

        def create_task(self, parent=None, task=None):
            seen.append(task)
            effect = create_side_effects.pop(0)
            if effect is not None:
                raise effect
            return task

    tasks = types.ModuleType("google.cloud.tasks_v2")
    tasks.CloudTasksClient = _Client
    tasks.HttpMethod = types.SimpleNamespace(POST=1)

    gexc = types.ModuleType("google.api_core.exceptions")
    gexc.AlreadyExists = _FakeAlreadyExists

    monkeypatch.setitem(sys.modules, "google.cloud.tasks_v2", tasks)
    monkeypatch.setitem(sys.modules, "google.api_core.exceptions", gexc)
    for mod, attr, val in (
        ("google.cloud", "tasks_v2", tasks),
        ("google.api_core", "exceptions", gexc),
    ):
        if mod in sys.modules:
            monkeypatch.setattr(sys.modules[mod], attr, val, raising=False)
    return seen


def test_the_task_carries_a_deterministic_name(monkeypatch):
    seen = _fake_tasks_modules(monkeypatch, [None])
    assert insight_tasks.enqueue_insight_task("run-abc", "SPY") is True
    assert seen[0]["name"].endswith("/tasks/insight-run-abc")


def test_an_accepted_task_that_errored_on_the_way_back_is_not_rerun(monkeypatch):
    """First create raises (ambiguous); the re-check says AlreadyExists, so
    the task DID land and the caller must not also run it in-process."""
    seen = _fake_tasks_modules(
        monkeypatch, [RuntimeError("504 deadline exceeded"), _FakeAlreadyExists()]
    )
    assert insight_tasks.enqueue_insight_task("run-abc", "SPY") is True
    assert len(seen) == 2, "the ambiguous failure must be re-checked, not guessed"


def test_a_genuinely_failed_enqueue_still_reports_false(monkeypatch):
    """Both attempts fail for a non-AlreadyExists reason: the task really is
    not queued, so the caller should fall back and run it."""
    _fake_tasks_modules(
        monkeypatch, [RuntimeError("permission denied"), RuntimeError("permission denied")]
    )
    assert insight_tasks.enqueue_insight_task("run-abc", "SPY") is False


def test_an_already_enqueued_run_is_not_reported_as_failed(monkeypatch):
    _fake_tasks_modules(monkeypatch, [_FakeAlreadyExists()])
    assert insight_tasks.enqueue_insight_task("run-abc", "SPY") is True
