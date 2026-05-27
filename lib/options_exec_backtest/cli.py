"""Options exec backtest — Cloud Run Job entry point.

Modes:
  --mode=emit_timestamps  : run the type model on `--ticker` × cells ×
                            the UNION test window (2022-2026 = 5fold).
                            Always emits the wider range so the same
                            AV intraday backfill covers both window
                            backtests. Writes a CSV of unique 5-min-
                            rounded setup timestamps.
  --mode=base             : Variant 0 — ATM 0DTE call (long) / put (short)
  --mode=variant_otm      : Variant 1 — +1 OTM strike, 0DTE
  --mode=variant_1dte     : Variant 2 — ATM, 1DTE

Walk-forward window (`--folds-mode`):
  - 5fold (2022-2026, ≥4/5 bar) — wider regime variety, partial 0DTE
    coverage in 2022-2023 (IWM Mon/Wed/Fri only; Tue/Thu setups void).
  - 3fold (2024-2026, ≥2/3 bar) — clean 99% coverage, single-bull sample.
  - both (default) — run both windows in one job, emit separate ledgers.
    Output subdirs `{variant}_5fold/` and `{variant}_3fold/`.

Outputs (Cloud Run Job mode writes to GCS):
  gs://${GCS_BUCKET}/research/options_exec_backtest/{run_id}/{variant}_{window}/results.json
  gs://${GCS_BUCKET}/research/options_exec_backtest/{run_id}/{variant}_{window}/trades.csv.gz
  gs://${GCS_BUCKET}/research/options_exec_backtest/{run_id}/{variant}_{window}/per_fold.csv
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
    DEFAULT_CUTOFFS, TIME_STOP_BY_CELL, POSITIVE_FOLD_THRESHOLD, WINDOWS,
    emit_setup_timestamps, load_1m_bars, run_one_cell,
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
    """Mode 1: emit setup timestamps for the AV backfill.

    Always emits the WIDER window (5fold = 2022-2026). The 3fold
    window is a subset, so one fetcher pass covers both.

    Writes to GCS at TWO paths when running as a Cloud Run Job:
      - {prefix}/setup_timestamps.csv (STABLE — the AV fetcher reads
        from here by default; latest emit overwrites)
      - {prefix}/{run_id}/setup_timestamps.csv (archival — per-run copy)

    Local mode (--out=...) writes only locally.
    """
    out_csv = args.timestamps_out or f"/tmp/{args.ticker.lower()}_setup_timestamps.csv"
    n = emit_setup_timestamps(
        engine,
        ticker=args.ticker,
        cells=args.cells.split(","),
        cutoffs=WINDOWS["5fold"]["cutoffs"],
        confidence=args.confidence,
        output_csv=out_csv,
    )
    log.info("✓ wrote %d unique timestamps to %s", n, out_csv)
    if args.out:
        return
    with open(out_csv, "rb") as f:
        content = f.read()
    archival = f"{GCS_PREFIX}/{_run_id()}/setup_timestamps.csv"
    stable = f"{GCS_PREFIX}/setup_timestamps.csv"
    uri_archival = _gcs_upload(content, archival, ctype="text/csv")
    uri_stable = _gcs_upload(content, stable, ctype="text/csv")
    log.info("✓ uploaded archival copy: %s", uri_archival)
    log.info("✓ uploaded STABLE handoff path (AV fetcher reads from here): %s", uri_stable)


def _resolve_variant(mode: str) -> tuple[int, int, str]:
    if mode == "variant_otm":
        return 1, 0, "variant_otm"
    if mode == "variant_1dte":
        return 0, 1, "variant_1dte"
    return 0, 0, "base"


def _run_one_window(
    engine, args, m1_bars, variant_label: str,
    otm_offset: int, expiration_dte: int, window_name: str,
    cutoffs: list[str], positive_fold_threshold: int,
    run_id: str,
) -> str:
    """Run all cells for ONE walk-forward window, persist its ledger,
    return the overall verdict.
    """
    cells = args.cells.split(",")
    log.info("═" * 70)
    log.info("WINDOW %s — %d folds, ≥%d positive bar — cutoffs=%s",
             window_name, len(cutoffs), positive_fold_threshold, cutoffs)
    all_trades = []
    all_per_fold = []
    per_cell_verdict = {}

    for cell in cells:
        trades, per_fold = run_one_cell(
            engine=engine,
            ticker=args.ticker,
            cell=cell,
            m1_bars=m1_bars,
            cutoffs=cutoffs,
            confidence=args.confidence,
            target_multiple=args.target,
            otm_offset=otm_offset,
            expiration_dte=expiration_dte,
        )
        all_trades.extend(trades)
        all_per_fold.extend(per_fold)
        verdict = evaluate_base_case_per_cell(
            per_fold, positive_fold_threshold=positive_fold_threshold,
        )
        per_cell_verdict[cell] = verdict
        log.info("[%s] CELL %s verdict: %s — pos_exp=%s/%s  net_exp=$%.4f  asym=%.3f",
                 window_name, cell, verdict["verdict"],
                 verdict.get("pos_exp_folds"), verdict.get("n_folds"),
                 verdict.get("weighted_net_exp", 0.0),
                 verdict.get("asymm_ratio", 0.0))

    trades_df = trades_to_dataframe(all_trades)
    per_fold_df = pd.DataFrame(all_per_fold)
    log.info("─" * 70)
    log.info("[%s] AGGREGATE: %d trades across %d cells",
             window_name, len(trades_df), len(cells))
    for cell, v in per_cell_verdict.items():
        log.info("  %s: %s", cell, v["verdict"])

    overall_verdict = "PASS" if all(v["verdict"] == "PASS"
                                     for v in per_cell_verdict.values()) else "FAIL"
    log.info("[%s] OVERALL %s: %s", window_name, variant_label.upper(),
             overall_verdict)

    subdir = f"{run_id}/{variant_label}_{window_name}"

    results = {
        "variant": variant_label,
        "window": window_name,
        "verdict": overall_verdict,
        "ticker": args.ticker,
        "cells": cells,
        "cutoffs": cutoffs,
        "confidence": args.confidence,
        "target_multiple": args.target,
        "otm_offset": otm_offset,
        "expiration_dte": expiration_dte,
        "positive_fold_threshold": positive_fold_threshold,
        "per_cell_verdict": per_cell_verdict,
        "trade_count": int(len(trades_df)),
    }
    _write_output(
        json.dumps(results, indent=2, default=str).encode(),
        "results.json", args.out, subdir, ctype="application/json",
    )

    if not per_fold_df.empty:
        per_fold_df_csv = per_fold_df.copy()
        if "voided" in per_fold_df_csv.columns:
            per_fold_df_csv["voided"] = per_fold_df_csv["voided"].astype(str)
        buf = io.BytesIO()
        per_fold_df_csv.to_csv(buf, index=False)
        _write_output(buf.getvalue(), "per_fold.csv", args.out, subdir,
                      ctype="text/csv")

    if not trades_df.empty:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            trades_df.to_csv(gz, index=False)
        _write_output(buf.getvalue(), "trades.csv.gz", args.out, subdir,
                      ctype="application/gzip")

    return overall_verdict


def _windows_to_run(folds_mode: str) -> list[str]:
    if folds_mode == "both":
        return ["3fold", "5fold"]
    if folds_mode in WINDOWS:
        return [folds_mode]
    raise ValueError(f"Unknown --folds-mode={folds_mode!r}")


def run_backtest(args, engine):
    """Mode 2/3/4: run the full backtest in the requested variant.

    Loads m1 bars ONCE (big query), then runs the backtest for each
    selected window (5fold / 3fold / both) reusing the same bars.
    """
    otm_offset, expiration_dte, variant_label = _resolve_variant(args.mode)
    windows = _windows_to_run(args.folds_mode)
    log.info("running variant=%s across windows=%s", variant_label, windows)

    log.info("loading 1m %s bars …", args.ticker)
    m1_bars = load_1m_bars(engine, ticker=args.ticker, start_date="2021-06-01")

    run_id = _run_id()
    verdicts = {}
    for window_name in windows:
        cfg = WINDOWS[window_name]
        verdicts[window_name] = _run_one_window(
            engine=engine, args=args, m1_bars=m1_bars,
            variant_label=variant_label,
            otm_offset=otm_offset, expiration_dte=expiration_dte,
            window_name=window_name,
            cutoffs=cfg["cutoffs"],
            positive_fold_threshold=cfg["positive_fold_threshold"],
            run_id=run_id,
        )

    log.info("═" * 70)
    log.info("WINDOW VERDICTS — variant=%s", variant_label)
    for w, v in verdicts.items():
        log.info("  %s: %s", w, v)
    return verdicts


def main():
    parser = argparse.ArgumentParser(description="Options exec backtest CLI.")
    parser.add_argument("--mode", choices=["emit_timestamps", "base", "variant_otm",
                                            "variant_1dte"],
                        default="base")
    parser.add_argument("--ticker", default="IWM",
                        help="Underlying (IWM default — Track B parity). "
                             "Also supports SPY, QQQ.")
    parser.add_argument("--folds-mode", choices=["5fold", "3fold", "both"],
                        default="both",
                        help="Walk-forward window. 'both' (default) runs 3fold "
                             "(2024-2026, ≥2/3 bar, clean 0DTE coverage) AND "
                             "5fold (2022-2026, ≥4/5 bar, wider regime variety "
                             "with partial 0DTE coverage in 22-23).")
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
                             "(default: /tmp/{ticker_lower}_setup_timestamps.csv)")
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
