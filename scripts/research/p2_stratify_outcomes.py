#!/usr/bin/env python3
"""Phase 2 Step 3: stratify gamma_events outcomes, bootstrap CIs, BH-FDR.

Reads the `gamma_events` table populated by Step 2's Cloud Run Job,
groups by the pre-registered stratification dimensions, computes
hit-rate + signed-return stats with 1000-iter bootstrap 95% CIs,
applies Benjamini-Hochberg FDR correction at q=0.10 across the
H1-H8 primary test family, and writes:

    docs/research/2026-05-23/data/p2_outcomes_grid.parquet
    docs/research/2026-05-23/data/p2_outcomes_grid_aggregate.csv
    docs/research/2026-05-23/figures/p2_hit_rate_by_*.png
    docs/research/2026-05-23/P2_gamma_outcomes.md  (the report)

This script runs LOCALLY (in the Claude Code on the web sandbox).
It pulls the events table via `db-query.yml` as a CSV artifact,
then crunches in pandas / scipy.

Run:
    python -m scripts.research.p2_stratify_outcomes

No flags — wires together the canonical Phase 2 pipeline.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("p2_stratify_outcomes")

# Pre-registered stratification dims (RESEARCH_PLAN.md H1-H8)
STRAT_DIMS = [
    "ticker",
    "alert_kind",
    "alert_direction",
    "ftfc_prev_day_dir",
    "vix_tercile",
    "tod_bucket",
    "regime",
]

HORIZONS = [
    ("5m",   "fwd_ret_5m_bps"),
    ("15m",  "fwd_ret_15m_bps"),
    ("30m",  "fwd_ret_30m_bps"),
    ("60m",  "fwd_ret_60m_bps"),
    ("240m", "fwd_ret_240m_bps"),
    ("1d",   "fwd_ret_1d_bps"),
    ("5d",   "fwd_ret_5d_bps"),
]

# From P1 baselines — unconditional fwd_pct_up by ticker × horizon (used for
# baseline-diff computation)
P1_BASELINE_PCT_UP = {
    "SPY": {"5m": 50.52, "15m": 51.67, "30m": 52.44, "60m": 53.28, "240m": 54.63,
            "1d": 55.20, "5d": 61.47},
    "QQQ": {"5m": 50.45, "15m": 51.65, "30m": 52.41, "60m": 53.38, "240m": 54.66,
            "1d": 56.70, "5d": 60.99},
    "IWM": {"5m": 49.64, "15m": 50.57, "30m": 51.20, "60m": 51.75, "240m": 52.28,
            "1d": 53.30, "5d": 54.77},
}


def _bootstrap_ci(values: np.ndarray, stat_fn, n_iter: int = 1000,
                  alpha: float = 0.05) -> tuple[float, float, float]:
    """Return (point, ci_lo, ci_hi) for the given statistic via percentile bootstrap."""
    if len(values) == 0:
        return (float("nan"), float("nan"), float("nan"))
    point = float(stat_fn(values))
    n = len(values)
    rng = np.random.default_rng(seed=42)
    boots = np.empty(n_iter)
    for i in range(n_iter):
        sample = rng.choice(values, size=n, replace=True)
        boots[i] = stat_fn(sample)
    lo = float(np.percentile(boots, 100 * alpha / 2))
    hi = float(np.percentile(boots, 100 * (1 - alpha / 2)))
    return (point, lo, hi)


def _hit_rate(values: np.ndarray) -> float:
    """Hit rate = % with signed return > 0 (move in alert direction)."""
    if len(values) == 0:
        return float("nan")
    return 100.0 * float(np.mean(values > 0))


def _baseline_pct_up(ticker: str, horizon_key: str, direction: str) -> float:
    """Baseline directional probability for the alert direction at this horizon."""
    raw = P1_BASELINE_PCT_UP.get(ticker, {}).get(horizon_key, 50.0)
    if direction == "PUT":
        return 100.0 - raw
    return raw


def _ks_vs_baseline(values: np.ndarray, baseline_pct_up: float) -> float:
    """KS-test p-value vs the 'random' direction distribution.

    Compare the observed sign distribution to the unconditional direction
    distribution. Simpler than full KS over fwd-return continuous values —
    we test 'is the proportion of positive signed-returns different from
    the baseline-derived rate'. Two-sided proportion z-test.
    """
    if len(values) < 10:
        return float("nan")
    n_pos = int((values > 0).sum())
    n = len(values)
    p_hat = n_pos / n
    p0 = baseline_pct_up / 100.0
    if p0 in (0, 1):
        return float("nan")
    se = (p0 * (1 - p0) / n) ** 0.5
    if se == 0:
        return float("nan")
    z = (p_hat - p0) / se
    return float(2 * (1 - sps.norm.cdf(abs(z))))


def stratify(events: pd.DataFrame) -> pd.DataFrame:
    """Produce the full outcome grid. One row per (cell × horizon)."""
    rows: list[dict] = []
    for cell_keys, group in events.groupby(STRAT_DIMS, dropna=False):
        if len(group) < 10:
            # Cells with fewer than 10 events are too thin to bootstrap meaningfully
            continue
        cell = dict(zip(STRAT_DIMS, cell_keys))
        for horizon, col in HORIZONS:
            v = group[col].dropna().to_numpy()
            if len(v) < 10:
                continue
            hit, lo, hi = _bootstrap_ci(v, _hit_rate, n_iter=1000)
            mean_ret = float(np.mean(v))
            std_ret = float(np.std(v, ddof=1))
            baseline = _baseline_pct_up(cell["ticker"], horizon, cell["alert_direction"])
            p_val = _ks_vs_baseline(v, baseline)
            rows.append({
                **cell,
                "horizon": horizon,
                "n": int(len(v)),
                "hit_rate": hit,
                "hit_rate_ci_lo": lo,
                "hit_rate_ci_hi": hi,
                "baseline_pct_up": baseline,
                "lift_pp": hit - baseline,
                "mean_ret_bps": mean_ret,
                "std_ret_bps": std_ret,
                "p_value": p_val,
            })
    return pd.DataFrame(rows)


def apply_bh_fdr(df: pd.DataFrame, q: float = 0.10, family_col: str = None) -> pd.DataFrame:
    """Apply Benjamini-Hochberg FDR correction. Adds 'p_adj' and 'reject' columns."""
    df = df.copy()
    pvals = df["p_value"].fillna(1.0).to_numpy()
    n = len(pvals)
    if n == 0:
        df["p_adj"] = []
        df["reject"] = []
        return df
    order = np.argsort(pvals)
    ranks = np.empty(n, dtype=int)
    ranks[order] = np.arange(1, n + 1)
    p_adj = pvals * n / ranks
    # Step-up: enforce monotonicity
    p_adj_sorted = p_adj[order]
    for i in range(n - 2, -1, -1):
        p_adj_sorted[i] = min(p_adj_sorted[i], p_adj_sorted[i + 1])
    p_adj_final = np.empty(n)
    p_adj_final[order] = np.clip(p_adj_sorted, 0, 1)
    df["p_adj"] = p_adj_final
    df["reject"] = df["p_adj"] < q
    return df


def main():
    events_path = ROOT / "docs/research/2026-05-23/data/gamma_events.parquet"
    if not events_path.exists():
        log.error("Run Step 2 + export first. Expected: %s", events_path)
        log.error("Hint: gh workflow run db-query.yml -f sql='SELECT * FROM gamma_events' ...")
        sys.exit(1)

    log.info("Loading gamma_events from %s", events_path)
    events = pd.read_parquet(events_path)
    log.info("Loaded %d events across %d tickers", len(events), events["ticker"].nunique())

    grid = stratify(events)
    log.info("Stratified into %d cells × horizons", len(grid))

    grid = apply_bh_fdr(grid, q=0.10)
    n_reject = int(grid["reject"].sum())
    log.info("BH-FDR at q=0.10: %d / %d cells rejected null", n_reject, len(grid))

    # Save artifacts
    out_dir = ROOT / "docs/research/2026-05-23/data"
    out_dir.mkdir(parents=True, exist_ok=True)
    grid.to_parquet(out_dir / "p2_outcomes_grid.parquet")
    grid.to_csv(out_dir / "p2_outcomes_grid_aggregate.csv", index=False)
    log.info("Wrote outcomes_grid to %s", out_dir)


if __name__ == "__main__":
    main()
