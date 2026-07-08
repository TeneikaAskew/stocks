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
