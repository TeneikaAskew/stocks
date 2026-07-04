"""Regression test for gcp/sql_export_to_gcs.py's POLL_MAX_SECS cap.

Codex review on PR #667 caught that raising the Cloud Run task-timeout to
21600s (6h) for cloud-sql-weekly-export was insufficient on its own: the
job's own `wait_for_op()` polls the Cloud SQL export operation and raises
TimeoutError after POLL_MAX_SECS, which was still hardcoded to 3600s (1h).
An export taking >1h but <6h would fail inside the app before Cloud Run's
own (much higher) timeout ever mattered.
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO = Path(__file__).resolve().parents[1]
DEPLOY_SH = (REPO / "gcp/deploy.sh").read_text()

# gcp/sql_export_to_gcs.py imports google.auth at module level purely to
# fetch an OAuth token in _get_token(), which every test here monkeypatches
# away. Stub it out (matching the pattern in test_magnitude_inference.py)
# rather than requiring the full google-auth/cryptography stack just to
# exercise the pure polling logic. Catches any import-time failure, not
# just ModuleNotFoundError, since a broken native cryptography backend
# raises other exception types.
for _mod in ("google", "google.auth", "google.auth.transport",
             "google.auth.transport.requests"):
    if _mod not in sys.modules:
        try:
            __import__(_mod)
        except Exception:
            sys.modules[_mod] = MagicMock()


def _deploy_task_timeout() -> int:
    m = re.search(r"deploy_weekly_pg_dump\(\)\s*\{(.*?)\n\}",
                  DEPLOY_SH, re.DOTALL)
    assert m is not None, "deploy_weekly_pg_dump function not found in deploy.sh"
    tm = re.search(r"--task-timeout\s+(\d+)", m.group(1))
    assert tm is not None
    return int(tm.group(1))


def test_poll_max_secs_default_below_task_timeout_with_margin():
    """The app-level poll cap must sit below the Cloud Run task-timeout
    with real margin, or Cloud Run's own kill (opaque NonZeroExitCode)
    fires before wait_for_op's TimeoutError (which is diagnosable)."""
    from gcp import sql_export_to_gcs as mod
    importlib.reload(mod)

    task_timeout = _deploy_task_timeout()
    assert mod.POLL_MAX_SECS < task_timeout, (
        f"POLL_MAX_SECS={mod.POLL_MAX_SECS} must be below the Cloud Run "
        f"task-timeout={task_timeout}s"
    )
    assert task_timeout - mod.POLL_MAX_SECS >= 300, (
        "leave at least 300s of margin below the Cloud Run task-timeout "
        "for container startup + the export-trigger round-trip"
    )
    # Regression guard: must actually have been raised from the original
    # 3600s that was too tight for a ~60min export (issue #657).
    assert mod.POLL_MAX_SECS > 3600, (
        "POLL_MAX_SECS regressed back to (or below) the original 1h cap "
        "that was too tight for the observed ~60min export runtime"
    )


def test_poll_max_secs_overridable_via_env(monkeypatch):
    monkeypatch.setenv("SQL_EXPORT_POLL_MAX_SECS", "7200")
    from gcp import sql_export_to_gcs as mod
    importlib.reload(mod)
    try:
        assert mod.POLL_MAX_SECS == 7200
    finally:
        monkeypatch.delenv("SQL_EXPORT_POLL_MAX_SECS", raising=False)
        importlib.reload(mod)


def test_wait_for_op_raises_timeout_error_after_poll_max_secs(monkeypatch):
    """wait_for_op must still fail loudly (not hang forever, not silently
    return) once the operation exceeds POLL_MAX_SECS."""
    from gcp import sql_export_to_gcs as mod
    importlib.reload(mod)

    monkeypatch.setattr(mod, "POLL_MAX_SECS", 30)
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)

    # Fake monotonic clock that advances past POLL_MAX_SECS after a few polls.
    clock = {"t": 0.0}

    def _fake_monotonic():
        return clock["t"]

    monkeypatch.setattr(mod.time, "monotonic", _fake_monotonic)

    class _FakeResp:
        status_code = 200

        def json(self):
            clock["t"] += 20  # advance the clock each poll
            return {"status": "RUNNING"}

    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResp())
    monkeypatch.setattr(mod, "_get_token", lambda: "fake-token")

    with pytest.raises(TimeoutError, match="30s"):
        mod.wait_for_op("op-123")
