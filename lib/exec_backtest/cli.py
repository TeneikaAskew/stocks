"""Exec backtest — Cloud Run Job entry point.

Runs the base case for IWM × {5m, 15m, 30m} across all 8 walk-forward folds.
Saves outputs to GCS:
  - gs://${GCS_BUCKET}/research/exec_backtest/{run_id}/results.json
  - gs://${GCS_BUCKET}/research/exec_backtest/{run_id}/trades.csv
  - gs://${GCS_BUCKET}/research/exec_backtest/{run_id}/per_fold.csv

Decision logic:
  1. Run BASE case (no FTFC, conf=0.55, 1.5R, time stop 30/60).
  2. Evaluate per-cell pass/fail with the four-condition spec bar.
  3. If ANY cell passed or was borderline (within 25% on every check),
     run variants on the candidate cell(s).
  4. Surface the FINAL verdict to stdout AND to the JSON output.

Variants only run when explicitly requested by --mode=variants and a
cell name. The orchestrator (the surrounding analysis script) decides
whether to dispatch variants based on the base-case JSON.

Usage (Cloud Run Job):
  python -m lib.exec_backtest.cli \
    --mode=base \
    --confidence=0.55 \
    --target=1.5

  python -m lib.exec_backtest.cli \
    --mode=variant_ftfc \
    --confidence=0.55 \
    --target=1.5 \
    --cells=15m,30m
"""
from __future__ import annotations
import argparse
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
from lib.exec_backtest.runner import (
    DEFAULT_CUTOFFS, TIME_STOP_BY_CELL,
    load_1m_iwm, run_one_cell, trades_to_dataframe,
    evaluate_base_case_per_cell,
)
from lib.exec_backtest.ftfc import build_ftfc_lookup
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


BUCKET_DEFAULT = "adept-mountain-474619-d4-trading-data"
GCS_PREFIX = "research/exec_backtest"


def _gcs_upload(content: bytes, blob_path: str, ctype="application/octet-stream"):
    from google.cloud import storage as gcs
    bucket = os.environ.get("GCS_BUCKET", BUCKET_DEFAULT)
    gcs.Client().bucket(bucket).blob(blob_path).upload_from_string(content, content_type=ctype)
    return f"gs://{bucket}/{blob_path}"


def _run_id() -> str:
    return (os.environ.get("CLOUD_RUN_EXECUTION")
            or os.environ.get("EXEC_BACKTEST_RUN_ID")
            or f"run_{int(time.time())}")


def run_base(confidence: float, target_multiple: float,
             cells: list, cutoffs: list, m1_bars, engine,
             write_gcs: bool = True) -> dict:
    """Run base case on all requested cells. Returns nested result dict."""
    log.info("=" * 70)
    log.info("EXEC BACKTEST  BASE CASE  conf=%.2f  target=%.1fR  cells=%s",
             confidence, target_multiple, ",".join(cells))
    log.info("=" * 70)

    all_results = {}
    all_trades_df_parts = []
    all_per_fold_parts = []

    for cell in cells:
        trades, per_fold = run_one_cell(
            engine, cell, m1_bars, cutoffs,
            confidence=confidence, target_multiple=target_multiple,
            apply_ftfc_filter=False,
        )
        cell_df = trades_to_dataframe(trades)
        per_fold_df = pd.DataFrame(per_fold)
        all_trades_df_parts.append(cell_df)
        all_per_fold_parts.append(per_fold_df)

        verdict = evaluate_base_case_per_cell(per_fold)
        all_results[cell] = {
            "per_fold": per_fold,
            "verdict": verdict,
            "n_trades": int(len(trades)),
        }
        log.info("=" * 70)
        log.info("CELL %s  VERDICT: %s", cell, verdict["verdict"])
        for k, v in verdict.get("checks", {}).items():
            log.info("  %-20s value=%.4f  thresh=%.4f  %s",
                     k, v[0] if isinstance(v[0], (int, float)) else 0.0,
                     v[1] if isinstance(v[1], (int, float)) else 0.0,
                     "PASS" if v[2] else "FAIL")

    trades_df = pd.concat(all_trades_df_parts, ignore_index=True) if all_trades_df_parts else pd.DataFrame()
    per_fold_df = pd.concat(all_per_fold_parts, ignore_index=True) if all_per_fold_parts else pd.DataFrame()

    run_id = _run_id()
    if write_gcs:
        results_blob = f"{GCS_PREFIX}/{run_id}/base_results.json"
        trades_blob = f"{GCS_PREFIX}/{run_id}/base_trades.csv"
        per_fold_blob = f"{GCS_PREFIX}/{run_id}/base_per_fold.csv"

        _gcs_upload(json.dumps(all_results, indent=2, default=str).encode(),
                    results_blob, "application/json")
        if not trades_df.empty:
            csv_buf = io.StringIO()
            trades_df.to_csv(csv_buf, index=False)
            _gcs_upload(csv_buf.getvalue().encode(), trades_blob, "text/csv")
        if not per_fold_df.empty:
            csv_buf = io.StringIO()
            per_fold_df.to_csv(csv_buf, index=False)
            _gcs_upload(csv_buf.getvalue().encode(), per_fold_blob, "text/csv")
        log.info("uploaded base results to gs://%s/%s/", BUCKET_DEFAULT, f"{GCS_PREFIX}/{run_id}")

    # Also dump to stdout for in-line console capture
    print("\n" + "=" * 70)
    print("EXEC BACKTEST — BASE CASE SUMMARY")
    print("=" * 70)
    for cell, r in all_results.items():
        v = r["verdict"]
        print(f"\nCell {cell}: {v['verdict']}  n_trades={r['n_trades']}  "
              f"weighted_net_exp=${v.get('weighted_net_exp', 0):.4f}  "
              f"hit_rate={v.get('overall_hit_rate', 0):.3f}  "
              f"pos_exp_folds={v.get('pos_exp_folds', 0)}/{v.get('n_folds', 0)}")
        for chk_name, chk in v.get("checks", {}).items():
            val, thresh, pas = chk
            print(f"   {chk_name}: value={val:.4f} thresh={thresh:.4f} "
                  f"{'PASS' if pas else 'FAIL'}")

    return {"base": all_results, "run_id": run_id,
            "trades_df": trades_df, "per_fold_df": per_fold_df}


def run_variants(passed_cells: list, confidence: float, target_multiple: float,
                  cutoffs: list, m1_bars, engine, base_results: dict,
                  variants: list, write_gcs: bool = True) -> dict:
    """Run requested variants ONLY on the cells that passed the base case.

    Variants (one knob at a time):
      v1_ftfc:      add FTFC alignment filter (score >= 0.5)
      v2_conf065:   raise confidence threshold to 0.65
      v3_target20:  raise target multiple to 2.0R
    """
    log.info("=" * 70)
    log.info("EXEC BACKTEST  VARIANTS=%s  cells=%s",
             ",".join(variants), ",".join(passed_cells))
    log.info("=" * 70)

    # Pre-compute FTFC lookup ONCE per call.
    ftfc_lookup = build_ftfc_lookup(m1_bars) if "v1_ftfc" in variants else None

    out = {}
    for v in variants:
        out[v] = {}
        for cell in passed_cells:
            if v == "v1_ftfc":
                trades, pf = run_one_cell(
                    engine, cell, m1_bars, cutoffs,
                    confidence=confidence, target_multiple=target_multiple,
                    apply_ftfc_filter=True, ftfc_threshold=0.5,
                    ftfc_lookup=ftfc_lookup)
            elif v == "v2_conf065":
                trades, pf = run_one_cell(
                    engine, cell, m1_bars, cutoffs,
                    confidence=0.65, target_multiple=target_multiple,
                    apply_ftfc_filter=False)
            elif v == "v3_target20":
                trades, pf = run_one_cell(
                    engine, cell, m1_bars, cutoffs,
                    confidence=confidence, target_multiple=2.0,
                    apply_ftfc_filter=False)
            else:
                continue
            verdict = evaluate_base_case_per_cell(pf)
            out[v][cell] = {
                "per_fold": pf, "verdict": verdict,
                "n_trades": int(len(trades)),
            }
            log.info("VARIANT %s CELL %s  VERDICT=%s  n=%d",
                     v, cell, verdict["verdict"], len(trades))

    run_id = _run_id()
    if write_gcs:
        blob = f"{GCS_PREFIX}/{run_id}/variants_results.json"
        _gcs_upload(json.dumps(out, indent=2, default=str).encode(),
                    blob, "application/json")
        log.info("uploaded variants to gs://%s/%s", BUCKET_DEFAULT, blob)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["base", "variants", "full"],
                   default="full",
                   help="base = run base only; variants = run variants on cells from "
                        "previous run; full = base + (variants if any cell passes)")
    p.add_argument("--cells", default="5m,15m,30m",
                   help="Comma-separated cells (default: 5m,15m,30m)")
    p.add_argument("--confidence", type=float, default=0.55)
    p.add_argument("--target", type=float, default=1.5,
                   help="Profit target multiple (R)")
    p.add_argument("--variants",
                   default="v1_ftfc,v2_conf065,v3_target20",
                   help="Variants to run, comma-separated.")
    p.add_argument("--m1-start-date", default="2018-01-01",
                   help="Earliest date for 1m IWM bar load (must precede "
                        "first fold's cutoff). Default 2018-01-01.")
    p.add_argument("--no-gcs", action="store_true",
                   help="Skip GCS upload (for local testing)")
    args = p.parse_args()

    cells = [c.strip() for c in args.cells.split(",") if c.strip()]
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    write_gcs = not args.no_gcs

    engine = get_engine()
    log.info("loading 1m IWM bars …")
    m1_bars = load_1m_iwm(engine, start_date=args.m1_start_date)

    base_out = run_base(
        confidence=args.confidence, target_multiple=args.target,
        cells=cells, cutoffs=DEFAULT_CUTOFFS, m1_bars=m1_bars,
        engine=engine, write_gcs=write_gcs,
    )

    if args.mode == "base":
        print("\nDONE (mode=base). Variants NOT dispatched.")
        return

    # Determine eligibility for variants. Spec: variants run only if base
    # PASSES or is BORDERLINE on at least one cell. We treat "borderline"
    # as: passed conditions 1, 3, 4 but missed c2 (net expectancy) by
    # <= 50% — i.e. the only failure is a small expectancy miss.
    candidates = []
    for cell, r in base_out["base"].items():
        v = r["verdict"]
        if v["verdict"] == "PASS":
            candidates.append(cell)
            continue
        checks = v.get("checks", {})
        if not checks:
            continue
        c1 = checks.get("c1_pos_exp_folds", (0, 0, False))[2]
        c2_val, c2_thr, c2_pass = checks.get("c2_agg_net_exp", (0, 0, False))
        c3 = checks.get("c3_hit_rate", (0, 0, False))[2]
        c4 = checks.get("c4_no_dom", (0, 0, False))[2]
        c2_borderline = (not c2_pass) and (c2_val >= 0.01)  # within 50% of 2¢
        if c1 and c3 and c4 and c2_borderline:
            candidates.append(cell)

    if not candidates:
        print("\nNo cells passed base case (and none borderline). "
              "Per spec: variants NOT run. Verdict = FAIL.")
        return

    log.info("BASE-CASE PASS/BORDERLINE cells eligible for variants: %s",
             ",".join(candidates))

    run_variants(
        passed_cells=candidates,
        confidence=args.confidence, target_multiple=args.target,
        cutoffs=DEFAULT_CUTOFFS, m1_bars=m1_bars, engine=engine,
        base_results=base_out["base"], variants=variants,
        write_gcs=write_gcs,
    )


if __name__ == "__main__":
    main()
