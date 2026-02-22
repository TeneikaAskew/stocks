#!/usr/bin/env python3
"""
Master runner: Execute all 7 phases of the per-ticker analysis pipeline.

Usage:
    python scripts/analysis/run_all_phases.py
    python scripts/analysis/run_all_phases.py --tickers IWM SPY
    python scripts/analysis/run_all_phases.py --phases 1 2 3
"""

import sys
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.analysis.shared_utils import TICKERS, REPORTS_DIR, timestamp_str


def run_all(tickers=None, phases=None):
    """Run all analysis phases."""
    if tickers is None:
        tickers = TICKERS
    if phases is None:
        phases = [1, 2, 3, 4, 5, 6, 7]

    print(f"=" * 60)
    print(f"Per-Ticker Trader's Playbook — Full Analysis Pipeline")
    print(f"=" * 60)
    print(f"Tickers: {', '.join(tickers)}")
    print(f"Phases: {phases}")
    print(f"Started: {timestamp_str()}")
    print(f"Output: {REPORTS_DIR}/")
    print(f"=" * 60)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    total_start = time.time()

    if 1 in phases:
        print(f"\n{'='*60}")
        print(f"PHASE 1: Strat Pattern Mining")
        print(f"{'='*60}")
        t0 = time.time()
        from scripts.analysis.phase1_strat_mining import run_phase1
        run_phase1(tickers=tickers)
        print(f"  Phase 1 completed in {time.time()-t0:.0f}s")

    if 2 in phases:
        print(f"\n{'='*60}")
        print(f"PHASE 2: Indicator Confirmation")
        print(f"{'='*60}")
        t0 = time.time()
        from scripts.analysis.phase2_indicator_confirmation import run_phase2
        run_phase2(tickers=tickers)
        print(f"  Phase 2 completed in {time.time()-t0:.0f}s")

    if 3 in phases:
        print(f"\n{'='*60}")
        print(f"PHASE 3: ORB-Based Strategies")
        print(f"{'='*60}")
        t0 = time.time()
        from scripts.analysis.phase3_orb_strategies import run_phase3
        run_phase3(tickers=tickers)
        print(f"  Phase 3 completed in {time.time()-t0:.0f}s")

    if 4 in phases:
        print(f"\n{'='*60}")
        print(f"PHASE 4: High-Probability Setup Discovery")
        print(f"{'='*60}")
        t0 = time.time()
        from scripts.analysis.phase4_setup_discovery import run_phase4
        run_phase4(tickers=tickers)
        print(f"  Phase 4 completed in {time.time()-t0:.0f}s")

    if 5 in phases:
        print(f"\n{'='*60}")
        print(f"PHASE 5: Additional Dimensions")
        print(f"{'='*60}")
        t0 = time.time()
        from scripts.analysis.phase5_additional_dimensions import run_phase5
        run_phase5(tickers=tickers)
        print(f"  Phase 5 completed in {time.time()-t0:.0f}s")

    if 6 in phases:
        print(f"\n{'='*60}")
        print(f"PHASE 6: Beginner's Playbook")
        print(f"{'='*60}")
        t0 = time.time()
        from scripts.analysis.phase6_playbook import run_phase6
        run_phase6(tickers=tickers)
        print(f"  Phase 6 completed in {time.time()-t0:.0f}s")

    if 7 in phases:
        print(f"\n{'='*60}")
        print(f"PHASE 7: Ongoing Scoring & Feedback Loop")
        print(f"{'='*60}")
        t0 = time.time()
        from scripts.analysis.phase7_feedback_loop import run_phase7
        run_phase7()
        print(f"  Phase 7 completed in {time.time()-t0:.0f}s")

    total_elapsed = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"ALL PHASES COMPLETE")
    print(f"Total time: {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")
    print(f"Reports saved to: {REPORTS_DIR}/")
    print(f"{'='*60}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run all analysis phases')
    parser.add_argument('--tickers', nargs='+', default=TICKERS,
                        help='Tickers to analyze (default: IWM SPY QQQ)')
    parser.add_argument('--phases', nargs='+', type=int, default=None,
                        help='Specific phases to run (default: all)')
    args = parser.parse_args()

    run_all(tickers=args.tickers, phases=args.phases)
