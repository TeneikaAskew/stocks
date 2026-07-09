"""Task-parallel Phase-2 ablation. One Cloud Run task runs one config
(resolved from CLOUD_RUN_TASK_INDEX). Reuses the production engines via their
--features path; records every slice in the slice_ledger."""
from __future__ import annotations
import logging, os
from gcp.database import get_engine
from gcp.research.direction_program.slice_ledger import SliceLedger
from gcp.research.direction_program.gate import slice_predictable

log = logging.getLogger("direction.phase2")
TICKERS = ("IWM", "SPY", "QQQ")
_FAMILIES = ["prune", "options_iv", "positioning", "cross_asset", "calendar"]


def _ladder(axis):
    cfgs = [{"axis": axis, "features": ""}]                    # baseline
    cfgs += [{"axis": axis, "features": f} for f in _FAMILIES]  # isolation
    cfgs.append({"axis": axis, "features": ",".join(_FAMILIES)})  # full stack
    return cfgs


ABLATION_CONFIGS = _ladder("direction") + _ladder("size")


def run_config(engine, cfg, ledger_path="docs/research/direction_program_ledger.jsonl"):
    from gcp.research.direction_program.baseline_runner import extract_fold_beats
    ledger = SliceLedger(ledger_path)
    per = {}
    for tk in TICKERS:
        if cfg["axis"] == "direction":
            from gcp.research.strat_engine.strat_dir_walk_forward import walk_forward_direction
            wf = walk_forward_direction(engine, tk, "5m", features=cfg["features"])
        else:
            from gcp.research.magnitude_engine.mag_walk_forward import walk_forward
            wf = walk_forward(engine, "phase0", tk, "5m", features=cfg["features"])
        beats = extract_fold_beats(wf)
        per[tk] = beats
        ledger.record(f"phase2:{cfg['axis']}:{cfg['features'] or 'baseline'}",
                      lever="phase2", target=cfg["axis"], conditioning="none",
                      feature_set="phase2:" + (cfg["features"] or "baseline"),
                      ticker=tk, fold_beats=beats, meta={"tf": "5m"})
    v = slice_predictable(per)
    log.info("PHASE2_VERDICT axis=%s features=%s predictable=%s n_tickers_pass=%d",
             cfg["axis"], cfg["features"] or "baseline",
             v["predictable"], v["n_tickers_pass"])
    return v


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    idx = int(os.environ.get("CLOUD_RUN_TASK_INDEX", "0"))
    if idx >= len(ABLATION_CONFIGS):
        log.info("task-index %d >= %d configs — no-op", idx, len(ABLATION_CONFIGS))
        return
    run_config(get_engine(), ABLATION_CONFIGS[idx])


if __name__ == "__main__":
    main()
