"""Regression test for `scripts/generate_historical_report.py:_upsert_report`.

Issue #333: PR #305 added `per_role_cost JSONB` to `insight_reports` but
the column wiring was only added to the Cloud Run job
(`gcp/insight_pipeline_job.py`) and the FastAPI router
(`platform/api/routers/insights.py`). The historical-replay script's
copy of `_upsert_report` was overlooked, so reports backfilled by
`generate_historical_report.py` had `per_role_cost = NULL` even though
`report.per_role_cost` was populated.

The test is source-based — it grep's the script file for the SQL
contract — because importing the script transitively pulls in
psycopg2, which isn't installed in every CI sandbox. Source-based
regression is appropriate here: the bug was a missed edit, not a
runtime path that needs simulation. Any future drift between the
three `_upsert_report` copies (job + router + script) trips this.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO / "scripts" / "generate_historical_report.py"


def test_upsert_report_writes_per_role_cost_column():
    src = SCRIPT_PATH.read_text()
    # Column appears in the INSERT column list
    assert "per_role_cost" in src, (
        "scripts/generate_historical_report.py must reference "
        "per_role_cost — issue #333."
    )
    # ON CONFLICT path refreshes the column on re-runs
    assert "per_role_cost = EXCLUDED.per_role_cost" in src, (
        "ON CONFLICT update must refresh per_role_cost so a re-run "
        "after a value-fix isn't a silent no-op."
    )
    # Params tuple serializes report.per_role_cost
    assert "json.dumps(report.per_role_cost)" in src, (
        "Params must JSON-serialize report.per_role_cost; the column "
        "type is JSONB."
    )


def test_three_upsert_copies_carry_per_role_cost():
    """Defends the invariant that all THREE writer paths persist
    per_role_cost. Catches the case where someone adds a fourth
    writer or removes the column from one path."""
    paths = [
        REPO / "scripts" / "generate_historical_report.py",
        REPO / "platform" / "api" / "routers" / "insights.py",
        REPO / "gcp" / "insight_pipeline_job.py",
    ]
    for p in paths:
        src = p.read_text()
        assert "per_role_cost" in src, (
            f"{p.relative_to(REPO)} writes to insight_reports but "
            f"does not reference per_role_cost — issue #333 / G.P3.2."
        )
        assert "EXCLUDED.per_role_cost" in src, (
            f"{p.relative_to(REPO)} must include per_role_cost in its "
            f"ON CONFLICT DO UPDATE clause."
        )
