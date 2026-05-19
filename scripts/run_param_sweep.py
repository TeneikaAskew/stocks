#!/usr/bin/env python3
"""Walk-forward parameter calibration sweep for the ETF intraday strategy.

For each (call_target, put_target, call_time_stop, put_time_stop) combo,
runs anchored walk-forward validation, ranks combos by out-of-sample
expectancy subject to stability gates, and auto-applies the winning
combo per ticker to ``exit_config_overrides`` — which the live signal
monitor reads at fire time.

Sibling to ``run_timeframe_sweep.py``: that sweeps timeframes, this
sweeps strategy exit parameters with walk-forward validation. Every
combo is written to ``walk_forward_results``; the selected winner is
also written to ``exit_config_overrides``.

Only the four exit parameters are swept — they apply cleanly at
fire-time through the existing per-ticker resolver pipeline.
``consecutive_periods`` is deliberately NOT swept: it is baked into a
precomputed indicator column, so varying it correctly would need a
per-combo indicator rebuild (and a per-ticker rebuild in the live
monitor) — out of safe scope for an auto-applied sweep.

Usage:
    python scripts/run_param_sweep.py                    # SPY,IWM,QQQ
    python scripts/run_param_sweep.py --tickers SPY
    python scripts/run_param_sweep.py --no-apply         # sweep only
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from lib.config import load_config
from lib.data_loader import DataLoader
from lib.indicators import add_all_indicators
from lib.walk_forward import WalkForwardValidator, select_calibration_winner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
log = logging.getLogger("param-sweep")

DEFAULT_TICKERS = ["SPY", "IWM", "QQQ"]

# Deep grid over the four exit params. 3^4 = 81 combos per ticker.
PARAM_GRID = {
    "call_target":    [0.0025, 0.0030, 0.0035],
    "put_target":     [0.0032, 0.0038, 0.0044],
    "call_time_stop": [25, 30, 35],
    "put_time_stop":  [30, 35, 40],
}


def combo_label(row) -> str:
    """Compact, stable label for one param combo (<=48 chars).

    Accepts a dict or a pandas Series — both support ``[]`` access.
    """
    return (
        f"ct{float(row['call_target']) * 10000:.0f}"
        f"_pt{float(row['put_target']) * 10000:.0f}"
        f"_cts{int(row['call_time_stop'])}"
        f"_pts{int(row['put_time_stop'])}"
    )


def persist_results(
    sweep_df: pd.DataFrame, run_id: str, ticker: str, winner_label: str | None,
) -> int:
    """Write every combo to ``walk_forward_results`` (``selected`` set on
    the winner). Raises on Cloud SQL failure — the table is the canonical
    record of the run."""
    from gcp.database import upsert_dataframe

    df = sweep_df.copy()
    df.insert(0, "run_id", run_id)
    df.insert(1, "ticker", ticker)
    df["label"] = df.apply(combo_label, axis=1)
    df["selected"] = df["label"] == winner_label

    cols = [
        "run_id", "ticker", "label",
        "call_target", "put_target", "call_time_stop", "put_time_stop",
        "avg_expectancy_pct", "avg_win_rate", "std_expectancy_pct",
        "stability_score", "total_folds", "total_trades", "selected",
    ]
    df = df[[c for c in cols if c in df.columns]]
    return upsert_dataframe(
        df, table="walk_forward_results",
        conflict_cols=["run_id", "ticker", "label"],
    )


def apply_winner(ticker: str, winner: dict, run_id: str) -> None:
    """Write the winning combo to ``exit_config_overrides`` as today's
    snapshot so the live signal monitor picks it up at the next fire.

    Uses INSERT ... SELECT so the prior row's non-swept knobs (call_stop,
    put_stop, blue_sky_atr_offset, consecutive_periods, disabled_*) are
    carried forward — a new snapshot must be complete, never a partial
    row that silently drops earlier calibration. Requires an existing
    row for the ticker (the core-3 are seeded in gcp/schema.sql)."""
    from gcp.database import execute_sql

    notes = (
        f"walk-forward param sweep run_id={run_id} "
        f"stability={float(winner['stability_score']):.2f} "
        f"avg_expectancy={float(winner['avg_expectancy_pct']):+.4%} "
        f"(n={int(winner['total_trades'])} trades, "
        f"{int(winner['total_folds'])} folds)"
    )
    sql = """
        INSERT INTO exit_config_overrides
          (ticker, calibration_date, call_target, put_target,
           call_stop, put_stop, call_time_stop, put_time_stop,
           consecutive_periods, disabled_conditions, disabled_directions,
           blue_sky_atr_offset, notes)
        SELECT ticker, CURRENT_DATE, :call_target, :put_target,
               call_stop, put_stop, :call_time_stop, :put_time_stop,
               consecutive_periods, disabled_conditions, disabled_directions,
               blue_sky_atr_offset, :notes
          FROM exit_config_overrides
         WHERE ticker = :ticker
         ORDER BY calibration_date DESC
         LIMIT 1
        ON CONFLICT (ticker, calibration_date) DO UPDATE SET
           call_target    = EXCLUDED.call_target,
           put_target     = EXCLUDED.put_target,
           call_time_stop = EXCLUDED.call_time_stop,
           put_time_stop  = EXCLUDED.put_time_stop,
           notes          = EXCLUDED.notes
    """
    execute_sql(sql, {
        "ticker": ticker,
        "call_target": float(winner["call_target"]),
        "put_target": float(winner["put_target"]),
        "call_time_stop": int(winner["call_time_stop"]),
        "put_time_stop": int(winner["put_time_stop"]),
        "notes": notes,
    })


def sweep_ticker(
    ticker: str, start: str | None, end: str | None,
    use_strat: bool, run_id: str, apply: bool,
) -> None:
    cfg = load_config(ticker=ticker)
    loader = DataLoader()
    log.info("[%s] loading 1-minute data ...", ticker)
    df = loader.load_best_available(ticker, start, end)
    if df is None or df.empty:
        log.error("[%s] no data available — skipping", ticker)
        return

    close_col = "Close" if "Close" in df.columns else "Last"
    df = add_all_indicators(df, close_col=close_col)
    log.info("[%s] %d bars %s..%s", ticker, len(df),
             df.index.min(), df.index.max())

    validator = WalkForwardValidator(
        risk_config=cfg.risk, exit_config=cfg.exit, signal_config=cfg.signal,
        strat_config=cfg.strat, backtest_config=cfg.backtest,
        indicator_config=cfg.indicator,
    )
    sweep_df = validator.walk_forward_sweep(
        df, PARAM_GRID, use_strat=use_strat, close_col=close_col,
    )
    if sweep_df.empty:
        log.error("[%s] sweep produced no rows — skipping", ticker)
        return

    winner = select_calibration_winner(sweep_df)
    winner_label = combo_label(winner) if winner is not None else None

    n = persist_results(sweep_df, run_id, ticker, winner_label)
    log.info("[%s] wrote %d combo row(s) to walk_forward_results", ticker, n)

    ranked = sweep_df.sort_values("avg_expectancy_pct", ascending=False)
    log.info("[%s] top combos by avg out-of-sample expectancy:", ticker)
    for _, r in ranked.head(5).iterrows():
        log.info("  %-22s exp=%+.4f stab=%.2f trades=%d",
                 combo_label(r), r["avg_expectancy_pct"],
                 r["stability_score"], int(r["total_trades"]))

    if winner is None:
        log.warning("[%s] NO combo cleared the gates — "
                    "params left unchanged", ticker)
        return
    log.info("[%s] winner=%s exp=%+.4f stab=%.2f",
             ticker, winner_label, winner["avg_expectancy_pct"],
             winner["stability_score"])
    if apply:
        apply_winner(ticker, winner, run_id)
        log.info("[%s] applied winner to exit_config_overrides", ticker)
    else:
        log.info("[%s] --no-apply set: winner NOT written", ticker)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Walk-forward parameter calibration sweep")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS),
                        help="Comma-separated tickers (default SPY,IWM,QQQ)")
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD")
    parser.add_argument("--use-strat", dest="use_strat", action="store_true",
                        default=True, help="Enable Strat scoring (default on)")
    parser.add_argument("--no-strat", dest="use_strat", action="store_false")
    parser.add_argument("--no-apply", dest="apply", action="store_false",
                        default=True,
                        help="Sweep + persist results but do NOT write "
                             "winners to exit_config_overrides")
    parser.add_argument("--run-id", type=str, default=None,
                        help="Shared run UUID (one is generated if omitted)")
    args = parser.parse_args()

    run_id = args.run_id or str(uuid.uuid4())
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    log.info("param sweep run_id=%s tickers=%s apply=%s",
             run_id, tickers, args.apply)

    failures = 0
    for ticker in tickers:
        try:
            sweep_ticker(ticker, args.start, args.end, args.use_strat,
                         run_id, args.apply)
        except Exception:
            failures += 1
            log.exception("[%s] sweep failed — continuing", ticker)

    log.info("param sweep complete (run_id=%s, %d/%d tickers failed)",
             run_id, failures, len(tickers))
    sys.exit(1 if failures == len(tickers) and tickers else 0)


if __name__ == "__main__":
    main()
