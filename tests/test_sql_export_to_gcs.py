"""Tests for gcp/sql_export_to_gcs.py — timeout alignment and poll logic."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

import gcp.sql_export_to_gcs as exp


# ── Timeout alignment (CLAUDE.md Rule 0.5) ───────────────────────────────────

# The Cloud Run task-timeout in deploy.sh is 10800s (3h). POLL_MAX_SECS must
# be strictly less than that, with at least a 300s gap so the Python code can
# raise TimeoutError and exit cleanly before Cloud Run kills the task.
_DEPLOY_TASK_TIMEOUT_SECS = 10800
_REQUIRED_HEADROOM_SECS = 300


def test_poll_max_secs_less_than_task_timeout():
    assert exp.POLL_MAX_SECS < _DEPLOY_TASK_TIMEOUT_SECS, (
        f"POLL_MAX_SECS ({exp.POLL_MAX_SECS}) must be < task-timeout "
        f"({_DEPLOY_TASK_TIMEOUT_SECS}) so the job exits cleanly before "
        "Cloud Run terminates it."
    )


def test_poll_max_secs_has_sufficient_headroom():
    headroom = _DEPLOY_TASK_TIMEOUT_SECS - exp.POLL_MAX_SECS
    assert headroom >= _REQUIRED_HEADROOM_SECS, (
        f"Only {headroom}s headroom between POLL_MAX_SECS ({exp.POLL_MAX_SECS}) "
        f"and task-timeout ({_DEPLOY_TASK_TIMEOUT_SECS}). Need >= {_REQUIRED_HEADROOM_SECS}s "
        "so the TimeoutError propagates before Cloud Run kills the task."
    )


# ── wait_for_op logic ────────────────────────────────────────────────────────

def _make_op_response(status: str, error: dict | None = None) -> MagicMock:
    body: dict = {"status": status}
    if error:
        body["error"] = error
    m = MagicMock(status_code=200)
    m.json.return_value = body
    m.raise_for_status = MagicMock()
    return m


@patch("gcp.sql_export_to_gcs.time.sleep")
@patch("gcp.sql_export_to_gcs.time.monotonic")
@patch("gcp.sql_export_to_gcs._get_token", return_value="tok")
@patch("gcp.sql_export_to_gcs.requests.get")
def test_wait_for_op_returns_on_done(mock_get, _mock_token, mock_mono, mock_sleep):
    mock_mono.side_effect = [0, 10]  # started=0, then 10s elapsed — well under cap
    mock_get.return_value = _make_op_response("DONE")

    result = exp.wait_for_op("projects/p/operations/op1")

    assert result["status"] == "DONE"
    mock_sleep.assert_called_once_with(exp.POLL_INTERVAL_SECS)


@patch("gcp.sql_export_to_gcs.time.sleep")
@patch("gcp.sql_export_to_gcs.time.monotonic")
@patch("gcp.sql_export_to_gcs._get_token", return_value="tok")
@patch("gcp.sql_export_to_gcs.requests.get")
def test_wait_for_op_raises_timeout(mock_get, _mock_token, mock_mono, mock_sleep):
    # monotonic() called twice per loop iteration: once for elapsed check,
    # once in the next iteration. Return a value > POLL_MAX_SECS immediately.
    mock_mono.side_effect = [0, exp.POLL_MAX_SECS + 1]

    with pytest.raises(TimeoutError, match="Export timed out"):
        exp.wait_for_op("projects/p/operations/op2")

    mock_sleep.assert_not_called()


@patch("gcp.sql_export_to_gcs.time.sleep")
@patch("gcp.sql_export_to_gcs.time.monotonic")
@patch("gcp.sql_export_to_gcs._get_token", return_value="tok")
@patch("gcp.sql_export_to_gcs.requests.get")
def test_wait_for_op_raises_on_export_error(mock_get, _mock_token, mock_mono, mock_sleep):
    mock_mono.side_effect = [0, 10]
    mock_get.return_value = _make_op_response(
        "DONE", error={"code": 500, "message": "internal error"}
    )

    with pytest.raises(RuntimeError, match="Export failed"):
        exp.wait_for_op("projects/p/operations/op3")
