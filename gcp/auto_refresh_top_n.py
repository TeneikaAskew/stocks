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

Cost control: the only knob is N, and it is bounded. N above
`insight_tasks.FANOUT_MAX_TICKERS` is clamped with a WARNING, because
every enqueued ticker becomes its own Cloud Run execution against one
Vertex quota and the queue does not throttle that — `jobs.run` returns
an Operation as soon as the execution is created, freeing the dispatch
slot immediately. Top-3 reports run in parallel and finish in ~90s,
comfortably before the premarket-brief at 8:30.

Exit codes:
  0 — dispatched. Covers DISPATCH, not reports: each child owns its own
      outcome in `insight_runs` from there. An all-cached run is also 0,
      since a warm cache is the outcome this job exists to produce.
  1 — dispatched nothing it had work for. This job has no in-process
      fallback (unlike insight-pipeline's `_dispatch_fanout`), so a green
      run producing zero reports would be indistinguishable from success.
  2 — misconfigured (negative N). Rejected before the ranker runs.

Usage:
    python -m gcp.auto_refresh_top_n              # production
    python -m gcp.auto_refresh_top_n --dry-run    # see what it would
                                                  # enqueue, no DB writes
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.agents.ranker import rank_tickers  # noqa: E402
from gcp.insight_tasks import FANOUT_MAX_TICKERS, EnqueueOutcome, enqueue_insight_task  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)

logger = logging.getLogger("auto-refresh-top-n")

# Documented in docs/plans/MORNING_RUN_PROTECTION_PLAN.md alongside
# run_kind='auto_refresh'. Forwarded on every enqueue so the child can
# classify itself; the prefix (not the exact string) is what
# _resolve_run_kind_and_update matches.
AUTO_REFRESH_TRIGGERED_BY = "cron:auto-refresh-top-n"


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
        from lib.agents.model_routing import connect

        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT 1 FROM insight_reports
                WHERE ticker = %s
                  AND as_of::date = (NOW() AT TIME ZONE 'UTC')::date
                  -- A backfill row for today would otherwise count as the
                  -- cache hit, skipping live generation, while the live-only
                  -- API query cannot serve that row: the ticker ends the day
                  -- with no visible report (Codex on #1098 round 2).
                  AND run_kind = 'live'
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
    from lib.agents.model_routing import connect

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


def _mark_run_failed(run_id: str, error: str) -> None:
    """Close out a `queued` row whose enqueue never landed.

    Mirrors gcp.insight_pipeline_job._transition's 'failed' branch. Raises
    nothing the caller must handle differently from any other ticker: a
    failure here is logged and the batch continues, because the enqueue
    failure it is recording has already been counted.
    """
    from lib.agents.model_routing import connect

    try:
        conn = connect()
        try:
            cur = conn.cursor()
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
    except Exception as exc:
        logger.error("could not mark run %s failed: %s", run_id, exc)


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

    # Validate before anything costs money. A negative N is unambiguously a
    # misconfiguration, and Python's slicing would read it as "all but the
    # last |N|" — `ranked[:-1]` is 19 tickers against the default ranker
    # limit, straight through the FANOUT_MAX_TICKERS ceiling below. Clamping
    # it to 0 instead would turn a typo into a silent no-op, which is the
    # failure this job was just fixed for. Exit 2 marks a config error,
    # distinct from 1 (dispatched nothing it had work for).
    if args.top_n < 0:
        logger.error(
            "top_n=%d is negative; refusing to run. Slicing a negative N "
            "selects every ranked ticker but the last, which would bypass "
            "FANOUT_MAX_TICKERS=%d entirely. Use 0 to disable pre-warming.",
            args.top_n, FANOUT_MAX_TICKERS,
        )
        return 2

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

    # 2. Pick top-N, bounded by the shared fan-out ceiling.
    #
    # Every enqueued ticker becomes its own Cloud Run execution, and they all
    # hit one Vertex quota — the 429 pressure this PR started from. The
    # scheduled pipeline answers an oversized batch by running it in-process;
    # this job has no in-process path (deliberately — see the exit-code note
    # below), so it clamps and says so. Delivering the highest-ranked N is
    # this job's purpose; delivering all of them at once is not worth
    # recreating the failure mode.
    effective_top_n = min(args.top_n, FANOUT_MAX_TICKERS)
    if effective_top_n < args.top_n:
        logger.warning(
            "top_n=%d exceeds FANOUT_MAX_TICKERS=%d; pre-warming the top %d "
            "only. %d enqueues would become %d concurrent executions against "
            "one Vertex quota. Raise the ceiling in gcp/insight_tasks.py if "
            "the quota genuinely supports it.",
            args.top_n, FANOUT_MAX_TICKERS, effective_top_n,
            args.top_n, args.top_n,
        )
    top = ranked[:effective_top_n]
    logger.info("top-%d: %s", len(top),
                [f"{r['ticker']}({r['score']:.2f})" for r in top])

    # 3. Skip cached + enqueue
    enqueued: list[tuple[str, str]] = []
    skipped_cached: list[str] = []
    enqueue_failures: list[str] = []
    # Tracked apart from failures: an unknown outcome is not a failure,
    # and counting it as one would under-report tickers that may have run.
    unknown_outcomes: list[str] = []

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
            # 'on_demand', not 'auto_refresh': insight_runs_trigger_check
            # permits only on_demand/scheduled/local_dev/manual_batch/
            # cache_hit/replay_refresh (verified against the live
            # constraint 2026-09-14), so 'auto_refresh' failed the insert
            # outright. 'on_demand' is also what this module's header says
            # it intends -- runs that "look identical to UI-triggered runs
            # (same trigger string)" -- and the UI path inserts 'on_demand'
            # at platform/api/routers/insights.py:832.
            run_id = _insert_queued_run(ticker, trigger="on_demand")
        except Exception as exc:
            logger.error("  %s: insert_run failed: %s", ticker, exc)
            enqueue_failures.append(ticker)
            continue

        outcome = enqueue_insight_task(
            run_id,
            ticker,
            # Container overrides replace the child's env, so this is the
            # only thing that tells the child it was pre-warmed rather than
            # hand-run. _resolve_run_kind_and_update maps it to
            # run_kind='auto_refresh', the value MORNING_RUN_PROTECTION_PLAN
            # defines for this producer.
            triggered_by=AUTO_REFRESH_TRIGGERED_BY,
        )
        if outcome == EnqueueOutcome.ENQUEUED:
            enqueued.append((ticker, run_id))
            logger.info("  %s: enqueued run_id=%s", ticker, run_id)
        elif outcome == EnqueueOutcome.NOT_ENQUEUED:
            # Definitively refused, so the row inserted 'queued' a moment
            # ago will never be picked up. Close it out: leaving it queued
            # shows operators and the UI a permanently pending run while
            # the job exits 0 and Cloud Run never retries.
            _mark_run_failed(run_id, "Cloud Tasks enqueue failed")
            enqueue_failures.append(ticker)
        else:
            # UNKNOWN: a child may be running this right now. Marking it
            # failed would label a live run dead, so leave it queued and
            # count it separately from a real failure.
            unknown_outcomes.append(ticker)
            logger.error(
                "  %s: enqueue outcome unknown for run_id=%s - left queued, "
                "not marked failed (a child may be running it)",
                ticker, run_id,
            )

    # 4. Summary
    logger.info(
        "summary: enqueued=%d cached_skipped=%d failed=%d unknown=%d "
        "total_top_n=%d",
        len(enqueued), len(skipped_cached), len(enqueue_failures),
        len(unknown_outcomes), len(top),
    )

    # Partial failure still exits 0: one ticker's enqueue failure must not
    # fail the run for the others, and per-ticker state is in insight_runs.
    #
    # A run that dispatched NOTHING it had work for is different, and must
    # not report success. `setup_insight_tasks_queue` is deliberately
    # non-fatal when it cannot grant roles/cloudtasks.enqueuer (setIamPolicy
    # is owner-only and the documented deploy identity holds roles/editor),
    # so a deploy can succeed with the binding absent. insight-pipeline
    # survives that — `_dispatch_fanout` hands NOT_ENQUEUED tickers back and
    # runs them in-process — but this job has no such fallback: it marks each
    # run failed and moves on. Returning 0 from there tells Cloud Scheduler
    # the pre-warm succeeded while producing zero reports, which is the exact
    # shape of the 30-day `enqueued=0` outage this module was just fixed for.
    # UNKNOWN does not count as a failure: a child may be running that ticker.
    if enqueue_failures and not enqueued and not unknown_outcomes:
        logger.error(
            "dispatched nothing: all %d ticker(s) refused (%s). Most likely "
            "trading-runner@ is missing roles/cloudtasks.enqueuer — "
            "gcp/deploy.sh prints the owner command it cannot run itself. "
            "Exiting non-zero so this surfaces as a failed execution rather "
            "than a green run that produced no reports.",
            len(enqueue_failures), ", ".join(enqueue_failures),
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
