"""Build / refresh `intraday_flow_15m` — the MATERIALIZED per-15m-bucket
order-flow imbalance aggregates (signed_vol / tot_vol / up_vol / dn_vol / n_min)
per ticker × 15m bar.

RULE 0 (NON-NEGOTIABLE): this Job is the ONLY place `market_data_intraday` is
scanned for the intraday-flow feature block. The per-experiment loader
(`lib.features.intraday_flow.add_intraflow_features`) reads the ~6.5k-rows/yr
materialized table instead, so experiments never re-aggregate the ~2M-row/ticker
1-min table (same discipline as the etf_options_daily_greeks build, which was
created after the 2026-06-05 shared-DB-starvation incident).

Design (per CLAUDE.md Rule 0):
  * ONE ticker at a time (no concurrent full scans of the shared DB).
  * Aggregation pushed into SQL + chunked by year inside compute_intraflow_frame.
  * Idempotent + RESUMABLE: ON CONFLICT (ticker, ts) DO UPDATE, and `--backfill`
    resumes from the gap after the last materialized bucket per ticker, so a run
    cut short by a timeout/crash continues instead of restarting from 2015. The
    durable materialized rows ARE the checkpoint; no separate state to manage.
  * Fast upsert: the whole per-ticker frame is written via one COPY → temp →
    INSERT…ON CONFLICT (`gcp.database.bulk_copy_upsert`), not a per-row loop —
    10-30× faster, which is what makes a full re-run cheap.
  * Observable: per-ticker upsert counts + per-year scan timings.
  * Bounded memory: each ticker's bucket frame is ~83k rows; written per ticker.

Modes:
  --backfill [--restart]     resume the full-history build (since 2015-01-01)
                             from the gap; --restart forces a clean recompute.
  --incremental [--days N]   recompute the last N days (default 7) — run on a
                             scheduler AFTER the intraday bars land.
  --ticker T                 restrict to one ticker (default: IWM,SPY,QQQ).

Examples:
  python -m gcp.build_intraday_flow --backfill            # resume from the gap
  python -m gcp.build_intraday_flow --backfill --restart  # full recompute
  python -m gcp.build_intraday_flow --incremental --days 7
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger(__name__)

TICKERS = ("IWM", "SPY", "QQQ")
BACKFILL_SINCE = "2015-01-01"


def upsert_intraflow(engine, ticker: str, frame: pd.DataFrame) -> int:
    """Idempotent per-bucket upsert via the COPY → temp → INSERT…ON CONFLICT fast
    path (`gcp.database.bulk_copy_upsert`). frame is indexed by ts with the raw
    aggregate columns; returns rows written.

    Why not a per-row loop: the previous implementation looped
    `conn.execute(sql, row)` once per bucket (~530k INSERT round-trips for a full
    backfill, ~70 min). `bulk_copy_upsert` streams the whole frame in one COPY
    (its docstring: 10-30× faster) and falls back to a multi-row INSERT if the
    COPY path errors. NaN stays NULL via CSV `\\N` (no fabricated 0, §3.7);
    `computed_at` falls to its schema DEFAULT NOW().
    """
    import gcp.database as db
    if frame is None or frame.empty:
        return 0
    out = frame.reset_index()                    # ts index -> column
    out.insert(0, "ticker", ticker)
    return db.bulk_copy_upsert(
        out, "intraday_flow_15m",
        conflict_cols=["ticker", "ts"],
        update_cols=["signed_vol", "tot_vol", "up_vol", "dn_vol", "n_min"],
    )


def _resume_since(engine, ticker: str, default_since: str) -> str:
    """Return the date to (re)start the scan from so a re-run does NOT recompute
    buckets already durably written — it picks up at the gap.

    Strategy: the day of the last materialized bucket for `ticker`, minus one
    day. Backing up a day re-fills any partially-written final day AND restores
    the tick-rule `lag(close)` context at the scan boundary; the upsert is
    idempotent (ON CONFLICT) so the one-day overlap is harmless. Returns
    `default_since` when the table has no rows for this ticker yet (fresh start).
    """
    from sqlalchemy import text
    with engine.connect() as conn:
        last = conn.execute(
            text("SELECT max(ts) FROM intraday_flow_15m WHERE ticker = :tk"),
            {"tk": ticker},
        ).scalar()
    if last is None:
        return default_since
    resume = (pd.Timestamp(last).date() - timedelta(days=1)).isoformat()
    return max(default_since, resume)


def build(engine, tickers, since: str, until: str, resume: bool = False) -> dict:
    """Compute + upsert intraday OFI buckets for each ticker SEQUENTIALLY.

    When `resume` is True, each ticker's scan starts at the gap after the last
    already-materialized bucket (see `_resume_since`) instead of `since`, so a
    re-run after a timeout/crash does not recompute completed history. The
    upsert is idempotent, so resume is always safe to enable.
    """
    from lib.features.intraday_flow import compute_intraflow_frame
    written = {}
    for tk in tickers:
        tk_since = _resume_since(engine, tk, since) if resume else since
        log.info("=" * 70)
        if resume and tk_since != since:
            log.info("RESUME ticker=%s: completed history present; scanning gap "
                     "from %s (skipping %s..%s)", tk, tk_since, since, tk_since)
        log.info("build-intraday-flow ticker=%s window=[%s..%s]", tk, tk_since, until)
        frame = compute_intraflow_frame(engine, tk, tk_since, until)
        n = upsert_intraflow(engine, tk, frame)
        written[tk] = n
        log.info("build-intraday-flow ticker=%s upserted=%d buckets "
                 "(signed_vol non-null=%d)", tk, n,
                 int(frame["signed_vol"].notna().sum()) if not frame.empty else 0)
    log.info("=" * 70)
    log.info("build-intraday-flow DONE: %s", written)
    return written


def main():
    from gcp.database import get_engine
    from lib.logging_config import setup_logging
    setup_logging()

    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backfill", action="store_true",
                      help="recompute ALL history since " + BACKFILL_SINCE)
    mode.add_argument("--incremental", action="store_true",
                      help="recompute the last --days days")
    p.add_argument("--days", type=int, default=7,
                   help="incremental lookback in days (default 7)")
    p.add_argument("--ticker", default=None, choices=list(TICKERS),
                   help="restrict to one ticker (default: all)")
    p.add_argument("--restart", action="store_true",
                   help="(backfill only) ignore already-written rows and "
                        "recompute ALL history from scratch; the default is to "
                        "RESUME from the gap after the last materialized bucket")
    args = p.parse_args()

    tickers = (args.ticker,) if args.ticker else TICKERS
    until = date.today().isoformat()
    since = (BACKFILL_SINCE if args.backfill
             else (date.today() - timedelta(days=args.days)).isoformat())

    # Resume is the default for --backfill (a re-run picks up where a prior run
    # stopped); --restart forces a full recompute. --incremental already bounds
    # its own window via --days, so it scans that window verbatim.
    resume = bool(args.backfill) and not args.restart

    engine = get_engine()
    build(engine, tickers, since, until, resume=resume)


if __name__ == "__main__":
    main()
