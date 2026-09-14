"""
Cloud Run Job entry point for the AI Insights agent pipeline.

This job is invoked two ways:

1. **On-demand** — the `/api/insights/report/{ticker}/refresh` endpoint
   enqueues a Cloud Tasks message targeting this job with env vars
   `INSIGHT_RUN_ID` and `INSIGHT_TICKER`. The job picks them up,
   transitions the run row through queued -> running -> done|failed,
   and upserts an InsightReport into Cloud SQL.

2. **Scheduled** — invoked without `INSIGHT_RUN_ID` to run the daily
   batch. It resolves the tickers (`INSIGHT_TICKERS`, else the
   watchlist, else `SPY,IWM,QQQ`), inserts a `queued` `insight_runs`
   row per ticker, and fans each one out as its own Cloud Tasks
   message back into mode 1 above, so the tickers run as parallel
   executions rather than a sequential in-process loop.

   Fan-out is about isolation more than speed. Under the old loop a
   single ticker's failure was contained only by a `try/except`: on
   2026-09-11 a transient Vertex 429 killed SPY at the judge node while
   IWM and QQQ had already been written, and the job still exited 0.
   One execution per ticker gives each its own task timeout and its own
   Cloud Run retry. Note that the queue does NOT throttle the resulting
   workloads: `max-concurrent-dispatches` bounds in-flight dispatch
   requests, and `jobs.run` returns as soon as the execution exists, so
   the slot frees immediately. Concurrency is bounded by refusing to fan
   out a batch larger than FANOUT_MAX_TICKERS instead.

   Set `INSIGHT_FANOUT=0` to revert to the sequential loop without a
   redeploy. An enqueue the server definitively refused falls back to
   running that ticker in-process, so an outage costs throughput rather
   than reports; an enqueue whose outcome is UNKNOWN does not, because a
   child may already be running it.

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

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional, Union
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gcp.insight_tasks import EnqueueOutcome, enqueue_insight_task  # noqa: E402
from lib.agents.model_routing import connect, load_routes_snapshot  # noqa: E402
from lib.agents.orchestrator import run_insight_pipeline  # noqa: E402
from lib.agents.schema import InsightReport  # noqa: E402
import lib.agents.vertex_adapter  # noqa: F401, E402 — registers adapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("insight-pipeline-job")


DEFAULT_TICKERS = ("SPY", "IWM", "QQQ")

# Default cap on the per-execution ticker list. The 8:45 AM cron only
# runs the 3 DEFAULT_TICKERS, so anything beyond ~10 is almost always a
# misconfiguration (the 4/24 incident: a manual run iterated 152 tickers
# and burned ~$1.20 + Vertex quota before anyone noticed). Override with
# INSIGHT_BATCH_OVERRIDE=1 for one-off intentional bulk runs.
DEFAULT_MAX_BATCH = 10


def parse_tickers(raw: str) -> list[str]:
    """Parse INSIGHT_TICKERS into a deduped, uppercase list.

    Accepts two forms so the caller can be explicit when scripting:
      • CSV string         → ``"SPY,IWM,QQQ"``
      • JSON array string  → ``'["SPY","IWM","QQQ"]'``

    JSON arrays are preferred for programmatic callers — they make the
    list-of-tickers intent explicit and let shell-quoting nightmares
    fall away. Empty or whitespace-only entries are dropped.
    """
    if not raw:
        return []
    raw = raw.strip()
    parsed: list = []
    # Anything starting with `{` is a JSON object, not a ticker list —
    # treat as invalid (return []) rather than fabricate semantics.
    if raw.startswith("{"):
        return []
    if raw.startswith("[") and raw.endswith("]"):
        try:
            obj = json.loads(raw)
            if isinstance(obj, list):
                parsed = obj
            else:
                parsed = []
        except json.JSONDecodeError:
            # Malformed JSON — fall through to CSV parsing.
            parsed = raw.split(",")
    else:
        parsed = raw.split(",")

    out: list[str] = []
    seen: set[str] = set()
    for item in parsed:
        tk = str(item).strip().upper()
        if tk and tk not in seen:
            seen.add(tk)
            out.append(tk)
    return out


def parse_as_of(raw: Optional[str]) -> Optional[Union[date, datetime]]:
    """Parse INSIGHT_AS_OF into a date or aware datetime.

    Accepted forms (in order of precedence):
      * ``YYYY-MM-DD``                   → ``date``
      * ``YYYY-MM-DDTHH:MM[:SS][Z|±HH:MM]`` → tz-aware ``datetime``
                                            (naive input is treated as UTC)

    Returns ``None`` when ``raw`` is empty/whitespace so the pipeline
    falls back to its default "as of now" behaviour.

    Raises ``ValueError`` on a malformed string or a future-dated cutoff
    so the caller can surface a clean error instead of silently running
    against the live snapshot. The caller is responsible for translating
    that into an exit-1 / 4xx response.
    """
    if not raw or not raw.strip():
        return None
    s = raw.strip()
    parsed: Union[date, datetime]
    # Date-only first — len 10 with two dashes is unambiguous
    if len(s) == 10 and s.count("-") == 2:
        parsed = date.fromisoformat(s)
    else:
        # Allow trailing 'Z' — Python <3.11 datetime.fromisoformat doesn't
        norm = s.replace("Z", "+00:00") if s.endswith("Z") else s
        dt = datetime.fromisoformat(norm)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        parsed = dt
    # Future-dated cutoffs are almost always a typo — reject so the user
    # sees a clean error instead of getting a "live" report mislabelled
    # as historical.
    now = datetime.now(timezone.utc)
    today = now.date()
    if isinstance(parsed, datetime):
        if parsed > now:
            raise ValueError(f"INSIGHT_AS_OF {s!r} is in the future")
    else:
        if parsed > today:
            raise ValueError(f"INSIGHT_AS_OF {s!r} is in the future")
    return parsed


def classify_trigger(tickers: list[str]) -> str:
    """Tag the trigger as `manual_batch` when the ticker list differs
    from the daily default (SPY/IWM/QQQ), otherwise `scheduled`.

    The audit trail in `insight_runs.trigger` then distinguishes the
    8:45 AM cron from one-off manual gcloud invocations, so usage
    accounting / cost attribution can split them.
    """
    default = set(DEFAULT_TICKERS)
    return "scheduled" if set(tickers) == default else "manual_batch"


# ---------------------------------------------------------------------------
# Run-state transitions (copy-pasted minimal subset of the router helpers
# so this module has no FastAPI dependency).
# ---------------------------------------------------------------------------


def _insert_run(ticker: str, trigger: str) -> str:
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


def _transition(
    run_id: str,
    status: str,
    *,
    error: str | None = None,
    report_id: str | None = None,
) -> bool:
    """Move a run to `status`. Returns whether this caller made the move.

    Only the 'running' transition can return False, and it is the claim
    that makes a redelivered launch safe. Two things can start a SECOND
    execution carrying the SAME run_id, and the deterministic task name
    fixes neither because it only deduplicates `create_task`:

      * Cloud Tasks retries the HTTP target POST (queue is --max-attempts 2).
        `jobs.run` creates the execution and returns an Operation, so a
        lost response after a successful launch is indistinguishable from
        a failed one, and the retry launches a second execution.
      * Cloud Run retries the task itself (job is --max-retries 1).

    Unclaimed, both executions run the paid pipeline, append their own
    insight_reports_history row, and race the final status. The DB row is
    the only state both can see, so the claim is a compare-and-swap on it:
    exactly one UPDATE matches and the loser stands down.

    'failed' is claimable so Cloud Run's own retry-after-failure still
    works. 'running' deliberately is NOT: a crashed execution leaves a
    visibly stuck row, which is better than a second one silently
    duplicating work we cannot prove has stopped. (Codex, PR #1094.)
    """
    conn = connect()
    try:
        cur = conn.cursor()
        if status == "running":
            cur.execute(
                "UPDATE insight_runs SET status='running', started_at=NOW() "
                "WHERE id=%s AND status IN ('queued', 'failed')",
                (run_id,),
            )
            claimed = cur.rowcount == 1
            conn.commit()
            return claimed
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
    # done/failed are unconditional and always "applied"; only the
    # 'running' claim above can decline.
    return True


def _resolve_run_kind_and_update(arg_update: bool) -> tuple[bool, str]:
    """Resolve allow_update + run_kind from CLI arg + env vars.

    Mirrors gcp.premarket_brief._resolve_run_kind_and_update so the two
    pipelines have identical override semantics.

    Precedence (highest first):
      1. arg_update=True OR INSIGHT_UPDATE=true → ('manual_update', True)
      2. INSIGHT_AS_OF set (replay) → ('replay_refresh', True)
      3. INSIGHT_TRIGGERED_BY starts with 'cloud-scheduler' → ('scheduled', False)
      4. INSIGHT_TRIGGERED_BY starts with 'cron:auto-refresh' → ('auto_refresh', False)
      5. otherwise → ('manual_replay', False)

    Branch 4 is the run_kind docs/plans/MORNING_RUN_PROTECTION_PLAN.md
    defines for auto_refresh_top_n, with 'cron:auto-refresh-top-n' as its
    documented triggered_by. Without it the pre-warm's children fall
    through to 'manual_replay' and are indistinguishable from a hand-run
    replay in insight_reports_history -- which is the only place that
    producer was still identifiable once its insight_runs.trigger had to
    become 'on_demand' to satisfy the check constraint (Codex, PR #1094).
    run_kind is VARCHAR(20) with no check constraint, so extending the
    set here needs no migration.
    """
    if arg_update or os.environ.get('INSIGHT_UPDATE') == 'true':
        return True, 'manual_update'
    if os.environ.get('INSIGHT_AS_OF'):
        return True, 'replay_refresh'
    triggered_by = os.environ.get('INSIGHT_TRIGGERED_BY', '')
    if triggered_by.startswith('cron:auto-refresh'):
        return False, 'auto_refresh'
    if triggered_by.startswith('cloud-scheduler'):
        return False, 'scheduled'
    return False, 'manual_replay'


def _insert_report_history(report: InsightReport, insight_run_id: str,
                           run_kind: str, triggered_by: Optional[str]) -> None:
    """Append to insight_reports_history. Append-only, never UPSERTs.

    Always called regardless of allow_update — the audit trail must
    capture every run attempt, even ones that don't touch the current
    table.
    """
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO insight_reports_history
                (insight_run_id, ticker, as_of, report, model_versions,
                 cost_usd, per_role_cost, latency_ms, run_kind, triggered_by)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s, %s, %s)
            """,
            (
                insight_run_id,
                report.ticker,
                report.as_of,
                report.model_dump_json(),
                json.dumps(report.model_versions),
                report.run_cost_usd,
                json.dumps(report.per_role_cost),
                report.run_latency_ms,
                run_kind,
                triggered_by,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _canonical_run_kind() -> str:
    """Provenance for the canonical insight_reports row.

    The operational `run_kind` threaded through _run_one ('scheduled',
    'manual_update', ...) describes HOW a run was triggered and lands in
    insight_reports_history. This is the three-value DATA taxonomy shared
    with trades, signal_alerts and premarket_analysis, which is what the
    routers filter on. An INSIGHT_AS_OF run reconstructs a past day's
    report from that day's data: real analysis, but not the report that
    was published then, so /api/insights must not serve it as one
    (audit 2026-09-14).

    Blank and whitespace-only are "no override": parse_as_of returns None
    for them and the pipeline generates a current live report, so testing
    the raw env var for truthiness would stamp that live report 'replay'
    and the new live-only readers would hide it (Codex on #1098 round 4).
    """
    raw = os.environ.get('INSIGHT_AS_OF')
    return 'replay' if raw and raw.strip() else 'live'


def _upsert_report(report: InsightReport, allow_update: bool = False) -> Optional[str]:
    """Write to insight_reports.

    When allow_update=True: UPSERT (existing behavior).
    When allow_update=False: INSERT...ON CONFLICT DO NOTHING — the
        canonical morning row is protected. Returns existing row's id
        on conflict; new row's id otherwise.

    Returns the row id (existing or new), or None if insert was a
    no-op AND lookup of existing row failed.
    """
    conn = connect()
    row_id = str(uuid4())
    try:
        cur = conn.cursor()
        if allow_update:
            cur.execute(
                """
                INSERT INTO insight_reports
                    (id, ticker, as_of, report, model_versions, cost_usd,
                     per_role_cost, latency_ms, run_kind)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s, %s)
                ON CONFLICT (ticker, as_of) DO UPDATE
                SET report = EXCLUDED.report,
                    model_versions = EXCLUDED.model_versions,
                    cost_usd = EXCLUDED.cost_usd,
                    per_role_cost = EXCLUDED.per_role_cost,
                    latency_ms = EXCLUDED.latency_ms,
                    -- Provenance rides the overwrite. Without it an as-of
                    -- replay overwriting a live row left the row reading 'live'
                    -- with replay content, which the live-only reader then serves
                    -- as current; the reverse hid newly live content (Codex, #1098).
                    run_kind = EXCLUDED.run_kind
                RETURNING id::text
                """,
                (
                    row_id, report.ticker, report.as_of,
                    report.model_dump_json(),
                    json.dumps(report.model_versions),
                    report.run_cost_usd,
                    json.dumps(report.per_role_cost),
                    report.run_latency_ms,
                    _canonical_run_kind(),
                ),
            )
            returned = cur.fetchone()
            if returned:
                row_id = returned[0]
            conn.commit()
            return row_id

        # Default — protect the canonical row. Insert if missing,
        # skip-and-return-existing-id if already present.
        cur.execute(
            """
            INSERT INTO insight_reports
                (id, ticker, as_of, report, model_versions, cost_usd,
                 per_role_cost, latency_ms, run_kind)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s, %s)
            -- Protect an existing LIVE row, but replace a non-live one.
            -- DO NOTHING alone deadlocked with the cache fix: once a
            -- backfill row held today's key, _is_cached_today correctly
            -- asked for a live refresh, this insert then did nothing, the
            -- run was marked done against the non-live row's id, and the
            -- live-only reader still had no row to serve. The ticker ended
            -- the day with no report at all (Codex on #1098 round 3).
            ON CONFLICT (ticker, as_of) DO UPDATE
            SET report = EXCLUDED.report,
                model_versions = EXCLUDED.model_versions,
                cost_usd = EXCLUDED.cost_usd,
                per_role_cost = EXCLUDED.per_role_cost,
                latency_ms = EXCLUDED.latency_ms,
                run_kind = EXCLUDED.run_kind
            WHERE insight_reports.run_kind <> 'live'
            RETURNING id::text
            """,
            (
                row_id, report.ticker, report.as_of,
                report.model_dump_json(),
                json.dumps(report.model_versions),
                report.run_cost_usd,
                json.dumps(report.per_role_cost),
                report.run_latency_ms,
                _canonical_run_kind(),
            ),
        )
        returned = cur.fetchone()
        if returned:
            row_id = returned[0]
            logger.info("insight_reports: inserted new row for %s as_of=%s",
                        report.ticker, report.as_of)
        else:
            # Conflict → look up existing row's id so caller can link
            cur.execute(
                "SELECT id::text FROM insight_reports "
                "WHERE ticker = %s AND as_of = %s",
                (report.ticker, report.as_of),
            )
            existing = cur.fetchone()
            row_id = existing[0] if existing else None
            logger.warning(
                "insight_reports: row already exists for %s as_of=%s — "
                "skipping current-table write (history-only). Pass "
                "--update or set INSIGHT_UPDATE=true to overwrite.",
                report.ticker, report.as_of,
            )
        conn.commit()
        return row_id
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pipeline wrapper
# ---------------------------------------------------------------------------


async def _run_one(
    run_id: str,
    ticker: str,
    as_of: Optional[Union[date, datetime]] = None,
    allow_update: bool = False,
    run_kind: str = 'scheduled',
    triggered_by: Optional[str] = None,
) -> bool:
    """Execute one pipeline run and persist transitions. Returns True
    on success.

    ``as_of`` (when provided) freezes every summarizer to the data
    available at that cutoff — daily bars, options snapshots, news,
    catalysts. The orchestrator threads it through unchanged.

    ``allow_update`` controls whether the existing insight_reports row
    can be overwritten on conflict. History row is always written
    regardless — the audit trail captures every run attempt.
    """
    logger.info(
        "[run_id=%s] starting pipeline for %s%s "
        "(allow_update=%s, run_kind=%s)",
        run_id, ticker,
        f" as_of={as_of}" if as_of else "",
        allow_update, run_kind,
    )
    if not _transition(run_id, "running"):
        # Another execution owns this run_id. Returning True rather than
        # False on purpose: nothing failed, and exiting non-zero here would
        # make Cloud Run retry the loser of the race over and over.
        logger.warning(
            "[run_id=%s] %s is already claimed by another execution "
            "(redelivered task or job retry) — standing down, not re-running it",
            run_id, ticker,
        )
        return True
    try:
        snapshot = load_routes_snapshot()
        report = await run_insight_pipeline(ticker, as_of=as_of, snapshot=snapshot)
        # Always append to history first; current-table write is conditional.
        _insert_report_history(report, run_id, run_kind, triggered_by)
        report_id = _upsert_report(report, allow_update=allow_update)
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


def _update_explicitly_requested(arg_update: bool) -> bool:
    """Whether an update was asked for OUTRIGHT, as opposed to implied.

    Mirrors the highest-precedence branch of
    `_resolve_run_kind_and_update`. A replay (`INSIGHT_AS_OF`) also
    resolves allow_update=True, but for a different reason and with a
    different run_kind, and a child re-derives that from the forwarded
    cutoff on its own. Only the outright request travels as
    INSIGHT_UPDATE.
    """
    return bool(arg_update or os.environ.get("INSIGHT_UPDATE") == "true")


# The queue's max-concurrent-dispatches bounds in-flight HTTP requests, NOT
# running executions: Cloud Run's jobs.run returns a long-running Operation
# as soon as the execution is created, so each :run response frees its queue
# slot immediately and N enqueued tickers become N concurrent executions.
# That is fine at the daily 3 and wrong at DEFAULT_MAX_BATCH=10, which would
# put roughly 10x the analyst fan-out against Vertex at once -- the opposite
# of what this change is for. Cap the batch size that may fan out; anything
# larger runs in-process, where the concurrency is one ticker at a time.
# (Codex, PR #1094.)
FANOUT_MAX_TICKERS = 5


def _fanout_enabled() -> bool:
    """Whether the scheduled batch fans out one execution per ticker.

    On by default. `INSIGHT_FANOUT=0` reverts to the in-process loop
    without a redeploy — the Cloud Scheduler body can pass it as a
    container override, so reverting is a scheduler edit, not a build.
    """
    raw = os.environ.get("INSIGHT_FANOUT", "1").strip().lower()
    return raw not in ("0", "false", "no")


def _dispatch_fanout(
    tickers: list[str],
    *,
    trigger: str,
    as_of: Optional[Union[date, datetime]],
    force_update: bool,
    triggered_by: Optional[str],
) -> list[tuple[str, str]]:
    """Enqueue one Cloud Tasks message per ticker.

    Returns the `(run_id, ticker)` pairs whose enqueue FAILED so the
    caller can run those in-process. A successfully enqueued ticker is
    picked up by a separate `insight-pipeline` execution in on-demand
    mode, which owns its own queued -> running -> done|failed
    transitions from there.

    The `insight_runs` row is inserted BEFORE the enqueue. A row whose
    enqueue was definitively refused is handed back to the caller and
    executed with that same id, so the run is never orphaned and never
    duplicated.

    Only NOT_ENQUEUED is handed back. An UNKNOWN outcome means a child
    may already be running that ticker, so running it here too would put
    two pipelines on one run_id; it is left queued and logged instead.
    """
    # date.isoformat() and datetime.isoformat() both round-trip through
    # parse_as_of (10-char date vs tz-aware datetime).
    as_of_iso = as_of.isoformat() if as_of is not None else None
    failed: list[tuple[str, str]] = []
    unknown = 0
    for ticker in tickers:
        run_id = _insert_run(ticker, trigger=trigger)
        outcome = enqueue_insight_task(
            run_id,
            ticker,
            as_of_iso=as_of_iso,
            triggered_by=triggered_by,
            force_update=force_update,
        )
        if outcome == EnqueueOutcome.ENQUEUED:
            logger.info("[run_id=%s] enqueued %s for parallel execution", run_id, ticker)
        elif outcome == EnqueueOutcome.NOT_ENQUEUED:
            failed.append((run_id, ticker))
        else:
            # Deliberately neither retried nor marked failed: the row may
            # be genuinely queued, and 'queued' is the honest state for
            # "not yet known to have started".
            unknown += 1
            logger.error(
                "[run_id=%s] %s enqueue outcome unknown - left queued, NOT run "
                "in-process. Re-run it on demand once you can confirm no child ran.",
                run_id, ticker,
            )
    logger.info(
        "fan-out dispatched: %d/%d enqueued, %d falling back in-process, %d unknown",
        len(tickers) - len(failed) - unknown, len(tickers), len(failed), unknown,
    )
    return failed


async def _run_on_demand(allow_update_arg: bool = False) -> int:
    run_id = os.environ["INSIGHT_RUN_ID"]
    ticker = os.environ["INSIGHT_TICKER"]
    try:
        as_of = parse_as_of(os.environ.get("INSIGHT_AS_OF"))
    except ValueError as exc:
        logger.error("INSIGHT_AS_OF invalid: %s", exc)
        return 1
    allow_update, run_kind = _resolve_run_kind_and_update(allow_update_arg)
    triggered_by = os.environ.get('INSIGHT_TRIGGERED_BY')
    ok = await _run_one(
        run_id, ticker, as_of=as_of,
        allow_update=allow_update, run_kind=run_kind,
        triggered_by=triggered_by,
    )
    return 0 if ok else 1


async def _run_scheduled(allow_update_arg: bool = False) -> int:
    # Ticker resolution chain (first non-empty wins):
    #   1. INSIGHT_TICKERS env var — explicit one-off override for ad-hoc
    #      gcloud run jobs execute invocations.
    #   2. Cloud SQL `watchlists` table — the production source of truth
    #      kept in sync with the React UI's add/remove endpoints.
    #   3. alert_config.json `watchlist` field — repo-baked seed.
    #   4. DEFAULT_TICKERS — last-resort hardcoded SPY/IWM/QQQ so the
    #      scheduled cron never silently no-ops.
    # Layers 2-3 share `gcp.fetchers._watchlist.load_watchlist`, which
    # also handles the Cloud SQL → file → env fallback internally and
    # fires a Discord alert when every layer comes back empty.
    tickers_env = os.environ.get("INSIGHT_TICKERS", "").strip()
    if tickers_env:
        tickers = parse_tickers(tickers_env)
        ticker_source = "INSIGHT_TICKERS env"
    else:
        try:
            # Filter to in_insight=TRUE — peer tickers added to the
            # watchlist for /similar comparison (MRVL, AMD, ANET, …)
            # are NOT auto-included in the daily AI insight pipeline,
            # which costs a Vertex call per ticker. Operator must
            # explicitly opt those in via UPDATE watchlists SET
            # in_insight=TRUE WHERE ticker='X'.
            from gcp.fetchers._watchlist import load_watchlist
            tickers = load_watchlist(surface='insight')
            ticker_source = "watchlists table (in_insight=TRUE)"
        except Exception as exc:
            logger.warning("watchlist load failed (%s); falling back to DEFAULT_TICKERS", exc)
            tickers = []
            ticker_source = "DEFAULT_TICKERS (watchlist load error)"
        if not tickers:
            tickers = list(DEFAULT_TICKERS)
            ticker_source = "DEFAULT_TICKERS (watchlist empty)"

    try:
        as_of = parse_as_of(os.environ.get("INSIGHT_AS_OF"))
    except ValueError as exc:
        logger.error("INSIGHT_AS_OF invalid: %s", exc)
        return 1
    if not tickers:
        logger.error(
            "no tickers resolved from any source (env=%r, watchlist empty, default empty); refusing to run",
            tickers_env,
        )
        return 1

    # Cap the batch size to prevent the 152-ticker accident class. The
    # default cap (DEFAULT_MAX_BATCH) is comfortable for the daily 3
    # plus a small ad-hoc add (e.g. SPY/IWM/QQQ + AVGO + MSFT). Anything
    # larger needs an explicit opt-in via INSIGHT_BATCH_OVERRIDE=1.
    try:
        max_batch = int(os.environ.get("INSIGHT_MAX_BATCH", str(DEFAULT_MAX_BATCH)))
    except ValueError:
        max_batch = DEFAULT_MAX_BATCH
    override = os.environ.get("INSIGHT_BATCH_OVERRIDE", "").lower() in ("1", "true", "yes")

    if len(tickers) > max_batch and not override:
        logger.error(
            "refusing to run %d tickers (cap=%d). Set INSIGHT_BATCH_OVERRIDE=1 to bypass. tickers=%s",
            len(tickers), max_batch, tickers,
        )
        return 1

    trigger = classify_trigger(tickers)
    logger.info(
        "scheduled run starting: trigger=%s source=%s ticker_count=%d max_batch=%d override=%s as_of=%s tickers=%s",
        trigger, ticker_source, len(tickers), max_batch, override, as_of, tickers,
    )

    allow_update, run_kind = _resolve_run_kind_and_update(allow_update_arg)
    triggered_by = os.environ.get('INSIGHT_TRIGGERED_BY')

    # Fan out unless disabled, unless there is only one ticker (a lone
    # ticker would pay a container start to save nothing), or unless the
    # batch is larger than FANOUT_MAX_TICKERS.
    pending: Optional[list[tuple[str, str]]] = None
    if _fanout_enabled() and len(tickers) > FANOUT_MAX_TICKERS:
        logger.warning(
            "fan-out skipped: %d tickers exceeds FANOUT_MAX_TICKERS=%d; "
            "running in-process so the batch cannot launch that many "
            "concurrent executions at the LLM provider",
            len(tickers), FANOUT_MAX_TICKERS,
        )
    elif _fanout_enabled() and len(tickers) > 1:
        pending = _dispatch_fanout(
            tickers, trigger=trigger, as_of=as_of,
            force_update=_update_explicitly_requested(allow_update_arg),
            triggered_by=triggered_by,
        )
        if pending:
            logger.warning(
                "Cloud Tasks enqueue failed for %d of %d ticker(s) (%s) - "
                "running those in-process so the batch still completes",
                len(pending), len(tickers), ",".join(t for _, t in pending),
            )

    any_failures = False
    if pending is None:
        # Sequential mode: insert each run row immediately before
        # executing it, as this job did before fan-out existed.
        for ticker in tickers:
            run_id = _insert_run(ticker, trigger=trigger)
            ok = await _run_one(
                run_id, ticker, as_of=as_of,
                allow_update=allow_update, run_kind=run_kind,
                triggered_by=triggered_by,
            )
            if not ok:
                any_failures = True
    else:
        # Enqueue-failure fallback: rows already exist, reuse their ids.
        for run_id, ticker in pending:
            ok = await _run_one(
                run_id, ticker, as_of=as_of,
                allow_update=allow_update, run_kind=run_kind,
                triggered_by=triggered_by,
            )
            if not ok:
                any_failures = True
    # Scheduled runs exit 0 even on partial failure — one ticker's
    # failure shouldn't block the other two from being reported as
    # "done" to Cloud Scheduler. The insight_runs table carries the
    # per-ticker error text for the admin to investigate.
    #
    # Under fan-out this exit code covers DISPATCH only: the children
    # run in their own executions and report their own status, so a
    # green dispatcher no longer implies three written reports. Per
    # ticker state lives in insight_runs either way.
    if any_failures:
        logger.warning("scheduled run completed with at least one failure")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description='Run the AI insight pipeline (orchestrator) and '
                    'persist insight_reports + history.')
    parser.add_argument(
        '--update', action='store_true',
        help="Allow overwriting today's canonical insight_reports row. "
             "Without this, re-runs only append to "
             "insight_reports_history; the current row is protected. "
             "Equivalent to INSIGHT_UPDATE=true env var. Implied "
             "when INSIGHT_AS_OF is set (replay).",
    )
    args = parser.parse_args(argv)

    if os.environ.get("INSIGHT_RUN_ID"):
        return asyncio.run(_run_on_demand(allow_update_arg=args.update))
    return asyncio.run(_run_scheduled(allow_update_arg=args.update))


if __name__ == "__main__":
    sys.exit(main())
