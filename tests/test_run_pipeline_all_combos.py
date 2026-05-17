"""Pins that the backtest pipeline runs the full timeframe-combo matrix.

scripts/run_timeframe_sweep.py has three phases:
  Phase 1 — each timeframe as a sole signal (1m, 5m, 15m, 30m, 1h)
  Phase 2 — 1m entries + higher-TF trend filter (always on)
  Phase 3 — ALL coarser-entry + higher-TF-filter combos (5m+15m, 5m+30m,
            5m+1h, 15m+30m, 15m+1h, 30m+1h) — gated behind --all-combos

run_pipeline.py is the comprehensive backtest surface, so it must pass
--all-combos to the sweep step. Without it, Phase 3 silently doesn't
run and the 5m/15m/30m entry-timeframe combos never reach
backtest_sweeps or the report. This AST check fails if the flag is
dropped — the regression is invisible otherwise (the pipeline still
"succeeds", just with a narrower result set).
"""
from __future__ import annotations

import ast
from pathlib import Path


def _sweep_step_args() -> list[str]:
    """Extract the run_timeframe_sweep.py argv list from run_pipeline.py.

    Finds the list literal that contains 'run_timeframe_sweep.py' and
    returns its string-constant elements.
    """
    src = Path("scripts/run_pipeline.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.List):
            continue
        # The filename is inside a `str(SCRIPTS_DIR / "...")` call, not a
        # direct list element — so scan ALL string constants anywhere in
        # the list node to identify it.
        all_strs = [n.value for n in ast.walk(node)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        if not any("run_timeframe_sweep.py" in s for s in all_strs):
            continue
        # Return only the top-level argv string elements (the actual flags).
        return [e.value for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    raise AssertionError(
        "no list literal referencing run_timeframe_sweep.py found in "
        "scripts/run_pipeline.py"
    )


def test_pipeline_passes_all_combos_to_sweep():
    """run_pipeline.py MUST pass --all-combos to run_timeframe_sweep.py
    so Phase 3 (the coarser-entry-TF combo matrix) actually runs."""
    args = _sweep_step_args()
    assert "--all-combos" in args, (
        "run_pipeline.py's timeframe-sweep step is missing --all-combos. "
        "Without it Phase 3 (5m+15m, 5m+30m, 15m+30m, ... entry-TF combos) "
        "silently never runs — see this module's docstring."
    )


def test_pipeline_sweep_step_still_uses_strat_and_run_id():
    """Sanity-pin the other sweep args so a future edit doesn't drop them."""
    args = _sweep_step_args()
    assert "--use-strat" in args
    assert "--run-id" in args
