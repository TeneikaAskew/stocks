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
        help="Only regenerate the report from existing CSVs",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output path for the report (default: BACKTEST_RESULTS.md)",
    )
    args = parser.parse_args()

    python = sys.executable
    tickers = args.tickers
    failed: list[str] = []

    log.info("Pipeline: tickers=%s  skip_sweep=%s  report_only=%s",
             tickers, args.skip_sweep, args.report_only)
    t_start = time.time()

    if not args.report_only:
        # --- Step 1: Base backtests (no Strat) ---
        for ticker in tickers:
            ok = run_step(
                [python, str(SCRIPTS_DIR / "run_backtest.py"),
                 "--ticker", ticker],
                f"Backtest {ticker} (base)",
            )
            if not ok:
                failed.append(f"backtest-base-{ticker}")

        # --- Step 2: Strat backtests (FTFC + ORB) ---
        for ticker in tickers:
            ok = run_step(
                [python, str(SCRIPTS_DIR / "run_backtest.py"),
                 "--ticker", ticker, "--use-strat"],
                f"Backtest {ticker} (strat)",
            )
            if not ok:
                failed.append(f"backtest-strat-{ticker}")

        # --- Step 3: Timeframe sweeps ---
        if not args.skip_sweep:
            for ticker in tickers:
                ok = run_step(
                    [python, str(SCRIPTS_DIR / "run_timeframe_sweep.py"),
                     "--ticker", ticker, "--use-strat"],
                    f"Timeframe sweep {ticker}",
                )
                if not ok:
                    failed.append(f"sweep-{ticker}")

    # --- Step 4: Generate report ---
    report_cmd = [
        python, str(SCRIPTS_DIR / "generate_backtest_report.py"),
        "--tickers", *tickers,
    ]
    if args.output:
        report_cmd += ["--output", args.output]

    ok = run_step(report_cmd, "Generate BACKTEST_RESULTS.md")
    if not ok:
        failed.append("report")

    # --- Summary ---
    elapsed_total = time.time() - t_start
    if failed:
        log.error("PIPELINE FAILED (%.0fs) — failed steps: %s",
                  elapsed_total, ", ".join(failed))
        sys.exit(1)
    else:
        output_path = args.output or str(PROJECT_ROOT / "BACKTEST_RESULTS.md")
        log.info("PIPELINE COMPLETE (%.0fs) — report: %s", elapsed_total, output_path)
        sys.exit(0)


if __name__ == "__main__":
    main()
