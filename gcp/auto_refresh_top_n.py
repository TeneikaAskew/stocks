"""
Cloud Run Job: pre-warm the AI insight cache for the top-N ranker tickers.

Scheduled at 8:10 AM ET weekdays — after the news fetchers (8:00, 8:05)
land fresh data and before premarket-brief at 8:30. The job:

  1. Calls lib.agents.ranker.rank_tickers() — deterministic, no LLM,
     ~5s for ~100 candidates.
  2. Picks the top N (env: INSIGHT_AUTO_REFRESH_TOP_N, default 3).
  3. For each, skips if today's insight_reports row already exists
     (avoids burning LLM budget on a same-day cache hit).
  4. For each remaining, inserts a `queued` insight_runs row and
     enqueues a Cloud Tasks message that triggers the existing
     `insight-pipeline` Cloud Run job in on-demand mode (same path
     the UI's refresh button uses).

Cost control: the only knob is N. With max-concurrent-dispatches=5 on
the Cloud Tasks queue, top-3 reports run in parallel and finish in
~90s — comfortably before the premarket-brief at 8:30.

Usage:
    python -m gcp.auto_refresh_top_n              # production
    python -m gcp.auto_refresh_top_n --dry-run    # see what it would
                                                  # enqueue, no DB writes
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.agents.ranker import rank_tickers  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("auto-refresh-top-n")


# ---------------------------------------------------------------------------
# DB helpers — insert queued run, check today's cache.
# Match the patterns in platform/api/routers/insights.py so the runs the
# auto-refresh enqueues look identical to UI-triggered runs (same trigger
# string, same cache invalidation behavior).
# ---------------------------------------------------------------------------


def _is_cached_today(ticker: str) -> bool:
    """Return True if there's already an insight_reports row for this
    ticker with today's UTC date — meaning a fresh report exists and
    we'd be wasting LLM budget to re-run."""
    try:
        from gcp.database import connect

        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT 1 FROM insight_reports
                WHERE ticker = %s
                  AND as_of::date = (NOW() AT TIME ZONE 'UTC')::date
                LIMIT 1
                """,
                (ticker.upper(),),
            )
            return cur.fetchone() is not None
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("cache check failed for %s: %s", ticker, exc)
        # Fail-open: if we can't check, run the pipeline. The on-conflict
        # upsert in the pipeline will overwrite cleanly.
        return False


def _insert_queued_run(ticker: str, trigger: str) -> str:
    """Insert a `queued` row in insight_runs and return its id.
    Mirrors platform.api.routers.insights._insert_run."""
    from gcp.database import connect

    conn = connect()
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


def _enqueue_cloud_task(run_id: str, ticker: str) -> bool:
    """Enqueue a Cloud Tasks message that runs the insight-pipeline
    Cloud Run job with INSIGHT_RUN_ID + INSIGHT_TICKER env overrides.

    Mirrors platform.api.routers.insights._enqueue_cloud_task. Returns
    True on success, False on any failure (so the orchestrator can
    log + skip without blocking the other tickers).
    """
    try:
        from google.cloud import tasks_v2  # type: ignore
    except ImportError:
        logger.error("google-cloud-tasks not installed — cannot enqueue")
        return False

    project = os.environ.get("GCP_PROJECT_ID", "adept-mountain-474619-d4")
    region = os.environ.get("GCP_REGION", "us-east1")
    queue = os.environ.get("INSIGHT_TASKS_QUEUE", "insight-pipeline-queue")
    sa_email = os.environ.get(
        "INSIGHT_TASKS_SERVICE_ACCOUNT",
        f"trading-runner@{project}.iam.gserviceaccount.com",
    )
    job_url = (
        f"https://{region}-run.googleapis.com/apis/run.googleapis.com/v1/"
        f"namespaces/{project}/jobs/insight-pipeline:run"
    )
    try:
        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(project, region, queue)
        body = json.dumps(
            {
                "overrides": {
                    "containerOverrides": [
                        {
                            "env": [
                                {"name": "INSIGHT_RUN_ID", "value": run_id},
                                {"name": "INSIGHT_TICKER", "value": ticker},
                            ]
                        }
                    ]
                }
            }
        ).encode()
        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": job_url,
                "headers": {"Content-Type": "application/json"},
                "body": body,
                "oauth_token": {"service_account_email": sa_email},
            }
        }
        client.create_task(parent=parent, task=task)
        return True
    except Exception as exc:
        logger.error("Cloud Tasks enqueue failed for %s: %s", ticker, exc)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pre-warm insight cache for the top-N ranker tickers."
    )
    parser.add_argument(
        "--top-n", type=int,
        default=int(os.environ.get("INSIGHT_AUTO_REFRESH_TOP_N", "3")),
        help="Number of highest-ranked tickers to run the LLM pipeline on.",
    )
    parser.add_argument(
        "--catalyst-filter", default=os.environ.get("INSIGHT_AUTO_REFRESH_FILTER", ""),
        help="Comma-separated catalyst types to require (empty = no filter).",
    )
    parser.add_argument(
        "--ranker-limit", type=int,
        default=int(os.environ.get("INSIGHT_AUTO_REFRESH_RANKER_LIMIT", "20")),
        help="Max candidates the ranker considers before we pick top-N from it.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run the ranker + cache check but don't insert/enqueue anything.",
    )
    args = parser.parse_args()

    started = datetime.now(tz=timezone.utc)
    logger.info("auto-refresh-top-n starting at %s", started.isoformat())
    logger.info("  top_n=%d ranker_limit=%d filter=%s dry_run=%s",
                args.top_n, args.ranker_limit, args.catalyst_filter, args.dry_run)

    catalyst_filter = (
        {c.strip() for c in args.catalyst_filter.split(",") if c.strip()}
        if args.catalyst_filter else None
    )

    # 1. Rank
    rank_result = rank_tickers(
        catalyst_filter=catalyst_filter,
        limit=args.ranker_limit,
        # Always persist the audit row — it doubles as the auto-refresh log.
        persist_audit=not args.dry_run,
    )
    ranked = rank_result.get("ranked", [])
    logger.info(
        "ranker: %d candidates → %d ranked, run_id=%s",
        rank_result.get("candidate_count", 0),
        len(ranked),
        rank_result.get("run_id", "?"),
    )

    if not ranked:
        logger.info("no ranked tickers — exiting cleanly")
        return 0

    # 2. Pick top-N
    top = ranked[: args.top_n]
    logger.info("top-%d: %s", len(top),
                [f"{r['ticker']}({r['score']:.2f})" for r in top])

    # 3. Skip cached + enqueue
    enqueued: list[tuple[str, str]] = []
    skipped_cached: list[str] = []
    enqueue_failures: list[str] = []

    for entry in top:
        ticker = entry["ticker"]
        if _is_cached_today(ticker) and not args.dry_run:
            skipped_cached.append(ticker)
            logger.info("  %s: skipped (today's report already cached)", ticker)
            continue

        if args.dry_run:
            logger.info("  %s: would enqueue (dry-run)", ticker)
            continue

        try:
            run_id = _insert_queued_run(ticker, trigger="auto_refresh")
        except Exception as exc:
            logger.error("  %s: insert_run failed: %s", ticker, exc)
            enqueue_failures.append(ticker)
            continue

        if _enqueue_cloud_task(run_id, ticker):
            enqueued.append((ticker, run_id))
            logger.info("  %s: enqueued run_id=%s", ticker, run_id)
        else:
            enqueue_failures.append(ticker)

    # 4. Summary
    logger.info(
        "summary: enqueued=%d cached_skipped=%d failed=%d total_top_n=%d",
        len(enqueued), len(skipped_cached), len(enqueue_failures), len(top),
    )

    # Exit 0 even on partial failures — one ticker's enqueue failure
    # shouldn't block the others. The cron retry policy handles
    # whole-job failures; per-ticker failures are visible in the logs.
    return 0


if __name__ == "__main__":
    sys.exit(main())
