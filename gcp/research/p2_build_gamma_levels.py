#!/usr/bin/env python3
"""Phase 2 Step 1: Build per-(ticker, date) gamma levels table from EOD chains.

Pre-computes Kings / Gates / Flip for every (ticker, date) in the
SPY/IWM/QQQ 10-year window, sourced from `etf_options_snapshots` with
`data_source='alphavantage'` (the long-history EOD source).

The resulting `gamma_levels_eod` table feeds Phase 2 Step 2 (outcome
grid) — instead of recomputing levels per bar, that job joins each
bar to the *prior day's* levels (which is exactly what production's
live `signal_monitor._latest_gamma_for_ticker_pure` returns at session
start, no leakage).

Why a separate table vs computing on-the-fly: the chain itself is
~46M rows; we only need the ~5-10 levels per (ticker, date) for
downstream queries. Pre-aggregating turns the bar-level join from
"O(M log N) over 46M rows" into "O(M) over ~40k rows" — and lets
the next job iterate the bars without ever re-touching the chain.

Schema:
    CREATE TABLE gamma_levels_eod (
      ticker          VARCHAR(16) NOT NULL,
      snapshot_date   DATE        NOT NULL,
      level_kind      VARCHAR(20) NOT NULL,  -- 'king' | 'gate' | 'gamma_balance'
      level_strike    NUMERIC(12,4) NOT NULL,
      gex             DOUBLE PRECISION,
      net_gamma       DOUBLE PRECISION,
      score           DOUBLE PRECISION,
      tags            TEXT,                  -- comma-joined tag list
      regime          VARCHAR(20),           -- positive_gamma | negative_gamma | unknown
      total_gex       DOUBLE PRECISION,
      gamma_balance_price DOUBLE PRECISION,  -- cumulative-net-gamma balance price
      gamma_flip      DOUBLE PRECISION,      -- true BS-recurved zero-gamma level
      spot_estimate   DOUBLE PRECISION,
      spot_method     VARCHAR(20),
      n_strikes_in_window INT,
      computed_at     TIMESTAMPTZ DEFAULT now(),
      PRIMARY KEY (ticker, snapshot_date, level_kind, level_strike)
    );

Usage (Cloud Run Job):
    gcloud run jobs execute p2-build-gamma-levels --region=us-east1 \\
      --args="--tickers=SPY,IWM,QQQ" --wait

Per-PR Rule 0 capacity math:
- Volume: 3 tickers × ~2,861 dates × ~5 levels each = ~43k inserts
- Velocity: 1 batched SELECT per (ticker, quarter) = 144 fetches;
  1 batched INSERT per (ticker) = 3 inserts; in-memory groupby
  is O(rows)
- Wall-clock: per-ticker quarter pull ~5s (DB round-trip + transfer),
  build_summary ~30ms × 2861 dates = ~90s, batched insert ~5s.
  Total ~5-10 min per ticker × 3 = ~15-30 min wall-clock.
- task-timeout: 1800s (30 min) = 1× wall-clock estimate; safe.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date as _date
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import execute_sql, get_engine, upsert_dataframe
from lib.gamma import build_summary
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

TICKERS_DEFAULT = ["SPY", "IWM", "QQQ"]


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS gamma_levels_eod (
    ticker          VARCHAR(16)  NOT NULL,
    snapshot_date   DATE         NOT NULL,
    level_kind      VARCHAR(20)  NOT NULL,
    level_strike    NUMERIC(12,4) NOT NULL,
    gex             DOUBLE PRECISION,
    net_gamma       DOUBLE PRECISION,
    score           DOUBLE PRECISION,
    tags            TEXT,
    regime          VARCHAR(20),
    total_gex       DOUBLE PRECISION,
    gamma_balance_price DOUBLE PRECISION,
    gamma_flip      DOUBLE PRECISION,
    spot_estimate   DOUBLE PRECISION,
    spot_method     VARCHAR(20),
    n_strikes_in_window INT,
    computed_at     TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, snapshot_date, level_kind, level_strike)
);
CREATE INDEX IF NOT EXISTS ix_gamma_levels_ticker_date
    ON gamma_levels_eod (ticker, snapshot_date);
"""


def _load_chain_for_ticker_quarter(engine, ticker: str, year: int, q: int) -> pd.DataFrame:
    """Pull one ticker × one calendar quarter of EOD chain rows from Cloud SQL.

    Uses SQLAlchemy text() with :name binds — pg8000 only accepts %s or %s-style,
    not psycopg2's %(name)s pyformat, so we route through SQLAlchemy.
    """
    from sqlalchemy import text
    q_start = pd.Timestamp(year, (q - 1) * 3 + 1, 1).date()
    q_end_dt = pd.Timestamp(year, (q - 1) * 3 + 1, 1) + pd.offsets.QuarterEnd()
    q_end = q_end_dt.date()
    sql = text("""
    SELECT
        snapshot_date,
        contract_symbol,
        option_type,
        expiration,
        strike,
        bid, ask, mark, last_price,
        volume, open_interest,
        implied_volatility,
        delta, gamma, theta, vega, rho,
        underlying_price
    FROM etf_options_snapshots
    WHERE ticker = :ticker
      AND data_source = 'alphavantage'
      AND market_session = 'EOD'
      AND snapshot_date BETWEEN :start AND :end
    """)
    with engine.connect() as conn:
        df = pd.read_sql(
            sql, conn,
            params={"ticker": ticker, "start": q_start, "end": q_end},
        )
    return df


def _chain_rows_to_options_list(rows: pd.DataFrame) -> list[dict]:
    """Convert a per-day chain DataFrame slice into lib.gamma's options-list shape.

    Field-name mapping caught 2026-05-23 after first execution produced 0
    levels: lib.gamma expects 'type' = 'call'/'put' (singular), 'last' (not
    'last_price'); etf_options_snapshots stores 'option_type' = 'calls'/
    'puts' (plural) and 'last_price'. We translate before passing.
    """
    df = rows.copy()
    # Map option_type -> type (singular 'call'/'put')
    df["type"] = df["option_type"].map({"calls": "call", "puts": "put"})
    # Map last_price -> last
    if "last_price" in df.columns:
        df["last"] = df["last_price"]
    return df.to_dict("records")


def _process_one_day(ticker: str, snap_date: _date, chain_rows: pd.DataFrame) -> list[dict]:
    """Build a GammaSummary for one (ticker, date) and emit level rows for insertion.

    Returns [] if the chain is too thin to summarize, or if no kings/gates/flip
    were identified. Empty days are skipped silently — they're a common
    occurrence on holidays/half-days and we don't want them inflating the
    `gamma_levels_eod` row count.
    """
    if chain_rows.empty:
        return []
    options = _chain_rows_to_options_list(chain_rows)
    try:
        summary = build_summary(
            ticker=ticker,
            snapshot_date=str(snap_date),
            options=options,
        )
    except Exception:
        log.exception("build_summary failed for %s %s (n=%d)", ticker, snap_date, len(options))
        return []

    out: list[dict] = []
    common = dict(
        ticker=ticker,
        snapshot_date=snap_date,
        regime=summary.regime,
        total_gex=float(summary.total_gex or 0.0),
        gamma_balance_price=float(summary.gamma_balance) if summary.gamma_balance is not None else None,
        gamma_flip=float(summary.gamma_flip) if summary.gamma_flip is not None else None,
        spot_estimate=float(summary.spot.price) if summary.spot.price else None,
        spot_method=str(summary.spot.method),
        n_strikes_in_window=len(summary.levels),
    )

    for lv in summary.kings:
        out.append({**common,
                    "level_kind": "king",
                    "level_strike": float(lv.strike),
                    "gex": float(lv.gex or 0.0),
                    "net_gamma": float(lv.net_gamma or 0.0),
                    "score": float(lv.score or 0.0),
                    "tags": ",".join(lv.tags or []),
                    })
    for lv in summary.gates:
        out.append({**common,
                    "level_kind": "gate",
                    "level_strike": float(lv.strike),
                    "gex": float(lv.gex or 0.0),
                    "net_gamma": float(lv.net_gamma or 0.0),
                    "score": float(lv.score or 0.0),
                    "tags": ",".join(lv.tags or []),
                    })
    if summary.gamma_balance is not None and float(summary.gamma_balance) > 0:
        out.append({**common,
                    "level_kind": "gamma_balance",
                    "level_strike": float(summary.gamma_balance),
                    "gex": None,
                    "net_gamma": None,
                    "score": None,
                    "tags": "gamma_balance",
                    })

    return out


def _process_ticker(engine, ticker: str, start_year: int, end_year: int) -> int:
    """Iterate one ticker's history quarter-by-quarter, return total rows inserted."""
    log.info("=== %s: processing %d → %d ===", ticker, start_year, end_year)
    total_rows = 0
    t0 = time.time()

    quarters: list[tuple[int, int]] = [
        (y, q) for y in range(start_year, end_year + 1) for q in (1, 2, 3, 4)
    ]
    for (year, q) in quarters:
        qt0 = time.time()
        chain = _load_chain_for_ticker_quarter(engine, ticker, year, q)
        if chain.empty:
            log.info("%s %dQ%d: no chain rows", ticker, year, q)
            continue
        # group by snapshot_date
        rows_to_insert: list[dict] = []
        dates_in_quarter = sorted(chain["snapshot_date"].unique())
        for snap_date in dates_in_quarter:
            day_rows = chain[chain["snapshot_date"] == snap_date]
            rows_to_insert.extend(_process_one_day(ticker, snap_date, day_rows))

        if not rows_to_insert:
            log.info("%s %dQ%d: %d dates, no levels emitted", ticker, year, q, len(dates_in_quarter))
            continue

        df = pd.DataFrame(rows_to_insert)
        # Use ON CONFLICT DO UPDATE so re-runs converge
        upsert_dataframe(
            df, "gamma_levels_eod",
            conflict_cols=["ticker", "snapshot_date", "level_kind", "level_strike"],
            update_cols=["gex", "net_gamma", "score", "tags", "regime",
                         "total_gex", "gamma_balance_price", "gamma_flip",
                         "spot_estimate", "spot_method", "n_strikes_in_window"],
        )
        n = len(df)
        total_rows += n
        log.info("%s %dQ%d: %d dates, %d level rows (%.1fs, chain=%d)",
                 ticker, year, q, len(dates_in_quarter), n,
                 time.time() - qt0, len(chain))

    log.info("=== %s: done — %d level rows in %.1fs ===",
             ticker, total_rows, time.time() - t0)
    return total_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default=",".join(TICKERS_DEFAULT),
                        help="Comma-separated ticker list (default SPY,IWM,QQQ)")
    parser.add_argument("--start-year", type=int, default=_date.today().year,
                        help="First year to (re)build. Default: current year — "
                             "the scheduled nightly run uses default args and so "
                             "only refreshes the current year (~1 min/ticker). "
                             "Pass --start-year=2015 for a full historical backfill.")
    parser.add_argument("--end-year", type=int, default=_date.today().year,
                        help="Last year to (re)build. Default: current year "
                             "(dynamic — no longer hardcoded).")
    parser.add_argument("--create-table-only", action="store_true",
                        help="Just create the table and exit (for testing)")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    log.info("Phase 2 Step 1: building gamma_levels_eod for %s (%d-%d)",
             tickers, args.start_year, args.end_year)

    execute_sql(CREATE_TABLE_SQL)
    log.info("Ensured gamma_levels_eod table exists")
    if args.create_table_only:
        return

    engine = get_engine()
    grand_total = 0
    for ticker in tickers:
        grand_total += _process_ticker(engine, ticker, args.start_year, args.end_year)

    log.info("All tickers complete — %d total level rows written", grand_total)


if __name__ == "__main__":
    main()
