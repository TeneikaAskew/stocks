#!/usr/bin/env python3
"""Earnings playability calibration sweep.

Walks the playability backtest over a grid of (min_nq, lookback_quarters),
measures each combo's out-of-sample quintile hit-rate spread, and
auto-applies the best combo to the ``earnings_calibration`` table —
which the premarket brief reads (via
``lib.earnings_reactions.get_earnings_calibration``) to tune how far
back its playability stats look and the minimum history before a
playability read is trusted.

The playability *formula* has no tunable coefficients, so this sweep
calibrates the two knobs that genuinely change predictions: how much
recent history feeds each read (``lookback_quarters``) and how much
history is required before a read is made (``min_nq``).

Sibling to ``run_param_sweep.py`` (the ETF exit-param sweep).

Usage:
    python -m scripts.calibrate_earnings
    python -m scripts.calibrate_earnings --no-apply
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.earnings_reactions import select_earnings_winner
from scripts.backtest_playability import compute_quintile_spread, run_backtest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
log = logging.getLogger("earnings-sweep")

# Grid: minimum quarters of history to score x recent-window cap.
# 3 x 4 = 12 combos. Each combo is one walk-forward pass over
# earnings_reactions (formula-eval, not simulation) — runtime is minutes.
MIN_NQ_VALUES = [8, 10, 12]
LOOKBACK_VALUES = [8, 12, 16, 20]


def run_sweep() -> list:
    """Run the playability backtest for every (min_nq, lookback) combo."""
    combos = [(mq, lb) for mq in MIN_NQ_VALUES for lb in LOOKBACK_VALUES]
    results = []
    for i, (min_nq, lookback) in enumerate(combos, 1):
        log.info("combo %d/%d: min_nq=%d lookback=%d",
                 i, len(combos), min_nq, lookback)
        preds = run_backtest(min_nq=min_nq, lookback=lookback)
        m = compute_quintile_spread(preds)
        results.append({
            "min_nq": min_nq,
            "lookback_quarters": lookback,
            "n_predictions": m["n_predictions"],
            "overall_hit_rate": m["overall_hit_rate"],
            "quintile_spread": m["quintile_spread"],
        })
        log.info("  -> n=%d hit=%.3f quintile_spread=%.3f",
                 m["n_predictions"], m["overall_hit_rate"],
                 m["quintile_spread"])
    return results


def apply_winner(winner: dict) -> None:
    """Write the winning combo to earnings_calibration (today's row).

    Idempotent: ON CONFLICT on calibration_date so a same-day re-run
    converges instead of duplicating."""
    from gcp.database import execute_sql

    notes = (
        f"earnings sweep: min_nq={winner['min_nq']} "
        f"lookback={winner['lookback_quarters']} "
        f"quintile_spread={winner['quintile_spread']:.3f} "
        f"hit={winner['overall_hit_rate']:.3f} "
        f"n={winner['n_predictions']}"
    )
    execute_sql(
        """
        INSERT INTO earnings_calibration
          (calibration_date, min_nq, lookback_quarters,
           quintile_spread, overall_hit_rate, n_predictions, notes)
        VALUES (CURRENT_DATE, :min_nq, :lookback,
                :spread, :hit, :n, :notes)
        ON CONFLICT (calibration_date) DO UPDATE SET
           min_nq            = EXCLUDED.min_nq,
           lookback_quarters = EXCLUDED.lookback_quarters,
           quintile_spread   = EXCLUDED.quintile_spread,
           overall_hit_rate  = EXCLUDED.overall_hit_rate,
           n_predictions     = EXCLUDED.n_predictions,
           notes             = EXCLUDED.notes
        """,
        {
            "min_nq": int(winner["min_nq"]),
            "lookback": int(winner["lookback_quarters"]),
            "spread": float(winner["quintile_spread"]),
            "hit": float(winner["overall_hit_rate"]),
            "n": int(winner["n_predictions"]),
            "notes": notes,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Earnings playability calibration sweep")
    parser.add_argument("--no-apply", dest="apply", action="store_false",
                        default=True,
                        help="Run the sweep but do NOT write "
                             "earnings_calibration")
    args = parser.parse_args()

    results = run_sweep()
    ranked = sorted(results, key=lambda r: r["quintile_spread"], reverse=True)
    log.info("ranked combos by quintile spread:")
    for r in ranked:
        log.info("  min_nq=%2d lookback=%2d  spread=%.3f hit=%.3f n=%d",
                 r["min_nq"], r["lookback_quarters"], r["quintile_spread"],
                 r["overall_hit_rate"], r["n_predictions"])

    winner = select_earnings_winner(results)
    if winner is None:
        log.warning("no combo cleared the gates — "
                    "earnings_calibration left unchanged")
        return
    log.info("winner: min_nq=%d lookback=%d quintile_spread=%.3f",
             winner["min_nq"], winner["lookback_quarters"],
             winner["quintile_spread"])
    if args.apply:
        apply_winner(winner)
        log.info("applied winner to earnings_calibration")
    else:
        log.info("--no-apply set: winner NOT written")


if __name__ == "__main__":
    main()
