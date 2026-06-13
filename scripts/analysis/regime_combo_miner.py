"""Effort A — General regime combination miner (ticker-interchangeable).

Finds the indicator-value COMBINATIONS that best predict, out-of-sample, the
next move's regime:
  * direction : UP / DOWN / FLAT (sideways/inside)
  * magnitude : BIG / SMALL

This is the productionised, ticker-parameterised version of the session
prototype. It reuses the shared math core (`lib.combo_mining`) and the
production indicator engine (`gcp.indicator_correlation_job.enrich`), so no
combo logic or indicator math is re-implemented (CLAUDE.md Rule 3.6).

Leakage discipline:
  * forward returns are strictly causal, per-session (enrich/add_forward_returns)
  * regime FLAT/BIG thresholds are quantiles of |return| fit on TRAIN rows only
  * model features are the stationary whitelist + candidate features; absolute
    price columns are excluded; intrabar-range features enter LAGGED by 1 bar
  * time-split: oldest `--train-frac` of bars TRAIN, newest TEST

Usage:
    python -m scripts.analysis.regime_combo_miner --ticker IWM
    python -m scripts.analysis.regime_combo_miner --ticker SPY,QQQ --horizons 15,30
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib import combo_mining as cm  # noqa: E402
from lib.config import IndicatorConfig  # noqa: E402
from gcp.indicator_correlation_job import enrich, _RETURN_PREFIX  # noqa: E402
from scripts.analysis.shared_utils import (  # noqa: E402
    load_ticker_1m, md_header, md_table, save_report, timestamp_str, progress,
)

DIRECTION_CLASSES = ["UP", "DOWN", "FLAT"]
MAGNITUDE_CLASSES = ["BIG"]  # SMALL is the complement; we mine the BIG side


def label_regimes(sub: pd.DataFrame, ret_col: str, train_mask: np.ndarray,
                  flat_q: float = 0.34, big_q: float = 0.66):
    """Direction (UP/DOWN/FLAT) + magnitude (BIG/SMALL) from forward return.

    Thresholds learned on TRAIN only: tau_flat = flat_q quantile of |ret|,
    tau_big = big_q quantile of |ret|.
    """
    r = sub[ret_col].astype(float)
    a = r.abs()
    tau_flat = a[train_mask].quantile(flat_q)
    tau_big = a[train_mask].quantile(big_q)
    direction = np.where(a <= tau_flat, "FLAT", np.where(r > 0, "UP", "DOWN"))
    magnitude = np.where(a >= tau_big, "BIG", "SMALL")
    return (pd.Series(direction, index=sub.index),
            pd.Series(magnitude, index=sub.index), tau_flat, tau_big)


def run_ticker(ticker: str, horizons: List[int], train_frac: float,
               min_support: int, top_k: int, max_order: int) -> str:
    cfg = IndicatorConfig()
    progress(f"loading {ticker} 1-min bars", ticker)
    raw = load_ticker_1m(ticker)
    if raw is None or raw.empty:
        return md_header(f"{ticker} — NO DATA", 2) + "\nNo intraday data available.\n"

    enr = enrich(raw, cfg, horizons)
    enr = cm.add_candidate_features(enr, cfg)
    feats = cm.stationary_feature_filter(enr.columns)

    lines = [md_header(f"Regime combination predictors — {ticker}", 1), ""]
    days = sorted(set(pd.to_datetime(enr["Time"]).dt.date)) if "Time" in enr else []
    lines.append(f"_Generated {timestamp_str()}_  ")
    lines.append(f"Sample: {len(enr):,} RTH bars over {len(days)} sessions "
                 f"({days[0]} .. {days[-1]})  " if days else "")
    lines.append(f"Features in model ({len(feats)}, stationary + candidates): "
                 f"{', '.join(feats)}")
    lines.append("")
    lines.append("**Method.** Production indicator engine + candidate features; "
                 "strictly-causal per-session forward log-returns; time-split OOS "
                 f"(oldest {train_frac:.0%} train / newest TEST); FLAT/BIG bands and "
                 "combo medians fit on TRAIN only. Lift = OOS hit-rate / base rate.")
    lines.append("")

    for h in horizons:
        ret_col = f"{_RETURN_PREFIX}{h}"
        sub = enr.dropna(subset=[ret_col]).copy()
        if len(sub) < 2000:
            lines.append(f"## Horizon {h}m — insufficient bars ({len(sub)})\n")
            continue
        cut = pd.to_datetime(sub["Time"]).quantile(train_frac)
        train_mask = (pd.to_datetime(sub["Time"]) <= cut).to_numpy()
        test_mask = ~train_mask
        direction, magnitude, tau_flat, tau_big = label_regimes(sub, ret_col, train_mask)

        lines.append(md_header(f"Horizon = {h} minutes", 2))
        lines.append(f"Train {int(train_mask.sum()):,} / Test {int(test_mask.sum()):,} "
                     f"bars (split @ {pd.Timestamp(cut).date()}). "
                     f"FLAT |move| ≤ {tau_flat*100:.3f}%, BIG |move| ≥ {tau_big*100:.3f}%.")
        lines.append("")

        # Model lift + permutation importance for each target.
        for name, lab in [("direction", direction), ("magnitude", magnitude)]:
            ml = cm.model_lift(sub, feats, lab, train_mask, test_mask, name)
            mix = ", ".join(f"{k}={v:.3f}" for k, v in ml.class_mix.items())
            lines.append(f"**{name.upper()}** — OOS acc {ml.oos_accuracy:.4f} vs "
                         f"base {ml.base_rate:.4f} (lift {ml.lift:.3f}×). Mix: {mix}")
            top = list(ml.perm_importance.items())[:8]
            lines.append("Top features: " + ", ".join(f"{f} {v:+.4f}" for f, v in top))
            lines.append("")

        # Interpretable combos per regime class.
        for cls, lab, tgt_metric in [
            ("UP", direction, sub[ret_col]),
            ("DOWN", direction, sub[ret_col]),
            ("FLAT", direction, -sub[ret_col].abs()),
            ("BIG", magnitude, sub[ret_col].abs()),
        ]:
            top_feats = cm.select_top_features(sub, feats, tgt_metric, train_mask,
                                               k=10, method="spearman")
            combos = cm.mine_combos(sub, top_feats, lab, cls, train_mask, test_mask,
                                    max_order=max_order, min_support=min_support,
                                    top_k=top_k)
            lines.append(md_header(f"Best combos → {cls} ({h}m)", 3))
            if not combos:
                lines.append("_No combos cleared the support floor._\n")
                continue
            rows = [[f"{c.hit_rate:.3f}", f"{c.lift:.2f}", str(c.support),
                     " AND ".join(c.conditions)] for c in combos]
            lines.append(md_table(["hit", "lift", "n", "conditions"], rows))
            lines.append("")

    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ticker", default="IWM",
                    help="Comma-separated tickers (default IWM).")
    ap.add_argument("--horizons", default="5,15,30,60",
                    help="Forward-return horizons in minutes (default 5,15,30,60).")
    ap.add_argument("--train-frac", type=float, default=0.70)
    ap.add_argument("--min-support", type=int, default=3000)
    ap.add_argument("--top-k", type=int, default=12)
    ap.add_argument("--max-order", type=int, default=3)
    args = ap.parse_args(argv)

    tickers = [t.strip().upper() for t in args.ticker.split(",") if t.strip()]
    horizons = sorted({int(h) for h in args.horizons.split(",") if h.strip()})

    for tk in tickers:
        report = run_ticker(tk, horizons, args.train_frac, args.min_support,
                            args.top_k, args.max_order)
        save_report(report, f"regime_combo_predictors_{tk}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
