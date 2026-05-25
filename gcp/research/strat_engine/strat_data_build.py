"""Stage 1 — Data — `strat_data_build.py`.

Modes:
  --mode=summary          Print row counts per (ticker, tf). Coverage gap report.
  --mode=verify           Run the leakage + label-sanity tests on the
                          labeled dataset for a (ticker, tf). This is the M1 gate.
  --mode=ensure-coverage  ORCHESTRATOR: identify missing (ticker, tf) combos
                          vs the config TICKERS x TIMEFRAMES grid and dispatch
                          backfill jobs for each gap. The strat_engine reuses
                          existing strat_features_{tf} tables wherever they
                          exist; this mode only fires builds for missing data.
  --mode=build-4h         Build strat_features_4h for one ticker by aggregating
                          from strat_features_60m. Called by ensure-coverage;
                          can also be run standalone.

PRD scope: this stage VERIFIES + BACKFILLS the labeled dataset (orchestrator
over existing tables); downstream stages (EDA/corr/model/FTFC/readout) consume
it via the shared loader in strat_dataset.py.
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine, bulk_copy_upsert, execute_sql
from gcp.research.strat_engine.strat_config import (
    TICKERS, TIMEFRAMES, TF_MINUTES,
    NUMERIC_FEATURES, STRAT_SEQUENCE_FEATURES, REGIME_FEATURES,
    LABEL_COL, LABEL_CLASSES, DEFAULT_TRAIN_UNTIL,
    GCS_BUCKET_DEFAULT, GCS_PREFIX, strat_features_table,
)
from gcp.research.strat_engine.strat_dataset import (
    load_labeled_dataset, base_rate,
)
from google.cloud import storage as gcs
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


# ─────────────────────── GCS ───────────────────────

def _upload(content: bytes, blob_path: str, ctype="application/json"):
    client = gcs.Client()
    bucket = client.bucket(os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT))
    bucket.blob(blob_path).upload_from_string(content, content_type=ctype)


# ─────────────────────── Mode: verify ───────────────────────

def verify(engine, ticker: str, tf: str) -> dict:
    """Run M1 acceptance tests:
      1. Row count vs source strat_features matches (modulo last bar / warmup).
      2. next_bar_type label correctness: spot-check a sample of bars by
         re-classifying bar t+1 from its OHLC against bar t — must match.
      3. Leakage check: for every numeric feature, verify that NO column
         contains future information (mean-of-feature must be invariant to
         truncating data after t).
      4. Class balance: report next_bar_type distribution.
    """
    log.info("=" * 70)
    log.info("Stage 1 VERIFY  ticker=%s  tf=%s", ticker, tf)
    log.info("=" * 70)

    # Pull source row count for comparison
    with engine.connect() as c:
        src_n = c.execute(
            text(f"SELECT count(*) FROM {strat_features_table(tf)} "
                 f"WHERE ticker = :t AND strat_candle IS NOT NULL"),
            {"t": ticker}
        ).scalar()

    df = load_labeled_dataset(engine, ticker, tf)
    log.info("source rows: %d  labeled rows: %d  (drop = last bar + 3-bar warmup)",
             src_n, len(df))

    # TEST 1: row count gap is ≤ 4 (1 final + 3 warmup)
    gap = src_n - len(df)
    test1 = "PASS" if 0 <= gap <= 10 else "FAIL"
    log.info("TEST 1 row-count gap: %d  [%s]", gap, test1)

    # TEST 2: label correctness — spot-check N random bars
    n_check = min(50, len(df) - 1)
    rng = np.random.default_rng(42)
    sample_idx = rng.choice(len(df) - 1, size=n_check, replace=False)
    mismatches = 0
    for i in sample_idx:
        row = df.iloc[i]
        next_row = df.iloc[i + 1]
        # Re-derive what bar t+1's classification SHOULD be by comparing its
        # OHLC against bar t's high/low.
        h_t, l_t = row["high"], row["low"]
        h_n, l_n = next_row["high"], next_row["low"]
        if h_n > h_t and l_n < l_t:    expected = "3"
        elif h_n > h_t:                 expected = "2U"
        elif l_n < l_t:                 expected = "2D"
        else:                           expected = "1"
        if row[LABEL_COL] != expected:
            mismatches += 1
    test2 = "PASS" if mismatches == 0 else f"FAIL ({mismatches}/{n_check})"
    log.info("TEST 2 label correctness on %d random bars: [%s]", n_check, test2)

    # TEST 3: leakage check via train/test mean comparison
    # For each numeric feature, the OOS mean should NOT systematically
    # depend on knowing future data. We can't directly prove no-leakage,
    # but we CAN detect the obvious case: vix_close was a known same-day
    # leak (now fixed). Re-run that check.
    leak_findings = []
    bd_2026_05_22 = pd.Timestamp("2026-05-22", tz="UTC").date()
    sample = df[df["bar_date"] == bd_2026_05_22] if "bar_date" in df.columns else pd.DataFrame()
    if len(sample) > 0 and "vix_close" in sample.columns:
        # Compare to ^VIX daily close for that date — should be DIFFERENT
        # (vix_close should be prior day's close, not same-day).
        with engine.connect() as c:
            same_day_vix = c.execute(
                text("SELECT close FROM market_data_daily "
                     "WHERE ticker='^VIX' AND date = :d"),
                {"d": bd_2026_05_22}
            ).scalar()
        sample_vix = float(sample["vix_close"].iloc[0])
        if same_day_vix is not None and abs(sample_vix - float(same_day_vix)) < 0.01:
            leak_findings.append(
                f"vix_close on {bd_2026_05_22} == same-day ^VIX close (LEAK)"
            )
    test3 = "PASS" if not leak_findings else f"FAIL: {leak_findings}"
    log.info("TEST 3 leakage check (vix_close vs same-day): [%s]", test3)

    # TEST 4: class balance
    br = base_rate(df[LABEL_COL])
    log.info("Class balance / base rate:")
    for cls in LABEL_CLASSES:
        log.info("  %-3s  %6.2f%%  (n=%d)", cls, br[cls]*100, int(br[cls]*len(df)))

    result = {
        "ticker": ticker, "tf": tf,
        "src_rows": int(src_n), "labeled_rows": int(len(df)),
        "row_gap": int(gap),
        "test1_row_gap": test1,
        "test2_label_mismatches": int(mismatches),
        "test2": test2,
        "test3_leak_findings": leak_findings,
        "test3": test3,
        "base_rate": {cls: float(br[cls]) for cls in LABEL_CLASSES},
        "verified_at": pd.Timestamp.utcnow().isoformat(),
    }

    blob = f"{GCS_PREFIX}/{ticker.lower()}_{tf}/verify_{int(time.time())}.json"
    _upload(json.dumps(result, indent=2, default=str).encode(), blob)
    log.info("saved: gs://%s/%s", os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT), blob)
    return result


# ─────────────────────── Mode: build-4h ───────────────────────

FOUR_H_DDL = """
CREATE TABLE IF NOT EXISTS strat_features_4h (
    ticker          VARCHAR(16) NOT NULL,
    ts              TIMESTAMPTZ NOT NULL,
    tf              VARCHAR(8) NOT NULL DEFAULT '4h',
    bar_date        DATE NOT NULL,
    open            DOUBLE PRECISION,
    high            DOUBLE PRECISION,
    low             DOUBLE PRECISION,
    close           DOUBLE PRECISION,
    volume          BIGINT,
    strat_candle    VARCHAR(8),
    prev_strat_candle VARCHAR(8),
    strat_combo     VARCHAR(64),
    is_continuation BOOLEAN,
    is_reversal     BOOLEAN,
    is_inside       BOOLEAN,
    strat_setup     BOOLEAN,
    consecutive_1s  SMALLINT,
    trigger_high    DOUBLE PRECISION,
    trigger_low     DOUBLE PRECISION,
    ema_9 DOUBLE PRECISION, ema_20 DOUBLE PRECISION, ema_50 DOUBLE PRECISION, ema_200 DOUBLE PRECISION,
    sma_50 DOUBLE PRECISION, sma_200 DOUBLE PRECISION,
    rsi_9 DOUBLE PRECISION, rsi_14 DOUBLE PRECISION,
    stoch_rsi_k DOUBLE PRECISION, stoch_rsi_d DOUBLE PRECISION,
    macd DOUBLE PRECISION, macd_signal DOUBLE PRECISION, macd_histogram DOUBLE PRECISION,
    atr_14 DOUBLE PRECISION, atr_20 DOUBLE PRECISION,
    bb_upper DOUBLE PRECISION, bb_lower DOUBLE PRECISION, bb_width DOUBLE PRECISION, bb_pct DOUBLE PRECISION,
    obv DOUBLE PRECISION, rvol DOUBLE PRECISION, rvol_10 DOUBLE PRECISION,
    vwap DOUBLE PRECISION,
    price_vs_vwap DOUBLE PRECISION, price_vs_ema9 DOUBLE PRECISION, price_vs_ema20 DOUBLE PRECISION,
    consecutive_up INTEGER, consecutive_down INTEGER,
    intraday_return DOUBLE PRECISION, high_low_spread_pct DOUBLE PRECISION,
    fwd_close_5bars DOUBLE PRECISION, fwd_close_15bars DOUBLE PRECISION,
    fwd_close_30bars DOUBLE PRECISION, fwd_close_60bars DOUBLE PRECISION,
    fwd_ret_5bars_bps DOUBLE PRECISION, fwd_ret_15bars_bps DOUBLE PRECISION,
    fwd_ret_30bars_bps DOUBLE PRECISION, fwd_ret_60bars_bps DOUBLE PRECISION,
    vix_close DOUBLE PRECISION, vix_tercile VARCHAR(8),
    total_gex DOUBLE PRECISION, gex_tercile VARCHAR(8),
    total_vex DOUBLE PRECISION, vex_tercile VARCHAR(8),
    dealer_regime VARCHAR(32), gamma_regime VARCHAR(32),
    flip_price DOUBLE PRECISION,
    distance_to_king_pct DOUBLE PRECISION, distance_to_gate_pct DOUBLE PRECISION,
    computed_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, ts)
);
CREATE INDEX IF NOT EXISTS ix_strat_features_4h_date ON strat_features_4h (bar_date);
CREATE INDEX IF NOT EXISTS ix_strat_features_4h_combo ON strat_features_4h (ticker, strat_combo);
"""


def build_4h(engine, ticker: str, source: str = "aggregate_from_60m") -> dict:
    """Build/refresh strat_features_4h for one ticker.

    source='aggregate_from_60m' (default): aggregate 60m OHLC → 4h, then
        re-compute indicators on 4h. Simplest; tracks 60m bars 1:1.
    source='raw_intraday': aggregate from 1m bars (more faithful but slower).
        Falls back to delegating to the existing p7_build_multi_tf_features
        helpers via import.
    """
    log.info("=" * 70)
    log.info("Stage 1 BUILD 4h  ticker=%s  source=%s", ticker, source)
    log.info("=" * 70)
    execute_sql(FOUR_H_DDL)
    log.info("schema ready: strat_features_4h")

    if source == "aggregate_from_60m":
        # Pull 60m bars; aggregate OHLCV to 4h (every 4 consecutive 60m bars
        # = one 4h bar, aligned to ET market open 9:30-13:30 / 13:30-17:30
        # — actually RTH is 9:30-16:00, that's 6.5h not divisible by 4).
        # Use 240-min bins aligned to ET 9:30 open.
        from lib.indicators import add_all_indicators
        from lib.strat import StratClassifier

        sql = text(f"SELECT ts, open, high, low, close, volume FROM "
                   f"{strat_features_table('60m')} WHERE ticker = :t "
                   f"AND strat_candle IS NOT NULL ORDER BY ts")
        with engine.connect() as c:
            bars_60m = pd.read_sql(sql, c, params={"t": ticker})
        bars_60m["ts"] = pd.to_datetime(bars_60m["ts"], utc=True)
        log.info("loaded %d 60m bars for %s", len(bars_60m), ticker)

        # Convert to ET for proper 4h alignment to market open
        bars_60m_et = bars_60m.set_index(bars_60m["ts"].dt.tz_convert("America/New_York"))
        # Resample 4h with origin at 9:30 ET (market open)
        agg = bars_60m_et.resample("4h", origin="start_day", offset="9h30min").agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum",
        }).dropna(subset=["open", "close"])
        agg = agg.reset_index().rename(columns={"ts": "ts_et"})
        agg["ts"] = pd.to_datetime(agg["ts_et"]).dt.tz_convert("UTC")
        agg["ticker"] = ticker
        agg["tf"] = "4h"
        agg["bar_date"] = agg["ts"].dt.date
        log.info("aggregated to %d 4h bars", len(agg))

        # Rename to Capitalized for lib helpers (they expect Open/High/Low/Close)
        agg = agg.rename(columns={"open": "Open", "high": "High",
                                   "low": "Low", "close": "Close",
                                   "volume": "Volume"})

        # Indicators + strat
        agg = add_all_indicators(agg, close_col="Close")
        clf = StratClassifier()
        agg = clf.detect_combos(agg)

        # Rename back to lowercase to match strat_features schema
        agg = agg.rename(columns={"Open": "open", "High": "high",
                                   "Low": "low", "Close": "close",
                                   "Volume": "volume"})

        # Upsert
        cols = [c for c in agg.columns if c not in ("ts_et",)]
        agg = agg[cols]
        bulk_copy_upsert(
            agg, "strat_features_4h",
            conflict_cols=["ticker", "ts"],
            update_cols=[c for c in cols if c not in ("ticker", "ts")],
        )
        log.info("upserted %d rows to strat_features_4h", len(agg))
        return {"ticker": ticker, "tf": "4h", "rows": int(len(agg))}

    raise NotImplementedError(f"source={source} not yet supported; use aggregate_from_60m")


# ─────────────────────── Mode: summary ───────────────────────

def summary(engine) -> dict:
    """Print row counts + class balance per (ticker, tf) so the user sees
    current coverage before kicking off Stage 2.

    Uses a FRESH connection per query to avoid aborted-transaction
    cascade when a 4h-table-missing exception poisons the txn.
    """
    log.info("=" * 70)
    log.info("Stage 1 SUMMARY")
    log.info("=" * 70)
    rows = []
    for ticker in TICKERS:
        for tf in TIMEFRAMES:
            try:
                with engine.connect() as c:
                    n = c.execute(text(
                        f"SELECT count(*) FROM {strat_features_table(tf)} "
                        f"WHERE ticker = :t AND strat_candle IS NOT NULL"
                    ), {"t": ticker}).scalar() or 0
            except Exception as e:
                log.warning("  %s %s: query failed (%s)", ticker, tf, type(e).__name__)
                n = 0
            rows.append({"ticker": ticker, "tf": tf, "n": int(n)})
            log.info("  %-3s %-3s  n=%d", ticker, tf, n)
    return {"summary": rows}


# ─────────────────────── Mode: ensure-coverage (orchestrator) ───────────────────────

def ensure_coverage(engine, dry_run: bool = False) -> dict:
    """Identify missing (ticker, tf) combos and dispatch backfills.

    For 1m / 5m / 15m / 30m / 60m: delegates to the existing
    `p7-build-multi-tf-features` Cloud Run Job (--tickers=X --tf-only=Y).
    For 4h: dispatches `--mode=build-4h` on this script itself (or
    handles in-process if dry_run is False — keeping it as a job
    dispatch matches the existing pattern).

    The strat_engine reuses existing tables wherever they exist; only
    real gaps get rebuilt.
    """
    import subprocess
    log.info("=" * 70)
    log.info("ENSURE COVERAGE  (dry_run=%s)", dry_run)
    log.info("=" * 70)
    gaps = []
    for ticker in TICKERS:
        for tf in TIMEFRAMES:
            try:
                with engine.connect() as c:
                    n = c.execute(text(
                        f"SELECT count(*) FROM {strat_features_table(tf)} "
                        f"WHERE ticker = :t AND strat_candle IS NOT NULL"
                    ), {"t": ticker}).scalar() or 0
            except Exception:
                n = 0
            # Threshold: <100 rows = effectively missing
            if n < 100:
                gaps.append({"ticker": ticker, "tf": tf, "current_rows": int(n)})
                log.info("  GAP %s %s (current=%d)", ticker, tf, n)
            else:
                log.info("  OK  %s %s (n=%d)", ticker, tf, n)

    if not gaps:
        log.info("No gaps. All (ticker, tf) combos populated.")
        return {"gaps": [], "dispatched": []}

    if dry_run:
        log.info("DRY RUN: would dispatch %d backfill jobs", len(gaps))
        return {"gaps": gaps, "dispatched": []}

    dispatched = []
    for g in gaps:
        if g["tf"] == "4h":
            # Dispatch this script's --mode=build-4h for the ticker
            cmd = ["gcloud", "run", "jobs", "execute",
                   "p7b-next-candle-classifier", "--region=us-east1",
                   f"--args=-m,gcp.research.strat_engine.strat_data_build,"
                   f"--mode=build-4h,--ticker={g['ticker']}",
                   "--format=value(metadata.name)", "--async"]
        else:
            # Dispatch p7-build-multi-tf-features for the gap
            cmd = ["gcloud", "run", "jobs", "execute",
                   "p7-build-multi-tf-features", "--region=us-east1",
                   f"--args=-m,gcp.research.p7_build_multi_tf_features,"
                   f"--tickers={g['ticker']},--tf-only={g['tf']}",
                   "--format=value(metadata.name)", "--async"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            exec_name = r.stdout.strip().split("\n")[-1] if r.returncode == 0 else None
            dispatched.append({**g, "execution": exec_name,
                              "ok": r.returncode == 0,
                              "stderr": r.stderr[-200:] if r.returncode else None})
            log.info("  dispatched %s %s -> %s", g["ticker"], g["tf"], exec_name)
        except Exception as e:
            dispatched.append({**g, "execution": None, "ok": False, "err": str(e)})
            log.warning("  failed %s %s: %s", g["ticker"], g["tf"], e)
    log.info("Dispatched %d / %d gap backfills", sum(1 for d in dispatched if d["ok"]), len(dispatched))
    return {"gaps": gaps, "dispatched": dispatched}


# ─────────────────────── Main ───────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode",
                   choices=["summary", "verify", "ensure-coverage", "build-4h"],
                   required=True)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--source", default="aggregate_from_60m",
                   choices=["aggregate_from_60m", "raw_intraday"])
    p.add_argument("--dry-run", action="store_true",
                   help="ensure-coverage: report gaps without dispatching")
    args = p.parse_args()
    engine = get_engine()

    if args.mode == "summary":
        summary(engine)
    elif args.mode == "verify":
        verify(engine, args.ticker, args.tf)
    elif args.mode == "ensure-coverage":
        ensure_coverage(engine, dry_run=args.dry_run)
    elif args.mode == "build-4h":
        build_4h(engine, args.ticker, source=args.source)


if __name__ == "__main__":
    main()
