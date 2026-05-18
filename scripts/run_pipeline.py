#!/usr/bin/env python3
"""
End-to-end backtest pipeline.

Runs backtests (base + strat), timeframe sweeps, and report generation
for all configured tickers in a single command.

Usage:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --tickers IWM SPY
    python scripts/run_pipeline.py --skip-sweep
    python scripts/run_pipeline.py --report-only
"""

import argparse
import logging
import subprocess
import sys
import time
import uuid
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DEFAULT_TICKERS = ["IWM", "SPY", "QQQ"]


log = logging.getLogger("pipeline")


def run_step(cmd: list[str], label: str) -> bool:
    """Run a subprocess, printing its output in real time. Returns True on success."""
    log.info("START: %s", label)
    t0 = time.time()
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    elapsed = time.time() - t0
    ok = result.returncode == 0
    if ok:
        log.info("OK: %s (%.0fs)", label, elapsed)
    else:
        log.error("FAILED: %s (%.0fs, exit %d)", label, elapsed, result.returncode)
    return ok


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end backtest pipeline: backtest + sweep + report"
    )
    parser.add_argument(
        "--tickers", nargs="+", default=DEFAULT_TICKERS,
        help="Tickers to process (default: IWM SPY QQQ)",
    )
    parser.add_argument(
        "--skip-sweep", action="store_true",
        help="Skip the timeframe sweep (faster)",
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help=("Only regenerate the report from an existing run's rows in "
              "the backtest tables (requires --run-id)"),
    )
    parser.add_argument(
        "--sweep-only", action="store_true",
        help=("Only re-run the timeframe sweep + report for an existing "
              "run, reusing that run's base/strat trades from "
              "backtest_trades (requires --run-id). Use after a change "
              "that affects only the sweep — skips the ~2h of base/strat "
              "backtests."),
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output path for the report (default: BACKTEST_RESULTS.md)",
    )
    parser.add_argument(
        "--run-id", type=str, default=None,
        help=("Pipeline run UUID. Threaded through every sub-step so all "
              "rows from one run share an id in the backtest_* tables. "
              "Defaults to a fresh uuid4."),
    )
    args = parser.parse_args()

    python = sys.executable
    tickers = args.tickers
    failed: list[str] = []

    # One run_id for the whole pipeline. Every sub-step receives it via
    # --run-id so backtest_trades / backtest_sweeps / backtest_reports
    # rows all join on it. --report-only re-runs against an EXISTING run,
    # so the caller must pass --run-id in that mode (a fresh uuid would
    # find no rows). For a fresh full run, a generated uuid is correct.
    if args.report_only and not args.run_id:
        log.error("--report-only requires --run-id (the run to report on); "
                  "a fresh uuid would match no rows in backtest_trades.")
        sys.exit(2)
    # --sweep-only reuses an existing run's base/strat trades, so it too
    # needs an explicit --run-id. It's mutually exclusive with the other
    # two scoping flags.
    if args.sweep_only and not args.run_id:
        log.error("--sweep-only requires --run-id (the run whose base/strat "
                  "trades to reuse); a fresh uuid would match no rows.")
        sys.exit(2)
    if args.sweep_only and args.report_only:
        log.error("--sweep-only and --report-only are mutually exclusive.")
        sys.exit(2)
    if args.sweep_only and args.skip_sweep:
        log.error("--sweep-only with --skip-sweep would run nothing.")
        sys.exit(2)
    run_id = args.run_id or str(uuid.uuid4())

    log.info("Pipeline: run_id=%s  tickers=%s  skip_sweep=%s  "
             "report_only=%s  sweep_only=%s",
             run_id, tickers, args.skip_sweep, args.report_only,
             args.sweep_only)
    t_start = time.time()

    # Step gating:
    #   full          → backtests + sweep + report
    #   --skip-sweep   → backtests + report
    #   --sweep-only   → sweep + report   (reuses existing base/strat trades)
    #   --report-only  → report
    run_backtests = not (args.report_only or args.sweep_only)
    run_sweep = not (args.report_only or args.skip_sweep)

    if run_backtests:
        # --- Step 1: Base backtests (no Strat) ---
        for ticker in tickers:
            ok = run_step(
                [python, str(SCRIPTS_DIR / "run_backtest.py"),
                 "--ticker", ticker, "--run-id", run_id],
                f"Backtest {ticker} (base)",
            )
            if not ok:
                failed.append(f"backtest-base-{ticker}")

        # --- Step 2: Strat backtests (FTFC + ORB) ---
        for ticker in tickers:
            ok = run_step(
                [python, str(SCRIPTS_DIR / "run_backtest.py"),
                 "--ticker", ticker, "--use-strat", "--run-id", run_id],
                f"Backtest {ticker} (strat)",
            )
            if not ok:
                failed.append(f"backtest-strat-{ticker}")

    if run_sweep:
        # --- Step 3: Timeframe sweeps ---
        # --all-combos runs Phase 3 — every coarser-entry-TF + higher-TF-filter
        # pair (5m+15m, 5m+30m, 5m+1h, 15m+30m, 15m+1h, 30m+1h), not just the
        # 1m-anchored Phase 2 combos. The pipeline is the comprehensive
        # backtest surface, so it always runs the full matrix; the coarser
        # entry TFs have far fewer bars than 1m so the extra wall-clock is
        # modest (~15-25 min/ticker) and well inside the 8h job timeout.
        for ticker in tickers:
            ok = run_step(
                [python, str(SCRIPTS_DIR / "run_timeframe_sweep.py"),
                 "--ticker", ticker, "--use-strat", "--all-combos",
                 "--run-id", run_id],
                f"Timeframe sweep {ticker}",
            )
            if not ok:
                failed.append(f"sweep-{ticker}")

    # --- Step 4: Generate report ---
    report_cmd = [
        python, str(SCRIPTS_DIR / "generate_backtest_report.py"),
        "--tickers", *tickers, "--run-id", run_id,
    ]
    if args.output:
        report_cmd += ["--output", args.output]

    ok = run_step(report_cmd, "Generate BACKTEST_RESULTS.md")
    if not ok:
        failed.append("report")

    # --- Summary ---
    elapsed_total = time.time() - t_start
    if failed:
        log.error("PIPELINE FAILED (%.0fs, run_id=%s) — failed steps: %s",
                  elapsed_total, run_id, ", ".join(failed))
        sys.exit(1)
    else:
        output_path = args.output or str(PROJECT_ROOT / "BACKTEST_RESULTS.md")
        log.info("PIPELINE COMPLETE (%.0fs, run_id=%s) — report: %s",
                 elapsed_total, run_id, output_path)
        sys.exit(0)


if __name__ == "__main__":
    main()
