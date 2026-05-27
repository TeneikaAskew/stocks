#!/usr/bin/env python3
"""Assemble per-phase magnitude_engine verdicts from GCS walk-forward outputs.

Pulls the LATEST walk_forward_*.json per (phase, ticker, tf) cell from
gs://.../research/magnitude_engine/{phase}/{ticker}_{tf}/, applies the
PRE-SET gates (from mag_config), and writes a markdown report.

Usage:
    python -m scripts.assemble_magnitude_results > /tmp/magnitude_report.md
    python -m scripts.assemble_magnitude_results --phases phase0,phase1,phase3 --update-doc

--update-doc rewrites docs/MAGNITUDE_ENGINE_RESULTS.md replacing PENDING
markers with actual numbers. The pre-set success bar at the top of that
file is NEVER modified.
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Import gate thresholds from mag_config — this enforces that we apply the
# SAME pre-set bar the harness applied, no re-tuning.
sys.path.insert(0, str(Path(__file__).parent.parent))
from gcp.research.magnitude_engine.mag_config import (
    TICKERS, TIMEFRAMES, PHASES, GCS_BUCKET_DEFAULT,
    SUCCESS_BAR_MIN_FOLDS_LOGLOSS, SUCCESS_BAR_MIN_FOLDS_ECE,
    SUCCESS_BAR_MIN_FOLDS_LIFT, SUCCESS_BAR_EXPLOSIVE_LIFT_MIN,
    ECE_CEILING_BY_TF, SUCCESS_BAR_MIN_PASSING_TICKERS_PER_TF,
)


def _ls(prefix: str) -> list[str]:
    """List GCS objects under a prefix via gcloud storage."""
    try:
        out = subprocess.check_output(
            ["gcloud", "storage", "ls", prefix],
            stderr=subprocess.DEVNULL,
        )
        return [l for l in out.decode().splitlines() if l.endswith(".json")]
    except subprocess.CalledProcessError:
        return []


def _cat(uri: str) -> dict:
    out = subprocess.check_output(
        ["gcloud", "storage", "cat", uri], stderr=subprocess.DEVNULL
    )
    return json.loads(out.decode())


def latest_result(phase: str, ticker: str, tf: str, bucket: str) -> dict | None:
    """Return the most recent walk_forward_*.json for one cell."""
    prefix = f"gs://{bucket}/research/magnitude_engine/{phase}/{ticker.lower()}_{tf}/"
    files = _ls(prefix)
    if not files:
        return None
    # Latest by name (filename includes run_id which is monotonic ts or
    # Cloud Run execution name like magnitude-engine-XXXXX — lex-sorted
    # works for both).
    latest = sorted(files)[-1]
    return _cat(latest)


def per_phase_verdict(cells: dict[tuple[str, str], dict]) -> dict:
    """Apply the per-phase pass rule: ≥ N tickers pass per TF, on ≥ M TFs."""
    by_tf: dict[str, int] = {tf: 0 for tf in TIMEFRAMES}
    cell_pass_map: dict[tuple[str, str], bool] = {}
    for (ticker, tf), result in cells.items():
        passed = bool(result.get("gates", {}).get("cell_pass"))
        cell_pass_map[(ticker, tf)] = passed
        if passed:
            by_tf[tf] += 1
    passing_tfs = [
        tf for tf in TIMEFRAMES
        if by_tf[tf] >= SUCCESS_BAR_MIN_PASSING_TICKERS_PER_TF
    ]
    verdict = "PASS" if len(passing_tfs) >= 2 else "FAIL"
    return {
        "cell_pass_map": cell_pass_map,
        "by_tf": by_tf,
        "passing_tfs": passing_tfs,
        "verdict": verdict,
    }


def fmt_cell_table(phase: str, cells: dict[tuple[str, str], dict],
                    verdict: dict) -> str:
    lines = []
    lines.append(f"| ticker | 5m | 15m | 30m |")
    lines.append(f"|--------|----|-----|-----|")
    for t in TICKERS:
        row = [t]
        for tf in TIMEFRAMES:
            r = cells.get((t, tf))
            if not r:
                row.append("MISSING")
                continue
            g = r["gates"]
            ok = "✅ PASS" if g["cell_pass"] else "❌ FAIL"
            row.append(
                f"{ok}<br>"
                f"g1={g['g1_logloss_beat_folds']}/{g['n_ok_folds']} "
                f"g2={g['g2_ece_pass_folds']}/{g['n_ok_folds']} "
                f"g3={g['g3_monotone_folds']}/{g['n_ok_folds']} "
                f"g4={g['g4_lift_pass_folds']}/{g['n_ok_folds']}"
            )
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append(f"**Per-TF tickers passing**: "
                  + ", ".join(f"{tf}={verdict['by_tf'][tf]}/3" for tf in TIMEFRAMES))
    lines.append(f"**Phase {phase} verdict**: **{verdict['verdict']}** "
                  f"(passing TFs: {', '.join(verdict['passing_tfs']) or 'none'})")
    return "\n".join(lines)


def fmt_fold_detail(phase: str, cells: dict[tuple[str, str], dict]) -> str:
    """Per-fold table per cell (only OK folds)."""
    rows = []
    rows.append("```")
    rows.append(f"{'ticker':6} {'tf':4} {'fold':25} {'n_test':>6} {'beat':>8} "
                f"{'ece':>6} ece_pass {'lift':>8}")
    rows.append("-" * 78)
    for t in TICKERS:
        for tf in TIMEFRAMES:
            r = cells.get((t, tf))
            if not r:
                continue
            for f in r.get("folds", []):
                if f.get("status") != "OK":
                    rows.append(f"{t:6} {tf:4} {f['fold']:25} {f.get('status', '?')}")
                    continue
                lift = (f.get("explosive") or {}).get("lift")
                lift_s = f"{lift:8.2f}" if isinstance(lift, (int, float)) else "    —   "
                rows.append(
                    f"{t:6} {tf:4} {f['fold']:25} "
                    f"{f['n_test']:6d} {f['beat']:+8.4f} "
                    f"{f['ece']:6.4f} {str(f['ece_pass']):8} {lift_s}"
                )
    rows.append("```")
    return "\n".join(rows)


def assemble(phases: list[str], bucket: str) -> dict[str, dict]:
    """For each phase, pull all cells and compute verdicts."""
    results: dict[str, dict] = {}
    for phase in phases:
        cells: dict[tuple[str, str], dict] = {}
        for ticker in TICKERS:
            for tf in TIMEFRAMES:
                r = latest_result(phase, ticker, tf, bucket)
                if r is not None:
                    cells[(ticker, tf)] = r
        verdict = per_phase_verdict(cells)
        results[phase] = {"cells": cells, "verdict": verdict}
    return results


def render_markdown(results: dict[str, dict]) -> str:
    out = []
    out.append("# Magnitude Engine — Phase Results (auto-assembled)")
    out.append("")
    out.append("> This report is generated by `scripts/assemble_magnitude_results.py`")
    out.append("> from the per-cell `walk_forward_*.json` files in GCS. The gates")
    out.append("> applied are the pre-set bars in `mag_config.py` — they are NOT")
    out.append("> recomputed here, only re-aggregated per phase.")
    out.append("")
    overall_verdicts = []
    for phase, payload in results.items():
        v = payload["verdict"]["verdict"]
        overall_verdicts.append(f"- **{phase}**: {v}")
    out.append("## Verdict summary")
    out.append("")
    out.extend(overall_verdicts)
    out.append("")
    for phase, payload in results.items():
        out.append(f"## {phase}")
        out.append("")
        out.append(fmt_cell_table(phase, payload["cells"], payload["verdict"]))
        out.append("")
        out.append("### Per-fold detail")
        out.append("")
        out.append(fmt_fold_detail(phase, payload["cells"]))
        out.append("")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phases", default="phase0,phase1,phase3")
    p.add_argument("--bucket", default=GCS_BUCKET_DEFAULT)
    p.add_argument("--output", default=None,
                   help="If set, write markdown here. Otherwise print to stdout.")
    args = p.parse_args()
    phases = [p.strip() for p in args.phases.split(",")]
    results = assemble(phases, args.bucket)
    md = render_markdown(results)
    if args.output:
        Path(args.output).write_text(md)
        print(f"wrote {args.output} ({len(md)} bytes)", file=sys.stderr)
    else:
        print(md)


if __name__ == "__main__":
    main()
