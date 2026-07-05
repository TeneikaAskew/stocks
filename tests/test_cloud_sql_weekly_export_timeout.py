"""Regression tests for the cloud-sql-weekly-export timeout fix.

Both the Cloud Run task-timeout (gcp/deploy.sh) and the script's own
polling cap (gcp/sql_export_to_gcs.py POLL_MAX_SECS) were fixed at 3600s
(1h) while `trading` grew to 152 GB. The last successful export
(2026-06-21) took 45.8 min; the next two attempts (2026-06-28) both hit
the 3600s cap without finishing (gcp-job-failure issue #657). Pin two
invariants so a future edit can't silently reintroduce the mismatch:

  1. Both timeouts were raised with real headroom over the last known
     wall-clock (>=4x per CLAUDE.md Rule 0.5).
  2. POLL_MAX_SECS stays strictly below the Cloud Run task-timeout, so
     the script's own clean TimeoutError fires before Cloud Run force-
     kills the container (the failure mode that produced the confusing
     duplicate-looking pair of errors in issue #657).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEPLOY_SH = (REPO / "gcp/deploy.sh").read_text()
SQL_EXPORT_PY = (REPO / "gcp/sql_export_to_gcs.py").read_text()

# Last known-good wall-clock for the export, in seconds (2026-06-21 run:
# 2,746,943 ms). Both timeouts must clear 4x this to satisfy Rule 0.5.
_LAST_KNOWN_GOOD_WALL_CLOCK_SECS = 2747


def _deploy_task_timeout() -> int:
    m = re.search(r"deploy_weekly_pg_dump\(\)\s*\{(.*?)\n\}", DEPLOY_SH, re.DOTALL)
    assert m is not None, "deploy_weekly_pg_dump function not found"
    body = m.group(1)
    tm = re.search(r"--task-timeout\s+(\d+)", body)
    assert tm is not None, "deploy_weekly_pg_dump must set --task-timeout"
    return int(tm.group(1))


def _script_poll_max_secs() -> int:
    pm = re.search(r"^POLL_MAX_SECS\s*=\s*(\d+)", SQL_EXPORT_PY, re.MULTILINE)
    assert pm is not None, "sql_export_to_gcs.py must define POLL_MAX_SECS"
    return int(pm.group(1))


def test_task_timeout_has_4x_headroom_over_last_known_wall_clock():
    assert _deploy_task_timeout() >= 4 * _LAST_KNOWN_GOOD_WALL_CLOCK_SECS


def test_poll_max_secs_has_4x_headroom_over_last_known_wall_clock():
    assert _script_poll_max_secs() >= 4 * _LAST_KNOWN_GOOD_WALL_CLOCK_SECS


def test_poll_max_secs_stays_below_task_timeout():
    """The script's own poll cap must fire (clean TimeoutError, exit 1)
    strictly before Cloud Run's task-timeout force-kills the container —
    otherwise the log shows a bare `Container called exit(1)`/SIGKILL
    with no diagnostic message."""
    assert _script_poll_max_secs() < _deploy_task_timeout()
