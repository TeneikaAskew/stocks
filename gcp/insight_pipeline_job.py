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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional, Union
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

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
) -> None:
    conn = connect()
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
    conn = connect()
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


async def _run_one(
    run_id: str,
    ticker: str,
    as_of: Optional[Union[date, datetime]] = None,
) -> bool:
    """Execute one pipeline run and persist transitions. Returns True
    on success.

    ``as_of`` (when provided) freezes every summarizer to the data
    available at that cutoff — daily bars, options snapshots, news,
    catalysts. The orchestrator threads it through unchanged.
    """
    logger.info(
        "[run_id=%s] starting pipeline for %s%s",
        run_id, ticker,
        f" as_of={as_of}" if as_of else "",
    )
    _transition(run_id, "running")
    try:
        snapshot = load_routes_snapshot()
        report = await run_insight_pipeline(ticker, as_of=as_of, snapshot=snapshot)
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
    try:
        as_of = parse_as_of(os.environ.get("INSIGHT_AS_OF"))
    except ValueError as exc:
        logger.error("INSIGHT_AS_OF invalid: %s", exc)
        return 1
    ok = await _run_one(run_id, ticker, as_of=as_of)
    return 0 if ok else 1


async def _run_scheduled() -> int:
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
            from gcp.fetchers._watchlist import load_watchlist
            tickers = load_watchlist()
            ticker_source = "watchlists table"
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

    any_failures = False
    for ticker in tickers:
        run_id = _insert_run(ticker, trigger=trigger)
        ok = await _run_one(run_id, ticker, as_of=as_of)
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
