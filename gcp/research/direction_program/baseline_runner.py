"""Run direction/size/type through the existing walk-forward engines, pure
prediction, and record slice-ledger rows. The direction axis reproduces the
0/72 close-sign control as a harness-trust check.

Reuses three existing walk-forward engines (does NOT modify them):
  - DIRECTION: gcp.research.strat_engine.strat_dir_walk_forward.walk_forward_direction
  - SIZE (magnitude): gcp.research.magnitude_engine.mag_walk_forward.walk_forward
  - TYPE (strat): gcp.research.strat_engine.strat_walk_forward.walk_forward

All three engines already report a per-fold "beat" key (log-loss beat over
the base-rate constant), so extract_fold_beats needs no key normalization.
"""
from __future__ import annotations
from gcp.research.direction_program.slice_ledger import SliceLedger
from gcp.research.direction_program.gate import slice_predictable

TICKERS = ("IWM", "SPY", "QQQ")


def extract_fold_beats(wf_result: dict) -> list:
    return [f["beat"] for f in wf_result.get("folds", []) if "beat" in f]


def _run_wf(engine, axis: str, ticker: str, tf: str) -> dict:
    if axis == "direction":
        from gcp.research.strat_engine.strat_dir_walk_forward import walk_forward_direction
        return walk_forward_direction(engine, ticker, tf)
    if axis == "size":
        from gcp.research.magnitude_engine.mag_walk_forward import walk_forward
        return walk_forward(engine, "phase0", ticker, tf)
    if axis == "type":
        from gcp.research.strat_engine.strat_walk_forward import walk_forward
        return walk_forward(engine, ticker, tf)
    raise ValueError(f"unknown axis {axis!r}")


def run_axis(engine, axis: str, ticker: str, tf: str, ledger: SliceLedger) -> list:
    wf = _run_wf(engine, axis, ticker, tf)
    beats = extract_fold_beats(wf)
    ledger.record(f"baseline:{axis}", lever="baseline", target=axis,
                  conditioning="none", feature_set="existing", ticker=ticker,
                  fold_beats=beats, meta={"tf": tf})
    return beats


def run_baseline(engine, tf: str = "5m",
                 ledger_path: str = "docs/research/direction_program_ledger.jsonl") -> dict:
    ledger = SliceLedger(ledger_path)
    out = {}
    for axis in ("direction", "size", "type"):
        per = {tk: run_axis(engine, axis, tk, tf, ledger) for tk in TICKERS}
        out[axis] = slice_predictable(per)
    return out


def main():
    """CLI entrypoint — run the 3-axis baseline against Cloud SQL and log the
    pre-registered verdict. Executed one-shot via the `direction-baseline`
    Cloud Run Job (the only path with Cloud SQL + ML-engine access)."""
    import argparse
    import json
    import logging
    from gcp.database import get_engine

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("direction.baseline")

    p = argparse.ArgumentParser(description="Run the 3-axis pure-prediction "
                                            "baseline (direction/size/type) and "
                                            "print the pre-registered verdict.")
    p.add_argument("--tf", default="5m", help="timeframe (default 5m)")
    p.add_argument("--ledger-path",
                   default="docs/research/direction_program_ledger.jsonl",
                   help="slice-ledger JSONL path (written inside the container)")
    args = p.parse_args()

    engine = get_engine()
    result = run_baseline(engine, tf=args.tf, ledger_path=args.ledger_path)

    # One greppable line per axis for Cloud Run logs, then the full result.
    for axis, v in result.items():
        log.info("BASELINE_VERDICT axis=%s tf=%s predictable=%s "
                 "n_tickers_pass=%d per_ticker=%s",
                 axis, args.tf, v["predictable"], v["n_tickers_pass"],
                 v["per_ticker_pass"])
    log.info("BASELINE_RESULT_JSON %s", json.dumps(result))
    return result


if __name__ == "__main__":
    main()
