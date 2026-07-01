"""Regression tests for gcp/sql_export_to_gcs.py.

Guards the invariant behind GH #657: POLL_MAX_SECS (the Python
process's internal poll ceiling) must stay comfortably below the
Cloud Run --task-timeout configured for cloud-sql-weekly-export in
gcp/deploy.sh, so the process exits with a clean TimeoutError instead
of being killed mid-poll by Cloud Run. The two 2026-06-28 failures
(bcmlz, cwh72) happened because these two numbers were equal (both
3600s) and then drifted out of sync when only one was bumped.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gcp.sql_export_to_gcs import POLL_MAX_SECS, wait_for_op

DEPLOY_SH = Path(__file__).resolve().parents[1] / "gcp" / "deploy.sh"


def _deployed_task_timeout() -> int:
    """Extract --task-timeout for cloud-sql-weekly-export from deploy.sh."""
    text = DEPLOY_SH.read_text()
    match = re.search(r"deploy_weekly_pg_dump\(\).*?\n\}", text, re.DOTALL)
    assert match, "deploy_weekly_pg_dump() function not found in deploy.sh"
    block = match.group(0)
    timeout_match = re.search(r"--task-timeout\s+(\d+)", block)
    assert timeout_match, "--task-timeout flag not found in deploy_weekly_pg_dump()"
    return int(timeout_match.group(1))


def test_poll_max_secs_less_than_deployed_task_timeout():
    """The Python poll ceiling must never exceed the Cloud Run task
    timeout, or Cloud Run kills the container before the code gets a
    chance to raise its own clean TimeoutError."""
    assert POLL_MAX_SECS < _deployed_task_timeout()


def test_poll_max_secs_has_sufficient_headroom():
    """Require real headroom (not just 1 second under) so a slow final
    poll iteration still finishes and exits before the hard Cloud Run
    kill — this is exactly the gap that caused execution cwh72 to fail
    with exit code 1 instead of a clean TimeoutError."""
    headroom = _deployed_task_timeout() - POLL_MAX_SECS
    assert headroom >= 300, (
        f"only {headroom}s headroom between POLL_MAX_SECS and the "
        "deployed --task-timeout; need >=300s for a clean exit"
    )


def test_wait_for_op_returns_on_done():
    """Happy path: operation reports DONE with no error -> returns."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"status": "DONE"}
    with patch("gcp.sql_export_to_gcs.requests.get", return_value=resp), \
         patch("gcp.sql_export_to_gcs.time.sleep"), \
         patch("gcp.sql_export_to_gcs._get_token", return_value="tok"):
        result = wait_for_op("op-123")
    assert result == {"status": "DONE"}


def test_wait_for_op_raises_on_export_error():
    """Operation reports DONE but with an error payload -> raise, don't
    report success (no silent fallback per CLAUDE.md §3.7)."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"status": "DONE", "error": {"code": 42}}
    with patch("gcp.sql_export_to_gcs.requests.get", return_value=resp), \
         patch("gcp.sql_export_to_gcs.time.sleep"), \
         patch("gcp.sql_export_to_gcs._get_token", return_value="tok"):
        with pytest.raises(RuntimeError, match="Export failed"):
            wait_for_op("op-123")


def test_wait_for_op_raises_timeout_before_poll_max_secs():
    """Exceeding POLL_MAX_SECS raises a clean TimeoutError referencing
    the ceiling — this is the code path that must fire well before
    Cloud Run's --task-timeout kills the container outright."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"status": "RUNNING"}

    # Simulate monotonic clock advancing past POLL_MAX_SECS on the
    # second check.
    times = iter([0.0, POLL_MAX_SECS + 1])
    with patch("gcp.sql_export_to_gcs.requests.get", return_value=resp), \
         patch("gcp.sql_export_to_gcs.time.sleep"), \
         patch("gcp.sql_export_to_gcs.time.monotonic", side_effect=lambda: next(times)), \
         patch("gcp.sql_export_to_gcs._get_token", return_value="tok"):
        with pytest.raises(TimeoutError, match=str(POLL_MAX_SECS)):
            wait_for_op("op-123")
