"""Regression test for the cloud-sql-weekly-export task-timeout drift.

deploy.sh's `deploy_weekly_pg_dump()` originally shipped with
`--task-timeout 3600` (1h). Execution cloud-sql-weekly-export-bcmlz hit
that ceiling on 2026-06-28 after running ~60 min and was killed
(GitHub issue #657). The live Cloud Run Job was hand-patched to 21600s
(6h) the same day and has succeeded on every run since, but deploy.sh
itself was never updated — so the next `./gcp/deploy.sh
cloud-sql-weekly-export` (or a full redeploy) would have silently
reverted the live job back to the value that already caused a
production failure. Pin the corrected value so that regression can't
recur silently.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEPLOY_SH = (REPO / "gcp/deploy.sh").read_text()


def _deploy_weekly_pg_dump_body() -> str:
    m = re.search(r"deploy_weekly_pg_dump\(\)\s*\{(.*?)\n\}",
                  DEPLOY_SH, re.DOTALL)
    assert m is not None, "deploy_weekly_pg_dump function not found in deploy.sh"
    return m.group(1)


def test_cloud_sql_weekly_export_task_timeout_matches_live_fix():
    """Must be >= 21600s (the value already validated in production after
    the 2026-06-28 timeout failure), not the original 3600s that failed."""
    body = _deploy_weekly_pg_dump_body()
    m = re.search(r"--task-timeout\s+(\d+)", body)
    assert m is not None, "deploy_weekly_pg_dump must set --task-timeout"
    timeout = int(m.group(1))
    assert timeout >= 21600, (
        f"cloud-sql-weekly-export --task-timeout={timeout}s is below the "
        f"21600s floor already proven necessary in production (issue #657) "
        f"— a redeploy would revert the live hot-fix and reintroduce the "
        f"1h timeout failure"
    )


def test_cloud_sql_weekly_export_timeout_has_headroom_over_observed_runtime():
    """Rule 0 capacity check: task-timeout must be >= 4x the observed
    worst-case wall-clock (~60 min, from cloud-sql-weekly-export-cwh72)."""
    body = _deploy_weekly_pg_dump_body()
    m = re.search(r"--task-timeout\s+(\d+)", body)
    assert m is not None
    timeout = int(m.group(1))
    observed_worst_case_seconds = 60 * 60  # ~60 min retry that succeeded
    assert timeout >= 4 * observed_worst_case_seconds, (
        f"task-timeout={timeout}s gives less than 4x headroom over the "
        f"observed ~{observed_worst_case_seconds}s worst-case runtime"
    )
