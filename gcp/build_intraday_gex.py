"""Build / refresh `intraday_gex_15m` — MATERIALIZED reconstructed intraday
dealer GEX/DEX per ticker × 15m bar, by walking the prior-day (T-1) EOD option
chain forward to each intraday spot (the delta-gamma re-curve; see
`lib.features.intraday_gex` for the math + assumptions).

RULE 0 (NON-NEGOTIABLE): this Job is the ONLY place `etf_options_snapshots`
(~14M rows) is scanned for the intraday-gex block. The per-experiment loader
(`lib.features.intraday_gex.add_intragex_features`) reads the small materialized
table. The EOD chain is collapsed to per-DAY scalars (NetΓ, A, B, flip, total_oi,
S_eod) once per date; per-bar values are a vectorized formula on the day's spots.

Design (per CLAUDE.md Rule 0):
  * ONE ticker at a time; per-YEAR scan (bounded memory, observable timings).
  * Idempotent + RESUMABLE: ON CONFLICT (ticker, ts) DO UPDATE, and `--backfill`
    resumes from the gap after the last materialized bucket per ticker — a run
    cut short by a timeout/crash continues instead of restarting from 2015. The
    durable rows ARE the checkpoint.
  * Fast upsert: one COPY → temp → INSERT…ON CONFLICT per ticker
    (`gcp.database.bulk_copy_upsert`), not a per-row loop.
  * No silent fallbacks (§3.7): a date with no prior EOD chain is SKIPPED
    (no fabricated 0 rows); a bar with bad spot yields NaN greeks.

Modes:
  --backfill [--restart]     resume the full-history build (since 2016-01-01)
                             from the gap; --restart forces a clean recompute.
  --incremental [--days N]   recompute the last N days (default 7).
  --ticker T                 restrict to one ticker (default: IWM,SPY,QQQ).

Examples:
  python -m gcp.build_intraday_gex --backfill            # resume from the gap
  python -m gcp.build_intraday_gex --incremental --days 7
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
BACKFILL_SINCE = "2016-01-01"   # AV EOD options history starts ~2016


def _load_eod_chains(engine, ticker: str, since: str, until: str) -> pd.DataFrame:
    """All T-1 EOD chain rows in [since, until). Uses the EOD covering index
    predicate (market_session='EOD' AND data_source='alphavantage'). DB errors
    propagate (§3.7). NOTE: the chain's own underlying_price is NULL for these
    rows, so S_eod comes from market_data_daily.close (see _load_daily_close)."""
    from sqlalchemy import text
    sql = text(
        """
        SELECT snapshot_date, option_type, strike, open_interest, delta, gamma
        FROM etf_options_snapshots
        WHERE ticker = :tk AND market_session = 'EOD'
          AND data_source = 'alphavantage'
          AND snapshot_date >= :s AND snapshot_date < :u
        """
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"tk": ticker, "s": since, "u": until})
    return df


def _load_daily_close(engine, ticker: str, since: str, until: str) -> dict:
    """{trading date -> EOD close} from market_data_daily. This is the S_eod the
    delta-gamma re-curve anchors on (the option chain's own underlying_price is
    NULL for EOD rows). DB errors propagate (§3.7)."""
    from sqlalchemy import text
    sql = text(
        """
        SELECT date, close FROM market_data_daily
        WHERE ticker = :tk AND date >= :s AND date < :u AND close IS NOT NULL
        """
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"tk": ticker, "s": since, "u": until})
    if df.empty:
        return {}
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return dict(zip(df["date"], df["close"].astype(float)))


def _load_intraday_spots(engine, ticker: str, since: str, until: str) -> pd.DataFrame:
    """Per-15m-bucket underlying spot = last 1-min close in [T, T+15m). Grid
    matches strat_features_15m (UTC bar-open, 15-min floor). `until` inclusive."""
    from sqlalchemy import text
    sql = text(
        """
        SELECT bucket AS ts, spot FROM (
            SELECT (date_trunc('hour', ts)
                    + floor(extract(minute FROM ts)::int / 15) * interval '15 minutes'
                   ) AS bucket,
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
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def compute_intragex_frame(engine, ticker: str, since: str,
                           until: str) -> pd.DataFrame:
    """RULE 0: scans etf_options_snapshots + market_data_intraday — called ONLY
    by this Job. Returns RAW per-bar aggregates indexed by ts. Each intraday
    ET-date is reconstructed from the most-recent PRIOR EOD chain."""
    from lib.features.intraday_gex import reconstruct_day, RAW_COLS

    s_year, u_year = int(since[:4]), int(until[:4])
    frames: list[pd.DataFrame] = []
    for y in range(s_year, u_year + 1):
        y_s = max(since, f"{y}-01-01")
        y_u_date = min(until, f"{y}-12-31")
        y_u = (pd.Timestamp(y_u_date) + pd.Timedelta(days=1)).date().isoformat()
        t0 = pd.Timestamp.utcnow()
        # Pull EOD chains from ~10d before y_s so Jan-2 has a prior chain.
        chain_s = (pd.Timestamp(y_s) - pd.Timedelta(days=10)).date().isoformat()
        chains = _load_eod_chains(engine, ticker, chain_s, y_u)
        spots = _load_intraday_spots(engine, ticker, y_s, y_u)
        dclose = _load_daily_close(engine, ticker, chain_s, y_u)
        if chains.empty or spots.empty or not dclose:
            log.info("intraday-gex year=%d chains=%d spots=%d dclose=%d (skip)", y,
                     len(chains), len(spots), len(dclose))
            continue

        chains["snapshot_date"] = pd.to_datetime(chains["snapshot_date"]).dt.date
        # S_eod anchors on market_data_daily.close (chain underlying_price is NULL).
        eod_dates = np.array(sorted(chains["snapshot_date"].unique()))

        spots = spots.copy()
        spots["et_date"] = (spots["ts"].dt.tz_convert("America/New_York").dt.date)

        n_days = 0
        for d, day_spots in spots.groupby("et_date"):
            # most-recent EOD date strictly before the intraday date d
            idx = int(np.searchsorted(eod_dates, d, side="left")) - 1
            if idx < 0:
                continue  # no prior chain — skip (no fabricated rows, §3.7)
            prior = eod_dates[idx]
            s_eod = dclose.get(prior, float("nan"))
            if not (s_eod and s_eod > 0):
                continue  # no EOD close for the prior day — skip (no NaN rows)
            chain_d = chains[chains["snapshot_date"] == prior]
            fr = reconstruct_day(chain_d, s_eod, day_spots[["ts", "spot"]])
            if not fr.empty:
                frames.append(fr)
                n_days += 1
        log.info("intraday-gex year=%d chains=%d spots=%d days=%d elapsed=%.1fs",
                 y, len(chains), len(spots), n_days,
                 (pd.Timestamp.utcnow() - t0).total_seconds())

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out[RAW_COLS]


def upsert_intragex(engine, ticker: str, frame: pd.DataFrame) -> int:
    """Idempotent per-bucket upsert via the COPY fast path
    (`gcp.database.bulk_copy_upsert`). NaN stays NULL (§3.7); computed_at falls
    to its schema DEFAULT NOW()."""
    import gcp.database as db
    if frame is None or frame.empty:
        return 0
    out = frame.reset_index()
    out.insert(0, "ticker", ticker)
    return db.bulk_copy_upsert(
        out, "intraday_gex_15m",
        conflict_cols=["ticker", "ts"],
        update_cols=["total_gex", "total_dex", "total_oi", "gamma_flip", "spot"],
    )


def _resume_since(engine, ticker: str, default_since: str) -> str:
    """Gap-resume start date: day of the last materialized bucket minus one day
    (idempotent overlap). default_since when the table has no rows yet."""
    from sqlalchemy import text
    with engine.connect() as conn:
        last = conn.execute(
            text("SELECT max(ts) FROM intraday_gex_15m WHERE ticker = :tk"),
            {"tk": ticker},
        ).scalar()
    if last is None:
        return default_since
    resume = (pd.Timestamp(last).date() - timedelta(days=1)).isoformat()
    return max(default_since, resume)


def build(engine, tickers, since: str, until: str, resume: bool = False) -> dict:
    """Compute + upsert reconstructed intraday GEX/DEX per ticker SEQUENTIALLY."""
    written = {}
    for tk in tickers:
        tk_since = _resume_since(engine, tk, since) if resume else since
        log.info("=" * 70)
        if resume and tk_since != since:
            log.info("RESUME ticker=%s: scanning gap from %s (skipping %s..%s)",
                     tk, tk_since, since, tk_since)
        log.info("build-intraday-gex ticker=%s window=[%s..%s]", tk, tk_since, until)
        frame = compute_intragex_frame(engine, tk, tk_since, until)
        n = upsert_intragex(engine, tk, frame)
        written[tk] = n
        log.info("build-intraday-gex ticker=%s upserted=%d buckets "
                 "(dex non-null=%d)", tk, n,
                 int(frame["total_dex"].notna().sum()) if not frame.empty else 0)
    log.info("=" * 70)
    log.info("build-intraday-gex DONE: %s", written)
    return written


def main():
    from gcp.database import get_engine
    from lib.logging_config import setup_logging
    setup_logging()

    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backfill", action="store_true",
                      help="resume full-history build (since " + BACKFILL_SINCE + ")")
    mode.add_argument("--incremental", action="store_true",
                      help="recompute the last --days days")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--ticker", default=None, choices=list(TICKERS))
    p.add_argument("--restart", action="store_true",
                   help="(backfill only) ignore existing rows; full recompute")
    args = p.parse_args()

    tickers = (args.ticker,) if args.ticker else TICKERS
    until = date.today().isoformat()
    since = (BACKFILL_SINCE if args.backfill
             else (date.today() - timedelta(days=args.days)).isoformat())
    resume = bool(args.backfill) and not args.restart

    engine = get_engine()
    build(engine, tickers, since, until, resume=resume)


if __name__ == "__main__":
    main()
