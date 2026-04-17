#!/usr/bin/env python3
"""
Generate AI Insight reports for historical dates.

Calls lib.agents.orchestrator.run_insight_pipeline with an explicit
`as_of` so the summarizers look at the state that existed on that
date rather than today. The resulting InsightReport is upserted into
the `insight_reports` Cloud SQL table keyed by (ticker, as_of) and
appears immediately in the platform's History tab.

Usage:
    set -a && source .env && set +a

    # One ticker, one day
    python scripts/generate_historical_report.py --ticker SPY --date 2025-10-15

    # Backfill a date range (weekdays only)
    python scripts/generate_historical_report.py --ticker SPY \\
        --from 2025-10-01 --to 2025-10-31

    # Multiple tickers, one day
    python scripts/generate_historical_report.py \\
        --ticker SPY,IWM,QQQ --date 2025-10-15

Costs roughly $0.002 per report at default Gemini Flash routing.
A 20-weekday month across 3 tickers is about $0.12.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
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
logger = logging.getLogger("historical-report")


def _upsert_report(report: InsightReport) -> str:
    """Store the report. Returns the row id. Copy of the helper in
    platform.api.routers.insights so this script has no FastAPI
    dependency."""
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


def _weekdays_in_range(start: date, end: date) -> list[date]:
    """Inclusive range of weekdays (Mon-Fri) between start and end."""
    out: list[date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # 0=Monday, 4=Friday
            out.append(d)
        d += timedelta(days=1)
    return out


async def _generate_one(ticker: str, as_of: date, snapshot) -> None:
    logger.info("[%s %s] starting pipeline", ticker, as_of)
    try:
        report = await run_insight_pipeline(ticker, as_of=as_of, snapshot=snapshot)
    except Exception as exc:
        logger.exception("[%s %s] pipeline failed: %s", ticker, as_of, exc)
        return
    row_id = _upsert_report(report)
    logger.info(
        "[%s %s] done  id=%s  dir=%s  conv=%s  cost=$%.4f  latency=%dms  failed=%s",
        ticker,
        as_of,
        row_id,
        report.direction,
        report.conviction,
        report.run_cost_usd,
        report.run_latency_ms,
        report.failed_sections or "-",
    )


async def _main_async(args: argparse.Namespace) -> int:
    tickers = [t.strip().upper() for t in args.ticker.split(",") if t.strip()]
    if not tickers:
        logger.error("no tickers specified")
        return 1

    if args.date:
        days = [datetime.strptime(args.date, "%Y-%m-%d").date()]
    else:
        start = datetime.strptime(args.from_date, "%Y-%m-%d").date()
        end = datetime.strptime(args.to_date, "%Y-%m-%d").date()
        if end < start:
            logger.error("--to is before --from")
            return 1
        days = _weekdays_in_range(start, end)

    logger.info("generating %d reports (%d tickers x %d days)", len(tickers) * len(days), len(tickers), len(days))
    snapshot = load_routes_snapshot()
    for d in days:
        for ticker in tickers:
            await _generate_one(ticker, d, snapshot)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ticker", required=True, help="Comma-separated tickers (e.g. SPY or SPY,IWM,QQQ)")
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument("--date", help="Single date in YYYY-MM-DD")
    date_group.add_argument("--from", dest="from_date", help="Start date (inclusive, YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", help="End date (inclusive, YYYY-MM-DD)")
    args = parser.parse_args()

    if args.from_date and not args.to_date:
        parser.error("--from requires --to")
    if args.to_date and not args.from_date:
        parser.error("--to requires --from")

    try:
        return asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        logger.info("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
