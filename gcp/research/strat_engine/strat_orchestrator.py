"""Strat Directionality Engine — orchestrator.

Chains stages 1 → 6 with gate enforcement. Each stage stays standalone-
runnable; the orchestrator just runs them in sequence and aborts if a
mandatory gate fails.

Modes:
  --mode=full        Run all 6 stages for (ticker, tf). Gates enforced.
  --mode=from-stage  Resume from a specific stage (1..6).
  --mode=only-stage  Run a single stage in isolation.
  --mode=all-tickers Run --mode=full for every (ticker, tf) cell in config.

Gates:
  Stage 1: TEST 1+2+3 must PASS (row count, label correctness, no leak).
  Stage 4: oos_accuracy beats base_rate by >= base_rate_beat_pp AND
           ece <= ece_ceiling. If FAIL, do not proceed to Stage 5/6 for
           that cell.
  Stage 5: at least one TF model must exist for the ticker.

Run cost (for one (ticker, tf) cell, full pipeline):
  Stage 1 verify: ~30s
  Stage 2 EDA:    ~30s
  Stage 3 corr:   ~60s (MI compute)
  Stage 4 train:  ~60s (LGBM + calibration)
  Stage 5 FTFC:   ~30s (needs all 6 TFs scored)
  Stage 6 readout: ~10s
  Total: ~3-4 minutes per ticker × TF cell.
"""
from __future__ import annotations
import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine
from gcp.research.strat_engine.strat_config import (
    TICKERS, TIMEFRAMES, DEFAULT_TRAIN_UNTIL,
    DEFAULT_BASE_RATE_BEAT_PP, DEFAULT_ECE_CEILING, DEFAULT_CALIBRATION,
)
from gcp.research.strat_engine.strat_data_pipeline import verify as stage1_verify
from gcp.research.strat_engine.strat_eda_baserates import run_eda as stage2_eda
from gcp.research.strat_engine.strat_corr_indicators import run_corr as stage3_corr
from gcp.research.strat_engine.strat_corr_combos import run_combos as stage3b_combos
from gcp.research.strat_engine.strat_pred_train import run_train as stage4_train
from gcp.research.strat_engine.strat_ftfc_assemble import assemble_ftfc as stage5_ftfc
from gcp.research.strat_engine.strat_readout import build_readout as stage6_readout
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


def run_pipeline(engine, ticker: str, tf: str, train_until: str,
                 calibration: str, base_rate_beat_pp: float,
                 ece_ceiling: float, from_stage: int = 1,
                 only_stage: int | None = None,
                 strict_gates: bool = True) -> dict:
    """Run stages from `from_stage` through 6, OR only `only_stage`."""
    result = {"ticker": ticker, "tf": tf, "train_until": train_until,
              "stages": {}}
    t_start = time.time()

    def should_run(stage_num: int) -> bool:
        if only_stage is not None:
            return stage_num == only_stage
        return stage_num >= from_stage

    # Stage 1
    if should_run(1):
        log.info(">>> STAGE 1 DATA / VERIFY")
        s1 = stage1_verify(engine, ticker, tf)
        result["stages"]["1_verify"] = s1
        if strict_gates and (s1["test1_row_gap"] != "PASS" or
                             s1["test2"] != "PASS" or
                             s1["test3"] != "PASS"):
            log.error("Stage 1 gate FAIL — aborting pipeline for %s %s", ticker, tf)
            result["pipeline"] = "FAIL_AT_STAGE_1"
            return result

    # Stage 2
    if should_run(2):
        log.info(">>> STAGE 2 EDA")
        s2 = stage2_eda(engine, ticker, tf, until=None)  # full history for EDA
        result["stages"]["2_eda"] = {
            "base_rate": s2["base_rate"]["rates"],
            "majority_class": s2["base_rate"]["majority_class"],
            "majority_rate": s2["base_rate"]["majority_rate"],
            "n_total": s2["base_rate"]["n_total"],
        }

    # Stage 3
    if should_run(3):
        log.info(">>> STAGE 3 CORRELATION")
        s3 = stage3_corr(engine, ticker, tf, train_until)
        result["stages"]["3_corr"] = {
            "n_train": s3["n_train"],
            "top_drivers_per_class": {
                cls: [r["feature"] for r in s3["rankings"][cls][:5]]
                for cls in s3["rankings"]
            },
        }

        # Stage 3b — COMBINATION mining (Effort B). Explainability add-on that
        # sits alongside the single-feature Stage 3; it NEVER gates the pipeline
        # (a combo-mining hiccup must not block the model train). Runs whenever
        # Stage 3 runs.
        log.info(">>> STAGE 3b COMBINATION MINING")
        try:
            s3b = stage3b_combos(engine, ticker, tf, train_until)
            result["stages"]["3b_combos"] = {
                "model_oos_lift": s3b["model"]["lift"],
                "model_oos_accuracy": s3b["model"]["oos_accuracy"],
                "best_combo_per_class": {
                    cls: (combos[0] if combos else None)
                    for cls, combos in s3b["combos"].items()
                },
            }
        except Exception as e:  # noqa: BLE001 — non-gating explainability stage
            log.warning("Stage 3b combos failed (non-gating): %s", e)
            result["stages"]["3b_combos"] = {"status": "skipped", "reason": str(e)}

    # Stage 4 (THE gate)
    if should_run(4):
        log.info(">>> STAGE 4 TRAIN + CALIBRATE")
        s4 = stage4_train(engine, ticker, tf, train_until,
                          calibration=calibration,
                          base_rate_beat_pp=base_rate_beat_pp,
                          ece_ceiling=ece_ceiling)
        result["stages"]["4_train"] = {
            "oos_accuracy": s4["oos_accuracy"],
            "base_accuracy": s4["base_accuracy"],
            "accuracy_beat_pp": s4["accuracy_beat_pp"],
            "ece": s4["ece"],
            "gate_verdict": s4["gate"]["verdict"],
        }
        if strict_gates and s4["gate"]["verdict"] != "PASS":
            log.warning("Stage 4 gate FAIL — skipping Stages 5/6 for %s %s",
                        ticker, tf)
            result["pipeline"] = "STOPPED_AFTER_STAGE_4_FAIL"
            result["total_wall_sec"] = time.time() - t_start
            return result

    # Stage 5 (only meaningful when Stage 4 has run for multiple TFs of this ticker)
    if should_run(5):
        log.info(">>> STAGE 5 FTFC ASSEMBLY")
        try:
            ftfc = stage5_ftfc(engine, ticker, train_until)
            result["stages"]["5_ftfc"] = {
                "n_rows": int(len(ftfc)),
                "continuity_mean": float(ftfc["continuity_score"].mean()),
                "aligned_direction_counts": ftfc["aligned_direction"].value_counts().to_dict(),
            }
        except RuntimeError as e:
            log.warning("Stage 5 SKIPPED: %s", e)
            result["stages"]["5_ftfc"] = {"skipped": str(e)}

    # Stage 6
    if should_run(6):
        log.info(">>> STAGE 6 READOUT")
        try:
            r6 = stage6_readout(engine, ticker, train_until)
            result["stages"]["6_readout"] = {
                "as_of_bar_ts": r6["as_of_bar_ts"],
                "continuity_score": r6["ftfc"]["continuity_score"],
                "aligned_direction": r6["ftfc"]["aligned_direction"],
                "tfs_in_stack": r6["ftfc"]["tfs_in_stack"],
            }
        except RuntimeError as e:
            log.warning("Stage 6 SKIPPED: %s", e)
            result["stages"]["6_readout"] = {"skipped": str(e)}

    result["pipeline"] = "COMPLETE"
    result["total_wall_sec"] = round(time.time() - t_start, 1)
    log.info("=" * 70)
    log.info("PIPELINE %s in %.1fs (ticker=%s tf=%s)",
             result["pipeline"], result["total_wall_sec"], ticker, tf)
    log.info("=" * 70)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode",
                   choices=["full", "from-stage", "only-stage", "all-tickers"],
                   default="full")
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--from-stage", type=int, default=1, choices=range(1, 7))
    p.add_argument("--only-stage", type=int, default=None, choices=range(1, 7))
    p.add_argument("--train-until", default=DEFAULT_TRAIN_UNTIL)
    p.add_argument("--calibration", default=DEFAULT_CALIBRATION,
                   choices=["isotonic", "sigmoid"])
    p.add_argument("--base-rate-beat-pp", type=float,
                   default=DEFAULT_BASE_RATE_BEAT_PP)
    p.add_argument("--ece-ceiling", type=float, default=DEFAULT_ECE_CEILING)
    p.add_argument("--lenient", action="store_true",
                   help="Disable strict gates (run all stages even if one fails)")
    args = p.parse_args()

    engine = get_engine()
    strict = not args.lenient

    if args.mode == "all-tickers":
        results = []
        for ticker in TICKERS:
            for tf in TIMEFRAMES:
                log.info("###  TICKER=%s TF=%s  ###", ticker, tf)
                try:
                    r = run_pipeline(
                        engine, ticker, tf, args.train_until,
                        calibration=args.calibration,
                        base_rate_beat_pp=args.base_rate_beat_pp,
                        ece_ceiling=args.ece_ceiling,
                        strict_gates=strict)
                    results.append(r)
                except Exception as e:
                    log.error("FAILED for %s %s: %s", ticker, tf, e)
                    results.append({"ticker": ticker, "tf": tf,
                                    "pipeline": "ERROR", "error": str(e)})
        log.info("=" * 70)
        log.info("ALL-TICKERS SUMMARY")
        log.info("=" * 70)
        for r in results:
            stage4 = r.get("stages", {}).get("4_train", {})
            log.info("  %-3s %-3s  pipeline=%-30s  oos_acc=%-6s  ece=%-6s  gate=%s",
                     r["ticker"], r["tf"], r["pipeline"],
                     f"{stage4.get('oos_accuracy', '-'):.3f}" if "oos_accuracy" in stage4 else "-",
                     f"{stage4.get('ece', '-'):.3f}" if "ece" in stage4 else "-",
                     stage4.get("gate_verdict", "-"))
    else:
        from_stage = args.only_stage if args.mode == "only-stage" else args.from_stage
        only_stage = args.only_stage if args.mode == "only-stage" else None
        run_pipeline(
            engine, args.ticker, args.tf, args.train_until,
            calibration=args.calibration,
            base_rate_beat_pp=args.base_rate_beat_pp,
            ece_ceiling=args.ece_ceiling,
            from_stage=from_stage,
            only_stage=only_stage,
            strict_gates=strict)


if __name__ == "__main__":
    main()
