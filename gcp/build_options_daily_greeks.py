"""Build / refresh `etf_options_daily_greeks` — the MATERIALIZED daily
directional-greek aggregates (dex / short_dte_dex / total_oi / vanna / charm)
per ticker × EOD day.

RULE 0 (NON-NEGOTIABLE): this Job is the ONLY place `etf_options_snapshots` is
scanned for flow features. The per-experiment loader
(`lib.features.flow_direction.add_flow_features`) reads the ~250-rows/yr
materialized table instead, so experiments never re-aggregate the ~14M-row
snapshots table (the 2026-06-05 incident: 5 concurrent runs, 100-900s/year-chunk,
shared-DB starvation).

Design (per CLAUDE.md Rule 0):
  * ONE ticker at a time (no concurrent full scans of the shared DB).
  * Aggregation chunked by year inside compute_daily_greeks_frame.
  * Idempotent: ON CONFLICT (ticker, snapshot_date) DO UPDATE — a re-run after a
    partial failure converges, never duplicates.
  * Observable: per-ticker upsert counts + per-year scan timings (logged by the
    flow_direction loaders).
  * Bounded memory: each ticker's daily frame is ~2500 rows; written before the
    next ticker.

Modes:
  --backfill                 recompute ALL history (since 2016-01-01).
  --incremental [--days N]   recompute the last N days (default 7) — run on a
                             scheduler AFTER the EOD options fetch lands.
  --ticker T                 restrict to one ticker (default: IWM,SPY,QQQ).

Examples:
  python -m gcp.build_options_daily_greeks --backfill --ticker IWM
  python -m gcp.build_options_daily_greeks --incremental --days 7
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger(__name__)

TICKERS = ("IWM", "SPY", "QQQ")
BACKFILL_SINCE = "2016-01-01"

# Built out-of-band (not in schema.sql) because a transactional CREATE INDEX on
# the ~14M-row table locks it and exceeds the statement timeout. CONCURRENTLY +
# AUTOCOMMIT builds it without a long lock; IF NOT EXISTS makes it idempotent.
_INDEX_DDL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_etf_options_eod_agg
    ON etf_options_snapshots (ticker, snapshot_date)
    INCLUDE (delta, open_interest, expiration, implied_volatility,
             option_type, strike)
    WHERE market_session = 'EOD' AND data_source = 'alphavantage'
"""

_UPSERT_SQL = """
INSERT INTO etf_options_daily_greeks
    (ticker, snapshot_date, dex, short_dte_dex, total_oi, vanna, charm,
     n_contracts, computed_at)
VALUES
    (:ticker, :snapshot_date, :dex, :short_dte_dex, :total_oi, :vanna, :charm,
     :n_contracts, NOW())
ON CONFLICT (ticker, snapshot_date) DO UPDATE SET
    dex           = EXCLUDED.dex,
    short_dte_dex = EXCLUDED.short_dte_dex,
    total_oi      = EXCLUDED.total_oi,
    vanna         = EXCLUDED.vanna,
    charm         = EXCLUDED.charm,
    n_contracts   = EXCLUDED.n_contracts,
    computed_at   = NOW()
"""


def _none(v):
    """NaN/NaT -> None so psycopg/pg8000 binds SQL NULL (no fabricated 0)."""
    if v is None:
        return None
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    return v


def upsert_daily_greeks(engine, ticker: str, frame: pd.DataFrame) -> int:
    """Idempotent per-day upsert. frame is indexed by snapshot_date with the
    table columns. Returns rows written."""
    from sqlalchemy import text
    if frame is None or frame.empty:
        return 0
    rows = []
    for d, r in frame.iterrows():
        rows.append({
            "ticker": ticker,
            "snapshot_date": d,
            "dex": _none(float(r["dex"]) if pd.notna(r["dex"]) else np.nan),
            "short_dte_dex": _none(float(r["short_dte_dex"])
                                   if pd.notna(r["short_dte_dex"]) else np.nan),
            "total_oi": _none(float(r["total_oi"])
                              if pd.notna(r["total_oi"]) else np.nan),
            "vanna": _none(float(r["vanna"]) if pd.notna(r["vanna"]) else np.nan),
            "charm": _none(float(r["charm"]) if pd.notna(r["charm"]) else np.nan),
            "n_contracts": int(r["n_contracts"]) if pd.notna(r["n_contracts"]) else 0,
        })
    sql = text(_UPSERT_SQL)
    with engine.begin() as conn:  # one transaction per ticker (atomic, idempotent)
        for row in rows:
            conn.execute(sql, row)
    return len(rows)


def build_index(engine) -> None:
    """Create the EOD covering index CONCURRENTLY (no long lock, no transaction).
    Idempotent via IF NOT EXISTS. CONCURRENTLY is illegal inside a transaction,
    so we force an AUTOCOMMIT connection."""
    log.info("build-index: CREATE INDEX CONCURRENTLY idx_etf_options_eod_agg "
             "(this scans the EOD/alphavantage slice; may take many minutes)...")
    raw = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        raw.exec_driver_sql(_INDEX_DDL)
        log.info("build-index: done (idx_etf_options_eod_agg present)")
    finally:
        raw.close()  # cleanup — original error already propagated


def build(engine, tickers, since: str, until: str) -> dict:
    """Compute + upsert daily greeks for each ticker SEQUENTIALLY."""
    from lib.features.flow_direction import compute_daily_greeks_frame
    written = {}
    for tk in tickers:
        log.info("=" * 70)
        log.info("build-options-greeks ticker=%s window=[%s..%s]", tk, since, until)
        frame = compute_daily_greeks_frame(engine, tk, since, until)
        n = upsert_daily_greeks(engine, tk, frame)
        written[tk] = n
        log.info("build-options-greeks ticker=%s upserted=%d days "
                 "(dex non-null=%d, vanna non-null=%d)", tk, n,
                 int(frame["dex"].notna().sum()) if not frame.empty else 0,
                 int(frame["vanna"].notna().sum()) if not frame.empty else 0)
    log.info("=" * 70)
    log.info("build-options-greeks DONE: %s", written)
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
    mode.add_argument("--build-index", action="store_true",
                      help="build the EOD covering index CONCURRENTLY (one-off)")
    p.add_argument("--days", type=int, default=7,
                   help="incremental lookback in days (default 7)")
    p.add_argument("--ticker", default=None, choices=list(TICKERS),
                   help="restrict to one ticker (default: all)")
    args = p.parse_args()

    tickers = (args.ticker,) if args.ticker else TICKERS
    until = date.today().isoformat()
    since = (BACKFILL_SINCE if args.backfill
             else (date.today() - timedelta(days=args.days)).isoformat())

    engine = get_engine()
    if args.build_index:
        build_index(engine)
        return
    build(engine, tickers, since, until)


if __name__ == "__main__":
    main()
