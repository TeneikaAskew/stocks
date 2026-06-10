"""Build / refresh `realtime_gex_15m` — MATERIALIZED per-15m-bucket REAL intraday
dealer GEX/DEX from the av-options-realtime feed (actual intraday greeks), so the
real-intraday-DEX LEAD can be walk-forward tested as the live window lengthens.

WHY (vs intraday_gex_15m): `intraday_gex_15m` RECONSTRUCTS intraday positioning by
re-curving the T-1 EOD chain (delta-gamma expansion) — it goes back to 2016 but its
DEX *magnitude* is only moderately faithful (corr 0.55–0.82 vs real; GEX worse).
This table stores the ACTUAL intraday greeks captured every 5 min by
`fetch_av_realtime_options` (market_session='REALTIME', live since 2026-05-23). It
is short (recent only) but exact — the ground truth the reconstruction approximates.
The 2026-06-06 exploratory read found real intraday DEX has the program's first
cross-ticker-positive IC vs forward returns (a LEAD, not yet a verdict — needs
≥6 months for an 8-fold walk-forward). This builder + its daily scheduler make that
data accrue in a small, query-cheap table so the verdict is ready when the window is.

DESIGN (CLAUDE.md Rule 0):
  * ONE ticker at a time. The expensive REALTIME scan (~1.2M rows/ticker/day) runs
    ONLY here; experiments read the ~26-rows/day materialized table via
    lib.features.intraday_gex.add_realgex_features.
  * Per 15m bucket: take the LAST REALTIME snapshot in the bucket, aggregate its
    chain to net γ·OI (call−put) and Σ δ·OI (real greeks), join the bucket spot
    from market_data_intraday (REALTIME underlying_price is NULL), and form
    total_gex / total_dex / gamma_flip via lib.gamma (same convention as the
    reconstruction, so the two tables are directly comparable).
  * Idempotent + RESUMABLE: ON CONFLICT (ticker, ts) DO UPDATE; --backfill resumes
    from the gap. COPY upsert (gcp.database.bulk_copy_upsert).
  * No silent fallbacks (§3.7): zero OI / missing spot → NaN greeks, never 0.

Modes:
  --backfill [--restart]     (re)build the whole live window (since 2026-05-23).
  --incremental [--days N]   recompute the last N days (default 3) — the scheduled
                             daily path; run after RTH close once the feed lands.
  --ticker T                 restrict to one ticker (default IWM,SPY,QQQ).
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
BACKFILL_SINCE = "2026-05-23"   # av-options-realtime feed went live


def _load_realtime_chain(engine, ticker: str, since: str, until: str) -> pd.DataFrame:
    """Per-(15m bucket, strike) REAL greek sums from the LAST REALTIME snapshot in
    each bucket. `until` exclusive (ISO date). DB errors propagate (§3.7)."""
    from sqlalchemy import text
    sql = text(
        """
        WITH base AS (
            SELECT (date_trunc('hour', snapshot_ts)
                    + floor(extract(minute FROM snapshot_ts)::int / 15) * interval '15 minutes'
                   ) AS bucket,
                   snapshot_ts, strike, option_type, gamma, delta, open_interest
            FROM etf_options_snapshots
            WHERE ticker = :tk AND market_session = 'REALTIME'
              AND snapshot_date >= :s AND snapshot_date < :u
        ),
        lastsnap AS (SELECT bucket, max(snapshot_ts) AS snap FROM base GROUP BY bucket)
        SELECT b.bucket AS ts, b.strike,
               SUM(CASE WHEN b.option_type = 'calls' THEN b.gamma * b.open_interest ELSE 0 END) AS call_g,
               SUM(CASE WHEN b.option_type = 'puts'  THEN b.gamma * b.open_interest ELSE 0 END) AS put_g,
               SUM(b.delta * b.open_interest) AS dxoi,
               SUM(b.open_interest)           AS oi
        FROM base b JOIN lastsnap l ON b.bucket = l.bucket AND b.snapshot_ts = l.snap
        GROUP BY b.bucket, b.strike
        ORDER BY b.bucket, b.strike
        """
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"tk": ticker, "s": since, "u": until})
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def _load_intraday_spots(engine, ticker: str, since: str, until: str) -> pd.DataFrame:
    """Per-15m-bucket spot = last 1-min close in [T, T+15m). `until` exclusive."""
    from sqlalchemy import text
    sql = text(
        """
        SELECT bucket AS ts, spot FROM (
            SELECT (date_trunc('hour', ts)
                    + floor(extract(minute FROM ts)::int / 15) * interval '15 minutes') AS bucket,
                   close AS spot,
                   row_number() OVER (
                     PARTITION BY (date_trunc('hour', ts)
                       + floor(extract(minute FROM ts)::int / 15) * interval '15 minutes')
                     ORDER BY ts DESC) AS rn
            FROM market_data_intraday
            WHERE ticker = :tk AND ts >= :s AND ts < :u
        ) q WHERE rn = 1 ORDER BY bucket
        """
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"tk": ticker, "s": since, "u": until})
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def compute_realtime_frame(engine, ticker: str, since: str, until: str) -> pd.DataFrame:
    """RULE 0: scans REALTIME + market_data_intraday — called ONLY by this Job.
    Returns RAW per-bar aggregates (RAW_COLS) indexed by ts."""
    from lib.features.intraday_gex import aggregate_realtime_buckets, RAW_COLS
    u = (pd.Timestamp(until) + pd.Timedelta(days=1)).date().isoformat()
    t0 = pd.Timestamp.utcnow()
    chain = _load_realtime_chain(engine, ticker, since, u)
    spots = _load_intraday_spots(engine, ticker, since, u)
    log.info("realtime-gex %s chain_rows=%d spot_buckets=%d elapsed=%.1fs",
             ticker, len(chain), len(spots), (pd.Timestamp.utcnow() - t0).total_seconds())
    if chain.empty or spots.empty:
        return pd.DataFrame()
    out = aggregate_realtime_buckets(chain, spots)
    return out[RAW_COLS] if not out.empty else out


def upsert_realtime_gex(engine, ticker: str, frame: pd.DataFrame) -> int:
    """Idempotent COPY upsert to realtime_gex_15m. NaN→NULL (§3.7)."""
    import gcp.database as db
    if frame is None or frame.empty:
        return 0
    out = frame.reset_index()
    out.insert(0, "ticker", ticker)
    return db.bulk_copy_upsert(
        out, "realtime_gex_15m",
        conflict_cols=["ticker", "ts"],
        update_cols=["total_gex", "total_dex", "total_oi", "gamma_flip", "spot"],
    )


def _resume_since(engine, ticker: str, default_since: str) -> str:
    """Gap-resume start: day of the last materialized bucket minus one day."""
    from sqlalchemy import text
    with engine.connect() as conn:
        last = conn.execute(
            text("SELECT max(ts) FROM realtime_gex_15m WHERE ticker = :tk"),
            {"tk": ticker},
        ).scalar()
    if last is None:
        return default_since
    resume = (pd.Timestamp(last).date() - timedelta(days=1)).isoformat()
    return max(default_since, resume)


def build(engine, tickers, since: str, until: str, resume: bool = False) -> dict:
    written = {}
    for tk in tickers:
        tk_since = _resume_since(engine, tk, since) if resume else since
        log.info("=" * 70)
        if resume and tk_since != since:
            log.info("RESUME ticker=%s: scanning gap from %s", tk, tk_since)
        log.info("build-realtime-gex ticker=%s window=[%s..%s]", tk, tk_since, until)
        frame = compute_realtime_frame(engine, tk, tk_since, until)
        n = upsert_realtime_gex(engine, tk, frame)
        written[tk] = n
        log.info("build-realtime-gex ticker=%s upserted=%d buckets (dex non-null=%d)",
                 tk, n, int(frame["total_dex"].notna().sum()) if not frame.empty else 0)
    log.info("=" * 70)
    log.info("build-realtime-gex DONE: %s", written)
    return written


def main():
    from gcp.database import get_engine
    from lib.logging_config import setup_logging
    setup_logging()

    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backfill", action="store_true",
                      help="(re)build the whole live window since " + BACKFILL_SINCE)
    mode.add_argument("--incremental", action="store_true",
                      help="recompute the last --days days (scheduled daily path)")
    p.add_argument("--days", type=int, default=3)
    p.add_argument("--ticker", default=None, choices=list(TICKERS))
    p.add_argument("--restart", action="store_true",
                   help="(backfill only) ignore existing rows; full recompute")
    args = p.parse_args()

    tickers = (args.ticker,) if args.ticker else TICKERS
    until = date.today().isoformat()
    since = (BACKFILL_SINCE if args.backfill
             else max(BACKFILL_SINCE,
                      (date.today() - timedelta(days=args.days)).isoformat()))
    resume = bool(args.backfill) and not args.restart

    engine = get_engine()
    build(engine, tickers, since, until, resume=resume)


if __name__ == "__main__":
    main()
