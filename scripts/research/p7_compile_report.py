#!/usr/bin/env python3
"""Phase 7 — Compile final report from per-TF GCS analysis artifacts.

Reads the 9 CSVs per TF written by gcp/research/p7_analyze_tf.py from
gs://{BUCKET}/research/p7-analysis/{tf}/ and produces:

  - docs/research/2026-05-24/data/p7/{tf}_*.csv  (local mirror)
  - docs/research/2026-05-24/P7_multi_tf_dataset.md  (main report)
  - docs/research/2026-05-24/P7_reverify_prior_findings.md  (confirm/refute)

Run locally (or in any environment with GCS read access):
    python -m scripts.research.p7_compile_report
"""
from __future__ import annotations
import os
import sys
from io import StringIO
from pathlib import Path

import pandas as pd

from google.cloud import storage as gcs

ROOT = Path(__file__).parent.parent.parent
OUT_DATA = ROOT / "docs/research/2026-05-24/data/p7"
OUT_DOCS = ROOT / "docs/research/2026-05-24"
BUCKET = os.environ.get("GCS_BUCKET", "adept-mountain-474619-d4-trading-data")
PREFIX = "research/p7-analysis"
TFS = ["1m", "5m", "15m", "30m", "60m"]
FILES = [
    "01_strat_transition.csv",
    "02_combo_dealer_regime.csv",
    "03a_combo_vix.csv",
    "03b_combo_gex.csv",
    "03c_combo_vex.csv",
    "04_indicator_correlations.csv",
    "05a_model_walkforward.csv",
    "05b_model_summary.csv",
    "05c_feature_importance_top50.csv",
]


def _pull():
    client = gcs.Client()
    bucket = client.bucket(BUCKET)
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    pulled = {}
    for tf in TFS:
        pulled[tf] = {}
        for f in FILES:
            blob = bucket.blob(f"{PREFIX}/{tf}/{f}")
            try:
                data = blob.download_as_text()
                df = pd.read_csv(StringIO(data))
                pulled[tf][f] = df
                # Mirror to local
                df.to_csv(OUT_DATA / f"{tf}_{f}", index=False)
            except Exception as e:
                print(f"  {tf}/{f}: {e.__class__.__name__}")
    return pulled


def _format_summary(pulled: dict) -> str:
    """Build the main P7 markdown report."""
    lines = ["# Phase 7 — Multi-TF Strat-Sequence Dataset: Findings\n"]
    lines.append("**Date:** 2026-05-24\n")
    lines.append("**Pipeline:** `gcp/research/p7_build_multi_tf_features.py` (build) → ")
    lines.append("`gcp/research/p7_analyze_tf.py` (per-TF analysis, parallel) → this report\n\n")
    lines.append("## TL;DR\n\n")
    lines.append("(populated by inspecting the artifacts)\n\n")

    lines.append("## 1. Model walk-forward summary (cross-TF view)\n\n")
    lines.append("Mean IC + cost-adjusted Sharpe across 5 purged walk-forward folds per TF:\n\n")
    lines.append("| TF | model | mean_IC | rank_IC | LS Sharpe | LS bps/day | LS win |\n")
    lines.append("|---|---|---|---|---|---|---|\n")
    for tf in TFS:
        s = pulled.get(tf, {}).get("05b_model_summary.csv")
        if s is None or s.empty:
            continue
        for _, row in s.iterrows():
            lines.append(f"| {tf} | {row['model']} | {row.get('mean_ic')} | "
                          f"{row.get('mean_rank_ic')} | {row.get('mean_ls_sharpe')} | "
                          f"{row.get('mean_ls_bps')} | {row.get('mean_ls_win')} |\n")

    lines.append("\n## 2. Top features by LGBM gain (per TF)\n\n")
    for tf in TFS:
        fi = pulled.get(tf, {}).get("05c_feature_importance_top50.csv")
        if fi is None or fi.empty:
            continue
        lines.append(f"### {tf}\n\n")
        lines.append("| rank | feature | gain |\n|---|---|---|\n")
        for i, row in fi.head(10).iterrows():
            lines.append(f"| {i+1} | `{row['feature']}` | {row['gain']:.0f} |\n")
        lines.append("\n")

    lines.append("\n## 3. Strat-combo predictability per TF (top 5 by |hit_pct - 50|)\n\n")
    for tf in TFS:
        tg = pulled.get(tf, {}).get("01_strat_transition.csv")
        if tg is None or tg.empty:
            continue
        lines.append(f"### {tf} — top extreme cells (prev → curr → fwd hit%)\n\n")
        tg2 = tg.copy()
        tg2["edge"] = (tg2["hit_pct"] - 50).abs()
        top = tg2.sort_values("edge", ascending=False).head(8)
        lines.append("| ticker | prev | curr | n | mean_bps | hit_pct |\n|---|---|---|---|---|---|\n")
        for _, row in top.iterrows():
            lines.append(f"| {row['ticker']} | {row['prev_strat_candle']} | {row['strat_candle']} | "
                          f"{row['n']} | {row['mean_bps']:.2f} | {row['hit_pct']:.2f} |\n")
        lines.append("\n")

    lines.append("\n## 4. Strat-combo × dealer_regime (3×3 GEX × VEX grid) — top edges per TF\n\n")
    for tf in TFS:
        cd = pulled.get(tf, {}).get("02_combo_dealer_regime.csv")
        if cd is None or cd.empty:
            continue
        lines.append(f"### {tf}\n\n")
        cd2 = cd.copy()
        cd2["edge"] = (cd2["hit_pct"] - 50).abs()
        top = cd2[cd2["n"] >= 50].sort_values("edge", ascending=False).head(10)
        lines.append("| ticker | combo | dealer_regime | n | hit_pct | ci_lo | ci_hi | mean_bps |\n")
        lines.append("|---|---|---|---|---|---|---|---|\n")
        for _, row in top.iterrows():
            lines.append(f"| {row['ticker']} | {row['strat_combo']} | {row['dealer_regime']} | "
                          f"{row['n']} | {row['hit_pct']:.2f} | {row['hit_ci_lo']:.2f} | "
                          f"{row['hit_ci_hi']:.2f} | {row['mean_bps']:.2f} |\n")
        lines.append("\n")

    return "".join(lines)


def _format_reverify(pulled: dict) -> str:
    """Reverify the 4 priority-1 findings from P6."""
    lines = ["# Phase 7 — Reverification of Prior-Audit Priority-1 Findings\n\n"]
    lines.append("Each row below was a P2/P3/P5 finding flagged as production-actionable in ")
    lines.append("`docs/research/2026-05-23/P6_synthesis.md` §3. P7 reruns the same calculation ")
    lines.append("against the new bar-level dataset to verify or refute.\n\n")
    lines.append("| original finding | reverification cell | replicated? | notes |\n")
    lines.append("|---|---|---|---|\n")

    # Finding 1: 212_bear_continuation × HIGH-VIX, 5d
    sub = pulled.get("60m", {}).get("03a_combo_vix.csv")
    note = "no data"
    if sub is not None and not sub.empty:
        cell = sub[(sub["strat_combo"]=="212_bear_continuation") & (sub["vix_tercile"]=="HIGH")]
        if not cell.empty:
            avg_hit = (cell["hit_pct"] * cell["n"]).sum() / cell["n"].sum()
            note = f"hit_pct = {avg_hit:.1f}% on n={int(cell['n'].sum())} 60m fwd-5bars events"
    lines.append(f"| P3: 212_bear_continuation × HIGH-VIX, 5d, +5.15pp | 60m × fwd_5bars × VIX_HIGH | {note} | |\n")

    # Finding 2: clean_2d_bear × HIGH-VIX, 5d
    note = "no data"
    if sub is not None and not sub.empty:
        cell = sub[(sub["strat_combo"]=="clean_2d_bear") & (sub["vix_tercile"]=="HIGH")]
        if not cell.empty:
            avg_hit = (cell["hit_pct"] * cell["n"]).sum() / cell["n"].sum()
            note = f"hit_pct = {avg_hit:.1f}% on n={int(cell['n'].sum())}"
    lines.append(f"| P3: clean_2d_bear × HIGH-VIX, 5d, +5.05pp | 60m × fwd_5bars × VIX_HIGH | {note} | |\n")

    # Finding 3: 322_bull_continuation, 5d, anti-predictive
    note = "no data"
    if sub is not None and not sub.empty:
        cell = sub[sub["strat_combo"]=="322_bull_continuation"]
        if not cell.empty:
            avg_hit = (cell["hit_pct"] * cell["n"]).sum() / cell["n"].sum()
            note = f"hit_pct = {avg_hit:.1f}% on n={int(cell['n'].sum())}"
    lines.append(f"| P3: 322_bull_continuation, 5d, -2.79pp (anti) | 60m × fwd_5bars (all VIX) | {note} | |\n")

    # Finding 4: flip-PUT 76.7% non-replication — at intraday level the gamma_events events
    # aren't in strat_features_* directly. Cross-reference via SQL join (TODO).
    lines.append("| P5: flip_cross PUT × FTFC-DOWN at 15m, live=76.7% | needs gamma_events ⋈ strat_features_5m join | TODO | requires SQL via db-query.yml |\n")

    return "".join(lines)


def main():
    print("Pulling P7 analysis artifacts from GCS...")
    pulled = _pull()
    found = sum(len(v) for v in pulled.values())
    print(f"Found {found} artifacts across {len(TFS)} TFs.")
    if found == 0:
        print("No artifacts yet — wait for the per-TF analyze_tf jobs to complete first.")
        return 1

    OUT_DOCS.mkdir(parents=True, exist_ok=True)
    (OUT_DOCS / "P7_multi_tf_dataset.md").write_text(_format_summary(pulled))
    (OUT_DOCS / "P7_reverify_prior_findings.md").write_text(_format_reverify(pulled))
    print(f"Wrote {OUT_DOCS}/P7_multi_tf_dataset.md and P7_reverify_prior_findings.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
