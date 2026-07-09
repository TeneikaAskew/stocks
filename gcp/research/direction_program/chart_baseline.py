"""Chart the 3-axis baseline (folds-beat per axis, per ticker) via the shared
small-multiples tool."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from scripts.magnitude_result_charts import small_multiples
from gcp.research.direction_program.slice_ledger import SliceLedger


def beats_to_panels(ledger_rows: list) -> dict:
    panels: dict = {}
    for r in ledger_rows:
        panels.setdefault(r["ticker"], {})[r["target"]] = [r["n_folds_beat"]]
    return panels


def chart_baseline(ledger_path: str, out_path: str) -> str:
    rows = SliceLedger(ledger_path).rows()
    panels = beats_to_panels(rows)
    axes = sorted({r["target"] for r in rows})
    return small_multiples(
        panels, axes, [0], out_path,
        title="Pure-prediction baseline — folds beating base rate (of 8)",
        subtitle="direction / size / type · purged walk-forward · pass bar = >=6/8 folds AND all 3 tickers",
        xlabel="", ylabel="folds beating base rate", pct=False, base_rate=6, ncols=3)
