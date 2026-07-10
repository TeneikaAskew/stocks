"""Task-parallel Phase-2 ablation. One Cloud Run task runs one config
(resolved from CLOUD_RUN_TASK_INDEX). Reuses the production engines via their
--features path; records every slice in the slice_ledger."""
from __future__ import annotations
import json, logging, os
import pandas as pd
from gcp.database import get_engine
from gcp.research.direction_program.slice_ledger import SliceLedger
from gcp.research.direction_program.gate import slice_predictable

log = logging.getLogger("direction.phase2")
TICKERS = ("IWM", "SPY", "QQQ")
_FAMILIES = ["prune", "options_iv", "positioning", "cross_asset", "calendar"]

# Timeframe / calibration / axes are env-configurable so the same job can run
# the 5m baseline sweep AND the 15m+isotonic follow-up (isotonic recal found
# size is predictable+calibrated at 15m; magnitude walk_forward takes
# calibration, the direction engine does not).
_TF = os.environ.get("PHASE2_TF", "5m")
_CALIBRATION = os.environ.get("PHASE2_CALIBRATION", "none")
_AXES = [a for a in os.environ.get("PHASE2_AXES", "direction,size").split(",") if a]


def _ladder(axis):
    cfgs = [{"axis": axis, "features": ""}]                    # baseline
    cfgs += [{"axis": axis, "features": f} for f in _FAMILIES]  # isolation
    cfgs.append({"axis": axis, "features": ",".join(_FAMILIES)})  # full stack
    return cfgs


ABLATION_CONFIGS = [c for axis in _AXES for c in _ladder(axis)]


def run_config(engine, cfg, ledger_path="docs/research/direction_program_ledger.jsonl"):
    from gcp.research.direction_program.baseline_runner import extract_fold_beats
    ledger = SliceLedger(ledger_path)
    per = {}
    for tk in TICKERS:
        try:
            if cfg["axis"] == "direction":
                from gcp.research.strat_engine.strat_dir_walk_forward import walk_forward_direction
                # direction engine has no post-hoc calibration (24/24-fold study)
                wf = walk_forward_direction(engine, tk, _TF, features=cfg["features"])
            else:
                from gcp.research.magnitude_engine.mag_walk_forward import walk_forward
                wf = walk_forward(engine, "phase0", tk, _TF,
                                  calibration=_CALIBRATION, features=cfg["features"])
            beats = extract_fold_beats(wf)
        except Exception:
            # One ticker failing (e.g. options INFEASIBLE RuntimeError) must not
            # abort the whole config under --max-retries 0. Empty beats → the
            # gate counts this ticker as a non-pass (honest), and the config
            # still produces a verdict from the surviving tickers.
            log.exception("run_config: ticker=%s axis=%s features=%s failed — "
                          "recording empty beats and continuing",
                          tk, cfg["axis"], cfg["features"] or "baseline")
            beats = []
        per[tk] = beats
        ledger.record(f"phase2:{cfg['axis']}:{_TF}:{_CALIBRATION}:{cfg['features'] or 'baseline'}",
                      lever="phase2", target=cfg["axis"], conditioning="none",
                      feature_set="phase2:" + (cfg["features"] or "baseline"),
                      ticker=tk, fold_beats=beats,
                      meta={"tf": _TF, "calibration": _CALIBRATION})
    v = slice_predictable(per)
    log.info("PHASE2_VERDICT axis=%s tf=%s cal=%s features=%s predictable=%s "
             "n_tickers_pass=%d per_ticker_beats=%s",
             cfg["axis"], _TF, _CALIBRATION, cfg["features"] or "baseline",
             v["predictable"], v["n_tickers_pass"], per)
    # Durable, config-attributable result: the per-task ledger file is ephemeral
    # (lost on container exit), so persist a small JSON to GCS keyed by config.
    features_tag = cfg["features"].replace(",", "-") if cfg["features"] else "baseline"
    ts = int(pd.Timestamp.utcnow().timestamp())
    blob = f"direction-program/phase2/{cfg['axis']}_{_TF}_{_CALIBRATION}_{features_tag}_{ts}.json"
    try:
        from gcp.research.strat_engine.strat_walk_forward import _gcs_upload
        payload = {"axis": cfg["axis"], "tf": _TF, "calibration": _CALIBRATION,
                   "features": cfg["features"] or "baseline",
                   "per_ticker_beats": per, "verdict": v}
        uri = _gcs_upload(json.dumps(payload, default=str).encode(), blob)
        log.info("PHASE2_RESULT_UPLOAD uri=%s", uri)
    except Exception:
        # Allowed cleanup catch — results are already durable in Cloud Run logs
        # (PHASE2_VERDICT with per_ticker_beats); the GCS copy is best-effort.
        log.warning("run_config: GCS result upload failed for blob=%s — results "
                    "still recoverable from logs", blob, exc_info=True)
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
