"""Stage 1b — Levels enrichment — `strat_enrich_levels.py`.

Backfills `strat_features_levels_{tf}` with the level-based features
that `strat_features_{tf}` is MISSING:

  - ORB (Opening Range Breakout) — 5m, 15m, 30m windows × ~12 cols each
    (add_all_indicators computes these but the explicit whitelist in
    p7_build_multi_tf_features dropped them)

  - Historical levels (`calculate_historical_levels`) — Prev_Day,
    Prev_Week, Prev_Month, Prev_Quarter, Prev_Year × {High, Low, Open,
    Close, HL_Mid, OC_Mid} × {value, _Pct, At_*} + Broke_* flags
    (~100 cols; not called anywhere in the existing pipeline)

  - Order blocks (`calculate_order_blocks`) — 7 cols (also not called)

This is the data the reviewer flagged as central to direction reads —
without these, the Stage 4 gate would be a false-negative kill on a
crippled feature set.

Schema: NEW table strat_features_levels_{tf} keyed by (ticker, ts).
Joined LEFT in strat_dataset.load_labeled_dataset.

Modes:
  --mode=schema           Issue CREATE TABLE IF NOT EXISTS for one TF.
  --mode=backfill         For one (ticker, TF): pull OHLCV from
                          strat_features, compute the 3 enrichments,
                          upsert to strat_features_levels_{tf}.
  --mode=schema-all       Schema for ALL TFs (1m..4h).
  --mode=backfill-all     Backfill for ALL (ticker, TF) combos.
"""
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine, execute_sql, bulk_copy_upsert
from gcp.research.strat_engine.strat_config import (
    TICKERS, TIMEFRAMES, strat_features_table,
)
from lib.indicators import (
    calculate_all_orb, calculate_historical_levels, calculate_order_blocks,
    calculate_atr, calculate_current_period_levels,
)
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


def levels_table(tf: str) -> str:
    return f"strat_features_levels_{tf}"


def _compute_enrichments(df: pd.DataFrame, include_current_period: bool = False) -> pd.DataFrame:
    """Compute ORB + historical levels + (optional current-period) + order
    blocks. Input: DataFrame with columns ts, open, high, low, close,
    volume (lowercase). Returns: same row count, ticker + ts +
    enrichment columns only.

    include_current_period defaults to FALSE to keep the M2 feature set
    consistent across TFs (the original 15m backfill predates
    calculate_current_period_levels). Flip to True once 15m has been
    migrated to add the cur_* cols.
    """
    times = pd.to_datetime(df["ts"], utc=True)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    o = df["open"].astype(float)
    c = df["close"].astype(float)

    # 1) ORB (all default windows: 5/15/30). The opening-range window
    # (market_open=09:30 ET in calculate_orb) must be matched in EASTERN time.
    # strat_features.ts is UTC, so the raw wall-clock never falls inside
    # 09:30-09:35 and every ORB high/low/mid/range comes back NaN — the
    # orb_5m_high "always NULL" bug that left the magnitude models trained on a
    # dead ORB feature set. Convert to ET before the session filter.
    orb = calculate_all_orb(times.dt.tz_convert("America/New_York"), h, l, c)
    orb.index = df.index
    log.info("  ORB: %d cols", orb.shape[1])

    # 2) Historical levels (prev day/week/month/quarter/year HLOC + flags)
    hist = calculate_historical_levels(times, h, l, o, c)
    hist.index = df.index
    log.info("  Historical levels (prev): %d cols", hist.shape[1])

    parts = [orb, hist]

    # 2b) OPTIONAL CURRENT-period running levels (today/WTD/MTD/QTD/YTD).
    # Gated by `include_current_period` so M2 feature set matches 15m's
    # pre-existing 143-col schema. Once 15m is migrated, default True.
    if include_current_period:
        cur = calculate_current_period_levels(times, h, l, o, c)
        cur.index = df.index
        log.info("  Current-period running levels: %d cols", cur.shape[1])
        parts.append(cur)
    else:
        log.info("  Current-period running levels: SKIPPED (M2 schema match)")

    # 3) Order blocks (uses ATR if available; compute ATR(14) here)
    atr14 = calculate_atr(h, l, c, period=14)
    ob = calculate_order_blocks(h, l, c, atr=atr14)
    ob.index = df.index
    # rename to OB_* prefix for clarity since the function returns
    # un-prefixed columns
    ob = ob.rename(columns={c: f"OB_{c}" if not c.startswith("OB_") else c
                             for c in ob.columns})
    log.info("  Order blocks: %d cols", ob.shape[1])

    parts.append(ob)
    out = pd.concat(parts, axis=1)
    # snake_case + lowercase column names for SQL friendliness
    rename = {}
    for col in out.columns:
        snake = col.replace("__", "_").lower()
        rename[col] = snake
    out = out.rename(columns=rename)
    log.info("  enrichment total: %d cols", out.shape[1])
    return out


def _create_table_for_tf(engine, tf: str, sample_cols: list[str]):
    """Create strat_features_levels_{tf} with the discovered enrichment
    columns. All numeric cols → DOUBLE PRECISION; flags handled the same."""
    col_defs = ["ticker VARCHAR(16) NOT NULL",
                "ts TIMESTAMPTZ NOT NULL"]
    for c in sample_cols:
        col_defs.append(f"{c} DOUBLE PRECISION")
    ddl = f"""
CREATE TABLE IF NOT EXISTS {levels_table(tf)} (
    {", ".join(col_defs)},
    computed_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, ts)
);
CREATE INDEX IF NOT EXISTS ix_{levels_table(tf)}_ts ON {levels_table(tf)} (ts);
"""
    execute_sql(ddl)
    log.info("ensured schema: %s (%d enrichment cols)", levels_table(tf), len(sample_cols))


def backfill_one(engine, ticker: str, tf: str, batch_year: bool = True,
                  include_current_period: bool = False):
    """Compute enrichments for ALL rows of (ticker, TF) in strat_features
    and UPSERT to strat_features_levels_{tf}. Returns row count.

    include_current_period defaults False for M2 schema consistency with
    the pre-existing 15m backfill."""
    log.info("=" * 70)
    log.info("BACKFILL  ticker=%s  tf=%s  include_current_period=%s",
             ticker, tf, include_current_period)
    log.info("=" * 70)
    sql = text(f"SELECT ts, open, high, low, close, volume FROM "
               f"{strat_features_table(tf)} WHERE ticker = :t "
               f"AND strat_candle IS NOT NULL ORDER BY ts")
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"t": ticker})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").reset_index(drop=True)
    log.info("loaded %d rows", len(df))
    if len(df) == 0:
        log.warning("  no source rows; skipping")
        return 0

    enrich = _compute_enrichments(df, include_current_period=include_current_period)
    enrich["ticker"] = ticker
    enrich["ts"] = df["ts"].values
    # reorder: ticker, ts first
    cols_order = ["ticker", "ts"] + [c for c in enrich.columns if c not in ("ticker", "ts")]
    enrich = enrich[cols_order]

    # ensure schema covers all our cols
    enrichment_cols = [c for c in enrich.columns if c not in ("ticker", "ts")]
    _create_table_for_tf(engine, tf, enrichment_cols)

    # bulk upsert
    bulk_copy_upsert(
        enrich, levels_table(tf),
        conflict_cols=["ticker", "ts"],
        update_cols=enrichment_cols + ["computed_at"] if "computed_at" in enrich.columns else enrichment_cols,
    )
    log.info("upserted %d rows × %d enrichment cols to %s",
             len(enrich), len(enrichment_cols), levels_table(tf))
    return len(enrich)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode",
                   choices=["schema", "backfill", "schema-all", "backfill-all"],
                   required=True)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--include-current-period", action="store_true",
                   help="Include cur_day_*/cur_week_*/etc. cols. Default OFF "
                        "for M2 to match 15m's 143-col feature set.")
    args = p.parse_args()
    engine = get_engine()

    if args.mode == "schema":
        # Need a sample to discover columns
        log.info("Computing column list from a 100-row sample for %s %s...",
                 args.ticker, args.tf)
        sql = text(f"SELECT ts, open, high, low, close, volume FROM "
                   f"{strat_features_table(args.tf)} WHERE ticker = :t "
                   f"AND strat_candle IS NOT NULL ORDER BY ts LIMIT 100")
        with engine.connect() as c:
            sample = pd.read_sql(sql, c, params={"t": args.ticker})
        sample["ts"] = pd.to_datetime(sample["ts"], utc=True)
        enrich = _compute_enrichments(sample)
        _create_table_for_tf(engine, args.tf,
                              [c for c in enrich.columns if c not in ("ticker", "ts")])
    elif args.mode == "backfill":
        backfill_one(engine, args.ticker, args.tf,
                     include_current_period=args.include_current_period)
    elif args.mode == "schema-all":
        for tf in TIMEFRAMES:
            # Use IWM as sample for column discovery
            sql = text(f"SELECT ts, open, high, low, close, volume FROM "
                       f"{strat_features_table(tf)} WHERE ticker = 'IWM' "
                       f"AND strat_candle IS NOT NULL ORDER BY ts LIMIT 100")
            try:
                with engine.connect() as c:
                    sample = pd.read_sql(sql, c)
                if len(sample) == 0:
                    log.warning("no sample for %s; skipping", tf)
                    continue
                sample["ts"] = pd.to_datetime(sample["ts"], utc=True)
                enrich = _compute_enrichments(sample)
                _create_table_for_tf(engine, tf,
                                      [c for c in enrich.columns if c not in ("ticker", "ts")])
            except Exception as e:
                log.error("schema-all for %s failed: %s", tf, e)
    elif args.mode == "backfill-all":
        for ticker in TICKERS:
            for tf in TIMEFRAMES:
                try:
                    backfill_one(engine, ticker, tf,
                                 include_current_period=args.include_current_period)
                except Exception as e:
                    log.error("backfill %s %s failed: %s", ticker, tf, e)


if __name__ == "__main__":
    main()
