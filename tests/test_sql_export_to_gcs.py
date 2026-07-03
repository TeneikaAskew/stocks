"""Regression tests for gcp/sql_export_to_gcs.py's poll-timeout sizing.

Background — 2026-06-28: cloud-sql-weekly-export-bcmlz and -cwh72 both
timed out after exactly 3600s (issue #657). POLL_MAX_SECS (the script's
own poll-loop cap) and the Cloud Run --task-timeout in
gcp/deploy.sh:deploy_weekly_pg_dump() were BOTH 3600s — a week earlier
(2026-06-21, execution v5cr5) the same export completed in ~46 min, so
the DB has grown past a cap with essentially zero headroom (CLAUDE.md
Rule 0: task-timeout must be >=4x the wall-clock estimate).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# gcp/sql_export_to_gcs.py imports google.auth at module level purely for
# its own SA-credential plumbing (_get_token, monkeypatched out below in
# every test that needs it). Stub it the same way test_magnitude_inference
# does for its own unavailable-in-CI deps: catch broad Exception, not just
# ImportError, since in this sandbox `google.auth.transport.requests` fails
# on a broken native `cryptography` extension rather than a clean
# ModuleNotFoundError.
_STUBBED_BY_THIS_MODULE: list[str] = []
for _mod in ("google.auth", "google.auth.transport", "google.auth.transport.requests"):
    if _mod in sys.modules:
        continue
    try:
        __import__(_mod)
    except BaseException:
        # BaseException, not Exception: the broken native `cryptography`
        # extension in this sandbox raises pyo3_runtime.PanicException,
        # which does not reliably subclass Exception.
        parts = _mod.split(".")
        for i in range(1, len(parts) + 1):
            key = ".".join(parts[:i])
            if key not in sys.modules:
                sys.modules[key] = MagicMock()
                _STUBBED_BY_THIS_MODULE.append(key)


@pytest.fixture(scope="module", autouse=True)
def _restore_stubbed_modules():
    yield
    for key in _STUBBED_BY_THIS_MODULE:
        if isinstance(sys.modules.get(key), MagicMock):
            sys.modules.pop(key, None)
    _STUBBED_BY_THIS_MODULE.clear()


_REPO = Path(__file__).resolve().parents[1]
_DEPLOY_SH = _REPO / "gcp" / "deploy.sh"


def _deploy_weekly_pg_dump_task_timeout() -> int:
    text = _DEPLOY_SH.read_text()
    start = text.index("deploy_weekly_pg_dump()")
    end = text.index("\n}\n", start)
    body = text[start:end]
    match = re.search(r"--task-timeout\s+(\d+)", body)
    assert match, "no --task-timeout found in deploy_weekly_pg_dump()"
    return int(match.group(1))


def test_poll_max_secs_has_real_headroom_over_last_observed_failure():
    """The 2026-06-28 timeouts hit at exactly 3600s, one week after a
    ~2760s (46 min) successful run. The new cap must clear that failure
    point with real margin (>=4x the old 3600s cap), not just nudge past
    it — a DB that keeps growing weekly needs headroom, not a new ceiling
    that times out again in a month."""
    from gcp import sql_export_to_gcs as mod

    assert mod.POLL_MAX_SECS >= 4 * 3600


def test_task_timeout_exceeds_script_poll_cap_with_margin():
    """The Cloud Run task-timeout must be a backstop STRICTLY AFTER the
    script's own poll timeout. Pre-fix, both were exactly 3600s, so
    whichever fired first did so with no useful distinction — a stuck
    export either raised the script's TimeoutError or got silently
    SIGKILLed by Cloud Run at the same instant. Now the script's own
    TimeoutError (with a clear message) must always fire first."""
    from gcp import sql_export_to_gcs as mod

    task_timeout = _deploy_weekly_pg_dump_task_timeout()
    assert task_timeout > mod.POLL_MAX_SECS, (
        f"Cloud Run task-timeout ({task_timeout}s) must exceed "
        f"POLL_MAX_SECS ({mod.POLL_MAX_SECS}s)"
    )


def test_wait_for_op_raises_timeout_after_poll_max_secs(monkeypatch):
    """wait_for_op must still raise TimeoutError (not hang forever, not
    silently return) once POLL_MAX_SECS elapses for a stuck export —
    the failure-detection contract this whole module exists to provide
    for failure_notifier. Uses a fake monotonic clock so the test doesn't
    actually sleep for hours."""
    from gcp import sql_export_to_gcs as mod

    monkeypatch.setattr(mod, "POLL_MAX_SECS", 30)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)

    # 1 call for `started`, then 4 loop-top elapsed-time checks; the last
    # exceeds POLL_MAX_SECS (30) so the 4th check raises.
    clock = iter([0, 5, 15, 25, 35])
    monkeypatch.setattr(mod.time, "monotonic", lambda: next(clock))

    class _RunningResponse:
        status_code = 200

        def json(self):
            return {"status": "RUNNING"}

    monkeypatch.setattr(mod.requests, "get",
                         lambda *a, **k: _RunningResponse())
    monkeypatch.setattr(mod, "_get_token", lambda: "fake-token")

    with pytest.raises(TimeoutError, match="30s"):
        mod.wait_for_op("op123")


def test_wait_for_op_returns_on_done_status(monkeypatch):
    """Sanity check the happy path still works: DONE with no error
    returns the operation dict without raising or looping forever."""
    from gcp import sql_export_to_gcs as mod

    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(mod.time, "monotonic", lambda: 0)

    class _DoneResponse:
        status_code = 200

        def json(self):
            return {"status": "DONE", "startTime": "2026-06-21T08:00:00Z",
                     "endTime": "2026-06-21T08:46:00Z"}

    monkeypatch.setattr(mod.requests, "get",
                         lambda *a, **k: _DoneResponse())
    monkeypatch.setattr(mod, "_get_token", lambda: "fake-token")

    result = mod.wait_for_op("op123")
    assert result["status"] == "DONE"
