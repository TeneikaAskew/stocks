"""
Cloud Run Job entry point for the AI Insights agent pipeline.

This job is invoked two ways:

1. **On-demand** — the `/api/insights/report/{ticker}/refresh` endpoint
   enqueues a Cloud Tasks message targeting this job with env vars
   `INSIGHT_RUN_ID` and `INSIGHT_TICKER`. The job picks them up,
   transitions the run row through queued -> running -> done|failed,
   and upserts an InsightReport into Cloud SQL.

2. **Scheduled** — invoked without `INSIGHT_RUN_ID` to run the daily
   batch. In that mode it iterates the tickers in `INSIGHT_TICKERS`
   (comma-separated, defaults to `SPY,IWM,QQQ`), inserts a new
   `insight_runs` row per ticker, and executes them sequentially.

Every run ends with exit 0 or exit 1; Cloud Run's retry policy takes
over from there. The job never raises — it catches top-level
exceptions and marks the run as failed so the platform can surface
the error.

Usage:
    python -m gcp.insight_pipeline_job                  # scheduled
    INSIGHT_RUN_ID=... INSIGHT_TICKER=SPY \\
        python -m gcp.insight_pipeline_job              # on-demand
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.agents.model_routing import _connect, load_routes_snapshot  # noqa: E402
from lib.agents.orchestrator import run_insight_pipeline  # noqa: E402
from lib.agents.schema import InsightReport  # noqa: E402
import lib.agents.vertex_adapter  # noqa: F401, E402 — registers adapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("insight-pipeline-job")


DEFAULT_TICKERS = ("SPY", "IWM", "QQQ")


# ---------------------------------------------------------------------------
# Run-state transitions (copy-pasted minimal subset of the router helpers
# so this module has no FastAPI dependency).
# ---------------------------------------------------------------------------


def _insert_run(ticker: str, trigger: str) -> str:
    conn = _connect()
    run_id = str(uuid4())
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO insight_runs (id, ticker, status, trigger)
            VALUES (%s, %s, 'queued', %s)
            """,
            (run_id, ticker.upper(), trigger),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def _transition(
    run_id: str,
    status: str,
    *,
    error: str | None = None,
    report_id: str | None = None,
) -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        if status == "running":
            cur.execute(
                "UPDATE insight_runs SET status='running', started_at=NOW() WHERE id=%s",
                (run_id,),
            )
        elif status == "done":
            cur.execute(
                """
                UPDATE insight_runs
                SET status='done', finished_at=NOW(), report_id=%s
                WHERE id=%s
                """,
                (report_id, run_id),
            )
        elif status == "failed":
            cur.execute(
                """
                UPDATE insight_runs
                SET status='failed', finished_at=NOW(), error=%s
                WHERE id=%s
                """,
                (error, run_id),
            )
        conn.commit()
    finally:
        conn.close()


def _upsert_report(report: InsightReport) -> str:
    conn = _connect()
    row_id = str(uuid4())
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO insight_reports
                (id, ticker, as_of, report, model_versions, cost_usd, latency_ms)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            ON CONFLICT (ticker, as_of) DO UPDATE
            SET report = EXCLUDED.report,
                model_versions = EXCLUDED.model_versions,
                cost_usd = EXCLUDED.cost_usd,
                latency_ms = EXCLUDED.latency_ms
            RETURNING id::text
            """,
            (
                row_id,
                report.ticker,
                report.as_of,
                report.model_dump_json(),
                json.dumps(report.model_versions),
                report.run_cost_usd,
                report.run_latency_ms,
            ),
        )
        returned = cur.fetchone()
        if returned:
            row_id = returned[0]
        conn.commit()
    finally:
        conn.close()
    return row_id


# ---------------------------------------------------------------------------
# Pipeline wrapper
# ---------------------------------------------------------------------------


async def _run_one(run_id: str, ticker: str) -> bool:
    """Execute one pipeline run and persist transitions. Returns True
    on success."""
    logger.info("[run_id=%s] starting pipeline for %s", run_id, ticker)
    _transition(run_id, "running")
    try:
        snapshot = load_routes_snapshot()
        report = await run_insight_pipeline(ticker, snapshot=snapshot)
        report_id = _upsert_report(report)
        _transition(run_id, "done", report_id=report_id)
        logger.info(
            "[run_id=%s] done — direction=%s conviction=%s cost=$%.4f latency=%dms",
            run_id,
            report.direction,
            report.conviction,
            report.run_cost_usd,
            report.run_latency_ms,
        )
        return True
    except Exception as exc:
        logger.exception("[run_id=%s] pipeline failed", run_id)
        _transition(run_id, "failed", error=str(exc))
        return False


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


async def _run_on_demand() -> int:
    run_id = os.environ["INSIGHT_RUN_ID"]
    ticker = os.environ["INSIGHT_TICKER"]
    ok = await _run_one(run_id, ticker)
    return 0 if ok else 1


async def _run_scheduled() -> int:
    tickers_env = os.environ.get("INSIGHT_TICKERS", ",".join(DEFAULT_TICKERS))
    tickers = [t.strip().upper() for t in tickers_env.split(",") if t.strip()]
    logger.info("scheduled run for tickers: %s", tickers)

    any_failures = False
    for ticker in tickers:
        run_id = _insert_run(ticker, trigger="scheduled")
        ok = await _run_one(run_id, ticker)
        if not ok:
            any_failures = True
    # Scheduled runs exit 0 even on partial failure — one ticker's
    # failure shouldn't block the other two from being reported as
    # "done" to Cloud Scheduler. The insight_runs table carries the
    # per-ticker error text for the admin to investigate.
    if any_failures:
        logger.warning("scheduled run completed with at least one failure")
    return 0


def main() -> int:
    if os.environ.get("INSIGHT_RUN_ID"):
        return asyncio.run(_run_on_demand())
    return asyncio.run(_run_scheduled())


if __name__ == "__main__":
    sys.exit(main())
