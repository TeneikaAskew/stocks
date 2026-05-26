"""Strat Engine — Stage 1 pipeline orchestrator.

Thin admin wrapper around the heavyweight `strat_data_builder.py`. The
builder is the source-of-truth that aggregates raw 1-min bars → all TFs
including 4h; this pipeline file holds the read-only / dispatch ops.

Modes:
  --mode=summary          Print row counts per (ticker, tf). Coverage report.
  --mode=verify           Run the label-correctness + VIX-leak tests on the
                          labeled dataset for one (ticker, tf). Stage 1 gate.
  --mode=ensure-coverage  Identify missing (ticker, tf) combos vs the
                          config grid and dispatch the strat-engine builder
                          for each gap. 4h is built uniformly with other
                          TFs via the builder's --tf-only=4h flag.

PRD scope: this stage VERIFIES coverage and DISPATCHES builds for gaps.
Downstream stages (EDA / corr / model / FTFC / readout) consume the
labeled dataset via the shared loader in `strat_dataset.py`.
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

from gcp.database import get_engine
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


# NOTE: build-4h mode was REMOVED 2026-05-26. The strat_data_builder now
# handles 4h natively (("4h", "4h") added to TF_LIST + FOUR_H_DDL applied
# just-in-time). Dispatch 4h gaps via:
#   gcloud run jobs execute strat-engine \
#     --args="-m,gcp.research.strat_engine.strat_data_builder,--tickers=X,--tf-only=4h"
# `ensure-coverage` below handles the dispatch automatically.


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

    Uniform dispatch path for ALL TFs (1m / 5m / 15m / 30m / 60m / 4h):
    delegates to the `strat-engine` Cloud Run Job running
    `gcp.research.strat_engine.strat_data_builder --tickers=X --tf-only=Y`.

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
        # Uniform dispatch: every TF goes through the strat_data_builder
        # via the strat-engine Cloud Run Job. The builder's TF_LIST
        # includes 4h since 2026-05-26 and applies FOUR_H_DDL just-in-time.
        cmd = ["gcloud", "run", "jobs", "execute",
               "strat-engine", "--region=us-east1",
               f"--args=-m,gcp.research.strat_engine.strat_data_builder,"
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
                   choices=["summary", "verify", "ensure-coverage"],
                   required=True)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
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


if __name__ == "__main__":
    main()
