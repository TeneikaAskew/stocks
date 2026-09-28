"""One-shot: backfill timeframe_tag + expected_hold_min on historical_signals.

Phase 1 added the columns and the live signal-monitor populates them
on every NEW fire. This script handles the historical rows that
already existed when the column was added — without it, downstream
consumers (weekly QA report, Phase 2 cooldown logic) hit NULLs on
every old row.

Approach:
  1. SELECT rows with timeframe_tag IS NULL, joining signal_metrics
     for atr_5m_pct context.
  2. Apply lib.strategies.timeframe.assign_timeframe_for_backfill —
     a documented-approximate helper that uses only the fields
     available retrospectively (strategy, signal_strength, ATR).
  3. Bulk UPDATE in chunks of 1000.

Idempotent: re-runs only touch rows where timeframe_tag IS NULL.
Re-running on already-tagged rows is a no-op.

--retag rewrites existing tags too, after the tagging rule changes (#1167
retired EMPIRICAL_LOOKUP). It selects every row, computes the current rule's
tag and writes only the rows whose (timeframe_tag, expected_hold_min) changes.

Capacity (per CLAUDE.md Rule 0):
  * Volume:   one SELECT (joined), 1000-row UPDATE batches
  * Velocity: ~92 batches for the original 91k-row backlog; a --retag of
              the ~245k-row table (2026-09) is at most ~245, fewer when tags
              are unchanged
  * Wall-clock: 0.5-2 s per batch round trip, so under 10 minutes
  * Memory:   <100MB
  * Cost:     $0 (DB-only, no API calls)

Usage:
    python -m scripts.backfill_timeframe_tags
    python -m scripts.backfill_timeframe_tags --tickers SPY,QQQ
    python -m scripts.backfill_timeframe_tags --dry-run
    python -m scripts.backfill_timeframe_tags --retag --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.strategies.timeframe import assign_timeframe_for_backfill  # noqa: E402

logger = logging.getLogger(__name__)


def fetch_rows_to_backfill(
    engine, tickers: Optional[list[str]] = None, limit: Optional[int] = None,
    retag: bool = False,
) -> pd.DataFrame:
    """Pull historical_signals rows missing timeframe_tag (or, with
    `retag`, every row, with its current tag as old_tag/old_hold), joined
    with signal_metrics for ATR context. signal_metrics may be missing for
    some rows (older or status='pending') — those get NULL atr_5m_pct
    and the backfill helper falls through to the strategy default."""
    from sqlalchemy import text

    where = [] if retag else ["h.timeframe_tag IS NULL"]
    params: dict = {}
    if tickers:
        where.append("h.ticker = ANY(:tickers)")
        params["tickers"] = [t.upper() for t in tickers]

    sql = text(f"""
        SELECT h.ticker,
               h.entry_time,
               h.strategy,
               h.signal_strength,
               h.entry_rsi,
               m.atr_5m_pct,
               h.timeframe_tag AS old_tag,
               h.expected_hold_min AS old_hold
          FROM historical_signals h
          LEFT JOIN signal_metrics m
            ON m.ticker = h.ticker
           AND m.entry_time = h.entry_time
           AND m.strategy = h.strategy
         {('WHERE ' + ' AND '.join(where)) if where else ''}
         ORDER BY h.entry_time
         {'LIMIT :limit' if limit else ''}
    """)
    if limit:
        params["limit"] = limit

    return pd.read_sql(sql, engine, params=params)


def apply_tags(df: pd.DataFrame) -> pd.DataFrame:
    """Compute (timeframe_tag, expected_hold_min) for every row using
    the backfill-specific helper. Pure; no DB."""
    if df.empty:
        return df

    tags = []
    holds = []
    for _, row in df.iterrows():
        atr = row.get("atr_5m_pct")
        if atr is not None and pd.isna(atr):
            atr = None
        rsi = row.get("entry_rsi")
        if rsi is not None and pd.isna(rsi):
            rsi = None
        tag, hold = assign_timeframe_for_backfill(
            strategy=row.get("strategy"),
            signal_strength=int(row.get("signal_strength") or 0),
            atr_5m_pct=float(atr) if atr is not None else None,
            entry_rsi=float(rsi) if rsi is not None else None,
        )
        tags.append(tag)
        holds.append(hold)

    df = df.copy()
    df["timeframe_tag"] = tags
    df["expected_hold_min"] = holds
    return df


def changed_rows(df: pd.DataFrame) -> pd.DataFrame:
    """The rows whose computed (timeframe_tag, expected_hold_min) differs
    from what is stored (old_tag, old_hold). An untagged row counts as
    changed. Pure; no DB."""
    if df.empty:
        return df
    old_hold = pd.to_numeric(df["old_hold"], errors="coerce")
    same = (df["old_tag"] == df["timeframe_tag"]) & (old_hold == df["expected_hold_min"])
    return df[~same.fillna(False)]


def upsert_chunk(engine, chunk: pd.DataFrame) -> int:
    """Bulk UPDATE one chunk via multi-row VALUES + JOIN.

    Issues a single network round-trip per chunk via UPDATE...FROM.

    Type-binding subtlety (pg8000 / SQLAlchemy):
      Without explicit bindparam types, pg8000 sends every parameter
      as text. The VALUES clause then infers a `text` column type
      for entry_time, and the JOIN against historical_signals.entry_time
      (TIMESTAMPTZ) fails with:
          operator does not exist: timestamp with time zone = text

      Adding `CAST(:e0 AS timestamptz)` in the SQL doesn't fix it
      because pg8000's prepared-statement type inference happens
      BEFORE the CAST is parsed. Casting on the alias side
      (`v.entry_time::timestamptz`) confuses SQLAlchemy's
      named-parameter rewriter.

      The actual fix: use SQLAlchemy `bindparam(name, type_=...)`
      to declare each parameter's type. SQLAlchemy then tells pg8000
      to send the value with the right OID, and Postgres infers the
      VALUES column type correctly. Verified working against Cloud
      SQL with native datetime objects.
    """
    if chunk.empty:
        return 0
    from sqlalchemy import text, bindparam
    from sqlalchemy.types import TIMESTAMP, String, Integer

    rows = chunk.to_dict(orient="records")
    value_tuples: list[str] = []
    bind_specs: list = []
    params: dict = {}
    for i, r in enumerate(rows):
        # Native datetime — Pandas Timestamp inherits from datetime,
        # so SQLAlchemy's TIMESTAMP type sends it as a real timestamp.
        et = r["entry_time"]
        params[f"t{i}"]  = r["ticker"]
        params[f"e{i}"]  = et
        params[f"s{i}"]  = r["strategy"]
        params[f"tf{i}"] = r["timeframe_tag"]
        params[f"hm{i}"] = r["expected_hold_min"]
        bind_specs.extend([
            bindparam(f"t{i}",  type_=String()),
            bindparam(f"e{i}",  type_=TIMESTAMP(timezone=True)),
            bindparam(f"s{i}",  type_=String()),
            bindparam(f"tf{i}", type_=String()),
            bindparam(f"hm{i}", type_=Integer()),
        ])
        value_tuples.append(
            f"(:t{i}, :e{i}, :s{i}, :tf{i}, :hm{i})"
        )

    sql = text(f"""
        UPDATE historical_signals h
           SET timeframe_tag      = v.timeframe_tag,
               expected_hold_min  = v.expected_hold_min
          FROM (VALUES {', '.join(value_tuples)})
            AS v(ticker, entry_time, strategy, timeframe_tag, expected_hold_min)
         WHERE h.ticker = v.ticker
           AND h.entry_time = v.entry_time
           AND h.strategy = v.strategy
    """).bindparams(*bind_specs)

    with engine.begin() as conn:
        result = conn.execute(sql, params)
    return result.rowcount or 0


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--tickers", default="",
                   help="Comma-separated ticker filter (default: all)")
    p.add_argument("--limit", type=int, default=None,
                   help="Limit rows for staged rollout / dev (with --retag: rows written, "
                        "counted after unchanged rows are filtered out)")
    p.add_argument("--chunk-size", type=int, default=1000,
                   help="Rows per UPDATE batch (default 1000)")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute tags but skip the UPDATE")
    p.add_argument("--retag", action="store_true",
                   help="Rewrite existing tags too, writing only rows whose tag changes "
                        "(after a change to the tagging rule, #1167)")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    args = parse_args(argv)

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or None

    from gcp.database import get_engine
    engine = get_engine()

    logger.info("loading rows to backfill (tickers=%s limit=%s retag=%s)",
                tickers, args.limit, args.retag)
    # With --retag the limit bounds the rows a run writes, applied after the
    # unchanged ones are filtered out: a SQL LIMIT would select the same
    # already-current rows on every staged run (Codex on #1207).
    df = fetch_rows_to_backfill(engine, tickers=tickers,
                                limit=None if args.retag else args.limit, retag=args.retag)
    logger.info("loaded %d rows", len(df))
    if df.empty:
        logger.info("nothing to backfill")
        return 0

    df = apply_tags(df)
    distribution = df["timeframe_tag"].value_counts().to_dict()
    logger.info("timeframe distribution: %s", distribution)
    if args.retag:
        selected = len(df)
        df = changed_rows(df)
        transitions = (df["old_tag"].fillna("NULL") + " -> " + df["timeframe_tag"]).value_counts().to_dict()
        logger.info("retag: %d rows selected, %d change: %s", selected, len(df), transitions)
        if df.empty:
            logger.info("nothing to retag")
            return 0
        if args.limit:
            df = df.head(args.limit)
            logger.info("retag: --limit %d, writing the first %d changed rows", args.limit, len(df))

    if args.dry_run:
        logger.info("--dry-run set — skipping UPDATE (%d rows ready)", len(df))
        return 0

    total = 0
    for start in range(0, len(df), args.chunk_size):
        chunk = df.iloc[start: start + args.chunk_size]
        n = upsert_chunk(engine, chunk)
        total += n
        logger.info("chunk %d-%d: updated %d rows (running total %d)",
                    start, start + len(chunk), n, total)
    logger.info("DONE updated=%d", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
