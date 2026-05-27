"""Options exec backtest — Cloud Run Job entry point.

Modes:
  --mode=emit_timestamps  : run the type model on SPY × cells × test
                            windows 2022-2026, write a CSV of unique
                            5-min-rounded setup timestamps. Input for
                            the AV intraday backfill fetcher.
  --mode=base             : Variant 0 — ATM 0DTE call (long) / put (short)
  --mode=variant_otm      : Variant 1 — +1 OTM strike, 0DTE
  --mode=variant_1dte     : Variant 2 — ATM, 1DTE

Outputs (Cloud Run Job mode writes to GCS):
  gs://${GCS_BUCKET}/research/options_exec_backtest/{run_id}/results.json
  gs://${GCS_BUCKET}/research/options_exec_backtest/{run_id}/trades.csv.gz
  gs://${GCS_BUCKET}/research/options_exec_backtest/{run_id}/per_fold.csv
  gs://${GCS_BUCKET}/research/options_exec_backtest/{run_id}/setup_timestamps.csv (emit mode)

Local mode (--out=/tmp/...) writes the same files to disk.
"""
from __future__ import annotations
import argparse
import gzip
import io
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import get_engine
from lib.logging_config import setup_logging
from lib.options_exec_backtest.runner import (
    DEFAULT_CUTOFFS, TIME_STOP_BY_CELL, POSITIVE_FOLD_THRESHOLD,
    emit_setup_timestamps, load_1m_spy, run_one_cell,
    trades_to_dataframe, evaluate_base_case_per_cell,
)

setup_logging()
log = logging.getLogger(__name__)

BUCKET_DEFAULT = "adept-mountain-474619-d4-trading-data"
GCS_PREFIX = "research/options_exec_backtest"


def _gcs_upload(content: bytes, blob_path: str, ctype: str = "application/octet-stream"):
    from google.cloud import storage as gcs
    bucket = os.environ.get("GCS_BUCKET", BUCKET_DEFAULT)
    gcs.Client().bucket(bucket).blob(blob_path).upload_from_string(content, content_type=ctype)
    return f"gs://{bucket}/{blob_path}"


def _local_write(content: bytes, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(content)
    return str(Path(path).resolve())


def _run_id() -> str:
    return (os.environ.get("CLOUD_RUN_EXECUTION")
            or os.environ.get("OPTIONS_EXEC_RUN_ID")
            or f"run_{int(time.time())}")


def _write_output(content: bytes, name: str, out_local_dir: str | None,
                   gcs_subdir: str, ctype: str = "application/octet-stream") -> str:
    if out_local_dir:
        return _local_write(content, str(Path(out_local_dir) / name))
    blob = f"{GCS_PREFIX}/{gcs_subdir}/{name}"
    return _gcs_upload(content, blob, ctype=ctype)


def run_emit_timestamps(args, engine):
    """Mode 1: emit setup timestamps for the AV backfill."""
    out_csv = args.timestamps_out or "/tmp/spy_setup_timestamps.csv"
    n = emit_setup_timestamps(
        engine,
        ticker=args.ticker,
        cells=args.cells.split(","),
        cutoffs=DEFAULT_CUTOFFS,
        confidence=args.confidence,
        output_csv=out_csv,
    )
    log.info("✓ wrote %d unique timestamps to %s", n, out_csv)
    # Also upload to GCS if no local dir
    if args.out:
        return
    with open(out_csv, "rb") as f:
        content = f.read()
    blob = f"{GCS_PREFIX}/{_run_id()}/setup_timestamps.csv"
    uri = _gcs_upload(content, blob, ctype="text/csv")
    log.info("✓ uploaded %s", uri)


def run_backtest(args, engine):
    """Mode 2/3/4: run the full backtest in the requested variant."""
    if args.mode == "variant_otm":
        otm_offset = 1
        expiration_dte = 0
        variant_label = "variant_otm"
    elif args.mode == "variant_1dte":
        otm_offset = 0
        expiration_dte = 1
        variant_label = "variant_1dte"
    else:
        otm_offset = 0
        expiration_dte = 0
        variant_label = "base"

    log.info("loading 1m SPY bars …")
    m1_bars = load_1m_spy(engine, start_date="2021-06-01")

    cells = args.cells.split(",")
    all_trades = []
    all_per_fold = []
    per_cell_verdict = {}

    for cell in cells:
        trades, per_fold = run_one_cell(
            engine=engine,
            ticker=args.ticker,
            cell=cell,
            m1_bars=m1_bars,
            cutoffs=DEFAULT_CUTOFFS,
            confidence=args.confidence,
            target_multiple=args.target,
            otm_offset=otm_offset,
            expiration_dte=expiration_dte,
        )
        all_trades.extend(trades)
        all_per_fold.extend(per_fold)
        verdict = evaluate_base_case_per_cell(per_fold)
        per_cell_verdict[cell] = verdict
        log.info("CELL %s verdict: %s — pos_exp=%s/%s  net_exp=$%.4f  asym=%.3f",
                 cell, verdict["verdict"],
                 verdict.get("pos_exp_folds"), verdict.get("n_folds"),
                 verdict.get("weighted_net_exp", 0.0),
                 verdict.get("asymm_ratio", 0.0))

    # Aggregate results
    trades_df = trades_to_dataframe(all_trades)
    per_fold_df = pd.DataFrame(all_per_fold)
    log.info("─" * 70)
    log.info("AGGREGATE: %d trades across %d cells", len(trades_df), len(cells))
    for cell, v in per_cell_verdict.items():
        log.info("  %s: %s", cell, v["verdict"])

    overall_verdict = "PASS" if all(v["verdict"] == "PASS"
                                     for v in per_cell_verdict.values()) else "FAIL"
    log.info("OVERALL %s: %s", variant_label.upper(), overall_verdict)

    # Persist outputs
    run_id = _run_id()
    subdir = f"{run_id}/{variant_label}"

    # 1. results.json
    results = {
        "variant": variant_label,
        "verdict": overall_verdict,
        "ticker": args.ticker,
        "cells": cells,
        "cutoffs": DEFAULT_CUTOFFS,
        "confidence": args.confidence,
        "target_multiple": args.target,
        "otm_offset": otm_offset,
        "expiration_dte": expiration_dte,
        "per_cell_verdict": per_cell_verdict,
        "trade_count": int(len(trades_df)),
        "positive_fold_threshold": POSITIVE_FOLD_THRESHOLD,
    }
    _write_output(
        json.dumps(results, indent=2, default=str).encode(),
        "results.json", args.out, subdir, ctype="application/json",
    )

    # 2. per_fold.csv
    if not per_fold_df.empty:
        # Drop the nested 'voided' dict for the CSV; preserve in JSON
        per_fold_df_csv = per_fold_df.copy()
        if "voided" in per_fold_df_csv.columns:
            per_fold_df_csv["voided"] = per_fold_df_csv["voided"].astype(str)
        buf = io.BytesIO()
        per_fold_df_csv.to_csv(buf, index=False)
        _write_output(buf.getvalue(), "per_fold.csv", args.out, subdir, ctype="text/csv")

    # 3. trades.csv.gz
    if not trades_df.empty:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            trades_df.to_csv(gz, index=False)
        _write_output(buf.getvalue(), "trades.csv.gz", args.out, subdir,
                      ctype="application/gzip")

    return overall_verdict


def main():
    parser = argparse.ArgumentParser(description="Options exec backtest CLI.")
    parser.add_argument("--mode", choices=["emit_timestamps", "base", "variant_otm",
                                            "variant_1dte"],
                        default="base")
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--cells", default="5m,15m,30m",
                        help="Comma-separated cells (default: 5m,15m,30m)")
    parser.add_argument("--confidence", type=float, default=0.55,
                        help="Type-model top_prob threshold (FROZEN at 0.55 per brief)")
    parser.add_argument("--target", type=float, default=1.5,
                        help="Target multiple in underlying-R (FROZEN at 1.5 per brief)")
    parser.add_argument("--out", default=None,
                        help="Local output dir. If unset, write to GCS.")
    parser.add_argument("--timestamps-out", default=None,
                        help="CSV path for emit_timestamps mode "
                             "(default: /tmp/spy_setup_timestamps.csv)")
    args = parser.parse_args()

    # Hard guardrail: per the brief, type-model thresholds are frozen.
    if args.confidence != 0.55:
        log.warning("Brief froze confidence at 0.55; you passed %s. Continuing but flagging.",
                    args.confidence)
    if args.target != 1.5:
        log.warning("Brief froze target at 1.5R; you passed %s. Continuing but flagging.",
                    args.target)

    engine = get_engine()

    if args.mode == "emit_timestamps":
        run_emit_timestamps(args, engine)
    else:
        run_backtest(args, engine)


if __name__ == "__main__":
    main()
