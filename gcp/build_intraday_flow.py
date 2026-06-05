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
  * Idempotent: ON CONFLICT (ticker, ts) DO UPDATE — re-run converges.
  * Observable: per-ticker upsert counts + per-year scan timings.
  * Bounded memory: each ticker's bucket frame is ~83k rows; written per ticker.

Modes:
  --backfill                 recompute ALL history (since 2015-01-01).
  --incremental [--days N]   recompute the last N days (default 7) — run on a
                             scheduler AFTER the intraday bars land.
  --ticker T                 restrict to one ticker (default: IWM,SPY,QQQ).

Examples:
  python -m gcp.build_intraday_flow --backfill --ticker SPY
  python -m gcp.build_intraday_flow --incremental --days 7
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
BACKFILL_SINCE = "2015-01-01"

_UPSERT_SQL = """
INSERT INTO intraday_flow_15m
    (ticker, ts, signed_vol, tot_vol, up_vol, dn_vol, n_min, computed_at)
VALUES
    (:ticker, :ts, :signed_vol, :tot_vol, :up_vol, :dn_vol, :n_min, NOW())
ON CONFLICT (ticker, ts) DO UPDATE SET
    signed_vol  = EXCLUDED.signed_vol,
    tot_vol     = EXCLUDED.tot_vol,
    up_vol      = EXCLUDED.up_vol,
    dn_vol      = EXCLUDED.dn_vol,
    n_min       = EXCLUDED.n_min,
    computed_at = NOW()
"""


def _none(v):
    """NaN -> None so the driver binds SQL NULL (no fabricated 0)."""
    if v is None:
        return None
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    return v


def upsert_intraflow(engine, ticker: str, frame: pd.DataFrame) -> int:
    """Idempotent per-bucket upsert. frame is indexed by ts with the raw
    aggregate columns. Returns rows written."""
    from sqlalchemy import text
    if frame is None or frame.empty:
        return 0
    rows = []
    for ts, r in frame.iterrows():
        rows.append({
            "ticker": ticker,
            "ts": ts.to_pydatetime(),
            "signed_vol": _none(float(r["signed_vol"])
                                if pd.notna(r["signed_vol"]) else np.nan),
            "tot_vol": _none(float(r["tot_vol"])
                             if pd.notna(r["tot_vol"]) else np.nan),
            "up_vol": _none(float(r["up_vol"]) if pd.notna(r["up_vol"]) else np.nan),
            "dn_vol": _none(float(r["dn_vol"]) if pd.notna(r["dn_vol"]) else np.nan),
            "n_min": int(r["n_min"]) if pd.notna(r["n_min"]) else 0,
        })
    sql = text(_UPSERT_SQL)
    # Chunked transactions (bounded memory / observable progress on a big
    # backfill); each chunk is atomic and idempotent.
    written = 0
    CHUNK = 5000
    for i in range(0, len(rows), CHUNK):
        batch = rows[i:i + CHUNK]
        with engine.begin() as conn:
            for row in batch:
                conn.execute(sql, row)
        written += len(batch)
        log.info("  upsert %s progress=%d/%d", ticker, written, len(rows))
    return written


def build(engine, tickers, since: str, until: str) -> dict:
    """Compute + upsert intraday OFI buckets for each ticker SEQUENTIALLY."""
    from lib.features.intraday_flow import compute_intraflow_frame
    written = {}
    for tk in tickers:
        log.info("=" * 70)
        log.info("build-intraday-flow ticker=%s window=[%s..%s]", tk, since, until)
        frame = compute_intraflow_frame(engine, tk, since, until)
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
    args = p.parse_args()

    tickers = (args.ticker,) if args.ticker else TICKERS
    until = date.today().isoformat()
    since = (BACKFILL_SINCE if args.backfill
             else (date.today() - timedelta(days=args.days)).isoformat())

    engine = get_engine()
    build(engine, tickers, since, until)


if __name__ == "__main__":
    main()
