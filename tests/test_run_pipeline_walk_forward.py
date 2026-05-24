"""Validation tests for run_pipeline.py's --walk-forward / --walk-forward-only flags.

Subprocess-based — mirrors tests/test_run_pipeline_all_combos.py. The
pipeline validates flag combinations before any DB / subprocess work,
so these run hermetically (no Cloud SQL needed). Each assertion checks
the exit code + the stderr/stdout message so the regression is visible
both ways.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


def _run_pipeline(*flags) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/run_pipeline.py", *flags],
        capture_output=True, text=True, timeout=30,
    )


# ── --walk-forward-only validation ─────────────────────────────────────

class TestWalkForwardOnlyValidation:
    def test_requires_run_id(self):
        """--walk-forward-only needs an existing run's --run-id; without
        it the IS-vs-OOS comparison has nothing to anchor against."""
        r = _run_pipeline("--walk-forward-only")
        assert r.returncode == 2
        assert "--walk-forward-only requires --run-id" in (r.stdout + r.stderr)

    def test_conflicts_with_report_only(self):
        r = _run_pipeline(
            "--walk-forward-only", "--report-only", "--run-id", "x",
        )
        assert r.returncode == 2
        assert "mutually exclusive" in (r.stdout + r.stderr)

    def test_conflicts_with_sweep_only(self):
        """The two scoping flags can't both apply — they're alternatives."""
        r = _run_pipeline(
            "--walk-forward-only", "--sweep-only", "--run-id", "x",
        )
        assert r.returncode == 2
        assert "mutually exclusive" in (r.stdout + r.stderr)


# ── argv inclusion test for the WF sub-step ────────────────────────────

def _wf_step_args() -> list[str]:
    """Extract the run_walk_forward.py argv list from run_pipeline.py."""
    src = Path("scripts/run_pipeline.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.List):
            continue
        all_strs = [n.value for n in ast.walk(node)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        if not any("run_walk_forward.py" in s for s in all_strs):
            continue
        return [e.value for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    raise AssertionError(
        "no list literal referencing run_walk_forward.py found in "
        "scripts/run_pipeline.py — the WF step was never wired in."
    )


class TestPipelineWiresWalkForwardStep:
    def test_pipeline_invokes_run_walk_forward(self):
        args = _wf_step_args()
        # Must thread the run_id and ticker through.
        assert "--ticker" in args
        assert "--run-id" in args

    def test_walk_forward_help_lists_both_flags(self):
        """Both --walk-forward (full pipeline + WF) and
        --walk-forward-only (re-run scope) must surface in --help."""
        r = _run_pipeline("--help")
        assert r.returncode == 0
        assert "--walk-forward" in r.stdout
        assert "--walk-forward-only" in r.stdout
